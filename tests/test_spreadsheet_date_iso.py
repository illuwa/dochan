"""Public Excel TEXT() cache cases for the shared XLS/XLSX formatter."""

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("cell,raw,fmt,expected", [
    ("A21", "36191.170208437499", "d-m-y", "2003-02-01"),
    ("A25", "36191.170208437499", "D-M-Y", "2003-02-01"),
    ("A31", "36191.170208437499", "h:m:s.00 A/P", "04:05:06.01"),
    ("A32", "36191.170208437499", "hh:mm:ss.000 am/pm", "04:05:06.009"),
    ("A33", "36191.170208437499", "d-m-y h:m:s", "2003-02-01 04:05:06"),
    ("A36", "36191.170208437499", "H:M:S.00 a/p", "04:05:06.01"),
    ("A43", "17816.607951388887", r"d \d\a\y\s h", "11 days 14"),
    ("A44", "17816.607951388887", 'd "days" h', "11 days 14"),
    ("A45", "17816.607951388887", r"d \d\a\y\s h a/p", "11 days 2 p"),
    ("A46", "17816.607951388887", 'd "days" h am/pm', "11 days 2 PM"),
])
def test_date_format_tests_xlsx_cache_components(cell, raw, fmt, expected):
    formatter = SpreadsheetNumberFormatter()
    formatter._date_1904 = True
    assert formatter._format_cell_value(raw, fmt) == expected, cell


@pytest.mark.parametrize("cell,raw,fmt,expected", [
    ("A10", "3.1415899999999999", '"It was "[h]" [yes, "h"] hours and "mm:ss',
     "It was 75 [yes, 75] hours and 23:53"),
    ("A11", "3.1415899999999999", '[s]" [yes, "ss"] seconds"',
     "271433 [yes, 271433] seconds"),
    ("A30", "0", '"It was "[h]" [yes, "h"] hours and "mm:ss',
     "It was 0 [yes, 0] hours and 00:00"),
    ("A31", "0", '[s]" [yes, "ss"] seconds"', "0 [yes, 00] seconds"),
    ("A40", "-8.5462962962962963E-2", '"It was "[h]" [yes, "h"] hours and "mm:ss',
     "-It was 2 [yes, 2] hours and 03:04"),
])
def test_elapsed_format_tests_xlsx_cache(cell, raw, fmt, expected):
    formatter = SpreadsheetNumberFormatter()
    formatter._date_1904 = True
    assert formatter._format_cell_value(raw, fmt) == expected, cell


@pytest.mark.parametrize("cell,raw,fmt,expected", [
    ("A100", "123.45", "0,0.00%", "12,345.00%"),
    ("A101", "123.45", "0,0.00%%", "1,234,500.00%%"),
    ("A103", "-123.45", "0,0.00%", "-12,345.00%"),
    ("A104", "-123.45", "0,0.00%%", "-1,234,500.00%%"),
])
def test_number_format_tests_xlsx_percent_grouping(cell, raw, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(raw, fmt) == expected, cell


def test_second_precision_and_unterminated_literal():
    formatter = SpreadsheetNumberFormatter()
    assert formatter._format_cell_value("0.5", "hh:mm:ss.000") == "12:00:00.000"
    assert isinstance(formatter._format_cell_value("0.5", 'd "unfinished h'), str)
