"""Run a reproducible Apache POI OOXML probe loop."""
import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_competitors import run_benchmark
from scripts.build_apache_poi_fixture_index import build_apache_poi_fixture_index
from scripts.download_public_ooxml_corpus import download_corpus
from scripts.run_isolated_competitor_benchmark import parse_competitors, run_isolated_benchmarks


DEFAULT_FORMATS = ("docx", "pptx", "xlsx")


def parse_formats(value: str) -> List[str]:
    return [item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()]


def validate_zip_files(corpus_dir: Path, records: Iterable[dict]) -> List[dict]:
    invalid = []
    for record in records:
        path = corpus_dir / record["path"]
        try:
            with zipfile.ZipFile(path) as archive:
                bad_member = archive.testzip()
            if bad_member:
                invalid.append({"path": record["path"], "error": f"bad member {bad_member}"})
        except Exception as exc:
                invalid.append({"path": record.get("path", str(path)), "error": repr(exc)})
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
    return {
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
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = list(formats)
    index_path = index_path or (output_dir / "apache-poi-fixtures.json")
    corpus_dir = output_dir / "corpus"
    dochan_report_path = output_dir / "dochan.json"
    isolated_dir = output_dir / "isolated"

    index = build_apache_poi_fixture_index(formats=formats)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    records = download_corpus(
        corpus_dir,
        formats,
        fixtures=index["fixtures"],
        probe_manifest_path=manifest_path,
        probe_name=probe_name,
        probe_per_format=per_format,
    )
    invalid = validate_zip_files(corpus_dir, records)
    invalid_paths = {item["path"] for item in invalid}
    if invalid:
        remove_invalid_zip_files(corpus_dir, invalid)
    valid_records = [record for record in records if record["path"] not in invalid_paths]
    if not valid_records:
        report = {
            "probe_name": probe_name,
            "output_dir": str(output_dir),
            "index_path": str(index_path),
            "manifest_path": str(manifest_path),
            "corpus_dir": str(corpus_dir),
            "formats": formats,
            "per_format": per_format,
            "downloaded": len(records),
            "files": [],
            "zip_invalid": invalid,
            "dochan": {},
            "isolated": {},
        }
        (output_dir / "probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    dochan_report = run_benchmark(
        corpus_dir,
        formats=formats,
        runs=1,
        converter_names=["dochan"],
        output_root=output_dir / "outputs" / "dochan",
    )
    dochan_report_path.write_text(json.dumps(dochan_report, ensure_ascii=False, indent=2), encoding="utf-8")
    isolated = run_isolated_benchmarks(
        corpus_root=corpus_dir,
        output_dir=isolated_dir,
        competitors=competitors,
        python=python,
        formats=formats,
        runs=runs,
        keep_venv=keep_venv,
        keep_going=keep_going,
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
        "files": [record["path"] for record in valid_records],
        "zip_invalid": invalid,
        "dochan": summarize_dochan_only(dochan_report),
        "isolated": isolated,
    }
    (output_dir / "probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a reproducible Apache POI OOXML probe loop.")
    parser.add_argument("output_dir", type=Path, help="Directory for corpus, reports, and outputs")
    parser.add_argument("--probe-name", required=True, help="Probe name recorded in manifest and report")
    parser.add_argument("--probe-manifest", type=Path, required=True, help="Persistent Apache POI probe manifest")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated extensions")
    parser.add_argument("--probe-per-format", type=int, default=10, help="Unseen fixtures selected per format")
    parser.add_argument("--competitors", default="markitdown,docling", help="Comma-separated competitors")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python executable for isolated venvs")
    parser.add_argument("--runs", type=int, default=1, help="Repeated runs per converter/file")
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
        index_path=args.index_path,
        keep_venv=args.keep_venv,
        keep_going=args.keep_going,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in report.get("isolated", {}).get("competitors", [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
