"""Run a reproducible OOXML probe from a fixture index JSON file."""
import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_competitors import run_benchmark
from scripts.download_public_ooxml_corpus import download_corpus, load_fixture_index
from scripts.run_apache_poi_probe import summarize_dochan_only, validate_zip_files, remove_invalid_zip_files
from scripts.run_isolated_competitor_benchmark import parse_competitors, run_isolated_benchmarks


DEFAULT_FORMATS = ("docx", "pptx", "xlsx")


def parse_formats(value: str) -> List[str]:
    return [item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()]


def run_fixture_probe(
    output_dir: Path,
    fixture_index: Path,
    probe_name: str,
    manifest_path: Path,
    formats: Iterable[str] = DEFAULT_FORMATS,
    per_format: int = 10,
    competitors: Iterable[str] = ("markitdown", "docling"),
    python: Path = Path(sys.executable),
    runs: int = 1,
    keep_venv: bool = False,
    keep_going: bool = False,
    timeout_seconds: float = 120.0,
    retry_failed_runs: int = 1,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = list(formats)
    corpus_dir = output_dir / "corpus"

    fixtures = load_fixture_index(fixture_index)
    records = download_corpus(
        corpus_dir,
        formats,
        fixtures=fixtures,
        probe_manifest_path=manifest_path,
        probe_name=probe_name,
        probe_per_format=per_format,
    )
    invalid = validate_zip_files(corpus_dir, records)
    invalid_paths = {item["path"] for item in invalid}
    if invalid:
        remove_invalid_zip_files(corpus_dir, invalid)
    valid_records = [record for record in records if record["path"] not in invalid_paths]

    report = {
        "probe_name": probe_name,
        "output_dir": str(output_dir),
        "fixture_index": str(fixture_index),
        "manifest_path": str(manifest_path),
        "corpus_dir": str(corpus_dir),
        "formats": formats,
        "per_format": per_format,
        "downloaded": len(records),
        "files": [record["path"] for record in valid_records],
        "zip_invalid": invalid,
        "dochan": {},
        "isolated": {},
    }
    if not valid_records:
        (output_dir / "probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    dochan_report = run_benchmark(
        corpus_dir,
        formats=formats,
        runs=1,
        converter_names=["dochan"],
        output_root=output_dir / "outputs" / "dochan",
    )
    (output_dir / "dochan.json").write_text(json.dumps(dochan_report, ensure_ascii=False, indent=2), encoding="utf-8")
    isolated = run_isolated_benchmarks(
        corpus_root=corpus_dir,
        output_dir=output_dir / "isolated",
        competitors=competitors,
        python=python,
        formats=formats,
        runs=runs,
        timeout_seconds=timeout_seconds,
        retry_failed_runs=retry_failed_runs,
        keep_venv=keep_venv,
        keep_going=keep_going,
    )
    report["dochan"] = summarize_dochan_only(dochan_report)
    report["isolated"] = isolated
    (output_dir / "probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a reproducible OOXML fixture-index probe loop.")
    parser.add_argument("output_dir", type=Path, help="Directory for corpus, reports, and outputs")
    parser.add_argument("--fixture-index", type=Path, required=True, help="Fixture index JSON")
    parser.add_argument("--probe-name", required=True, help="Probe name recorded in manifest and report")
    parser.add_argument("--probe-manifest", type=Path, required=True, help="Persistent probe manifest")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated extensions")
    parser.add_argument("--probe-per-format", type=int, default=10, help="Unseen fixtures selected per format")
    parser.add_argument("--competitors", default="markitdown,docling", help="Comma-separated competitors")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python executable for isolated venvs")
    parser.add_argument("--runs", type=int, default=1, help="Repeated runs per converter/file")
    parser.add_argument("--timeout", type=float, default=120.0, help="Seconds before a single conversion is recorded as timed out")
    parser.add_argument("--retry-failed-runs", type=int, default=1, help="Retry a failed isolated competitor benchmark command this many times")
    parser.add_argument("--keep-venv", action="store_true", help="Keep temporary competitor venvs")
    parser.add_argument("--keep-going", action="store_true", help="Continue after isolated competitor failure")
    args = parser.parse_args()

    report = run_fixture_probe(
        output_dir=args.output_dir,
        fixture_index=args.fixture_index,
        probe_name=args.probe_name,
        manifest_path=args.probe_manifest,
        formats=parse_formats(args.formats),
        per_format=args.probe_per_format,
        competitors=parse_competitors(args.competitors),
        python=args.python,
        runs=args.runs,
        timeout_seconds=args.timeout,
        retry_failed_runs=args.retry_failed_runs,
        keep_venv=args.keep_venv,
        keep_going=args.keep_going,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in report.get("isolated", {}).get("competitors", [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
