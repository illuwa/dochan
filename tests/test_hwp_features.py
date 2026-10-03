"""Synthetic HWP forms and revision records; no corpus is required."""
import struct
from types import SimpleNamespace

import pytest

from dochan.hwp.forms import form_text, clickhere_prompt, parse_parameter_text
from dochan.hwp.revisions import parse_change, parse_author, project_text_result
from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.section import RawRecord, SectionParser


def _parameter(name, value):
    length = len(value.encode('utf-16-le')) // 2
    return '{}:wstring:{}:{} '.format(name, length, value)


def _set(name, contents):
    return '{}:set:{}:{}'.format(name, len(contents.encode('utf-16-le')) // 2, contents)


def _form(kind, contents):
    count = len(contents.encode('utf-16-le')) // 2
    return kind + kind + struct.pack('<IH', count, count) + contents.encode('utf-16-le')


@pytest.mark.parametrize('kind,group,key,value', [
    (b'tbp+', 'ButtonSet', 'Caption', '명령 단추'),
    (b'tbc+', 'ButtonSet', 'Caption', '선택 상자'),
    (b'tbr+', 'ButtonSet', 'Caption', '라디오 단추'),
    (b'boc+', 'ComboBoxSet', 'Text', '한 여름:Caption:wstring:99:내용'),
    (b'tde+', 'EditSet', 'Text', '입력 😀 내용'),
])
def test_form_objects_project_only_visible_text(kind, group, key, value):
    contents = _set('CommonSet', _parameter('Name', 'internal-name')) + ' '
    contents += _set(group, _parameter(key, value)) + ' '
    expected = '[ ]' + value if kind in (b'tbc+', b'tbr+') else value
    assert form_text(_form(kind, contents)) == expected


def test_form_parser_rejects_truncated_or_unbounded_lengths():
    good = _form(b'tbp+', _set('ButtonSet', _parameter('Caption', 'test')))
    with pytest.raises(ValueError):
        form_text(good[:-2])
    with pytest.raises(ValueError):
        parse_parameter_text('ButtonSet:set:999999999999:Caption:wstring:1:x')
    with pytest.raises(ValueError):
        parse_parameter_text('ButtonSet:set:8:Caption:wstring:1:x')


def test_form_parser_does_not_leak_hidden_names_or_passwords():
    assert form_text(_form(b'tde+', _set('CommonSet', _parameter('Name', 'private')))) == ''
    payload = _set('EditSet', _parameter('Text', 'secret') + _parameter('PasswordChar', '*'))
    assert form_text(_form(b'tde+', payload)) == ''


def test_clickhere_command_projects_direction():
    command = _set('Clickhere', _parameter('Direction', '여기에 입력') + _parameter('HelpState', '도움말'))
    count = len(command.encode('utf-16-le')) // 2
    data = b'klc%' + b'\x00' * 5 + struct.pack('<H', count) + command.encode('utf-16-le')
    assert clickhere_prompt(data) == '여기에 입력'


def test_parameter_parser_bounds_recursion():
    text = _parameter('Text', 'ok')
    for _ in range(20):
        text = _set('Nested', text)
    with pytest.raises(ValueError, match='depth'):
        parse_parameter_text(text)


def _change(kind, author=1):
    return struct.pack('<I6H6sI', kind, 2025, 9, 19, 16, 10, author, b'\x00' * 6, int(kind == 0x11))


def test_revision_metadata_decodes_change_and_author():
    change = parse_change(_change(0x10))
    assert change.kind == 'Insert'
    assert change.author_id == 1
    assert change.timestamp == (2025, 9, 19, 16, 10)
    assert parse_change(_change(0x11)).hidden is True
    author = parse_author(struct.pack('<I', 4) + 'user'.encode('utf-16-le') + struct.pack('<II', 1, 0))
    assert (author.name, author.mark, author.color) == ('user', 1, 0)


@pytest.mark.parametrize('mode,expected', [('preserve', 'aNEWoldz'), ('final', 'aNEWz'), ('original', 'aoldz')])
def test_revision_ranges_project_text_result(mode, expected):
    text = parse_para_text('aNEWoldz\r'.encode('utf-16-le'))
    ranges = struct.pack('<6I', 1, 4, 0x10000001, 4, 7, 0x11000002)
    errors = []
    result = project_text_result(text, [ranges],
                                 {1: parse_change(_change(0x10)), 2: parse_change(_change(0x11))}, mode, errors)
    assert result['text'] == expected
    assert errors == []


def test_revision_ranges_map_raw_control_and_surrogate_positions():
    data = struct.pack('<H', 2) + b'dces' + b'\x00' * 8 + struct.pack('<H', 2)
    data += 'a😀NEWz\r'.encode('utf-16-le')
    text = parse_para_text(data)
    ranges = struct.pack('<3I', 11, 14, 0x10000001)
    errors = []
    result = project_text_result(text, [ranges], {1: parse_change(_change(0x10))}, 'original', errors)
    assert result['text'] == 'a😀z'
    assert not errors


def test_revision_invalid_ranges_preserve_contents_and_warn():
    text = parse_para_text('abcdef\r'.encode('utf-16-le'))
    ranges = struct.pack('<9I', 1, 4, 0x10000001, 2, 5, 0x11000002, 5, 99, 0x10000001)
    errors = []
    result = project_text_result(text, [ranges], {1: parse_change(_change(0x10)), 2: parse_change(_change(0x11))}, 'original', errors)
    assert result is text
    assert any('overlap' in e for e in errors)
    assert any('bounds' in e for e in errors)


def test_revision_truncated_or_unknown_metadata_fails_closed():
    with pytest.raises(ValueError):
        parse_change(_change(0x10)[:-1])
    with pytest.raises(ValueError):
        parse_change(_change(0x12))
    with pytest.raises(ValueError):
        parse_author(struct.pack('<I', 0xFFFFFFFF))


def test_revision_missing_reference_and_truncated_range_are_not_applied():
    text = parse_para_text('abc\r'.encode('utf-16-le'))
    errors = []
    assert project_text_result(text, [struct.pack('<3I', 0, 3, 0x10000003)], {}, 'original', errors) is text
    assert any('reference' in e for e in errors)
    errors.clear()
    assert project_text_result(text, [b'\x00'], {}, 'original', errors) is text
    assert any('truncated' in e for e in errors)


def test_revision_text_projection_remaps_shapes_and_fields():
    text = parse_para_text('aNEWz\r'.encode('utf-16-le'))
    text['field_marks'] = [(0, 'start', b'klh%'), (5, 'end', None)]
    result = project_text_result(text, [struct.pack('<3I', 1, 4, 0x10000001)],
                                 {1: parse_change(_change(0x10))}, 'original', [])
    assert result['text'] == 'az'
    assert result['raw_to_text'] == [0, 1, 1, 1, 1, 2]
    assert result['field_marks'] == [(0, 'start', b'klh%'), (2, 'end', None)]
    assert text['text'] == 'aNEWz'


def test_revision_invalid_paragraph_preserves_even_valid_adjacent_range():
    text = parse_para_text('abcdef\r'.encode('utf-16-le'))
    ranges = struct.pack('<6I', 0, 2, 0x10000001, 4, 7, 0x10000001)
    assert project_text_result(text, [ranges], {1: parse_change(_change(0x10))}, 'original', []) is text


def _node(tag, level, data=b'', children=()):
    return {'record': RawRecord(tag, level, len(data), data), 'children': list(children)}


@pytest.mark.parametrize('mode,expected', [('preserve', 'aNEWoldz'), ('final', 'aNEWz'), ('original', 'aoldz')])
def test_section_parser_binary_revision_projection(mode, expected):
    changes = {1: parse_change(_change(0x10)), 2: parse_change(_change(0x11))}
    info = SimpleNamespace(track_changes=changes, track_authors=[], char_shapes=[], styles=[])
    ranges = struct.pack('<6I', 1, 4, 0x10000001, 4, 7, 0x11000002)
    tree = [_node(66, 0, b'\x00' * 24, [
        _node(67, 1, 'aNEWoldz\r'.encode('utf-16-le')),
        _node(70, 1, ranges),
    ])]
    section = SectionParser(info, revision_mode=mode)._tree_to_section(tree)
    assert [p.text for p in section.elements] == [expected]


def test_section_parser_form_visible_text_keeps_inline_order():
    inline = struct.pack('<H', 11) + b'mrof' + b'\x00' * 8 + struct.pack('<H', 11)
    form = _form(b'tbp+', _set('ButtonSet', _parameter('Caption', '누르기')))
    tree = [_node(66, 0, b'\x00' * 24, [
        _node(67, 1, 'A'.encode('utf-16-le') + inline + 'B\r'.encode('utf-16-le')),
        _node(71, 1, b'mrof', [_node(91, 2, form)]),
    ])]
    section = SectionParser()._tree_to_section(tree)
    assert [p.text for p in section.elements] == ['A누르기B']


def test_section_parser_malformed_form_warns_and_preserves_adjacent_text():
    inline = struct.pack('<H', 11) + b'mrof' + b'\x00' * 8 + struct.pack('<H', 11)
    tree = [_node(66, 0, b'\x00' * 24, [
        _node(67, 1, 'A'.encode('utf-16-le') + inline + 'B\r'.encode('utf-16-le')),
        _node(71, 1, b'mrof', [_node(91, 2, b'bad')]),
    ])]
    parser = SectionParser()
    section = parser._tree_to_section(tree)
    assert [p.text for p in section.elements] == ['AB']
    assert any('form' in error.lower() for error in parser.errors)


# 한컴오피스 HWP(Mac) 화면 실측: 단추·선택 상자·라디오 캡션은 윈도 단축키 표기처럼 '&&' 를 '&' 로,
# 단독 '&'(단축키 표시)와 끝의 '&' 는 숨긴다. 공개 form-002 의 "IP R&&D연계" 가 "IP R&D연계" 로 보인다.
@pytest.mark.parametrize('raw,shown', [
    ('가&나 A&&B 끝&', '가나 A&B 끝'),
    ('&첫 중&&&간', '첫 중&간'),
    ('R&&D &&&&', 'R&D &&'),
])
def test_button_captions_hide_mnemonic_ampersands_like_hancom(raw, shown):
    for kind in (b'tbp+', b'tbc+', b'tbr+'):
        contents = _set('ButtonSet', _parameter('Caption', raw))
        prefix = '[ ]' if kind != b'tbp+' else ''
        assert form_text(_form(kind, contents)) == prefix + shown
    # 콤보 상자·입력 상자의 글은 캡션이 아니므로 그대로다.
    assert form_text(_form(b'tde+', _set('EditSet', _parameter('Text', raw)))) == raw
    assert form_text(_form(b'boc+', _set('ComboBoxSet', _parameter('Text', raw)))) == raw



def _char_shape_record(props):
    # 글꼴 7 + 장평 7 + 자간 7 + 상대 크기 7 + 위치 7 + 기준 크기 4 + 속성 4 (+ 색 4)
    return bytes(14) + bytes(7) * 4 + struct.pack('<iII', 1000, props, 0)


# 한컴오피스 화면 실측과 공개 HWP·HWPX 짝 511개의 대응: 밑줄 종류(비트 2-3)는 1(아래)·3(위)만 보이고 2 는 HWPX
# NONE 이며, 취소선(비트 18-20)은 모양(비트 26-29)이 3D 계열(13·14·15)이면 그리지 않는다.
@pytest.mark.parametrize('props,underline,strikeout', [
    (0x3c0400f8, False, False),   # 공개 실물: 밑줄 2·모양 15, 취소선 1·모양 15(3D) — 화면에 둘 다 없음
    (0x00040008, False, True),    # 밑줄 2, 취소선 1·모양 0(SOLID)
    (0x00000004, True, False),    # 밑줄 1(아래)
    (0x0000000c, True, False),    # 밑줄 3(위)
    (0x1c040000, False, True),    # 취소선 모양 7(DOUBLE_SLIM)
    (0x2c040000, False, True),    # 취소선 모양 11(WAVE)
    (0x34040000, False, False),   # 취소선 모양 13(THICK_3D)
    (0x38040000, False, False),   # 취소선 모양 14(THICK_3D_REVERS)
])
def test_hwp_char_shape_visible_underline_and_strikeout(props, underline, strikeout):
    from dochan.hwp.records.char_shape import CharShape
    shape = CharShape.parse(_char_shape_record(props))
    assert shape.has_underline is underline
    assert shape.has_strikeout is strikeout
