"""4차 감수: "색만 다른 음수 구역에만 - 를 붙인다" 결정을 정의대로 구현하는지.

기대값은 결정의 문언과 Excel 구역 규칙(ECMA-376 §18.8.31)에서 추론한 것이다(Excel 저장 표시값이 아님).
S4 의 한 구역 서식 음수 부호 위치는 NumberFormatTests A22(`"before "¥#.00` → `-before ¥12.30`) Excel 저장값이 근거다.
"""
import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("value,fmt,expected", [
    # 음수 구역에만 있는 부호 문자(▲·△·U+2212)는 그 표기를 그대로 낸다.
    ("-1234.5", '#,##0;[Red]"▲"#,##0', "▲1,235"),
    ("-1234.5", '#,##0;[Red]"△"#,##0', "△1,235"),
    ("-1234.5", '#,##0;[Red]"−"#,##0', "−1,235"),
    # 양쪽 구역에 같은 리터럴이 있으면 색만 다른 것이므로 부호를 붙인다.
    ("-1234.5", '#,##0.00 "USD";[Red]#,##0.00 "USD"', "-1,234.50 USD"),
    ("-1234.5", "0.00E-00;[Red]0.00E-00", "-1.23E+03"),
    # 지역화된 색 이름도 색 표기다.
    ("-1234.5", "#,##0;[빨강]#,##0", "-1,235"),
    # 결정 사항과 괄호 구역 확인.
    ("-1234.5", "#,##0;[Red]#,##0", "-1,235"),
    ("-1234.5", "#,##0;[Red]\\(#,##0\\)", "(1,235)"),
    # 색 없이 부호를 뺀 음수 구역은 작성자 의도(절댓값 표시)로 둔다.
    ("-1234.5", "#,##0;#,##0", "1,235"),
])
def test_color_only_negative_section_rule(value, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt).strip() == expected


def test_single_section_general_puts_minus_before_literal_prefix():
    assert SpreadsheetNumberFormatter()._format_cell_value("-5", '"Total "General') == "-Total 5"
