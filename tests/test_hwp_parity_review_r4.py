"""PARA_TEXT block anchors must preserve the source paragraph order."""

import struct
from types import SimpleNamespace

from dochan.constants import (
    HWPTAG_CTRL_DATA, HWPTAG_CTRL_HEADER, HWPTAG_EQEDIT, HWPTAG_LIST_HEADER,
    HWPTAG_PARA_CHAR_SHAPE, HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_TABLE,
)
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import SectionParser
from dochan.model.document import Paragraph
from dochan.model.header_footer import HeaderFooter
from dochan.model.table import Table


def _rec(tag, level, data):
    return struct.pack('<I', (len(data) << 20) | (level << 10) | tag) + data


def _anchor(code, ctrl_id):
    return struct.pack('<H', code) + ctrl_id + bytes(8) + struct.pack('<H', code)


def _table(value):
    return (_rec(HWPTAG_CTRL_HEADER, 1, b' lbt' + bytes(8)) +
            _rec(HWPTAG_TABLE, 2, bytes(4) + struct.pack('<HH', 1, 1)) +
            _rec(HWPTAG_LIST_HEADER, 2, bytes(8) + struct.pack('<HHHH', 0, 0, 1, 1)) +
            _rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 3, (value + '\r').encode('utf-16-le')))


def _parse(text, controls):
    return SectionParser().parse_stream(
        _rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        _rec(HWPTAG_PARA_TEXT, 1, text + b'\r\x00') + controls, False).elements


def test_table_anchor_before_text_precedes_paragraph():
    elements = _parse(_anchor(11, b' lbt') + '뒤'.encode('utf-16-le'), _table('셀'))
    assert [type(e) for e in elements] == [Table, Paragraph]
    assert elements[1].text == '뒤'


def test_table_anchor_splits_text_at_original_position():
    elements = _parse('앞'.encode('utf-16-le') + _anchor(11, b' lbt') +
                      '뒤'.encode('utf-16-le'), _table('셀'))
    assert [type(e) for e in elements] == [Paragraph, Table, Paragraph]
    assert [e.text for e in elements if isinstance(e, Paragraph)] == ['앞', '뒤']


def test_multiple_table_anchors_keep_text_between_tables():
    elements = _parse(_anchor(11, b' lbt') + '사이'.encode('utf-16-le') +
                      _anchor(11, b' lbt') + '끝'.encode('utf-16-le'),
                      _table('첫 셀') + _table('둘째 셀'))
    assert [type(e) for e in elements] == [Table, Paragraph, Table, Paragraph]
    assert [e.text for e in elements if isinstance(e, Paragraph)] == ['사이', '끝']
    assert [e.rows[0][0].text for e in elements if isinstance(e, Table)] == ['첫 셀', '둘째 셀']


def test_header_anchor_before_body_preserves_order():
    control = (_rec(HWPTAG_CTRL_HEADER, 1, b'daeh' + bytes(8)) +
               _rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
               _rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
               _rec(HWPTAG_PARA_TEXT, 3, '머리말\r'.encode('utf-16-le')))
    elements = _parse(_anchor(16, b'daeh') + '본문'.encode('utf-16-le'), control)
    assert [type(e) for e in elements] == [HeaderFooter, Paragraph]
    assert elements[1].text == '본문'


def test_note_and_table_at_same_text_offset_follow_raw_anchor_order():
    note = (_rec(HWPTAG_CTRL_HEADER, 1, b'  nf' + bytes(8)) +
            _rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
            _rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            _rec(HWPTAG_PARA_TEXT, 3, '각주\r'.encode('utf-16-le')))
    for note_first in (True, False):
        anchors = [_anchor(17, b'  nf'), _anchor(11, b' lbt')]
        controls = [note, _table('셀')]
        if not note_first:
            anchors.reverse()
            controls.reverse()
        elements = _parse(b''.join(anchors) + '뒤'.encode('utf-16-le'), b''.join(controls))
        flow = [e for e in elements if isinstance(e, (Table, Paragraph))]
        if note_first:
            assert [type(e) for e in flow] == [Paragraph, Table, Paragraph]
            assert flow[0].text == '[1]'
            assert flow[2].text == '뒤'
        else:
            assert [type(e) for e in flow] == [Table, Paragraph]
            assert flow[1].text == '[1]뒤'


def test_split_table_paragraph_preserves_surrogates_and_run_properties():
    text = '😀앞'.encode('utf-16-le') + _anchor(11, b' lbt') + '뒤'.encode('utf-16-le')
    info = SimpleNamespace(char_shapes=[CharShape(bold=True, base_size=1000)],
                           para_shapes=[], styles=[])
    section = SectionParser(doc_info=info).parse_stream(
        _rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        _rec(HWPTAG_PARA_TEXT, 1, text + b'\r\x00') +
        _rec(HWPTAG_PARA_CHAR_SHAPE, 1, struct.pack('<II', 0, 0)) + _table('셀'), False)
    before, table, after = section.elements
    assert isinstance(table, Table)
    assert (before.text, after.text) == ('😀앞', '뒤')
    assert all(run.bold and run.font_size_pt == 10 for p in (before, after) for run in p.runs)


def test_inline_equation_shift_does_not_move_following_table_inside_latex():
    script = 'a over b'.encode('utf-16-le')
    control = (_rec(HWPTAG_CTRL_HEADER, 1, b'deqe' + struct.pack('<I', 1) + bytes(36)) +
               _rec(HWPTAG_EQEDIT, 2, bytes(4) + struct.pack('<H', len(script) // 2) + script))
    elements = _parse('앞'.encode('utf-16-le') + _anchor(11, b'deqe') +
                      _anchor(11, b' lbt') + '뒤'.encode('utf-16-le'), control + _table('셀'))
    assert [type(e) for e in elements] == [Paragraph, Table, Paragraph]
    assert elements[0].text == r'앞\frac{a}{b}'
    assert elements[0].runs[-1].equation is not None
    assert elements[2].text == '뒤'


def test_bookmark_is_preserved_when_table_splits_paragraph():
    name = '표위치'.encode('utf-16-le')
    bookmark = (_rec(HWPTAG_CTRL_HEADER, 1, b'mkob' + bytes(8)) +
                _rec(HWPTAG_CTRL_DATA, 2, bytes(10) + struct.pack('<H', len(name) // 2) + name))
    elements = _parse(_anchor(11, b' lbt') + '뒤'.encode('utf-16-le'), bookmark + _table('셀'))
    assert [type(e) for e in elements] == [Paragraph, Table, Paragraph]
    assert elements[0].text == '[bookmark: 표위치] '
    assert elements[2].text == '뒤'


def test_unanchored_control_keeps_existing_text_then_table_fallback():
    elements = _parse('본문'.encode('utf-16-le'), _table('셀'))
    assert [type(e) for e in elements] == [Paragraph, Table]
    assert elements[0].text == '본문'
