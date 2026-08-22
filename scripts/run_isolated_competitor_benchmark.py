"""Run competitor benchmarks in temporary isolated virtual environments."""
import argparse
import hashlib
import json
import math
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.download_public_ooxml_corpus import atomic_write_text  # noqa: E402

SUPPORTED_COMPETITORS = ("markitdown", "docling")
DEFAULT_FORMATS = ("docx", "pptx", "xlsx")
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_SETUP_TIMEOUT_SECONDS = 900.0
PIP_VERSION = "26.2.1"
COMPETITOR_PACKAGES = {
    "markitdown": "markitdown[docx,pptx,xlsx]==0.1.7",
    "docling": "docling==2.119.0",
}
HASH_CHUNK_BYTES = 1024 * 1024
MAX_CORPUS_FILE_BYTES = 100 * 1024 * 1024
MAX_CORPUS_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_CORPUS_FILES = 10_000


class CompetitorRunError(RuntimeError):
    def __init__(self, record: dict):
        super().__init__(record.get("error", "competitor benchmark failed"))
        self.record = record


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
    try:
        return [COMPETITOR_PACKAGES[competitor]]
    except KeyError:
        raise ValueError(f"Unsupported competitor: {competitor}") from None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_open_deadline(deadline: Optional[float], path: Path) -> None:
    if deadline is None:
        return
    if time.monotonic() >= deadline:
        raise TimeoutError("setup timeout exceeded during corpus inventory: {}".format(path))


def _open_regular_file(path: Path, deadline: Optional[float] = None) -> Tuple[int, os.stat_result]:
    _require_open_deadline(deadline, path)
    try:
        before = os.lstat(str(path))
    except OSError as exc:
        raise ValueError("fixture is not a regular file: {}".format(path)) from exc
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("fixture is not a regular file: {}".format(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    nonblock_flag = getattr(os, "O_NONBLOCK", 0)
    if nonblock_flag:
        flags |= nonblock_flag
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


def _fixture_digest(path: Path, max_file_bytes: int, deadline: Optional[float] = None) -> Tuple[int, str]:
    descriptor, before = _open_regular_file(path, deadline=deadline)
    if before.st_size > max_file_bytes:
        os.close(descriptor)
        raise ValueError("fixture exceeds per-file limit of {} bytes: {}".format(max_file_bytes, path))
    digest = hashlib.sha256()
    size = 0
    after = before
    try:
        while True:
            _require_open_deadline(deadline, path)
            chunk = os.read(descriptor, HASH_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            if size > max_file_bytes:
                raise ValueError(
                    "fixture exceeds per-file limit of {} bytes: {}".format(
                        max_file_bytes,
                        path,
                    )
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    # keep after comparison descriptor-based to work on Python 3.9 and remain symlink-safe
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("fixture changed while it was being hashed: {}".format(path))
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise ValueError("fixture identity changed while it was being hashed: {}".format(path))
    if not stat.S_ISREG(after.st_mode):
        raise ValueError("fixture is not a regular file: {}".format(path))
    return size, digest.hexdigest()


def build_corpus_inventory(
    corpus_root: Path,
    formats: Iterable[str],
    max_file_bytes: int = MAX_CORPUS_FILE_BYTES,
    max_total_bytes: int = MAX_CORPUS_TOTAL_BYTES,
    max_files: int = MAX_CORPUS_FILES,
    input_files: Iterable[str] = None,
    setup_timeout_seconds: Optional[float] = None,
) -> dict:
    if setup_timeout_seconds is not None:
        setup_timeout_seconds = _require_positive_timeout(
            setup_timeout_seconds,
            "setup_timeout_seconds",
        )
    setup_deadline = time.monotonic() + setup_timeout_seconds if setup_timeout_seconds else None

    root = corpus_root.resolve(strict=True)
    requested = {item.lower().lstrip(".") for item in formats}
    files = []
    total_bytes = 0
    if input_files is None:
        candidates = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower().lstrip(".") in requested:
                candidates.append(path)
                if len(candidates) > max_files:
                    raise ValueError("too many input files; maximum is {}".format(max_files))
        candidates.sort()
    else:
        candidates = []
        seen = set()
        for value in input_files:
            relative = str(value)
            posix_path = PurePosixPath(relative)
            windows_path = PureWindowsPath(relative)
            if (
                not relative
                or relative in {".", ".."}
                or posix_path.as_posix() != relative
                or posix_path.is_absolute()
                or windows_path.is_absolute()
                or "\\" in relative
                or any(part in {"", ".", ".."} for part in posix_path.parts)
            ):
                raise ValueError(
                    "fixture path must be a normalized relative path: {}".format(value)
                )
            candidate = root.joinpath(*posix_path.parts)
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
            if len(candidates) > max_files:
                raise ValueError("too many input files; maximum is {}".format(max_files))
    if len(candidates) > max_files:
        raise ValueError("too many input files; maximum is {}".format(max_files))
    for candidate in candidates:
        _require_open_deadline(setup_deadline, candidate)
        if candidate.suffix.lower().lstrip(".") not in requested:
            raise ValueError("fixture format was not requested: {}".format(candidate))
        resolved = candidate.resolve(strict=True)
        if candidate.is_symlink() or not _is_relative_to(resolved, root):
            raise ValueError("fixture resolves outside corpus: {}".format(candidate))
        size, sha256 = _fixture_digest(resolved, max_file_bytes, deadline=setup_deadline)
        total_bytes += size
        if total_bytes > max_total_bytes:
            raise ValueError(
                "corpus exceeds total limit of {} bytes".format(max_total_bytes)
            )
        files.append({
            "path": resolved.relative_to(root).as_posix(),
            "bytes": size,
            "sha256": sha256,
        })
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
    }


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / "bin" / "python"


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
    input_files: Iterable[str] = None,
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
    for input_file in input_files or ():
        command.extend(["--input-file", str(input_file)])
    return command


def _positive_float(value: str) -> float:
    return _require_positive_timeout(value, "timeout_seconds")


def _require_positive_timeout(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError("{} must be greater than zero".format(name))
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("{} must be greater than zero".format(name))
    return parsed


def _terminate_process_group(process: subprocess.Popen) -> None:
    group_signalled = False
    try:
        os.killpg(process.pid, signal.SIGTERM)
        group_signalled = True
    except ProcessLookupError:
        return
    except OSError:
        if process.poll() is None:
            process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    if group_signalled:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            if process.poll() is None:
                process.kill()
    elif process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def run_command(
    command: List[str],
    cwd: Path,
    timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS,
    capture_output: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess:
    # command is always an argv list assembled from validated paths, integers, and
    # the fixed package allowlist above; shell expansion is deliberately disabled.
    timeout_seconds = _require_positive_timeout(timeout_seconds, "command timeout")
    process = subprocess.Popen(  # nosemgrep: dangerous-subprocess-use-audit
        command,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        try:
            process.communicate(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    except BaseException:
        _terminate_process_group(process)
        try:
            process.communicate(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    if process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode,
            command,
            output=stdout,
            stderr=stderr,
        )
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def installed_package_versions(
    python_executable: Path,
    timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS,
) -> dict:
    # python_executable is created by make_venv_dir, and every remaining argv
    # entry is a fixed literal.  The call never invokes a shell.
    completed = run_command(
        [
            str(python_executable),
            "-m",
            "pip",
            "list",
            "--format",
            "json",
            "--disable-pip-version-check",
        ],
        PROJECT_ROOT,
        timeout_seconds,
        capture_output=True,
        text=True,
    )
    packages = json.loads(completed.stdout)
    return {
        str(package["name"]).lower(): str(package["version"])
        for package in sorted(packages, key=lambda item: str(item["name"]).lower())
    }


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


def competitor_report_status(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "ok": report.get("ok", False),
        "failure_reasons": report.get("failure_reasons", []),
        "file_count": report.get("file_count", 0),
        "converters": report.get("converters", []),
        "converter_status": report.get("converter_status", {}),
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
    corpus_sha256: str = "",
    corpus_file_count: int = None,
    input_files: Iterable[str] = None,
    setup_timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS,
) -> dict:
    timeout_seconds = _require_positive_timeout(timeout_seconds, "timeout_seconds")
    setup_timeout_seconds = _require_positive_timeout(
        setup_timeout_seconds,
        "setup_timeout_seconds",
    )
    deadline = time.monotonic() + setup_timeout_seconds
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
        "report_status": {},
        "requested_packages": competitor_install_packages(competitor),
        "pip_version": PIP_VERSION,
        "resolved_packages": {},
        "corpus_sha256": corpus_sha256,
        "timeout_seconds": timeout_seconds,
        "setup_timeout_seconds": setup_timeout_seconds,
    }

    def remaining_timeout(command: List[str]) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, setup_timeout_seconds)
        return remaining

    try:
        command = [str(python), "-m", "venv", str(venv_dir)]
        run_command(command, PROJECT_ROOT, remaining_timeout(command))
        command = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "pip=={}".format(PIP_VERSION),
        ]
        run_command(
            command,
            PROJECT_ROOT,
            remaining_timeout(command),
        )
        command = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            ".",
            *record["requested_packages"],
        ]
        run_command(
            command,
            PROJECT_ROOT,
            remaining_timeout(command),
        )
        pip_list_command = [
            str(python_executable),
            "-m",
            "pip",
            "list",
            "--format",
            "json",
            "--disable-pip-version-check",
        ]
        record["resolved_packages"] = installed_package_versions(
            python_executable,
            remaining_timeout(pip_list_command),
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
            input_files,
        )
        max_attempts = max(1, retry_failed_runs + 1)
        for attempt in range(max_attempts):
            record["attempts"] = attempt + 1
            try:
                run_command(command, PROJECT_ROOT, remaining_timeout(command))
                break
            except Exception as exc:
                record["errors"].append(repr(exc))
                if attempt + 1 >= max_attempts:
                    raise
        record["report_summary"] = summarize_competitor_report(output_path)
        record["report_status"] = competitor_report_status(output_path)
        status = record["report_status"]
        if status.get("ok") is not True:
            raise RuntimeError(
                "benchmark report failed: {}".format(
                    ", ".join(status.get("failure_reasons", [])) or "unknown reason"
                )
            )
        if status.get("file_count", 0) <= 0:
            raise RuntimeError("benchmark report contains no input files")
        if (
            corpus_file_count is not None
            and status.get("file_count") != corpus_file_count
        ):
            raise RuntimeError(
                "benchmark report file count {} does not match corpus inventory {}".format(
                    status.get("file_count"),
                    corpus_file_count,
                )
            )
        reported_converters = set(status.get("converters", []))
        if not {"dochan", competitor}.issubset(reported_converters):
            raise RuntimeError(
                "benchmark report is missing required converters: dochan, {}".format(
                    competitor
                )
            )
        record["ok"] = True
    except Exception as exc:
        record["error"] = repr(exc)
        raise CompetitorRunError(record) from exc
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
    input_files: Iterable[str] = None,
    setup_timeout_seconds: float = DEFAULT_SETUP_TIMEOUT_SECONDS,
) -> dict:
    timeout_seconds = _require_positive_timeout(timeout_seconds, "timeout_seconds")
    setup_timeout_seconds = _require_positive_timeout(
        setup_timeout_seconds,
        "setup_timeout_seconds",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = list(formats)
    competitors = list(competitors)
    input_files = list(input_files) if input_files is not None else None
    corpus_inventory = build_corpus_inventory(
        corpus_root,
        formats,
        setup_timeout_seconds=setup_timeout_seconds,
        input_files=input_files,
    )
    records = []
    for competitor in competitors if corpus_inventory["file_count"] else ():
        try:
            records.append(
                run_competitor(
                    competitor=competitor,
                    corpus_root=corpus_root,
                    output_dir=output_dir,
                    python=python,
                    formats=formats,
                    runs=runs,
                    keep_venv=keep_venv,
                    timeout_seconds=timeout_seconds,
                    retry_failed_runs=retry_failed_runs,
                    corpus_sha256=corpus_inventory["sha256"],
                    corpus_file_count=corpus_inventory["file_count"],
                    input_files=input_files,
                    setup_timeout_seconds=setup_timeout_seconds,
                )
            )
        except CompetitorRunError as exc:
            records.append(exc.record)
            if not keep_going:
                break
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
                "requested_packages": competitor_install_packages(competitor),
                "pip_version": PIP_VERSION,
                "resolved_packages": {},
                "corpus_sha256": corpus_inventory["sha256"],
            }
            records.append(record)
            if not keep_going:
                break
    failure_reasons = []
    if corpus_inventory["file_count"] == 0:
        failure_reasons.append("no input files")
    if not competitors:
        failure_reasons.append("no competitors requested")
    failed_records = [record for record in records if not record.get("ok")]
    if failed_records:
        failure_reasons.append(
            "competitor benchmark failures: {}".format(len(failed_records))
        )
    if corpus_inventory["file_count"] and len(records) != len(competitors):
        failure_reasons.append(
            "competitor benchmarks incomplete: {}/{}".format(
                len(records),
                len(competitors),
            )
        )
    index = {
        "corpus": str(corpus_root),
        "output_dir": str(output_dir),
        "requested_competitors": competitors,
        "timeout_seconds": timeout_seconds,
        "setup_timeout_seconds": setup_timeout_seconds,
        "corpus_inventory": corpus_inventory,
        "competitors": records,
        "failure_reasons": failure_reasons,
        "ok": not failure_reasons,
    }
    atomic_write_text(
        output_dir / "index.json",
        json.dumps(index, ensure_ascii=False, indent=2),
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dochan competitor benchmarks in isolated temporary venvs.")
    parser.add_argument("corpus", type=Path, help="Directory containing OOXML benchmark files")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for JSON reports")
    parser.add_argument("--competitors", default=",".join(SUPPORTED_COMPETITORS), help="Comma-separated competitors")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python executable used to create venvs")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated extensions")
    parser.add_argument("--runs", type=int, default=3, help="Repeated runs per converter/file")
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Seconds before a single conversion is recorded as timed out",
    )
    parser.add_argument(
        "--setup-timeout",
        type=_positive_float,
        default=DEFAULT_SETUP_TIMEOUT_SECONDS,
        help="Absolute seconds allowed for each competitor setup and benchmark process",
    )
    parser.add_argument("--retry-failed-runs", type=int, default=0, help="Retry a failed competitor benchmark command this many times")
    parser.add_argument("--keep-venv", action="store_true", help="Keep temporary venvs for debugging")
    parser.add_argument("--keep-going", action="store_true", help="Continue after a competitor install or run failure")
    parser.add_argument(
        "--input-file",
        action="append",
        default=None,
        help="Relative input path to include; repeat to restrict a reused corpus to the current run",
    )
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
        setup_timeout_seconds=args.setup_timeout,
        retry_failed_runs=args.retry_failed_runs,
        input_files=args.input_file,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
