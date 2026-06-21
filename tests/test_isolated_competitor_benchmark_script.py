import subprocess
from pathlib import Path

from scripts import run_isolated_competitor_benchmark as script
from scripts.run_isolated_competitor_benchmark import (
    benchmark_command,
    competitor_install_packages,
    make_venv_dir,
    parse_competitors,
    run_competitor,
    summarize_competitor_report,
    venv_python,
)


def test_parse_competitors_normalizes_and_filters_supported_names():
    assert parse_competitors(" markitdown,docling,MARKITDOWN ") == ["markitdown", "docling"]


def test_competitor_install_packages_are_pinned_to_converter_extras():
    assert competitor_install_packages("markitdown") == ["markitdown[docx,pptx,xlsx]"]
    assert competitor_install_packages("docling") == ["docling"]


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
    monkeypatch.setattr(script.shutil, "rmtree", lambda path, ignore_errors: None)

    def fake_run_command(command, cwd):
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
    )

    benchmark_commands = [command for command in commands if "scripts/benchmark_competitors.py" in command]
    assert len(benchmark_commands) == 2
    assert record["ok"] is True
    assert record["attempts"] == 2
    assert "CalledProcessError" in record["errors"][0]
    assert record["report_summary"] == {"file_count": 1}
