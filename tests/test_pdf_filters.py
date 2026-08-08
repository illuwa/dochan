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


def test_unknown_filter_warns():
    warnings = []
    assert decode_stream({"Filter": "LZWDecode"}, b"data", warnings) == b""
    assert any("LZWDecode" in w for w in warnings)


def test_corrupt_flate_warns_and_returns_empty():
    warnings = []
    assert decode_stream({"Filter": "FlateDecode"}, b"not-zlib", warnings) == b""
    assert any("FlateDecode" in w for w in warnings)


def test_predictor_warns():
    warnings = []
    raw = zlib.compress(b"x")
    decode_stream({"Filter": "FlateDecode", "DecodeParms": {"Predictor": 12}}, raw, warnings)
    assert any("Predictor" in w for w in warnings)
