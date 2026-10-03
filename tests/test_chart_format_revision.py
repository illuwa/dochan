"""리뷰의 경과 시간 표시, 원시 값 보존 및 서식 토큰 계약을 합성 입력으로 검증한다."""
import pytest

from dochan.ooxml import charts
from dochan.ooxml.xlsx import XLSXReader
from dochan.ooxml.pptx import PPTXReader
from dochan.hwpx.charts import parse_chart_xml
from dochan.utils import safe_xml as etree
from test_chart_details import root, series, table


@pytest.mark.parametrize("fmt,expected", [
    ("0.00_h", "1.50 "), ("0.00*h", "1.50"),
    ('0.00"h"', "1.50h"), (r"0.00\h", "1.50h"),
    ('0.00_"', "1.50 "),
])
def test_spacing_fill_and_literals_are_not_time_tokens(fmt, expected):
    reader = XLSXReader()
    assert reader._format_metadata(fmt).kind == "decimal"
    assert reader._format_cell_value("1.5", fmt) == expected
    assert charts.format_chart_number("1.5", fmt) == "1.5"


@pytest.mark.parametrize("value,fmt", [
    ("3.14159", "[ss].000"), ("0.5", "ss.00"),
    ("-1.5", "[h]:mm:ss"), ("-0.25", "[mm]:ss"),
    ("1.5", "[h]:ss"), ("1.5", "[m]:mm"), ("1.5", "[s]:ss"),
    ("1.5", "[h]:mmm"), ("1.5", "[h]:mm:ss.000"),
    ("1.5", "[h] mm"), ("1.5", "[h]:mm:hh"),
    ("1.5", '[h]":"mm'), ("1.5", "[h]:[m]"),
    ("0.1702084490740741", "h:m:s.00"),
    ("0.1702084490740741", "hh:mm:ss.000"),
    ("0.1702084490740741", "h:m:s"), ("0.5", "s"),
    ("-0.25", "h:mm"), ("-1", "yyyy-mm-dd"),
])
@pytest.mark.parametrize("date_1904", [False, True])
def test_unsupported_temporal_displays_preserve_raw(value, fmt, date_1904):
    reader = XLSXReader()
    reader._date_1904 = date_1904
    # Fifth review explicitly replaces these earlier raw fallbacks with display.
    supported = {
        "[ss].000": "271433.376", "ss.00": "00.00",
        "[h]:mm:ss.000": "36:00:00.000", "[h] mm": "36 00",
        '[h]":"mm': "36:00", "h:m:s.00": "4:5:6.01",
        "hh:mm:ss.000": "04:05:06.010", "h:m:s": "4:5:6", "s": "0",
    }
    if date_1904:
        supported.update({"[h]:mm:ss": "-36:00:00", "[mm]:ss": "-360:00"})
    expected = supported.get(fmt, value)
    assert reader._format_cell_value(value, fmt) == expected
    assert charts.format_chart_number(value, fmt, date_1904) == expected


@pytest.mark.parametrize("fmt", ["[h]", "[hh]", "[mm]", "[ss]", "[HHH]"])
def test_repeated_elapsed_units_are_classified_as_duration(fmt):
    assert XLSXReader()._format_metadata(fmt).kind == "duration"


def test_accounting_spacing_and_fill_are_rendered_as_plain_text():
    reader = XLSXReader()
    assert reader._format_cell_value("2667.6", '_(* $#,##0.00_);_(* ($#,##0.00);_(* "-"??_);_(@_)') == " $2,667.60 "
    assert reader._format_sections('0.00_;h:mm') == ['0.00_;h:mm']
    assert reader._format_sections('0.00*;h:mm') == ['0.00*;h:mm']


@pytest.mark.parametrize("value,fmt,expected", [
    # 음수 구역의 이스케이프 괄호가 표시 기호다. 기존 단언은 첫 구역을 적용했다.
    ("-1234.125", r"#,##0.000_);\(#,##0.000\)", "(1,234.125)"),
    ("12.5", r'_-* #,##0.00\ "€"_-', " 12.50 € "),
    ("12.5", '0.0"_*"', "12.5_*"),
])
def test_layout_token_removal_keeps_sign_currency_and_quoted_literals(value, fmt, expected):
    assert XLSXReader()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value,expected", [
    ("0.034999999999999996", "4%"), ("-0.034999999999999996", "-4%"),
    ("0.0149999999999999", "1%"),
])
def test_percentage_rounds_fifteen_significant_digits_half_up(value, expected):
    assert XLSXReader()._format_cell_value(value, "0%") == expected


def test_missing_title_never_synthesizes_a_series_heading():
    xml = root('<c:barChart>' + series('Revenue', ['A'], ['1']) + '</c:barChart>',
               extra='<c:autoTitleDeleted val="0"/>')
    assert charts.chart_title(xml) == ""
    elements, _ = parse_chart_xml(etree.tostring(xml), display_values=True)
    assert all(hasattr(element, "rows") for element in elements)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_general_numeric_formats_always_warn(value):
    reader = XLSXReader()
    reader._errors = []
    assert reader._format_cell_value(value, "General") == value
    assert len(reader._errors) == 1


def test_chart_format_limit_prevents_reader_creation(monkeypatch):
    def forbidden(*args):
        pytest.fail("oversized format reached reader/cache")
    monkeypatch.setattr(charts, "_number_format_reader", forbidden)
    assert charts.format_chart_number("1.5", "h:mm" + " " * 252) == "1.5"


def test_chart_selects_conditional_section_before_temporal_kind():
    assert charts.format_chart_number("0.5", "[>=1]yyyy-mm-dd;h:mm") == "12:00"
    assert charts.format_chart_number("43831", "[<1]h:mm;yyyy-mm-dd") == "2020-01-01"


def test_unsupported_fraction_does_not_become_a_rounded_integer():
    assert XLSXReader()._format_cell_value("-3.75", "|#_?=/=#|") == "-3.75"


def test_fraction_fallback_does_not_change_formats_without_padding():
    assert XLSXReader()._format_cell_value("0", r"|#\:#/#|") == "|0|"


@pytest.mark.parametrize("value,fmt", [
    ("1.5", "0.00_h"), ("1.5", "0.00*h"), ("0.5", "[ss].000"),
    ("1.5", "[h]:ss"), ("-0.25", "h:mm"), ("0.125", "hh:mm:ss.000"),
    ("-1.5", "[h]:mm:ss"), ("0.5", "h:m:s"),
])
def test_temporal_fallback_reaches_all_four_chart_readers(value, fmt):
    from dochan.office_binary.xls_chart import parse_chart_substreams
    from test_xls_chart import cache, chart, rows, series as biff_series
    from test_xls_chart_details import formatted_brai

    expected = {"[ss].000": "43200.000", "hh:mm:ss.000": "03:00:00.000",
                "h:m:s": "12:0:0"}.get(fmt, value)
    xml = root('<c:scatterChart>' + series('S', [value], ['2'], True, fmt) + '</c:scatterChart>')
    for reader_type in (XLSXReader, PPTXReader):
        assert table(reader_type, xml)[1] == [expected, "2"]
    elements, _ = parse_chart_xml(etree.tostring(xml), display_values=True)
    assert next(element for element in elements if hasattr(element, "rows")).rows[1][0].text == expected
    data = chart(biff_series(formatted_brai(2, 164)), cache(2, [float(value)]), cache(1, [2]))
    assert rows(parse_chart_substreams(data, number_formats={164: fmt})[0])[1] == [expected, "2"]


ELAPSED_CASES = [
    ("1.5", "[h]:mm:ss", "36:00:00"),
    ("1.5", "[hh]:mm:ss", "36:00:00"),
    ("0.04", "[h]:mm", "0:57"),
    ("0.0423", "[mm]:ss", "60:55"),
    ("0.0423", "[hh]:mm:ss", "01:00:55"),
    ("3.14159", "[ss]", "271433"),
    ("0.5", "[hhh]", "012"),
    ("0.000011574074074074074", "[s]", "1"),
    ("0.5", "[ss]", "43200"),
    ("1.5", "[mm]:ss", "2160:00"),
    ("0", "[hh]:mm:ss", "00:00:00"),
    ("0", "[mm]", "00"),
    ("0", "[ss]", "00"),
    ("0.0423", "[h]:m:s", "1:0:55"),
    ("0.0423", "[h]:m:ss", "1:0:55"),
    ("0.0423", "[h]:mm:s", "1:00:55"),
    ("0.00002", "[m]:s", "0:2"),
    ("0.00002", "[m]:ss", "0:02"),
    ("0.00002", "[s]", "2"),
    ("0.999999", "[h]:mm:ss", "24:00:00"),
    ("0.999999", "[m]", "1440"),
    ("0.00069", "[h]:mm", "0:01"),
    ("0.0423", "[HH]:MM:SS", "01:00:55"),
    ("0.0423", '"elapsed "[hh]:mm:ss" total"', "elapsed 01:00:55 total"),
    ("0.0423", '"h;"[m]:ss"s"', "h;60:55s"),
]


@pytest.mark.parametrize("value,fmt,expected", ELAPSED_CASES)
@pytest.mark.parametrize("date_1904", [False, True])
def test_supported_elapsed_displays_total_units(value, fmt, expected, date_1904):
    reader = XLSXReader()
    reader._date_1904 = date_1904
    assert reader._format_cell_value(value, fmt) == expected
    display = charts.format_chart_number(value, fmt, date_1904)
    assert display == expected
    assert display.raw == value


@pytest.mark.parametrize("value,fmt,expected", ELAPSED_CASES)
def test_elapsed_display_reaches_all_four_chart_readers(value, fmt, expected):
    from dochan.office_binary.xls_chart import parse_chart_substreams
    from test_xls_chart import cache, chart, rows, series as biff_series
    from test_xls_chart_details import formatted_brai

    xml = root('<c:scatterChart>' + series('S', [value], [value], True, fmt, fmt) + '</c:scatterChart>')
    for reader_type in (XLSXReader, PPTXReader):
        assert table(reader_type, xml)[1] == [expected, expected]
    elements, _ = parse_chart_xml(etree.tostring(xml), display_values=True)
    assert [cell.text for cell in next(e for e in elements if hasattr(e, "rows")).rows[1]] == [expected, expected]
    data = chart(biff_series(formatted_brai(2, 164), formatted_brai(1, 164)),
                 cache(2, [float(value)]), cache(1, [float(value)]))
    assert rows(parse_chart_substreams(data, number_formats={164: fmt})[0])[1] == [expected, expected]
