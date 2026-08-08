from dochan.pdf.content import ContentTextExtractor, default_byte_decoder


def _extract(content: bytes, decoders=None):
    return ContentTextExtractor(decoders or {}).extract(content)


def test_tj_and_td_produce_lines():
    content = b"BT /F1 12 Tf 72 720 Td (Line one) Tj 0 -14 Td (Line two) Tj ET"
    assert _extract(content) == ["Line one", "Line two"]


def test_horizontal_td_stays_on_same_line_with_word_space():
    content = b"BT (Left) Tj 100 0 Td (Right) Tj ET"
    assert _extract(content) == ["Left Right"]


def test_tj_array_inserts_space_on_large_adjustment():
    content = b"BT [(Hello) -500 (world)] TJ ET"
    assert _extract(content) == ["Hello world"]


def test_tj_array_small_adjustment_no_space():
    content = b"BT [(Ke) -40 (rning)] TJ ET"
    assert _extract(content) == ["Kerning"]


def test_tstar_and_quote_start_new_lines():
    content = b"BT (a) Tj T* (b) Tj (c) ' ET"
    assert _extract(content) == ["a", "b", "c"]


def test_tm_same_y_keeps_line_different_y_breaks():
    content = (
        b"BT 1 0 0 1 72 700 Tm (Left) Tj 1 0 0 1 200 700 Tm (Right) Tj "
        b"1 0 0 1 72 680 Tm (Below) Tj ET"
    )
    assert _extract(content) == ["Left Right", "Below"]


def test_words_split_across_bt_blocks_join_with_space():
    # HWP→PDF 내보내기가 흔히 쓰는 패턴: 단어(어절)마다 BT...ET 블록 분리
    content = (
        b"BT 1 0 0 1 72 700 Tm (Hello) Tj ET "
        b"BT 1 0 0 1 120 700 Tm (world) Tj ET "
        b"BT 1 0 0 1 72 680 Tm (Next) Tj ET"
    )
    assert _extract(content) == ["Hello world", "Next"]


def test_font_decoder_selected_by_tf():
    decoders = {"F7": lambda raw: raw.decode("ascii").upper()}
    content = b"BT /F7 10 Tf (abc) Tj ET"
    assert _extract(content, decoders) == ["ABC"]


def test_hex_string_show():
    content = b"BT <414243> Tj ET"
    assert _extract(content) == ["ABC"]


def test_inline_image_is_skipped():
    content = b"BT (before) Tj ET BI /W 1 /H 1 ID \x00\xff\x28 EI BT (after) Tj ET"
    assert _extract(content) == ["before", "after"]


def test_binary_ei_lookalike_inside_inline_image_is_not_terminator():
    # 2차 감수: 이진 데이터 속 우연한 'EI' 는 공백으로 구분되지 않으면 종결자가 아니다
    content = b"BT (a) Tj ET BI /W 1 ID xxEIyy EI BT (b) Tj ET"
    assert _extract(content) == ["a", "b"]


def test_leftward_tm_same_y_starts_new_line():
    # 2차 감수 M5: 같은 기준선이라도 왼쪽 되돌림(2단 조판·표 열)은 병합하면 안 된다
    content = (
        b"BT 1 0 0 1 300 700 Tm (right-col) Tj "
        b"1 0 0 1 72 700 Tm (left-col) Tj ET"
    )
    assert _extract(content) == ["right-col", "left-col"]


def test_default_decoder_cp1252():
    assert default_byte_decoder(b"caf\xe9") == "caf\xe9"
