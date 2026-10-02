from types import SimpleNamespace
import io
import struct

from dochan.model.document import Document, TextRun
from dochan.office_binary.doc_structure import StructureRenderer


class Binary:
    styles = {}
    warnings = []

    def __init__(self, text, props=None):
        self.text = text
        self.props = props or {}

    def char_props(self, cp):
        return self.props.get(cp, {})


class Stories:
    def hidden(self, cp):
        return False

    def markers(self, cp):
        return []

    def suffix(self, cp):
        return ''


class Pictures:
    def image_at(self, cp, props):
        return None


def render(text, props=None, paragraph_props=None):
    renderer = StructureRenderer(Binary(text, props), Document(), Stories(), Pictures())
    return renderer.paragraph(SimpleNamespace(start=0, end=len(text), text=text,
                                             props=paragraph_props or {}))


def test_doc_structure_formats_runs_and_filters_deleted_text():
    blocks = render('abcD\r', {0: {'bold': True}, 1: {'italic': True},
                             2: {'inserted': True}, 3: {'deleted': True}})
    assert blocks[0].text == 'abc'
    assert blocks[0].runs[0].bold
    assert blocks[0].runs[1].italic


def test_doc_structure_preserves_single_character_tabs_and_soft_breaks():
    assert render('A\tB\x0bC\r')[0].text == 'A\tB\nC'
    assert render('X\r')[0].text == 'X'


def test_doc_structure_heading_and_utf16_surrogates():
    block = render('\ud83d\ude00\r', paragraph_props={'istd': 9, 'heading_level': 9})[0]
    assert block.text == '\U0001f600'
    assert block.heading_level == 6
    assert block.style_id == 9


def test_doc_structure_note_markers_do_not_merge_into_plain_runs():
    stories = Stories()
    stories.markers = lambda cp: [TextRun('[1]', note_ref=1)] if cp == 1 else []
    text = 'A\x02B\r'
    renderer = StructureRenderer(Binary(text), Document(), stories, Pictures())
    blocks = renderer.paragraph(SimpleNamespace(start=0, end=4, text=text, props={}))
    assert blocks[0].text == 'A[1]B'
    assert blocks[0].runs[1].note_ref == 1


def test_doc_structure_image_is_between_adjacent_text_blocks():
    from dochan.model.image import Image
    pictures = Pictures()
    pictures.image_at = lambda cp, props: Image(image_data=b'png') if cp == 1 else None
    text = 'A\x01B\r'
    renderer = StructureRenderer(Binary(text), Document(), Stories(), pictures)
    blocks = renderer.paragraph(SimpleNamespace(start=0, end=4, text=text, props={}))
    assert blocks[0].text == 'A'
    assert isinstance(blocks[1], Image)
    assert blocks[2].text == 'B'


def test_doc_structure_textbox_appears_at_anchor_without_tail_duplicate():
    from dochan.model.document import Paragraph
    stories = Stories()
    stories.textbox = lambda index, render, header=False: [Paragraph(runs=[TextRun('Box')])]
    pictures = Pictures()
    pictures.textbox_at = lambda cp: 0 if cp == 1 else None
    text = 'A\x08B\r'
    binary = Binary(text)
    binary.stories = {'header': (4, 4)}
    renderer = StructureRenderer(binary, Document(), stories, pictures)
    blocks = renderer.paragraph(SimpleNamespace(start=0, end=4, text=text, props={}))
    assert [block.text for block in blocks] == ['A', 'Box', 'B']


def _native_streams():
    text = b'Native text\r'
    word = bytearray(2048)
    struct.pack_into('<HH', word, 0, 0xa5ec, 0xc1)
    struct.pack_into('<H', word, 32, 14)
    struct.pack_into('<H', word, 62, 22)
    struct.pack_into('<I', word, 76, len(text))
    struct.pack_into('<H', word, 152, 93)
    word[1024:1024 + len(text)] = text
    pcd = struct.pack('<IIHIH', 0, len(text), 0, 0x40000800, 0)
    table = b'\x02' + struct.pack('<I', len(pcd)) + pcd
    struct.pack_into('<II', word, 154 + 33 * 8, 0, len(table))
    return {'WordDocument': bytes(word), '0Table': table}


def _fake_reader(monkeypatch, tmp_path, streams):
    from dochan.office_binary.doc import DOCReader
    class Ole:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in streams

        def openstream(self, name):
            return io.BytesIO(streams[name])

        def close(self):
            pass
    monkeypatch.setattr('dochan.office_binary.doc.cfb.OleFileIO', Ole)
    path = tmp_path / 'native.doc'
    path.write_bytes(b'fake')
    return DOCReader().read(str(path))


def test_doc_structure_reader_uses_native_cp_path(monkeypatch, tmp_path):
    doc = _fake_reader(monkeypatch, tmp_path, _native_streams())
    assert doc.sections[0].elements[0].text == 'Native text'
    assert doc.sections[0].elements[0].provenance.path == 'WordDocument#cp0'
    assert doc.errors == []


def test_doc_structure_reader_falls_back_when_structure_raises(monkeypatch, tmp_path):
    def fail(*args):
        raise ValueError('damaged structure')
    monkeypatch.setattr('dochan.office_binary.doc_structure.parse_structured_doc', fail)
    doc = _fake_reader(monkeypatch, tmp_path, _native_streams())
    assert doc.sections[0].elements[0].text == 'Native text'
    assert any('WARN:' in error and 'text fallback' in error for error in doc.errors)


def test_doc_structure_reader_falls_back_on_invalid_fib_count(monkeypatch, tmp_path):
    streams = _native_streams()
    word = bytearray(streams['WordDocument'])
    struct.pack_into('<H', word, 152, 0xffff)
    streams['WordDocument'] = bytes(word)
    doc = _fake_reader(monkeypatch, tmp_path, streams)
    assert doc.sections[0].elements[0].text == 'Native text'
    assert any('WARN:' in error and 'text fallback' in error for error in doc.errors)
