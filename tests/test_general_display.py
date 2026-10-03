"""General 표시와 텍스트 구역을 두 리더의 실제 셀 경로에서 검사한다."""
import struct

import pytest

from dochan.office_binary.xls import (_RichString, _display_number_with_format,
                                       _display_text_with_format, parse_biff_workbook)
from dochan.ooxml.xlsx import XLSXReader
from dochan.spreadsheet_format import SpreadsheetNumberFormatter
from test_xls_reader import _bof, _boundsheet, _eof, _format_record, _xf, _record, _sst
from test_xlsx_reader import _write_xlsx


@pytest.mark.parametrize("raw,expected", [
    ("0.30000000000000004", "0.3"),
    ("0.7999999999999999", "0.8"),
    ("12345678901234567168", "1.23456789012346E+19"),
    ("123456789012", "123456789012"),
    ("0.125", "0.125"),
    ("1.123e-10", "1.123E-10"),
    ("0.0000000001123", "1.123E-10"),
    ("0.000000001", "0.000000001"),
])
def test_general_uses_fifteen_significant_digits(raw, expected):
    formatter = SpreadsheetNumberFormatter()
    assert formatter._format_cell_value(raw, "General") == expected
    assert XLSXReader()._format_cell_value(raw, "") == expected
    assert _display_number_with_format(float(raw), "General") == expected


@pytest.mark.parametrize("raw,fmt,expected", [
    ("jello", ';;;"hi"', "hi"),
    ("jello", ";;;-@-", "-jello-"),
    ("jello", '"Mr. "@', "Mr. jello"),
    ("TRUE", ";;;-@-", "-TRUE-"),
    ("FALSE", "General", "FALSE"),
])
def test_text_section_rendering(raw, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_text_cell_value(raw, fmt) == expected


@pytest.mark.parametrize("fmt", ['"x@', ';;;"x@', ';;;[Red"x@', ';;;[Red]"x@'])
def test_malformed_text_section_preserves_original(fmt):
    assert SpreadsheetNumberFormatter()._format_text_cell_value("Payroll total", fmt) == "Payroll total"


@pytest.mark.parametrize("fmt,expected", [
    ('_(@_)', 'abc'),
    (';;;_(@_)', 'abc'),
    (';;;" "@" "', ' abc '),
    (';;;', 'abc'),
    (';;;"hi"', 'hi'),
])
def test_text_section_padding_and_empty_fallback(fmt, expected):
    assert SpreadsheetNumberFormatter()._format_text_cell_value("abc", fmt) == expected


def test_text_section_output_limit_preserves_original_and_warns():
    formatter = XLSXReader()
    formatter._errors = []
    value = "a" * 32767
    assert formatter._format_text_cell_value(value, "@" * 100) == value
    assert any("text format" in error for error in formatter._errors)


@pytest.mark.parametrize("raw,expected", [
    ("1E+20", "1E+20"),
    ("1.234567890123456E+19", "1.23456789012346E+19"),
    ("4.0947118061319582E+231", "4.09471180613196E+231"),
    ("1E+15", "1E+15"),
    ("1E-10", "1E-10"),
    ("1.234567890123456E-20", "1.23456789012346E-20"),
    ("1E-9", "0.000000001"),
    ("-0", "0"),
    ("007", "7"),
])
def test_general_scientific_boundaries_and_lexical_numbers(raw, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(raw, "General") == expected


@pytest.mark.parametrize("fmt,expected", [("0@", "1235@"), ("@0", "@1235")])
def test_numeric_section_with_text_placeholder_keeps_previous_display(fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value("1234.5", fmt) == expected


def test_unchanged_text_section_preserves_rich_string_runs():
    original = _RichString("abc", [(0, 1)], False)
    assert _display_text_with_format(original, "@") is original
    assert original.format_runs == [(0, 1)]


def test_xlsx_reader_applies_general_and_text_section_to_real_cells(tmp_path):
    path = tmp_path / "cells.xlsx"
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    workbook = (f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"><sheets><sheet name="Sheet1" '
                'sheetId="1" r:id="rId1"/></sheets></workbook>')
    styles = (f'<styleSheet xmlns="{ns}"><numFmts count="2">'
              '<numFmt numFmtId="164" formatCode=";;;-@-"/>'
              '<numFmt numFmtId="165" formatCode="&quot;Mr. &quot;@"/>'
              '</numFmts><cellXfs count="3"><xf numFmtId="0"/>'
              '<xf numFmtId="164"/><xf numFmtId="165"/></cellXfs></styleSheet>')
    shared = f'<sst xmlns="{ns}"><si><t>jello</t></si></sst>'
    sheet = (f'<worksheet xmlns="{ns}"><sheetData><row r="1">'
             '<c r="A1"><v>0.30000000000000004</v></c>'
             '<c r="B1" s="1" t="s"><v>0</v></c>'
             '<c r="C1" s="1" t="b"><v>1</v></c>'
             '<c r="D1" s="2" t="inlineStr"><is><t>Smith</t></is></c>'
             '</row></sheetData></worksheet>')
    _write_xlsx(path, workbook, {"xl/worksheets/sheet1.xml": sheet},
                shared_strings_xml=shared, styles_xml=styles)
    doc = XLSXReader().read(str(path))
    assert [cell.text for cell in doc.find_all("table")[0].rows[0]] == [
        "0.3", "-jello-", "-TRUE-", "Mr. Smith"]


def test_xlsx_reader_preserves_malformed_and_bounded_shared_text(tmp_path):
    path = tmp_path / "text.xlsx"
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    workbook = (f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"><sheets><sheet name="Sheet1" '
                'sheetId="1" r:id="rId1"/></sheets></workbook>')
    styles = (f'<styleSheet xmlns="{ns}"><numFmts count="3">'
              '<numFmt numFmtId="164" formatCode="&quot;x@"/>'
              '<numFmt numFmtId="165" formatCode=";;;"/>'
              f'<numFmt numFmtId="166" formatCode="{"@" * 100}"/>'
              '</numFmts><cellXfs count="4"><xf numFmtId="0"/>'
              '<xf numFmtId="164"/><xf numFmtId="165"/>'
              '<xf numFmtId="166"/></cellXfs></styleSheet>')
    shared = f'<sst xmlns="{ns}"><si><t>Payroll total</t></si><si><t>{"A" * 40000}</t></si></sst>'
    sheet = (f'<worksheet xmlns="{ns}"><sheetData><row r="1">'
             '<c r="A1" s="1" t="s"><v>0</v></c>'
             '<c r="B1" s="2" t="s"><v>0</v></c>'
             '<c r="C1" s="3" t="s"><v>1</v></c>'
             '<c r="D1" s="3" t="s"><v>1</v></c>'
             '</row></sheetData></worksheet>')
    _write_xlsx(path, workbook, {"xl/worksheets/sheet1.xml": sheet},
                shared_strings_xml=shared, styles_xml=styles)
    doc = XLSXReader().read(str(path))
    assert [cell.text for cell in doc.find_all("table")[0].rows[0]] == [
        "Payroll total", "Payroll total", "A" * 40000, "A" * 40000]
    assert sum("text format exceeds" in error for error in doc.errors) == 1


def test_xlsx_general_lexical_numbers_in_reader(tmp_path):
    path = tmp_path / "lexical.xlsx"
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    workbook = (f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"><sheets><sheet name="Sheet1" '
                'sheetId="1" r:id="rId1"/></sheets></workbook>')
    sheet = (f'<worksheet xmlns="{ns}"><sheetData><row r="1">'
             '<c r="A1"><v>1E+20</v></c><c r="B1"><v>-0</v></c>'
             '<c r="C1"><v>007</v></c></row></sheetData></worksheet>')
    _write_xlsx(path, workbook, {"xl/worksheets/sheet1.xml": sheet})
    doc = XLSXReader().read(str(path))
    assert [cell.text for cell in doc.find_all("table")[0].rows[0]] == [
        "1E+20", "0", "7"]


def test_xls_reader_applies_general_and_text_section_to_real_cells():
    globals_part = (_bof() + _format_record(200, ";;;-@-") + _xf(0) + _xf(200)
                    + _sst(["jello"]))
    sheet = (_bof()
             + _record(0x0203, struct.pack("<HHHd", 0, 0, 0, 0.30000000000000004))
             + _record(0x00FD, struct.pack("<HHHI", 0, 1, 1, 0))
             + _record(0x0205, struct.pack("<HHHBB", 0, 2, 1, 1, 0))
             + _eof())
    offset = len(globals_part) + len(_boundsheet(0, "Sheet1"))
    doc = parse_biff_workbook(globals_part + _boundsheet(offset, "Sheet1") + sheet)
    assert [cell.text for cell in doc.find_all("table")[0].rows[0]] == [
        "0.3", "-jello-", "-TRUE-"]


def test_xls_reader_preserves_malformed_empty_and_padded_text_sections():
    globals_part = (_bof() + _format_record(200, '"x@') + _format_record(201, ';;;')
                    + _format_record(202, '_(@_)') + _xf(0) + _xf(200)
                    + _xf(201) + _xf(202) + _sst(["Payroll total"]))
    sheet = (_bof()
             + _record(0x00FD, struct.pack("<HHHI", 0, 0, 1, 0))
             + _record(0x00FD, struct.pack("<HHHI", 0, 1, 2, 0))
             + _record(0x00FD, struct.pack("<HHHI", 0, 2, 3, 0))
             + _record(0x0205, struct.pack("<HHHBB", 0, 3, 2, 1, 0))
             + _eof())
    offset = len(globals_part) + len(_boundsheet(0, "Sheet1"))
    doc = parse_biff_workbook(globals_part + _boundsheet(offset, "Sheet1") + sheet)
    assert [cell.text for cell in doc.find_all("table")[0].rows[0]] == [
        "Payroll total", "Payroll total", "Payroll total", "TRUE"]
