"""Synthetic embedded object streams; external corpus is never needed in CI."""
import io
import struct
import zlib

from dochan.conversion import Provenance
from dochan.office_binary.ole_objects import (
    EmbeddedObjects, DocObjects, decompress_ppt_storage, parse_embedded_chart,
)


def rec(sid, data=b''):
    return struct.pack('<HH', sid, len(data)) + data


def chart(graph=False):
    bof = rec(0x809, struct.pack('<HH', 0x680 if graph else 0x600, 0x8000 if graph else 0x20))
    data = b''
    if graph:
        data = rec(0x1052, b'\x01\x02\x10\0') + rec(0x1033)
        data += rec(0x1055, b'\x01\0\0\0\0\x01')
        for row, col, value in [(0, 1, 2000), (1, 1, 12), (0, 2, 2001), (1, 2, 18)]:
            data += rec(3, struct.pack('<HH3sd', row, col, b'\0'*3, value))
        data += rec(0x1034)
    data += rec(0x1003, struct.pack('<6H', 1, 1, 2, 2, 1, 0)) + rec(0x1033)
    data += rec(0x100d, b'\0\0\x05\0Sales')
    if graph:
        data += rec(0x1051, struct.pack('<BBHHH', 1, 1, 2, 0, 1))
        data += rec(0x1051, struct.pack('<BBHHH', 2, 1, 2, 0, 0))
    data += rec(0x1034) + rec(0x1017, b'\0'*6)
    data += rec(0x1025, b'\0'*32) + rec(0x1033)
    data += rec(0x100d, b'\0\0\x06\0Annual') + rec(0x1027, struct.pack('<3H', 1, 0, 0)) + rec(0x1034)
    if not graph:
        data += rec(0x1065, b'\x01\0')
        data += rec(0x203, struct.pack('<HHHd', 0, 0, 0, 12))
        data += rec(0x203, struct.pack('<HHHd', 1, 0, 0, 18))
    return bof + data + rec(10)


def rows(table):
    return [[c.text for c in row] for row in table.rows]


def test_embedded_biff_chart_matches_ooxml_title_table_contract():
    errors = []
    out = parse_embedded_chart(chart(), errors)
    assert out[0].text == 'Annual' and out[0].heading_level == 3
    assert rows(out[1]) == [['Category', 'Sales'], ['1', '12'], ['2', '18']]
    assert out[1].caption[0].text == 'Chart type: column'
    assert not errors


def test_msgraph_chart_datasheet_becomes_shared_chart_cache():
    errors = []
    out = parse_embedded_chart(chart(True), errors, graph=True)
    assert out[0].text == 'Annual'
    assert rows(out[1]) == [['Category', 'Sales'], ['2000', '12'], ['2001', '18']]
    assert not errors


def test_ppt_storage_size_and_zlib_completion_are_checked():
    raw = b'embedded compound file'
    assert decompress_ppt_storage(struct.pack('<I', len(raw)) + zlib.compress(raw), 1) == raw
    assert decompress_ppt_storage(raw, 0) == raw
    import pytest
    for data in [struct.pack('<I', 1) + zlib.compress(raw),
                 struct.pack('<I', len(raw)) + zlib.compress(raw)[:-1],
                 struct.pack('<I', 0xffffffff) + zlib.compress(raw)]:
        with pytest.raises(ValueError):
            decompress_ppt_storage(data, 1)


class Ole:
    def __init__(self, streams):
        self.streams = streams

    def exists(self, path):
        return '/'.join(path) in self.streams if isinstance(path, list) else path in self.streams

    def openstream(self, path):
        return io.BytesIO(self.streams['/'.join(path) if isinstance(path, list) else path])


def test_doc_objectpool_uses_field_separator_id_not_picture_offset():
    from types import SimpleNamespace
    streams = {'ObjectPool/_77/Workbook': chart()}
    binary = SimpleNamespace(text='\x13 EMBED Excel.Chart.8 \x14\x01\x15',
                             char_props=lambda cp: {'pic_location': 77 if cp == 22 else 400})
    field = SimpleNamespace(start=0, separator=22, end=24, instruction=' EMBED Excel.Chart.8 ')
    resolver = DocObjects(Ole(streams), binary, [field], [])
    out = resolver.at(23, {}, Provenance(source_format='doc', path='WordDocument#cp23'))
    assert out[0].text == 'Annual'
    assert out[1].rows[0][0].provenance.source_format == 'doc'
    assert 'ObjectPool/_77' in out[1].rows[0][0].provenance.path
    assert resolver.at(400, {'pic_location': 77}, None) == []


def test_unknown_equation_warns_and_leaves_preview_available():
    errors = []
    pool = EmbeddedObjects(errors)
    out = pool.read(Ole({'Equation Native': b'bad'}), [], Provenance(source_format='ppt'))
    assert out == []
    assert errors and all(e.startswith('WARN:') for e in errors)


def compound(stream_name, content):
    """Minimal real CFB v3 with one regular stream (no external fixture)."""
    size = max(4096, ((len(content) + 511) // 512) * 512)
    sectors = size // 512
    header = bytearray(512)
    header[:8] = bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<HHHH', header, 24, 0x3e, 3, 0xfffe, 9)
    struct.pack_into('<H', header, 32, 6)
    struct.pack_into('<IIIIIIIII', header, 40, 0, 1, 0, 0, 4096,
                     0xfffffffe, 0, 0xfffffffe, 0)
    struct.pack_into('<109I', header, 76, 1, *([0xffffffff] * 108))
    directory = bytearray(512)
    for index, name, kind, child, start, length in [
            (0, 'Root Entry', 5, 1, 0xfffffffe, 0),
            (1, stream_name, 2, 0xffffffff, 2, size)]:
        off = index * 128
        encoded = (name + '\0').encode('utf-16le')
        directory[off:off + len(encoded)] = encoded
        struct.pack_into('<HBBIII', directory, off + 64, len(encoded), kind, 1,
                         0xffffffff, 0xffffffff, child)
        struct.pack_into('<IQ', directory, off + 116, start, length)
    fat = [0xfffffffe, 0xfffffffd] + list(range(3, 2 + sectors)) + [0xfffffffe]
    fat.extend([0xffffffff] * (128 - len(fat)))
    return bytes(header) + bytes(directory) + struct.pack('<128I', *fat) + content.ljust(size, b'\0')


def test_ppt_chart_uses_latest_storage_and_shape_position():
    from test_ppt_structure import record, presentation, slide_list, shape, sheet
    from dochan.office_binary.ppt import parse_ppt_document_stream
    raw = compound('Workbook', chart())
    storage = record(4113, struct.pack('<I', len(raw)) + zlib.compress(raw), instance=1)
    ref = record(0xF004, record(0xF00A, struct.pack('<II', 1026, 0xA00))
                 + record(0xF010, struct.pack('<4h', 100, 0, 100, 200))
                 + record(0xF011, record(3009, struct.pack('<I', 77))), container=True)
    embedded = record(4035, struct.pack('<6I', 1, 0, 77, 0, 3, 0))
    data, current = presentation(
        [(2, sheet(shapes=shape(b'Before', y=0) + ref + shape(b'After', y=300))),
         (3, record(4113, b'old damaged storage'))],
        [slide_list([(2, 256, b'')]), record(1033, embedded, container=True)],
        previous=(3, storage))
    doc = parse_ppt_document_stream(data, current_user=current)
    out = doc.sections[0].elements
    assert [getattr(e, 'text', type(e).__name__) for e in out] == ['Before', 'Annual', 'Table', 'After']
    assert rows(out[2])[1:] == [['1', '12'], ['2', '18']]
    assert out[2].rows[0][0].provenance.slide == 1
    assert not doc.errors


def test_doc_equation_is_between_text_and_unsupported_keeps_image():
    from types import SimpleNamespace
    from test_doc_structure import Binary, Stories, Pictures
    from test_mtef import char, mtef, native
    from dochan.model.document import Document
    from dochan.model.image import Image
    from dochan.office_binary.doc_structure import StructureRenderer
    from dochan.model.equation import Equation
    text = 'Before\x01After\r'
    binary = Binary(text)
    field = SimpleNamespace(separator=5, end=7, instruction=' EMBED Equation.3 ')
    binary.props = {5: {'pic_location': 77}}
    for content, kind in [(native(mtef(char('x=2'))), Equation), (b'bad', Image)]:
        doc = Document()
        objects = DocObjects(Ole({'ObjectPool/_77/Equation Native': content}), binary, [field], doc.errors)
        pictures = Pictures()
        pictures.image_at = lambda cp, props: Image(image_data=b'preview')
        renderer = StructureRenderer(binary, doc, Stories(), pictures, objects)
        out = renderer.paragraph(SimpleNamespace(start=0, end=len(text), props={}))
        assert out[0].text == 'Before' and out[-1].text == 'After'
        assert isinstance(out[1], kind)
        if kind is Equation:
            assert out[1].latex == 'x=2' and not doc.errors
        else:
            assert out[1].image_data == b'preview' and doc.errors


def test_only_active_excel_chart_sheet_is_rendered():
    first = chart().replace(b'Annual', b'Hidden')
    second = chart()
    bof = rec(0x809, struct.pack('<HH', 0x600, 5))
    window = rec(0x3d, b'\0' * 10 + struct.pack('<H', 1))
    # Two minimal BoundSheet records, each four offset + two flag bytes.
    start = len(bof + window) + 2 * 10 + 4
    data = bof + window + rec(0x85, struct.pack('<IBB', start, 0, 2))
    data += rec(0x85, struct.pack('<IBB', start + len(first), 0, 2)) + rec(10) + first + second
    out = parse_embedded_chart(data, [])
    assert [e.text for e in out if hasattr(e, 'heading_level')] == ['Annual']


def test_graph_column_series_and_ascii_labels_with_unicode_codepage():
    data = chart(True).replace(rec(0x1055, b'\x01\0\0\0\0\x01'),
                              rec(0x1055, b'\0\0\0\0\0\x01'))
    # Transpose the datasheet records; orientation alone must not swap values.
    from dochan.office_binary.ole_objects import _records
    parts = []
    for _, sid, payload in _records(data):
        if sid == 3:
            row, col = struct.unpack_from('<HH', payload)
            payload = struct.pack('<HH', col, row) + payload[4:]
        parts.append(rec(sid, payload))
    out = parse_embedded_chart(b''.join(parts), [], graph=True)
    assert rows(out[1]) == [['Category', 'Sales'], ['2000', '12'], ['2001', '18']]


def test_embedded_limits_and_truncation_warn_instead_of_failing_document(monkeypatch):
    import dochan.office_binary.ole_objects as module
    errors = []
    monkeypatch.setattr(module, 'MAX_OBJECT_BYTES', 32)
    assert parse_embedded_chart(chart(), errors) == []
    assert errors
    errors.clear()
    assert parse_embedded_chart(b'\x09\x08\x10\0short', errors) == []
    pool = EmbeddedObjects(errors)
    pool.remaining = 0
    assert pool.read(Ole({'Workbook': chart()}), [], None) == []
    assert all(e.startswith('WARN:') for e in errors)


def test_doc_unreadable_equation_without_preview_retains_text_marker():
    from types import SimpleNamespace
    from test_doc_structure import Binary, Stories, Pictures
    from dochan.model.document import Document
    from dochan.office_binary.doc_structure import StructureRenderer
    text = 'A\x01B\r'
    binary = Binary(text, {0: {'pic_location': 1}})
    doc = Document()
    objects = DocObjects(Ole({'ObjectPool/_1/Equation Native': b'bad'}), binary,
                         [SimpleNamespace(separator=0, end=2, instruction=' EMBED Equation.3 ')], doc.errors)
    out = StructureRenderer(binary, doc, Stories(), Pictures(), objects).paragraph(
        SimpleNamespace(start=0, end=len(text), props={}))
    assert [e.text for e in out] == ['A', '[내장 수식]', 'B']


def test_multiple_graph_substreams_do_not_reuse_previous_datasheet():
    errors = []
    assert parse_embedded_chart(chart(True) + chart(True), errors, graph=True) == []
    assert any('multiple' in e for e in errors)


def test_ppt_unsupported_equation_keeps_preview_and_surrounding_text():
    from test_ppt_structure import record, presentation, slide_list, shape, sheet
    from dochan.office_binary.ppt import parse_ppt_document_stream
    from dochan.office_binary.officeart import parse_records
    raw_shape = shape(pib=1, description='Equation preview', y=100)
    payload = bytes(parse_records(raw_shape)[0].data) + record(0xF011, record(3009, struct.pack('<I', 77)))
    ref = record(0xF004, payload, container=True)
    embedded = record(4035, struct.pack('<6I', 1, 0, 77, 0, 3, 0))
    data, current = presentation(
        [(2, sheet(shapes=shape(b'Before', y=0) + ref + shape(b'After', y=300))),
         (3, record(4113, compound('Equation Native', b'unsupported')))],
        [slide_list([(2, 256, b'')]), record(1033, embedded, container=True)])
    doc = parse_ppt_document_stream(data, current_user=current)
    paragraphs = doc.find_all('paragraph')
    # The preview is an Image at the shape position, not a duplicate Markdown
    # paragraph (office-fix2 image-output regression).
    assert [p.text for p in paragraphs] == ['Before', 'After']
    assert [type(e).__name__ for e in doc.sections[0].elements] == ['Paragraph', 'Image', 'Paragraph']
    assert doc.find_all('image')[0].alt_text == 'Equation preview'
    assert doc.find_all('image') and not doc.find_all('equation')
    assert doc.errors and all(e.startswith('WARN:') for e in doc.errors)
