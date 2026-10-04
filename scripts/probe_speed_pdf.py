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

from dochan.reader import Dochan


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _worker(path, profile=False):
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


def _run_one(path, timeout, profile=False):
    command = [sys.executable, "-m", "scripts.probe_speed_pdf", "--worker", str(path)]
    if profile:
        command.append("--profile-worker")
    try:
        # nosemgrep: dangerous-subprocess-use-audit
        run = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
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
    args = parser.parse_args()
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
    if args.hash_only:
        top, lookup = [], {}
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
