"""Regression tests for embedded chart selection and preview preservation."""
import struct

from test_ole_objects import Ole, chart, rec, rows
from dochan.office_binary.ole_objects import EmbeddedObjects, parse_embedded_chart, _records


def workbook(streams, active=0):
    """Each entry is (BOUNDSHEET type, sheet bytes)."""
    header = rec(0x809, struct.pack('<HH', 0x600, 5))
    header += rec(0x3d, b'\0' * 10 + struct.pack('<H', active))
    offset = len(header) + len(streams) * 13 + 4
    bounds = b''
    for kind, stream in streams:
        bounds += rec(0x85, struct.pack('<IBBBB', offset, 0, kind, 1, 0) + b'S')
        offset += len(stream)
    return header + bounds + rec(10) + b''.join(stream for _, stream in streams)


def selected_graph(extra=b'', rows_selection=(0, 2), cols_selection=(0, 3), counts=None):
    parts = []
    for _, sid, payload in _records(chart(True)):
        if sid == 0x1055:
            parts.extend([rec(0x1053, struct.pack('<HH', *rows_selection)),
                          rec(0x1054, struct.pack('<HH', *cols_selection)), extra])
        if sid == 0x1003 and counts:
            payload = payload[:4] + struct.pack('<HH', *counts) + payload[8:]
        parts.append(rec(sid, payload))
    return b''.join(parts)


def test_graph_selection_excludes_outside_datasheet_points():
    extra = b''.join(rec(3, struct.pack('<HH3sd', r, 3, b'\0'*3, v))
                     for r, v in [(0, 999), (1, 777)])
    errors = []
    out = parse_embedded_chart(selected_graph(extra), errors, graph=True)
    assert rows(out[1]) == [['Category', 'Sales'], ['2000', '12'], ['2001', '18']]
    assert not errors


def test_graph_series_count_mismatch_retains_preview():
    errors = []
    assert parse_embedded_chart(selected_graph(counts=(2, 3)), errors, graph=True) == []
    assert any('point count' in e for e in errors)


def test_graph_unrecognized_selection_retains_preview():
    errors = []
    assert parse_embedded_chart(selected_graph(cols_selection=(1, 3)), errors, graph=True) == []
    assert errors


def test_active_worksheet_excel_object_retains_preview():
    sheet = rec(0x809, struct.pack('<HH', 0x600, 0x10)) + chart() + rec(10)
    data = workbook([(0, sheet)])
    errors = []
    out = EmbeddedObjects(errors).read(Ole({'Workbook': data, '\x01CompObj': b'Excel.Sheet.8\0'}), [], None)
    assert out == []
    assert not errors


def test_excel_chart_progid_allows_chart_in_active_worksheet():
    sheet = rec(0x809, struct.pack('<HH', 0x600, 0x10)) + chart() + rec(10)
    out = EmbeddedObjects([]).read(Ole({'Workbook': workbook([(0, sheet)]),
                                       '\x01CompObj': b'Excel.Chart.8\0'}), [], None)
    assert rows(out[1])[1:] == [['1', '12'], ['2', '18']]


def test_empty_embedded_chart_retains_preview():
    data = b''.join(rec(sid, p) for _, sid, p in _records(chart()) if sid != 0x203)
    errors = []
    assert parse_embedded_chart(data, errors) == []
    assert errors


def test_embedded_chart_resolves_internal_brai_without_cache():
    # Shared workbook parser resolves Ref/Area tokens against worksheet cells.
    formula = b'\x3b' + struct.pack('<5H', 0, 0, 1, 0, 0)
    linked = rec(0x809, struct.pack('<HH', 0x600, 0x20))
    linked += rec(0x1003, struct.pack('<6H', 1, 1, 2, 2, 1, 0)) + rec(0x1033)
    linked += rec(0x1051, struct.pack('<BBHHH', 1, 2, 0, 0, len(formula)) + formula)
    linked += rec(0x1034) + rec(0x1017, b'\0'*6) + rec(10)
    sheet = rec(0x809, struct.pack('<HH', 0x600, 0x10))
    sheet += rec(0x203, struct.pack('<HHHd', 0, 0, 0, 12))
    sheet += rec(0x203, struct.pack('<HHHd', 1, 0, 0, 18)) + rec(10)
    data = workbook([(0, sheet), (2, linked)], active=1)
    # Inserting global records shifts each absolute sheet offset.
    extra = rec(0x1ae, struct.pack('<HH', 2, 0x401)) + rec(0x17, struct.pack('<4H', 1, 0, 0, 0))
    parts = []
    inserted = False
    for _, sid, p in _records(data):
        if sid == 0x85:
            p = struct.pack('<I', struct.unpack_from('<I', p)[0] + len(extra)) + p[4:]
        if sid == 10 and not inserted:
            parts.append(extra)
            inserted = True
        parts.append(rec(sid, p))
    errors = []
    out = parse_embedded_chart(b''.join(parts), errors)
    assert rows(out[-1]) == [['Category', 'Series 1'], ['1', '12'], ['2', '18']]
    assert not errors


def test_default_chart_category_is_one_based():
    out = parse_embedded_chart(chart(), [])
    assert rows(out[1])[1:] == [['1', '12'], ['2', '18']]
