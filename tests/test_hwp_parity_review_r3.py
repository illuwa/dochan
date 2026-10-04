"""Synthetic records for the public HWP/HWPX parity review."""

import struct

from dochan.constants import (
    HWPTAG_CTRL_HEADER, HWPTAG_LIST_HEADER, HWPTAG_PARA_HEADER,
    HWPTAG_PARA_TEXT, HWPTAG_TABLE,
)
from dochan.hwp.section import SectionParser
from dochan.model.document import Document
from dochan.model.header_footer import Footnote
from dochan.model.table import Table
from dochan.output.markdown import to_markdown


def _rec(tag, level, data):
    return struct.pack('<I', (len(data) << 20) | (level << 10) | tag) + data


def _text(value):
    return value.encode('utf-16-le') + struct.pack('<H', 13)


def _note_marker(ctrl_id):
    return struct.pack('<H', 17) + ctrl_id + bytes(8) + struct.pack('<H', 17)


def _note_control(level, ctrl_id, body):
    return (_rec(HWPTAG_CTRL_HEADER, level, ctrl_id + bytes(8)) +
            _rec(HWPTAG_LIST_HEADER, level + 1, bytes(8)) +
            _rec(HWPTAG_PARA_HEADER, level + 1, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, level + 2, _text(body)))


def test_caption_direction_uses_low_bits_of_list_header_attribute():
    caption_attr = 0x006f0042  # TOP in bits 0-1; other bits are set.
    data = (_rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 1, _text('앞')) +
            _rec(HWPTAG_CTRL_HEADER, 1, b' lbt' + bytes(8)) +
            _rec(HWPTAG_LIST_HEADER, 2, struct.pack('<III', 1, 0, caption_attr) + bytes(18)) +
            _rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 3, _text('위 캡션')) +
            _rec(HWPTAG_TABLE, 2, bytes(4) + struct.pack('<HH', 1, 1)) +
            _rec(HWPTAG_LIST_HEADER, 2, bytes(8) + struct.pack('<HHHH', 0, 0, 1, 1)) +
            _rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 3, _text('셀')))
    section = SectionParser().parse_stream(data, False)
    table = next(e for e in section.elements if isinstance(e, Table))
    assert table.caption_side == 'TOP'


def test_footnote_inside_table_cell_is_preserved():
    data = (_rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 1, _text('앞')) +
            _rec(HWPTAG_CTRL_HEADER, 1, b' lbt' + bytes(8)) +
            _rec(HWPTAG_TABLE, 2, bytes(4) + struct.pack('<HH', 1, 1)) +
            _rec(HWPTAG_LIST_HEADER, 2, bytes(8) + struct.pack('<HHHH', 0, 0, 1, 1)) +
            _rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 3, '셀'.encode('utf-16-le') +
                 _note_marker(b'  nf') + _text('뒤')) +
            _note_control(3, b'  nf', '셀 주석'))
    section = SectionParser().parse_stream(data, False)
    table = next(e for e in section.elements if isinstance(e, Table))
    assert [type(e) for e in table.rows[0][0].paragraphs][-1] is Footnote
    assert '셀[^1]뒤' in to_markdown(Document(sections=[section]))
    assert '[^1]: 셀 주석' in to_markdown(Document(sections=[section]))


def test_endnote_reference_is_inline_with_original_text():
    data = (_rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 1, '앞'.encode('utf-16-le') +
                 _note_marker(b'  ne') + _text('뒤')) +
            _note_control(1, b'  ne', '미주 본문'))
    section = SectionParser().parse_stream(data, False)
    paragraph, note = section.elements
    assert paragraph.text == '앞[1]뒤'
    assert [(run.text, run.note_ref) for run in paragraph.runs] == [
        ('앞', 0), ('[1]', 1), ('뒤', 0)]
    assert (note.type, note.number) == ('endnote', 1)
    assert to_markdown(Document(sections=[section])) == '앞[^1]뒤\n\n[^1]: 미주 본문'


def test_note_only_paragraph_keeps_reference():
    data = (_rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 1, _note_marker(b'  nf') + struct.pack('<H', 13)) +
            _note_control(1, b'  nf', '단독 각주'))
    section = SectionParser().parse_stream(data, False)
    assert to_markdown(Document(sections=[section])) == '[^1]\n\n[^1]: 단독 각주'
