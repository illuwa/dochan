"""Public Excel TEXT() cache cases for the shared XLS/XLSX formatter."""

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter
from dochan.ooxml.charts import format_chart_number


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
    assert formatter._format_cell_value("0.5", 'd "unfinished h') == "0.5"


@pytest.mark.parametrize("fmt", [
    "Standard", "Estándar", "Padrão", "Ogólny", "Allmänt", "Yleinen",
    '0.00 "day', '#,##0 "pound', '[Red 0.00', '0.00 m',
    '0.0 dB', '#,##0.00 y',
])
def test_non_date_labels_are_not_classified_as_dates(fmt):
    formatter = SpreadsheetNumberFormatter()
    assert formatter._format_metadata(fmt).kind != "date"


@pytest.mark.parametrize("fmt,raw,expected", [
    ("d", "40735", "11"),
    ('m"月"d"日"', "40735", "7月11日"),
    ('d "days" h', "0.5", "0 days 12"),
    ('d "days" h', "60.25", "29 days 6"),
    ('d "days" h', "29.999999", "30 days 0"),
    ('d "days" h:mm', "40735.5", "11 days 12:00"),
    ('[Red]d "days" h', "40735.5", "11 days 12"),
    ('d "days" h a/p', "40735.5", "11 days 12 p"),
    ('d "days" h a/pm', "40735.5", "40735.5"),
    ('d "days" h am/p', "40735.5", "40735.5"),
])
def test_partial_date_tokens_and_excel_1900_edges(fmt, raw, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(raw, fmt) == expected


@pytest.mark.parametrize("fmt,raw,expected", [
    ('d "days" h', "0", "0 days 0"),
    ('d "days" h', "60", "29 days 0"),
    ("[H]:mm", "3.14159", "75:23"),
    ('[H]" [yes, "H"] hours"', "3.14159", "75 [yes, 75] hours"),
    ("dddd h", "45000.6", "2023-03-15 14:24"),
    ('ddd "at" h AM/PM', "45000.6", "2023-03-15 14:24"),
])
def test_elapsed_case_and_existing_named_date_contract(fmt, raw, expected):
    formatter = SpreadsheetNumberFormatter()
    formatter._errors = []
    assert formatter._format_cell_value(raw, fmt) == expected
    assert not formatter._errors


def test_chart_general_labels_and_out_of_range_clock():
    for label in ("Standard", "Estándar", "Padrão", "Ogólny", "Allmänt", "Yleinen"):
        assert format_chart_number("13", label) == "13"
    assert SpreadsheetNumberFormatter()._format_cell_value(
        "10000000", "hh:mm:ss.00 AM/PM") == "10000000"
    assert SpreadsheetNumberFormatter()._format_cell_value(
        "0.5", "h:mm a/pm") == "0.5"
