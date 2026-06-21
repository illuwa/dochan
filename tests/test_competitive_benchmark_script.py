import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from scripts.benchmark_competitors import (
    compare_against_dochan,
    compare_files_against_dochan,
    discover_converters,
    find_file_improvement_candidates,
    find_improvement_candidates,
    inspect_converter_availability,
    input_has_ooxml_semantic_signal,
    iter_input_files,
    load_expectations,
    output_capture_path,
    profile_output,
    summarize_results,
    summarize_by_format,
    run_benchmark,
    score_output,
)
from scripts.generate_ooxml_benchmark_corpus import generate_corpus


def test_iter_input_files_filters_supported_office_formats(tmp_path):
    for name in ["a.docx", "b.pptx", "c.xlsx", "d.hwp", "e.pdf", "f.txt"]:
        (tmp_path / name).write_text("x", encoding="utf-8")

    files = [path.name for path in iter_input_files(tmp_path, formats=["docx", "pptx", "xlsx"])]

    assert files == ["a.docx", "b.pptx", "c.xlsx"]


def test_discover_converters_always_includes_dochan():
    converters = discover_converters()

    assert "dochan" in converters
    assert callable(converters["dochan"])


def test_inspect_converter_availability_reports_requested_missing_converters():
    status = inspect_converter_availability(["dochan", "missing_converter"])

    assert status["dochan"]["available"] is True
    assert status["dochan"]["error"] == ""
    assert status["missing_converter"]["available"] is False
    assert "Unknown converter" in status["missing_converter"]["error"]


def test_run_benchmark_reports_requested_missing_converter_status(tmp_path):
    generate_corpus(tmp_path)

    report = run_benchmark(tmp_path, formats=["docx"], runs=1, converter_names=["dochan", "missing_converter"])

    assert report["converters"] == ["dochan"]
    assert report["requested_converters"] == ["dochan", "missing_converter"]
    assert report["converter_status"]["dochan"]["available"] is True
    assert report["converter_status"]["missing_converter"]["available"] is False
    assert len(report["results"]) == 1


def test_output_capture_path_preserves_relative_input_structure(tmp_path):
    path = output_capture_path(
        output_root=tmp_path / "outputs",
        converter="dochan",
        relative_input=Path("nested/report.docx"),
        run_index=2,
    )

    assert path == tmp_path / "outputs" / "dochan" / "nested" / "report.docx.run2.md"


def test_run_benchmark_can_save_converter_outputs(tmp_path):
    generate_corpus(tmp_path)
    output_root = tmp_path / "outputs"

    report = run_benchmark(
        tmp_path,
        formats=["docx"],
        runs=1,
        converter_names=["dochan"],
        output_root=output_root,
    )
    row = report["results"][0]

    assert row["output_path"] == str(output_root / "dochan" / "sample.docx.run1.md")
    assert (output_root / "dochan" / "sample.docx.run1.md").read_text(encoding="utf-8")
    assert report["output_root"] == str(output_root)


def test_run_benchmark_records_converter_timeout(tmp_path, monkeypatch):
    generate_corpus(tmp_path)

    def slow_converter(_path):
        time.sleep(1)
        return "late"

    monkeypatch.setattr(
        "scripts.benchmark_competitors.inspect_converter_availability",
        lambda _names: {"slow": {"available": True, "error": ""}},
    )
    monkeypatch.setattr(
        "scripts.benchmark_competitors.discover_converters",
        lambda _names: {"slow": slow_converter},
    )

    report = run_benchmark(
        tmp_path,
        formats=["docx"],
        runs=1,
        converter_names=["slow"],
        timeout_seconds=0.01,
    )

    assert report["timeout_seconds"] == 0.01
    assert report["results"][0]["nonempty"] is False
    assert "TimeoutError" in report["results"][0]["error"]


def test_load_expectations_reads_manifest_by_relative_file(tmp_path):
    manifest = tmp_path / "expected.json"
    manifest.write_text(json.dumps({
        "docs/sample.docx": {
            "expected_text": ["Title", "Body"],
            "expected_tables": [[["A", "B"]]],
        }
    }), encoding="utf-8")

    expectations = load_expectations(tmp_path)

    assert expectations["docs/sample.docx"]["expected_text"] == ["Title", "Body"]
    assert expectations["docs/sample.docx"]["expected_tables"] == [[["A", "B"]]]


def test_score_output_counts_text_and_table_cell_coverage():
    expectation = {
        "expected_text": ["Title", "Body"],
        "expected_tables": [[["Name", "Value"], ["A", "10"]]],
    }
    output = "# Title\n\nBody\n\n| Name | Value |\n| --- | --- |\n| A | 10 |"

    score = score_output(output, expectation)

    assert score["expected_text_total"] == 2
    assert score["expected_text_found"] == 2
    assert score["expected_table_cells_total"] == 4
    assert score["expected_table_cells_found"] == 4
    assert score["accuracy"] == 1.0


def test_score_output_ignores_blank_expected_table_cells():
    expectation = {
        "expected_tables": [[["Merged Header", ""], ["", "Q2"]]],
    }

    score = score_output("", expectation)

    assert score["expected_table_cells_total"] == 2
    assert score["expected_table_cells_found"] == 0
    assert score["accuracy"] == 0.0


def test_score_output_counts_expected_table_rows_with_blank_cells():
    expectation = {
        "expected_table_rows": [
            ["Top Left", "", "Top Right"],
            ["", "", ""],
            ["Bottom Left", "", ""],
        ],
    }
    output = "| Top Left |  | Top Right |\n| --- | --- | --- |\n|  |  |  |\n| Bottom Left |  |  |"

    score = score_output(output, expectation)

    assert score["expected_table_rows_total"] == 3
    assert score["expected_table_rows_found"] == 3
    assert score["accuracy"] == 1.0


def test_score_output_counts_expected_markdown_snippets():
    expectation = {
        "expected_text": ["Inherited Title"],
        "expected_markdown": ["# Inherited Title"],
    }

    score = score_output("Inherited Title", expectation)

    assert score["expected_markdown_total"] == 1
    assert score["expected_markdown_found"] == 0
    assert score["accuracy"] == 0.5


def test_score_output_counts_expected_empty_documents():
    expectation = {"expected_empty": True}

    empty_score = score_output("", expectation)
    noisy_score = score_output("Unexpected text", expectation)

    assert empty_score["expected_empty_total"] == 1
    assert empty_score["expected_empty_found"] == 1
    assert empty_score["accuracy"] == 1.0
    assert noisy_score["expected_empty_total"] == 1
    assert noisy_score["expected_empty_found"] == 0
    assert noisy_score["accuracy"] == 0.0


def test_score_output_counts_expected_structured_assets():
    expectation = {
        "expected_text": ["Document"],
        "expected_assets": ["word/embeddings/workbook.xlsx"],
    }

    score = score_output(
        "Document",
        expectation,
        {"json_asset_paths": ["word/embeddings/workbook.xlsx"]},
    )

    assert score["expected_assets_total"] == 1
    assert score["expected_assets_found"] == 1
    assert score["accuracy"] == 1.0


def test_profile_output_counts_markdown_quality_signals():
    output = "\n".join([
        "# Title",
        "See Report <https://example.com/report>",
        "Mail Team <mailto:team@example.com>",
        "![Diagram](word/media/image1.png)",
        "[bookmark: Summary] Summary Target",
        "Body[comment 1]",
        "| Name | Value |",
        "| --- | --- |",
        "| A | 10 (=A1*2) |",
    ])

    profile = profile_output(output)

    assert profile["line_count"] == 9
    assert profile["heading_count"] == 1
    assert profile["markdown_table_row_count"] == 2
    assert profile["link_count"] == 2
    assert profile["image_reference_count"] == 1
    assert profile["comment_marker_count"] == 1
    assert profile["bookmark_marker_count"] == 1
    assert profile["formula_marker_count"] == 1
    assert profile["unique_text_token_count"] == 12


def test_profile_output_counts_image_references_with_brackets_in_alt_text():
    output = "\n".join([
        "![C:\\Temp\\Picture[1].jpg Picture 2](ppt/media/image8.jpeg)",
        "![Diagram](ppt/media/image9.png)",
    ])

    profile = profile_output(output)

    assert profile["image_reference_count"] == 2
    assert profile["unique_text_token_count"] == 0


def test_profile_output_ignores_generated_shape_placeholder_images():
    output = "\n".join([
        "![](Shape662.jpg)",
        "![Diagram](ppt/media/image9.png)",
    ])

    profile = profile_output(output)

    assert profile["image_reference_count"] == 1


def test_profile_output_ignores_spreadsheet_blank_placeholders_as_unique_tokens():
    output = "| Name | Unnamed: 1 |\n| --- | --- |\n| NaN | Value |\n| nan | Unnamed: 2 |\n| NaT | nat |"

    profile = profile_output(output)

    assert profile["unique_text_token_count"] == 2


def test_profile_output_ignores_numeric_only_tokens():
    output = "\n".join([
        "| Rate | Raw | Label |",
        "| --- | --- | --- |",
        "| 6.2% | 0.061700000000000005 | Income tax |",
        "| 2026-06-21 | 12345 | Payroll |",
    ])

    profile = profile_output(output)

    assert profile["unique_text_token_count"] == 6


def test_profile_output_ignores_empty_markdown_table_rows_without_affecting_scoring():
    output = "\n".join([
        "| Name | Value |",
        "| --- | --- |",
        "|  |  |",
        "| A | 10 |",
        "| | |",
        "| NaN | nan | Unnamed: 2 |",
    ])

    profile = profile_output(output)
    score = score_output(output, {"expected_table_rows": [["", ""], ["A", "10"], ["NaN", "nan", "Unnamed: 2"]]})

    assert profile["markdown_table_row_count"] == 2
    assert score["expected_table_rows_found"] == 3


def test_profile_output_counts_only_meaningful_headings():
    output = "\n".join([
        "#",
        "## Sheet",
        "## Sheet1",
        "## Hoja1",
        "### Chart",
        "### Chart:",
        "### Notes:",
        "# Quarterly Review",
    ])

    profile = profile_output(output)

    assert profile["heading_count"] == 1


def test_benchmark_script_uses_worktree_dochan_when_executed_by_path(tmp_path):
    generate_corpus(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_competitors.py",
            str(tmp_path),
            "--formats",
            "docx,pptx,xlsx",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    report = json.loads(result.stdout)
    dochan_rows = [row for row in report["results"] if row["converter"] == "dochan"]

    assert len(dochan_rows) == 3
    assert all(row["nonempty"] for row in dochan_rows)
    assert all(row["accuracy"] == 1.0 for row in dochan_rows)
    assert all(row["line_count"] > 0 for row in dochan_rows)
    assert any(row["bookmark_marker_count"] == 1 for row in dochan_rows if row["format"] == "docx")
    assert any(row["comment_marker_count"] == 1 for row in dochan_rows if row["format"] == "xlsx")


def test_run_benchmark_repeats_and_summarizes_dochan_results(tmp_path):
    generate_corpus(tmp_path)

    report = run_benchmark(tmp_path, formats=["docx"], runs=2)

    assert report["runs"] == 2
    rows = [row for row in report["results"] if row["converter"] == "dochan"]
    assert len(rows) == 2
    assert rows[0]["run"] == 1
    assert rows[1]["run"] == 2
    summary = report["summary"][0]
    assert summary["converter"] == "dochan"
    assert summary["format"] == "docx"
    assert summary["runs"] == 2
    assert summary["median_seconds"] >= 0
    assert summary["best_seconds"] >= 0
    assert summary["mean_accuracy"] == 1.0
    assert summary["median_chars"] > 0
    assert summary["median_table_rows"] >= 0
    assert summary["median_links"] >= 0


def test_run_benchmark_profiles_dochan_structured_json(tmp_path):
    generate_corpus(tmp_path)

    report = run_benchmark(tmp_path, formats=["xlsx"], runs=1, converter_names=["dochan"])
    row = report["results"][0]

    assert row["converter"] == "dochan"
    assert row["json_asset_count"] == 1
    assert row["json_section_provenance_count"] >= 1
    assert row["json_table_count"] >= 1
    assert row["json_table_cell_count"] >= 1
    assert row["json_cell_provenance_count"] >= 1
    assert row["json_cell_paragraph_count"] >= 1
    assert row["json_run_provenance_count"] >= 1
    assert row["json_rich_run_count"] >= 0


def test_run_benchmark_summarizes_dochan_structured_json_profile(tmp_path):
    generate_corpus(tmp_path)

    report = run_benchmark(tmp_path, formats=["docx"], runs=2, converter_names=["dochan"])

    summary = report["summary"][0]
    format_summary = report["format_summary"][0]
    assert summary["median_json_asset_count"] == 1.0
    assert summary["median_json_cell_provenance_count"] >= 1
    assert summary["median_json_run_provenance_count"] >= 1
    assert summary["median_json_rich_run_count"] >= 1
    assert format_summary["median_json_asset_count"] == summary["median_json_asset_count"]
    assert format_summary["median_json_run_provenance_count"] == summary["median_json_run_provenance_count"]


def test_summarize_results_groups_converter_file_and_format():
    summary = summarize_results([
        {
            "converter": "dochan",
            "file": "a.docx",
            "format": "docx",
            "seconds": 0.03,
            "chars": 10,
            "accuracy": 1.0,
            "nonempty": True,
            "error": "",
            "markdown_table_row_count": 2,
            "heading_count": 1,
            "link_count": 1,
            "comment_marker_count": 0,
            "bookmark_marker_count": 1,
            "formula_marker_count": 0,
        },
        {
            "converter": "dochan",
            "file": "a.docx",
            "format": "docx",
            "seconds": 0.01,
            "chars": 30,
            "accuracy": 0.5,
            "nonempty": True,
            "error": "",
            "markdown_table_row_count": 4,
            "heading_count": 3,
            "link_count": 1,
            "comment_marker_count": 2,
            "bookmark_marker_count": 1,
            "formula_marker_count": 2,
        },
    ])

    assert summary == [{
        "converter": "dochan",
        "file": "a.docx",
        "format": "docx",
        "runs": 2,
        "best_seconds": 0.01,
        "median_seconds": 0.02,
        "mean_accuracy": 0.75,
        "success_rate": 1.0,
        "median_chars": 20.0,
        "median_table_rows": 3.0,
        "median_headings": 2.0,
        "median_links": 1.0,
        "median_image_references": 0.0,
        "median_comments": 1.0,
        "median_bookmarks": 1.0,
        "median_formula_markers": 1.0,
        "median_unique_text_tokens": 0.0,
        "representative_output_path": "",
        "median_json_asset_count": 0.0,
        "median_json_section_provenance_count": 0.0,
        "median_json_table_count": 0.0,
        "median_json_table_cell_count": 0.0,
        "median_json_cell_provenance_count": 0.0,
        "median_json_cell_paragraph_count": 0.0,
        "median_json_run_provenance_count": 0.0,
        "median_json_rich_run_count": 0.0,
    }]


def test_summarize_results_treats_expected_empty_output_as_success():
    summary = summarize_results([
        {
            "converter": "dochan",
            "file": "empty.pptx",
            "format": "pptx",
            "seconds": 0.01,
            "chars": 0,
            "accuracy": 1.0,
            "nonempty": False,
            "error": "",
            "expected_empty_total": 1,
            "expected_empty_found": 1,
            "markdown_table_row_count": 0,
            "heading_count": 0,
            "link_count": 0,
            "comment_marker_count": 0,
            "bookmark_marker_count": 0,
            "formula_marker_count": 0,
            "unique_text_token_count": 0,
        },
    ])

    assert summary[0]["success_rate"] == 1.0


def test_summarize_results_treats_semantically_empty_input_as_success_without_expectations():
    summary = summarize_results([
        {
            "converter": "dochan",
            "file": "empty.xlsx",
            "format": "xlsx",
            "seconds": 0.01,
            "chars": 0,
            "nonempty": False,
            "error": "",
            "input_semantic_empty": True,
            "markdown_table_row_count": 0,
            "heading_count": 0,
            "link_count": 0,
            "comment_marker_count": 0,
            "bookmark_marker_count": 0,
            "formula_marker_count": 0,
            "unique_text_token_count": 0,
        },
    ])

    assert summary[0]["success_rate"] == 1.0


def test_input_has_ooxml_semantic_signal_ignores_generic_empty_xlsx_sheet_names(tmp_path):
    empty = tmp_path / "empty.xlsx"
    valued = tmp_path / "valued.xlsx"

    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "xl/workbook.xml",
            '<workbook><sheets><sheet name="Sheet1"/><sheet name="Sheet2"/></sheets></workbook>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row r="1"><c r="A1" s="1"/></row></sheetData></worksheet>')
    with zipfile.ZipFile(valued, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", '<workbook><sheets><sheet name="Data"/></sheets></workbook>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row r="1"><c r="A1"><v>42</v></c></row></sheetData></worksheet>')

    assert input_has_ooxml_semantic_signal(empty) is False
    assert input_has_ooxml_semantic_signal(valued) is True


def test_input_has_ooxml_semantic_signal_counts_docx_alt_chunk_html(tmp_path):
    path = tmp_path / "alt-chunk.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            """
            <w:document
              xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <w:body><w:altChunk r:id="htmlDoc"/></w:body>
            </w:document>
            """,
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship
                Id="htmlDoc"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk"
                Target="/word/htmlDoc.html"/>
            </Relationships>
            """,
        )
        archive.writestr("word/htmlDoc.html", "<html><body><p>Imported HTML body</p></body></html>")

    assert input_has_ooxml_semantic_signal(path) is True


def test_input_has_ooxml_semantic_signal_ignores_empty_docx_with_app_props(tmp_path):
    path = tmp_path / "empty-no-coreprops.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "docProps/app.xml",
            """
            <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
              <Application>Microsoft Macintosh Word</Application>
              <DocSecurity>0</DocSecurity>
            </Properties>
            """,
        )
        archive.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p>
                  <w:bookmarkStart w:id="0" w:name="_GoBack"/>
                  <w:bookmarkEnd w:id="0"/>
                </w:p>
                <w:sectPr/>
              </w:body>
            </w:document>
            """,
        )

    assert input_has_ooxml_semantic_signal(path) is False


def test_summarize_results_treats_unexpected_empty_output_as_failure():
    summary = summarize_results([
        {
            "converter": "markitdown",
            "file": "empty.pptx",
            "format": "pptx",
            "seconds": 0.01,
            "chars": 15,
            "accuracy": 0.0,
            "nonempty": True,
            "error": "",
            "expected_empty_total": 1,
            "expected_empty_found": 0,
            "markdown_table_row_count": 0,
            "heading_count": 0,
            "link_count": 0,
            "comment_marker_count": 0,
            "bookmark_marker_count": 0,
            "formula_marker_count": 0,
            "unique_text_token_count": 1,
        },
    ])

    assert summary[0]["success_rate"] == 0.0


def test_summarize_by_format_compares_real_corpus_without_expectations():
    rows = [
        {
            "converter": "dochan",
            "file": "a.docx",
            "format": "docx",
            "seconds": 0.02,
            "chars": 100,
            "nonempty": True,
            "error": "",
            "markdown_table_row_count": 2,
            "heading_count": 1,
            "link_count": 1,
            "comment_marker_count": 0,
            "bookmark_marker_count": 1,
            "formula_marker_count": 0,
        },
        {
            "converter": "dochan",
            "file": "b.docx",
            "format": "docx",
            "seconds": 0.04,
            "chars": 300,
            "nonempty": True,
            "error": "",
            "markdown_table_row_count": 6,
            "heading_count": 3,
            "link_count": 1,
            "comment_marker_count": 2,
            "bookmark_marker_count": 1,
            "formula_marker_count": 0,
        },
        {
            "converter": "markitdown",
            "file": "a.docx",
            "format": "docx",
            "seconds": 0.20,
            "chars": 20,
            "nonempty": True,
            "error": "",
            "markdown_table_row_count": 0,
            "heading_count": 0,
            "link_count": 0,
            "comment_marker_count": 0,
            "bookmark_marker_count": 0,
            "formula_marker_count": 0,
        },
    ]

    summary = summarize_by_format(rows)

    assert summary == [
        {
            "converter": "dochan",
            "format": "docx",
            "files": 2,
            "runs": 2,
            "success_rate": 1.0,
            "best_seconds": 0.02,
            "median_seconds": 0.03,
            "mean_accuracy": None,
            "median_chars": 200.0,
            "median_table_rows": 4.0,
            "median_headings": 2.0,
            "median_links": 1.0,
            "median_image_references": 0.0,
            "median_comments": 1.0,
            "median_bookmarks": 1.0,
            "median_formula_markers": 0.0,
            "median_unique_text_tokens": 0.0,
            "representative_output_path": "",
            "median_json_asset_count": 0.0,
            "median_json_section_provenance_count": 0.0,
            "median_json_table_count": 0.0,
            "median_json_table_cell_count": 0.0,
            "median_json_cell_provenance_count": 0.0,
            "median_json_cell_paragraph_count": 0.0,
            "median_json_run_provenance_count": 0.0,
            "median_json_rich_run_count": 0.0,
        },
        {
            "converter": "markitdown",
            "format": "docx",
            "files": 1,
            "runs": 1,
            "success_rate": 1.0,
            "best_seconds": 0.20,
            "median_seconds": 0.20,
            "mean_accuracy": None,
            "median_chars": 20,
            "median_table_rows": 0,
            "median_headings": 0,
            "median_links": 0,
            "median_image_references": 0,
            "median_comments": 0,
            "median_bookmarks": 0,
            "median_formula_markers": 0,
            "median_unique_text_tokens": 0,
            "representative_output_path": "",
            "median_json_asset_count": 0,
            "median_json_section_provenance_count": 0,
            "median_json_table_count": 0,
            "median_json_table_cell_count": 0,
            "median_json_cell_provenance_count": 0,
            "median_json_cell_paragraph_count": 0,
            "median_json_run_provenance_count": 0,
            "median_json_rich_run_count": 0,
        },
    ]


def test_compare_against_dochan_reports_speed_and_accuracy_delta_by_format():
    format_summary = [
        {
            "converter": "dochan",
            "format": "docx",
            "files": 3,
            "runs": 9,
            "success_rate": 1.0,
            "median_seconds": 0.01,
            "mean_accuracy": 1.0,
            "median_chars": 300,
            "median_table_rows": 4,
            "median_headings": 3,
            "median_links": 2,
            "median_image_references": 1,
            "median_comments": 1,
            "median_bookmarks": 1,
            "median_formula_markers": 2,
            "median_unique_text_tokens": 10,
            "median_json_asset_count": 1,
            "median_json_run_provenance_count": 12,
        },
        {
            "converter": "markitdown",
            "format": "docx",
            "files": 3,
            "runs": 9,
            "success_rate": 1.0,
            "median_seconds": 0.05,
            "mean_accuracy": 0.6,
            "median_chars": 120,
            "median_table_rows": 1,
            "median_headings": 1,
            "median_links": 0,
            "median_image_references": 0,
            "median_comments": 0,
            "median_bookmarks": 0,
            "median_formula_markers": 0,
            "median_unique_text_tokens": 4,
            "median_json_asset_count": 0,
            "median_json_run_provenance_count": 0,
        },
        {
            "converter": "docling",
            "format": "pptx",
            "files": 3,
            "runs": 9,
            "success_rate": 0.0,
            "median_seconds": 0.04,
            "mean_accuracy": None,
            "median_chars": 0,
            "median_table_rows": 0,
            "median_headings": 0,
            "median_links": 0,
            "median_image_references": 0,
            "median_comments": 0,
            "median_bookmarks": 0,
            "median_formula_markers": 0,
            "median_unique_text_tokens": 0,
        },
    ]

    comparison = compare_against_dochan(format_summary)

    assert comparison == [
        {
            "format": "docx",
            "competitor": "markitdown",
            "dochan_available": True,
            "competitor_available": True,
            "dochan_median_seconds": 0.01,
            "competitor_median_seconds": 0.05,
            "speedup_vs_competitor": 5.0,
            "dochan_mean_accuracy": 1.0,
            "competitor_mean_accuracy": 0.6,
            "accuracy_delta": 0.4,
            "dochan_success_rate": 1.0,
            "competitor_success_rate": 1.0,
            "success_rate_delta": 0.0,
            "median_chars_delta": 180,
            "median_table_rows_delta": 3,
            "median_headings_delta": 2,
            "median_links_delta": 2,
            "median_image_references_delta": 1,
            "median_comments_delta": 1,
            "median_bookmarks_delta": 1,
            "median_formula_markers_delta": 2,
            "median_unique_text_tokens_delta": 6,
            "median_json_asset_count_delta": 1,
            "median_json_run_provenance_count_delta": 12,
        },
        {
            "format": "pptx",
            "competitor": "docling",
            "dochan_available": False,
            "competitor_available": True,
            "dochan_median_seconds": None,
            "competitor_median_seconds": 0.04,
            "speedup_vs_competitor": None,
            "dochan_mean_accuracy": None,
            "competitor_mean_accuracy": None,
            "accuracy_delta": None,
            "dochan_success_rate": None,
            "competitor_success_rate": 0.0,
            "success_rate_delta": None,
            "median_chars_delta": None,
            "median_table_rows_delta": None,
            "median_headings_delta": None,
            "median_links_delta": None,
            "median_image_references_delta": None,
            "median_comments_delta": None,
            "median_bookmarks_delta": None,
            "median_formula_markers_delta": None,
            "median_unique_text_tokens_delta": None,
        },
    ]


def test_find_improvement_candidates_prioritizes_dochan_weaknesses():
    rows = [
        {
            "format": "docx",
            "competitor": "markitdown",
            "accuracy_delta": -0.4,
            "success_rate_delta": -0.5,
            "median_table_rows_delta": -2,
            "median_headings_delta": -1,
            "median_links_delta": -1,
            "median_chars_delta": -120,
        },
        {
            "format": "pptx",
            "competitor": "docling",
            "accuracy_delta": 1.0,
            "success_rate_delta": 1.0,
            "median_table_rows_delta": 7,
            "median_links_delta": 3,
            "median_chars_delta": 409,
        },
        {
            "format": "xlsx",
            "competitor": "markitdown",
            "accuracy_delta": 0.75,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": 1,
            "median_links_delta": 4,
            "median_chars_delta": 151,
        },
    ]

    candidates = find_improvement_candidates(rows)

    assert candidates == [
        {
            "format": "docx",
            "competitor": "markitdown",
            "worst_gap_score": 1.05,
            "reasons": [
                "dochan_accuracy_trails_by=0.400",
                "dochan_success_rate_trails_by=0.500",
                "dochan_table_rows_trail_by=2",
                "dochan_headings_trail_by=1",
                "dochan_links_trail_by=1",
            ],
        },
    ]


def test_compare_files_against_dochan_reports_file_level_profile_gaps():
    summary = [
        {
            "converter": "dochan",
            "file": "corpus/a.docx",
            "format": "docx",
            "runs": 1,
            "median_seconds": 0.01,
            "mean_accuracy": None,
            "success_rate": 1.0,
            "median_chars": 100,
            "median_table_rows": 0,
            "median_headings": 0,
            "median_links": 0,
            "median_image_references": 0,
            "median_comments": 0,
            "median_bookmarks": 0,
            "median_formula_markers": 0,
            "median_unique_text_tokens": 4,
            "representative_output_path": "/tmp/out/dochan/a.docx.run1.md",
        },
        {
            "converter": "markitdown",
            "file": "corpus/a.docx",
            "format": "docx",
            "runs": 1,
            "median_seconds": 0.02,
            "mean_accuracy": None,
            "success_rate": 1.0,
            "median_chars": 500,
            "median_table_rows": 4,
            "median_headings": 2,
            "median_links": 2,
            "median_image_references": 1,
            "median_comments": 1,
            "median_bookmarks": 1,
            "median_formula_markers": 0,
            "median_unique_text_tokens": 10,
            "representative_output_path": "/tmp/out/markitdown/a.docx.run1.md",
        },
    ]

    comparison = compare_files_against_dochan(summary)

    assert comparison == [
        {
            "file": "corpus/a.docx",
            "format": "docx",
            "competitor": "markitdown",
            "dochan_available": True,
            "competitor_available": True,
            "dochan_median_seconds": 0.01,
            "competitor_median_seconds": 0.02,
            "speedup_vs_competitor": 2.0,
            "dochan_mean_accuracy": None,
            "competitor_mean_accuracy": None,
            "accuracy_delta": None,
            "dochan_success_rate": 1.0,
            "competitor_success_rate": 1.0,
            "success_rate_delta": 0.0,
            "median_chars_delta": -400,
            "median_table_rows_delta": -4,
            "median_headings_delta": -2,
            "median_links_delta": -2,
            "median_image_references_delta": -1,
            "median_comments_delta": -1,
            "median_bookmarks_delta": -1,
            "median_formula_markers_delta": 0,
            "median_unique_text_tokens_delta": -6,
            "dochan_output_path": "/tmp/out/dochan/a.docx.run1.md",
            "competitor_output_path": "/tmp/out/markitdown/a.docx.run1.md",
        },
    ]


def test_file_improvement_candidates_surface_single_file_regressions():
    rows = [
        {
            "file": "corpus/a.docx",
            "format": "docx",
            "competitor": "markitdown",
            "accuracy_delta": None,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": -4,
            "median_headings_delta": -2,
            "median_links_delta": -2,
            "median_chars_delta": -400,
            "median_unique_text_tokens_delta": -6,
            "dochan_output_path": "/tmp/out/dochan/a.docx.run1.md",
            "competitor_output_path": "/tmp/out/markitdown/a.docx.run1.md",
        },
        {
            "file": "corpus/b.pptx",
            "format": "pptx",
            "competitor": "docling",
            "accuracy_delta": None,
            "success_rate_delta": 1.0,
            "median_table_rows_delta": 2,
            "median_headings_delta": 0,
            "median_links_delta": 0,
            "median_chars_delta": 120,
            "median_unique_text_tokens_delta": 0,
        },
    ]

    candidates = find_file_improvement_candidates(rows)

    assert candidates == [
        {
            "file": "corpus/a.docx",
            "format": "docx",
            "competitor": "markitdown",
            "worst_gap_score": 0.15,
            "reasons": [
                "dochan_table_rows_trail_by=4",
                "dochan_headings_trail_by=2",
                "dochan_links_trail_by=2",
            ],
            "dochan_output_path": "/tmp/out/dochan/a.docx.run1.md",
            "competitor_output_path": "/tmp/out/markitdown/a.docx.run1.md",
        },
    ]


def test_file_improvement_candidates_ignore_table_only_layout_deltas():
    rows = [
        {
            "file": "corpus/layout-only.xlsx",
            "format": "xlsx",
            "competitor": "docling",
            "accuracy_delta": None,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": -137,
            "median_headings_delta": 0,
            "median_links_delta": 0,
            "median_chars_delta": -6000,
            "median_unique_text_tokens_delta": 0,
        },
    ]

    assert find_file_improvement_candidates(rows) == []


def test_format_improvement_candidates_ignore_table_only_layout_deltas():
    rows = [
        {
            "format": "xlsx",
            "competitor": "docling",
            "accuracy_delta": 0.571,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": -1,
            "median_headings_delta": 3,
            "median_links_delta": 4,
            "median_chars_delta": -411,
            "median_unique_text_tokens_delta": 12,
        },
    ]

    assert find_improvement_candidates(rows) == []


def test_file_improvement_candidates_ignore_placeholder_only_token_deltas():
    rows = [
        {
            "file": "xlsx/book.xlsx",
            "format": "xlsx",
            "competitor": "markitdown",
            "accuracy_delta": 0.5,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": -2,
            "median_headings_delta": 0,
            "median_links_delta": 0,
            "median_chars_delta": -80,
            "median_unique_text_tokens_delta": 0,
        },
    ]

    assert find_file_improvement_candidates(rows) == []


def test_profile_ignores_nat_placeholder_table_rows():
    output = """
    | Unnamed: 0 | Unnamed: 1 |
    | --- | --- |
    | NaT | NaN |
    | 2026-06-21 | Revenue |
    """

    profile = profile_output(output)

    assert profile["markdown_table_row_count"] == 1


def test_file_improvement_candidates_surface_semantic_profile_deltas():
    rows = [
        {
            "file": "corpus/rich.xlsx",
            "format": "xlsx",
            "competitor": "docling",
            "accuracy_delta": None,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": 0,
            "median_headings_delta": 0,
            "median_links_delta": 0,
            "median_image_references_delta": -2,
            "median_comments_delta": -1,
            "median_bookmarks_delta": 0,
            "median_formula_markers_delta": -3,
            "median_chars_delta": -80,
            "median_unique_text_tokens_delta": -5,
            "dochan_output_path": "/tmp/out/dochan/rich.xlsx.run1.md",
            "competitor_output_path": "/tmp/out/docling/rich.xlsx.run1.md",
        },
    ]

    assert find_file_improvement_candidates(rows) == [
        {
            "file": "corpus/rich.xlsx",
            "format": "xlsx",
            "competitor": "docling",
            "worst_gap_score": 0.15,
            "reasons": [
                "dochan_image_references_trail_by=2",
                "dochan_comments_trail_by=1",
                "dochan_formula_markers_trail_by=3",
            ],
            "dochan_output_path": "/tmp/out/dochan/rich.xlsx.run1.md",
            "competitor_output_path": "/tmp/out/docling/rich.xlsx.run1.md",
        },
    ]


def test_file_improvement_candidates_surface_heading_structure_deltas():
    rows = [
        {
            "file": "corpus/structured.docx",
            "format": "docx",
            "competitor": "markitdown",
            "accuracy_delta": None,
            "success_rate_delta": 0.0,
            "median_table_rows_delta": 0,
            "median_headings_delta": -3,
            "median_links_delta": 0,
            "median_image_references_delta": 0,
            "median_comments_delta": 0,
            "median_bookmarks_delta": 0,
            "median_formula_markers_delta": 0,
            "median_chars_delta": -120,
            "median_unique_text_tokens_delta": -4,
            "dochan_output_path": "/tmp/out/dochan/structured.docx.run1.md",
            "competitor_output_path": "/tmp/out/markitdown/structured.docx.run1.md",
        },
    ]

    assert find_file_improvement_candidates(rows) == [
        {
            "file": "corpus/structured.docx",
            "format": "docx",
            "competitor": "markitdown",
            "worst_gap_score": 0.05,
            "reasons": [
                "dochan_headings_trail_by=3",
            ],
            "dochan_output_path": "/tmp/out/dochan/structured.docx.run1.md",
            "competitor_output_path": "/tmp/out/markitdown/structured.docx.run1.md",
        },
    ]
