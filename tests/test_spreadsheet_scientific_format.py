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
    """NumberFormatApproxTests.xlsx A21, A30, A11의 동일 수치와 지수 자리 규칙."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected
