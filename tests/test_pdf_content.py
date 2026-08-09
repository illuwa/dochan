"""콘텐츠 스트림 텍스트 연산자 해석 — 좌표 기반 계약.

폰트 폭/크기가 있는 실제 지오메트리로 단어 간격·줄바꿈·읽기 순서를
검증한다. (이전 휴리스틱 테스트를 좌표 기반 계약으로 갱신)
"""
from dochan.pdf.content import ContentTextExtractor, FontInfo, default_byte_decoder
from dochan.pdf.widths import WidthMap


def _font(width=500, code_bytes=1, decode=None):
    return FontInfo(
        decode=decode or (lambda raw: raw.decode("latin-1")),
        widths=WidthMap({32: 250}, float(width)),
        code_bytes=code_bytes,
    )


def _extract(content: bytes, fonts=None):
    fonts = fonts or {"F1": _font()}
    return ContentTextExtractor.from_fonts(fonts).extract(content)


def test_tj_and_td_produce_lines():
    content = b"BT /F1 12 Tf 72 720 Td (Line one) Tj 0 -14 Td (Line two) Tj ET"
    assert _extract(content) == ["Line one", "Line two"]


def test_horizontal_td_stays_on_same_line_with_word_space():
    content = b"BT /F1 10 Tf 72 700 Td (Left) Tj 100 0 Td (Right) Tj ET"
    assert _extract(content) == ["Left Right"]


def test_adjacent_runs_no_spurious_space():
    # 인접해 이어지는 런은 공백 없이 붙는다 (폭 기반 전진)
    content = b"BT /F1 10 Tf 72 700 Td (Ker) Tj (ning) Tj ET"
    assert _extract(content) == ["Kerning"]


def test_tstar_starts_new_line():
    content = b"BT /F1 10 Tf 72 700 Td 12 TL (a) Tj T* (b) Tj T* (c) Tj ET"
    assert _extract(content) == ["a", "b", "c"]


def test_tm_same_y_keeps_line_different_y_breaks():
    content = (
        b"BT /F1 10 Tf 1 0 0 1 72 700 Tm (Left) Tj 1 0 0 1 200 700 Tm (Right) Tj "
        b"1 0 0 1 72 680 Tm (Below) Tj ET"
    )
    assert _extract(content) == ["Left Right", "Below"]


def test_hex_string_show():
    content = b"BT /F1 10 Tf 72 700 Td <414243> Tj ET"
    assert _extract(content) == ["ABC"]


def test_inline_image_is_skipped():
    content = (
        b"BT /F1 10 Tf 72 700 Td (before) Tj ET "
        b"BI /W 1 /H 1 ID \x00\xff\x28 EI "
        b"BT /F1 10 Tf 72 680 Td (after) Tj ET"
    )
    assert _extract(content) == ["before", "after"]


def test_binary_ei_lookalike_inside_inline_image_is_not_terminator():
    content = (
        b"BT /F1 10 Tf 72 700 Td (a) Tj ET BI /W 1 ID xxEIyy EI "
        b"BT /F1 10 Tf 72 680 Td (b) Tj ET"
    )
    assert _extract(content) == ["a", "b"]


def test_default_decoder_cp1252():
    assert default_byte_decoder(b"caf\xe9") == "caf\xe9"


def test_extract_sized_reports_line_font_sizes():
    content = (
        b"BT /F1 24 Tf 72 720 Td (Big Title) Tj ET "
        b"BT /F1 10 Tf 72 690 Td (Body text) Tj ET"
    )
    sized = ContentTextExtractor.from_fonts({"F1": _font()}).extract_sized(content)
    assert [(t, round(s)) for t, s in sized] == [("Big Title", 24), ("Body text", 10)]


def test_text_without_font_still_extracts():
    # Tf 미지정이어도 유실되지 않는다 (기본 폰트 폴백)
    content = b"BT 72 700 Td (No font set) Tj ET"
    assert ContentTextExtractor.from_fonts({}).extract(content) == ["No font set"]
