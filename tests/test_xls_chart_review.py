"""차트 리뷰의 문자열 범주, 수치 손실, 그룹 식별자를 재현한다."""
import struct

from dochan.office_binary.xls import _format_number_with_format
from dochan.office_binary.xls_chart import parse_chart_substreams
from test_xls_chart import area, cache, chart, rec, rows, series, text
from test_xls_chart_details import formatted_brai


def group(icrt, kind):
    return (rec(0x1014, b'\0' * 18 + struct.pack('<H', icrt)) + rec(0x1033)
            + rec(kind, b'\0' * 6) + rec(0x1034))


def test_xls_review_string_reference_category_ignores_brai_date_format():
    data = chart(series(formatted_brai(2, 14, tokens=area(0, 0, 0, 0, 0))), cache(1, [5]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '001'}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['001', '5']


def test_xls_review_linked_source_uses_raw_number_not_rounded_display():
    value = _format_number_with_format(8253465.25, '#,##0')
    data = chart(series(formatted_brai(1, 0, linked=True, tokens=area(0, 0, 0, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): value}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '8253465.25']


def test_xls_review_unlinked_brai_keeps_raw_number_precision():
    value = _format_number_with_format(0.0891, '0%')
    data = chart(series(formatted_brai(1, 2, tokens=area(0, 0, 0, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): value}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '0.0891']


def test_xls_review_cached_percent_keeps_raw_number_precision():
    data = chart(series(formatted_brai(1, 9)), cache(1, [0.0891]))
    assert rows(parse_chart_substreams(data)[0])[1] == ['0', '0.0891']


def test_xls_review_quoted_date_tokens_keep_raw_number():
    value = _format_number_with_format(12.5, '0.0"mm"')
    data = chart(series(formatted_brai(1, 0, linked=True, tokens=area(0, 0, 0, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): value}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '12.5']


def test_xls_review_chartformat_uses_icrt_not_record_order():
    data = chart(series(text('Bars'), rec(0x1045, struct.pack('<H', 3))),
                 series(text('Dots'), rec(0x1045, struct.pack('<H', 1))),
                 group(1, 0x101b), group(3, 0x1017),
                 cache(2, [2]), cache(2, [3], 1), cache(1, [10]), cache(1, [20], 1))
    out = parse_chart_substreams(data)
    assert rows(out[0]) == [['Series', 'Category', 'X', 'Y'],
                            ['Bars', '2', '', '10'], ['Dots', '', '3', '20']]


def test_xls_review_equal_time_displays_do_not_merge_distinct_raw_x():
    data = chart(series(text('A'), formatted_brai(2, 20)),
                 series(text('B'), formatted_brai(2, 20)), rec(0x101b, b'\0' * 6),
                 cache(2, [0.50001]), cache(2, [0.50002], 1),
                 cache(1, [10]), cache(1, [20], 1))
    out = parse_chart_substreams(data)
    assert rows(out[0]) == [['Series', 'X', 'Y'], ['A', '12:00', '10'], ['B', '12:00', '20']]
