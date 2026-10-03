"""Synthetic HWP GSO and embedded CFB chart fixtures."""
import io
import struct
import zlib

from dochan.constants import (HWPTAG_CTRL_HEADER, HWPTAG_PARA_HEADER,
                              HWPTAG_PARA_TEXT, HWPTAG_SHAPE_COMPONENT,
                              HWPTAG_SHAPE_COMP_OLE)
from dochan.hwp.bin_data import BinDataItem, extract_bin_data
from dochan.hwp.charts import resolve_charts
from dochan.hwp.doc_info import BinDataEntry
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
    resolve_charts(doc, {1: item}, [BinDataEntry(type=2)])
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
