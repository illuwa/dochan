"""Synthetic HWP control records and HWPX inline text regression tests."""

import struct

import pytest

from dochan.hwp.section import SectionParser
from dochan.hwp.doc_info import DocInfo
from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.records.char_shape import CharShape
from dochan.hwpx.parser import HWPXParser
from test_hwp_section_controls import field_end_block, field_start_block, hlk_ctrl_payload, rec
from test_hwp_runs_review import _package


def _extended(ctrl_id):
    return struct.pack('<H', 23) + ctrl_id + bytes(8) + struct.pack('<H', 23)


def _compose(value, border=0):
    encoded = value.encode('utf-16-le')
    return b'spct' + struct.pack('<H', len(encoded) // 2) + encoded + bytes((border, 0, 0, 0))


def _dutmal(main, sub):
    main_bytes = main.encode('utf-16-le')
    sub_bytes = sub.encode('utf-16-le')
    return (b'tudt' + struct.pack('<H', len(main_bytes) // 2) + main_bytes
            + struct.pack('<H', len(sub_bytes) // 2) + sub_bytes + bytes(20))


def _hwp(body, *controls):
    data = rec(66, 0, bytes(22)) + rec(67, 1, body + struct.pack('<H', 13))
    return data + b''.join(rec(71, 1, control) for control in controls)


def _text(section):
    return ''.join(element.text for element in section.elements if hasattr(element, 'runs'))


def test_hwp_compose_and_dutmal_insert_at_control_positions():
    data = _hwp('앞'.encode('utf-16-le') + _extended(b'spct') +
                '중'.encode('utf-16-le') + _extended(b'tudt') +
                '뒤'.encode('utf-16-le'), _compose('1'), _dutmal('본말', '덧말'))
    assert _text(SectionParser().parse_stream(data, False)) == '앞1중본말(덧말)뒤'


@pytest.mark.parametrize('stored,border,expected', [
    ('◯한韓', 1, '한韓'), ('□한韓', 3, '한韓'), ('\u3000한韓', 0, '한韓'),
    ('\U000f02b1', 3, '1'), ('①', 1, '1'), ('①', 0, '①'),
    ('❷', 2, '2'), ('\U000f02d0', 3, '3'),
    ('\U000f02ba\U000f02c3', 3, '10'),
])
def test_hwp_compose_omits_drawn_border(stored, border, expected):
    data = _hwp(_extended(b'spct'), _compose(stored, border))
    assert _text(SectionParser().parse_stream(data, False)) == expected


def test_hwp_compose_old_layout_has_no_border_tail():
    parser = SectionParser()
    data = _hwp('앞'.encode('utf-16-le') + _extended(b'spct') +
                '뒤'.encode('utf-16-le'), b'spct\x02\x00A\x00B\x00')
    assert _text(parser.parse_stream(data, False)) == '앞AB뒤'
    assert parser.errors == []


def test_hwp_compose_old_layout_rejects_partial_tail():
    parser = SectionParser()
    data = _hwp(_extended(b'spct'), b'spct\x01\x00A\x00\x00')
    assert _text(parser.parse_stream(data, False)) == ''
    assert any('truncated or invalid' in error for error in parser.errors)


@pytest.mark.parametrize('stored,expected', [
    ('\U000f02ba\U000f02c3', '\U000f02ba\U000f02c3'),
    ('\U000f02b1', '\U000f02b1'),
])
def test_hwp_compose_borderless_pua_is_preserved(stored, expected):
    data = _hwp(_extended(b'spct'), _compose(stored, 0))
    assert _text(SectionParser().parse_stream(data, False)) == expected


def test_hwp_compose_replaces_lone_surrogate():
    parser = SectionParser()
    data = _hwp(_extended(b'spct'), b'spct\x02\x00\x00\xd8A\x00' + bytes(4))
    assert _text(parser.parse_stream(data, False)) == '\ufffdA'
    assert parser.errors == []


def test_hwp_missing_form_reference_retains_original_warning():
    parser = SectionParser()
    parser._form_text_result(parse_para_text(_extended(b'mrof')), [])
    assert parser.errors == ['WARN: HWP form object reference missing']


def test_hwp_revision_control_warning_does_not_claim_preservation():
    parser = SectionParser(revision_mode='final')
    parser._warn_revision_controls(
        {'inline_controls': [(0, 8, b'spct')]},
        [struct.pack('<III', 0, 8, (0x11 << 24) | 1)],
    )
    assert parser.errors == [
        'ERR: HWP revision partial [control]; inline control projection may differ']


def test_hwp_compose_preserves_link_positions():
    body = (field_start_block(b'klh%') + '앞'.encode('utf-16-le')
            + _extended(b'spct') + '뒤'.encode('utf-16-le')
            + field_end_block() + '밖'.encode('utf-16-le'))
    section = SectionParser().parse_stream(
        _hwp(body, hlk_ctrl_payload('https://example.org;1;0;0;'), _compose('1')), False)
    runs = section.elements[0].runs
    assert ''.join(run.text for run in runs) == '앞1뒤밖'
    assert [(run.text, run.link) for run in runs] == [
        ('앞1뒤', 'https://example.org'), ('밖', '')]


def test_hwp_compose_preserves_char_shape_boundary():
    body = '앞'.encode('utf-16-le') + _extended(b'spct') + '뒤'.encode('utf-16-le')
    data = (_hwp(body, _compose('1'))
            + rec(68, 1, struct.pack('<IIII', 0, 0, 9, 1)))
    parser = SectionParser(DocInfo(char_shapes=[CharShape(), CharShape(bold=True)]))
    runs = parser.parse_stream(data, False).elements[0].runs
    assert [(run.text, run.bold) for run in runs] == [('앞1', False), ('뒤', True)]


@pytest.mark.parametrize('control', [b'spct\x03\x00A\x00', b'tudt\x03\x00A\x00'])
def test_hwp_truncated_inline_control_warns_and_preserves_surroundings(control):
    parser = SectionParser()
    section = parser.parse_stream(_hwp('앞'.encode('utf-16-le') +
                                       _extended(control[:4]) + '뒤'.encode('utf-16-le'), control), False)
    assert _text(section) == '앞뒤'
    assert any('WARN' in error for error in parser.errors)


@pytest.mark.parametrize('sub,expected', [('덧말', '앞본말(덧말)뒤'), ('', '앞본말뒤')])
def test_hwpx_dutmal_main_and_sub_text(sub, expected):
    body = ('<hp:p><hp:run><hp:t>앞</hp:t><hp:dutmal>'
            '<hp:mainText>본말</hp:mainText><hp:subText>%s</hp:subText>'
            '</hp:dutmal><hp:t>뒤</hp:t></hp:run></hp:p>') % sub
    doc = HWPXParser().parse(_package(body))
    assert doc.find_all('paragraph')[0].text == expected
