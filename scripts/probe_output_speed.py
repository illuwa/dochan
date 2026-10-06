"""전 형식의 파싱·Markdown·JSON·일반 텍스트 단계 시간과 출력 해시를 모으고 두 실행을 대조한다.

출력 계층(직렬화기·평탄화 도우미)이나 공용 모델을 고친 뒤 "출력은 그대로, 시간만 줄었다"를
코퍼스 전수로 확인하는 도구다. 본문은 저장하지 않고 SHA-256 과 시간만 기록한다.

예:
    python -m scripts.probe_output_speed collect corpus/hwp-public corpus/poi-src \\
        --output .codex-work/after.json --workers 8
    python -m scripts.probe_output_speed collect corpus/hwp-public corpus/poi-src \\
        --source ../snapshot-before --output .codex-work/before.json --workers 8
    python -m scripts.probe_output_speed compare .codex-work/before.json .codex-work/after.json
"""
import argparse
import hashlib
import json
import multiprocessing
import os
import signal
import sys
import time
from collections import defaultdict
from pathlib import Path

EXTENSIONS = ("hwp", "hwpx", "doc", "ppt", "xls", "docx", "pptx", "xlsx", "pdf")
STAGES = ("parse", "markdown", "json", "text")
HASHES = ("markdown_sha256", "json_sha256", "text_sha256", "errors_sha256")
_state = {"source": None, "timeout": 180}


class _Timeout(Exception):
    pass


def _raise_timeout(signum, frame):
    raise _Timeout()


def collect_paths(roots):
    """지원 확장자의 일반 파일만 정렬해 돌려준다. 심볼릭 링크와 숨김 폴더는 건너뛴다."""
    paths = []
    for root in roots:
        for directory, names, files in os.walk(root):
            names[:] = sorted(name for name in names if not name.startswith("."))
            for name in sorted(files):
                path = os.path.join(directory, name)
                suffix = os.path.splitext(name)[1].lower().lstrip(".")
                if suffix in EXTENSIONS and os.path.isfile(path) and not os.path.islink(path):
                    paths.append(path)
    return sorted(set(paths))


def _hash(text):
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _init_worker(source, timeout):
    _state["source"], _state["timeout"] = source, timeout
    if source:
        sys.path.insert(0, source)
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _raise_timeout)


def measure_file(path):
    """한 파일의 단계별 시간과 출력 해시. 예외와 시간 초과는 failure 로 남긴다."""
    from dochan import Dochan

    try:
        from dochan.output import json_indent
    except ImportError:  # 직렬화기가 없던 기준 소스
        json_indent = None
    record = {}
    marks = [time.perf_counter()]
    stage = "parse"
    alarm = hasattr(signal, "SIGALRM")
    if alarm:
        signal.alarm(_state["timeout"])
    try:
        fallbacks = json_indent.stdlib_fallbacks() if json_indent else 0
        doc = Dochan(path)
        marks.append(time.perf_counter())
        stage = "markdown"
        record["markdown_sha256"] = _hash(doc.to_markdown())
        marks.append(time.perf_counter())
        stage = "json"
        record["json_sha256"] = _hash(doc.to_json())
        marks.append(time.perf_counter())
        stage = "text"
        record["text_sha256"] = _hash(doc.to_plain_text())
        marks.append(time.perf_counter())
        record["errors_sha256"] = _hash(json.dumps([str(e) for e in doc.errors], ensure_ascii=False))
        if json_indent:
            record["json_fallbacks"] = json_indent.stdlib_fallbacks() - fallbacks
    except _Timeout:
        record["failure"] = "timeout:" + stage
    except Exception as exc:
        record["failure"] = "{}:{}".format(stage, type(exc).__name__)
    finally:
        if alarm:
            signal.alarm(0)
    for name, start, end in zip(STAGES, marks, marks[1:]):
        record[name] = end - start
    return path, record


def collect(roots, workers=1, source=None, timeout=180):
    paths = collect_paths(roots)
    # 큰 파일부터 나눠 주어 마지막 작업자 하나만 남는 꼬리를 줄인다
    paths.sort(key=lambda path: -os.path.getsize(path))
    started = time.perf_counter()
    if workers <= 1:
        _init_worker(source, timeout)
        records = dict(measure_file(path) for path in paths)
    else:
        with multiprocessing.Pool(workers, _init_worker, (source, timeout), maxtasksperchild=300) as pool:
            records = dict(pool.imap_unordered(measure_file, paths, chunksize=2))
    return {"source": source or "", "workers": workers, "wall": time.perf_counter() - started,
            "python": sys.version.split()[0], "records": records}


def compare_records(before, after):
    """형식별로 해시 차이·실패 변화·단계 시간 합계를 모은다."""
    summary = defaultdict(lambda: {"files": 0, "missing": 0, "failure_changed": 0, "both_failed": 0,
                                   "json_fallbacks": 0,
                                   **{name: 0 for name in HASHES},
                                   **{"before_" + stage: 0.0 for stage in STAGES},
                                   **{"after_" + stage: 0.0 for stage in STAGES}})
    for path, old in before.items():
        row = summary[os.path.splitext(path)[1].lower().lstrip(".")]
        row["files"] += 1
        new = after.get(path)
        if new is None:
            row["missing"] += 1
            continue
        row["json_fallbacks"] += new.get("json_fallbacks", 0)
        if old.get("failure") != new.get("failure"):
            row["failure_changed"] += 1
            continue
        if "failure" in old:
            row["both_failed"] += 1
            continue
        for name in HASHES:
            row[name] += old.get(name) != new.get(name)
        for stage in STAGES:
            row["before_" + stage] += old.get(stage, 0.0)
            row["after_" + stage] += new.get(stage, 0.0)
    return dict(summary)


def differences(summary):
    return sum(row["missing"] + row["failure_changed"] + row["json_fallbacks"] + sum(row[name] for name in HASHES)
               for row in summary.values())


def _print_summary(summary):
    print("형식   파일  해시차이  실패변화  폴백 | " + " | ".join("{} 전→후(초)".format(s) for s in STAGES))
    for suffix in sorted(summary):
        row = summary[suffix]
        stages = " | ".join("{:8.1f}→{:8.1f}".format(row["before_" + s], row["after_" + s]) for s in STAGES)
        print("{:5} {:5d} {:8d} {:8d} {:5d} | {}".format(
            suffix, row["files"], sum(row[name] for name in HASHES), row["failure_changed"] + row["missing"],
            row["json_fallbacks"], stages))


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("roots", nargs="+")
    collect_parser.add_argument("--output", required=True)
    collect_parser.add_argument("--workers", type=int, default=1)
    collect_parser.add_argument("--timeout", type=int, default=180)
    collect_parser.add_argument("--source", help="측정할 다른 소스 체크아웃(기준 스냅숏)의 경로")
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("before")
    compare_parser.add_argument("after")
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect(args.roots, args.workers, args.source, args.timeout)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        failures = sum("failure" in record for record in result["records"].values())
        print("files={} failures={} wall={:.1f}s".format(len(result["records"]), failures, result["wall"]))
        return 0
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))["records"]
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))["records"]
    summary = compare_records(before, after)
    _print_summary(summary)
    return 1 if differences(summary) else 0


if __name__ == "__main__":
    sys.exit(main())
