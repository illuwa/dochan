import hashlib
import io
import json
import re

import pytest

import scripts.download_public_ooxml_corpus as corpus_script
from scripts.download_public_ooxml_corpus import (
    APACHE_POI_PROBE_MANIFEST_VERSION,
    PUBLIC_OOXML_EXPECTATIONS,
    PUBLIC_OOXML_FIXTURES,
    apache_poi_fixture_id,
    apache_poi_fixture_source_id,
    atomic_write_text,
    download_corpus,
    load_fixture_index,
    load_apache_poi_probe_manifest,
    record_apache_poi_probe_manifest,
    record_probe_outcome,
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


def test_builtin_fixture_sources_and_integrity_are_immutable():
    for fixture in PUBLIC_OOXML_FIXTURES:
        revision = fixture["source_revision"]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)
        assert "/{}/".format(revision) in fixture["url"]
        assert isinstance(fixture["bytes"], int) and fixture["bytes"] > 0
        assert re.fullmatch(r"[0-9a-f]{64}", fixture["sha256"])


def test_selected_fixtures_filters_formats_without_losing_order():
    fixtures = selected_fixtures(["xlsx", "docx"])

    assert fixtures
    assert [fixture["format"] for fixture in fixtures] == [
        fixture["format"]
        for fixture in PUBLIC_OOXML_FIXTURES
        if fixture["format"] in {"xlsx", "docx"}
    ]


def test_selected_fixtures_preserves_an_explicit_empty_fixture_index():
    assert selected_fixtures(["docx"], fixtures=[]) == []


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
    assert "[^1]: XXX" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-endnotes.docx"]["expected_markdown"]
    assert "### Third paragraph" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-heading123.docx"]["expected_markdown"]
    assert "This is a simple header, with a € euro symbol in it." in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-header-footer-unicode.docx"]["expected_text"]
    assert "Let me see what happens if I insert a worksheet." in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_text"]
    assert "![image](word/media/image1.emf)" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_markdown"]
    assert "word/embeddings/Microsoft_Office_Excel_97-2003_Worksheet1.xls" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_assets"]
    assert "word/media/image1.emf" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-embedded-document.docx"]["expected_assets"]
    assert "Eto ochen prostoy[^1] text so snoskoy" in PUBLIC_OOXML_EXPECTATIONS["docx/apache-poi-footnotes.docx"]["expected_text"]
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


def test_write_expected_manifest_atomically_replaces_stale_data_with_empty_object(tmp_path):
    manifest = tmp_path / "expected.json"
    manifest.write_text(
        json.dumps({"docx/stale.docx": {"expected_text": ["stale"]}}),
        encoding="utf-8",
    )

    write_expected_manifest(tmp_path, [{"path": "docx/current.docx"}])

    assert json.loads(manifest.read_text(encoding="utf-8")) == {}
    assert list(tmp_path.glob(".expected.json.*.tmp")) == []


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


def test_fixture_identity_changes_with_revision_and_content_digest():
    fixture = {
        "name": "same.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "fixtures/same.docx",
        "source_revision": "1" * 40,
        "sha256": "a" * 64,
    }

    original = apache_poi_fixture_id(fixture)
    revised = apache_poi_fixture_id({**fixture, "source_revision": "2" * 40})
    changed_content = apache_poi_fixture_id({**fixture, "sha256": "b" * 64})

    assert original.startswith("v2:")
    assert len({original, revised, changed_content}) == 3


def test_fixture_identity_rejects_a_spoofed_recorded_id():
    fixture = {
        "name": "same.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "fixtures/same.docx",
        "source_revision": "1" * 40,
        "sha256": "a" * 64,
        "fixture_id": "v2:" + "0" * 64,
    }

    with pytest.raises(ValueError, match="fixture_id"):
        apache_poi_fixture_id(fixture)


def test_fixture_index_rejects_a_recorded_id_without_content_digest(tmp_path):
    fixture = {
        "name": "same.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "fixtures/same.docx",
        "source_revision": "1" * 40,
        "fixture_id": "v2:" + "0" * 64,
    }
    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps([fixture]), encoding="utf-8")

    with pytest.raises(ValueError, match="sha256-backed"):
        load_fixture_index(fixture_index)


def test_legacy_manifest_does_not_hide_a_new_immutable_revision(tmp_path):
    manifest_path = tmp_path / "legacy.json"
    manifest_path.write_text(
        json.dumps({"version": 1, "used": {"docx": ["same.docx"]}, "probes": []}),
        encoding="utf-8",
    )
    candidate = {
        "name": "same.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "same.docx",
        "source_revision": "1" * 40,
    }

    manifest = load_apache_poi_probe_manifest(manifest_path)
    selected = select_unseen_apache_poi_fixtures(
        [candidate], ["docx"], per_format=1, manifest=manifest
    )

    assert manifest["version"] == APACHE_POI_PROBE_MANIFEST_VERSION
    assert manifest["legacy_used"] == {"docx": ["same.docx"]}
    assert selected == [candidate]


def test_v2_manifest_reprobes_once_to_migrate_to_content_and_source_identity(
    tmp_path,
):
    manifest_path = tmp_path / "v2.json"
    candidate = {
        "name": "same.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "fixtures/same.docx",
        "source_revision": "1" * 40,
    }
    old_pre_download_id = apache_poi_fixture_id(candidate)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "used": {"docx": [old_pre_download_id]},
                "legacy_used": {},
                "probes": [],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_apache_poi_probe_manifest(manifest_path)

    assert manifest["version"] == APACHE_POI_PROBE_MANIFEST_VERSION
    assert manifest["used"] == {}
    assert manifest["used_sources"] == {}
    assert manifest["legacy_used"] == {"docx": [old_pre_download_id]}
    assert select_unseen_apache_poi_fixtures(
        [candidate], ["docx"], per_format=1, manifest=manifest
    ) == [candidate]


@pytest.mark.parametrize("version", [0, APACHE_POI_PROBE_MANIFEST_VERSION + 1])
def test_probe_manifest_rejects_unsupported_versions(tmp_path, version):
    manifest_path = tmp_path / "unsupported.json"
    manifest_path.write_text(
        json.dumps({"version": version, "used": {}, "probes": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="version"):
        load_apache_poi_probe_manifest(manifest_path)


@pytest.mark.parametrize("version", [True, False, 1.0, "1"])
def test_probe_manifest_rejects_non_integer_version_types(tmp_path, version):
    manifest_path = tmp_path / "invalid-version.json"
    manifest_path.write_text(
        json.dumps({"version": version, "used": {}, "probes": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="version must be an integer"):
        load_apache_poi_probe_manifest(manifest_path)


@pytest.mark.parametrize("probes", [{}, "probe", ["probe"], [None]])
def test_probe_manifest_rejects_malformed_probe_lists(tmp_path, probes):
    manifest_path = tmp_path / "invalid-probes.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": APACHE_POI_PROBE_MANIFEST_VERSION,
                "used": {},
                "probes": probes,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="probes"):
        load_apache_poi_probe_manifest(manifest_path)


def test_successful_content_identity_uses_source_key_to_skip_only_same_revision(
    tmp_path,
):
    manifest_path = tmp_path / "probe.json"
    candidate = {
        "name": "same.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "fixtures/same.docx",
        "source_revision": "1" * 40,
    }
    record = {
        **candidate,
        "identity_sha256": "a" * 64,
        "sha256": "a" * 64,
        "path": "docx/same.docx",
    }
    record["fixture_id"] = apache_poi_fixture_id(record)

    manifest = record_probe_outcome(
        manifest_path,
        [record],
        "complete",
        successful_records=[record],
    )

    assert manifest["used"] == {"docx": [record["fixture_id"]]}
    assert manifest["used_sources"] == {
        "docx": [apache_poi_fixture_source_id(candidate)]
    }
    assert select_unseen_apache_poi_fixtures(
        [candidate], ["docx"], per_format=1, manifest=manifest
    ) == []
    revised = {**candidate, "source_revision": "2" * 40}
    assert select_unseen_apache_poi_fixtures(
        [revised], ["docx"], per_format=1, manifest=manifest
    ) == [revised]


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
    assert reloaded["version"] == APACHE_POI_PROBE_MANIFEST_VERSION
    assert reloaded["used"] == {
        "docx": sorted(apache_poi_fixture_id(record) for record in first_records[:1] + second_records),
        "xlsx": [apache_poi_fixture_id(first_records[1])],
    }
    assert [probe["name"] for probe in reloaded["probes"]] == ["probe-1", "probe-2"]
    assert reloaded["probes"][0]["files"] == [
        {
            "format": "docx",
            "id": apache_poi_fixture_id(first_records[0]),
            "path": "docx/first.docx",
            "status": "success",
        },
        {
            "format": "xlsx",
            "id": apache_poi_fixture_id(first_records[1]),
            "path": "",
            "status": "success",
        },
    ]


def test_record_probe_outcome_records_all_files_but_retries_failed_and_invalid(tmp_path):
    manifest_path = tmp_path / "probe.json"
    records = [
        {
            "format": "docx",
            "name": "good.docx",
            "source": "owner/repo",
            "source_name": "good.docx",
            "source_revision": "1" * 40,
            "sha256": "a" * 64,
            "path": "docx/good.docx",
        },
        {
            "format": "docx",
            "name": "failed.docx",
            "source": "owner/repo",
            "source_name": "failed.docx",
            "source_revision": "1" * 40,
            "sha256": "b" * 64,
            "path": "docx/failed.docx",
        },
        {
            "format": "docx",
            "name": "invalid.docx",
            "source": "owner/repo",
            "source_name": "invalid.docx",
            "source_revision": "1" * 40,
            "sha256": "c" * 64,
            "path": "docx/invalid.docx",
        },
    ]

    manifest = record_probe_outcome(
        manifest_path,
        records,
        "mixed",
        successful_records=[records[0]],
        invalid=[{"path": records[2]["path"], "error": "bad ZIP"}],
        failure_reasons=["invalid OOXML archives: 1", "benchmark failed"],
    )

    assert manifest["used"] == {"docx": [apache_poi_fixture_id(records[0])]}
    assert [item["status"] for item in manifest["probes"][-1]["files"]] == [
        "failed",
        "success",
        "invalid",
    ]
    assert manifest["probes"][-1]["failure_reasons"] == [
        "invalid OOXML archives: 1",
        "benchmark failed",
    ]


def test_load_fixture_index_accepts_top_level_list_and_fixtures_object(tmp_path):
    list_path = tmp_path / "fixtures-list.json"
    object_path = tmp_path / "fixtures-object.json"
    list_path.write_text(json.dumps([{"name": "a.docx", "format": "docx"}]), encoding="utf-8")
    object_path.write_text(json.dumps({"fixtures": [{"name": "b.xlsx", "format": "xlsx"}]}), encoding="utf-8")

    assert load_fixture_index(list_path) == [{"name": "a.docx", "format": "docx"}]
    assert load_fixture_index(object_path) == [{"name": "b.xlsx", "format": "xlsx"}]


@pytest.mark.parametrize(
    "fixture",
    [
        {"name": "unsupported.pdf", "format": "pdf"},
        {"name": "", "format": "docx"},
        {"name": "/tmp/absolute.docx", "format": "docx"},
        {"name": "../traversal.docx", "format": "docx"},
        {"name": "nested/fixture.docx", "format": "docx"},
        {"name": r"nested\fixture.docx", "format": "docx"},
    ],
    ids=["format", "empty", "absolute", "parent", "slash", "backslash"],
)
def test_load_fixture_index_rejects_unsafe_fixture_identity(tmp_path, fixture):
    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps([fixture]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_fixture_index(fixture_index)


@pytest.mark.parametrize(
    "url",
    [
        "https://raw.githubusercontent.com/owner/repo/"
        + "1" * 40
        + "/fixtures/other.docx",
        "https://raw.githubusercontent.com/owner/repo/"
        + "1" * 40
        + "/fixtures/sample.docx/extra",
        "https://raw.githubusercontent.com/owner/repo/"
        + "1" * 40
        + "/fixtures/sample.docx?download=1",
        "https://raw.githubusercontent.com/owner/repo/"
        + "1" * 40
        + "/fixtures/sample.docx#fragment",
    ],
    ids=["different-name", "extra-suffix", "query", "fragment"],
)
def test_load_fixture_index_requires_exact_raw_github_source_path(tmp_path, url):
    fixture = {
        "name": "sample.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "fixtures/sample.docx",
        "source_revision": "1" * 40,
        "url": url,
    }
    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps([fixture]), encoding="utf-8")

    with pytest.raises(ValueError, match="URL"):
        load_fixture_index(fixture_index)


def test_load_fixture_index_accepts_percent_encoded_exact_raw_github_path(tmp_path):
    fixture = {
        "name": "sample.docx",
        "format": "docx",
        "source": "owner/repo",
        "source_name": "test files/sample fixture.docx",
        "source_revision": "1" * 40,
        "url": (
            "https://raw.githubusercontent.com/owner/repo/"
            + "1" * 40
            + "/test%20files/sample%20fixture.docx"
        ),
    }
    fixture_index = tmp_path / "fixtures.json"
    fixture_index.write_text(json.dumps([fixture]), encoding="utf-8")

    assert load_fixture_index(fixture_index) == [fixture]


def test_download_fixture_rejects_symlink_escape_before_network(tmp_path, monkeypatch):
    output_dir = tmp_path / "corpus"
    outside_dir = tmp_path / "outside"
    output_dir.mkdir()
    outside_dir.mkdir()
    (output_dir / "docx").symlink_to(outside_dir, target_is_directory=True)
    network_calls = []

    def unexpected_network_call(*args, **kwargs):
        network_calls.append((args, kwargs))
        raise AssertionError("network must not be contacted for an escaping destination")

    monkeypatch.setattr(corpus_script.urllib.request, "urlopen", unexpected_network_call)
    monkeypatch.setattr(corpus_script.urllib.request, "urlretrieve", unexpected_network_call)

    with pytest.raises(ValueError, match="outside output directory"):
        corpus_script.download_fixture(
            {
                "name": "escape.docx",
                "format": "docx",
                "url": "https://example.test/escape.docx",
            },
            output_dir,
        )

    assert network_calls == []
    assert list(outside_dir.iterdir()) == []


def test_download_fixture_rejects_format_directory_swap_during_download(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "corpus"
    format_dir = output_dir / "docx"
    displaced_dir = output_dir / "docx-original"
    outside_dir = tmp_path / "outside"
    format_dir.mkdir(parents=True)
    outside_dir.mkdir()
    sentinel = outside_dir / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    def swapping_urlopen(url, timeout):
        format_dir.rename(displaced_dir)
        format_dir.symlink_to(outside_dir, target_is_directory=True)
        return io.BytesIO(b"downloaded fixture bytes")

    monkeypatch.setattr(
        corpus_script.urllib.request,
        "urlopen",
        swapping_urlopen,
    )

    with pytest.raises(OSError, match="directory changed"):
        corpus_script.download_fixture(
            {
                "name": "swapped.docx",
                "format": "docx",
                "url": "https://example.test/swapped.docx",
            },
            output_dir,
        )

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert not (outside_dir / "swapped.docx").exists()
    assert not (displaced_dir / "swapped.docx").exists()
    assert not list(displaced_dir.glob("*.part"))


def test_download_fixture_streams_with_timeout_and_records_actual_integrity(tmp_path, monkeypatch):
    payload = b"downloaded fixture bytes"
    calls = []

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(payload)

    def forbidden_urlretrieve(*args, **kwargs):
        raise AssertionError("urlretrieve must not be used")

    monkeypatch.setattr(corpus_script.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(corpus_script.urllib.request, "urlretrieve", forbidden_urlretrieve)
    fixture = {
        "name": "sample.docx",
        "format": "docx",
        "url": "https://example.test/sample.docx",
        "source": "owner/repo",
        "source_name": "fixtures/sample.docx",
        "source_revision": "1" * 40,
    }

    record = corpus_script.download_fixture(
        fixture,
        tmp_path / "corpus",
        timeout=1.5,
        max_download_bytes=1024,
    )

    destination = tmp_path / "corpus" / "docx" / "sample.docx"
    assert destination.read_bytes() == payload
    assert calls == [(fixture["url"], 1.5)]
    assert record["bytes"] == len(payload)
    assert record["sha256"] == hashlib.sha256(payload).hexdigest()
    assert record["identity_sha256"] == record["sha256"]
    assert record["fixture_id"] == apache_poi_fixture_id(record)
    assert record["fixture_id"] != apache_poi_fixture_id(fixture)
    assert [path.name for path in destination.parent.iterdir()] == [destination.name]


def test_download_fixture_rejects_supplied_id_that_differs_from_actual_content(
    tmp_path,
    monkeypatch,
):
    payload = b"downloaded fixture bytes"
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    fixture = {
        "name": "sample.docx",
        "format": "docx",
        "url": "https://example.test/sample.docx",
        "source": "owner/repo",
        "source_name": "fixtures/sample.docx",
        "source_revision": "1" * 40,
        "sha256": actual_sha256,
        "identity_sha256": "0" * 64,
    }
    fixture["fixture_id"] = apache_poi_fixture_id(fixture)
    monkeypatch.setattr(
        corpus_script.urllib.request,
        "urlopen",
        lambda url, timeout: io.BytesIO(payload),
    )
    output_dir = tmp_path / "corpus"

    with pytest.raises(ValueError, match="downloaded content identity"):
        corpus_script.download_fixture(fixture, output_dir)

    assert list((output_dir / "docx").iterdir()) == []


def test_download_fixture_enforces_maximum_bytes_and_removes_temporary_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        corpus_script.urllib.request,
        "urlopen",
        lambda url, timeout: io.BytesIO(b"too large"),
    )
    output_dir = tmp_path / "corpus"

    with pytest.raises(ValueError, match="maximum download size"):
        corpus_script.download_fixture(
            {
                "name": "oversized.pptx",
                "format": "pptx",
                "url": "https://example.test/oversized.pptx",
            },
            output_dir,
            max_download_bytes=4,
        )

    destination_dir = output_dir / "pptx"
    assert not (destination_dir / "oversized.pptx").exists()
    assert list(destination_dir.iterdir()) == []


def test_download_fixture_enforces_absolute_wall_clock_deadline_and_cleans_temp(
    tmp_path, monkeypatch
):
    class SlowDrip:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read1(self, _size):
            return b"x"

    ticks = iter([0.0, 0.1, 0.6, 1.1])
    monkeypatch.setattr(corpus_script.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        corpus_script.urllib.request,
        "urlopen",
        lambda url, timeout: SlowDrip(),
    )
    output_dir = tmp_path / "corpus"

    with pytest.raises(TimeoutError, match="wall clock"):
        corpus_script.download_fixture(
            {
                "name": "slow.docx",
                "format": "docx",
                "url": "https://example.test/slow.docx",
            },
            output_dir,
            timeout=1.0,
        )

    assert list((output_dir / "docx").iterdir()) == []


@pytest.mark.parametrize(
    "expected",
    [
        {"sha256": "0" * 64},
        {"bytes": 1},
    ],
    ids=["sha256", "bytes"],
)
def test_download_fixture_rejects_integrity_mismatch_without_destination(
    tmp_path,
    monkeypatch,
    expected,
):
    payload = b"actual fixture"
    monkeypatch.setattr(
        corpus_script.urllib.request,
        "urlopen",
        lambda url, timeout: io.BytesIO(payload),
    )
    fixture = {
        "name": "mismatch.xlsx",
        "format": "xlsx",
        "url": "https://example.test/mismatch.xlsx",
    }
    fixture.update(expected)
    output_dir = tmp_path / "corpus"

    with pytest.raises(ValueError, match="does not match"):
        corpus_script.download_fixture(fixture, output_dir)

    destination_dir = output_dir / "xlsx"
    assert not (destination_dir / "mismatch.xlsx").exists()
    assert list(destination_dir.iterdir()) == []


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
        "docx": [apache_poi_fixture_id(fixtures[0])],
        "xlsx": [apache_poi_fixture_id(fixtures[2])],
    }
    assert [probe["name"] for probe in manifest["probes"]] == ["already-used"]
    assert sorted((tmp_path / "corpus").rglob("*.*"))


def test_atomic_write_text_refuses_a_symlink_destination(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("unchanged", encoding="utf-8")
    destination = tmp_path / "report.json"
    destination.symlink_to(outside)

    with pytest.raises(OSError, match="regular file"):
        atomic_write_text(destination, "replacement")

    assert outside.read_text(encoding="utf-8") == "unchanged"


def test_atomic_write_text_detects_parent_swap_and_removes_displaced_output(
    tmp_path, monkeypatch
):
    parent = tmp_path / "reports"
    displaced = tmp_path / "reports-original"
    outside = tmp_path / "outside"
    parent.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    real_replace = corpus_script.os.replace

    def swapping_replace(source, destination, *, src_dir_fd, dst_dir_fd):
        parent.rename(displaced)
        parent.symlink_to(outside, target_is_directory=True)
        return real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(corpus_script.os, "replace", swapping_replace)

    with pytest.raises(OSError, match="directory changed"):
        atomic_write_text(parent / "report.json", "replacement")

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert not (outside / "report.json").exists()
    assert not (displaced / "report.json").exists()
    assert list(displaced.iterdir()) == []
