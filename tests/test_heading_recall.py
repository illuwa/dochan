"""실제 HWP 레코드와 HWPX XML에서 강조 절 제목의 공통 판정."""

import html
import struct

import pytest

from dochan.constants import HWPTAG_PARA_CHAR_SHAPE, HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT
from dochan.hwp.doc_info import DocInfo
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Document
from dochan.utils.heading_font import finalize_font_headings
from test_hwp_section_controls import rec
from test_hwpx_controls import package


BODY = '본문 문장은 충분히 길게 이어지며 관련 사실을 설명합니다.'
SHAPES = [(14, False), (15, False), (14, True), (15, True), (12, False)]


def _documents(tmp_path, parts):
    """parts: 문단별 (문자열, 글자 모양 ID) 런 목록."""
    body_parts = [[(BODY, 0)] for _ in range(3)] + parts
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
