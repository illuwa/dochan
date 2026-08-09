"""PDF 좌표 기반 레이아웃 추출 테스트 (글리프 폭 + 텍스트 행렬)."""
from dochan.pdf.content import ContentTextExtractor, FontInfo
from dochan.pdf.widths import WidthMap


def _mono(name="F1", width=600, code_bytes=1):
    # 모든 글리프가 동일 폭인 단순 폰트
    return FontInfo(
        decode=lambda raw: raw.decode("latin-1"),
        widths=WidthMap({}, float(width)),
        code_bytes=code_bytes,
    )


def _extract_fragments(content, fonts):
    ex = ContentTextExtractor.from_fonts(fonts)
    return ex.extract_fragments(content)


def test_fragment_x_advances_by_glyph_width():
    # 12pt 폰트, 폭 600 → 글자당 device 전진 = 600/1000*12 = 7.2
    content = b"BT /F1 12 Tf 100 700 Td (AB) Tj (C) Tj ET"
    frags = _extract_fragments(content, {"F1": _mono(width=600)})
    # 첫 조각 x=100, 둘째 조각(C)은 AB(2글자) 뒤 = 100 + 14.4
    assert abs(frags[0].x - 100) < 0.01
    assert frags[0].text == "AB"
    assert abs(frags[1].x - (100 + 14.4)) < 0.01


def test_wide_x_gap_becomes_space_in_line():
    # 같은 줄에서 Td 로 큰 수평 이동 → 공백 삽입
    content = b"BT /F1 10 Tf 72 700 Td (Left) Tj 200 0 Td (Right) Tj ET"
    ex = ContentTextExtractor.from_fonts({"F1": _mono(width=500)})
    lines = ex.extract(content)
    assert lines == ["Left Right"]


def test_different_y_splits_lines_in_reading_order():
    content = (
        b"BT /F1 10 Tf 72 700 Td (First line) Tj ET "
        b"BT /F1 10 Tf 72 680 Td (Second line) Tj ET"
    )
    ex = ContentTextExtractor.from_fonts({"F1": _mono()})
    assert ex.extract(content) == ["First line", "Second line"]


def test_two_column_reading_order_top_to_bottom_left_to_right():
    # 왼쪽 칼럼(x=72) 2줄, 오른쪽 칼럼(x=320) 2줄이 뒤섞여 그려져도
    # 읽기 순서는 각 줄 y 기준으로 정렬
    content = (
        b"BT /F1 10 Tf 72 700 Td (L1) Tj ET "
        b"BT /F1 10 Tf 320 700 Td (R1) Tj ET "
        b"BT /F1 10 Tf 72 680 Td (L2) Tj ET "
        b"BT /F1 10 Tf 320 680 Td (R2) Tj ET"
    )
    ex = ContentTextExtractor.from_fonts({"F1": _mono()})
    lines = ex.extract(content)
    # 같은 y 는 한 줄로: "L1 R1", "L2 R2"
    assert lines == ["L1 R1", "L2 R2"]


def test_cid_two_byte_codes_advance_correctly():
    content = b"BT /F1 10 Tf 72 700 Td <00410042> Tj <0058> Tj ET"
    fonts = {
        "F1": FontInfo(
            decode=lambda raw: bytes(raw[i + 1] for i in range(0, len(raw), 2)).decode("latin-1"),
            widths=WidthMap({0x41: 1000, 0x42: 1000, 0x58: 1000}, 1000.0),
            code_bytes=2,
        )
    }
    frags = _extract_fragments(content, fonts)
    assert frags[0].text == "AB"
    # 2글자 × (1000/1000*10) = 20 전진 후 X
    assert abs(frags[1].x - (72 + 20)) < 0.01
    assert frags[1].text == "X"


def test_bold_italic_flags_from_font_carry_to_runs():
    from dochan.pdf.content import ContentTextExtractor, FontInfo
    from dochan.pdf.widths import WidthMap

    plain = FontInfo(decode=lambda r: r.decode("latin-1"), widths=WidthMap({}, 500.0))
    bold = FontInfo(decode=lambda r: r.decode("latin-1"), widths=WidthMap({}, 500.0), bold=True)
    ital = FontInfo(decode=lambda r: r.decode("latin-1"), widths=WidthMap({}, 500.0), italic=True)
    content = (
        b"BT /P 10 Tf 72 700 Td (normal ) Tj "
        b"/B 10 Tf (bold ) Tj /I 10 Tf (italic) Tj ET"
    )
    ex = ContentTextExtractor.from_fonts({"P": plain, "B": bold, "I": ital})
    line = ex.extract_lines(content)[0]
    # 서식별로 run 이 분리되어야 한다
    flags = [(t.strip(), b, i) for t, b, i in line.runs if t.strip()]
    assert ("normal", False, False) in flags
    assert ("bold", True, False) in flags
    assert ("italic", False, True) in flags
