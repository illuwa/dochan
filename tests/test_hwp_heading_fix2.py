"""깊은 개요와 표 셀의 큰 글자를 제목으로 승격하지 않는다."""

import struct

import pytest

from dochan import Dochan
from dochan.hwp.doc_info import DocInfo, DocInfoParser
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import RawRecord, SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Document, Paragraph, TextRun
from dochan.model.style import StyleEntry
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from test_hwp_revision_reader import TrackedOle, _section
from test_hwpx_controls import package
from test_parser_hardening_review import (
    _hwp_cell_with_paragraph, _hwp_paragraph_with_control,
    _hwp_table_control_node, _hwp_text_paragraph,
)


def _documents(tmp_path, source, level, size, cell_depth=0):
    """같은 개요/글자 정보를 합성 레코드와 XML로 각각 작성한다."""
    name = '개요 %d' % level if source == 'name' else 'Custom'
    info = DocInfo(char_shapes=[CharShape(base_size=size * 100)],
                   styles=[StyleEntry(name=name, para_shape_id=0)])
    props = ((1 << 23) | ((level - 1) << 25)) if source in ('direct', 'default') else 0
    DocInfoParser()._parse_para_shape(struct.pack('<I', props), info)
    direct_id = 65535 if source == 'default' else 0
    header = ('<hh:charPr id="0" height="%d"/>'
              '<hh:paraPr id="0"><hh:heading type="%s" level="%d"/></hh:paraPr>'
              '<hh:style id="0" name="%s" paraPrIDRef="0"/>') % (
                  size * 100, 'OUTLINE' if props else 'NONE', level - 1, name)

    def paragraph(text):
        node = _hwp_text_paragraph(text)
        data = bytearray(node['record'].data)
        struct.pack_into('<H', data, 8, direct_id)
        node['record'] = RawRecord(66, 0, len(data), bytes(data))
        node['children'].append({'record': RawRecord(68, 1, 8, struct.pack('<II', 0, 0)),
                                 'children': []})
        xml = ('<hp:p paraPrIDRef="%d" styleIDRef="0"><hp:run charPrIDRef="0">'
               '<hp:t>%s</hp:t></hp:run></hp:p>') % (direct_id, text)
        return node, xml

    node, xml = paragraph('◦ 항목')
    for _ in range(cell_depth):
        table = _hwp_table_control_node(1, 1, [])
        table['children'].append(_hwp_cell_with_paragraph(node))
        node = _hwp_paragraph_with_control(table)
        xml = ('<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
               '<hp:subList>%s</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>') % xml
    after, after_xml = paragraph('뒤 문단')
    parser = SectionParser(info)
    hwp = Document(sections=[parser._tree_to_section([node, after])])
    hwpx = HWPXParser().parse(package(tmp_path, xml + after_xml, header))
    assert not parser.errors
    assert not hwpx.errors
    return hwp, hwpx


def _first_paragraph(doc, cell_depth):
    element = doc.sections[0].elements[0]
    for _ in range(cell_depth):
        element = element.rows[0][0].paragraphs[0]
    return element


@pytest.mark.parametrize('first_size,second_size,expected', [
    (10, 20, 1), (20, 10, 0),
])
def test_hwp_font_heading_uses_first_nonblank_run(first_size, second_size, expected):
    para = Paragraph(runs=[TextRun(text=' ', font_size_pt=first_size),
                           TextRun(text='실제 제목', font_size_pt=second_size)])
    assert SectionParser._heading_level_by_font(para) == expected


@pytest.mark.parametrize('source', ['direct', 'name', 'default'])
@pytest.mark.parametrize('level', [4, 5, 6])
@pytest.mark.parametrize('size', [14, 20])
def test_deep_outline_stays_body_in_both_formats(tmp_path, source, level, size):
    for doc in _documents(tmp_path, source, level, size):
        assert _first_paragraph(doc, 0).heading_level == 0
        assert to_dict(doc)['sections'][0]['elements'][0]['heading_level'] == 0
        assert not to_markdown(doc).startswith('#')


@pytest.mark.parametrize('cell_depth', [1, 2])
@pytest.mark.parametrize('size,expected', [(14, 3), (16, 2), (20, 1)])
def test_cell_font_fallback_is_disabled_and_context_restored(tmp_path, cell_depth, size, expected):
    for doc in _documents(tmp_path, 'none', 1, size, cell_depth):
        assert _first_paragraph(doc, cell_depth).heading_level == 0
        serialized = to_dict(doc)['sections'][0]['elements'][0]
        for _ in range(cell_depth):
            serialized = serialized['rows'][0][0]['paragraphs'][0]
        assert serialized['heading_level'] == 0
        assert doc.sections[0].elements[-1].heading_level == expected


@pytest.mark.parametrize('source', ['direct', 'name', 'default'])
@pytest.mark.parametrize('level', [1, 2, 3])
def test_explicit_shallow_heading_survives_inside_cells(tmp_path, source, level):
    for doc in _documents(tmp_path, source, level, 20, 1):
        assert _first_paragraph(doc, 1).heading_level == level


@pytest.mark.parametrize('slack', [-1, 0])
def test_preserve_fallback_shares_cumulative_stream_budget(monkeypatch, tmp_path, slack):
    opened = []

    class BudgetOle(TrackedOle):
        def __init__(self, path):
            super().__init__(path)
            self.streams['ViewText/Section0'] = _section('VIEW') * 3
            self.streams['BodyText/Section0'] = _section('BODY')

        def openstream(self, name):
            opened.append(name)
            return super().openstream(name)

    streams = BudgetOle(None).streams
    limit = sum(len(value) for value in streams.values()) + slack
    monkeypatch.setattr('dochan.reader.cfb.OleFileIO', BudgetOle)
    monkeypatch.setattr('dochan.reader.MAX_OLE_DOCUMENT_SIZE', limit)
    monkeypatch.setattr('dochan.hwp.section.MAX_HWP_RECORDS', 3)
    path = tmp_path / 'budget.hwp'
    path.write_bytes(b'\xd0\xcf\x11\xe0')
    reader = Dochan(path)
    assert 'ViewText/Section0' in opened
    if slack == 0:
        assert 'BodyText/Section0' in opened
        assert reader.find_all('paragraph')[0].text == 'BODY'
        assert not any(error.startswith('ERR:') for error in reader.errors)
    else:
        assert 'BodyText/Section0' not in opened
        assert any('document stream budget' in error for error in reader.errors)
