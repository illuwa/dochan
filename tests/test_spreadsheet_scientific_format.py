"""Excel TEXT() 캐시에서 확인한 과학 표기 표시 계약."""

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("value, fmt, expected", [
    ("123456.789", "|#|e-|#|", "|1|e|5|"),
    ("123456.789", "|#.#|e+|#|", "|1.2|e|+5|"),
    ("123456.789", "|####.####|e-|#|", "|12.3457|e|4|"),
    ("123456.789", "|#,######.####|e-|#|", "|123,456.789|e|0|"),
    ("123456.789", "|0000.0000|e-|0|", "|0012.3457|e|4|"),
    ("123456.789", "|????.????|e-|?|", "|  12.3457|e|4|"),
    ("1.23456789E-5", "|0000000.0000|e-|0|", "|0000123.4568|e|-7|"),
    ("1.2345678000000001E+142", "|#.#|e+|????|", "|1.2|e|+ 142|"),
    ("0", "|#.#|e+|#|", "|0.|e|+0|"),
    ("123456.789", "|#%e-#|", "|1%e5|"),
    ("123456.789", "|#e+#%|", "|1e+5%|"),
    ("0", "|####.####|e-|#|", "|0000.|e|0|"),
    ("0", "|?,??????.????|e+|?|", "|0,000,000.    |e|+0|"),
    ("1.23456789E-5", "|?,??????.????|e-|?|", "|      123.4568|e|-7|"),
])
def test_excel_text_cache_scientific_sections(value, fmt, expected):
    """NumberFormatApproxTests.xlsx A6, A26, A8, A10, A13, A18, A54, A226, A228, A4, A24, A104, A135, A60의 TEXT 캐시."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("123456.789", "#E+#", "1E+5"),
    ("123456.789", "0E+0", "1E+5"),
    ("123456.789", "0E-0", "1E5"),
])
def test_scientific_integer_mantissa_and_exponent_slots(value, fmt, expected):
    """NumberFormatApproxTests.xlsx A21, A30, A11에서 파생한 자리 규칙 사례."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt", [
    ("1234", '"x0.00E+00'),
    ("1234", '0E+"0'),
    ("-1234", '0.0E+0;"0E+0'),
])
def test_unterminated_scientific_quote_falls_back_to_raw_value(value, fmt):
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == value


def test_scientific_marker_scans_long_literal_linearly():
    from time import perf_counter

    formatter = SpreadsheetNumberFormatter()
    short = "E+" * 20000 + "0"
    long = "E+" * 40000 + "0"
    start = perf_counter()
    assert formatter._scientific_marker(short) is None
    short_time = perf_counter() - start
    start = perf_counter()
    assert formatter._scientific_marker(long) is None
    long_time = perf_counter() - start
    assert long_time < max(short_time * 3.5, 0.5)


@pytest.mark.parametrize("value, fmt, expected", [
    ("0", "##0.0E+0", "0.0E+0"),
    ("0", "0.0E+0", "0.0E+0"),
    ("123", "#,##?E+0", "123E+0"),
    ("1000", "0E+??0", "1E+  3"),
    ("1234", "$0.00E+00", "$1.23E+03"),
    ("1234", "[$€-2] 0.00E+00", "€ 1.23E+03"),
    ("12345", "000-0000E+0", "001-2345E+0"),
])
def test_scientific_mixed_slots_and_currency(value, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected
