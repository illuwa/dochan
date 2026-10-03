"""Regression cases for number-format token interpretation (synthetic values)."""
import pytest

from dochan.ooxml.xlsx import XLSXReader


@pytest.mark.parametrize("value,fmt,expected", [
    ("12.5", '0.0"mm"', "12.5mm"),
    # Excel 숫자 표시의 동점은 올림이다. 12yy는 Python의 짝수 반올림 결과였다.
    ("12.5", '0"yy"', "13yy"),
    ("0.5", '0.0"%"', "0.5%"),
    ("1.25", "[$-412]General", "1.25"),
    ("43831", "[White]yyyy-mm-dd", "2020-01-01"),
    ("0.001", "mm:ss", "01:26"),
    ("0.125", "0%", "13%"),
    ("1.4999999999999999E-2", "0%", "2%"),
    ("0.0149999999999999", "0%", "1%"),
    ("-0.125", "0%", "-13%"),
    ("43831.9999999", "m/d/yyyy h:mm", "2020-01-02 00:00"),
    ("1e400", "0%", "1e400"),
    ("0.125", "[<1]0.00%;0", "12.50%"),
    ("12.5", "[<1]0.00%;0", "13"),
    ("0.5", "[>=1]yyyy-mm-dd;0.00", "0.50"),
    ("12.5", '0.0"[<1]"', "12.5[<1]"),
    ("0.5555671296296296", 'h"时"mm"分"ss"秒";@', "13:20:01"),
    ("0.000011574074074074074", "[s]", "1"),
    ("43831.5", 'm-d h"时"mm"分"', "2020-01-01 12:00"),
    ("43831.5", "mm-d h", "2020-01-01 12:00"),
    ("1.25", "0.00;h", "1.25"),
    ("0.5", '[<1]0.0"[<1]";0', "0.5[<1]"),
    ("0.5", '"[<1]"[<1]0.0;0', "[<1]0.5"),
    ("1021.02", '[>999999]#,,"M";[>999]#,"K";#', "1021.02"),
    ("1021020", '#,,"M"', "1021020"),
    ("1021.02", '#,##0.00', "1,021.02"),
    ("1021.02", '#,##0.00","', "1,021.02,"),
    ("1021.02", r'#,##0.00\,', "1,021.02,"),
])
def test_review_cell_number_formats(value, fmt, expected):
    assert XLSXReader()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("fmt,kind", [
    ('0.0"mm"', "decimal"),
    ('0"yy"', "decimal"),
    ('0.0"%"', "decimal"),
    ("[$-412]General", ""),
    ("[White]yyyy-mm-dd", "date"),
    ("mm:ss", "time"),
    ('h"时"mm"分"ss"秒";@', "time"),
])
def test_review_format_kind_ignores_literals_and_locale(fmt, kind):
    assert XLSXReader()._format_metadata(fmt).kind == kind


def test_review_nonfinite_numeric_value_warns_without_losing_raw_value():
    reader = XLSXReader()
    reader._errors = []
    assert reader._format_cell_value("1e400", "0%") == "1e400"
    assert any("out of range" in warning for warning in reader._errors)
