"""2차 리뷰의 Excel 저장값과 명세 기반 규칙 추론을 구분해 검사한다."""

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("value, fmt, expected", [
    ("-1.234", "0.00;0.000", "1.234"),
    ("0", '0;0;"zero"', "zero"),
    ("0", '0;0;"-"', "-"),
    ("0", '0;0;"-"??', "-  "),
    ("-12", '0;"neg "0', "neg 12"),
])
def test_selected_numeric_section_controls_display(value, fmt, expected):
    """규칙 추론: 명시 음수 구역은 절댓값을 쓰고 영 구역은 리터럴을 낸다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("123456", '"ID-"0000', "ID-123456"),
    ("123456", '"No. "000', "No. 123456"),
    ("1234", '"#"00', "#1234"),
    ("12345678", r"000\-0000", "1234-5678"),
])
def test_zero_fill_overflow_follows_literal_prefix(value, fmt, expected):
    """규칙 추론: 넘친 숫자는 첫 자리 토큰에 붙는다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("1.5", "# ??/105", "1 53/105"),
    ("2.3", "# ???/205", "2 61/205"),
    ("1.5", "# ?/1001", "1 501/1001"),
    ("1.5", "# ?/20", "1 10/20"),
])
def test_fixed_denominator_digits_are_not_suffix(value, fmt, expected):
    """규칙 추론: 고정 분모의 중간 0은 접미사가 아니다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("12.3", "000.00", "012.30"),
    ("1234567", "0,", "1235"),
    ("1234567", "0,,", "1"),
    ("1234", "000,", "001"),
    ("12", "0$", "12$"),
    ("2.3", "# 0/8", "2.3"),
])
def test_decimal_display_positions(value, fmt, expected):
    """Excel 저장값: 000.00과 0,; 나머지는 규칙 추론이다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("12200000", "#0.0E+0", "12.2E+6"),
    ("12345", "##0.0E+0", "12.3E+3"),
    ("3.14", "0.00e+00", "3.14e+00"),
])
def test_scientific_mantissa_width_and_case(value, fmt, expected):
    """Excel 저장값: 소문자 e; 공학 가수 폭은 ECMA 규칙 추론이다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


def test_elapsed_token_can_follow_plain_seconds():
    """Excel 저장값: ElapsedFormatTests.xlsx의 경과 시간 표시를 따른다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(
        "3.14159", 's" secs and "[m]" mins"') == "53 secs and 4523 mins"


def test_warning_names_shared_spreadsheet_formatter():
    """규칙 추론: XLS와 XLSX가 공유하는 오류 메시지는 형식 중립적이다."""
    formatter = SpreadsheetNumberFormatter()
    formatter._errors = []
    formatter._format_cell_value("inf", "0")
    assert formatter._errors and "XLSX" not in formatter._errors[0]


@pytest.mark.parametrize("value, fmt, expected", [
    ("-0.94", "# ?/?", "-1"),          # 더 가까운 8/9 가 아니라 수렴분수 1
    ("-1.03", "# ??/??", "-1 1/33"),
    ("0.7", "# ?/?", "2/3"),           # 5/7 가 더 가깝지만 수렴분수가 아니다
    ("0.1", "# ?/?", "0"),             # 부동소수 1/0.1 == 10.0 이라 1/10 에서 멈춘다
    ("0.9", "# ?/?", "8/9"),
    ("0.01", "# ??/??", "0"),
    ("0.89", "# ??/??", "8/9"),
    ("0.87", "# ??/??", "67/77"),       # 부동소수 몫 3.999… → 3
    ("0.5", "# ?/?", "1/2"),
])
def test_variable_denominator_public_excel_table(value, fmt, expected):
    """Excel 저장값: 공개 54686 분수 표(D·E열)의 가변 분모 사례다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("fmt, expected", [
    ("# ?/?", "123 1/2"),       # 가장 가까운 4/9 가 아니다
    ("# ??/??", "123 26/57"),   # 가장 가까운 31/68 이 아니다
    ("# ???/???", "123 57/125"),
])
def test_variable_denominator_microsoft_support_example(fmt, expected):
    """Microsoft 지원 문서 'Display numbers as fractions' 의 123.456 예시다."""
    assert SpreadsheetNumberFormatter()._format_cell_value("123.456", fmt) == expected


def test_continued_fraction_without_room_is_zero():
    assert SpreadsheetNumberFormatter._continued_fraction(0.5, 0) == 0
