from __future__ import annotations

import json
import os
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from scripts.run_tracked_security_audit import (
    AuditWrapperError,
    build_snapshot,
    run_security_audit,
)


RAW_SECRET = "sk-live-secret-that-must-never-be-printed"


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "-c", "init.templateDir=", "init", "--quiet")
    return path


def _write_security_rules(path: Path) -> Path:
    nested = path / "audit"
    nested.mkdir(parents=True)
    (path / "top-level.yaml").write_text("rules: []\n", encoding="utf-8")
    (nested / "nested.yml").write_text("rules: []\n", encoding="utf-8")
    (nested / "fixture.py").write_text("pass\n", encoding="utf-8")
    return path


def _write_fake_secaudit(
    path: Path,
    *,
    record_path: Path | None = None,
    exit_code: int = 0,
    sleep_seconds: float = 0,
    valid_json: bool = True,
    notes: list[str] | None = None,
    mode: object = "all",
    total: object = 1,
    severity: object = "high",
) -> Path:
    record_statement = ""
    if record_path is not None:
        record_statement = textwrap.dedent(
            f"""
            tracked = subprocess.check_output(
                ["git", "ls-files", "-z"], cwd=snapshot
            ).decode().rstrip("\\0").split("\\0")
            scanner_home = Path(os.environ["SECAUDIT_HOME"])
            python_rules = scanner_home / "rules" / "python"
            Path({str(record_path)!r}).write_text(
                json.dumps(
                    {{
                        "snapshot": str(snapshot),
                        "scanner_home": str(scanner_home),
                        "tracked": tracked,
                        "baseline_exists": (
                            snapshot / ".secaudit" / "baseline.json"
                        ).exists(),
                        "config": json.loads(
                            (snapshot / ".secaudit" / "config.json").read_text(
                                encoding="utf-8"
                            )
                        ),
                        "rule_files": sorted(
                            str(rule.relative_to(python_rules))
                            for rule in python_rules.rglob("*")
                            if rule.is_file()
                        ),
                    }}
                ),
                encoding="utf-8",
            )
            """
        )

    if valid_json:
        report_notes = notes
        if report_notes is None:
            report_notes = [f"unsafe diagnostic {RAW_SECRET}"]
        output_statement = textwrap.dedent(
            f"""
            print(json.dumps({{
                "mode": {mode!r},
                "total": {total!r},
                "new": [{{
                    "tool": "gitleaks",
                    "rule_id": "generic-api-key",
                    "title": "unsafe title {RAW_SECRET}",
                    "path": "tracked.py",
                    "line": 7,
                    "severity": {severity!r},
                    "snippet": "{RAW_SECRET}",
                    "fingerprint": "sha256:{RAW_SECRET}",
                    "also": ["second-rule"],
                }}],
                "notes": {report_notes!r},
            }}))
            """
        )
    else:
        output_statement = f'print("invalid scanner output {RAW_SECRET}")\n'

    source = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import os
        import subprocess
        import sys
        import time
        from pathlib import Path

        snapshot = Path(sys.argv[sys.argv.index("--repo") + 1])
        assert sys.argv[1] == "scan"
        assert "--json" in sys.argv
        """
    )
    source += record_statement
    source += f"time.sleep({sleep_seconds!r})\n"
    source += f'sys.stderr.write("scanner stderr {RAW_SECRET}\\n")\n'
    source += output_statement
    source += f"raise SystemExit({exit_code})\n"
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_audit_snapshots_only_git_selected_files_and_omits_baseline(
    tmp_path, capsys
):
    repo = _init_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (repo / "tracked.py").write_text("print('tracked')\n", encoding="utf-8")
    (repo / ".secaudit").mkdir()
    (repo / ".secaudit" / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / ".secaudit" / "baseline.json").write_text(
        '{"fingerprints": ["opaque"]}\n', encoding="utf-8"
    )
    _git(
        repo,
        "add",
        "--",
        ".gitignore",
        "tracked.py",
        ".secaudit/config.json",
        ".secaudit/baseline.json",
    )
    (repo / "untracked.py").write_text("print('untracked')\n", encoding="utf-8")
    ignored = repo / "ignored"
    ignored.mkdir()
    with (ignored / "huge.bin").open("wb") as stream:
        stream.truncate(8 * 1024 * 1024)

    record = tmp_path / "scanner-record.json"
    fake = _write_fake_secaudit(
        tmp_path / "fake-secaudit", record_path=record, exit_code=1
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")
    temp_parent = tmp_path / "snapshots"
    temp_parent.mkdir()
    expected_total_bytes = sum(
        (repo / relative).stat().st_size
        for relative in (
            ".gitignore",
            ".secaudit/config.json",
            "tracked.py",
            "untracked.py",
        )
    )

    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        max_file_bytes=1024 * 1024,
        max_total_bytes=4 * 1024 * 1024,
        temp_parent=temp_parent,
        security_rules_dir=security_rules,
    )

    assert returncode == 1
    scanner_record = json.loads(record.read_text(encoding="utf-8"))
    assert scanner_record["baseline_exists"] is False
    assert scanner_record["config"] == {
        "exclude": [],
        "fail_on_severity": "high",
        "enable": {"semgrep": True, "gitleaks": True, "osv": True},
    }
    assert scanner_record["rule_files"] == ["audit/nested.yml", "top-level.yaml"]
    assert set(scanner_record["tracked"]) == {
        ".gitignore",
        ".secaudit/repository-config.input.json",
        "tracked.py",
        "untracked.py",
    }
    assert not Path(scanner_record["snapshot"]).exists()
    assert not Path(scanner_record["scanner_home"]).exists()

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["snapshot"] == {
        "file_count": 4,
        "total_bytes": expected_total_bytes,
        "missing_count": 0,
        "baseline_suppression": False,
    }
    assert report["findings"] == [
        {
            "tool": "gitleaks",
            "rule_id": "generic-api-key",
            "severity": "high",
            "path": "tracked.py",
            "line": 7,
            "also_count": 1,
        }
    ]
    assert captured.err == ""
    assert RAW_SECRET not in captured.out
    assert RAW_SECRET not in captured.err


def test_audit_replaces_repository_controlled_scanner_bypass_config(
    tmp_path, capsys
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    (repo / ".secaudit").mkdir()
    (repo / ".secaudit" / "config.json").write_text(
        json.dumps(
            {
                "exclude": ["."],
                "enable": {
                    "semgrep": False,
                    "gitleaks": False,
                    "osv": False,
                },
            }
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "--", "tracked.py", ".secaudit/config.json")
    record = tmp_path / "scanner-record.json"
    fake = _write_fake_secaudit(
        tmp_path / "fake-secaudit",
        record_path=record,
        severity="medium",
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")

    assert run_security_audit(
        repo,
        secaudit=str(fake),
        security_rules_dir=security_rules,
    ) == 0

    scanner_record = json.loads(record.read_text(encoding="utf-8"))
    assert scanner_record["config"] == {
        "exclude": [],
        "fail_on_severity": "high",
        "enable": {"semgrep": True, "gitleaks": True, "osv": True},
    }
    assert ".secaudit/repository-config.input.json" in scanner_record["tracked"]
    assert ".secaudit/config.json" not in scanner_record["tracked"]
    capsys.readouterr()


@pytest.mark.parametrize(
    ("max_file_bytes", "max_total_bytes", "expected_message"),
    [
        (3, 100, "per-file"),
        (100, 7, "total-size"),
    ],
)
def test_snapshot_enforces_file_and_total_size_limits(
    tmp_path, max_file_bytes, max_total_bytes, expected_message
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "a.txt").write_bytes(b"1234")
    (repo / "b.txt").write_bytes(b"5678")
    _git(repo, "add", "--", "a.txt", "b.txt")

    with pytest.raises(AuditWrapperError, match=expected_message):
        build_snapshot(
            repo,
            tmp_path / "snapshot",
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )


def test_snapshot_rejects_a_symlink_that_replaces_a_selected_file(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    selected = repo / "selected.txt"
    selected.write_text("safe\n", encoding="utf-8")
    _git(repo, "add", "--", "selected.txt")
    selected.unlink()
    outside = tmp_path / "outside-secret.txt"
    outside.write_text(RAW_SECRET, encoding="utf-8")
    selected.symlink_to(outside)

    with pytest.raises(AuditWrapperError, match="symlinks"):
        build_snapshot(repo, tmp_path / "snapshot")


def test_snapshot_rejects_a_special_file_without_opening_it(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO files are not supported on this platform")
    repo = _init_repo(tmp_path / "repo")
    selected = repo / "selected.pipe"
    selected.write_text("index this path\n", encoding="utf-8")
    _git(repo, "add", "--", "selected.pipe")
    selected.unlink()
    os.mkfifo(selected)

    with pytest.raises(AuditWrapperError, match="special files"):
        build_snapshot(repo, tmp_path / "snapshot")


def test_scanner_timeout_returns_124_and_cleans_the_snapshot(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(
        tmp_path / "slow-secaudit",
        sleep_seconds=10,
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")
    temp_parent = tmp_path / "snapshots"
    temp_parent.mkdir()

    started = time.monotonic()
    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        timeout_seconds=0.5,
        temp_parent=temp_parent,
        security_rules_dir=security_rules,
    )

    assert returncode == 124
    assert time.monotonic() - started < 3
    assert list(temp_parent.iterdir()) == []
    captured = capsys.readouterr()
    assert '"status": "timeout"' in captured.err
    assert RAW_SECRET not in captured.out
    assert RAW_SECRET not in captured.err


def test_non_json_scanner_failure_preserves_exit_code_without_raw_output(
    tmp_path, capsys
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(
        tmp_path / "broken-secaudit", exit_code=7, valid_json=False
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")

    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        security_rules_dir=security_rules,
    )

    assert returncode == 7
    captured = capsys.readouterr()
    assert '"status": "invalid-report"' in captured.err
    assert RAW_SECRET not in captured.out
    assert RAW_SECRET not in captured.err


@pytest.mark.parametrize(
    "diagnostic",
    [
        "semgrep 미설치",
        "semgrep 건너뜀",
        "semgrep 실행 실패(rc=2)",
        "semgrep 출력 파싱 실패(rc=1)",
        "semgrep 룰셋 없음",
        "semgrep Timeout while evaluating a rule",
        "semgrep 시간 초과(30s)",
    ],
)
def test_successful_scanner_exit_fails_closed_for_incomplete_diagnostics(
    tmp_path, capsys, diagnostic
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(
        tmp_path / "incomplete-secaudit",
        notes=[f"{diagnostic}: {RAW_SECRET}"],
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")

    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        security_rules_dir=security_rules,
    )

    assert returncode == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "invalid-report",
        "reason": "one or more required scanners did not complete",
        "raw_scanner_output": "withheld",
    }
    assert diagnostic not in captured.err
    assert RAW_SECRET not in captured.err


def test_successful_scanner_exit_allows_benign_notes_without_disclosing_them(
    tmp_path, capsys
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    benign_note = f"scanner advisory only: {RAW_SECRET}"
    fake = _write_fake_secaudit(
        tmp_path / "complete-secaudit",
        notes=[benign_note],
        severity="medium",
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")

    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        security_rules_dir=security_rules,
    )

    assert returncode == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["scanner_diagnostic_count"] == 1
    assert captured.err == ""
    assert benign_note not in captured.out
    assert RAW_SECRET not in captured.out


def test_audit_uses_default_secaudit_home_without_host_state(
    tmp_path, monkeypatch, capsys
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    secaudit_home = tmp_path / "installed-secaudit"
    _write_security_rules(secaudit_home / "rules" / "python" / "lang" / "security")
    monkeypatch.setenv("SECAUDIT_HOME", str(secaudit_home))
    record = tmp_path / "scanner-record.json"
    fake = _write_fake_secaudit(
        tmp_path / "fake-secaudit",
        record_path=record,
        severity="medium",
    )

    assert run_security_audit(repo, secaudit=str(fake)) == 0

    scanner_record = json.loads(record.read_text(encoding="utf-8"))
    assert scanner_record["rule_files"] == ["audit/nested.yml", "top-level.yaml"]
    assert Path(scanner_record["scanner_home"]) != secaudit_home
    capsys.readouterr()


def test_audit_fails_closed_when_security_rules_are_missing(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(tmp_path / "fake-secaudit")

    with pytest.raises(AuditWrapperError, match="Python security rules"):
        run_security_audit(
            repo,
            secaudit=str(fake),
            security_rules_dir=tmp_path / "missing-rules",
        )


def test_audit_rejects_symlinked_security_rules(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(tmp_path / "fake-secaudit")
    rules = _write_security_rules(tmp_path / "security-rules")
    outside = tmp_path / "outside.yaml"
    outside.write_text("rules: []\n", encoding="utf-8")
    (rules / "linked.yaml").symlink_to(outside)

    with pytest.raises(AuditWrapperError, match="symlink"):
        run_security_audit(
            repo,
            secaudit=str(fake),
            security_rules_dir=rules,
        )


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_successful_scanner_exit_is_overridden_for_blocking_findings(
    tmp_path, capsys, severity
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(
        tmp_path / "unsafe-secaudit",
        severity=severity,
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")

    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        security_rules_dir=security_rules,
    )

    assert returncode == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["total_findings"] == 1
    assert report["findings"][0]["severity"] == severity
    assert captured.err == ""
    assert RAW_SECRET not in captured.out


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"total": 0}, "total"),
        ({"mode": "diff"}, "mode"),
        ({"severity": f"high-{RAW_SECRET}"}, "severity"),
    ],
)
def test_successful_scanner_exit_rejects_inconsistent_report_schema_without_raw_output(
    tmp_path, capsys, overrides, reason
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.py").write_text("pass\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.py")
    fake = _write_fake_secaudit(
        tmp_path / "inconsistent-secaudit",
        **overrides,
    )
    security_rules = _write_security_rules(tmp_path / "security-rules")

    returncode = run_security_audit(
        repo,
        secaudit=str(fake),
        security_rules_dir=security_rules,
    )

    assert returncode == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "invalid-report",
        "raw_scanner_output": "withheld",
    }
    assert reason not in captured.err
    assert RAW_SECRET not in captured.err


def test_snapshot_skips_an_in_repo_symlink_without_following_it(tmp_path):
    # 저장소 안의 파일을 가리키는 링크(예: CLAUDE.md -> AGENTS.md)는 대상이 이미
    # 선택돼 있으므로 건너뛴다. 저장소 밖으로 나가는 링크는 여전히 거부한다.
    repo = _init_repo(tmp_path / "repo")
    target = repo / "AGENTS.md"
    target.write_text("shared agent guide\n", encoding="utf-8")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    _git(repo, "add", "--", "AGENTS.md", "CLAUDE.md")

    stats = build_snapshot(repo, tmp_path / "snapshot")

    assert stats.skipped_symlink_count == 1
    assert (tmp_path / "snapshot" / "AGENTS.md").is_file()
    assert not (tmp_path / "snapshot" / "CLAUDE.md").exists()


def test_snapshot_git_operations_ignore_inherited_hook_repository_env(tmp_path, monkeypatch):
    # git 훅 안에서는 GIT_DIR/GIT_INDEX_FILE 이 상속된다. 이를 그대로 물려주면 스냅샷용
    # git add 가 실제 저장소 인덱스에 실행돼 커밋 대상이 통째로 바뀐다.
    repo = _init_repo(tmp_path / "repo")
    (repo / "selected.txt").write_text("safe\n", encoding="utf-8")
    _git(repo, "add", "--", "selected.txt")
    other = _init_repo(tmp_path / "other")
    (other / "untouched.txt").write_text("do not stage me\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_PREFIX", "")

    stats = build_snapshot(repo, tmp_path / "snapshot")

    for name in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX"):
        monkeypatch.delenv(name)
    assert stats.file_count == 1
    assert (tmp_path / "snapshot" / "selected.txt").is_file()
    staged_in_other = subprocess.run(
        ["git", "ls-files", "--cached"], cwd=other, stdout=subprocess.PIPE, check=True
    ).stdout
    assert staged_in_other == b""
