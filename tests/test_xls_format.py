"""XLS 숫자 셀은 XLSX와 같은 표시 서식을 사용한다."""
import struct

from dochan.office_binary.xls import _decode_formula_cached_result, parse_biff_workbook
from dochan.ooxml.xlsx import XLSXReader
from test_xls_reader import _bof, _boundsheet, _eof, _format_record, _styled_number, _xf


def _formatted_workbook(cases, date_1904=False):
    globals_part = _bof() + (b"\x22\x00\x02\x00" + struct.pack("<H", 1) if date_1904 else b"")
    for index, (fmt, _) in enumerate(cases, 200):
        globals_part += _format_record(index, fmt)
    globals_part += _xf(0)
    for index in range(len(cases)):
        globals_part += _xf(200 + index)
    worksheet = _bof()
    for index, (_, value) in enumerate(cases):
        worksheet += _styled_number(index, 0, index + 1, value)
    worksheet += _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Formats"))
    return globals_part + _boundsheet(offset, "Formats") + worksheet


def test_xls_format_records_use_xlsx_numeric_display_rules():
    cases = [
        ("0.0%", 0.164),
        ("0%", 0.125),
        ("[$-412]#,##0.00", 1234.5),
        ("yyyy-mm-dd hh:mm:ss", 45292.5),
        ("[h]:mm:ss", 1.5),
    ]
    doc = parse_biff_workbook(_formatted_workbook(cases))
    actual = [row[0].text for row in doc.sections[0].elements[0].rows]
    formatter = XLSXReader()
    expected = [formatter._format_cell_value(str(value), fmt) for fmt, value in cases]
    assert actual == expected


def test_xls_datemode_record_applies_to_datetime_cells():
    cases = [("yyyy-mm-dd hh:mm:ss", 1.5)]
    doc = parse_biff_workbook(_formatted_workbook(cases, date_1904=True))
    formatter = XLSXReader()
    formatter._date_1904 = True
    assert doc.sections[0].elements[0].rows[0][0].text == formatter._format_cell_value("1.5", cases[0][0])


def test_xls_builtin_xf_uses_shared_percent_format():
    globals_part = _bof() + _xf(10)
    worksheet = _bof() + _styled_number(0, 0, 0, 0.125) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Builtin"))
    doc = parse_biff_workbook(globals_part + _boundsheet(offset, "Builtin") + worksheet)
    assert doc.sections[0].elements[0].rows[0][0].text == "12.50%"


def test_xls_formula_numeric_cache_uses_datemode():
    record_data = struct.pack("<HHHd", 0, 0, 0, 1.5)
    assert _decode_formula_cached_result(record_data, "m/d/yy h:mm", True) == "1904-01-02 12:00"
