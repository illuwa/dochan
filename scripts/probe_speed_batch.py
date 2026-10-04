"""고정 공개 표본의 배치 처리량·해시·CPU/RSS를 측정한다 (표준 라이브러리만 사용)."""

import argparse
import cProfile
import hashlib
import json
import logging
import os
import pickle
import platform
import pstats
import random
import re
import resource
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


DEFAULT_COUNTS = {"hwp": 2000, "hwpx": 1000, "pdf": 500, "docx": 500,
                  "pptx": 200, "xlsx": 200, "xls": 200}
PUBLIC_ROOTS = (
    "hwp-public/hwp", "hwp-public/hwpx", "press-pairs",
    "pdfjs-src/test/pdfs", "poi-src/test-data/document",
    "poi-src/test-data/slideshow", "poi-src/test-data/spreadsheet",
    "lo-src/sw/qa", "lo-src/sd/qa",
)
_PROCESS_SINGLE = None


def select_sample(corpus, counts, seed):
    """내부 문서와 구현 소스를 읽지 않고 공개 입력 파일만 선정한다."""
    candidates = {extension: [] for extension in counts}
    for relative in PUBLIC_ROOTS:
        root = corpus / relative
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            extension = path.suffix.lower().lstrip(".")
            if extension in candidates and path.is_file() and not path.is_symlink():
                candidates[extension].append(path.relative_to(corpus).as_posix())
    rng = random.Random(seed)
    selected = []
    for extension, count in counts.items():
        paths = sorted(set(candidates[extension]))
        if len(paths) < count:
            raise ValueError("{}: requested {}, available {}".format(
                extension, count, len(paths)))
        selected.extend(rng.sample(paths, count))
    return sorted(selected)


def _profile_summary(profiler):
    stats = pstats.Stats(profiler)
    stages = {"_collect_sources", "_plan_outputs", "_copy_exact_source",
              "_private_source_snapshot", "_atomic_write_text", "submit",
              "info", "error", "_parse_dispatch", "to_json", "to_markdown",
              "to_plain_text", "<built-in method posix.fsync>",
              "<built-in method _pickle.dumps>"}
    stage_rows = [{"file": Path(key[0]).name, "function": key[2],
                   "calls": value[1], "self_seconds": value[2],
                   "cumulative_seconds": value[3]}
                  for key, value in stats.stats.items() if key[2] in stages]
    return {"total_seconds": stats.total_tt, "stages": stage_rows, "top": [
        {"file": Path(key[0]).name, "line": key[1], "function": key[2],
         "calls": value[1], "self_seconds": value[2], "cumulative_seconds": value[3]}
        for key, value in sorted(stats.stats.items(), key=lambda item: item[1][3],
                                 reverse=True)[:35]]}


def _timed_process_single(*args, **kwargs):
    """실제 작업자 쓰기 후 해시만 보관하고 출력을 즉시 삭제한다."""
    import dochan.batch as batch

    process = _PROCESS_SINGLE or batch._process_single
    if process is _timed_process_single:
        raise RuntimeError("recursive benchmark instrumentation")
    started = time.perf_counter()
    wall_started = time.time()
    cpu_started = time.process_time()
    write_seconds = []
    original_write = batch._atomic_write_text

    def timed_write(*write_args, **write_kwargs):
        before = time.perf_counter()
        try:
            return original_write(*write_args, **write_kwargs)
        finally:
            write_seconds.append(time.perf_counter() - before)

    profiler = cProfile.Profile() if os.environ.get("DOCHAN_BATCH_PROBE_PROFILE") else None
    if profiler:
        profiler.enable()
    import_started = time.perf_counter()
    __import__("dochan.reader")
    import_seconds = time.perf_counter() - import_started
    with patch.object(batch, "_atomic_write_text", timed_write):
        result = process(*args, **kwargs)
    if profiler:
        profiler.disable()
    completed = time.perf_counter()
    wall_completed = time.time()
    cpu_seconds = time.process_time() - cpu_started
    digest = None
    output_bytes = 0
    hash_started = time.perf_counter()
    if result.success:
        output = Path(result.output_path)
        try:
            hasher = hashlib.sha256()
            with output.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
                    output_bytes += len(block)
            digest = hasher.hexdigest()
        finally:
            output.unlink()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result_pickle_bytes = len(pickle.dumps(result))
    result._probe = {
        "pid": os.getpid(), "start": wall_started, "end": wall_completed,
        "seconds": completed - started, "cpu_seconds": cpu_seconds,
        "lifetime_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "max_rss_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "write_seconds": sum(write_seconds), "output_sha256": digest,
        "output_bytes": output_bytes, "hash_seconds": time.perf_counter() - hash_started,
        "import_seconds": import_seconds, "result_pickle_bytes": result_pickle_bytes,
    }
    if profiler:
        result._probe["profile"] = _profile_summary(profiler)
    return result


class _MemorySampler:
    """ps로 측정 프로세스와 자손의 RSS 합계를 0.5초 간격으로 관찰한다."""

    def __init__(self):
        self.peak_kib = 0
        self.worker_peak_kib = {}
        self.errors = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop.is_set():
            try:
                # nosemgrep: dangerous-subprocess-use-audit
                data = subprocess.check_output(
                    ["ps", "-axo", "pid=,ppid=,rss=,comm="], text=True)
                rows = {}
                for line in data.splitlines():
                    fields = line.split(None, 3)
                    if len(fields) == 4:
                        rows[int(fields[0])] = (int(fields[1]), int(fields[2]), fields[3])
                descendants = {os.getpid()}
                for _ in range(8):
                    added = {pid for pid, (parent, _, _) in rows.items()
                             if parent in descendants}
                    if added.issubset(descendants):
                        break
                    descendants.update(added)
                values = {pid: rows[pid][1] for pid in descendants if pid in rows
                          and Path(rows[pid][2]).name != "ps"}
                self.peak_kib = max(self.peak_kib, sum(values.values()))
                for pid, rss in values.items():
                    self.worker_peak_kib[pid] = max(self.worker_peak_kib.get(pid, 0), rss)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                self.errors.append(type(exc).__name__)
                break
            self.stop.wait(0.5)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()


def _normalize_error(value, corpus, output):
    value = value.replace(str(corpus), "<corpus>").replace(str(output), "<output>")
    return re.sub(r"[^\s'\"]*/dochan-batch-[^/\s]+/source", "<snapshot>/source", value)


def measure(corpus, temporary, selected, workers, output_format, profile=False,
            log=False):
    import dochan.batch as batch

    global _PROCESS_SINGLE
    _PROCESS_SINGLE = batch._process_single
    collect = batch._collect_sources
    wanted = set(selected)
    collection_seconds = []

    def selected_sources(input_root, output_root, extensions):
        # 링크 허용으로 보안을 완화하지 않는다. 원본의 기존 descriptor 수집을
        # 그대로 사용하고, 공통 corpus 루트에 대한 identity/상대 경로로 재표현한다.
        started = time.perf_counter()
        root_stat = input_root.stat()
        rows = []
        for relative in PUBLIC_ROOTS:
            source_root = input_root / relative
            if not source_root.is_dir():
                continue
            for source, _, identity in collect(source_root, output_root, extensions):
                source_relative = source.relative_to(input_root)
                if source_relative.as_posix() in wanted:
                    rows.append((source, source_relative, replace(
                        identity, root_device=root_stat.st_dev, root_inode=root_stat.st_ino)))
        if len(rows) != len(wanted):
            raise ValueError("sample disappeared or changed: {} != {}".format(
                len(rows), len(wanted)))
        collection_seconds.append(time.perf_counter() - started)
        return rows

    if log:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("dochan").setLevel(logging.INFO if log else logging.CRITICAL)
    if profile and workers > 1:
        os.environ["DOCHAN_BATCH_PROBE_PROFILE"] = "1"
    else:
        os.environ.pop("DOCHAN_BATCH_PROBE_PROFILE", None)
    profiler = cProfile.Profile() if profile else None
    with TemporaryDirectory(prefix="output-", dir=str(temporary)) as name:
        output = Path(name)
        if profiler:
            profiler.enable()
        started = time.perf_counter()
        wall_started = time.time()
        cpu_started = time.process_time()
        with _MemorySampler() as memory:
            with patch.object(batch, "_collect_sources", selected_sources), \
                    patch.object(batch, "_process_single", _timed_process_single):
                summary = batch.batch_convert(str(corpus), str(output), output_format,
                                              max_workers=workers)
        elapsed = time.perf_counter() - started
        parent_cpu = time.process_time() - cpu_started
        if profiler:
            profiler.disable()
        records = {}
        per_worker = {}
        for result in summary.results:
            label = Path(result.file_path).relative_to(corpus).as_posix()
            telemetry = result._probe
            record = asdict(result)
            record["file_path"] = label
            record["output_path"] = (Path(result.output_path).relative_to(output).as_posix()
                                     if result.output_path else "")
            record["errors"] = [_normalize_error(error, corpus, output)
                                for error in record["errors"]]
            record.update({"sha256": telemetry["output_sha256"],
                           "bytes": telemetry["output_bytes"]})
            records[label] = record
            pid = telemetry["pid"]
            row = per_worker.setdefault(pid, {"files": 0, "cpu_seconds": 0,
                                              "busy_seconds": 0, "write_seconds": 0,
                                              "hash_seconds": 0, "max_rss_bytes": 0,
                                              "import_seconds": 0, "result_pickle_bytes": 0,
                                              "first_start": telemetry["start"],
                                              "last_end": telemetry["end"]})
            row["files"] += 1
            for target, source in (("cpu_seconds", "cpu_seconds"),
                                   ("busy_seconds", "seconds"),
                                   ("write_seconds", "write_seconds"),
                                   ("hash_seconds", "hash_seconds"),
                                   ("import_seconds", "import_seconds"),
                                   ("result_pickle_bytes", "result_pickle_bytes")):
                row[target] += telemetry[source]
            row["max_rss_bytes"] = max(row["max_rss_bytes"], telemetry["max_rss_bytes"])
            row["lifetime_cpu_seconds"] = max(row.get("lifetime_cpu_seconds", 0),
                                               telemetry["lifetime_cpu_seconds"])
            row["first_start"] = min(row["first_start"], telemetry["start"])
            row["last_end"] = max(row["last_end"], telemetry["end"])
        for row in per_worker.values():
            row["cpu_percent_of_run"] = row["cpu_seconds"] / elapsed * 100
            row["cpu_percent_while_busy"] = row["cpu_seconds"] / row["busy_seconds"] * 100
            row["first_task_delay_seconds"] = row.pop("first_start") - wall_started
            row["idle_tail_seconds"] = elapsed - (row.pop("last_end") - wall_started)
        top = sorted(summary.results, key=lambda result: result._probe["seconds"],
                     reverse=True)[:20]
        measurement = {
            "workers": workers, "format": output_format, "seconds": elapsed,
            "files_per_second": summary.total / elapsed,
            "total": summary.total, "success": summary.success, "failed": summary.failed,
            "parent_cpu_seconds": parent_cpu,
            "collection_seconds": sum(collection_seconds),
            "peak_tree_rss_mib": memory.peak_kib / 1024 if not memory.errors else None,
            "sum_worker_peak_rss_mib": sum(row["max_rss_bytes"] for row in per_worker.values()) / 1048576,
            "parent_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
                1048576 if sys.platform == "darwin" else 1024),
            "rss_sampling_errors": memory.errors,
            "per_worker": per_worker, "records": records,
            "slowest": [{"file": Path(result.file_path).relative_to(corpus).as_posix(),
                         **result._probe} for result in top],
        }
        if profiler:
            measurement["parent_profile"] = _profile_summary(profiler)
        return measurement


def compare_records(reference, actual):
    """시간·PID·완료 순서 외의 성공/실패·경고·경로·출력을 모두 비교한다."""
    names = set(reference) | set(actual)
    mismatches = [name for name in sorted(names) if reference.get(name) != actual.get(name)]
    return {"files": len(names), "identical": len(names) - len(mismatches),
            "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--temporary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path, help="기준 dochan 소스 스냅숏")
    parser.add_argument("--manifest", type=Path, help="기존 고정 표본 JSON")
    parser.add_argument("--reference", type=Path, help="해시·결과 비교 기준 측정 JSON")
    parser.add_argument("--counts", default=",".join(
        "{}={}".format(ext, count) for ext, count in DEFAULT_COUNTS.items()))
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--workers", default="1,4,8,12,15")
    parser.add_argument("--formats", default="markdown")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--log", action="store_true")
    args = parser.parse_args()
    if args.source:
        sys.path.insert(0, str(args.source.resolve()))
    corpus = args.corpus.resolve()
    temporary = args.temporary.resolve()
    temporary.mkdir(parents=True, exist_ok=True)
    if corpus == temporary or corpus in temporary.parents:
        parser.error("temporary directory must be outside corpus")
    counts = {ext: int(count) for ext, count in
              (value.split("=", 1) for value in args.counts.split(","))}
    if any(count < 0 for count in counts.values()):
        parser.error("counts must be nonnegative")
    selected = (json.loads(args.manifest.read_text())["sample"] if args.manifest
                else select_sample(corpus, counts, args.seed))
    if not selected or any(Path(name).is_absolute() or ".." in Path(name).parts
                           for name in selected):
        parser.error("sample must contain relative paths below corpus")
    reference = json.loads(args.reference.read_text()) if args.reference else None
    result = {"environment": {"platform": platform.platform(),
                               "python": platform.python_version(), "cpus": os.cpu_count()},
              "seed": args.seed, "sample": selected,
              "counts": dict(Counter(Path(name).suffix.lstrip(".") for name in selected)),
              "measurements": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="sample-", dir=str(temporary)) as links_name:
        links = Path(links_name)
        for index, name in enumerate(selected):
            (links / ("{:05d}{}".format(index, Path(name).suffix))).symlink_to(corpus / name)
        for output_format in args.formats.split(","):
            for workers in map(int, args.workers.split(",")):
                row = measure(corpus, temporary, selected, workers, output_format,
                              args.profile, args.log)
                if reference:
                    baseline = next(item for item in reference["measurements"]
                                    if item["format"] == output_format)
                    row["comparison"] = compare_records(baseline["records"], row["records"])
                serial = next((item for item in result["measurements"]
                               if item["workers"] == 1 and item["format"] == output_format), None)
                if serial:
                    row["parallel_efficiency_percent"] = serial["seconds"] / row["seconds"] / workers * 100
                    if not reference:
                        row["comparison"] = compare_records(serial["records"], row["records"])
                result["measurements"].append(row)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
                print(json.dumps({key: row[key] for key in
                                  ("workers", "format", "seconds", "files_per_second",
                                   "success", "failed", "peak_tree_rss_mib")}), flush=True)
    return int(any(row.get("comparison", {}).get("mismatches")
                   for row in result["measurements"]))


if __name__ == "__main__":
    raise SystemExit(main())
