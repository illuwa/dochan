#!/usr/bin/env python3
"""Run ``secaudit`` against a bounded snapshot of the current worktree.

Only paths returned by ``git ls-files --cached --others --exclude-standard``
are copied.  The committed secaudit baseline is deliberately left out so the
result reports every current finding instead of silently suppressing old ones.
A fixed local scanner configuration prevents repository content from disabling
or excluding required scans.  Semgrep sees only the installed Python security
rules through an isolated ``SECAUDIT_HOME``; gitleaks and OSV inspect the
bounded snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Sequence


DEFAULT_MAX_FILE_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_FILES = 100_000
DEFAULT_TIMEOUT_SECONDS = 900.0
MAX_FILE_LIST_BYTES = 16 * 1024 * 1024
MAX_PATH_BYTES = 4096
MAX_SCANNER_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_SECURITY_RULE_BYTES = 2 * 1024 * 1024
MAX_SECURITY_RULE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SECURITY_RULE_FILES = 10_000
GIT_TIMEOUT_SECONDS = 60.0
BASELINE_PARTS = (".secaudit", "baseline.json")
CONFIG_PARTS = (".secaudit", "config.json")
QUARANTINED_CONFIG_PARTS = (".secaudit", "repository-config.input.json")
PYTHON_SECURITY_RULE_PARTS = ("rules", "python", "lang", "security")
RULE_CONFIG_SUFFIXES = frozenset({".yaml", ".yml"})
SCANNER_REPORT_MODE = "all"
FINDING_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
BLOCKING_FINDING_SEVERITIES = frozenset({"critical", "high"})
INCOMPLETE_SCANNER_NOTE_MARKERS = (
    "미설치",
    "건너뜀",
    "실행 실패",
    "출력 파싱 실패",
    "룰셋 없음",
    "timeout",
    "시간 초과",
)
TRUSTED_SCANNER_CONFIG = {
    "exclude": [],
    "fail_on_severity": "high",
    "enable": {"semgrep": True, "gitleaks": True, "osv": True},
}


class AuditWrapperError(RuntimeError):
    """The wrapper could not construct or scan a trustworthy snapshot."""


@dataclass(frozen=True)
class SnapshotStats:
    file_count: int
    total_bytes: int
    missing_count: int
    skipped_baseline_count: int


@dataclass(frozen=True)
class ScannerResult:
    returncode: int
    stdout: bytes
    timed_out: bool = False
    output_too_large: bool = False


def _git_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return env


def _run_git(
    cwd: Path,
    arguments: Sequence[str],
    *,
    stdin: BinaryIO | None = None,
    timeout: float = GIT_TIMEOUT_SECONDS,
) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            env=_git_environment(),
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AuditWrapperError("git executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise AuditWrapperError("git operation timed out") from exc
    except OSError as exc:
        raise AuditWrapperError("git operation could not be started") from exc

    if result.returncode != 0:
        raise AuditWrapperError(
            f"git operation failed with exit code {result.returncode}"
        )
    return result.stdout


def resolve_repository(path: Path) -> Path:
    try:
        candidate = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise AuditWrapperError("repository path cannot be resolved") from exc
    if not candidate.is_dir():
        raise AuditWrapperError("repository path is not a directory")

    raw_root = _run_git(candidate, ["rev-parse", "--show-toplevel"])
    try:
        root = Path(os.fsdecode(raw_root.rstrip(b"\r\n"))).resolve(strict=True)
    except OSError as exc:
        raise AuditWrapperError("git repository root cannot be resolved") from exc
    if not root.is_dir():
        raise AuditWrapperError("git repository root is not a directory")
    return root


def _validate_git_path(raw_path: bytes) -> tuple[str, PurePosixPath]:
    if not raw_path or len(raw_path) > MAX_PATH_BYTES:
        raise AuditWrapperError("git returned an invalid path")
    text = os.fsdecode(raw_path)
    pure = PurePosixPath(text)
    if pure.is_absolute() or str(pure) != text:
        raise AuditWrapperError("git returned a non-canonical path")
    if any(part in ("", ".", "..") for part in pure.parts):
        raise AuditWrapperError("git returned an unsafe relative path")
    if any(part.casefold() == ".git" for part in pure.parts):
        raise AuditWrapperError("git returned a reserved metadata path")
    return text, pure


def list_snapshot_paths(repo: Path) -> list[tuple[str, PurePosixPath]]:
    output = _run_git(
        repo,
        [
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--full-name",
        ],
    )
    if len(output) > MAX_FILE_LIST_BYTES:
        raise AuditWrapperError("git file list exceeds the safety limit")
    if output and not output.endswith(b"\0"):
        raise AuditWrapperError("git returned a malformed file list")

    raw_paths = output[:-1].split(b"\0") if output else []
    if len(raw_paths) > DEFAULT_MAX_FILES:
        raise AuditWrapperError("git file count exceeds the safety limit")

    paths: list[tuple[str, PurePosixPath]] = []
    seen: set[bytes] = set()
    for raw_path in raw_paths:
        if raw_path in seen:
            raise AuditWrapperError("git returned a duplicate path")
        seen.add(raw_path)
        paths.append(_validate_git_path(raw_path))
    return paths


def _copy_regular_file(
    source: Path,
    destination: Path,
    *,
    expected_stat: os.stat_result,
    max_file_bytes: int,
) -> tuple[int, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise AuditWrapperError("a selected file could not be opened safely") from exc

    copied = 0
    try:
        opened_stat = os.fstat(descriptor)
        identity_before = (expected_stat.st_dev, expected_stat.st_ino)
        identity_after = (opened_stat.st_dev, opened_stat.st_ino)
        if identity_before != identity_after or not stat.S_ISREG(opened_stat.st_mode):
            raise AuditWrapperError("a selected file changed during snapshot creation")
        if opened_stat.st_size > max_file_bytes:
            raise AuditWrapperError("a selected file exceeds the per-file safety limit")

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            output = destination.open("xb")
        except OSError as exc:
            raise AuditWrapperError("snapshot destination could not be created") from exc

        with os.fdopen(descriptor, "rb", closefd=False) as input_file, output:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > max_file_bytes or copied > opened_stat.st_size:
                    raise AuditWrapperError("a selected file changed while being copied")
                output.write(chunk)
        if copied != opened_stat.st_size:
            raise AuditWrapperError("a selected file changed while being copied")
    finally:
        os.close(descriptor)

    mode = 0o755 if opened_stat.st_mode & 0o111 else 0o644
    destination.chmod(mode)
    return copied, mode


def _index_snapshot_file(snapshot: Path, relative_path: str, mode: int) -> None:
    destination = snapshot.joinpath(*PurePosixPath(relative_path).parts)
    with destination.open("rb") as input_file:
        object_id = _run_git(
            snapshot,
            ["hash-object", "-w", "--no-filters", "--stdin"],
            stdin=input_file,
        ).strip()
    if len(object_id) not in (40, 64):
        raise AuditWrapperError("git returned an invalid object identifier")
    object_text = object_id.decode("ascii", errors="strict")
    index_mode = "100755" if mode & 0o111 else "100644"
    _run_git(
        snapshot,
        ["update-index", "--add", "--cacheinfo", f"{index_mode},{object_text},{relative_path}"],
    )


def build_snapshot(
    repo: Path,
    snapshot: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
) -> SnapshotStats:
    if min(max_file_bytes, max_total_bytes, max_files) <= 0:
        raise AuditWrapperError("snapshot limits must be positive")

    paths = list_snapshot_paths(repo)
    if len(paths) > max_files:
        raise AuditWrapperError("selected file count exceeds the safety limit")
    try:
        snapshot.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError as exc:
        raise AuditWrapperError("temporary snapshot could not be created") from exc
    _run_git(snapshot, ["-c", "init.templateDir=", "init", "--quiet"])

    repo_real = repo.resolve(strict=True)
    file_count = 0
    total_bytes = 0
    missing_count = 0
    skipped_baseline_count = 0

    for relative_text, relative in paths:
        if relative.parts == BASELINE_PARTS:
            skipped_baseline_count += 1
            continue

        source = repo.joinpath(*relative.parts)
        try:
            source_stat = source.lstat()
        except FileNotFoundError:
            missing_count += 1
            continue
        except OSError as exc:
            raise AuditWrapperError("a selected path could not be inspected") from exc

        if not stat.S_ISREG(source_stat.st_mode):
            raise AuditWrapperError(
                "selected symlinks, directories, and special files are not allowed"
            )
        try:
            source.resolve(strict=True).relative_to(repo_real)
        except (OSError, ValueError) as exc:
            raise AuditWrapperError("a selected path escapes the repository") from exc
        if source_stat.st_size > max_file_bytes:
            raise AuditWrapperError("a selected file exceeds the per-file safety limit")
        if total_bytes + source_stat.st_size > max_total_bytes:
            raise AuditWrapperError("selected files exceed the total-size safety limit")

        destination = snapshot.joinpath(*relative.parts)
        copied, mode = _copy_regular_file(
            source,
            destination,
            expected_stat=source_stat,
            max_file_bytes=max_file_bytes,
        )
        if total_bytes + copied > max_total_bytes:
            raise AuditWrapperError("selected files exceed the total-size safety limit")
        total_bytes += copied
        file_count += 1
        _index_snapshot_file(snapshot, relative_text, mode)

    return SnapshotStats(
        file_count=file_count,
        total_bytes=total_bytes,
        missing_count=missing_count,
        skipped_baseline_count=skipped_baseline_count,
    )


def _install_trusted_scanner_config(snapshot: Path) -> None:
    """Quarantine repository config and install an untracked fixed config."""
    config = snapshot.joinpath(*CONFIG_PARTS)
    quarantined = snapshot.joinpath(*QUARANTINED_CONFIG_PARTS)
    if config.exists():
        if quarantined.exists():
            raise AuditWrapperError(
                "repository scanner configuration quarantine path is occupied"
            )
        try:
            config_stat = config.stat()
            config.replace(quarantined)
        except OSError as exc:
            raise AuditWrapperError(
                "repository scanner configuration could not be quarantined"
            ) from exc
        _run_git(
            snapshot,
            ["update-index", "--force-remove", "--", "/".join(CONFIG_PARTS)],
        )
        _index_snapshot_file(
            snapshot,
            "/".join(QUARANTINED_CONFIG_PARTS),
            config_stat.st_mode,
        )
    else:
        try:
            config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise AuditWrapperError(
                "trusted scanner configuration directory could not be created"
            ) from exc

    encoded_config = (
        json.dumps(TRUSTED_SCANNER_CONFIG, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    try:
        with config.open("xb") as stream:
            stream.write(encoded_config)
        config.chmod(0o600)
    except OSError as exc:
        raise AuditWrapperError(
            "trusted scanner configuration could not be installed"
        ) from exc


def _terminate_process_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        process.kill()
    process.wait()


def _resolve_python_security_rules(configured_path: Path | None) -> Path:
    if configured_path is None:
        secaudit_home = Path(
            os.environ.get("SECAUDIT_HOME", str(Path.home() / ".secaudit"))
        )
        candidate = secaudit_home.joinpath(*PYTHON_SECURITY_RULE_PARTS)
    else:
        candidate = configured_path.expanduser()

    try:
        candidate_stat = candidate.lstat()
    except OSError as exc:
        raise AuditWrapperError("installed Python security rules were not found") from exc
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise AuditWrapperError("Python security rules directory cannot be a symlink")
    if not stat.S_ISDIR(candidate_stat.st_mode):
        raise AuditWrapperError("Python security rules path is not a directory")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise AuditWrapperError("Python security rules cannot be resolved") from exc


def _copy_python_security_rules(source: Path, scanner_home: Path) -> None:
    destination_root = scanner_home / "rules" / "python"
    try:
        scanner_home.mkdir(mode=0o700, parents=False, exist_ok=False)
        destination_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    except OSError as exc:
        raise AuditWrapperError("temporary secaudit home could not be created") from exc

    source_real = source.resolve(strict=True)
    config_count = 0
    total_bytes = 0

    def fail_on_walk_error(error: OSError) -> None:
        raise AuditWrapperError(
            "Python security rules could not be inspected"
        ) from error

    try:
        walker = os.walk(
            source_real,
            topdown=True,
            onerror=fail_on_walk_error,
            followlinks=False,
        )
        for current_text, directory_names, file_names in walker:
            current = Path(current_text)
            for name in directory_names:
                directory = current / name
                directory_stat = directory.lstat()
                if stat.S_ISLNK(directory_stat.st_mode):
                    raise AuditWrapperError("Python security rules contain a symlink")
                if not stat.S_ISDIR(directory_stat.st_mode):
                    raise AuditWrapperError(
                        "Python security rules contain a special filesystem entry"
                    )

            for name in file_names:
                rule = current / name
                rule_stat = rule.lstat()
                if stat.S_ISLNK(rule_stat.st_mode):
                    raise AuditWrapperError("Python security rules contain a symlink")
                if not stat.S_ISREG(rule_stat.st_mode):
                    raise AuditWrapperError(
                        "Python security rules contain a special filesystem entry"
                    )
                if rule.suffix.lower() not in RULE_CONFIG_SUFFIXES:
                    continue
                try:
                    relative = rule.resolve(strict=True).relative_to(source_real)
                except (OSError, ValueError) as exc:
                    raise AuditWrapperError(
                        "a Python security rule escapes its rules directory"
                    ) from exc
                if config_count >= MAX_SECURITY_RULE_FILES:
                    raise AuditWrapperError(
                        "Python security rule count exceeds the safety limit"
                    )
                if total_bytes + rule_stat.st_size > MAX_SECURITY_RULE_TOTAL_BYTES:
                    raise AuditWrapperError(
                        "Python security rules exceed the total-size safety limit"
                    )
                copied, _ = _copy_regular_file(
                    rule,
                    destination_root.joinpath(*relative.parts),
                    expected_stat=rule_stat,
                    max_file_bytes=MAX_SECURITY_RULE_BYTES,
                )
                total_bytes += copied
                config_count += 1
    except OSError as exc:
        raise AuditWrapperError("Python security rules could not be inspected") from exc

    if config_count == 0:
        raise AuditWrapperError("Python security rules contain no YAML configurations")


def _run_scanner(
    executable: Path,
    snapshot: Path,
    scanner_home: Path,
    timeout_seconds: float,
) -> ScannerResult:
    scanner_environment = os.environ.copy()
    scanner_environment.update(
        {
            "SECAUDIT_HOME": str(scanner_home),
            "SEMGREP_SEND_METRICS": "off",
        }
    )
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            # `_resolve_secaudit` canonicalizes an existing executable, argv is
            # a fixed list, and shell execution is never enabled.
            process = subprocess.Popen(  # nosemgrep: dangerous-subprocess-use-audit
                [str(executable), "scan", "--repo", str(snapshot), "--json"],
                cwd=snapshot,
                env=scanner_environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError as exc:
            raise AuditWrapperError("secaudit could not be started") from exc

        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            return ScannerResult(returncode=124, stdout=b"", timed_out=True)

        output_size = os.fstat(stdout_file.fileno()).st_size
        if output_size > MAX_SCANNER_OUTPUT_BYTES:
            return ScannerResult(
                returncode=returncode,
                stdout=b"",
                output_too_large=True,
            )
        stdout_file.seek(0)
        return ScannerResult(returncode=returncode, stdout=stdout_file.read())


def _bounded_text(value: object, limit: int = 512) -> str:
    if not isinstance(value, str):
        return ""
    safe = value.encode("utf-8", errors="backslashreplace").decode("utf-8")
    return safe if len(safe) <= limit else safe[:limit] + "..."


def _safe_report(
    raw_output: bytes, stats: SnapshotStats
) -> tuple[dict[str, object], bool]:
    try:
        payload = json.loads(raw_output.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditWrapperError("secaudit returned an invalid JSON report") from exc
    if not isinstance(payload, dict):
        raise AuditWrapperError("secaudit returned an unexpected JSON report")

    mode = payload.get("mode")
    total = payload.get("total")
    raw_findings = payload.get("new")
    if mode != SCANNER_REPORT_MODE:
        raise AuditWrapperError("secaudit returned an unexpected report mode")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise AuditWrapperError("secaudit returned an invalid finding total")
    if not isinstance(raw_findings, list):
        raise AuditWrapperError("secaudit returned an unexpected finding list")
    if total != len(raw_findings):
        raise AuditWrapperError("secaudit finding total does not match its finding list")

    findings: list[dict[str, object]] = []
    for raw_finding in raw_findings:
        if not isinstance(raw_finding, dict):
            raise AuditWrapperError("secaudit returned an unexpected finding")
        raw_severity = raw_finding.get("severity")
        if not isinstance(raw_severity, str):
            raise AuditWrapperError("secaudit returned an invalid finding severity")
        severity = raw_severity.strip().casefold()
        if severity not in FINDING_SEVERITIES:
            raise AuditWrapperError("secaudit returned an invalid finding severity")
        line = raw_finding.get("line")
        findings.append(
            {
                "tool": _bounded_text(raw_finding.get("tool"), 64),
                "rule_id": _bounded_text(raw_finding.get("rule_id"), 512),
                "severity": severity,
                "path": _bounded_text(raw_finding.get("path"), MAX_PATH_BYTES),
                "line": line if isinstance(line, int) and line >= 0 else 0,
                "also_count": len(raw_finding.get("also") or [])
                if isinstance(raw_finding.get("also"), list)
                else 0,
            }
        )

    notes = payload.get("notes")
    if not isinstance(notes, list) or not all(
        isinstance(note, str) for note in notes
    ):
        raise AuditWrapperError("secaudit returned unexpected scanner diagnostics")
    incomplete_scanner = any(
        marker in note.casefold()
        for note in notes
        for marker in INCOMPLETE_SCANNER_NOTE_MARKERS
    )

    report = {
        "mode": mode,
        "total_findings": len(findings),
        "findings": findings,
        "scanner_diagnostic_count": len(notes),
        "snapshot": {
            "file_count": stats.file_count,
            "total_bytes": stats.total_bytes,
            "missing_count": stats.missing_count,
            "baseline_suppression": False,
        },
    }
    return report, incomplete_scanner


def _has_blocking_findings(report: dict[str, object]) -> bool:
    findings = report.get("findings", [])
    return any(
        isinstance(finding, dict)
        and finding.get("severity") in BLOCKING_FINDING_SEVERITIES
        for finding in findings
    )


def _resolve_secaudit(executable: str) -> Path:
    resolved_name = shutil.which(executable)
    if not resolved_name:
        raise AuditWrapperError("secaudit executable was not found")
    try:
        path = Path(resolved_name).resolve(strict=True)
    except OSError as exc:
        raise AuditWrapperError("secaudit executable cannot be resolved") from exc
    if not path.is_file() or not os.access(path, os.X_OK):
        raise AuditWrapperError("secaudit executable is not runnable")
    return path


def run_security_audit(
    repo: Path,
    *,
    secaudit: str = "secaudit",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
    temp_parent: Path | None = None,
    security_rules_dir: Path | None = None,
) -> int:
    if timeout_seconds <= 0:
        raise AuditWrapperError("scanner timeout must be positive")
    root = resolve_repository(repo)
    executable = _resolve_secaudit(secaudit)
    resolved_security_rules = _resolve_python_security_rules(security_rules_dir)

    temp_parent_text = str(temp_parent) if temp_parent is not None else None
    with tempfile.TemporaryDirectory(
        prefix="dochan-secaudit-", dir=temp_parent_text
    ) as temp_directory:
        snapshot = Path(temp_directory) / "repository"
        stats = build_snapshot(
            root,
            snapshot,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
            max_files=max_files,
        )
        _install_trusted_scanner_config(snapshot)
        scanner_home = Path(temp_directory) / "secaudit-home"
        _copy_python_security_rules(resolved_security_rules, scanner_home)
        result = _run_scanner(
            executable,
            snapshot,
            scanner_home,
            timeout_seconds,
        )

        if result.timed_out:
            print(
                json.dumps(
                    {
                        "status": "timeout",
                        "timeout_seconds": timeout_seconds,
                        "raw_scanner_output": "withheld",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 124
        if result.output_too_large:
            print(
                json.dumps(
                    {
                        "status": "invalid-report",
                        "reason": "scanner output exceeded the safety limit",
                        "raw_scanner_output": "withheld",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return result.returncode if result.returncode else 2

        try:
            report, incomplete_scanner = _safe_report(result.stdout, stats)
        except AuditWrapperError:
            print(
                json.dumps(
                    {
                        "status": "invalid-report",
                        "raw_scanner_output": "withheld",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return result.returncode if result.returncode else 2

        if incomplete_scanner:
            print(
                json.dumps(
                    {
                        "status": "invalid-report",
                        "reason": "one or more required scanners did not complete",
                        "raw_scanner_output": "withheld",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            if result.returncode < 0:
                return 128 + abs(result.returncode)
            return result.returncode if result.returncode else 2

        print(json.dumps(report, ensure_ascii=False, indent=2))
        if result.returncode < 0:
            return 128 + abs(result.returncode)
        if _has_blocking_findings(report) and result.returncode == 0:
            return 1
        return result.returncode


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="repository or its subdirectory"
    )
    parser.add_argument(
        "--secaudit", default="secaudit", help="installed secaudit executable"
    )
    parser.add_argument(
        "--security-rules-dir",
        type=Path,
        help=(
            "Python security rule directory "
            "(default: $SECAUDIT_HOME/rules/python/lang/security)"
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-file-bytes", type=_positive_int, default=DEFAULT_MAX_FILE_BYTES
    )
    parser.add_argument(
        "--max-total-bytes", type=_positive_int, default=DEFAULT_MAX_TOTAL_BYTES
    )
    parser.add_argument("--max-files", type=_positive_int, default=DEFAULT_MAX_FILES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return run_security_audit(
            args.repo,
            secaudit=args.secaudit,
            timeout_seconds=args.timeout_seconds,
            max_file_bytes=args.max_file_bytes,
            max_total_bytes=args.max_total_bytes,
            max_files=args.max_files,
            security_rules_dir=args.security_rules_dir,
        )
    except AuditWrapperError as exc:
        print(f"tracked-security-audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
