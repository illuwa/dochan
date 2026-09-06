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


def test_ctm_scale_translation_flip_and_restore():
    import pytest

    ex = ContentTextExtractor.from_fonts({"F1": _mono(width=500)})
    frags = ex.extract_fragments(
        b"Q q 2 0 0 -2 100 700 cm BT /F1 10 Tf 3 4 Td (AB) Tj ET Q "
        b"BT /F1 10 Tf 3 4 Td (C) Tj ET"
    )
    assert (frags[0].x, frags[0].y, frags[0].width, frags[0].size,
            frags[0].space_width) == pytest.approx((106, 692, 20, 20, 10))
    assert (frags[1].x, frags[1].y) == (3, 4)
    assert [f.order for f in frags] == [0, 1]


def test_nested_graphics_states_and_overflow_restore_outer_state():
    ex = ContentTextExtractor()
    content = (b"q 1 0 0 1 10 0 cm " + b"q " * 300 + b"Q " * 300
               + b"BT /F1 10 Tf (inner) Tj ET Q BT /F1 10 Tf (outer) Tj ET")
    frags = ex.extract_fragments(content)
    assert [f.x for f in frags] == [10, 0]


def test_separate_ctm_blocks_sort_words_and_split_baselines():
    ex = ContentTextExtractor()
    assert ex.extract(
        b"q 1 0 0 1 50 700 cm BT /F1 10 Tf (right) Tj ET Q "
        b"q 1 0 0 1 10 700 cm BT /F1 10 Tf (left) Tj ET Q "
        b"q 1 0 0 1 10 680 cm BT /F1 10 Tf (next) Tj ET Q"
    ) == ["left right", "next"]


def test_large_font_baseline_tolerance_scales():
    ex = ContentTextExtractor()
    assert ex.extract(b"BT /F1 20 Tf 0 100 Td (A) Tj 30 -6 Td (B) Tj ET") == ["A B"]


def test_paths_paint_clip_rectangles_and_ctm():
    ex = ContentTextExtractor()
    page = ex.extract_page(
        b"0 0 m 10 0 l S 0 0 100 100 re W n "
        b"20 20 10 10 re S 0 0 100 100 re f 0 40 20 1 re f "
        b"0 0 m 10 10 l S q 2 0 0 -2 10 100 cm 0 0 m 10 0 l S Q"
    )
    assert len(page.segments) == 10
    assert (page.segments[-1].x0, page.segments[-1].y0,
            page.segments[-1].x1, page.segments[-1].y1) == (10, 100, 30, 100)


def test_segment_budget_preserves_text_and_warns():
    page = ContentTextExtractor().extract_page(
        b"0 0 m 10 0 l S " * 20001 + b"BT (alive) Tj ET"
    )
    assert len(page.segments) == 20000
    assert len(page.warnings) == 1
    assert page.fragments[0].text == "alive"


def test_noncommuting_ctm_and_text_matrix_composition():
    import pytest

    frags = ContentTextExtractor().extract_fragments(
        b'1 0 0 1 100 200 cm 2 0 0 3 0 0 cm '
        b'BT /F1 10 Tf 0 1 -1 0 4 5 Tm (ab) Tj (c) Tj ET'
    )
    assert (frags[0].x, frags[0].y, frags[0].width) == pytest.approx((108, 215, 30))
    assert frags[0].size == pytest.approx(10 * 6 ** 0.5)
    assert (frags[1].x, frags[1].y) == pytest.approx((108, 245))


def test_graphics_restore_text_parameters_but_not_text_matrix():
    frags = ContentTextExtractor().extract_fragments(
        b'BT /F1 10 Tf q /F1 20 Tf (a) Tj Q (b) Tj ET'
    )
    assert [f.size for f in frags] == [20, 10]
    assert [f.x for f in frags] == [0, 10]


def test_closepath_curves_paints_and_inline_image_skipping():
    ex = ContentTextExtractor()
    page = ex.extract_page(
        b'0 0 m 10 0 l 10 10 l h B* '
        b'20 0 m 20 10 l s '
        b'30 0 m 30 2 30 8 30 10 c S '
        b'40 0 m 40 2 40 10 v S 50 0 m 50 2 50 10 y S '
        b'BI /W 1 /H 1 ID 0 0 m 100 0 l S EI BT (safe) Tj ET'
    )
    assert len(page.segments) == 7
    assert page.fragments[0].text == 'safe'


def test_huge_clip_path_does_not_emit_segments_or_budget_warning():
    page = ContentTextExtractor().extract_page(
        b'0 0 m ' + b'10 0 l 0 0 l ' * 10001 + b'W* n BT (safe) Tj ET'
    )
    assert page.segments == []
    assert page.warnings == []
