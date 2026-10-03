"""Excel 저장값과 규칙 추론을 구분해 XLS/XLSX 공용 서식을 검사한다."""
import struct

import pytest

from dochan.office_binary.xls import parse_biff_workbook
from dochan.spreadsheet_format import BUILTIN_NUM_FORMATS, SpreadsheetNumberFormatter
from test_xls_reader import _bof, _boundsheet, _eof, _styled_number, _xf


@pytest.mark.parametrize("value, fmt, expected", [
    ("1.159", "#\\ ?/2", "1"),
    ("-1.05", "#\\ ??/100", "-1 5/100"),
    ("0.83", "#\\ ?/10", "8/10"),
    ("1.15", "#\\ ?/10", "1 1/10"),
    ("5716.5", '"$"#,##0', "$5,717"),
    ("1.25", "0.0", "1.3"),
    ("0.615", "0.00", "0.62"),
    ("12.3", "$###.00", "$12.30"),
    ("-12.3", "$###.00", "-$12.30"),
    ("12.3", "#.00", "12.30"),
    ("1.5", "0", "2"),
    ("1.9", "0000", "0002"),
    ("10", '[< 10]#" Wow"', "10"),
    ("42272007011", r"0\-00000\-00000\-0", "0-42272-00701-1"),
    ("1234.5", "#,##0", "1,235"),
    ("5", ";;;", ""),
    ("1234.5", "0.00E+000", "1.23E+003"),
    ("-1234", '_(* #,##0_);_(* \\(#,##0\\);_(* "-"??_);_(@_)', " (1,234)"),
    ("1234.5", "[$€-2] #,##0.00", "€ 1,234.50"),
])
def test_excel_numeric_display_examples(value, fmt, expected):
    """K191·K223·L3, NumberFormat A10·A15, FormatChoice A24는 저장값이다.

    나머지 사례의 기대는 서식 규칙에서 추론했다.
    """
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("index, value, expected", [
    (3, 1234.5, "1,235"),
    (4, 1234.5, "1,234.50"),
    (37, -1234.5, "(1,235)"),
    (38, -1234.5, "(1,235)"),
    (39, -1234.5, "(1,234.50)"),
    (40, -1234.5, "(1,234.50)"),
    (45, 0.5, "00:00"),
    (46, 1.5, "36:00:00"),
    (47, 0.5, "0000.0"),
    (48, 1234.5, "1.2E+3"),
    (49, 1234.5, "1234.5"),
])
def test_xls_builtin_format_from_xf(index, value, expected):
    globals_part = _bof() + _xf(index)
    worksheet = _bof() + _styled_number(0, 0, 0, value) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Builtin"))
    doc = parse_biff_workbook(globals_part + _boundsheet(offset, "Builtin") + worksheet)
    assert doc.sections[0].elements[0].rows[0][0].text == expected


def test_biff5_format_uses_byte_length_and_codepage():
    format_record = struct.pack("<HH", 0x041E, 2 + 1 + 5) + struct.pack("<H", 200) + b"\x05" + b"0.00%"
    legacy_bof = struct.pack("<HHH", 0x0809, 8, 0x0500) + b"\x00" * 6
    globals_part = legacy_bof + format_record + _xf(200)
    worksheet = _bof() + _styled_number(0, 0, 0, 1.55) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Legacy"))
    doc = parse_biff_workbook(globals_part + _boundsheet(offset, "Legacy") + worksheet)
    assert doc.sections[0].elements[0].rows[0][0].text == "155.00%"


def test_xls_formatter_warning_sink_is_connected():
    globals_part = _bof() + _xf(1)
    worksheet = _bof() + _styled_number(0, 0, 0, float("inf")) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Warnings"))
    doc = parse_biff_workbook(globals_part + _boundsheet(offset, "Warnings") + worksheet)
    assert any("formatted numeric value is out of range" in error for error in doc.errors)


def test_builtin_mapping_contains_reviewed_indexes():
    assert all(index in BUILTIN_NUM_FORMATS for index in (3, 4, 37, 38, 39, 40, 45, 46, 47, 48, 49))
