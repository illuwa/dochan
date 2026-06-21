import zipfile

import pytest

from dochan.ooxml.package import OOXMLPackage, detect_ooxml_format


def _write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_detects_docx_from_package_entries(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<w:document xmlns:w='w'/>"})

    assert detect_ooxml_format(str(path)) == "docx"


def test_detects_pptx_from_package_entries(tmp_path):
    path = tmp_path / "sample.pptx"
    _write_zip(path, {"ppt/presentation.xml": "<p:presentation xmlns:p='p'/>"})

    assert detect_ooxml_format(str(path)) == "pptx"


def test_detects_xlsx_from_package_entries(tmp_path):
    path = tmp_path / "sample.xlsx"
    _write_zip(path, {"xl/workbook.xml": "<workbook/>"})

    assert detect_ooxml_format(str(path)) == "xlsx"


def test_detects_xlsx_from_backslash_package_entries(tmp_path):
    path = tmp_path / "sample.xlsx"
    _write_zip(path, {"xl\\workbook.xml": "<workbook/>"})

    assert detect_ooxml_format(str(path)) == "xlsx"


def test_unknown_zip_returns_empty_format(tmp_path):
    path = tmp_path / "sample.zip"
    _write_zip(path, {"data/file.txt": "hello"})

    assert detect_ooxml_format(str(path)) == ""


def test_reads_xml_part_with_xxe_disabled(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<root><child>ok</child></root>"})

    with OOXMLPackage(str(path)) as package:
        root = package.read_xml_part("word/document.xml")

    assert root.tag == "root"
    assert root.find("child").text == "ok"


def test_reads_xml_part_with_dtd_entity_bomb_neutralized(tmp_path):
    path = tmp_path / "sample.xlsx"
    xml = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>Test &lol2; Spreadsheet &amp; data</t></si>
</sst>
"""
    _write_zip(path, {"xl/sharedStrings.xml": xml})

    with OOXMLPackage(str(path)) as package:
        root = package.read_xml_part("xl/sharedStrings.xml")

    text = root.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t").text
    assert text == "Test  Spreadsheet & data"


def test_reads_backslash_package_entries_by_normalized_part_name(tmp_path):
    path = tmp_path / "sample.xlsx"
    _write_zip(path, {"xl\\workbook.xml": "<root><child>ok</child></root>"})

    with OOXMLPackage(str(path)) as package:
        assert package.exists("xl/workbook.xml")
        root = package.read_xml_part("xl/workbook.xml")

    assert root.tag == "root"
    assert root.find("child").text == "ok"


def test_rejects_path_traversal_part_name(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<root/>"})

    with OOXMLPackage(str(path)) as package:
        with pytest.raises(ValueError, match="unsafe package path"):
            package.read_part("../evil.xml")


def test_rejects_mixed_separator_path_traversal_part_name(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<root/>"})

    with OOXMLPackage(str(path)) as package:
        with pytest.raises(ValueError, match="unsafe package path"):
            package.read_part("folder\\..\\evil.xml")
