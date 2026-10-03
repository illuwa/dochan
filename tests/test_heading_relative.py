"""HWP와 HWPX는 글꼴 제목을 문서 본문 크기에 상대적으로 판정한다."""

import struct

import pytest

from dochan.constants import (
    HWPTAG_CTRL_DATA, HWPTAG_CTRL_HEADER, HWPTAG_PARA_CHAR_SHAPE,
    HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT,
)
from dochan.hwp.doc_info import DocInfo
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.utils.heading_font import (
    body_font_size, finalize_font_headings, heading_level_from_style_name,
    relative_heading_level,
)
import dochan.hwp.section as hwp_section
import dochan.hwpx.parser as hwpx_parser
from test_hwpx_controls import package


def _paragraph(text, size):
    return Paragraph(runs=[TextRun(text=text, font_size_pt=size)])


def test_twenty_point_title_on_fourteen_point_body_is_h2():
    assert relative_heading_level(_paragraph('문서 제목', 20).runs, 14) == 2


def test_hwp_font_headings_use_document_body_size():
    parser = SectionParser()
    paragraphs = [
        _paragraph("문서 제목", 21),
        _paragraph("본문 문단은 길게 이어지고 여러 글자를 포함합니다.", 14),
        _paragraph("다른 본문 문단 역시 글자 크기가 같습니다.", 14),
        _paragraph("여기에도 본문 문장이 충분히 들어 있습니다.", 14),
        _paragraph("절 제목", 18),
        _paragraph("소제목", 16),
    ]
    for para in paragraphs:
        para.heading_level = parser._detect_heading_level(para)
    parser.finalize_font_headings()
    assert [para.heading_level for para in paragraphs] == [1, 0, 0, 0, 2, 3]


def test_hwpx_font_headings_use_document_body_size(tmp_path):
    items = [("문서 제목", 21),
             ("본문 문단은 길게 이어지고 여러 글자를 포함합니다.", 14),
             ("다른 본문 문단 역시 글자 크기가 같습니다.", 14),
             ("여기에도 본문 문장이 충분히 들어 있습니다.", 14),
             ("절 제목", 18), ("소제목", 16)]
    header = ''.join('<hh:charPr id="%d" height="%d"/>' % (size, size * 100)
                     for _, size in items)
    body = ''.join('<hp:p><hp:run charPrIDRef="%d"><hp:t>%s</hp:t>'
                   '</hp:run></hp:p>' % (size, text) for text, size in items)
    doc = HWPXParser().parse(package(tmp_path, body, header))
    assert doc.errors == []
    assert [para.heading_level for para in doc.sections[0].elements] == [1, 0, 0, 0, 2, 3]


def test_hwpx_title_named_style_matches_hwp(tmp_path):
    from test_hwpx_heading_priority import _heading_document
    for name in ('문서제목', 'Custom Title', '부제목'):
        para = _heading_document(tmp_path, 'NONE', 0, name, 0)
        expected = 2 if name == '부제목' else 1
        assert para.heading_level == expected


@pytest.mark.parametrize('name', (
    '표제목', '표 제목', '통계표 제목', '그림제목', '박스제목/표제목',
    '차례(소제목)', '목차 제목2', '차례 개요 1', '통계표 데이터',
))
def test_caption_contents_form_style_is_not_named_heading_in_both_readers(tmp_path, name):
    from dochan.model.style import StyleEntry
    from test_hwp_styles import _paragraph as hwp_paragraph
    from test_hwpx_heading_priority import _heading_document

    assert heading_level_from_style_name(name) == 0
    assert hwp_paragraph(DocInfo(styles=[StyleEntry(name=name)])).heading_level == 0
    assert _heading_document(tmp_path, 'NONE', 0, name, 0).heading_level == 0


def test_caption_style_keeps_explicit_outline_and_font_fallback(tmp_path):
    from test_hwpx_heading_priority import _heading_document

    assert _heading_document(tmp_path, 'OUTLINE', 1, '표제목', 0).heading_level == 2
    assert _heading_document(tmp_path, 'NONE', 0, '표제목', 0,
                             font_size=2000).heading_level == 1


def test_hwpx_caption_name_is_not_overridden_by_english_title(tmp_path):
    header = ('<hh:charProperties><hh:charPr id="0" height="1000"/>'
              '</hh:charProperties><hh:styles>'
              '<hh:style id="1" name="표제목" engName="Custom Title"/>'
              '</hh:styles>')
    body = ('<hp:p styleIDRef="1"><hp:run charPrIDRef="0">'
            '<hp:t>표 위 설명</hp:t></hp:run></hp:p>')
    doc = HWPXParser().parse(package(tmp_path, body, header))
    assert doc.sections[0].elements[0].heading_level == 0


def test_h1_boundary_and_long_large_paragraph():
    assert relative_heading_level(_paragraph('짧은 제목', 20).runs, 14) == 2
    assert relative_heading_level(_paragraph('가' * 121, 24).runs, 14) == 0


def test_body_estimate_excludes_notes_and_label_lines():
    body = [_paragraph('본문 문장이 충분히 길어서 기준이 됩니다.' * 2, 14)
            for _ in range(3)]
    labels = [_paragraph(prefix + ' 작은 안내문 ' * 12, 10)
              for prefix in ('※', '*', '주:', '(단위')]
    header = _paragraph('머리말 문장 ' * 30, 10)
    footer = _paragraph('꼬리말 문장 ' * 30, 10)
    footnote = _paragraph('각주 제목', 18)
    caption = _paragraph('캡션 문장 ' * 30, 10)
    detached = _paragraph('실패한 섹션 문장 ' * 100, 9)
    image = Image(caption=[caption])
    doc = Document(sections=[Section(elements=body + labels + [
        HeaderFooter(type='header', paragraphs=[header]),
        HeaderFooter(type='footer', paragraphs=[footer]),
        Footnote(paragraphs=[footnote]), image])])
    candidates = body + labels + [header, footer, footnote, caption, detached]
    assert body_font_size(candidates, doc=doc) == 14
    finalize_font_headings(candidates, doc=doc)
    assert all(p.heading_level == 0 for p in body)
    assert all(p.heading_level == 0 for p in labels)
    assert footnote.heading_level == 2  # 추정 표본만 제외하고 수준 판정은 적용한다.


def test_hwpx_limit_marker_is_filtered_and_cleared(tmp_path, monkeypatch):
    monkeypatch.setattr(hwpx_parser, 'MAX_FONT_HEADING_PARAGRAPHS', 3)
    body = ''.join('<hp:p><hp:run charPrIDRef="14"><hp:t>본문 문장 %d 입니다. 충분히 긴 문장입니다.</hp:t></hp:run></hp:p>' % i
                   for i in range(5))
    parser = HWPXParser()
    doc = parser.parse(package(tmp_path, body, '<hh:charPr id="14" height="1400"/>'))
    assert len(doc.sections[0].elements) == 5
    assert any('글꼴 제목 문단 한도' in error for error in doc.errors)
    assert [p.heading_level for p in doc.sections[0].elements] == [3] * 5
    assert parser._font_heading_paragraphs == []


def test_hwp_limit_marker_is_filtered(monkeypatch):
    monkeypatch.setattr(hwp_section, 'MAX_FONT_HEADING_PARAGRAPHS', 3)
    parser = SectionParser()
    paragraphs = [_paragraph('본문 문장 %d 입니다. 충분히 긴 문장입니다.' % i, 14)
                  for i in range(5)]
    for para in paragraphs:
        para.heading_level = parser._detect_heading_level(para)
    parser.finalize_font_headings()
    assert [p.heading_level for p in paragraphs] == [3] * 5
    assert len(parser._font_heading_paragraphs) == 0


def test_hwp_bookmark_marker_keeps_paragraph_font_size():
    from test_hwp_section_controls import bokm_ctrl_data, rec
    payload = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, '책갈피 제목'.encode('utf-16-le') + b'\r\x00') +
        rec(HWPTAG_PARA_CHAR_SHAPE, 1, struct.pack('<II', 0, 0)) +
        rec(HWPTAG_CTRL_HEADER, 1, b'mkob') +
        rec(HWPTAG_CTRL_DATA, 2, bokm_ctrl_data('표지'))
    )
    info = DocInfo(char_shapes=[CharShape(base_size=1800)])
    parser = SectionParser(info)
    para = parser.parse_stream(payload, is_compressed=False).elements[0]
    assert para.runs[0].text == '[bookmark: 표지] '
    assert para.runs[0].font_size_pt == 18
    assert para.heading_level == 2



@pytest.mark.parametrize('name, level', (
    ('표지 제목', 1), ('별표제목', 1), ('양식제목', 1), ('차례 제목', 1), ('목차,발간사 제목', 1),
    ('개요 2', 2), ('개요 7', 7), ('개요 10', 10), ('사업개요', 0), ('□ 사업개요', 0),
))
def test_cover_appendix_form_titles_stay_and_outline_number_is_exact(name, level):
    """표지·별표·양식 제목과 차례 쪽 제목은 실제 제목이다. 개요 번호는 그대로 돌려주고 4 이상은 호출자가 본문으로 둔다(감수)."""
    assert heading_level_from_style_name(name) == level


def test_outline_seven_named_style_is_body_in_both_readers(tmp_path):
    from dochan.model.style import StyleEntry
    from test_hwp_styles import _paragraph as hwp_paragraph
    from test_hwpx_heading_priority import _heading_document

    assert hwp_paragraph(DocInfo(styles=[StyleEntry(name='개요 7')])).heading_level == 0
    assert _heading_document(tmp_path, 'NONE', 0, '개요 7', 0).heading_level == 0
