"""공개 HWP/HWPX 코퍼스의 출력 지문과 내부 쌍의 익명 집계를 비교한다.

snapshot --source-root 는 비교할 소스를 지정한다. 문서 원본은 읽기만 하며,
내부 --pairs 결과에는 파일명, 내용, 오류 문자열을 저장하지 않는다.
"""

import argparse
import hashlib
import json
import multiprocessing
import resource
import sys
import time
from pathlib import Path


def _initialize(source_root):
    sys.path.insert(0, source_root)


def _fingerprint(text):
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "characters": len(text)}


def _convert(task):
    from dochan import Dochan

    root, filename = task
    start = time.monotonic()
    row = {"file": filename}
    try:
        reader = Dochan(str(Path(root) / filename))
        row["json"] = _fingerprint(json.dumps(reader.to_dict(), ensure_ascii=False,
                                              sort_keys=True, separators=(",", ":")))
        row["markdown"] = _fingerprint(reader.to_markdown())
        row["plain"] = _fingerprint(reader.to_plain_text())
        row["errors"] = reader.errors
    except Exception as exc:
        row["exception"] = type(exc).__name__ + ": " + str(exc)
    row["seconds"] = round(time.monotonic() - start, 6)
    # macOS getrusage 는 byte, Linux 는 KiB 단위다.
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    row["peak_rss_bytes"] = rss if sys.platform == "darwin" else rss * 1024
    return row


def _private_pairs(directory):
    from scripts.compare_hwp_pairs import compare_pair, find_pairs, summarize

    rows = {}
    for index, (_, hwpx, hwp) in enumerate(find_pairs([directory])):
        try:
            rows[str(index)] = compare_pair(hwpx, hwp)
        except Exception:
            rows[str(index)] = {"error": True}
    summary = summarize(rows)
    summary["pair_metrics_sha256"] = _fingerprint(json.dumps(
        list(rows.values()), ensure_ascii=False, sort_keys=True))["sha256"]
    return summary


def _synthetic_corrupt_sections():
    from scripts.probe_hwp_corrupt_sections import probe

    return [probe(damage) for damage in ("invalid", "truncated", "checksum")]


def snapshot(args):
    root = Path(args.corpus).resolve()
    files = sorted(str(path.relative_to(root)) for directory in ("hwp", "hwpx")
                   for path in (root / directory).iterdir()
                   if path.is_file() and path.suffix.lower() in (".hwp", ".hwpx"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    counts = {"hwp": 0, "hwpx": 0}
    with multiprocessing.get_context("spawn").Pool(
            args.workers, initializer=_initialize,
            initargs=(str(Path(args.source_root).resolve()),), maxtasksperchild=25) as pool:
        with output.open("w", encoding="utf-8") as handle:
            for index, row in enumerate(pool.imap_unordered(
                    _convert, ((str(root), name) for name in files)), 1):
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                counts[Path(row["file"]).suffix[1:].lower()] += 1
                if index % 250 == 0:
                    print(json.dumps({"converted": index, "total": len(files),
                                      "seconds": round(time.monotonic() - start, 1)}),
                          flush=True)
        pairs = pool.apply(_private_pairs, (args.pairs,)) if args.pairs else None
        synthetic = pool.apply(_synthetic_corrupt_sections)
    summary = {"source_root": str(Path(args.source_root).resolve()),
               "revision": args.revision, "counts": counts,
               "standard_counts": {ext: sum(name.startswith(ext + "/")
                                             and name.endswith("." + ext)
                                             for name in files)
                                   for ext in ("hwp", "hwpx")},
               "extra_files": sum(not any(name.startswith(ext + "/")
                                              and name.endswith("." + ext)
                                              for ext in ("hwp", "hwpx"))
                                  for name in files),
               "seconds": round(time.monotonic() - start, 3), "private_pairs": pairs,
               "synthetic_corrupt_sections": synthetic}
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def compare(args):
    def load(filename):
        with open(filename, encoding="utf-8") as handle:
            return {row["file"]: row for row in map(json.loads, handle)}

    before, after = load(args.before), load(args.after)
    changes = []
    identical = {"hwp": 0, "hwpx": 0}
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name, {}), after.get(name, {})
        keys = [key for key in ("json", "markdown", "plain", "errors", "exception")
                if old.get(key) != new.get(key)]
        if keys or not old or not new:
            changes.append({"file": name, "changed_fields": keys,
                            "before": old, "after": new})
        else:
            identical[Path(name).suffix[1:].lower()] += 1
    result = {"before_count": len(before), "after_count": len(after),
              "identical": identical, "changed_count": len(changes), "changes": changes}
    synthetic = []
    summaries = [Path(name).with_suffix(".summary.json") for name in (args.before, args.after)]
    if all(path.exists() for path in summaries):
        old_cases, new_cases = [
            {row["case"]: row for row in json.loads(path.read_text(encoding="utf-8")).get(
                "synthetic_corrupt_sections", [])} for path in summaries
        ]
        for case in sorted(set(old_cases) | set(new_cases)):
            old, new = old_cases.get(case, {}), new_cases.get(case, {})
            synthetic.append({"case": case, "before": old, "after": new,
                              "outputs_identical": all(old.get(key) == new.get(key)
                                                       for key in ("markdown", "json")),
                              "valid_sections_preserved": new.get("valid_texts_match", False)})
    result["synthetic_corrupt_sections"] = synthetic
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "changes"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--corpus", required=True)
    snap.add_argument("--source-root", required=True)
    snap.add_argument("--revision", required=True)
    snap.add_argument("--output", required=True)
    snap.add_argument("--workers", type=int, default=3)
    snap.add_argument("--pairs")
    diff = commands.add_parser("compare")
    diff.add_argument("--before", required=True)
    diff.add_argument("--after", required=True)
    diff.add_argument("--output", required=True)
    args = parser.parse_args()
    (snapshot if args.command == "snapshot" else compare)(args)


if __name__ == "__main__":
    main()
