"""리뷰 지적을 외부 표본 없이 원시 WCHAR와 레코드로 재현한다."""
import struct

import pytest

from dochan.hwp.doc_info import DocInfo, DocInfoParser
from dochan.hwp.forms import form_text
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.section import SectionParser
from dochan.model.style import StyleEntry
from test_hwp_features import _node, _form, _set, _parameter, _change
from test_hwp_styles import _paragraph
from test_parser_hardening_review import _hwp_table_control_node, _hwp_cell_with_paragraph, _hwp_text_paragraph
from dochan.hwp.revisions import parse_change


def _inline(code, cid=b'\x00' * 4):
    return struct.pack('<H', code) + cid + b'\x00' * 8 + struct.pack('<H', code)


def _click(props=0):
    command = _set('Clickhere', _parameter('Direction', 'PROMPT'))
    return _node(71, 1, b'klc%' + struct.pack('<IBH', props, 0, len(command)) + command.encode('utf-16-le'))


@pytest.mark.parametrize('body,props,expected', [
    (b'', 0, ''), (b'', 1 << 15, ''),
    (_inline(11, b' lbt'), 0, ''), (b'\x00\x00', 0, ''),
    ('VALUE'.encode('utf-16-le'), 0, 'VALUE'),
])
def test_clickhere_preserves_body_without_synthesizing_prompt(body, props, expected):
    raw = _inline(3, b'klc%') + body + _inline(4)
    result, _ = SectionParser()._form_text_result(parse_para_text(raw), [_click(props)])
    assert result['text'] == expected


def test_clickhere_does_not_prepend_prompt_to_form_value():
    raw = _inline(3, b'klc%') + _inline(11, b'mrof') + _inline(4)
    form = _node(71, 1, b'mrof', [_node(91, 2, _form(b'tbp+', _set('ButtonSet', _parameter('Caption', 'VALUE'))))])
    result, _ = SectionParser()._form_text_result(parse_para_text(raw), [_click(), form])
    assert result['text'] == 'VALUE'


@pytest.mark.parametrize('kind', [b'tbc+', b'tbr+'])
@pytest.mark.parametrize('value,mark', [(0, '[ ]'), (1, '[x]')])
def test_binary_button_state_matches_docx(kind, value, mark):
    data = _form(kind, _set('ButtonSet', _parameter('Caption', 'Choice') + 'Value:int:{} '.format(value)))
    assert form_text(data) == mark + 'Choice'


def test_binary_and_xml_checkbox_have_same_output_contract():
    from dochan.utils import safe_xml as etree
    from dochan.hwpx.parser import HWPXParser
    element = etree.fromstring(b'<hp:checkBtn xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" caption="Choice" value="CHECKED"/>')
    data = _form(b'tbc+', _set('ButtonSet', _parameter('Caption', 'Choice') + 'Value:int:1 '))
    assert form_text(data) == HWPXParser()._parse_form_run(element).text


@pytest.mark.parametrize('level,expected', [(1, 2), (4, 0)])
def test_direct_outline_precedes_style(level, expected):
    info = DocInfo(styles=[StyleEntry(name='Custom', para_shape_id=0)])
    for raw_level in (0, level):
        DocInfoParser()._parse_para_shape(struct.pack('<I', (1 << 23) | (raw_level << 25)), info)
    assert _paragraph(info, para_id=1).heading_level == expected


def test_style_char_shape_is_not_invented_without_direct_reference():
    info = DocInfo(char_shapes=[CharShape(bold=True, underline_type=1, strikeout=1)],
                   styles=[StyleEntry(name='Custom', char_shape_id=0)])
    run = _paragraph(info).runs[0]
    assert not run.bold and not run.underline and not run.strikeout


def test_attachment_title_is_not_subtitle():
    assert _paragraph(DocInfo(styles=[StyleEntry(name='첨부제목')])).heading_level == 1


@pytest.mark.parametrize('align', range(6))
def test_para_alignment_uses_bits_two_through_four(align):
    info = DocInfo()
    DocInfoParser()._parse_para_shape(struct.pack('<I', (align << 2) | 3), info)
    assert info.para_shapes[0].align == align


@pytest.mark.parametrize('mode,kind', [('final', 0x11), ('original', 0x10)])
def test_removed_revision_control_is_excluded_or_reports_partial(mode, kind):
    table = _hwp_table_control_node(1, 1, [])
    table['children'].append(_hwp_cell_with_paragraph(_hwp_text_paragraph('DELETED CELL')))
    raw = 'X'.encode('utf-16-le') + _inline(11, b' lbt') + 'Y'.encode('utf-16-le')
    paragraph = _node(66, 0, b'\x00' * 24, [
        _node(67, 1, raw), _node(70, 1, struct.pack('<III', 0, 9, (kind << 24) | 1)), table])
    info = DocInfo(track_changes={1: parse_change(_change(kind))})
    parser = SectionParser(info, revision_mode=mode)
    result = parser._tree_to_section([paragraph])
    assert len(result.elements) == 1 or any(error.startswith('ERR: HWP revision partial [control]') for error in parser.errors)
