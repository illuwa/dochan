"""Run competitor benchmarks in temporary isolated virtual environments."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_COMPETITORS = ("markitdown", "docling")
DEFAULT_FORMATS = ("docx", "pptx", "xlsx")
DEFAULT_TIMEOUT_SECONDS = 120.0


def parse_competitors(value: str) -> List[str]:
    competitors = []
    for item in value.split(","):
        name = item.strip().lower()
        if not name or name in competitors:
            continue
        if name not in SUPPORTED_COMPETITORS:
            raise ValueError(f"Unsupported competitor: {item}")
        competitors.append(name)
    return competitors


def competitor_install_packages(competitor: str) -> List[str]:
    if competitor == "markitdown":
        return ["markitdown[docx,pptx,xlsx]"]
    if competitor == "docling":
        return ["docling"]
    raise ValueError(f"Unsupported competitor: {competitor}")


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / "bin" / "python"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def make_venv_dir(competitor: str, corpus_root: Path) -> Path:
    corpus = corpus_root.resolve()
    candidates = [Path("/tmp"), Path(tempfile.gettempdir()), PROJECT_ROOT / ".tmp"]
    for candidate in candidates:
        parent = candidate.resolve()
        if _is_relative_to(parent, corpus):
            continue
        parent.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=f"dochan-{competitor}-venv.", dir=str(parent)))
    raise RuntimeError(f"Could not find venv parent outside corpus: {corpus_root}")


def benchmark_command(
    python_executable: Path,
    corpus_root: Path,
    output_path: Path,
    competitor: str,
    formats: Iterable[str],
    runs: int,
    output_root: Path = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> List[str]:
    command = [
        str(python_executable),
        "scripts/benchmark_competitors.py",
        str(corpus_root),
        "--formats",
        ",".join(formats),
        "--converters",
        f"dochan,{competitor}",
        "--runs",
        str(runs),
        "--timeout",
        f"{timeout_seconds:g}",
        "--output",
        str(output_path),
    ]
    if output_root is not None:
        command.extend(["--save-outputs", str(output_root)])
    return command


def run_command(command: List[str], cwd: Path) -> None:
    subprocess.run(command, cwd=str(cwd), check=True)


def summarize_competitor_report(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "file_count": report.get("file_count", 0),
        "converters": report.get("converters", []),
        "format_summary": report.get("format_summary", []),
        "competitive_summary": report.get("competitive_summary", []),
        "improvement_candidates": report.get("improvement_candidates", []),
        "file_improvement_candidates": report.get("file_improvement_candidates", []),
    }


def run_competitor(
    competitor: str,
    corpus_root: Path,
    output_dir: Path,
    python: Path,
    formats: Iterable[str],
    runs: int,
    keep_venv: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    retry_failed_runs: int = 0,
) -> dict:
    output_path = output_dir / f"{competitor}.json"
    venv_dir = make_venv_dir(competitor, corpus_root)
    python_executable = venv_python(venv_dir)
    record = {
        "competitor": competitor,
        "output": str(output_path),
        "venv": str(venv_dir),
        "ok": False,
        "error": "",
        "attempts": 0,
        "errors": [],
        "report_summary": {},
    }
    try:
        run_command([str(python), "-m", "venv", str(venv_dir)], PROJECT_ROOT)
        run_command([str(python_executable), "-m", "pip", "install", "--upgrade", "pip"], PROJECT_ROOT)
        run_command(
            [str(python_executable), "-m", "pip", "install", "-e", ".", *competitor_install_packages(competitor)],
            PROJECT_ROOT,
        )
        command = benchmark_command(
            python_executable,
            corpus_root,
            output_path,
            competitor,
            formats,
            runs,
            output_dir / "outputs" / competitor,
            timeout_seconds,
        )
        max_attempts = max(1, retry_failed_runs + 1)
        for attempt in range(max_attempts):
            record["attempts"] = attempt + 1
            try:
                run_command(command, PROJECT_ROOT)
                break
            except Exception as exc:
                record["errors"].append(repr(exc))
                if attempt + 1 >= max_attempts:
                    raise
        record["ok"] = True
        record["report_summary"] = summarize_competitor_report(output_path)
    except Exception as exc:
        record["error"] = repr(exc)
        raise
    finally:
        if not keep_venv:
            shutil.rmtree(venv_dir, ignore_errors=True)
            record["venv"] = ""
    return record


def run_isolated_benchmarks(
    corpus_root: Path,
    output_dir: Path,
    competitors: Iterable[str],
    python: Path,
    formats: Iterable[str],
    runs: int,
    keep_venv: bool = False,
    keep_going: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    retry_failed_runs: int = 0,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for competitor in competitors:
        try:
            records.append(
                run_competitor(
                    competitor,
                    corpus_root,
                    output_dir,
                    python,
                    formats,
                    runs,
                    keep_venv,
                    timeout_seconds,
                    retry_failed_runs,
                )
            )
        except Exception as exc:
            record = {
                "competitor": competitor,
                "output": str(output_dir / f"{competitor}.json"),
                "venv": "",
                "ok": False,
                "error": repr(exc),
                "attempts": 0,
                "errors": [repr(exc)],
                "report_summary": {},
            }
            records.append(record)
            if not keep_going:
                break
    index = {
        "corpus": str(corpus_root),
        "output_dir": str(output_dir),
        "competitors": records,
    }
    (output_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dochan competitor benchmarks in isolated temporary venvs.")
    parser.add_argument("corpus", type=Path, help="Directory containing OOXML benchmark files")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for JSON reports")
    parser.add_argument("--competitors", default=",".join(SUPPORTED_COMPETITORS), help="Comma-separated competitors")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python executable used to create venvs")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated extensions")
    parser.add_argument("--runs", type=int, default=3, help="Repeated runs per converter/file")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Seconds before a single conversion is recorded as timed out")
    parser.add_argument("--retry-failed-runs", type=int, default=0, help="Retry a failed competitor benchmark command this many times")
    parser.add_argument("--keep-venv", action="store_true", help="Keep temporary venvs for debugging")
    parser.add_argument("--keep-going", action="store_true", help="Continue after a competitor install or run failure")
    args = parser.parse_args()

    competitors = parse_competitors(args.competitors)
    formats = [item.strip().lstrip(".") for item in args.formats.split(",") if item.strip()]
    report = run_isolated_benchmarks(
        corpus_root=args.corpus,
        output_dir=args.output_dir,
        competitors=competitors,
        python=args.python,
        formats=formats,
        runs=args.runs,
        keep_venv=args.keep_venv,
        keep_going=args.keep_going,
        timeout_seconds=args.timeout,
        retry_failed_runs=args.retry_failed_runs,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in report["competitors"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
