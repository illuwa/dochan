"""Review regressions using synthetic BIFF records only."""
import struct
import pytest
from dochan.office_binary import xls
from test_xls_remaining import record, workbook, font
from test_xls_hyperlink import _hlink


def labels(count):
    return b''.join(record(0xFD, struct.pack('<HHHI', r, 0, 0, 0)) for r in range(count))


def sst(text=b'ab', rich=True):
    value = struct.pack('<HB', len(text), 8 if rich else 0)
    if rich:
        value += struct.pack('<H', 2)
    value += text
    if rich:
        value += struct.pack('<4H', 0, 0, 1, 1)
    return record(0xFC, struct.pack('<II', 1, 1) + value)


def test_plain_sst_retains_shared_string_identity():
    doc = xls.parse_biff_workbook(workbook(sst(b'x' * 1000, False), labels(10)))
    texts = [row[0].paragraphs[0].runs[0].text for row in doc.sections[0].elements[0].rows]
    assert type(texts[0]) is str
    assert all(t is texts[0] for t in texts)


def test_rich_fragments_shared_but_cell_provenance_distinct():
    doc = xls.parse_biff_workbook(workbook(font() + font(True) + sst(), labels(3)))
    rows = doc.sections[0].elements[0].rows
    a, b = rows[0][0].paragraphs[0].runs, rows[1][0].paragraphs[0].runs
    assert a[1].text is b[1].text
    assert a[1].provenance.cell == 'A1'
    assert b[1].provenance.cell == 'A2'


def test_rich_output_budget_falls_back_to_plain_text(monkeypatch):
    monkeypatch.setattr(xls, 'MAX_RICH_RUNS', 4, raising=False)
    doc = xls.parse_biff_workbook(workbook(font() + font(True) + sst(), labels(4)))
    rows = doc.sections[0].elements[0].rows
    assert [c[0].text for c in rows] == ['ab'] * 4
    assert sum(len(r[0].paragraphs[0].runs) for r in rows) <= 6
    assert any('rich text' in e and 'limit' in e for e in doc.errors)


def test_rejected_cells_do_not_capture_rich_runs(monkeypatch):
    monkeypatch.setattr(xls, 'MAX_BIFF_DENSE_CELLS', 1)
    sheet = xls._SheetInfo('S', 0)
    value = xls._RichString('ab', [(0, 0), (1, 1)])
    xls._parse_sheet_records(labels(3), sheet, [value], {}, [], [], [], [], fonts=[(False,)*4, (True,False,False,False)])
    assert set(sheet.cell_rich) == {(0, 0)}


def test_unterminated_chart_does_not_swallow_worksheet_cells():
    broken_chart = record(0x809, struct.pack('<HH', 0x600, 0x20)) + record(0x1003, b'\0' * 12)
    doc = xls.parse_biff_workbook(workbook(sst(b'after', False), broken_chart + labels(5)))
    assert [row[0].text for row in doc.sections[0].elements[0].rows] == ['after'] * 5
    assert any('chart' in e for e in doc.errors)


@pytest.mark.parametrize('component', ['chart', 'drawing'])
def test_optional_component_failure_keeps_worksheet(monkeypatch, component):
    def fail(*args, **kwargs):
        raise ValueError('synthetic failure')
    if component == 'chart':
        monkeypatch.setattr(xls, 'parse_chart_substreams', fail)
    else:
        monkeypatch.setattr(xls.XlsDrawingReader, 'read_sheet', fail)
    doc = xls.parse_biff_workbook(workbook(sst(b'kept', False), labels(1)))
    assert doc.sections[0].elements[0].rows[0][0].text == 'kept'
    assert any(e.startswith('WARN:') and component in e for e in doc.errors)


def test_hyperlink_range_display_only_at_anchor():
    data = _hlink('S!A1', 'Jump')
    data = struct.pack('<4H', 0, 2, 0, 0) + data[8:]
    doc = xls.parse_biff_workbook(workbook(b'', record(0x1B8, data)))
    assert [r[0].text for r in doc.sections[0].elements[0].rows] == ['Jump <#S!A1>', '#S!A1', '#S!A1']


def test_formula_string_continue_switches_encoding_without_nul():
    tokens = b'\x1e\x01\0'
    formula = record(6, struct.pack('<3H', 0, 0, 0) + b'\0'*6 + b'\xff\xff' + struct.pack('<HIH',0,0,len(tokens)) + tokens)
    string = record(0x207, struct.pack('<HB', 4, 0) + b'ab')
    string += record(0x3C, b'\1' + '가나'.encode('utf-16le'))
    doc = xls.parse_biff_workbook(workbook(b'', formula + string))
    assert doc.sections[0].elements[0].rows[0][0].text == 'ab가나 (=1)'


def test_chart_blank_cache_is_not_a_worksheet_recovery_boundary():
    chart = record(0x809, struct.pack('<HH', 0x600, 0x20))
    chart += record(0x1065, struct.pack('<H', 1))
    chart += record(0x201, struct.pack('<3H', 0, 0, 0)) + record(10)
    doc = xls.parse_biff_workbook(workbook(sst(b'kept', False), labels(1) + chart))
    assert not any('unterminated chart' in e for e in doc.errors)
    assert doc.sections[0].elements[0].rows[0][0].text == 'kept'


def test_rich_byte_budget_keeps_text(monkeypatch):
    monkeypatch.setattr(xls, 'MAX_RICH_BYTES', 8)
    doc = xls.parse_biff_workbook(workbook(font() + font(True) + sst(b'abcdef'), labels(2)))
    assert [r[0].text for r in doc.sections[0].elements[0].rows] == ['abcdef'] * 2
    assert any('rich text limit' in e for e in doc.errors)


def test_chart_inputs_follow_boundsheet_order_and_use_views(monkeypatch):
    observed = []
    def capture(data, **kwargs):
        observed.append((data, kwargs))
        return []
    monkeypatch.setattr(xls, 'parse_chart_substreams', capture)
    bof = record(0x809, struct.pack('<HH', 0x600, 0x10))
    a = bof + record(0x203, struct.pack('<3Hd', 0,0,0,11)) + record(10)
    b = bof + record(0x203, struct.pack('<3Hd', 0,0,0,22)) + record(10)
    def bounds(offset, name):
        return record(0x85, struct.pack('<IBBBB',offset,0,0,1,0) + name)
    offset = len(bof + bounds(0,b'B') + bounds(0,b'A') + record(10))
    data = bof + bounds(offset+len(a),b'B') + bounds(offset,b'A') + record(10) + a + b
    xls.parse_biff_workbook(data)
    assert [s[(0,0)] for s in observed[0][1]['sheets']] == ['22','11']
    assert observed[0][1]['current_sheet'] == 1
    assert all(isinstance(d,memoryview) for d,_ in observed)


def test_chart_receives_formula_cache_separately_from_display(monkeypatch):
    seen = []
    def capture(data, **kwargs):
        seen.append(kwargs['formula_values'])
        return []
    monkeypatch.setattr(xls, 'parse_chart_substreams', capture)
    tokens = b'\x1e\x01\0'
    f = record(6, struct.pack('<3H',0,0,0) + b'\3'+b'\0'*5+b'\xff\xff' + struct.pack('<HIH',0,0,len(tokens))+tokens)
    xls.parse_biff_workbook(workbook(b'', f))
    assert seen == [[{(0,0):None}]]


def test_array_formula_anchor_and_follower_keep_template_and_cache():
    tokens = b'\x24' + struct.pack('<HH', 0, 0xC000)
    exp = b'\x01' + struct.pack('<HH',0,1)
    def formula(row, val):
        return record(6, struct.pack('<3H',row,1,0) + struct.pack('<d',val) + struct.pack('<HIH',0,0,len(exp)) + exp)
    array = record(0x221, struct.pack('<HHBBHIH',0,1,1,1,0,0,len(tokens)) + tokens)
    doc = xls.parse_biff_workbook(workbook(b'', formula(0,10) + array + formula(1,20)))
    assert doc.sections[0].elements[0].rows[0][1].text == '10 (=A1)'
    assert doc.sections[0].elements[0].rows[1][1].text == '20'


def test_rejected_cells_do_not_capture_font_metadata(monkeypatch):
    monkeypatch.setattr(xls, 'MAX_BIFF_DENSE_CELLS', 1)
    sheet = xls._SheetInfo('S', 0)
    xls._parse_sheet_records(labels(3), sheet, ['a'], {}, [], [], [], [],
                             fonts=[(True,False,False,False)], xf_fonts=[0])
    assert set(sheet.cell_fonts) == {(0,0)}
