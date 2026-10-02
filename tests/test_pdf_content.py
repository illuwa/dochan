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


def _vertical_font(w_array=None, dw2=None):
    from dochan.pdf.content import VerticalMetrics
    widths = WidthMap({1: 600, 2: 1000}, 1000)
    return FontInfo(decode=lambda raw: "".join(chr(64 + c) for c in raw[1::2]),
                    widths=widths, code_bytes=2, wmode=1,
                    vertical_metrics=VerticalMetrics(w_array, dw2, widths))


def test_vertical_nonfinite_geometry_warns_and_keeps_other_text():
    font = _vertical_font([1, [1e308, 1e308, 1e308]])
    extractor = ContentTextExtractor.from_fonts({"F1": font, "F2": _font()})
    page = extractor.extract_page(b"BT /F1 10000 Tf <0001> Tj ET BT /F2 10 Tf 72 700 Td (Safe) Tj ET")
    assert [f.text for f in page.fragments] == ["Safe"]
    assert page.warnings


def test_vertical_default_metrics_and_origins():
    from dochan.pdf.content import writing_direction
    font = _vertical_font()
    content = b"BT /F1 10 Tf 100 700 Td <0001> Tj <0002> Tj ET"
    extractor = ContentTextExtractor.from_fonts({"F1": font})
    a, b = extractor.extract_fragments(content)
    assert (a.x, a.y, a.width) == (97, 691.2, 10)
    assert (b.x, b.y, b.width) == (95, 681.2, 10)
    assert writing_direction(a) == "down"
    assert extractor.extract(content) == ["AB"]


def test_vertical_w2_array_and_range_forms():
    font = _vertical_font([1, [-1200, 300, 900], 2, 3, -800, 500, 700])
    assert font.vertical_metrics.metrics(1) == (-1200, 300, 900)
    assert font.vertical_metrics.metrics(2) == (-800, 500, 700)
    assert font.vertical_metrics.metrics(3) == (-800, 500, 700)
    extractor = ContentTextExtractor.from_fonts({"F1": font})
    a, b = extractor.extract_fragments(b"BT /F1 10 Tf 100 700 Td <0001> Tj <0002> Tj ET")
    assert (a.x, a.y, a.width) == (97, 691, 12)
    assert (b.x, b.y, b.width) == (95, 681, 8)


def test_vertical_tj_adjustment_uses_y_and_ignores_horizontal_scale():
    extractor = ContentTextExtractor.from_fonts({"F1": _vertical_font()})
    content = b"BT /F1 10 Tf 200 Tz 100 700 Td [<0001> 500 <0002>] TJ ET"
    a, b = extractor.extract_fragments(content)
    assert (a.x, a.y, a.width) == (94, 691.2, 10)
    assert (b.x, b.y, b.width) == (90, 676.2, 10)


def test_vertical_ctm_transforms_writing_axis_and_displacement():
    from dochan.pdf.content import writing_direction
    extractor = ContentTextExtractor.from_fonts({"F1": _vertical_font()})
    a, b = extractor.extract_fragments(
        b"0 1 -1 0 0 0 cm BT /F1 10 Tf 100 700 Td <0001> Tj <0002> Tj ET")
    assert writing_direction(a) == "ltr"
    assert a.width == 10
    assert b.x - a.x == 10


def test_vertical_dw2_and_character_spacing():
    extractor = ContentTextExtractor.from_fonts({"F1": _vertical_font(dw2=[900, -1200])})
    a, b = extractor.extract_fragments(
        b"BT /F1 10 Tf 2 Tc 100 700 Td <0001> Tj <0002> Tj ET")
    assert (a.y, a.width, b.y) == (691, 10, 681)


def test_vertical_w2_malformed_and_oversized_ranges_are_bounded():
    font = _vertical_font([0, 100000000, -1000, 500, 880, 1, ["bad", 300, 880]])
    assert font.vertical_metrics.metrics(1) == (-1000, 300, 880)
    assert font.vertical_metrics.warnings


def test_vertical_w2_cumulative_expansion_budget():
    font = _vertical_font([0, 65535, -1000, 500, 880, 0, 65535, -2000, 500, 880])
    assert len(font.vertical_metrics._table) == 65536
    assert font.vertical_metrics.metrics(1) == (-1000, 500, 880)
    assert font.vertical_metrics.warnings
