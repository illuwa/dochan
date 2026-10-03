"""Third review regressions: Excel caches are distinct from inferred rules."""
import struct

import pytest

from dochan.office_binary.xls import _decode_formula_cached_result
from dochan.spreadsheet_format import SpreadsheetNumberFormatter
from scripts.probe_xls_fraction_excel import _load_before
from scripts.probe_spreadsheet_format_hashes import _kind


@pytest.mark.parametrize("value, fmt, expected", [
    ("-5", "General;-General", "-5"),
    ("-5", "0;[Red]-General", "-5"),
    ("5", "G/通用格式", "5"),
    ("-5", "0;[Red]", "-5"),
    ("5", '"TRUE";"TRUE";"FALSE"', "TRUE"),
    ("5", r"\#\r\e\c", "#rec"),
    ("5", '" Excellent"', " Excellent"),
])
def test_general_and_literal_only_sections(value, fmt, expected):
    """규칙 추론: General은 값 자리이고 인용되지 않은 문자는 리터럴이 아니다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("-1234.5", "#,##0;[Red]#,##0", "-1,235"),
    ("-0.125", "0.0%;[Red]0.0%", "-12.5%"),
    ("-1.25", "# ?/?;[Red]# ?/?", "-1 1/4"),
    ("-1234", "0.0E+00;[Red]0.0E+00", "-1.2E+03"),
])
def test_negative_color_section_preserves_sign(value, fmt, expected):
    """Markdown에 색이 없을 때 부호를 보존한다는 출력 계약이다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


def test_negative_accounting_section_keeps_alignment_space():
    """규칙 추론: _x의 선행 공백은 음수 구역에서도 유지한다."""
    fmt = '_("$"* \\(#,##0.00\\)'
    assert SpreadsheetNumberFormatter()._format_cell_value("-255924.375", "0;" + fmt) == " $(255,924.38)"


@pytest.mark.parametrize("value, fmt, expected", [
    ("1234567", "#,.#,", "1.2"),
    ("-1234567", "#,.#,", "-1.2"),
    ("123456.789", "|#,e-#|", "|1e5|"),
    ("123456.789", "|#%e-#|", "|1%e5|"),
])
def test_scaling_commas_and_scientific_sections(value, fmt, expected):
    """NumberFormatTests.xlsx A93·A97 및 NumberFormatApproxTests.xlsx A2·A4의 Excel 저장값."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("12.3", "£000.00", "£012.30"),
    ("1234567", "0,0000000", "01,234,567"),
    ("1234567", "0,00000000", "001,234,567"),
    ("1234567", "0,000000000", "0,001,234,567"),
    ("314159", "$000,000,000", "$000,314,159"),
])
def test_currency_and_grouping_keep_required_zeroes(value, fmt, expected):
    """Excel 저장값: NumberFormatTests A5·A67~A69·A335."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


def test_string_formula_cache_does_not_decode_as_nan():
    """합성 BIFF FORMULA의 결과 유형 0은 뒤따르는 STRING 레코드가 값을 담는다."""
    cached = bytes([0, 0, 0, 0, 0, 0, 0xff, 0xff])
    record = struct.pack("<HHH", 0, 0, 0) + cached
    formatter = SpreadsheetNumberFormatter()
    formatter._errors = []
    assert _decode_formula_cached_result(record, "0.00", formatter=formatter) == ""
    assert formatter._errors == []


def test_fraction_probe_loads_pre_shared_formatter_tree(tmp_path):
    """1.12.0처럼 공용 모듈이 없는 트리도 XLSX 서식기로 비교한다."""
    package = tmp_path / "dochan" / "ooxml"
    package.mkdir(parents=True)
    (tmp_path / "dochan" / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "xlsx.py").write_text(
        "class XLSXReader:\n"
        "    def _format_cell_value(self, value, fmt):\n"
        "        return 'old:' + value + ':' + fmt\n")
    before = _load_before(tmp_path)
    try:
        assert before(1.25, "0.0") == "old:1.25:0.0"
    finally:
        before.close()


def test_hash_probe_classifies_accounting_without_removed_metadata_field():
    formatter = SpreadsheetNumberFormatter()
    assert _kind('#,##0;(#,##0)', formatter) == "currency/accounting"
