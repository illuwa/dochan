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


def field_start_block(ctrl_id_le: bytes) -> bytes:
    """확장 컨트롤 3(필드 시작) 16바이트 — 실측: 코드(2)+ctrlId(4)+예비(8)+코드(2)"""
    return struct.pack("<H", 3) + ctrl_id_le + bytes(8) + struct.pack("<H", 3)


def field_end_block() -> bytes:
    """인라인 컨트롤 4(필드 끝) 16바이트"""
    return struct.pack("<H", 4) + b"klh" + bytes(9) + struct.pack("<H", 4)


def hlk_ctrl_payload(command: str) -> bytes:
    """%hlk CTRL_HEADER — 실측(수당 및 제수수료 지급규칙 hexdump):
    ctrlId(4) + 속성(4) + 기타속성(1) + len(UINT16) + Command(UTF-16LE) + 인스턴스ID(4)"""
    cmd = command.encode("utf-16-le")
    return (b"klh%" + struct.pack("<I", 0x800) + b"\x00" +
            struct.pack("<H", len(command)) + cmd + bytes(8))


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


def test_header_footer_ctrl_id_is_head_foot():
    """머리말/꼬리말 ctrlId 는 실측상 'head'/'foot' (LE 저장 b'daeh'/b'toof').
    기존 상수 'hdr '/'ftr ' 로는 실문서 머리말이 전부 무시된다 (회계규칙 실측)."""
    from dochan.model.header_footer import HeaderFooter

    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"daeh" + bytes(8)) +
        rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("머리말 텍스트")) +
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문2")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"toof" + bytes(8)) +
        rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("꼬리말 텍스트"))
    )
    section = parse_section(data)

    hfs = [e for e in section.elements if isinstance(e, HeaderFooter)]
    assert [(hf.type, hf.text) for hf in hfs] == [
        ("header", "머리말 텍스트"), ("footer", "꼬리말 텍스트")]


def test_header_keeps_table_and_nested_image_blocks():
    """머리말 안 표, 그 셀 안 GSO 이미지까지 유지돼야 한다 (회계규칙 실측 구조)."""
    from dochan.constants import HWPTAG_TABLE
    from dochan.model.header_footer import HeaderFooter
    from dochan.model.document import Document

    pic_payload = bytes(71) + struct.pack("<H", 1)
    table_payload = bytes(4) + struct.pack("<HH", 1, 1)
    cell_lh = bytes(8) + struct.pack("<HHHH", 0, 0, 1, 1)
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"daeh" + bytes(8)) +
        rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("머리말 문단")) +
        rec(HWPTAG_CTRL_HEADER, 3, b" lbt" + bytes(4)) +
        rec(HWPTAG_TABLE, 4, table_payload) +
        rec(HWPTAG_LIST_HEADER, 4, cell_lh) +
        rec(HWPTAG_PARA_HEADER, 4, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 5, para_text_payload("셀 텍스트")) +
        rec(HWPTAG_CTRL_HEADER, 5, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMPONENT, 6, bytes(4)) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 7, pic_payload)
    )
    section = parse_section(data)

    hfs = [e for e in section.elements if isinstance(e, HeaderFooter)]
    assert len(hfs) == 1
    assert "셀 텍스트" in hfs[0].text  # 표 블록 유지

    # find_all 로 머리말→표→셀 내부 이미지까지 도달해야 BinData 연결이 가능하다
    doc = Document(sections=[section])
    assert len(doc.find_all('image')) == 1


def test_link_images_uses_one_based_bin_item():
    """SC_PICTURE binItem 은 1-based (실측: 정보보안 세부지침 bin_id 1..12
    ↔ BinDataEntry 12개). 0-based 로 읽으면 한 칸 밀리거나 연결이 빠진다."""
    from dochan.hwp.bin_data import BinDataItem, link_images_to_bin_data
    from dochan.hwp.doc_info import BinDataEntry
    from dochan.model.document import Document, Section

    img = Image(bin_id=1)
    doc = Document(sections=[Section(elements=[img])])
    entries = [BinDataEntry(bin_data_id=7)]
    items = {7: BinDataItem(storage_id=7, data=b"PNGDATA", extension="png")}

    link_images_to_bin_data(doc, items, entries)

    assert img.image_data == b"PNGDATA"
    assert img.filename == "BIN0007.png"


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


# ── Task 2: 하이퍼링크 필드(%hlk) ──

def test_field_command_url_extraction():
    """Command 문자열 → URL: 첫 비이스케이프 ';' 앞까지 + 백슬래시 이스케이프 해제.
    실측 Command 표본 (corpus): 'http\\://www.hancom.co.kr;1;0;0;' 등."""
    from dochan.hwp.records.ctrl_header import parse_field_command_url

    def payload(cmd):
        return hlk_ctrl_payload(cmd)

    assert parse_field_command_url(payload("http\\://www.hancom.co.kr;1;0;0;")) == \
        "http://www.hancom.co.kr"
    assert parse_field_command_url(payload("www.hufscit.com;1;0;0;")) == "www.hufscit.com"
    # 책갈피형('?참조')은 문서 내 책갈피로 가는 내부 하이퍼링크 → '#참조'
    assert parse_field_command_url(payload("?참조;0;0;0;")) == "#참조"
    # 스크립트 링크는 여전히 버린다
    assert parse_field_command_url(payload("javascript\\:\\;;1;0;0;")) == ""
    # 이스케이프된 세미콜론은 URL 의 일부다
    assert parse_field_command_url(payload("http\\://a.kr/x\\;y;1;0;0;")) == "http://a.kr/x;y"


def test_hyperlink_field_applies_link_to_runs():
    """필드 시작(3)~끝(4) 사이 텍스트에 %hlk Command 의 URL 이 걸린다."""
    text_payload = (
        "앞 ".encode("utf-16-le") +
        field_start_block(b"klh%") +
        "www.hufscit.com".encode("utf-16-le") +
        field_end_block() +
        " 뒤".encode("utf-16-le") +
        struct.pack("<H", 13)
    )
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text_payload) +
        rec(HWPTAG_CTRL_HEADER, 1, hlk_ctrl_payload("www.hufscit.com;1;0;0;"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    assert len(paras) == 1
    linked = [r for r in paras[0].runs if r.link]
    assert [r.text for r in linked] == ["www.hufscit.com"]
    assert linked[0].link == "www.hufscit.com"
    # 링크 밖 텍스트에는 링크가 없어야 한다
    assert all(not r.link for r in paras[0].runs if "www" not in r.text)
    assert paras[0].text == "앞 www.hufscit.com 뒤"


def test_hyperlink_multiple_fields_map_in_order():
    """한 문단에 %hlk 가 여럿이면 등장 순서대로 CTRL_HEADER 와 짝을 맺는다."""
    text_payload = (
        field_start_block(b"klh%") +
        "첫째".encode("utf-16-le") +
        field_end_block() +
        " 사이 ".encode("utf-16-le") +
        field_start_block(b"klh%") +
        "둘째".encode("utf-16-le") +
        field_end_block() +
        struct.pack("<H", 13)
    )
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text_payload) +
        rec(HWPTAG_CTRL_HEADER, 1, hlk_ctrl_payload("http\\://one.kr;1;0;0;")) +
        rec(HWPTAG_CTRL_HEADER, 1, hlk_ctrl_payload("http\\://two.kr;1;0;0;"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    links = [(r.text, r.link) for r in paras[0].runs if r.link]
    assert links == [("첫째", "http://one.kr"), ("둘째", "http://two.kr")]


def test_hyperlink_renders_as_markdown_link():
    """마크다운 출력에서 [텍스트](URL) 로 렌더된다 (HWPX 와 동일 경로)."""
    from dochan.model.document import Document
    from dochan.output.markdown import to_markdown

    text_payload = (
        field_start_block(b"klh%") +
        "한컴".encode("utf-16-le") +
        field_end_block() +
        struct.pack("<H", 13)
    )
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text_payload) +
        rec(HWPTAG_CTRL_HEADER, 1, hlk_ctrl_payload("http\\://www.hancom.co.kr;1;0;0;"))
    )
    section = parse_section(data)
    md = to_markdown(Document(sections=[section]))

    assert "[한컴](http://www.hancom.co.kr)" in md


def test_internal_hyperlink_to_bookmark_renders_as_anchor():
    """책갈피형 %hlk('?참조')는 문서 내 책갈피로 가는 내부 하이퍼링크(#참조)로
    렌더된다 (실측 143E433F503322BD33: HWP %hlk '?참조' ↔ HWPX 동일)."""
    from dochan.model.document import Document
    from dochan.output.markdown import to_markdown

    text_payload = (
        field_start_block(b"klh%") +
        "내부참조".encode("utf-16-le") +
        field_end_block() +
        struct.pack("<H", 13)
    )
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text_payload) +
        rec(HWPTAG_CTRL_HEADER, 1, hlk_ctrl_payload("?참조;0;0;0;"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    linked = [(r.text, r.link) for r in paras[0].runs if r.link]
    assert linked == [("내부참조", "#참조")]
    assert to_markdown(Document(sections=[section])) == "[내부참조](#참조)"


# ── 필드 결과 텍스트 + 컨트롤/스마트 태그 텍스트 ──

def field_ctrl_payload(ctrl_id_le: bytes, command: str) -> bytes:
    """임의 필드 CTRL_HEADER — %hlk 와 동일 레이아웃(ctrlId 만 다름)."""
    cmd = command.encode("utf-16-le")
    return (ctrl_id_le + struct.pack("<I", 0x800) + b"\x00" +
            struct.pack("<H", len(command)) + cmd + bytes(8))


def test_click_here_field_result_text_is_captured():
    """누름틀(%clk, CLICK_HERE) — HWP 의 콘텐츠 컨트롤 — 의 결과(표시) 텍스트가
    본문에 그대로 남고 하이퍼링크는 걸리지 않는다.
    (컨트롤/스마트 태그 텍스트 + 필드 결과 텍스트) — 실측 문서관리규칙 '공개'."""
    text_payload = (
        "구분: ".encode("utf-16-le") +
        field_start_block(b"klc%") +          # %clk (LE)
        "공개".encode("utf-16-le") +
        field_end_block() +
        struct.pack("<H", 13)
    )
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text_payload) +
        rec(HWPTAG_CTRL_HEADER, 1, field_ctrl_payload(b"klc%", "publication;"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    assert paras[0].text == "구분: 공개"
    assert all(not r.link for r in paras[0].runs)


def test_formula_field_result_text_is_captured():
    """계산식(%fmu, FORMULA) 필드의 결과 텍스트가 본문에 남는다.
    (필드 결과 텍스트) — 실측 사내벤처 창업 및 운영지침 '100'."""
    text_payload = (
        "합계 ".encode("utf-16-le") +
        field_start_block(b"umf%") +          # %fmu (LE)
        "100".encode("utf-16-le") +
        field_end_block() +
        struct.pack("<H", 13)
    )
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text_payload) +
        rec(HWPTAG_CTRL_HEADER, 1, field_ctrl_payload(b"umf%", "=SUM(?4:?18)??%g,;;100"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    assert paras[0].text == "합계 100"
    assert all(not r.link for r in paras[0].runs)


# ── 내부 북마크 (bokm 컨트롤 + CTRL_DATA) ──

def bokm_ctrl_data(name: str) -> bytes:
    """책갈피 CTRL_DATA(tag 87) — 실측(143E '참조' / 전략물자 'wrapper' hexdump):
    sig(0x021b) + cnt(UINT32) + item(00 40 01 00) + 이름 길이(UINT16, off10)
    + UTF-16LE 이름(off12)."""
    nb = name.encode("utf-16-le")
    return (b"\x1b\x02" + struct.pack("<I", 1) + b"\x00\x40\x01\x00" +
            struct.pack("<H", len(name)) + nb)


def test_bookmark_control_becomes_marker():
    """책갈피(bokm 컨트롤 + CTRL_DATA)의 이름이 [bookmark: NAME] 마커로 나온다.
    (내부 북마크) — 실측 143E433F503322BD33 '참조', 전략물자 종합교육 'wrapper'."""
    from dochan.constants import HWPTAG_CTRL_DATA

    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("이 지침은")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"mkob") +          # 'bokm' (LE)
        rec(HWPTAG_CTRL_DATA, 2, bokm_ctrl_data("wrapper"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    assert len(paras) == 1
    assert "[bookmark: wrapper]" in paras[0].text
    assert "이 지침은" in paras[0].text


def test_bookmark_underscore_name_is_ignored():
    """_GoBack 등 밑줄로 시작하는 자동 책갈피는 마커로 내보내지 않는다 (DOCX 규약)."""
    from dochan.constants import HWPTAG_CTRL_DATA

    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"mkob") +
        rec(HWPTAG_CTRL_DATA, 2, bokm_ctrl_data("_GoBack"))
    )
    section = parse_section(data)

    paras = [e for e in section.elements if isinstance(e, Paragraph)]
    assert paras[0].text == "본문"
    assert "bookmark" not in paras[0].text


# ── Task 3: 이미지 대체 텍스트 (개체 설명문) ──

def test_gso_description_becomes_image_alt_text():
    """개체 공통 속성(표 70) 끝의 설명문이 Image.alt_text 로 들어간다.
    실측: 회계규칙 GSO CTRL_HEADER offset 44 = UINT16 길이 + UTF-16LE,
    내용 '그림입니다.\\r\\n원본 그림의 이름: ...' — HWPX shapeComment 와 동일."""
    pic_payload = bytes(71) + struct.pack("<H", 1)
    desc = "그림입니다.\r\n원본 그림의 이름: CLP0001.bmp"
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("그림 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload(desc)) +
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 3, pic_payload)
    )
    section = parse_section(data)

    images = [e for e in section.elements if isinstance(e, Image)]
    assert len(images) == 1
    # HWPX 는 XML 개행 정규화로 \r\n 이 \n 이 된다 — HWP 쪽도 맞춘다
    assert images[0].alt_text == "그림입니다.\n원본 그림의 이름: CLP0001.bmp"


def test_gso_without_description_has_empty_alt_text():
    """설명문 길이 0 이면 alt_text 는 빈 문자열 (회계규칙 두 번째 GSO 실측)."""
    pic_payload = bytes(71) + struct.pack("<H", 1)
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("그림 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, gso_ctrl_payload()) +
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 3, pic_payload)
    )
    section = parse_section(data)

    images = [e for e in section.elements if isinstance(e, Image)]
    assert images[0].alt_text == ""


def test_gso_truncated_common_properties_is_safe():
    """설명문 필드가 아예 없는 짧은 CTRL_HEADER 도 안전해야 한다."""
    pic_payload = bytes(71) + struct.pack("<H", 1)
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("그림 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, b" osg" + bytes(8)) +  # 44바이트 미만
        rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) +
        rec(HWPTAG_SHAPE_COMP_PICTURE, 3, pic_payload)
    )
    section = parse_section(data)

    images = [e for e in section.elements if isinstance(e, Image)]
    assert len(images) == 1
    assert images[0].alt_text == ""


# ── Task 4: 주석(메모, tcmt) ──

def test_memo_control_becomes_comment_footnote():
    """CTRL_HEADER('tcmt') → LIST_HEADER → PARA_HEADER 구조(han_grammar.hwp
    실측)가 Footnote(type='comment') 로 나온다."""
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"tmct") +
        rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("메모 첫 문단")) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("메모 둘째 문단"))
    )
    section = parse_section(data)

    comments = [e for e in section.elements
                if isinstance(e, Footnote) and e.type == 'comment']
    assert len(comments) == 1
    assert comments[0].text == "메모 첫 문단\n메모 둘째 문단"


def test_memo_renders_as_comment_definition_in_markdown():
    """마크다운에서 comment-N 라벨 정의로 렌더된다 (DOCX 주석과 같은 규약)."""
    from dochan.model.document import Document
    from dochan.output.markdown import to_markdown

    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("본문")) +
        rec(HWPTAG_CTRL_HEADER, 1, b"tmct") +
        rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("검토 의견입니다"))
    )
    section = parse_section(data)
    md = to_markdown(Document(sections=[section]))

    assert "[^comment-1]: 검토 의견입니다" in md


# ── 표 캡션 (실측: 캡션 LIST_HEADER 가 TABLE 레코드 앞에 온다) ──

def table_caption_lh(direction: int = 2) -> bytes:
    """표 캡션 LIST_HEADER — 실측(Trade and Security / 정보보안 hexdump):
    paraCount(UINT32)=1 + attr(UINT32)=0 + 위치(UINT32; 0=L,1=R,2=T,3=B) + 나머지.
    셀 LIST_HEADER(47바이트)와 달리 TABLE 레코드보다 먼저 등장한다."""
    return struct.pack("<I", 1) + struct.pack("<I", 0) + struct.pack("<I", direction) + bytes(18)


def test_table_caption_is_attached_and_dimensions_survive():
    """캡션이 있는 표에서 (1) 캡션이 Table.caption 으로 분리되고
    (2) 캡션 LIST_HEADER 가 셀로 오염되지 않아 표 차원이 보존돼야 한다.

    실측 레코드 순서 (Trade and Security 학술지 운영지침.hwp):
      CTRL_HEADER('tbl ') → LIST_HEADER(캡션) → PARA_HEADER(캡션문단)
      → TABLE → LIST_HEADER(셀) → PARA_HEADER(셀문단)
    캡션 LH 는 TABLE 레코드를 트리 보정으로 자식으로 흡수한다."""
    from dochan.constants import HWPTAG_TABLE
    from dochan.model.table import Table

    table_payload = bytes(4) + struct.pack("<HH", 1, 1)  # 1x1
    cell_lh = bytes(8) + struct.pack("<HHHH", 0, 0, 1, 1)  # col,row,colspan,rowspan
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("표 앞 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, b" lbt" + bytes(4)) +
        rec(HWPTAG_LIST_HEADER, 2, table_caption_lh(direction=2)) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("< 표 1. 캡션 >")) +
        rec(HWPTAG_TABLE, 2, table_payload) +
        rec(HWPTAG_LIST_HEADER, 2, cell_lh) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("셀 텍스트"))
    )
    section = parse_section(data)

    tables = [e for e in section.elements if isinstance(e, Table)]
    assert len(tables) == 1
    table = tables[0]
    # 캡션이 별도 슬롯으로 분리됨
    assert table.caption_text == "< 표 1. 캡션 >"
    assert table.caption_side == "TOP"
    # 차원 보존: 캡션이 셀로 오염되면 1x1 이 무너진다
    assert table.row_count == 1
    assert table.col_count == 1
    assert table.rows[0][0].text == "셀 텍스트"
    # 캡션 텍스트가 셀 안으로 새지 않았다
    assert "캡션" not in table.rows[0][0].text


def test_table_without_caption_still_parses():
    """캡션 없는 표(TABLE 이 CTRL_HEADER 직속 첫 자식)는 기존과 동일해야 한다."""
    from dochan.constants import HWPTAG_TABLE
    from dochan.model.table import Table

    table_payload = bytes(4) + struct.pack("<HH", 1, 1)
    cell_lh = bytes(8) + struct.pack("<HHHH", 0, 0, 1, 1)
    data = (
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, para_text_payload("표 문단")) +
        rec(HWPTAG_CTRL_HEADER, 1, b" lbt" + bytes(4)) +
        rec(HWPTAG_TABLE, 2, table_payload) +
        rec(HWPTAG_LIST_HEADER, 2, cell_lh) +
        rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 3, para_text_payload("셀만"))
    )
    section = parse_section(data)

    tables = [e for e in section.elements if isinstance(e, Table)]
    assert len(tables) == 1
    assert tables[0].caption_text == ""
    assert tables[0].row_count == 1
    assert tables[0].rows[0][0].text == "셀만"
