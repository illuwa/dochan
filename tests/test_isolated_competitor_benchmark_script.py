import hashlib
import json
import subprocess
import sys
import os
import time
from pathlib import Path

import pytest

from scripts import run_isolated_competitor_benchmark as script
from scripts.run_isolated_competitor_benchmark import (
    benchmark_command,
    competitor_install_packages,
    make_venv_dir,
    parse_competitors,
    run_command,
    run_competitor,
    summarize_competitor_report,
    venv_python,
)


def test_parse_competitors_normalizes_and_filters_supported_names():
    assert parse_competitors(" markitdown,docling,MARKITDOWN ") == ["markitdown", "docling"]


def test_competitor_install_packages_are_pinned_to_converter_extras():
    assert competitor_install_packages("markitdown") == ["markitdown[docx,pptx,xlsx]==0.1.7"]
    assert competitor_install_packages("docling") == ["docling==2.119.0"]


def test_corpus_inventory_records_stable_fixture_digests(tmp_path):
    corpus = tmp_path / "corpus"
    (corpus / "docx").mkdir(parents=True)
    (corpus / "xlsx").mkdir()
    (corpus / "docx" / "a.docx").write_bytes(b"alpha")
    (corpus / "xlsx" / "b.xlsx").write_bytes(b"beta")
    (corpus / "ignored.txt").write_bytes(b"ignored")

    inventory = script.build_corpus_inventory(corpus, ["xlsx", "docx"])

    assert inventory["files"] == [
        {
            "path": "docx/a.docx",
            "bytes": 5,
            "sha256": hashlib.sha256(b"alpha").hexdigest(),
        },
        {
            "path": "xlsx/b.xlsx",
            "bytes": 4,
            "sha256": hashlib.sha256(b"beta").hexdigest(),
        },
    ]
    canonical = json.dumps(inventory["files"], sort_keys=True, separators=(",", ":"))
    assert inventory["sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert inventory["total_bytes"] == 9


def test_corpus_inventory_ignores_stale_files_when_current_inputs_are_explicit(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "current.docx").write_bytes(b"current")
    (corpus / "stale.docx").write_bytes(b"stale")

    inventory = script.build_corpus_inventory(
        corpus,
        ["docx"],
        input_files=["current.docx"],
    )

    assert [item["path"] for item in inventory["files"]] == ["current.docx"]
    assert (corpus / "stale.docx").exists()


def test_corpus_inventory_rejects_too_many_files(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.docx").write_bytes(b"a")
    (corpus / "b.docx").write_bytes(b"b")
    (corpus / "c.docx").write_bytes(b"c")

    with pytest.raises(ValueError, match="too many input files"):
        script.build_corpus_inventory(corpus, ["docx"], max_files=2)


def test_corpus_inventory_rejects_too_many_explicit_input_files(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.docx").write_bytes(b"a")
    (corpus / "b.docx").write_bytes(b"b")
    (corpus / "c.docx").write_bytes(b"c")

    with pytest.raises(ValueError, match="too many input files"):
        script.build_corpus_inventory(
            corpus,
            ["docx"],
            max_files=2,
            input_files=["a.docx", "b.docx", "c.docx"],
        )


def test_corpus_inventory_rejects_non_regular_input_file(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    fifo = corpus / "blocked.docx"
    os.mkfifo(fifo)

    start = time.perf_counter()
    try:
        with pytest.raises(ValueError, match="fixture is not a regular file"):
            script.build_corpus_inventory(corpus, ["docx"], input_files=["blocked.docx"], setup_timeout_seconds=0.5)
    finally:
        os.unlink(fifo)

    assert time.perf_counter() - start < 0.5

def test_corpus_inventory_enforces_per_file_and_total_limits(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "large.docx").write_bytes(b"12345")

    with pytest.raises(ValueError, match="per-file limit"):
        script.build_corpus_inventory(corpus, ["docx"], max_file_bytes=4)

    with pytest.raises(ValueError, match="total limit"):
        script.build_corpus_inventory(
            corpus,
            ["docx"],
            max_file_bytes=5,
            max_total_bytes=4,
        )


def test_isolated_benchmark_index_persists_corpus_inventory(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "fixture.docx").write_bytes(b"fixture")
    output_dir = tmp_path / "reports"

    index = script.run_isolated_benchmarks(
        corpus_root=corpus,
        output_dir=output_dir,
        competitors=[],
        python=Path("/usr/bin/python3"),
        formats=["docx"],
        runs=1,
    )

    assert index["corpus_inventory"]["file_count"] == 1
    assert index["corpus_inventory"]["files"][0]["path"] == "fixture.docx"
    assert index["ok"] is False
    assert index["failure_reasons"] == ["no competitors requested"]
    assert json.loads((output_dir / "index.json").read_text(encoding="utf-8")) == index


def test_isolated_benchmark_fails_closed_without_current_fixture_files(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    index = script.run_isolated_benchmarks(
        corpus_root=corpus,
        output_dir=tmp_path / "reports",
        competitors=["markitdown"],
        python=Path("/usr/bin/python3"),
        formats=["docx"],
        runs=1,
        input_files=[],
    )

    assert index["corpus_inventory"]["file_count"] == 0
    assert index["competitors"] == []
    assert index["ok"] is False
    assert "no input files" in index["failure_reasons"]


def test_isolated_benchmark_cli_returns_nonzero_for_empty_competitors(
    tmp_path, monkeypatch, capsys
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "fixture.docx").write_bytes(b"fixture")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_competitor_benchmark.py",
            str(corpus),
            "--output-dir",
            str(tmp_path / "reports"),
            "--competitors",
            "",
        ],
    )

    assert script.main() == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_isolated_benchmark_preserves_resolved_versions_from_failed_run(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "fixture.docx").write_bytes(b"fixture")
    failed_record = {
        "competitor": "markitdown",
        "ok": False,
        "error": "benchmark failed",
        "resolved_packages": {"markitdown": "0.1.7", "pip": "26.2.1"},
    }

    def fail_with_record(*args, **kwargs):
        raise script.CompetitorRunError(failed_record)

    monkeypatch.setattr(script, "run_competitor", fail_with_record)

    index = script.run_isolated_benchmarks(
        corpus_root=corpus,
        output_dir=tmp_path / "reports",
        competitors=["markitdown"],
        python=Path("/usr/bin/python3"),
        formats=["docx"],
        runs=1,
    )

    assert index["competitors"] == [failed_record]
    assert index["ok"] is False
    assert "competitor benchmark failures: 1" in index["failure_reasons"]


def test_venv_python_uses_local_bin_python():
    assert venv_python(Path("/tmp/bench-venv")).as_posix() == "/tmp/bench-venv/bin/python"


def test_make_venv_dir_avoids_corpus_root_when_tmpdir_points_inside_corpus(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    monkeypatch.setenv("TMPDIR", str(corpus))

    venv_dir = make_venv_dir("docling", corpus)
    try:
        assert not venv_dir.resolve().is_relative_to(corpus.resolve())
    finally:
        venv_dir.rmdir()


def test_benchmark_command_runs_worktree_script_with_explicit_converter(tmp_path):
    command = benchmark_command(
        python_executable=Path("/tmp/bench-venv/bin/python"),
        corpus_root=tmp_path / "corpus",
        output_path=tmp_path / "out" / "markitdown.json",
        competitor="markitdown",
        formats=["docx", "pptx", "xlsx"],
        runs=3,
    )

    assert command == [
        "/tmp/bench-venv/bin/python",
        "scripts/benchmark_competitors.py",
        str(tmp_path / "corpus"),
        "--formats",
        "docx,pptx,xlsx",
        "--converters",
        "dochan,markitdown",
        "--runs",
        "3",
        "--timeout",
        "120",
        "--output",
        str(tmp_path / "out" / "markitdown.json"),
    ]


def test_benchmark_command_can_save_converter_outputs(tmp_path):
    command = benchmark_command(
        python_executable=Path("/tmp/bench-venv/bin/python"),
        corpus_root=tmp_path / "corpus",
        output_path=tmp_path / "out" / "docling.json",
        competitor="docling",
        formats=["docx"],
        runs=1,
        output_root=tmp_path / "out" / "outputs" / "docling",
    )

    assert command[-2:] == ["--save-outputs", str(tmp_path / "out" / "outputs" / "docling")]


def test_benchmark_command_passes_only_explicit_current_inputs(tmp_path):
    command = benchmark_command(
        python_executable=Path("/tmp/bench-venv/bin/python"),
        corpus_root=tmp_path / "corpus",
        output_path=tmp_path / "out" / "docling.json",
        competitor="docling",
        formats=["docx"],
        runs=1,
        input_files=["nested/current.docx"],
    )

    assert command[-2:] == ["--input-file", "nested/current.docx"]


def test_benchmark_command_accepts_timeout(tmp_path):
    command = benchmark_command(
        python_executable=Path("/tmp/bench-venv/bin/python"),
        corpus_root=tmp_path / "corpus",
        output_path=tmp_path / "out" / "docling.json",
        competitor="docling",
        formats=["xlsx"],
        runs=1,
        timeout_seconds=3.5,
    )

    assert "--timeout" in command
    assert command[command.index("--timeout") + 1] == "3.5"


def test_run_command_terminates_process_group_on_timeout(tmp_path, monkeypatch):
    command = ["python", "-m", "pip", "install", "package"]
    terminated = []

    class HangingProcess:
        pid = 1234
        returncode = None

        def communicate(self, timeout):
            raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(script.subprocess, "Popen", lambda *args, **kwargs: HangingProcess())
    monkeypatch.setattr(
        script,
        "_terminate_process_group",
        lambda process: terminated.append(process.pid),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        run_command(command, tmp_path, timeout_seconds=2.5)

    assert terminated == [1234]


def test_run_command_terminates_process_group_when_interrupted(tmp_path, monkeypatch):
    command = ["python", "-m", "pip", "install", "package"]
    terminated = []

    class InterruptedProcess:
        pid = 1234
        returncode = None

        def communicate(self, timeout):
            if timeout == 1:
                return None, None
            raise KeyboardInterrupt

    monkeypatch.setattr(
        script.subprocess,
        "Popen",
        lambda *args, **kwargs: InterruptedProcess(),
    )
    monkeypatch.setattr(
        script,
        "_terminate_process_group",
        lambda process: terminated.append(process.pid),
    )

    with pytest.raises(KeyboardInterrupt):
        run_command(command, tmp_path, timeout_seconds=2.5)

    assert terminated == [1234]


def test_terminate_process_group_kills_descendants_after_leader_exits(monkeypatch):
    signals = []

    class ExitedLeader:
        pid = 4321

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(
        script.os,
        "killpg",
        lambda process_group, signal_number: signals.append(
            (process_group, signal_number)
        ),
    )

    script._terminate_process_group(ExitedLeader())

    assert signals == [
        (4321, script.signal.SIGTERM),
        (4321, script.signal.SIGKILL),
    ]


def test_run_competitor_uses_one_absolute_deadline_for_setup_and_benchmark(
    tmp_path, monkeypatch
):
    venv_dir = tmp_path / "venv"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    ticks = iter([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    timeouts = []

    monkeypatch.setattr(script.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(script, "make_venv_dir", lambda competitor, corpus_root: venv_dir)
    monkeypatch.setattr(script, "venv_python", lambda path: path / "bin" / "python")

    def fake_run_command(command, cwd, timeout_seconds):
        timeouts.append(("command", timeout_seconds, command))

    def fake_installed_versions(path, timeout_seconds):
        timeouts.append(("list", timeout_seconds, [str(path), "pip", "list"]))
        return {"docling": "2.119.0"}

    monkeypatch.setattr(script, "run_command", fake_run_command)
    monkeypatch.setattr(script, "installed_package_versions", fake_installed_versions)
    monkeypatch.setattr(script, "summarize_competitor_report", lambda path: {"file_count": 1})
    monkeypatch.setattr(
        script,
        "competitor_report_status",
        lambda path: {
            "ok": True,
            "failure_reasons": [],
            "file_count": 1,
            "converters": ["dochan", "docling"],
            "converter_status": {},
        },
    )
    monkeypatch.setattr(script.shutil, "rmtree", lambda path, ignore_errors: None)

    record = run_competitor(
        competitor="docling",
        corpus_root=tmp_path / "corpus",
        output_dir=output_dir,
        python=Path("/usr/bin/python3"),
        formats=["docx"],
        runs=1,
        setup_timeout_seconds=10.0,
        corpus_file_count=1,
    )

    assert record["ok"] is True
    assert [item[1] for item in timeouts] == [9.0, 8.0, 7.0, 6.0, 5.0]
    assert "scripts/benchmark_competitors.py" in timeouts[-1][2]


def test_run_competitor_deadline_failure_cleans_temporary_venv(tmp_path, monkeypatch):
    venv_dir = tmp_path / "venv"
    venv_dir.mkdir()
    removed = []
    ticks = iter([10.0, 12.0])
    monkeypatch.setattr(script.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(script, "make_venv_dir", lambda competitor, corpus_root: venv_dir)
    monkeypatch.setattr(
        script.shutil,
        "rmtree",
        lambda path, ignore_errors: removed.append((path, ignore_errors)),
    )

    with pytest.raises(script.CompetitorRunError) as exc_info:
        run_competitor(
            competitor="docling",
            corpus_root=tmp_path / "corpus",
            output_dir=tmp_path / "out",
            python=Path("/usr/bin/python3"),
            formats=["docx"],
            runs=1,
            setup_timeout_seconds=1.0,
        )

    assert "TimeoutExpired" in exc_info.value.record["error"]
    assert removed == [(venv_dir, True)]


@pytest.mark.parametrize(
    ("option", "value"),
    [("--timeout", "0"), ("--timeout", "-1"), ("--setup-timeout", "0")],
)
def test_isolated_benchmark_cli_rejects_nonpositive_timeouts(
    tmp_path, monkeypatch, option, value
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_isolated_competitor_benchmark.py",
            str(corpus),
            "--output-dir",
            str(tmp_path / "out"),
            option,
            value,
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        script.main()

    assert exc_info.value.code == 2


def test_summarize_competitor_report_extracts_index_fields(tmp_path):
    report_path = tmp_path / "markitdown.json"
    report_path.write_text(
        """{
          "file_count": 3,
          "converters": ["dochan", "markitdown"],
          "format_summary": [{"format": "docx", "median_json_run_provenance_count": 59}],
          "competitive_summary": [{"format": "docx", "speedup_vs_competitor": 2.0}],
          "improvement_candidates": [{"format": "xlsx", "worst_gap_score": 0.5}],
          "file_improvement_candidates": [{"file": "xlsx/book.xlsx", "format": "xlsx", "worst_gap_score": 0.2}]
        }""",
        encoding="utf-8",
    )

    summary = summarize_competitor_report(report_path)

    assert summary == {
        "file_count": 3,
        "converters": ["dochan", "markitdown"],
        "format_summary": [{"format": "docx", "median_json_run_provenance_count": 59}],
        "competitive_summary": [{"format": "docx", "speedup_vs_competitor": 2.0}],
        "improvement_candidates": [{"format": "xlsx", "worst_gap_score": 0.5}],
        "file_improvement_candidates": [{"file": "xlsx/book.xlsx", "format": "xlsx", "worst_gap_score": 0.2}],
    }


def test_run_competitor_retries_failed_benchmark_command_once(tmp_path, monkeypatch):
    venv_dir = tmp_path / "venv"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    commands = []
    benchmark_failures = [subprocess.CalledProcessError(-11, ["python", "scripts/benchmark_competitors.py"])]

    monkeypatch.setattr(script, "make_venv_dir", lambda competitor, corpus_root: venv_dir)
    monkeypatch.setattr(script, "venv_python", lambda path: path / "bin" / "python")
    monkeypatch.setattr(script, "summarize_competitor_report", lambda path: {"file_count": 1})
    monkeypatch.setattr(
        script,
        "competitor_report_status",
        lambda path: {
            "ok": True,
            "failure_reasons": [],
            "file_count": 1,
            "converters": ["dochan", "docling"],
            "converter_status": {},
        },
    )
    monkeypatch.setattr(
        script,
        "installed_package_versions",
        lambda path, timeout_seconds: {"docling": "2.119.0", "pip": "26.2.1"},
    )
    monkeypatch.setattr(script.shutil, "rmtree", lambda path, ignore_errors: None)

    def fake_run_command(command, cwd, timeout_seconds):
        commands.append(command)
        if "scripts/benchmark_competitors.py" in command and benchmark_failures:
            raise benchmark_failures.pop()

    monkeypatch.setattr(script, "run_command", fake_run_command)

    record = run_competitor(
        competitor="docling",
        corpus_root=tmp_path / "corpus",
        output_dir=output_dir,
        python=Path("/usr/bin/python3"),
        formats=["xlsx"],
        runs=1,
        retry_failed_runs=1,
        corpus_sha256="corpus-digest",
    )

    benchmark_commands = [command for command in commands if "scripts/benchmark_competitors.py" in command]
    assert len(benchmark_commands) == 2
    assert record["ok"] is True
    assert record["attempts"] == 2
    assert "CalledProcessError" in record["errors"][0]
    assert record["report_summary"] == {"file_count": 1}
    assert record["resolved_packages"] == {"docling": "2.119.0", "pip": "26.2.1"}
    assert record["corpus_sha256"] == "corpus-digest"
    assert [
        str(venv_dir / "bin" / "python"),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "pip==26.2.1",
    ] in commands


def test_run_competitor_rejects_benchmark_report_that_failed_closed(tmp_path, monkeypatch):
    venv_dir = tmp_path / "venv"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setattr(script, "make_venv_dir", lambda competitor, corpus_root: venv_dir)
    monkeypatch.setattr(script, "venv_python", lambda path: path / "bin" / "python")
    monkeypatch.setattr(
        script,
        "run_command",
        lambda command, cwd, timeout_seconds: None,
    )
    monkeypatch.setattr(
        script,
        "installed_package_versions",
        lambda path, timeout_seconds: {},
    )
    monkeypatch.setattr(
        script,
        "summarize_competitor_report",
        lambda path: {"file_count": 1, "converters": ["dochan"]},
    )
    monkeypatch.setattr(
        script,
        "competitor_report_status",
        lambda path: {
            "ok": False,
            "file_count": 1,
            "converters": ["dochan"],
            "failure_reasons": ["converter unavailable: markitdown"],
            "converter_status": {},
        },
    )

    with pytest.raises(script.CompetitorRunError) as exc_info:
        run_competitor(
            competitor="markitdown",
            corpus_root=tmp_path / "corpus",
            output_dir=output_dir,
            python=Path("/usr/bin/python3"),
            formats=["docx"],
            runs=1,
            corpus_file_count=1,
        )

    assert exc_info.value.record["ok"] is False
    assert exc_info.value.record["report_status"]["ok"] is False
