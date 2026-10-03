"""BIFF 차트 세부 서식과 축 구분을 합성 레코드로 검증한다."""
import struct

from dochan.office_binary.xls_chart import parse_chart_substreams
from test_xls_chart import area, cache, chart, rec, rows, series, text


def formatted_brai(role, ifmt, linked=False, tokens=b''):
    return rec(0x1051, struct.pack('<BBHHH', role, 2 if tokens else 1,
                                 0 if linked else 1, ifmt, len(tokens)) + tokens)


def axis_title(role, title):
    return (rec(0x1025, b'\0' * 32) + rec(0x1033) + text(title)
            + rec(0x1027, struct.pack('<3H', role, 0, 0)) + rec(0x1034))


def group(kind, icrt=0):
    return (rec(0x1014, b'\0' * 18 + struct.pack('<H', icrt)) + rec(0x1033)
            + rec(kind, b'\0' * 6) + rec(0x1034))


def test_xls_scatter_axes_use_horizontal_and_vertical_object_links():
    out = parse_chart_substreams(chart(series(), rec(0x101b, b'\0' * 6),
                                       axis_title(2, 'Mass'), axis_title(3, 'Time'), cache(1, [2])))
    assert out[0].caption_text == 'Chart type: scatter; X axis: Time; Y axis: Mass'


def test_xls_chart_cache_formats_date_time_and_percent():
    data = chart(series(formatted_brai(2, 164), formatted_brai(1, 10)),
                 cache(2, [42213.5]), cache(1, [0.217]))
    out = parse_chart_substreams(data, number_formats={164: 'm/d/yy h:mm'})
    assert rows(out[0]) == [['Category', 'Series 1'], ['2015-07-28 12:00', '0.217']]


def test_xls_chart_builtin_time_and_1904_epoch():
    data = chart(series(formatted_brai(2, 14), formatted_brai(1, 21)),
                 cache(2, [0]), cache(1, [0.5]))
    out = parse_chart_substreams(data, date_1904=True)
    assert rows(out[0])[1] == ['1904-01-01', '12:00:00']


def test_xls_chart_linked_source_format_is_not_applied_twice():
    data = chart(series(formatted_brai(1, 10, linked=True, tokens=area(0, 0, 0, 0, 0))),
                 cache(1, [0.99]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '21.7%'}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '21.7%']


def test_xls_chart_unlinked_format_overrides_plain_source_value():
    data = chart(series(formatted_brai(1, 10, tokens=area(0, 0, 0, 0, 0))), cache(1, [0.99]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '0.217'}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '0.217']


def test_xls_mixed_chart_keeps_categories_out_of_numeric_x_column():
    label = struct.pack('<HHHHB', 0, 0, 0, 3, 0) + b'Jan'
    data = chart(series(text('Bars'), rec(0x1045, struct.pack('<H', 0))),
                 series(text('Dots'), rec(0x1045, struct.pack('<H', 1))),
                 group(0x1017), group(0x101b, 1), rec(0x1065, struct.pack('<H', 2)),
                 rec(0x0204, label), cache(2, [2], 1), cache(1, [10]), cache(1, [20], 1))
    out = parse_chart_substreams(data)
    assert rows(out[0]) == [['Series', 'Category', 'X', 'Y'], ['Bars', 'Jan', '', '10'],
                            ['Dots', '', '2', '20']]


def test_xls_chart_mixed_output_budget_accounts_for_four_columns():
    data = chart(series(rec(0x1045, struct.pack('<H', 0))),
                 series(rec(0x1045, struct.pack('<H', 1))), group(0x1017), group(0x101b, 1),
                 cache(2, [1]), cache(2, [2], 1), cache(1, [10]), cache(1, [20], 1))
    errors = []
    assert parse_chart_substreams(data, budget=[11], errors=errors) == []
    assert any('output cell limit' in error for error in errors)


def test_xls_chart_overrides_source_display_without_losing_raw_numeric_value():
    from dochan.office_binary.xls import _format_number_with_format
    value = _format_number_with_format(0.217, '0%')
    data = chart(series(formatted_brai(1, 2, tokens=area(0, 0, 0, 0, 0))), cache(1, [0.99]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): value}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '0.217']
    assert str(value) == '22%'  # 0% displays a rounded whole percent.


def test_xls_chart_linked_source_reuses_exact_time_value():
    from dochan.office_binary.xls import _format_number_with_format
    value = _format_number_with_format(42213.5, 'm/d/yy h:mm')
    data = chart(series(formatted_brai(2, 0, linked=True, tokens=area(0, 0, 0, 0, 0))), cache(1, [1]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): value}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['2015-07-28 12:00', '1']


def test_xls_chart_formula_cached_number_keeps_original_numeric_precision():
    from dochan.office_binary.xls import _format_number_with_format
    cached = _format_number_with_format(0.217, '0%')
    data = chart(series(formatted_brai(1, 2, tokens=area(0, 0, 0, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): str(cached) + ' (=A2)'}],
                                 formula_values=[{(0, 0): cached}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '0.217']


def test_xls_numeric_metadata_preserves_string_copy_and_json_contract():
    import copy
    import json
    from dochan.office_binary.xls import _format_number_with_format
    original = _format_number_with_format(0.217, '0%')
    copied = copy.deepcopy(original)
    assert json.dumps(copied) == '"22%"'
    assert copied.number == original.number == 0.217
    assert copied.number_format == '0%'


def test_xls_chart_linked_non_temporal_source_preserves_raw_value():
    from dochan.office_binary.xls import _format_number_with_format
    value = _format_number_with_format(8253465.0, '#,##0_ ')
    data = chart(series(formatted_brai(1, 0, linked=True, tokens=area(0, 0, 0, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): value}], external_sheets=[(0, 0)])
    assert rows(out[0])[1] == ['0', '8253465']


def test_xls_chart_string_category_is_not_coerced_by_number_format():
    label = struct.pack('<HHHHB', 0, 0, 0, 3, 0) + b'001'
    data = chart(series(formatted_brai(2, 14)), rec(0x1065, struct.pack('<H', 2)),
                 rec(0x0204, label), cache(1, [5]))
    assert rows(parse_chart_substreams(data)[0])[1] == ['001', '5']


def test_xls_workbook_plumbs_chart_formats_epoch_and_numeric_source():
    from dochan.office_binary.xls import parse_biff_workbook
    code = 'm/d/yy h:mm'
    fmt = rec(0x041e, struct.pack('<HHB', 164, len(code), 0) + code.encode('ascii'))
    globals_part = (rec(0x0809, struct.pack('<HH', 0x0600, 0x0005)) + fmt
                    + rec(0x0022, struct.pack('<H', 1)) + rec(0x00e0, struct.pack('<HH', 0, 164)))
    def boundsheet(offset):
        return rec(0x0085, struct.pack('<IBBBB', offset, 0, 0, 1, 0) + b'S')
    sheet_offset = len(globals_part) + len(boundsheet(0)) + len(rec(0x000a))
    tokens = struct.pack('<B4H', 0x25, 0, 0, 0, 0)
    data = (globals_part + boundsheet(sheet_offset) + rec(0x000a)
            + rec(0x0809, struct.pack('<HH', 0x0600, 0x0010))
            + rec(0x0203, struct.pack('<HHHd', 0, 0, 0, 0.5))
            + chart(series(formatted_brai(2, 0, linked=True, tokens=tokens), formatted_brai(1, 164)),
                    cache(1, [1.5])) + rec(0x000a))
    doc = parse_biff_workbook(data)
    assert rows(doc.sections[0].elements[0]) == [['1904-01-01 12:00']]
    assert rows(doc.sections[0].elements[1])[1] == ['1904-01-01 12:00', '1904-01-02 12:00']
