import json
import zipfile
from pathlib import Path

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

    def fake_run_benchmark(root, formats, runs, converter_names, output_root):
        calls.append(("dochan", tuple(formats), runs, tuple(converter_names), output_root.name))
        return {
            "file_count": 1,
            "format_summary": [{"converter": "dochan", "format": "docx", "success_rate": 1.0}],
            "results": [{"file": str(root / "a.docx"), "error": "", "nonempty": True}],
        }

    def fake_isolated(corpus_root, output_dir, competitors, python, formats, runs, keep_venv, keep_going):
        calls.append(("isolated", tuple(competitors), tuple(formats), runs, keep_venv, keep_going))
        return {
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

    def fake_run_benchmark(root, formats, runs, converter_names, output_root):
        calls.append(("dochan", sorted(path.name for path in root.glob("*.docx"))))
        return {
            "file_count": 1,
            "format_summary": [{"converter": "dochan", "format": "docx", "success_rate": 1.0}],
            "results": [{"file": str(root / "valid.docx"), "error": "", "nonempty": True}],
        }

    def fake_isolated(corpus_root, output_dir, competitors, python, formats, runs, keep_venv, keep_going):
        calls.append(("isolated", sorted(path.name for path in corpus_root.glob("*.docx"))))
        return {
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
    assert not (tmp_path / "probe" / "corpus" / "corrupt.docx").exists()
