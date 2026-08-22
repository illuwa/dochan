import json
import sys
from pathlib import Path

import pytest

from scripts.run_fixture_probe import run_fixture_probe


def test_run_fixture_probe_uses_fixture_index_and_records_invalid_zip(tmp_path, monkeypatch):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "probe"
    fixture_index.write_text(json.dumps({"fixtures": [{"name": "a.docx", "format": "docx"}]}), encoding="utf-8")
    calls = []

    def fake_download_corpus(output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format):
        calls.append(("download", tuple(formats), fixtures, Path(probe_manifest_path).name, probe_name, probe_per_format))
        path = output_dir / "docx"
        path.mkdir(parents=True)
        (path / "a.docx").write_bytes(b"not-a-zip")
        return [{"path": "docx/a.docx", "format": "docx", "name": "a.docx"}]

    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)

    report = run_fixture_probe(
        output_dir=output_dir,
        fixture_index=fixture_index,
        probe_name="generic-probe",
        manifest_path=manifest_path,
        formats=["docx"],
        per_format=1,
        competitors=[],
    )

    assert calls == [(
        "download",
        ("docx",),
        [{"name": "a.docx", "format": "docx"}],
        "manifest.json",
        "generic-probe",
        1,
    )]
    assert report["files"] == []
    assert report["zip_invalid"][0]["path"] == "docx/a.docx"
    assert report["ok"] is False
    assert report["failure_reasons"] == ["invalid OOXML archives: 1", "no valid fixture files"]
    assert json.loads((output_dir / "probe.json").read_text(encoding="utf-8"))["probe_name"] == "generic-probe"


def test_run_fixture_probe_fails_closed_if_downloaded_fixture_is_mutated(tmp_path, monkeypatch):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "probe"
    fixture_index.write_text(
        json.dumps({"fixtures": [{"name": "a.docx", "format": "docx"}]}),
        encoding="utf-8",
    )

    expected_bytes = 11
    expected_sha256 = "0" * 64
    def fake_download_corpus(output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format):
        path = output_dir / "docx"
        path.mkdir(parents=True)
        with open(path / "a.docx", "wb") as writer:
            writer.write(b"original data")
        return [{
            "path": "docx/a.docx",
            "format": "docx",
            "name": "a.docx",
            "bytes": expected_bytes,
            "sha256": expected_sha256,
        }]

    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)
    monkeypatch.setattr(script, "validate_zip_files", lambda corpus_dir, records: [])
    monkeypatch.setattr(script, "run_benchmark", lambda *args, **kwargs: {
        "ok": True,
        "file_count": 1,
        "format_summary": [],
        "results": [{"file": "docx/a.docx", "nonempty": True, "error": ""}],
    })
    monkeypatch.setattr(
        script,
        "run_isolated_benchmarks",
        lambda *args, **kwargs: {
            "ok": True,
            "competitors": [{"competitor": "markitdown", "ok": True, "report_summary": {}}],
        },
    )
    (output_dir / "docx").mkdir(parents=True)
    (output_dir / "docx" / "a.docx").write_bytes(b"tampered")

    report = run_fixture_probe(
        output_dir=output_dir,
        fixture_index=fixture_index,
        probe_name="generic-probe",
        manifest_path=manifest_path,
        formats=["docx"],
        per_format=1,
        competitors=["markitdown"],
    )

    assert report["files"] == []
    assert report["ok"] is False
    assert report["zip_invalid"]  # fail-closed evidence should be captured
    assert report["failure_reasons"] == ["invalid OOXML archives: 1", "no valid fixture files"]
    assert report["zip_invalid"][0]["error"].startswith("fixture size changed after download:")


def test_run_fixture_probe_runs_dochan_and_isolated_competitors_for_valid_records(tmp_path, monkeypatch):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps({"fixtures": [{"name": "a.xlsx", "format": "xlsx"}]}), encoding="utf-8")

    output_dir = tmp_path / "probe"
    stale = output_dir / "corpus" / "xlsx" / "stale.xlsx"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")

    def fake_download_corpus(output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format):
        path = output_dir / "xlsx"
        path.mkdir(parents=True, exist_ok=True)
        (path / "a.xlsx").write_bytes(b"placeholder")
        return [{"path": "xlsx/a.xlsx", "format": "xlsx", "name": "a.xlsx"}]

    def fake_validate_zip_files(corpus_dir, records):
        return []

    def fake_run_benchmark(
        corpus_dir,
        formats,
        runs,
        converter_names,
        output_root,
        timeout_seconds,
        input_files,
    ):
        assert timeout_seconds == 120.0
        assert input_files == ["xlsx/a.xlsx"]
        return {
            "ok": True,
            "file_count": 1,
            "format_summary": [{"converter": "dochan", "format": "xlsx", "success_rate": 1.0}],
            "results": [{"file": "xlsx/a.xlsx", "nonempty": True, "error": ""}],
        }

    def fake_run_isolated_benchmarks(
        corpus_root,
        output_dir,
        competitors,
        python,
        formats,
        runs,
        keep_venv,
        keep_going,
        timeout_seconds,
        setup_timeout_seconds,
        retry_failed_runs,
        input_files,
    ):
        assert retry_failed_runs == 1
        assert timeout_seconds == 120.0
        assert setup_timeout_seconds == 900.0
        assert input_files == ["xlsx/a.xlsx"]
        return {
            "ok": True,
            "competitors": [{
                "competitor": "markitdown",
                "ok": True,
                "report_summary": {"file_improvement_candidates": []},
            }]
        }

    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)
    monkeypatch.setattr(script, "validate_zip_files", fake_validate_zip_files)
    monkeypatch.setattr(script, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(script, "run_isolated_benchmarks", fake_run_isolated_benchmarks)

    report = run_fixture_probe(
        output_dir=output_dir,
        fixture_index=fixture_index,
        probe_name="generic-probe",
        manifest_path=tmp_path / "manifest.json",
        formats=["xlsx"],
        per_format=1,
        competitors=["markitdown"],
    )

    assert report["files"] == ["xlsx/a.xlsx"]
    assert report["dochan"]["error_count"] == 0
    assert report["isolated"]["competitors"][0]["ok"] is True
    assert report["ok"] is True
    assert stale.exists()


def test_run_fixture_probe_gates_failed_isolated_record_even_if_index_claims_ok(tmp_path, monkeypatch):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(
        json.dumps({"fixtures": [{"name": "a.docx", "format": "docx"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        script,
        "download_corpus",
        lambda output_dir, *args, **kwargs: [
            {"path": "a.docx", "format": "docx", "name": "a.docx"}
        ],
    )
    monkeypatch.setattr(script, "validate_zip_files", lambda corpus_dir, records: [])
    monkeypatch.setattr(
        script,
        "run_benchmark",
        lambda *args, **kwargs: {
            "ok": True,
            "file_count": 1,
            "format_summary": [],
            "results": [{"file": "a.docx", "nonempty": True, "error": ""}],
        },
    )
    monkeypatch.setattr(
        script,
        "run_isolated_benchmarks",
        lambda *args, **kwargs: {
            "ok": True,
            "competitors": [{"competitor": "markitdown", "ok": False}],
        },
    )

    report = run_fixture_probe(
        output_dir=tmp_path / "probe",
        fixture_index=fixture_index,
        probe_name="failed-record",
        manifest_path=tmp_path / "manifest.json",
        formats=["docx"],
        per_format=1,
        competitors=["markitdown"],
    )

    assert report["ok"] is False
    assert "isolated benchmark failed" in report["failure_reasons"]


def test_fixture_probe_cli_returns_nonzero_when_no_valid_fixtures(
    tmp_path, monkeypatch, capsys
):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps({"fixtures": []}), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_fixture_probe.py",
            str(tmp_path / "probe"),
            "--fixture-index",
            str(fixture_index),
            "--probe-name",
            "empty",
            "--probe-manifest",
            str(tmp_path / "manifest.json"),
            "--probe-per-format",
            "1",
        ],
    )

    assert script.main() == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_run_fixture_probe_fails_closed_when_competitors_are_empty(tmp_path, monkeypatch):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(
        json.dumps({"fixtures": [{"name": "a.docx", "format": "docx"}]}),
        encoding="utf-8",
    )

    def fake_download_corpus(output_dir, *args, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "a.docx").write_text("placeholder", encoding="utf-8")
        return [{"path": "a.docx", "format": "docx", "name": "a.docx"}]

    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)
    monkeypatch.setattr(script, "validate_zip_files", lambda corpus_dir, records: [])
    monkeypatch.setattr(
        script,
        "run_benchmark",
        lambda *args, **kwargs: {
            "ok": True,
            "file_count": 1,
            "format_summary": [],
            "results": [{"file": "a.docx", "nonempty": True, "error": ""}],
        },
    )

    report = run_fixture_probe(
        output_dir=tmp_path / "probe",
        fixture_index=fixture_index,
        probe_name="empty-competitors",
        manifest_path=tmp_path / "manifest.json",
        formats=["docx"],
        per_format=1,
        competitors=[],
    )

    assert report["isolated"]["ok"] is False
    assert report["ok"] is False
    assert "isolated benchmark failed" in report["failure_reasons"]


def test_fixture_probe_cli_forwards_conversion_and_setup_timeouts(
    tmp_path, monkeypatch, capsys
):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text('{"fixtures": []}', encoding="utf-8")
    captured = {}

    def fake_probe(**kwargs):
        captured.update(kwargs)
        return {"ok": False, "failure_reasons": ["synthetic"]}

    monkeypatch.setattr(script, "run_fixture_probe", fake_probe)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_fixture_probe.py",
            str(tmp_path / "probe"),
            "--fixture-index",
            str(fixture_index),
            "--probe-name",
            "timeouts",
            "--probe-manifest",
            str(tmp_path / "manifest.json"),
            "--timeout",
            "3.5",
            "--setup-timeout",
            "30",
        ],
    )

    assert script.main() == 1
    assert captured["timeout_seconds"] == 3.5
    assert captured["setup_timeout_seconds"] == 30.0
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize(
    ("option", "value"),
    [("--timeout", "0"), ("--setup-timeout", "-1")],
)
def test_fixture_probe_cli_rejects_nonpositive_timeouts(
    tmp_path,
    monkeypatch,
    option,
    value,
):
    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text('{"fixtures": []}', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_fixture_probe.py",
            str(tmp_path / "probe"),
            "--fixture-index",
            str(fixture_index),
            "--probe-name",
            "timeouts",
            "--probe-manifest",
            str(tmp_path / "manifest.json"),
            option,
            value,
        ],
    )

    from scripts import run_fixture_probe as script

    with pytest.raises(SystemExit) as exc_info:
        script.main()

    assert exc_info.value.code == 2
