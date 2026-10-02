"""Synthetic final-review regressions for optional embedded objects."""
import struct
import zlib
from types import SimpleNamespace

import pytest

from dochan.office_binary.mtef import parse_mtef
from dochan.office_binary.ole_objects import PptObjects, parse_embedded_chart
from dochan.office_binary.officeart import parse_records, read_bstore
from test_mtef_review import char, equation
from test_ole_objects import compound, rec, rows
from test_ole_objects_chart_fix import selected_graph, workbook
from test_officeart import record


def test_embedded_workbook_warnings_are_bounded_and_not_fatal():
    # Each malformed RK supplies a distinct row coordinate; no corpus needed.
    sheet = rec(0x809, struct.pack('<HH', 0x600, 0x10))
    sheet += b''.join(rec(0x27e, struct.pack('<HHHI', row, 300, 0, 0)) for row in range(4000)) + rec(10)
    errors = []
    assert parse_embedded_chart(workbook([(0, sheet)]), errors, chart_object=True) == []
    assert len(errors) <= 17
    assert all(e.startswith('WARN:') for e in errors)
    assert any('3985 additional diagnostics omitted' in e for e in errors)


def test_embedded_workbook_error_is_downgraded_without_losing_host_error():
    sheet = rec(0x809, struct.pack('<HH', 0x600, 0x10))
    sheet += rec(0x200, struct.pack('<IIHHH', 0, 0x10001, 0, 1, 0)) + rec(10)
    errors = ['ERR: unrelated host failure']
    assert parse_embedded_chart(workbook([(0, sheet)]), errors, chart_object=True) == []
    assert errors[0] == 'ERR: unrelated host failure'
    assert all(e.startswith('WARN:') for e in errors[1:])
    assert any('DIMENSION' in e for e in errors)


def test_graph_unselected_series_does_not_leave_empty_column():
    excluded = rec(0x1003, struct.pack('<6H', 1, 1, 2, 2, 1, 0)) + rec(0x1033)
    excluded += rec(0x100d, b'\0\0\x08\0Excluded')
    excluded += rec(0x1051, struct.pack('<BBHHH', 1, 1, 2, 0, 2))
    excluded += rec(0x1051, struct.pack('<BBHHH', 2, 1, 2, 0, 0)) + rec(0x1034)
    data = selected_graph().replace(rec(0x1017, b'\0' * 6), excluded + rec(0x1017, b'\0' * 6))
    errors = []
    out = parse_embedded_chart(data, errors, graph=True)
    assert rows(out[-1]) == [['Category', 'Sales'], ['2000', '12'], ['2001', '18']]
    assert errors == []


@pytest.mark.parametrize('bt,refs', [(0, 0), (6, 0), (0, 2)])
def test_empty_or_unreferenced_fbse_does_not_read_delay_zero(bt, refs):
    fbse = struct.pack('<BB16sHIIIBBBB', bt, bt, bytes(16), 0, 0, refs, 0, 0, 0, 0, 0)
    store = record(0xf001, record(0xf007, fbse, version=2), version=15)
    errors = []
    entries = read_bstore(parse_records(store), delayed_stream=b'not a blip', errors=errors)
    assert len(entries) == 1 and entries[0].image is None
    assert errors == []


def test_adjacent_mtef_superscripts_share_script_level():
    def script(text):
        return b'\x03\x0f\0\0\x11\x01' + char(text, version=2) + b'\0\0'
    assert parse_mtef(equation(char('x', version=2) + script('2') + script('3'), 2)) == 'x^{23}'


def test_ooxml_package_preview_does_not_report_unused_compression_framing():
    raw = compound('Package', b'PK\x03\x04')
    compressed = struct.pack('<I', len(raw)) + zlib.compress(raw)[:-4]
    storage = SimpleNamespace(data=compressed, header=SimpleNamespace(rec_instance=1))
    errors = []
    assert PptObjects({2: storage}, errors, {2: 'Excel.Sheet.12'}).at(2, None) == []
    assert errors == []


def test_nested_mtef_superscript_keeps_its_own_baseline():
    def script(body):
        return b'\x03\x0f\0\0\x11\x01' + body + b'\0\0'
    body = char('x', version=2) + script(char('2', version=2) + script(char('3', version=2)))
    assert parse_mtef(equation(body, 2)) == 'x^{2^{3}}'


def test_native_storage_compression_warning_is_still_reported():
    from test_ole_objects import chart
    raw = compound('Workbook', chart())
    compressed = struct.pack('<I', len(raw)) + zlib.compress(raw)[:-4]
    storage = SimpleNamespace(data=compressed, header=SimpleNamespace(rec_instance=1))
    errors = []
    out = PptObjects({2: storage}, errors, {2: 'Excel.Chart.8'}).at(2, None)
    assert rows(out[-1])[1:] == [['1', '12'], ['2', '18']]
    assert any('compression framing anomaly' in e for e in errors)


def test_plain_workbook_diagnostics_preserve_prior_suppression_count():
    from dochan.office_binary.ole_objects import _ObjectErrors
    local = _ObjectErrors()
    # Public Document.errors is an ordinary mutable list, including its summary.
    local.extend(['ERR: XLS cell %d' % index for index in range(100)] +
                 ['WARN: XLS 3900 additional diagnostics omitted'])
    host = []
    local.copy_to_host(host)
    assert len(host) == 17
    assert host[-1] == 'WARN: embedded OLE 3984 additional diagnostics omitted'
    assert all(message.startswith('WARN:') for message in host)
