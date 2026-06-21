import json
from pathlib import Path

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
    assert json.loads((output_dir / "probe.json").read_text(encoding="utf-8"))["probe_name"] == "generic-probe"


def test_run_fixture_probe_runs_dochan_and_isolated_competitors_for_valid_records(tmp_path, monkeypatch):
    from scripts import run_fixture_probe as script

    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps({"fixtures": [{"name": "a.xlsx", "format": "xlsx"}]}), encoding="utf-8")

    def fake_download_corpus(output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format):
        path = output_dir / "xlsx"
        path.mkdir(parents=True)
        (path / "a.xlsx").write_bytes(b"placeholder")
        return [{"path": "xlsx/a.xlsx", "format": "xlsx", "name": "a.xlsx"}]

    def fake_validate_zip_files(corpus_dir, records):
        return []

    def fake_run_benchmark(corpus_dir, formats, runs, converter_names, output_root):
        return {
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
        retry_failed_runs,
    ):
        assert retry_failed_runs == 1
        return {
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
        output_dir=tmp_path / "probe",
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
