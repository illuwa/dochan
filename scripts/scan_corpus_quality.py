"""Scan a HWP/HWPX corpus for parser crashes, internal errors, and suspiciously
thin output (likely under-extraction), without writing per-file Markdown to disk.

Unlike `dochan batch`, which only reports hard crashes, this walks every file,
converts it in-process, and inspects `Dochan.errors` plus output length even on
"successful" conversions so silent quality regressions surface in aggregate.
"""
import argparse
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List


def _scan_one(file_path: str) -> dict:
    from dochan import Dochan

    file_size = Path(file_path).stat().st_size
    record = {"file": file_path, "bytes": file_size}
    start = time.monotonic()
    try:
        doc = Dochan(file_path)
        markdown = doc.to_markdown()
    except Exception as exc:  # noqa: BLE001 - want every crash captured, not just known types
        record["crashed"] = True
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["elapsed"] = time.monotonic() - start
        return record

    record["crashed"] = False
    record["elapsed"] = time.monotonic() - start
    record["internal_errors"] = list(doc.errors)
    record["markdown_len"] = len(markdown)
    record["markdown_stripped_len"] = len(markdown.strip())
    return record


def _cluster_key(message: str) -> str:
    key = re.sub(r"0x[0-9a-fA-F]+", "0xN", message)
    key = re.sub(r"\d+", "N", key)
    key = re.sub(r"'[^']*'", "'...'", key)
    return key[:120]


def scan_corpus(input_dir: Path, workers: int, extensions=(".hwp", ".hwpx")) -> List[dict]:
    files = [
        str(p) for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    ]
    files.sort()
    results = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scan_one, f): f for f in files}
        for i, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if i % 500 == 0:
                print(f"...{i}/{len(files)} scanned")
    return results


def build_report(results: List[dict], thin_ratio_threshold: float = 0.01, thin_min_bytes: int = 3000) -> dict:
    crashes = [r for r in results if r["crashed"]]
    successes = [r for r in results if not r["crashed"]]
    with_internal_errors = [r for r in successes if r.get("internal_errors")]
    empty_output = [r for r in successes if r.get("markdown_stripped_len", 0) == 0]
    thin_output = [
        r for r in successes
        if r.get("markdown_stripped_len", 0) > 0
        and r["bytes"] >= thin_min_bytes
        and r["markdown_stripped_len"] / max(r["bytes"], 1) < thin_ratio_threshold
    ]

    crash_clusters = {}
    for r in crashes:
        key = _cluster_key(r["error"])
        crash_clusters.setdefault(key, []).append(r["file"])

    error_clusters = {}
    for r in with_internal_errors:
        for err in r["internal_errors"]:
            key = _cluster_key(str(err))
            error_clusters.setdefault(key, []).append(r["file"])

    return {
        "total_files": len(results),
        "crashed": len(crashes),
        "succeeded": len(successes),
        "succeeded_with_internal_errors": len(with_internal_errors),
        "empty_output": len(empty_output),
        "thin_output_suspect": len(thin_output),
        "crash_clusters": {
            k: {"count": len(v), "examples": v[:5]} for k, v in
            sorted(crash_clusters.items(), key=lambda kv: -len(kv[1]))
        },
        "internal_error_clusters": {
            k: {"count": len(v), "examples": v[:5]} for k, v in
            sorted(error_clusters.items(), key=lambda kv: -len(kv[1]))
        },
        "empty_output_examples": [r["file"] for r in empty_output[:20]],
        "thin_output_examples": [
            {"file": r["file"], "bytes": r["bytes"], "markdown_stripped_len": r["markdown_stripped_len"]}
            for r in sorted(thin_output, key=lambda r: r["markdown_stripped_len"] / max(r["bytes"], 1))[:20]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a HWP/HWPX corpus for crashes and thin/empty output")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=None, help="Write full per-file results + report JSON here")
    args = parser.parse_args()

    results = scan_corpus(args.input_dir, args.workers)
    report = build_report(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"report": report, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
