"""BIFF8 chart records assembled without external corpus dependencies."""
import struct

from dochan.office_binary.xls_chart import parse_chart_substreams
from dochan.model.document import Paragraph
from dochan.model.table import Table


def rec(sid, payload=b''):
    return struct.pack('<HH', sid, len(payload)) + payload


def chart(*records):
    return rec(0x0809, struct.pack('<HH', 0x0600, 0x0020)) + b''.join(records) + rec(0x000a)


def series(*records):
    return rec(0x1003, struct.pack('<6H', 1, 1, 2, 2, 1, 0)) + rec(0x1033) + b''.join(records) + rec(0x1034)


def text(value):
    return rec(0x100d, struct.pack('<HBB', 0, len(value), 1) + value.encode('utf-16le'))


def brai(role, tokens):
    return rec(0x1051, struct.pack('<BBHHH', role, 2, 0, 0, len(tokens)) + tokens)


def area(sheet, r1, r2, c1, c2):
    return struct.pack('<B5H', 0x3b, sheet, r1, r2, c1, c2)


def cache(kind, values, col=0):
    return rec(0x1065, struct.pack('<H', kind)) + b''.join(
        rec(0x0203, struct.pack('<HHHd', i, col, 0, value)) for i, value in enumerate(values)
    )


def rows(table):
    return [[c.text for c in row] for row in table.rows]


def test_chart_title_data_and_caption_contract():
    data = chart(series(text('Revenue')), rec(0x1017, struct.pack('<3H', 0, 150, 0)),
                 rec(0x1025, b'\0' * 32), rec(0x1033), text('Annual'),
                 rec(0x1027, struct.pack('<3H', 1, 0, 0)), rec(0x1034), cache(1, [12, 20]))
    elements = parse_chart_substreams(data, path='Workbook#Sheet', sheet_name='Sheet')
    assert isinstance(elements[0], Paragraph)
    assert elements[0].text == 'Annual'
    assert elements[0].heading_level == 3
    assert rows(elements[1]) == [['Category', 'Revenue'], ['0', '12'], ['1', '20']]
    assert elements[1].caption[0].text == 'Chart type: column'
    assert elements[1].caption_side == 'TOP'
    assert '#chart1' in elements[1].rows[0][0].provenance.path


def test_chart_brai_resolves_cross_sheet_ranges_without_cache():
    data = chart(series(brai(0, struct.pack('<B3H', 0x3a, 0, 0, 1)),
                        brai(1, area(0, 1, 2, 1, 1)), brai(2, area(0, 1, 2, 0, 0))), rec(0x1018, b'\0\0'))
    cells = {(0, 1): 'Sales', (1, 0): 'Jan', (2, 0): 'Feb', (1, 1): '5', (2, 1): '8'}
    elements = parse_chart_substreams(data, sheets=[cells], external_sheets=[(0, 0)])
    assert rows(elements[0]) == [['Category', 'Sales'], ['Jan', '5'], ['Feb', '8']]
    assert elements[0].caption[0].text == 'Chart type: line'


def test_chart_internal_cells_take_precedence_and_two_charts_are_isolated():
    data = chart(series(text('First'), brai(1, area(0, 0, 1, 0, 0))), cache(1, [2, 3]))
    data += chart(series(text('Second')), cache(1, [8]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '4', (1, 0): '6'}], external_sheets=[(0, 0)])
    assert rows(out[0]) == [['Category', 'First'], ['0', '4'], ['1', '6']]
    assert rows(out[1]) == [['Category', 'Second'], ['0', '8']]


def test_chart_axis_title_does_not_become_chart_title():
    data = chart(series(), rec(0x1018, b'\0\0'), rec(0x1025, b'\0' * 32), rec(0x1033),
                 text('Years'), rec(0x1027, struct.pack('<3H', 3, 0, 0)), rec(0x1034), cache(1, [5]))
    out = parse_chart_substreams(data)
    assert len(out) == 1 and isinstance(out[0], Table)
    assert out[0].caption[0].text == 'Chart type: line; Category axis: Years'


def test_scatter_different_x_uses_shared_ooxml_long_table():
    data = chart(series(text('A')), series(text('B')), rec(0x101b, b'\0' * 6),
                 cache(2, [1, 2]), cache(2, [3, 4], 1), cache(1, [10, 20]), cache(1, [30, 40], 1))
    out = parse_chart_substreams(data)
    assert rows(out[0]) == [['Series', 'X', 'Y'], ['A', '1', '10'], ['A', '2', '20'],
                            ['B', '3', '30'], ['B', '4', '40']]
    assert out[0].caption[0].text == 'Chart type: scatter'


def test_chart_oversized_range_is_warning_not_dense_allocation():
    errors = []
    out = parse_chart_substreams(chart(series(brai(1, area(0, 0, 65535, 0, 255)))),
                                 sheets=[{}], external_sheets=[(0, 0)], errors=errors)
    assert errors and all(e.startswith('WARN:') for e in errors)
    assert len(out) <= 1


def test_chart_truncated_record_warns_and_does_not_raise():
    errors = []
    parse_chart_substreams(chart(series())[:-4] + struct.pack('<HH', 0x0203, 14) + b'\0', errors=errors)
    assert errors and 'truncated' in errors[0]


def test_chart_parser_does_not_read_worksheet_numbers_as_cache():
    sheet = rec(0x0809, struct.pack('<HH', 0x0600, 0x0010))
    data = sheet + cache(1, [999]) + chart(series(), cache(1, [1])) + rec(0x000a)
    assert rows(parse_chart_substreams(data)[0]) == [['Category', 'Series 1'], ['0', '1']]


def test_chart_reference_uses_formula_cached_scalar():
    data = chart(series(brai(1, area(0, 0, 1, 0, 0))))
    cells = {(0, 0): '12 (=SUM(B1:B2))', (1, 0): '(=SUM(B3:B4))'}
    out = parse_chart_substreams(data, sheets=[cells], external_sheets=[(0, 0)])
    assert rows(out[0]) == [['Category', 'Series 1'], ['0', '12']]


def test_chart_bof_depth_limit_warns():
    from dochan.office_binary.xls_chart import MAX_DEPTH
    errors = []
    bof = rec(0x0809, struct.pack('<HH', 0x0600, 0x0020))
    assert parse_chart_substreams(bof * (MAX_DEPTH + 1), errors=errors) == []
    assert any('nesting limit' in e for e in errors)


def test_chart_references_share_point_budget(monkeypatch):
    from dochan.office_binary import xls_chart
    monkeypatch.setattr(xls_chart, 'MAX_POINTS', 3)
    data = chart(series(brai(1, area(0, 0, 1, 0, 0))), series(brai(1, area(0, 0, 1, 1, 1))))
    errors = []
    parse_chart_substreams(data, sheets=[{(0, 0): '1', (1, 0): '2', (0, 1): '3', (1, 1): '4'}],
                           external_sheets=[(0, 0)], errors=errors)
    assert any('point limit' in e for e in errors)


def test_chart_kind_record_flags_and_mixed_groups():
    data = chart(series(), rec(0x1017, struct.pack('<3H', 0, 150, 1)),
                 rec(0x1018, b'\0\0'), cache(1, [2]))
    out = parse_chart_substreams(data)
    assert out[0].caption_text == 'Chart type: bar + line'
    data = chart(series(), rec(0x1019, struct.pack('<3H', 0, 50, 0)), cache(1, [2]))
    assert parse_chart_substreams(data)[0].caption_text == 'Chart type: doughnut'
    data = chart(series(), rec(0x101b, struct.pack('<3H', 100, 1, 1)), cache(1, [2]))
    assert parse_chart_substreams(data)[0].caption_text == 'Chart type: bubble'


def test_chart_truncated_brai_preserves_cached_data():
    errors = []
    bad = rec(0x1051, struct.pack('<BBHHH', 1, 2, 0, 0, 500))
    out = parse_chart_substreams(chart(series(bad), cache(1, [7])), errors=errors)
    assert rows(out[0]) == [['Category', 'Series 1'], ['0', '7']]
    assert 'truncated BRAI' in errors[0]


def test_chart_cached_string_categories():
    label = '분기'
    value = struct.pack('<HHHHB', 0, 0, 0, len(label), 1) + label.encode('utf-16le')
    data = chart(series(), rec(0x1065, struct.pack('<H', 2)), rec(0x204, value), cache(1, [7]))
    assert rows(parse_chart_substreams(data)[0]) == [['Category', 'Series 1'], ['분기', '7']]


def test_review_internal_reference_overrides_stale_zero_cache():
    data = chart(series(brai(1, area(0, 0, 1, 0, 0))), cache(1, [0, 0]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '21.7%', (1, 0): '16.4%'}],
                                 external_sheets=[(0, 0)])
    assert rows(out[0])[1:] == [['0', '21.7%'], ['1', '16.4%']]


def test_review_external_reference_cannot_read_local_cells():
    errors = []
    data = chart(series(brai(1, area(0, 0, 0, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '42'}],
                                 external_sheets=[(1, 0, 0)], internal_supbooks={0}, errors=errors)
    assert '42' not in str([rows(t) for t in out if isinstance(t, Table)])
    assert any('external' in e for e in errors)
    out = parse_chart_substreams(chart(series(brai(1, area(0, 0, 0, 0, 0))), cache(1, [7])),
                                 sheets=[{(0, 0): '42'}], external_sheets=[(1, 0, 0)], internal_supbooks={0})
    assert rows(out[0])[1:] == [['0', '7']]


def test_review_formula_metadata_prevents_formula_text_as_chart_value():
    data = chart(series(brai(1, area(0, 0, 2, 0, 0))))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '=1+2', (1, 0): '=literal', (2, 0): '=SUM(A1)'}],
                                 external_sheets=[(0, 0)], formula_values=[{(0, 0): None, (2, 0): '3'}])
    assert rows(out[0])[1:] == [['1', '=literal'], ['2', '3']]


def test_review_truncated_chart_preserves_valid_cache():
    errors = []
    out = parse_chart_substreams(chart(series(), cache(1, [7]))[:-4], errors=errors)
    assert rows(out[0])[1:] == [['0', '7']]
    assert any('unterminated' in e for e in errors)


def test_review_serparent_auxiliary_series_excluded():
    out = parse_chart_substreams(chart(series(text('ACa')), series(rec(0x104a, b'\x01\0')),
                                       cache(1, [5]), cache(1, [0], 1)))
    assert rows(out[0]) == [['Category', 'ACa'], ['0', '5']]


def test_review_workbook_chart_and_point_limits_shared_across_calls(monkeypatch):
    from dochan.office_binary import xls_chart
    monkeypatch.setattr(xls_chart, 'MAX_CHARTS', 2)
    monkeypatch.setattr(xls_chart, 'MAX_POINTS', 3)
    shared = [1000]
    errors = []
    data = chart(series(), cache(1, [1, 2]))
    parse_chart_substreams(data, budget=shared, errors=errors)
    parse_chart_substreams(data, budget=shared, errors=errors)
    assert parse_chart_substreams(data, budget=shared, errors=errors) == []
    assert any('point limit' in e for e in errors)
    assert any('chart count' in e for e in errors)


def test_review_sparse_range_visits_only_actual_cells():
    class Sparse(dict):
        def get(self, key, default=None):
            raise AssertionError('dense coordinate scan')
    data = chart(series(brai(1, area(0, 0, 65535, 0, 255))))
    out = parse_chart_substreams(data, sheets=[Sparse({(65535, 255): '9'})], external_sheets=[(0, 0)])
    assert rows(out[0])[1:] == [['16777215', '9']]


def test_review_chart_accepts_memoryview_without_copying_whole_stream():
    out = parse_chart_substreams(memoryview(chart(series(text('Name')), cache(1, [7]))))
    assert rows(out[0]) == [['Category', 'Name'], ['0', '7']]


def test_review_unterminated_chart_stops_at_worksheet_record():
    errors = []
    data = chart(series(), cache(1, [7]))[:-4]
    data += rec(0x00fd, struct.pack('<HHHI', 0, 0, 0, 0))
    data += rec(0x0203, struct.pack('<HHHd', 0, 0, 0, 99)) + rec(0x000a)
    out = parse_chart_substreams(data, errors=errors)
    assert rows(out[0])[1:] == [['0', '7']]
    assert any('worksheet record' in e for e in errors)


def test_review_resolved_empty_formula_does_not_resurrect_stale_chart_cache():
    data = chart(series(brai(1, area(0, 0, 0, 0, 0))), cache(1, [99]))
    out = parse_chart_substreams(data, sheets=[{(0, 0): '=1+2'}], external_sheets=[(0, 0)],
                                 formula_values=[{(0, 0): None}])
    assert rows(out[0]) == [['Category', 'Series 1']]
