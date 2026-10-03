"""Synthetic HWP GSO and embedded CFB chart fixtures."""
import io
import struct
import zlib

from dochan.constants import (HWPTAG_CTRL_HEADER, HWPTAG_LIST_HEADER,
                              HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT,
                              HWPTAG_SHAPE_COMPONENT, HWPTAG_SHAPE_COMP_OLE,
                              HWPTAG_TABLE)
from dochan.hwp.bin_data import BinDataItem, extract_bin_data
from dochan.hwp.charts import ChartReference, discard_chart_references, resolve_charts
from dochan.hwp.doc_info import BinDataEntry, DocInfo, DocInfoParser
from dochan.hwp.section import SectionParser
from dochan.model.document import Document
from dochan.model.table import Table


END = 0xfffffffe
FREE = 0xffffffff
FAT = 0xfffffffd


def _entry(name, kind, start=END, size=0, child=FREE):
    data = bytearray(128)
    encoded = (name + '\0').encode('utf-16le')
    data[:len(encoded)] = encoded
    struct.pack_into('<HBBIII', data, 64, len(encoded), kind, 1, FREE, FREE, child)
    struct.pack_into('<IQ', data, 116, start, size)
    return data


def _chart_cfb(xml):
    xml += b' ' * max(0, 4096 - len(xml))
    sectors = (len(xml) + 511) // 512
    header = bytearray(512)
    header[:8] = bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<5H', header, 24, 0x3e, 3, 0xfffe, 9, 6)
    struct.pack_into('<9I', header, 40, 0, 1, 0, 0, 4096, END, 0, END, 0)
    struct.pack_into('<I', header, 76, 1)
    directory = bytearray(512)
    directory[:256] = _entry('Root Entry', 5, child=1) + _entry('OOXMLChartContents', 2, 2, len(xml))
    fat = [END, FAT] + list(range(3, 2 + sectors)) + [END]
    fat += [FREE] * (128 - len(fat))
    return bytes(header) + bytes(directory) + struct.pack('<128I', *fat) + xml.ljust(sectors * 512, b'\0')


def _record(tag, level, data):
    return struct.pack('<I', (len(data) << 20) | (level << 10) | tag) + data


def _section(bin_id=1):
    ole = bytearray(30)
    struct.pack_into('<H', ole, 12, bin_id)
    data = (_record(HWPTAG_PARA_HEADER, 0, bytes(22)) +
            _record(HWPTAG_PARA_TEXT, 1, '앞'.encode('utf-16le') + b'\r\0') +
            _record(HWPTAG_CTRL_HEADER, 1, b' osg' + bytes(42)) +
            _record(HWPTAG_SHAPE_COMPONENT, 2, b'elo$' + bytes(192)) +
            _record(HWPTAG_SHAPE_COMP_OLE, 3, bytes(ole)) +
            _record(HWPTAG_PARA_HEADER, 0, bytes(22)) +
            _record(HWPTAG_PARA_TEXT, 1, '뒤'.encode('utf-16le') + b'\r\0'))
    return SectionParser().parse_stream(data, False)


def _xml():
    return (b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            b'<c:chart><c:title><c:tx><c:v>Title</c:v></c:tx></c:title><c:plotArea>'
            b'<c:barChart><c:ser><c:order val="0"/><c:tx><c:v>Sales</c:v></c:tx>'
            b'<c:cat><c:strLit><c:ptCount val="1"/><c:pt idx="0"><c:v>A</c:v>'
            b'</c:pt></c:strLit></c:cat><c:val><c:numLit><c:ptCount val="1"/>'
            b'<c:pt idx="0"><c:v>2</c:v></c:pt></c:numLit></c:val></c:ser>'
            b'</c:barChart></c:plotArea></c:chart></c:chartSpace>')


def _resolve(payload, bin_id=1):
    doc = Document(sections=[_section(bin_id)])
    item = BinDataItem(storage_id=1, data=payload, extension='ole')
    resolve_charts(doc, {1: item}, [BinDataEntry(type=2, bin_data_id=1)])
    return doc


def test_gso_ole_chart_in_body_order_with_hwpx_output_contract():
    cfb = _chart_cfb(_xml())
    doc = _resolve(struct.pack('<I', len(cfb)) + cfb)
    assert [type(item).__name__ for item in doc.sections[0].elements] == [
        'Paragraph', 'Paragraph', 'Table', 'Paragraph']
    table = doc.find_all('table')[0]
    assert isinstance(table, Table)
    assert [[cell.text for cell in row] for row in table.rows] == [
        ['범주', 'Sales'], ['A', '2']]
    assert doc.sections[0].elements[1].text == 'Title'
    assert doc.sections[0].elements[1].heading_level == 3
    assert table.caption_side == 'TOP'
    assert table.caption_text == 'Chart type: column'
    assert doc.errors == []


def test_truncated_or_invalid_embedded_chart_only_warns():
    cfb = _chart_cfb(_xml())
    for payload in (struct.pack('<I', len(cfb) + 1) + cfb,
                    struct.pack('<I', 10) + b'bad'):
        doc = _resolve(payload)
        assert doc.find_all('table') == []
        assert [p.text for p in doc.find_all('paragraph')] == ['앞', '뒤']
        assert any('WARN:' in error for error in doc.errors)


def test_oversized_and_nested_cfb_are_rejected_without_expansion():
    cfb = _chart_cfb(_xml())
    nested = _chart_cfb(cfb)
    for payload in (struct.pack('<I', 0xffffffff) + b'x',
                    struct.pack('<I', len(nested)) + nested):
        doc = _resolve(payload)
        assert doc.find_all('table') == []
        assert any('WARN:' in error for error in doc.errors)


def test_oversized_embedded_cfb_is_rejected_before_parser(monkeypatch):
    from dochan.hwp import charts
    calls = []
    monkeypatch.setattr(charts.cfb, 'OleFileIO', lambda *a, **k: calls.append(1))
    payload = b'x' * (charts.MAX_CHART_CFB_BYTES + 1)
    doc = _resolve(struct.pack('<I', len(payload)) + payload)
    assert calls == []
    assert doc.find_all('table') == []
    assert any('size limit' in warning for warning in doc.errors)


def test_many_ole_records_are_bounded():
    parser = SectionParser()
    ole = bytearray(30)
    struct.pack_into('<H', ole, 12, 1)
    prefix = (_record(HWPTAG_PARA_HEADER, 0, bytes(22)) +
              _record(HWPTAG_CTRL_HEADER, 1, b' osg' + bytes(42)) +
              _record(HWPTAG_SHAPE_COMPONENT, 2, b'elo$' + bytes(192)))
    section = parser.parse_stream(prefix + _record(HWPTAG_SHAPE_COMP_OLE, 3, ole) * 20000, False)
    assert len(section.elements) <= 256
    assert any('chart' in error.lower() for error in parser.errors)


def test_oversized_inflated_ole_is_a_warning_not_document_failure():
    class Ole:
        def listdir(self):
            return [['BinData', 'BIN0001.OLE']]

        def openstream(self, name):
            compressor = zlib.compressobj(wbits=-15)
            return io.BytesIO(compressor.compress(b'x' * 4096) + compressor.flush())

    errors = []
    assert extract_bin_data(Ole(), True, max_item_size=128,
                            max_total_size=128, warnings=errors) == {}
    assert errors and errors[0].startswith('WARN:')


def test_tens_of_thousands_of_ole_streams_have_read_count_cap():
    class Ole:
        calls = 0

        def listdir(self):
            return [['BinData', 'BIN%04X.OLE' % i] for i in range(1, 20001)]

        def openstream(self, name):
            self.calls += 1
            return io.BytesIO(b'')

    ole = Ole()
    errors = []
    items = extract_bin_data(ole, False, warnings=errors)
    assert len(items) == 256
    assert ole.calls == 256
    assert errors == ['WARN: HWP embedded OLE item count limit exceeded']


def test_storage_entry_id_selects_current_chart_not_old_slot():
    info = DocInfo()
    DocInfoParser()._parse_bin_data(struct.pack('<HH', 2, 3), info)
    assert info.bin_data_entries[0].bin_data_id == 3
    cfb = _chart_cfb(_xml())
    payload = struct.pack('<I', len(cfb)) + cfb
    doc = Document(sections=[_section(1)])
    resolve_charts(doc, {1: BinDataItem(1, b'bad', 'ole'),
                         3: BinDataItem(3, payload, 'ole')}, info.bin_data_entries)
    assert len(doc.find_all('table')) == 1
    assert doc.errors == []


def test_chart_reference_in_table_cell_and_caption_survives_parse():
    parser = SectionParser()
    para = {'record': type('R', (), {'tag_id': HWPTAG_PARA_HEADER})(), 'children': []}
    parser._parse_paragraph_group = lambda node: [ChartReference(1)]
    cell = parser._parse_cell_info_impl({'children': [para], 'cell_info': {}})
    assert cell['paragraphs'] == [ChartReference(1)]
    caption = parser._parse_table_caption([{'record': type('R', (), {'data': bytes(12)})(),
                                            'children': [para]}])
    assert caption[0] == [ChartReference(1)]


def test_chart_in_table_cell_is_rendered_at_cell_position():
    def ole(level):
        payload = bytearray(30)
        struct.pack_into('<H', payload, 12, 1)
        return (_record(HWPTAG_CTRL_HEADER, level, b' osg' + bytes(42)) +
                _record(HWPTAG_SHAPE_COMPONENT, level + 1, b'elo$' + bytes(192)) +
                _record(HWPTAG_SHAPE_COMP_OLE, level + 2, payload))

    cell_header = bytes(8) + struct.pack('<HHHH', 0, 0, 1, 1)
    raw = (_record(HWPTAG_PARA_HEADER, 0, bytes(22)) +
           _record(HWPTAG_CTRL_HEADER, 1, b' lbt' + bytes(4)) +
           _record(HWPTAG_TABLE, 2, bytes(4) + struct.pack('<HH', 1, 1)) +
           _record(HWPTAG_LIST_HEADER, 2, cell_header) +
           _record(HWPTAG_PARA_HEADER, 2, bytes(22)) + ole(3))
    section = SectionParser().parse_stream(raw, False)
    doc = Document(sections=[section])
    cfb = _chart_cfb(_xml())
    resolve_charts(doc, {1: BinDataItem(1, struct.pack('<I', len(cfb)) + cfb, 'ole')},
                   [BinDataEntry(type=2, bin_data_id=1)])
    outer = section.elements[0]
    assert isinstance(outer, Table)
    assert isinstance(outer.rows[0][0].paragraphs[-1], Table)
    assert len(doc.find_all('table')) == 2


def test_repeated_chart_storage_opens_once_with_distinct_models(monkeypatch):
    from dochan.hwp import charts
    cfb = _chart_cfb(_xml())
    payload = struct.pack('<I', len(cfb)) + cfb
    doc = Document(sections=[_section(1)])
    doc.sections[0].elements.extend([ChartReference(1)] * 4)
    original = charts.cfb.OleFileIO
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(charts.cfb, 'OleFileIO', counted)
    resolve_charts(doc, {1: BinDataItem(1, payload, 'ole')},
                   [BinDataEntry(type=2, bin_data_id=1)])
    assert len(calls) == 1
    tables = doc.find_all('table')
    assert len(tables) == 5
    assert len({id(table) for table in tables}) == 5


def test_embedded_ole_stream_bounded_error_warns_and_skips_only_item():
    class Ole:
        def listdir(self):
            return [['BinData', 'BIN0001.OLE'], ['BinData', 'BIN0002.png']]

        def get_size(self, name):
            return 200 if name.endswith('OLE') else 1

        def openstream(self, name):
            return io.BytesIO(b'x')

    warnings = []
    items = extract_bin_data(Ole(), False, max_item_size=128, warnings=warnings)
    assert set(items) == {2}
    assert len(warnings) == 1 and 'stream(s)' in warnings[0]


def test_failed_chart_resolution_removes_nested_temporary_markers():
    from dochan.model.table import Cell
    cell = Cell(paragraphs=[ChartReference(1)])
    table = Table(rows=[[cell]], caption=[ChartReference(1)])
    doc = Document(sections=[_section(1)])
    doc.sections[0].elements.append(table)
    discard_chart_references(doc)
    assert all(not isinstance(block, ChartReference)
               for block in doc.sections[0].elements + cell.paragraphs + table.caption)


def test_deep_nesting_discards_all_transient_chart_markers():
    from dochan.model.table import Cell
    nested = [ChartReference(1)]
    for _ in range(40):
        nested = [Table(rows=[[Cell(paragraphs=nested)]])]
    doc = Document(sections=[_section(1)])
    doc.sections[0].elements.extend(nested)
    resolve_charts(doc, {}, [BinDataEntry(type=2, bin_data_id=1)])
    inner = nested[0]
    for _ in range(39):
        inner = inner.rows[0][0].paragraphs[0]
    assert inner.rows[0][0].paragraphs == []


def test_reader_bindata_failure_does_not_publish_unknown_chart_marker(monkeypatch):
    from types import SimpleNamespace
    from dochan import reader as reader_module
    from dochan.output.json_out import to_dict
    from dochan.utils.bounded_io import ResourceLimitError

    class Ole:
        def exists(self, name):
            return True

        def close(self):
            pass

    class Header:
        is_encrypted = False
        is_drm = False
        is_compressed = False
        is_track_change = False
        is_distribution = False
        body_storage = 'BodyText'

        def validate(self):
            return []

    class Parser:
        errors = []
        _document_cells = 0

        def __init__(self, **kwargs):
            pass

        def parse_stream(self, *args, **kwargs):
            return _section(1)

    info = DocInfo()
    info.section_count = 1
    info.bin_data_entries = [BinDataEntry(type=2, bin_data_id=1)]
    monkeypatch.setattr(reader_module, 'validate_file_size', lambda *a: None)
    monkeypatch.setattr(reader_module.cfb, 'OleFileIO', lambda *a: Ole())
    monkeypatch.setattr(reader_module, 'read_ole_stream', lambda *a, **k: bytes(256))
    monkeypatch.setattr(reader_module.FileHeader, 'parse', lambda *a: Header())
    monkeypatch.setattr(reader_module, 'DocInfoParser',
                        lambda: SimpleNamespace(parse_stream=lambda *a: info))
    monkeypatch.setattr(reader_module, 'SectionParser', Parser)
    monkeypatch.setattr(reader_module, 'append_recovery_warnings', lambda *a: None)
    monkeypatch.setattr(reader_module, 'extract_bin_data',
                        lambda *a, **k: (_ for _ in ()).throw(ResourceLimitError('budget')))
    reader = reader_module.Dochan.__new__(reader_module.Dochan)
    reader.file_path = 'synthetic.hwp'
    reader._revision_mode = 'preserve'
    reader.doc = Document()
    reader._hwp_section_indices = lambda *a: [0]
    reader._parse_hwp()
    assert not any(type(block).__name__ == 'ChartReference'
                   for block in reader.doc.sections[0].elements)
    assert 'unknown' not in str(to_dict(reader.doc))
    assert any('WARN:' in error for error in reader.doc.errors)


def test_chart_tables_share_existing_document_cell_limit():
    cfb = _chart_cfb(_xml())
    payload = struct.pack('<I', len(cfb)) + cfb
    doc = Document(sections=[_section(1)])
    resolve_charts(doc, {1: BinDataItem(1, payload, 'ole')},
                   [BinDataEntry(type=2, bin_data_id=1)], existing_cells=200000)
    assert doc.find_all('table') == []
    assert any('cell limit' in warning for warning in doc.errors)


def test_chart_document_byte_budget_is_not_reported_as_unreadable(monkeypatch):
    from dochan.hwp import charts
    monkeypatch.setattr(charts, 'MAX_DOCUMENT_CHART_XML_BYTES', 1)
    cfb = _chart_cfb(_xml())
    doc = _resolve(struct.pack('<I', len(cfb)) + cfb)
    assert doc.find_all('table') == []
    assert doc.errors == ['WARN: HWP chart document byte budget exhausted']


def test_excel_chart_8_reuses_embedded_workbook_chart_parser(monkeypatch):
    from dochan.hwp import charts
    from dochan.model.table import Cell

    class EmbeddedOle:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def listdir(self):
            return [['\x01CompObj'], ['Workbook']]

        def exists(self, name):
            return name in ('\x01CompObj', 'Workbook')

        def get_size(self, name):
            return len(b'Excel.Chart.8\0') if name == '\x01CompObj' else len(b'workbook')

        def openstream(self, name):
            return io.BytesIO(b'Excel.Chart.8\0' if name == '\x01CompObj' else b'workbook')

    calls = []

    def parse(data, errors, graph=False, budget=None, chart_object=False):
        calls.append((data, graph, chart_object))
        return [Table(rows=[[Cell(paragraphs=[])]])]

    monkeypatch.setattr(charts.cfb, 'OleFileIO', lambda *a, **k: EmbeddedOle())
    monkeypatch.setattr(charts, 'parse_embedded_chart', parse, raising=False)
    doc = Document(sections=[_section(1)])
    resolve_charts(doc, {1: BinDataItem(1, struct.pack('<I', 3) + b'cfb', 'ole')},
                   [BinDataEntry(type=2, bin_data_id=1)])
    assert calls == [(b'workbook', False, True)]
    assert len(doc.find_all('table')) == 1
