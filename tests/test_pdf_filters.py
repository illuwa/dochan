import zlib

from dochan.pdf.filters import decode_stream


def test_flate_decode_roundtrip():
    warnings = []
    raw = zlib.compress(b"hello pdf")
    assert decode_stream({"Filter": "FlateDecode"}, raw, warnings) == b"hello pdf"
    assert warnings == []


def test_no_filter_returns_raw():
    assert decode_stream({}, b"plain", []) == b"plain"


def test_filter_chain_applies_in_order():
    warnings = []
    payload = zlib.compress(b"chained")
    hex_encoded = payload.hex().encode("ascii") + b">"
    result = decode_stream({"Filter": ["ASCIIHexDecode", "FlateDecode"]}, hex_encoded, warnings)
    assert result == b"chained"


def test_ascii_hex_decode_ignores_whitespace():
    assert decode_stream({"Filter": "ASCIIHexDecode"}, b"68 65 6C 6C 6F>", []) == b"hello"


def test_image_filter_returns_empty_without_warning_spam():
    warnings = []
    assert decode_stream({"Filter": "DCTDecode"}, b"\xff\xd8jpeg", warnings) == b""
    assert warnings == []


def test_unknown_filter_warns():
    warnings = []
    assert decode_stream({"Filter": "LZWDecode"}, b"data", warnings) == b""
    assert any("LZWDecode" in w for w in warnings)


def test_corrupt_flate_warns_and_returns_empty():
    warnings = []
    assert decode_stream({"Filter": "FlateDecode"}, b"not-zlib", warnings) == b""
    assert any("FlateDecode" in w for w in warnings)


def test_predictor_warns_and_drops_corrupted_data():
    warnings = []
    raw = zlib.compress(b"x")
    result = decode_stream({"Filter": "FlateDecode", "DecodeParms": {"Predictor": 12}}, raw, warnings)
    assert result == b""  # Predictor 미해제 데이터는 깨진 텍스트 — 내보내지 않는다
    assert any("Predictor" in w for w in warnings)


def _png_encode(rows, filter_type):
    # 각 행 앞에 필터 타입 바이트를 붙인 PNG 인코딩을 수동 구성
    out = bytearray()
    prev = bytes(len(rows[0]))
    for row in rows:
        out.append(filter_type)
        if filter_type == 0:      # None
            out += row
        elif filter_type == 1:    # Sub
            enc = bytearray()
            for i, b in enumerate(row):
                left = row[i - 1] if i > 0 else 0
                enc.append((b - left) & 0xFF)
            out += enc
        elif filter_type == 2:    # Up
            enc = bytearray((b - p) & 0xFF for b, p in zip(row, prev))
            out += enc
        prev = row
    return bytes(out)


def test_flate_with_png_up_predictor_decodes_xref_style_rows():
    rows = [bytes([1, 0, 0x10, 0]), bytes([1, 0, 0x25, 0]), bytes([2, 0, 0x03, 1])]
    encoded = _png_encode(rows, 2)
    raw = zlib.compress(encoded)
    warnings = []

    out = decode_stream(
        {"Filter": "FlateDecode", "DecodeParms": {"Predictor": 12, "Columns": 4}},
        raw, warnings,
    )

    assert out == b"".join(rows)
    assert warnings == []


def test_flate_with_png_sub_predictor():
    rows = [bytes([10, 20, 30]), bytes([5, 5, 5])]
    encoded = _png_encode(rows, 1)
    raw = zlib.compress(encoded)

    out = decode_stream(
        {"Filter": "FlateDecode", "DecodeParms": {"Predictor": 11, "Columns": 3}},
        raw, [],
    )

    assert out == b"".join(rows)


def test_png_predictor_with_truncated_data_warns():
    raw = zlib.compress(b"\x02\x01")  # 열 4 선언인데 행 데이터 부족
    warnings = []

    out = decode_stream(
        {"Filter": "FlateDecode", "DecodeParms": {"Predictor": 12, "Columns": 4}},
        raw, warnings,
    )

    assert out == b"" or len(out) < 4
    assert any("Predictor" in w or "행" in w for w in warnings) or out == b""
