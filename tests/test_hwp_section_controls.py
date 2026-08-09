"""
tests/test_hwp_section_controls.py — HWP 섹션 컨트롤 파싱 (GSO 도형 텍스트,
하이퍼링크 필드, 이미지 대체 텍스트, 메모)

레코드 스트림은 실물 문서 구조를 그대로 축소한 합성 픽스처다.
구조 근거 (실측 — test_pairs / corpus 실파일 덤프):
  - GSO 텍스트박스: CTRL_HEADER('gso ') → SHAPE_COMPONENT → LIST_HEADER
    → PARA_HEADER(동일 레벨; 트리 보정으로 LH 자식이 됨) → PARA_TEXT
    (정보보안 세부지침(2024년도 8월 개정).hwp 실측 구조와 동일)
  - 하이퍼링크: PARA_TEXT 안 확장 컨트롤 3(필드 시작, ctrlId 'klh%' 내장)
    + 인라인 컨트롤 4(필드 끝), CTRL_HEADER('%hlk')의 Command 에 URL
    (수당 및 제수수료 지급규칙(2024년도 8월 개정).hwp 실측 hexdump 근거)
  - 개체 설명문: GSO CTRL_HEADER 개체 공통 속성(표 70) offset 44 에
    UINT16 길이 + UTF-16LE 문자열 (회계규칙(2024년도 8월 개정).hwp 실측)
  - 메모: CTRL_HEADER('tcmt') → LIST_HEADER → PARA_HEADER
    (han_grammar.hwp / 숨은설명.hwp 실측)
"""
import struct

from dochan.constants import (
    HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_CTRL_HEADER,
    HWPTAG_LIST_HEADER, HWPTAG_SHAPE_COMPONENT, HWPTAG_SHAPE_COMP_PICTURE,
)
from dochan.hwp.section import SectionParser
from dochan.model.document import Paragraph
from dochan.model.image import Image
from dochan.model.header_footer import Footnote


def rec(tag: int, level: int, payload: bytes) -> bytes:
    """HWP 레코드 하나 (헤더 4바이트 + payload)"""
    assert len(payload) < 0xFFF
    return struct.pack("<I", (len(payload) << 20) | (level << 10) | tag) + payload


def para_text_payload(text: str) -> bytes:
    return text.encode("utf-16-le") + struct.pack("<H", 13)  # 13 = 문단 끝


def simple_paragraph(text: str, level: int = 0) -> bytes:
    return (rec(HWPTAG_PARA_HEADER, level, bytes(22)) +
            rec(HWPTAG_PARA_TEXT, level + 1, para_text_payload(text)))


def gso_ctrl_payload(description: str = "") -> bytes:
    """개체 공통 속성(표 70): ctrlId(4)+속성(4)+오프셋(8)+크기(8)+z(4)
    +여백(8)+인스턴스ID(4)+쪽나눔방지(4) = 44바이트, 이어서 설명문."""
    payload = b" osg" + bytes(40)
    desc_bytes = description.encode("utf-16-le")
    payload += struct.pack("<H", len(description)) + desc_bytes
    return payload


def parse_section(data: bytes):
    return SectionParser().parse_stream(data, is_compressed=False)


# ── Task 1: GSO 텍스트박스/도형 내부 텍스트 ──

def test_gso_textbox_text_is_extracted():
    """도형(사각형 등) 내부 문단이 문서 흐름으로 나와야 한다."""
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_LIST_HEADER, 3, bytes(8)) +
        # 실파일과 동일: PARA_HEADER 가 LIST_HEADER 와 같은 레벨로 이어진다
        rec(HWPTAG_PARA_HEADER, 3, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 4, para_text_payload("도형 안 텍스트"))
    )
    section = parse_section(data)

    texts = [e.text for e in section.elements if isinstance(e, Paragraph)]
    assert "본문 문단" in texts
    assert "도형 안 텍스트" in texts


def test_gso_nested_container_text_is_extracted():
    """묶음 개체(SHAPE_COMPONENT 중첩) 안의 텍스트도 나와야 한다."""
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("앞 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_SHAPE_COMPONENT, 3, bytes(4)) +
        rec(HWPTAG_LIST_HEADER, 4, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 4, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 5, para_text_payload("중첩 도형 텍스트"))
    )
    section = parse_section(data)

    texts = [e.text for e in section.elements if isinstance(e, Paragraph)]
    assert "중첩 도형 텍스트" in texts


def test_gso_nested_picture_becomes_image():
    """SC_PICTURE 가 SHAPE_COMPONENT 아래 중첩되어도 Image 로 나와야 한다.
    (실파일 구조 — 기존 코드는 CTRL_HEADER 직속 자식만 봐서 놓쳤다)"""
    pic_payload = bytes(71) + struct.pack("<H", 3)  # binItem=3 at offset 71
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("그림 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 3, pic_payload)
    )
    section = parse_section(data)

    images = [e for e in section.elements if isinstance(e, Image)]
    assert len(images) == 1
    assert images[0].bin_id == 3


def test_gso_direct_picture_child_still_works():
    """기존 구조(SC_PICTURE 가 CTRL_HEADER 직속)도 계속 동작해야 한다."""
    pic_payload = bytes(71) + struct.pack("<H", 1)
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("그림 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 2, pic_payload)
    )
    section = parse_section(data)

    images = [e for e in section.elements if isinstance(e, Image)]
    assert len(images) == 1
    assert images[0].bin_id == 1


def test_gso_caption_is_attached_to_image():
    """GSO 직속 LIST_HEADER(캡션 리스트)의 문단이 Image.caption 으로 붙는다."""
    pic_payload = bytes(71) + struct.pack("<H", 1)
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("그림 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()) +
        rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("그림 1. 캡션")) +
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 3, pic_payload)
    )
    section = parse_section(data)

    images = [e for e in section.elements if isinstance(e, Image)]
    assert len(images) == 1
    assert images[0].caption_text == "그림 1. 캡션"


def test_gso_textbox_text_inside_table_cell():
    """표 셀 안 GSO 도형 텍스트도 셀 문단으로 수집된다 (정보보안 실측 구조)."""
    from dochan.constants import HWPTAG_TABLE
    from dochan.model.table import Table

    table_payload = bytes(4) + struct.pack("<HH", 1, 1)  # 1x1
    cell_lh = bytes(8) + struct.pack("<HHHH", 0, 0, 1, 1)  # col,row,colspan,rowspan
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("표 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, b" lbt" + bytes(4)) +
        rec(HWPTAG_TABLE, 2, table_payload) +
        rec(HWPTAG_LIST_HEADER, 2, cell_lh) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("셀 텍스트")) +
        rec(HWPTAG_CTRL_HEADER, 3, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMPONENT, 4, bytes(4)) +
        rec(HWPTAG_LIST_HEADER, 5, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 5, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 6, para_text_payload("셀 안 도형 텍스트"))
    )
    section = parse_section(data)

    tables = [e for e in section.elements if isinstance(e, Table)]
    assert len(tables) == 1
    cell_text = tables[0].rows[0][0].text
    assert "셀 텍스트" in cell_text
    assert "셀 안 도형 텍스트" in cell_text
