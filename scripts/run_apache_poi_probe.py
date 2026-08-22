"""Run a pinned-input Apache POI OOXML probe loop."""
import argparse
import hashlib
import os
import json
import math
import sys
import stat
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_competitors import (  # noqa: E402
    preflight_ooxml_archive,
    run_benchmark,
)
from scripts.build_apache_poi_fixture_index import build_apache_poi_fixture_index  # noqa: E402
from scripts.download_public_ooxml_corpus import (  # noqa: E402
    atomic_write_text,
    download_corpus,
    record_probe_outcome,
)
from scripts.run_isolated_competitor_benchmark import (  # noqa: E402
    parse_competitors,
    run_isolated_benchmarks,
)


DEFAULT_FORMATS = ("docx", "pptx", "xlsx")
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_SETUP_TIMEOUT_SECONDS = 900.0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _require_positive_timeout(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError("{} must be greater than zero".format(name))
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("{} must be greater than zero".format(name))
    return parsed


def _open_regular_file(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise ValueError("fixture is not a regular file: {}".format(path)) from exc
    try:
        info = os.fstat(descriptor)
    except Exception:
        os.close(descriptor)
        raise
    if not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise ValueError("fixture is not a regular file: {}".format(path))
    return descriptor, info


def _verify_fixture_records(corpus_dir: Path, records: Iterable[dict]) -> List[dict]:
    invalid = []
    for record in records:
        path = record.get("path")
        if not isinstance(path, str):
            invalid.append({
                "path": str(path),
                "error": "fixture path missing",
            })
            continue
        full_path = corpus_dir / path
        expected_bytes = record.get("bytes")
        expected_sha256 = record.get("sha256")
        if expected_bytes is None and expected_sha256 is None:
            continue
        try:
            descriptor, before = _open_regular_file(full_path)
        except ValueError as exc:
            invalid.append({
                "path": path,
                "error": str(exc),
            })
            continue
        digest = hashlib.sha256()
        actual_bytes = 0
        try:
            with os.fdopen(descriptor, "rb") as source:
                descriptor = -1
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    actual_bytes += len(chunk)
                    digest.update(chunk)
        finally:
            if descriptor != -1:
                os.close(descriptor)
        actual_digest = digest.hexdigest()
        if expected_bytes is not None and actual_bytes != expected_bytes:
            invalid.append({
                "path": path,
                "error": "fixture size changed after download: {} != {}".format(
                    actual_bytes,
                    expected_bytes,
                ),
            })
            continue
        if expected_sha256 is not None and actual_digest != expected_sha256:
            invalid.append({
                "path": path,
                "error": "fixture sha256 changed after download: {} != {}".format(
                    actual_digest,
                    expected_sha256,
                ),
            })
            continue
        if expected_bytes is not None and before.st_size != expected_bytes:
            invalid.append({
                "path": path,
                "error": "fixture identity changed after download: size {} != {}".format(
                    before.st_size,
                    expected_bytes,
                ),
            })
    return invalid


def parse_formats(value: str) -> List[str]:
    return [item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()]


def validate_zip_files(corpus_dir: Path, records: Iterable[dict]) -> List[dict]:
    invalid = []
    for record in records:
        path = corpus_dir / record["path"]
        error = preflight_ooxml_archive(path)
        if error:
            invalid.append({"path": record.get("path", str(path)), "error": error})
    return invalid


def remove_invalid_zip_files(corpus_dir: Path, invalid: Iterable[dict]) -> None:
    for item in invalid:
        path = corpus_dir / item.get("path", "")
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def summarize_dochan_only(report: dict) -> dict:
    rows = report.get("results", [])
    errors = [row for row in rows if row.get("error")]
    empty = [
        row for row in rows
        if not row.get("nonempty") and not row.get("error") and not row.get("input_semantic_empty")
    ]
    semantic_empty = [
        row for row in rows
        if not row.get("nonempty") and row.get("input_semantic_empty")
    ]
    failure_reasons = []
    if report.get("ok") is not True:
        failure_reasons.append("dochan benchmark report failed")
    if report.get("file_count", 0) <= 0:
        failure_reasons.append("dochan benchmark contains no input files")
    if errors:
        failure_reasons.append("dochan conversion errors: {}".format(len(errors)))
    if empty:
        failure_reasons.append(
            "dochan unexpected empty outputs: {}".format(len(empty))
        )
    return {
        "ok": not failure_reasons,
        "failure_reasons": failure_reasons,
        "file_count": report.get("file_count", 0),
        "format_summary": report.get("format_summary", []),
        "error_count": len(errors),
        "errors": [{"file": row["file"], "error": row["error"]} for row in errors],
        "unexpected_empty_count": len(empty),
        "unexpected_empty": [row["file"] for row in empty],
        "semantic_empty_count": len(semantic_empty),
        "semantic_empty": [row["file"] for row in semantic_empty],
    }


def run_apache_poi_probe(
    output_dir: Path,
    probe_name: str,
    manifest_path: Path,
    formats: Iterable[str] = DEFAULT_FORMATS,
    per_format: int = 10,
    competitors: Iterable[str] = ("markitdown", "docling"),
    python: Path = Path(sys.executable),
    runs: int = 1,
    index_path: Path = None,
    keep_venv: bool = False,
    keep_going: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    setup_timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS,
    retry_failed_runs: int = 0,
) -> dict:
    timeout_seconds = _require_positive_timeout(timeout_seconds, "timeout_seconds")
    setup_timeout_seconds = _require_positive_timeout(
        setup_timeout_seconds,
        "setup_timeout_seconds",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = list(formats)
    index_path = index_path or (output_dir / "apache-poi-fixtures.json")
    corpus_dir = output_dir / "corpus"
    dochan_report_path = output_dir / "dochan.json"
    isolated_dir = output_dir / "isolated"

    index = build_apache_poi_fixture_index(formats=formats)
    atomic_write_text(
        index_path,
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
    )

    records = download_corpus(
        corpus_dir,
        formats,
        fixtures=index["fixtures"],
        probe_manifest_path=manifest_path,
        probe_name=probe_name,
        probe_per_format=per_format,
    )
    integrity_failures = _verify_fixture_records(corpus_dir, records)
    invalid = validate_zip_files(corpus_dir, records)
    invalid.extend(integrity_failures)
    invalid_paths = {item["path"] for item in invalid}
    if invalid:
        remove_invalid_zip_files(corpus_dir, invalid)
    valid_records = [record for record in records if record["path"] not in invalid_paths]
    valid_files = [record["path"] for record in valid_records]
    if not valid_records:
        failure_reasons = []
        if invalid:
            failure_reasons.append("invalid OOXML archives: {}".format(len(invalid)))
        failure_reasons.append("no valid fixture files")
        report = {
            "probe_name": probe_name,
            "output_dir": str(output_dir),
            "index_path": str(index_path),
            "manifest_path": str(manifest_path),
            "corpus_dir": str(corpus_dir),
            "formats": formats,
            "per_format": per_format,
            "downloaded": len(records),
            "files": valid_files,
            "zip_invalid": invalid,
            "dochan": {},
            "isolated": {},
            "failure_reasons": failure_reasons,
            "ok": False,
        }
        atomic_write_text(
            output_dir / "probe.json",
            json.dumps(report, ensure_ascii=False, indent=2),
        )
        record_probe_outcome(
            manifest_path,
            records,
            probe_name,
            successful_records=(),
            invalid=invalid,
            failure_reasons=failure_reasons,
        )
        return report

    dochan_report = run_benchmark(
        corpus_dir,
        formats=formats,
        runs=1,
        converter_names=["dochan"],
        output_root=output_dir / "outputs" / "dochan",
        timeout_seconds=timeout_seconds,
        input_files=valid_files,
    )
    atomic_write_text(
        dochan_report_path,
        json.dumps(dochan_report, ensure_ascii=False, indent=2),
    )
    isolated = run_isolated_benchmarks(
        corpus_root=corpus_dir,
        output_dir=isolated_dir,
        competitors=competitors,
        python=python,
        formats=formats,
        runs=runs,
        timeout_seconds=timeout_seconds,
        setup_timeout_seconds=setup_timeout_seconds,
        retry_failed_runs=retry_failed_runs,
        keep_venv=keep_venv,
        keep_going=keep_going,
        input_files=valid_files,
    )
    dochan_summary = summarize_dochan_only(dochan_report)
    failure_reasons = []
    if invalid:
        failure_reasons.append("invalid OOXML archives: {}".format(len(invalid)))
    dochan_complete = dochan_summary["file_count"] == len(valid_files)
    if not dochan_complete:
        failure_reasons.append(
            "dochan benchmark file count mismatch: {}/{}".format(
                dochan_summary["file_count"],
                len(valid_files),
            )
        )
    if not dochan_summary["ok"]:
        failure_reasons.append("dochan benchmark failed")
    isolated_records = isolated.get("competitors", [])
    isolated_complete = not (
        isolated.get("ok") is not True
        or not isolated_records
        or any(record.get("ok") is not True for record in isolated_records)
    )
    if not isolated_complete:
        failure_reasons.append("isolated benchmark failed")
    successful_records = (
        valid_records
        if dochan_complete and dochan_summary["ok"] and isolated_complete
        else []
    )
    report = {
        "probe_name": probe_name,
        "output_dir": str(output_dir),
        "index_path": str(index_path),
        "manifest_path": str(manifest_path),
        "corpus_dir": str(corpus_dir),
        "formats": formats,
        "per_format": per_format,
        "downloaded": len(records),
        "files": valid_files,
        "zip_invalid": invalid,
        "dochan": dochan_summary,
        "isolated": isolated,
        "failure_reasons": failure_reasons,
        "ok": not failure_reasons,
    }
    atomic_write_text(
        output_dir / "probe.json",
        json.dumps(report, ensure_ascii=False, indent=2),
    )
    record_probe_outcome(
        manifest_path,
        records,
        probe_name,
        successful_records=successful_records,
        invalid=invalid,
        failure_reasons=failure_reasons,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a pinned-input Apache POI OOXML probe loop."
    )
    parser.add_argument("output_dir", type=Path, help="Directory for corpus, reports, and outputs")
    parser.add_argument("--probe-name", required=True, help="Probe name recorded in manifest and report")
    parser.add_argument("--probe-manifest", type=Path, required=True, help="Persistent Apache POI probe manifest")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated extensions")
    parser.add_argument("--probe-per-format", type=int, default=10, help="Unseen fixtures selected per format")
    parser.add_argument("--competitors", default="markitdown,docling", help="Comma-separated competitors")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python executable for isolated venvs")
    parser.add_argument("--runs", type=int, default=1, help="Repeated runs per converter/file")
    parser.add_argument("--timeout", type=_positive_float, default=DEFAULT_TIMEOUT_SECONDS, help="Seconds before a single conversion is recorded as timed out")
    parser.add_argument("--setup-timeout", type=_positive_float, default=DEFAULT_SETUP_TIMEOUT_SECONDS, help="Absolute seconds allowed for each competitor setup and benchmark process")
    parser.add_argument("--retry-failed-runs", type=int, default=0, help="Retry a failed isolated competitor benchmark command this many times")
    parser.add_argument("--index-path", type=Path, default=None, help="Optional fixture index output path")
    parser.add_argument("--keep-venv", action="store_true", help="Keep temporary competitor venvs")
    parser.add_argument("--keep-going", action="store_true", help="Continue after isolated competitor failure")
    args = parser.parse_args()

    report = run_apache_poi_probe(
        output_dir=args.output_dir,
        probe_name=args.probe_name,
        manifest_path=args.probe_manifest,
        formats=parse_formats(args.formats),
        per_format=args.probe_per_format,
        competitors=parse_competitors(args.competitors),
        python=args.python,
        runs=args.runs,
        timeout_seconds=args.timeout,
        setup_timeout_seconds=args.setup_timeout,
        retry_failed_runs=args.retry_failed_runs,
        index_path=args.index_path,
        keep_venv=args.keep_venv,
        keep_going=args.keep_going,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
