"""실제 HWP 레코드와 HWPX XML에서 강조 절 제목의 공통 판정."""

import html
import struct

import pytest

from dochan.constants import (
    HWPTAG_CTRL_DATA, HWPTAG_CTRL_HEADER, HWPTAG_LIST_HEADER,
    HWPTAG_PARA_CHAR_SHAPE, HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT,
    HWPTAG_SHAPE_COMPONENT,
)
from dochan.hwp.doc_info import DocInfo
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Document, TextRun
from dochan.utils.heading_font import finalize_font_headings
from test_hwp_section_controls import bokm_ctrl_data, gso_ctrl_payload, rec
from test_hwpx_controls import package


BODY = '본문 문장은 충분히 길게 이어지며 관련 사실을 설명합니다.'
SHAPES = [(14, False), (15, False), (14, True), (15, True), (12, False),
          (21, False), (12, True), (10.25, False)]


def _documents(tmp_path, parts, body_shape=0):
    """parts: 문단별 (문자열, 글자 모양 ID) 런 목록."""
    body_parts = [[(BODY, body_shape)] for _ in range(3)] + parts
    shapes = [CharShape(base_size=size * 100, bold=bold) for size, bold in SHAPES]
    parser = SectionParser(DocInfo(char_shapes=shapes))
    payload = bytearray()
    for runs in body_parts:
        text = ''.join(value for value, _ in runs)
        payload.extend(rec(HWPTAG_PARA_HEADER, 0, bytes(22)))
        payload.extend(rec(HWPTAG_PARA_TEXT, 1, text.encode('utf-16-le') + b'\r\x00'))
        boundaries = bytearray()
        position = 0
        for value, shape_id in runs:
            boundaries.extend(struct.pack('<II', position, shape_id))
            position += len(value.encode('utf-16-le')) // 2
        payload.extend(rec(HWPTAG_PARA_CHAR_SHAPE, 1, bytes(boundaries)))
    section = parser.parse_stream(bytes(payload), is_compressed=False)
    hwp = Document(sections=[section])
    parser.finalize_font_headings(doc=hwp)

    header = ''.join(
        '<hh:charPr id="%d" height="%d">%s</hh:charPr>' % (
            index, size * 100, '<hh:bold/>' if bold else '')
        for index, (size, bold) in enumerate(SHAPES))
    xml = ''.join(
        '<hp:p>%s</hp:p>' % ''.join(
            '<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run>' % (
                shape_id, html.escape(value)) for value, shape_id in runs)
        for runs in body_parts)
    hwpx = HWPXParser().parse(package(tmp_path, xml, header))
    return hwp, hwpx


@pytest.mark.parametrize('parts, expected', [
    ([('□ 추진배경', 1)], 3),
    ([('□ 내역별 노동비용', 2)], 3),
    ([('< 보도내용 요약 >', 2)], 3),
    ([('〈행위 사실〉', 1)], 3),
    ([('[ 추진 배경]', 2)], 3),
    ([('【 ➊ 현장대기 프로젝트 신속 가동 】', 1)], 3),
    ([('Ⅰ. 사업 개요', 3)], 3),
    ([('1. 사건 개요', 3)], 3),
    ([('1-1. 내역별 노동비용', 1)], 3),
    ([('2) 청주 노선 관련 시정조치', 3)], 3),
    ([('가. 추진 계획', 1)], 3),
    ([('\U000f0a71 ', 4), ('(소비자물가) 전년동월비 2.9% 상승', 1)], 3),
    ([('1. 강조 없는 목록 줄', 0)], 0),
    ([('1. 같은 크기의 굵은 목록 줄', 2)], 0),
    ([('2026. 3. 3.', 3)], 0),
    ([('○ 목록 줄', 3)], 0),
    ([('※ 주석 줄', 3)], 0),
    ([('□ 사업명: 지역 사업', 3)], 0),
    ([('□ 표 1. 수치 자료', 3)], 0),
    ([('□ 관련 사실을 설명하고자 여러 정보를 제공한다.', 2)], 0),
    ([('문장 안의 ', 0), ('굵은 강조', 2), (' 표시입니다.', 0)], 0),
    ([('□ ' + BODY * 3, 3)], 0),
])
def test_emphasized_sections_match_in_both_formats(tmp_path, parts, expected):
    for doc in _documents(tmp_path, [parts]):
        assert [p.heading_level for p in doc.sections[0].elements][-1] == expected
        assert doc.errors == []


def test_same_size_marker_in_table_stays_body(tmp_path):
    header = '<hh:charPr id="0" height="1400"><hh:bold/></hh:charPr>'
    body = ''.join('<hp:p><hp:run charPrIDRef="0"><hp:t>%s</hp:t></hp:run></hp:p>'
                   % BODY for _ in range(3))
    body += ('<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
             '<hp:subList><hp:p><hp:run charPrIDRef="0"><hp:t>□ 셀 제목</hp:t>'
             '</hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>')
    doc = HWPXParser().parse(package(tmp_path, body, header))
    cell = doc.sections[0].elements[-1].rows[0][0]
    assert cell.paragraphs[0].heading_level == 0


def test_emphasis_requires_top_level_even_when_finalizer_receives_nested_paragraph(tmp_path):
    doc, _ = _documents(tmp_path, [[('□ 최상위 절', 2)]])
    nested = doc.sections[0].elements[-1]
    doc.sections[0].elements.pop()
    nested.heading_level = 0
    finalize_font_headings([nested] + doc.sections[0].elements, doc=doc)
    assert nested.heading_level == 0


@pytest.mark.parametrize('parts, expected', [
    ([('□ ' + '가' * 119, 2)], 0),  # M01: 120자 초과
    ([('□ 제목\n계속', 2)], 0),  # M03
    ([('□ 분류：제목', 2)], 0),  # M05
    ([('\U000f0a71 항목', 2)], 0),  # M10: PUA에 굵기 경로 없음
    ([('□ 보통 굵기', 0)], 0),  # M11
    ([('< 닫히지 않은 제목', 2)], 0),  # M14
    ([('  □ ', 0), ('제목', 2)], 3),  # M17: 앞 공백과 표지 제외
    ([('< ', 0), ('>', 2)], 0),  # M18: 닫는 괄호는 내용 아님
    ([('3.5% 증가', 1)], 0),  # M22: 소수는 번호 아님
    ([('IV. 사업 개요', 1)], 3),  # M25
    ([('□ 큰 제목', 5)], 1),  # M29: 기존 크기 수준 보존
    ([('□ 작은 굵은 줄', 6)], 0),  # M31
])
def test_emphasis_review_mutations_in_both_formats(tmp_path, parts, expected):
    for doc in _documents(tmp_path, [parts]):
        assert doc.sections[0].elements[-1].heading_level == expected


@pytest.mark.parametrize('text, expected', [
    ('□ 추진배경', 3),
    ('< 보도내용 요약 >', 3),
    ('□ 관련 내용을 설명함.', 0),
    ('2026. 3. 3.', 0),
])
def test_note_reference_is_not_heading_evidence_in_both_formats(tmp_path, text, expected):
    hwp, _ = _documents(tmp_path, [[(text, 3)]], body_shape=1)
    para = hwp.sections[0].elements[-1]
    para.runs.append(TextRun(text='[1]', note_ref=1, font_size_pt=15))
    finalize_font_headings(hwp.sections[0].elements, doc=hwp)
    assert para.heading_level == expected

    header = ('<hh:charPr id="0" height="1500"/>'
              '<hh:charPr id="3" height="1500"><hh:bold/></hh:charPr>')
    body = ''.join('<hp:p><hp:run charPrIDRef="0"><hp:t>%s</hp:t></hp:run></hp:p>'
                   % BODY for _ in range(3))
    body += ('<hp:p><hp:run charPrIDRef="3"><hp:t>%s</hp:t>'
             '<hp:ctrl><hp:footNote><hp:subList><hp:p><hp:run>'
             '<hp:t>주석</hp:t></hp:run></hp:p></hp:subList></hp:footNote></hp:ctrl>'
             '</hp:run></hp:p>') % html.escape(text)
    hwpx = HWPXParser().parse(package(tmp_path, body, header))
    hwpx_para = next(p for p in hwpx.sections[0].elements
                     if hasattr(p, 'runs') and p.text.startswith(text))
    assert any(run.note_ref for run in hwpx_para.runs)
    assert hwpx_para.heading_level == expected


def test_bookmark_marker_is_not_heading_evidence_in_both_formats(tmp_path):
    shapes = [CharShape(base_size=1400), CharShape(base_size=1400, bold=True)]
    parser = SectionParser(DocInfo(char_shapes=shapes))
    payload = bytearray()
    for text in [BODY] * 3 + ['□ 추진배경']:
        level = 1 if text.startswith('□') else 0
        payload.extend(rec(HWPTAG_PARA_HEADER, 0, bytes(22)))
        payload.extend(rec(HWPTAG_PARA_TEXT, 1, text.encode('utf-16-le') + b'\r\x00'))
        payload.extend(rec(HWPTAG_PARA_CHAR_SHAPE, 1, struct.pack('<II', 0, level)))
        if level:
            payload.extend(rec(HWPTAG_CTRL_HEADER, 1, b'mkob'))
            payload.extend(rec(HWPTAG_CTRL_DATA, 2, bokm_ctrl_data('anchor')))
    hwp = Document(sections=[parser.parse_stream(bytes(payload), is_compressed=False)])
    parser.finalize_font_headings(doc=hwp)
    assert hwp.sections[0].elements[-1].heading_level == 3

    header = ('<hh:charPr id="0" height="1400"/>'
              '<hh:charPr id="1" height="1400"><hh:bold/></hh:charPr>')
    body = ''.join('<hp:p><hp:run charPrIDRef="0"><hp:t>%s</hp:t></hp:run></hp:p>' % BODY
                   for _ in range(3))
    body += ('<hp:p><hp:run charPrIDRef="1">'
             '<hp:ctrl><hp:bookmark name="anchor"/></hp:ctrl>'
             '<hp:t>□ 추진배경</hp:t></hp:run></hp:p>')
    hwpx = HWPXParser().parse(package(tmp_path, body, header))
    assert hwpx.sections[0].elements[-1].heading_level == 3


@pytest.mark.parametrize('text, expected', [
    ('가. 사업 개요', 3), ('하. 사업 개요', 3),
    ('각. 사업 개요', 0), ('힣. 사업 개요', 0),
])
def test_korean_number_marker_is_fourteen_ordered_syllables(tmp_path, text, expected):
    for doc in _documents(tmp_path, [[(text, 1)]]):
        assert doc.sections[0].elements[-1].heading_level == expected


def test_body_and_candidate_size_use_same_tenth_point_rounding(tmp_path):
    for doc in _documents(tmp_path, [[('□ 보통 크기', 7)]], body_shape=7):
        assert doc.sections[0].elements[-1].heading_level == 0


def test_shape_caption_without_picture_stays_body_but_textbox_is_eligible(tmp_path):
    shapes = [CharShape(base_size=1400), CharShape(base_size=1400, bold=True)]
    parser = SectionParser(DocInfo(char_shapes=shapes))
    payload = bytearray()
    for text in [BODY] * 3:
        payload.extend(rec(HWPTAG_PARA_HEADER, 0, bytes(22)))
        payload.extend(rec(HWPTAG_PARA_TEXT, 1, text.encode('utf-16-le') + b'\r\x00'))
        payload.extend(rec(HWPTAG_PARA_CHAR_SHAPE, 1, struct.pack('<II', 0, 0)))
    payload.extend(rec(HWPTAG_PARA_HEADER, 0, bytes(22)))
    payload.extend(rec(HWPTAG_PARA_TEXT, 1, '도형 자리'.encode('utf-16-le') + b'\r\x00'))
    payload.extend(rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()))
    payload.extend(rec(HWPTAG_LIST_HEADER, 2, bytes(8)))
    payload.extend(rec(HWPTAG_PARA_HEADER, 2, bytes(22)))
    payload.extend(rec(HWPTAG_PARA_TEXT, 3, '□ 캡션 제목'.encode('utf-16-le') + b'\r\x00'))
    payload.extend(rec(HWPTAG_PARA_CHAR_SHAPE, 3, struct.pack('<II', 0, 1)))
    payload.extend(rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)))
    payload.extend(rec(HWPTAG_LIST_HEADER, 3, bytes(8)))
    payload.extend(rec(HWPTAG_PARA_HEADER, 3, bytes(22)))
    payload.extend(rec(HWPTAG_PARA_TEXT, 4, '□ 글상자 제목'.encode('utf-16-le') + b'\r\x00'))
    payload.extend(rec(HWPTAG_PARA_CHAR_SHAPE, 4, struct.pack('<II', 0, 1)))
    hwp = Document(sections=[parser.parse_stream(bytes(payload), is_compressed=False)])
    parser.finalize_font_headings(doc=hwp)
    levels = {para.text: para.heading_level for para in hwp.sections[0].elements
              if hasattr(para, 'heading_level')}
    assert levels['□ 캡션 제목'] == 0
    assert levels['□ 글상자 제목'] == 3

    header = ('<hh:charPr id="0" height="1400"/>'
              '<hh:charPr id="1" height="1400"><hh:bold/></hh:charPr>')
    body = ''.join('<hp:p><hp:run charPrIDRef="0"><hp:t>%s</hp:t></hp:run></hp:p>' % BODY
                   for _ in range(3))
    body += ('<hp:p><hp:run><hp:rect>'
             '<hp:caption><hp:subList><hp:p><hp:run charPrIDRef="1">'
             '<hp:t>□ 캡션 제목</hp:t></hp:run></hp:p></hp:subList></hp:caption>'
             '<hp:drawText><hp:subList>'
             '<hp:p><hp:run charPrIDRef="1"><hp:t>□ 글상자 제목</hp:t>'
             '</hp:run></hp:p></hp:subList></hp:drawText></hp:rect>'
             '</hp:run></hp:p>')
    hwpx = HWPXParser().parse(package(tmp_path, body, header))
    assert all(getattr(p, 'text', '') != '□ 캡션 제목'
               for p in hwpx.sections[0].elements)
    assert any(getattr(p, 'text', '') == '□ 글상자 제목' and p.heading_level == 3
               for p in hwpx.sections[0].elements)


def test_emphasis_needs_document_context(tmp_path):
    doc, _ = _documents(tmp_path, [[('□ 추진배경', 2)]])
    paragraphs = doc.sections[0].elements
    paragraphs[-1].heading_level = 0
    finalize_font_headings(paragraphs)
    assert paragraphs[-1].heading_level == 0
