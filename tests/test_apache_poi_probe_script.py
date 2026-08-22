import json
import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

from dochan.ooxml import package as ooxml_package
from scripts.run_apache_poi_probe import (
    parse_formats,
    remove_invalid_zip_files,
    run_apache_poi_probe,
    summarize_dochan_only,
    validate_zip_files,
)


def test_parse_formats_normalizes_extensions():
    assert parse_formats(" .DOCX, pptx,xlsx ") == ["docx", "pptx", "xlsx"]


def test_validate_zip_files_reports_corrupt_archives(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    valid = corpus / "valid.docx"
    invalid = corpus / "invalid.docx"
    with zipfile.ZipFile(valid, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    invalid.write_text("not a zip", encoding="utf-8")

    problems = validate_zip_files(corpus, [{"path": "valid.docx"}, {"path": "invalid.docx"}])

    assert problems == [{"path": "invalid.docx", "error": "BadZipFile('File is not a zip file')"}]


def test_validate_zip_files_rejects_parts_over_the_parser_budget(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    oversized = corpus / "oversized.docx"
    with zipfile.ZipFile(oversized, "w") as archive:
        archive.writestr("word/document.xml", b"12345")
    monkeypatch.setattr(ooxml_package, "MAX_PART_SIZE", 4)

    problems = validate_zip_files(corpus, [{"path": "oversized.docx"}])

    assert problems[0]["path"] == "oversized.docx"
    assert "part too large" in problems[0]["error"]


def test_validate_zip_files_rejects_xml_and_compression_ratio_limits(
    tmp_path, monkeypatch
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    xml_limited = corpus / "xml-limited.docx"
    ratio_limited = corpus / "ratio-limited.docx"
    with zipfile.ZipFile(xml_limited, "w") as archive:
        archive.writestr("word/document.xml", b"12345")
    with zipfile.ZipFile(
        ratio_limited,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("word/media/image.bin", b"x" * 1024)
    monkeypatch.setattr(ooxml_package, "MAX_XML_PART_SIZE", 4)
    monkeypatch.setattr(ooxml_package, "MAX_COMPRESSION_RATIO", 1)

    problems = validate_zip_files(
        corpus,
        [{"path": "xml-limited.docx"}, {"path": "ratio-limited.docx"}],
    )

    assert [item["path"] for item in problems] == [
        "xml-limited.docx",
        "ratio-limited.docx",
    ]
    assert "XML part too large" in problems[0]["error"]
    assert "compression ratio too high" in problems[1]["error"]


def test_remove_invalid_zip_files_unlinks_only_invalid_paths(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    valid = corpus / "valid.docx"
    invalid = corpus / "invalid.docx"
    valid.write_text("valid", encoding="utf-8")
    invalid.write_text("invalid", encoding="utf-8")

    remove_invalid_zip_files(corpus, [{"path": "invalid.docx"}, {"path": "missing.docx"}])

    assert valid.exists()
    assert not invalid.exists()


def test_summarize_dochan_only_separates_errors_empty_and_semantic_empty():
    summary = summarize_dochan_only({
        "file_count": 3,
        "format_summary": [{"format": "docx"}],
        "results": [
            {"file": "bad.docx", "error": "boom", "nonempty": False},
            {"file": "empty.docx", "error": "", "nonempty": False, "input_semantic_empty": False},
            {"file": "semantic-empty.xlsx", "error": "", "nonempty": False, "input_semantic_empty": True},
        ],
    })

    assert summary["error_count"] == 1
    assert summary["unexpected_empty"] == ["empty.docx"]
    assert summary["semantic_empty"] == ["semantic-empty.xlsx"]


def test_run_apache_poi_probe_orchestrates_without_network_or_venv(tmp_path, monkeypatch):
    from scripts import run_apache_poi_probe as script

    calls = []

    def fake_build_index(formats):
        calls.append(("build_index", tuple(formats)))
        return {
            "fixtures": [
                {"name": "a.docx", "format": "docx", "source_name": "a.docx", "url": "https://example.test/a.docx"},
            ],
            "counts": {"docx": 1},
        }

    def fake_download_corpus(output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format):
        calls.append(("download", tuple(formats), probe_name, probe_per_format, Path(probe_manifest_path).name))
        output_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_dir / "a.docx", "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        return [{"path": "a.docx", "format": "docx", "source_name": "a.docx"}]

    def fake_run_benchmark(
        root,
        formats,
        runs,
        converter_names,
        output_root,
        timeout_seconds,
        input_files,
    ):
        calls.append(("dochan", tuple(formats), runs, tuple(converter_names), output_root.name))
        assert timeout_seconds == 120.0
        assert input_files == ["a.docx"]
        return {
            "ok": True,
            "file_count": 1,
            "format_summary": [{"converter": "dochan", "format": "docx", "success_rate": 1.0}],
            "results": [{"file": str(root / "a.docx"), "error": "", "nonempty": True}],
        }

    def fake_isolated(
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
        calls.append(("isolated", tuple(competitors), tuple(formats), runs, keep_venv, keep_going))
        assert timeout_seconds == 120.0
        assert setup_timeout_seconds == 900.0
        assert retry_failed_runs == 0
        assert input_files == ["a.docx"]
        return {
            "ok": True,
            "corpus": str(corpus_root),
            "output_dir": str(output_dir),
            "competitors": [
                {"competitor": "markitdown", "ok": True, "report_summary": {"improvement_candidates": []}},
            ],
        }

    monkeypatch.setattr(script, "build_apache_poi_fixture_index", fake_build_index)
    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)
    monkeypatch.setattr(script, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(script, "run_isolated_benchmarks", fake_isolated)

    report = run_apache_poi_probe(
        output_dir=tmp_path / "probe",
        probe_name="apache-poi-test",
        manifest_path=tmp_path / "manifest.json",
        formats=["docx"],
        per_format=1,
        competitors=["markitdown"],
        python=Path("/usr/bin/python3"),
        runs=2,
    )

    assert calls == [
        ("build_index", ("docx",)),
        ("download", ("docx",), "apache-poi-test", 1, "manifest.json"),
        ("dochan", ("docx",), 1, ("dochan",), "dochan"),
        ("isolated", ("markitdown",), ("docx",), 2, False, False),
    ]
    assert report["downloaded"] == 1
    assert report["zip_invalid"] == []
    assert report["dochan"]["error_count"] == 0
    assert report["ok"] is True
    assert (tmp_path / "probe" / "probe.json").exists()
    assert json.loads((tmp_path / "probe" / "probe.json").read_text(encoding="utf-8"))["probe_name"] == "apache-poi-test"


def test_run_apache_poi_probe_skips_invalid_zip_fixtures_and_continues(tmp_path, monkeypatch):
    from scripts import run_apache_poi_probe as script

    calls = []

    def fake_build_index(formats):
        return {
            "fixtures": [
                {"name": "valid.docx", "format": "docx", "source_name": "valid.docx", "url": "https://example.test/valid.docx"},
                {"name": "corrupt.docx", "format": "docx", "source_name": "corrupt.docx", "url": "https://example.test/corrupt.docx"},
            ],
            "counts": {"docx": 2},
        }

    def fake_download_corpus(output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format):
        output_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_dir / "valid.docx", "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        (output_dir / "corrupt.docx").write_text("not a zip", encoding="utf-8")
        return [
            {"path": "valid.docx", "format": "docx", "source_name": "valid.docx"},
            {"path": "corrupt.docx", "format": "docx", "source_name": "corrupt.docx"},
        ]

    def fake_run_benchmark(
        root,
        formats,
        runs,
        converter_names,
        output_root,
        timeout_seconds,
        input_files,
    ):
        calls.append(("dochan", sorted(path.name for path in root.glob("*.docx"))))
        assert timeout_seconds == 120.0
        assert input_files == ["valid.docx"]
        return {
            "ok": True,
            "file_count": 1,
            "format_summary": [{"converter": "dochan", "format": "docx", "success_rate": 1.0}],
            "results": [{"file": str(root / "valid.docx"), "error": "", "nonempty": True}],
        }

    def fake_isolated(
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
        calls.append(("isolated", sorted(path.name for path in corpus_root.glob("*.docx"))))
        assert input_files == ["valid.docx"]
        return {
            "ok": True,
            "corpus": str(corpus_root),
            "output_dir": str(output_dir),
            "competitors": [
                {"competitor": "markitdown", "ok": True, "report_summary": {"improvement_candidates": []}},
            ],
        }

    monkeypatch.setattr(script, "build_apache_poi_fixture_index", fake_build_index)
    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)
    monkeypatch.setattr(script, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(script, "run_isolated_benchmarks", fake_isolated)

    report = run_apache_poi_probe(
        output_dir=tmp_path / "probe",
        probe_name="apache-poi-test",
        manifest_path=tmp_path / "manifest.json",
        formats=["docx"],
        per_format=2,
        competitors=["markitdown"],
        python=Path("/usr/bin/python3"),
        runs=1,
    )

    assert calls == [
        ("dochan", ["valid.docx"]),
        ("isolated", ["valid.docx"]),
    ]
    assert report["downloaded"] == 2
    assert report["files"] == ["valid.docx"]
    assert report["zip_invalid"] == [{"path": "corrupt.docx", "error": "BadZipFile('File is not a zip file')"}]
    assert report["ok"] is False
    assert report["failure_reasons"][0] == "invalid OOXML archives: 1"
    assert not (tmp_path / "probe" / "corpus" / "corrupt.docx").exists()


def test_probe_records_manifest_only_after_a_completed_outcome(tmp_path, monkeypatch):
    from scripts import run_apache_poi_probe as script

    records = [
            {
                "path": "valid.docx",
                "name": "valid.docx",
                "format": "docx",
                "source": "apache/poi",
                "source_name": "valid.docx",
                "source_revision": "1" * 40,
                "sha256": hashlib.sha256(b"valid").hexdigest(),
                "bytes": 5,
            }
        ]
    calls = []
    monkeypatch.setattr(script, "build_apache_poi_fixture_index", lambda formats: {"fixtures": records})
    def fake_download_corpus(
        output_dir, formats, fixtures, probe_manifest_path, probe_name, probe_per_format
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        content = b"valid"
        path = output_dir / "valid.docx"
        path.write_bytes(content)
        return [
            {
                "path": "valid.docx",
                "name": "valid.docx",
                "format": "docx",
                "source": "apache/poi",
                "source_name": "valid.docx",
                "source_revision": "1" * 40,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ]
    monkeypatch.setattr(script, "download_corpus", fake_download_corpus)
    monkeypatch.setattr(script, "validate_zip_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        script,
        "run_benchmark",
        lambda *args, **kwargs: {
            "ok": True,
            "file_count": 1,
            "format_summary": [],
            "results": [{"file": "valid.docx", "nonempty": True, "error": ""}],
        },
    )
    monkeypatch.setattr(
        script,
        "run_isolated_benchmarks",
        lambda *args, **kwargs: {"ok": True, "competitors": [{"ok": True}]},
    )
    monkeypatch.setattr(
        script,
        "record_probe_outcome",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    report = run_apache_poi_probe(
        output_dir=tmp_path / "probe",
        probe_name="complete",
        manifest_path=tmp_path / "manifest.json",
        formats=["docx"],
        per_format=1,
        competitors=["markitdown"],
    )

    assert report["ok"] is True
    assert len(calls) == 1
    assert calls[0][1]["successful_records"] == records
    assert json.loads((tmp_path / "probe" / "probe.json").read_text(encoding="utf-8"))["ok"] is True


def test_summarize_dochan_only_fails_closed_for_errors_and_unexpected_empty():
    summary = summarize_dochan_only({
        "ok": False,
        "file_count": 2,
        "format_summary": [],
        "results": [
            {"file": "bad.docx", "error": "boom", "nonempty": False},
            {"file": "empty.docx", "error": "", "nonempty": False, "input_semantic_empty": False},
        ],
    })

    assert summary["ok"] is False
    assert summary["error_count"] == 1
    assert summary["unexpected_empty_count"] == 1


def test_apache_poi_probe_cli_returns_nonzero_for_failed_report(
    tmp_path, monkeypatch, capsys
):
    from scripts import run_apache_poi_probe as script

    monkeypatch.setattr(
        script,
        "run_apache_poi_probe",
        lambda **kwargs: {"ok": False, "failure_reasons": ["no valid fixture files"]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_apache_poi_probe.py",
            str(tmp_path / "probe"),
            "--probe-name",
            "empty",
            "--probe-manifest",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert script.main() == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_apache_poi_probe_cli_forwards_conversion_and_setup_timeouts(
    tmp_path, monkeypatch, capsys
):
    from scripts import run_apache_poi_probe as script

    captured = {}

    def fake_probe(**kwargs):
        captured.update(kwargs)
        return {"ok": False, "failure_reasons": ["synthetic"]}

    monkeypatch.setattr(script, "run_apache_poi_probe", fake_probe)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_apache_poi_probe.py",
            str(tmp_path / "probe"),
            "--probe-name",
            "timeouts",
            "--probe-manifest",
            str(tmp_path / "manifest.json"),
            "--timeout",
            "4.5",
            "--setup-timeout",
            "45",
            "--retry-failed-runs",
            "2",
        ],
    )

    assert script.main() == 1
    assert captured["timeout_seconds"] == 4.5
    assert captured["setup_timeout_seconds"] == 45.0
    assert captured["retry_failed_runs"] == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize(
    ("option", "value"),
    [("--timeout", "0"), ("--setup-timeout", "-1")],
)
def test_apache_poi_probe_cli_rejects_nonpositive_timeouts(
    tmp_path,
    monkeypatch,
    option,
    value,
):
    from scripts import run_apache_poi_probe as script

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_apache_poi_probe.py",
            str(tmp_path / "probe"),
            "--probe-name",
            "timeouts",
            "--probe-manifest",
            str(tmp_path / "manifest.json"),
            option,
            value,
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        script.main()

    assert exc_info.value.code == 2
