import json

import scripts.download_public_ooxml_corpus as corpus_script
from scripts.download_public_ooxml_corpus import (
    PUBLIC_OOXML_EXPECTATIONS,
    PUBLIC_OOXML_FIXTURES,
    download_corpus,
    load_fixture_index,
    load_apache_poi_probe_manifest,
    record_apache_poi_probe_manifest,
    selected_fixtures,
    select_unseen_apache_poi_fixtures,
    write_expected_manifest,
)


def test_public_ooxml_fixtures_cover_docx_pptx_and_xlsx_with_licenses():
    formats = {fixture["format"] for fixture in PUBLIC_OOXML_FIXTURES}
    names = {fixture["name"] for fixture in PUBLIC_OOXML_FIXTURES}

    assert {"docx", "pptx", "xlsx"}.issubset(formats)
    assert all(fixture["license"] in {"MIT", "BSD-3-Clause", "Apache-2.0"} for fixture in PUBLIC_OOXML_FIXTURES)
    assert all(fixture["url"].startswith("https://raw.githubusercontent.com/") for fixture in PUBLIC_OOXML_FIXTURES)
    assert sum(1 for fixture in PUBLIC_OOXML_FIXTURES if fixture["format"] == "docx") >= 14
    assert sum(1 for fixture in PUBLIC_OOXML_FIXTURES if fixture["format"] == "pptx") >= 13
    assert sum(1 for fixture in PUBLIC_OOXML_FIXTURES if fixture["format"] == "xlsx") >= 15
    assert {
        "apache-poi-footnotes.docx",
        "apache-poi-bookmarks.docx",
        "apache-poi-checkboxes.docx",
        "apache-poi-deep-table-cell.docx",
        "apache-poi-shapes-with-text.docx",
        "apache-poi-endnotes.docx",
        "apache-poi-heading123.docx",
        "apache-poi-header-footer-unicode.docx",
        "apache-poi-embedded-document.docx",
        "apache-poi-sample.docx",
        "apache-poi-bar-chart.pptx",
        "apache-poi-sample.pptx",
        "apache-poi-shapes.pptx",
        "apache-poi-with-master.pptx",
        "apache-poi-comments.pptx",
        "apache-poi-inline-strings.xlsx",
        "apache-poi-with-japanese.pptx",
        "apache-poi-sample.xlsx",
        "apache-poi-sample-strict.xlsx",
        "apache-poi-shared-hyperlink.xlsx",
        "apache-poi-header-footer.xlsx",
        "apache-poi-ampersand-header.xlsx",
        "apache-poi-header-footer-complex.xlsx",
        "apache-poi-simple-comments.xlsx",
        "apache-poi-simple-strict.xlsx",
        "apache-poi-with-textbox.xlsx",
        "apache-poi-with-drawing.xlsx",
        "apache-poi-picture.xlsx",
        "apache-poi-with-chart.xlsx",
        "apache-poi-chart-title-formula.xlsx",
        "python-docx-comments-rich-para.docx",
        "doxx-comprehensive.docx",
        "python-pptx-prs-notes.pptx",
        "python-pptx-shp-shapes.pptx",
        "eparse-nested.xlsx",
    }.issubset(names)


def test_selected_fixtures_filters_formats_without_losing_order():
    fixtures = selected_fixtures(["xlsx", "docx"])

    assert fixtures
    assert [fixture["format"] for fixture in fixtures] == [
        fixture["format"]
        for fixture in PUBLIC_OOXML_FIXTURES
        if fixture["format"] in {"xlsx", "docx"}
    ]


def test_public_ooxml_expectations_cover_selected_semantic_fixtures():
    assert {
        "docx/apache-poi-footnotes.docx",
        "docx/apache-poi-bookmarks.docx",
        "docx/apache-poi-checkboxes.docx",
        "docx/apache-poi-deep-table-cell.docx",
        "docx/apache-poi-shapes-with-text.docx",
        "docx/apache-poi-endnotes.docx",
        "docx/apache-poi-heading123.docx",
        "docx/apache-poi-header-footer-unicode.docx",
        "docx/apache-poi-embedded-document.docx",
        "docx/apache-poi-sample.docx",
        "docx/doxx-images.docx",
        "docx/doxx-comprehensive.docx",
        "docx/python-docx-blk-inner-content.docx",
        "docx/python-docx-comments-rich-para.docx",
        "docx/python-docx-having-images.docx",
        "docx/python-docx-hdr-header-footer.docx",
        "docx/python-docx-num-having-numbering-part.docx",
        "docx/python-docx-test.docx",
        "pptx/apache-poi-bar-chart.pptx",
        "pptx/apache-poi-sample.pptx",
        "pptx/apache-poi-shapes.pptx",
        "pptx/apache-poi-with-master.pptx",
        "pptx/apache-poi-comments.pptx",
        "pptx/apache-poi-with-japanese.pptx",
        "pptx/python-pptx-cht-charts.pptx",
        "pptx/python-pptx-minimal.pptx",
        "pptx/python-pptx-prs-notes.pptx",
        "pptx/python-pptx-shp-picture.pptx",
        "pptx/python-pptx-shp-shapes.pptx",
        "pptx/python-pptx-tbl-cell.pptx",
        "pptx/python-pptx-test-slides.pptx",
        "pptx/python-pptx-test.pptx",
        "xlsx/apache-poi-inline-strings.xlsx",
        "xlsx/apache-poi-sample.xlsx",
        "xlsx/apache-poi-sample-strict.xlsx",
        "xlsx/apache-poi-shared-hyperlink.xlsx",
        "xlsx/apache-poi-header-footer.xlsx",
        "xlsx/apache-poi-ampersand-header.xlsx",
        "xlsx/apache-poi-header-footer-complex.xlsx",
        "xlsx/apache-poi-simple-comments.xlsx",
        "xlsx/apache-poi-simple-strict.xlsx",
        "xlsx/apache-poi-with-textbox.xlsx",
        "xlsx/apache-poi-with-drawing.xlsx",
        "xlsx/apache-poi-picture.xlsx",
        "xlsx/apache-poi-with-chart.xlsx",
        "xlsx/apache-poi-chart-title-formula.xlsx",
        "xlsx/eparse-nested.xlsx",
        "xlsx/eparse-unit.xlsx",
        "xlsx/pyexcel-bug-176.xlsx",
        "xlsx/pyexcel-empty-sheet.xlsx",
    }.issubset(PUBLIC_OOXML_EXPECTATIONS)
    assert "[bookmark: poi] Sample Word Document" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-bookmarks.docx"]["expected_markdown"]
    assert "unchecked: [ ]" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-checkboxes.docx"]["expected_text"]
    assert ["[ ]", "[x]"] in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-checkboxes.docx"]["expected_table_rows"]
    assert "Nested level 31" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-deep-table-cell.docx"]["expected_text"]
    assert "[nested table omitted: depth limit exceeded]" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-deep-table-cell.docx"]["expected_markdown"]
    assert "A square shape with text inside" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-shapes-with-text.docx"]["expected_text"]
    assert "A square shape with text inside\nAn ellipse with text inside" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-shapes-with-text.docx"]["expected_markdown"][0]
    assert "[^미주]: XXX" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-endnotes.docx"]["expected_markdown"]
    assert "### Third paragraph" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-heading123.docx"]["expected_markdown"]
    assert "This is a simple header, with a € euro symbol in it." in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-header-footer-unicode.docx"]["expected_text"]
    assert "Let me see what happens if I insert a worksheet." in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_text"]
    assert "![image](word/media/image1.emf)" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_markdown"]
    assert "word/embeddings/Microsoft_Office_Excel_97-2003_Worksheet1.xls" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_assets"]
    assert "word/media/image1.emf" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_assets"]
    assert "Eto ochen prostoy<sup>[1]</sup> text so snoskoy" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-footnotes.docx"]["expected_text"]
    assert "# Test Document" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-sample.docx"]["expected_markdown"]
    assert "# Comprehensive Test Document" in PUBLIC_OOXML_EXPECTATIONS["docx/doxx-comprehensive.docx"]["expected_markdown"]
    assert ["Product", "Quantity", "Price"] in PUBLIC_OOXML_EXPECTATIONS["docx/doxx-comprehensive.docx"]["expected_tables"][0]
    assert ["T2", ""] in PUBLIC_OOXML_EXPECTATIONS["docx/python-docx-blk-inner-content.docx"]["expected_table_rows"]
    assert "![Picture 5](word/media/image3.png)" in PUBLIC_OOXML_EXPECTATIONS["docx/python-docx-having-images.docx"]["expected_markdown"]
    assert "<!-- header: Header for section-1 -->" in PUBLIC_OOXML_EXPECTATIONS["docx/python-docx-hdr-header-footer.docx"]["expected_markdown"]
    assert "Paragraph having List Number style." in PUBLIC_OOXML_EXPECTATIONS["docx/python-docx-num-having-numbering-part.docx"]["expected_text"]
    assert "Photo of boulders on beach in bright sunshine" in PUBLIC_OOXML_EXPECTATIONS["docx/doxx-images.docx"]["expected_text"]
    assert "python-docx was here too!" in PUBLIC_OOXML_EXPECTATIONS["docx/python-docx-test.docx"]["expected_text"]
    assert ["Column1", "Column2", "Column3"] in PUBLIC_OOXML_EXPECTATIONS["pptx/apache-poi-shapes.pptx"]["expected_table_rows"]
    assert ["Category", "Sales"] in PUBLIC_OOXML_EXPECTATIONS["pptx/apache-poi-bar-chart.pptx"]["expected_table_rows"]
    assert "# Lorem ipsum dolor sit amet" in PUBLIC_OOXML_EXPECTATIONS["pptx/apache-poi-sample.pptx"]["expected_markdown"]
    assert "This text comes from the Master Slide" in PUBLIC_OOXML_EXPECTATIONS["pptx/apache-poi-with-master.pptx"]["expected_text"]
    assert "[comment: XPVMWARE01: testdoc]" in PUBLIC_OOXML_EXPECTATIONS["pptx/apache-poi-comments.pptx"]["expected_text"]
    assert "ゾルゲと尾崎、淡々と最期" in PUBLIC_OOXML_EXPECTATIONS["pptx/apache-poi-with-japanese.pptx"]["expected_text"]
    assert ["Category 4", "4.5", "2.8", "5.0"] in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-cht-charts.pptx"]["expected_table_rows"]
    assert "Author: python-pptx" in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-minimal.pptx"]["expected_markdown"]
    assert "Notes" in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-prs-notes.pptx"]["expected_text"]
    assert "![Picture 3](ppt/media/image2.png)" in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-shp-picture.pptx"]["expected_markdown"]
    assert "expected_text" not in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-shp-shapes.pptx"]
    assert ["Category", "Sales"] in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-shp-shapes.pptx"]["expected_table_rows"]
    assert ["a", "b", "c"] in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-tbl-cell.pptx"]["expected_table_rows"]
    assert "Group test text" in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-test-slides.pptx"]["expected_text"]
    assert "Presentation Title Text" in PUBLIC_OOXML_EXPECTATIONS["pptx/python-pptx-test.pptx"]["expected_text"]
    assert ["12", "A", "1st Inline String", "12 (=A2)"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-inline-strings.xlsx"]["expected_table_rows"]
    assert ["1", "10", "2", "13 (=SUM(A7:C7))"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-sample.xlsx"]["expected_table_rows"]
    assert ["1", "10", "2", "13 (=SUM(A7:C7))"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-sample-strict.xlsx"]["expected_table_rows"]
    assert "http://www.apache.org <http://www.apache.org/>" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-shared-hyperlink.xlsx"]["expected_markdown"]
    assert "<!-- header: top left | top center | top right -->" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-header-footer.xlsx"]["expected_markdown"]
    assert ["abc", "123"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-header-footer.xlsx"]["expected_table_rows"]
    assert "<!-- header: one & two && -->" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-ampersand-header.xlsx"]["expected_markdown"]
    assert "<!-- footer: Footer ArialBlue TahomaBoldGreen -->" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-header-footer-complex.xlsx"]["expected_markdown"]
    assert ["2", "two [comment: Yegor Kozlov: Yegor Kozlov: second cell]"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-simple-comments.xlsx"]["expected_table_rows"]
    assert ["10 (=SUM(A3:D3))", "", "3 (=C3)", "", "", ""] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-simple-strict.xlsx"]["expected_table_rows"]
    assert "Line 1\nLine 2\nLine 3" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-with-textbox.xlsx"]["expected_markdown"]
    assert "![tomcat.png Picture 4](xl/media/image3.png)" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-with-drawing.xlsx"]["expected_markdown"]
    assert "Sheet with various pictures\n(jpeg, png, wmf, emf and pict)" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-with-drawing.xlsx"]["expected_markdown"]
    assert "![Graphics 1 Graphics 1](xl/media/10000000000006450000032120C875D8.jpg)" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-picture.xlsx"]["expected_markdown"]
    assert ["Lorem", "111"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-picture.xlsx"]["expected_table_rows"]
    assert ["Category", "1st Column", "2nd Column"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-with-chart.xlsx"]["expected_table_rows"]
    assert ["5", "6", "17"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-with-chart.xlsx"]["expected_table_rows"]
    assert "### Formula Title from Excel 2016" in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-chart-title-formula.xlsx"]["expected_markdown"]
    assert ["5", "3.1"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/apache-poi-chart-title-formula.xlsx"]["expected_table_rows"]
    assert ["", "", "", "ID001", "Item 1", "Category A", "100", "Active", "2024-01-01", "Note 1", "Extra 1", "More 1"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/eparse-nested.xlsx"]["expected_table_rows"]
    assert ["", "Financials", "Revenue", "809127967.91789377", "964987674.26480222", "354635194.54920423", "644839345.4671768", "297294601.68441468", "808624104.77259195", "22288256.012496509", "576767887.49204695"] in PUBLIC_OOXML_EXPECTATIONS["xlsx/eparse-unit.xlsx"]["expected_table_rows"]
    assert ["title", "Coffs Harbour", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""] in PUBLIC_OOXML_EXPECTATIONS["xlsx/pyexcel-bug-176.xlsx"]["expected_table_rows"]


def test_write_expected_manifest_filters_to_downloaded_records(tmp_path):
    records = [
        {"path": "docx/doxx-comprehensive.docx"},
        {"path": "pptx/python-pptx-minimal.pptx"},
        {"path": "xlsx/pyexcel-empty-sheet.xlsx"},
    ]

    write_expected_manifest(tmp_path, records)

    expected = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))
    assert sorted(expected) == [
        "docx/doxx-comprehensive.docx",
        "pptx/python-pptx-minimal.pptx",
        "xlsx/pyexcel-empty-sheet.xlsx",
    ]


def test_select_unseen_apache_poi_fixtures_skips_manifested_ids_per_format():
    candidates = [
        {"name": "a.docx", "format": "docx", "source_name": "a.docx"},
        {"name": "b.docx", "format": "docx", "source_name": "b.docx"},
        {"name": "c.docx", "format": "docx", "source_name": "c.docx"},
        {"name": "a.pptx", "format": "pptx", "source_name": "a.pptx"},
        {"name": "b.pptx", "format": "pptx", "source_name": "b.pptx"},
    ]
    manifest = {
        "version": 1,
        "used": {
            "docx": ["a.docx"],
            "pptx": ["a.pptx"],
        },
        "probes": [],
    }

    selected = select_unseen_apache_poi_fixtures(candidates, ["docx", "pptx"], per_format=1, manifest=manifest)

    assert [item["source_name"] for item in selected] == ["b.docx", "b.pptx"]


def test_record_apache_poi_probe_manifest_persists_used_ids_and_probe_files(tmp_path):
    manifest_path = tmp_path / "apache-poi-probe-manifest.json"
    first_records = [
        {"format": "docx", "source_name": "first.docx", "path": "docx/first.docx"},
        {"format": "xlsx", "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/first.xlsx"},
    ]
    second_records = [
        {"format": "docx", "source_name": "second.docx", "path": "docx/second.docx"},
    ]

    record_apache_poi_probe_manifest(manifest_path, first_records, "probe-1")
    manifest = record_apache_poi_probe_manifest(manifest_path, second_records, "probe-2")
    reloaded = load_apache_poi_probe_manifest(manifest_path)

    assert manifest == reloaded
    assert reloaded["used"] == {
        "docx": ["first.docx", "second.docx"],
        "xlsx": ["first.xlsx"],
    }
    assert [probe["name"] for probe in reloaded["probes"]] == ["probe-1", "probe-2"]
    assert reloaded["probes"][0]["files"] == [
        {"format": "docx", "id": "first.docx", "path": "docx/first.docx"},
        {"format": "xlsx", "id": "first.xlsx", "path": ""},
    ]


def test_load_fixture_index_accepts_top_level_list_and_fixtures_object(tmp_path):
    list_path = tmp_path / "fixtures-list.json"
    object_path = tmp_path / "fixtures-object.json"
    list_path.write_text(json.dumps([{"name": "a.docx", "format": "docx"}]), encoding="utf-8")
    object_path.write_text(json.dumps({"fixtures": [{"name": "b.xlsx", "format": "xlsx"}]}), encoding="utf-8")

    assert load_fixture_index(list_path) == [{"name": "a.docx", "format": "docx"}]
    assert load_fixture_index(object_path) == [{"name": "b.xlsx", "format": "xlsx"}]


def test_download_corpus_can_filter_fixture_index_through_probe_manifest(tmp_path, monkeypatch):
    fixtures = [
        {
            "name": "a.docx",
            "format": "docx",
            "source_name": "a.docx",
            "source": "apache/poi",
            "license": "Apache-2.0",
            "url": "https://example.test/a.docx",
        },
        {
            "name": "b.docx",
            "format": "docx",
            "source_name": "b.docx",
            "source": "apache/poi",
            "license": "Apache-2.0",
            "url": "https://example.test/b.docx",
        },
        {
            "name": "a.xlsx",
            "format": "xlsx",
            "source_name": "a.xlsx",
            "source": "apache/poi",
            "license": "Apache-2.0",
            "url": "https://example.test/a.xlsx",
        },
        {
            "name": "b.xlsx",
            "format": "xlsx",
            "source_name": "b.xlsx",
            "source": "apache/poi",
            "license": "Apache-2.0",
            "url": "https://example.test/b.xlsx",
        },
    ]
    manifest_path = tmp_path / "apache-poi-probe-manifest.json"
    record_apache_poi_probe_manifest(manifest_path, [fixtures[0], fixtures[2]], "already-used")

    def fake_download_fixture(fixture, output_dir):
        format_dir = output_dir / fixture["format"]
        format_dir.mkdir(parents=True, exist_ok=True)
        destination = format_dir / fixture["name"]
        destination.write_text("fixture", encoding="utf-8")
        record = dict(fixture)
        record["path"] = destination.relative_to(output_dir).as_posix()
        record["bytes"] = destination.stat().st_size
        return record

    monkeypatch.setattr(corpus_script, "download_fixture", fake_download_fixture)

    records = download_corpus(
        tmp_path / "corpus",
        ["docx", "xlsx"],
        fixtures=fixtures,
        probe_manifest_path=manifest_path,
        probe_name="next-probe",
        probe_per_format=1,
    )
    manifest = load_apache_poi_probe_manifest(manifest_path)

    assert [record["source_name"] for record in records] == ["b.docx", "b.xlsx"]
    assert manifest["used"] == {
        "docx": ["a.docx", "b.docx"],
        "xlsx": ["a.xlsx", "b.xlsx"],
    }
    assert manifest["probes"][-1]["name"] == "next-probe"
    assert sorted((tmp_path / "corpus").rglob("*.*"))
