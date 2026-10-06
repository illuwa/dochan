"""PDF 변환 시간과 출력 해시를 파일별 독립 프로세스로 측정한다.

예: python -m scripts.probe_speed_pdf corpus/pdfjs-src/test/pdfs corpus/press-pairs \
    --output .codex-work/pdf-before.json
"""
import argparse
import cProfile
import hashlib
import json
import math
import pstats
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _worker(path, profile=False):
    from dochan.reader import Dochan
    from dochan.pdf.content import CONTENT_SCANNER_BACKEND, CONTENT_INTERPRETER_BACKEND

    profiler = cProfile.Profile() if profile else None
    if profiler:
        profiler.enable()
    started = time.perf_counter()
    doc = Dochan(str(path))
    parsed = time.perf_counter()
    markdown = doc.to_markdown()
    rendered_md = time.perf_counter()
    json_text = doc.to_json()
    rendered_json = time.perf_counter()
    if profiler:
        profiler.disable()
    errors = json.dumps(doc.errors, ensure_ascii=False)
    result = {
        "content_scanner_backend": CONTENT_SCANNER_BACKEND,
        "content_interpreter_backend": CONTENT_INTERPRETER_BACKEND,
        "parse": parsed - started,
        "markdown": rendered_md - parsed,
        "json": rendered_json - rendered_md,
        "total": rendered_json - started,
        "markdown_sha256": _hash(markdown),
        "markdown_chars": len(markdown),
        "json_sha256": _hash(json_text),
        "json_chars": len(json_text),
        "errors_sha256": _hash(errors),
        "errors_count": len(doc.errors),
    }
    if profiler:
        stats = pstats.Stats(profiler)
        entries = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)
        result["profile_total"] = stats.total_tt
        result["profile"] = [
            {"function": "{}:{}:{}".format(*key), "calls": item[1],
             "self": item[2], "cumulative": item[3]}
            for key, item in entries[:50]
        ]
    return result


def _profile_stages(stats, compiled_only=False):
    """자기 시간만 나눈다. 누적 시간과 재귀 호출 시간은 더하지 않는다."""
    from dochan.pdf.content import ContentScanner, _Line, _Segment

    def method_keys(cls):
        keys = set()
        for value in vars(cls).values():
            value = getattr(value, "__func__", value)
            code = getattr(value, "__code__", None)
            if code is not None:
                keys.add((code.co_filename, code.co_firstlineno, code.co_name))
        return keys

    scanner_keys = method_keys(ContentScanner)
    line_keys = method_keys(_Line) | method_keys(_Segment)

    def category(key):
        filename, _line, name = key
        filename = filename.replace("\\", "/")
        module = filename.rsplit("/", 1)[-1]
        if compiled_only:
            return ("candidate_modules" if "/pdf/" in filename
                    and module in ("objects.py", "content.py", "paths.py") else "other")
        if ("/output/" in filename or "/json/encoder.py" in filename
                or module == "dataclasses.py" and name in ("asdict", "_asdict_inner")):
            return "output"
        if "/pdf/" not in filename:
            return "other"
        if module == "filters.py":
            return "filters"
        if module in ("objects.py", "structure.py"):
            return "objects"
        if module in ("annotations.py", "notes.py"):
            return "links_notes"
        if module in ("tables.py", "text_tables.py"):
            return "tables"
        if module in ("layout.py", "pagination.py", "running.py"):
            return "lines_paragraphs"
        if module == "paths.py":
            return "graphics_paths"
        if module == "content.py":
            if key in scanner_keys:
                return "scanner"
            if name in ("_show", "_show_vertical", "_iter_code_chunks", "_iter_codes",
                        "default_byte_decoder", "metrics", "_numbers"):
                return "glyphs_decode"
            if key in line_keys or name in ("assemble_lines", "_assemble_lines",
                                           "_in_writing_order", "along", "across",
                                           "writing_direction"):
                return "lines_paragraphs"
            return "graphics_paths"
        if module in ("widths.py", "cmap.py", "cid_unicode.py", "core14.py",
                      "font_program.py", "truetype.py"):
            return "glyphs_decode"
        return "other"

    stages = dict.fromkeys(("filters", "objects", "scanner", "graphics_paths",
                           "glyphs_decode", "lines_paragraphs", "tables",
                           "links_notes", "output", "other"), 0.0)
    if compiled_only:
        stages = {"candidate_modules": 0.0, "other": 0.0}
    for key, entry in stats.stats.items():
        _primitive, _calls, self_time, _cumulative, callers = entry
        if key[0] == "~" and callers:
            # C 함수의 자기 시간을 직접 호출자의 자기 시간 비율로 귀속한다.
            weights = [(caller, values[2]) for caller, values in callers.items()]
            total = sum(value for _caller, value in weights)
            if total > 0:
                for caller, value in weights:
                    stages[category(caller)] += self_time * value / total
                continue
        stages[category(key)] += self_time
    return stages


def _batch(paths, profile=False, backend="dochan", timeout=120):
    """한 번 import한 뒤 목록을 순회한다. 본문 대신 해시·개수만 저장한다."""
    import signal

    def expired(_signum, _frame):
        raise TimeoutError("file deadline exceeded")

    profiler = cProfile.Profile() if profile else None
    rows = []
    if backend == "pymupdf":
        import pymupdf
    else:
        __import__("dochan.reader")
    previous = signal.signal(signal.SIGALRM, expired)
    try:
        if profiler:
            profiler.enable()
        for index, path in enumerate(paths):
            signal.alarm(timeout)
            started = time.perf_counter()
            try:
                if backend == "pymupdf":
                    with pymupdf.open(str(path)) as document:
                        text = "\n".join(page.get_text() for page in document)
                    elapsed = time.perf_counter() - started
                    row = {"total": elapsed, "convert_md": elapsed,
                           "text_sha256": _hash(text), "text_chars": len(text)}
                else:
                    row = _worker(path)
                    row["convert_md"] = row["parse"] + row["markdown"]
            except Exception as exc:
                row = {"failure": type(exc).__name__, "total": time.perf_counter() - started}
            finally:
                signal.alarm(0)
            row["index"] = index
            rows.append(row)
    finally:
        if profiler:
            profiler.disable()
        signal.signal(signal.SIGALRM, previous)
    result = {"rows": rows, "backend": backend,
              "completed": sum("failure" not in row for row in rows),
              "total": sum(row["total"] for row in rows)}
    if backend == "dochan":
        result["loaded_modules"] = {
            name: Path(sys.modules["dochan.pdf." + name].__file__).name
            for name in ("objects", "content", "paths")}
        if "cscan" in sys.modules:
            result["loaded_modules"]["cscan"] = Path(sys.modules["cscan"].__file__).name
        for name in ("dochan.cfb", "dochan.hwp.records.para_text"):
            if name in sys.modules:
                result["loaded_modules"][name] = Path(sys.modules[name].__file__).name
    if profiler:
        stats = pstats.Stats(profiler)
        result["profile_total"] = stats.total_tt
        result["stages"] = _profile_stages(stats)
        result["compile_scope"] = _profile_stages(stats, compiled_only=True)
        result["profile_top"] = [
            {"module": Path(key[0]).name, "function": key[2], "line": key[1],
             "self": entry[2], "cumulative": entry[3]}
            for key, entry in sorted(stats.stats.items(), key=lambda item: item[1][3],
                                     reverse=True)[:30]]
    return result


def _run_one(path, timeout, profile=False, source=None):
    command = [sys.executable, "-m", "scripts.probe_speed_pdf", "--worker", str(path)]
    if profile:
        command.append("--profile-worker")
    try:
        # nosemgrep: dangerous-subprocess-use-audit
        run = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                             cwd=source)
        if run.returncode:
            return {"failure": "exit {}".format(run.returncode)}
        return json.loads(run.stdout)
    except subprocess.TimeoutExpired:
        return {"failure": "timeout"}
    except (OSError, ValueError) as exc:
        return {"failure": type(exc).__name__}


def _files(roots):
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(path for path in root.glob("*.pdf") if path.is_file())
    return sorted(set(files))


def _label(path, roots, internal_number):
    if path.parent.name == "test_pairs":
        return "internal-{:03d}".format(internal_number)
    for root in roots:
        if path == root or root in path.parents:
            return "{}/{}".format(root.name, path.name)
    return path.name


def _measure(paths, roots, workers, timeout):
    rows = {}
    labels = {}
    internal = 0
    for path in paths:
        if path.parent.name == "test_pairs":
            internal += 1
        labels[path] = _label(path, roots, internal)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, path, timeout): path for path in paths}
        for future in as_completed(futures):
            path = futures[future]
            rows[labels[path]] = future.result()
            if len(rows) % 200 == 0:
                print("measured {}/{}".format(len(rows), len(paths)), file=sys.stderr,
                      flush=True)
    return rows


def _repeat_top(rows, paths, roots, timeout, selected=None):
    lookup = {}
    internal = 0
    for path in paths:
        if path.parent.name == "test_pairs":
            internal += 1
        lookup[_label(path, roots, internal)] = path
    top = selected or sorted((label for label in rows if "total" in rows[label]),
                             key=lambda label: rows[label]["total"], reverse=True)[:30]
    for label in top:
        if rows[label].get("median3") is not None:
            continue
        samples = [rows[label]["total"]]
        for _ in range(2):
            repeat = _run_one(lookup[label], timeout)
            if "total" in repeat:
                samples.append(repeat["total"])
            elif "failure" in repeat:
                rows[label]["repeat_failure"] = repeat["failure"]
        rows[label]["repeats"] = samples
        rows[label]["median3"] = median(samples) if len(samples) == 3 else None
    return top, lookup


def _alternate_top(labels, lookup, source, timeout):
    """동일 표본의 이전·현재 코드를 AB/BA/AB 순서로 각각 세 번 잰다."""
    results = {}
    keys = ("markdown_sha256", "json_sha256", "errors_sha256")
    for label in labels:
        timings = {"before": [], "after": []}
        hashes_equal = True
        failures = []
        for repeat in range(3):
            pair = {}
            order = (("before", source), ("after", None))
            if repeat == 1:
                order = tuple(reversed(order))
            for version, cwd in order:
                row = _run_one(lookup[label], timeout, source=cwd)
                if "total" in row:
                    timings[version].append(row["total"])
                else:
                    failures.append("{}: {}".format(version, row.get("failure")))
                pair[version] = row
            hashes_equal = hashes_equal and all(
                pair["before"].get(key) == pair["after"].get(key) for key in keys)
        results[label] = {
            "before": timings["before"], "after": timings["after"],
            "median_before": median(timings["before"]) if len(timings["before"]) == 3 else None,
            "median_after": median(timings["after"]) if len(timings["after"]) == 3 else None,
            "hashes_equal": hashes_equal, "failures": failures,
        }
        print("alternated {}/{}".format(len(results), len(labels)), file=sys.stderr,
              flush=True)
    return results


def _summary(rows):
    groups = {}
    for label, row in rows.items():
        group = label.split("/", 1)[0] if "/" in label else "internal"
        groups.setdefault(group, []).append(row)
    groups["all"] = list(rows.values())
    result = {}
    for group, entries in groups.items():
        values = sorted(row["total"] for row in entries if "total" in row)
        result[group] = {"files": len(entries), "completed": len(values)}
        if values:
            result[group].update({"sum": sum(values), "mean": sum(values) / len(values),
                                  "median": median(values),
                                  "p95": values[math.ceil(len(values) * .95) - 1],
                                  "max": values[-1]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--profile-worker", action="store_true")
    parser.add_argument("--profile-top", action="store_true")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--existing", type=Path,
                        help="기존 전수 측정에 상위 반복·프로파일만 추가")
    parser.add_argument("--hash-only", action="store_true")
    parser.add_argument("--public-top", action="store_true",
                        help="공개 표본의 느린 상위 30개만 3회 중앙값 측정")
    parser.add_argument("--alternate-source", type=Path,
                        help="이전 코드 스냅숏 경로. 상위 표본을 이전/현재 교대 측정")
    parser.add_argument("--batch-list", type=Path,
                        help="경로 JSON 배열. 한 프로세스에서 순서대로 측정")
    parser.add_argument("--batch-profile", action="store_true")
    parser.add_argument("--backend", choices=("dochan", "pymupdf"), default="dochan")
    parser.add_argument("--accelerator-root", type=Path,
                        help="격리된 프로토타입 사본. 원본 런타임은 변경하지 않음")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    if args.accelerator_root:
        if not (args.accelerator_root / "dochan" / "__init__.py").is_file():
            parser.error("--accelerator-root must contain a dochan package copy")
        sys.path.insert(0, str(args.accelerator_root.resolve()))
    if args.batch_list:
        if args.output is None:
            parser.error("--batch-list requires --output")
        paths = json.loads(args.batch_list.read_text())
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            parser.error("--batch-list must contain a JSON array of paths")
        result = _batch(paths, args.batch_profile, args.backend, args.timeout)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1))
        print(json.dumps({"files": len(paths), "completed": result["completed"],
                          "seconds": result["total"]}))
        return
    if args.worker:
        print(json.dumps(_worker(args.worker, args.profile_worker), ensure_ascii=False))
        return
    if not args.roots or args.output is None:
        parser.error("roots and --output are required")
    if not 1 <= args.workers <= 4:
        parser.error("workers must be 1..4")
    paths = _files(args.roots)
    rows = (json.loads(args.existing.read_text())["rows"] if args.existing
            else _measure(paths, args.roots, args.workers, args.timeout))
    reference = json.loads(args.reference.read_text()) if args.reference else None
    alternating = None
    if args.hash_only:
        top, lookup = [], {}
    elif args.alternate_source:
        selected = reference["top30"] if reference else sorted(
            (label for label in rows if "total" in rows[label]),
            key=lambda label: rows[label]["total"], reverse=True)[:30]
        lookup = {}
        internal = 0
        for path in paths:
            if path.parent.name == "test_pairs":
                internal += 1
            lookup[_label(path, args.roots, internal)] = path
        top = selected
        alternating = _alternate_top(top, lookup, args.alternate_source, args.timeout)
    else:
        selected = reference["top30"] if reference else None
        if args.public_top:
            source_rows = reference["rows"] if reference else rows
            selected = sorted((label for label in source_rows
                               if not label.startswith("internal") and
                               "total" in source_rows[label]),
                              key=lambda label: source_rows[label]["total"],
                              reverse=True)[:30]
        top, lookup = _repeat_top(rows, paths, args.roots, args.timeout,
                                  selected)
    profiles = {}
    if args.profile_top:
        for label in top[:10]:
            profiles[label] = _run_one(lookup[label], args.timeout * 3, profile=True)
    result = {"summary": _summary(rows), "rows": rows, "top30": top,
              "profiles": profiles}
    if alternating is not None:
        result["alternating"] = alternating
    if reference:
        keys = ("markdown_sha256", "json_sha256", "errors_sha256")
        mismatches = [label for label, row in rows.items()
                      if any(row.get(key) != reference["rows"].get(label, {}).get(key)
                             for key in keys)]
        result["comparison"] = {"files": len(rows), "identical": len(rows) - len(mismatches),
                                "mismatches": mismatches}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"files": len(rows), "completed": result["summary"]["all"]["completed"],
                      "seconds": result["summary"]["all"].get("sum", 0),
                      "comparison": result.get("comparison")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
