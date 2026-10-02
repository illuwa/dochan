import zlib

import pytest

from dochan.pdf.filters import decode_stream


def _pack_codes(codes, early=1):
    """합성 LZW 코드열. 사전 전이를 바이트 경계와 독립적으로 구성한다."""
    width, next_code, previous = 9, 258, False
    bits = ""
    for code in codes:
        bits += format(code, "0%db" % width)
        if code == 256:
            width, next_code, previous = 9, 258, False
        elif code != 257:
            if previous and next_code < 4096:
                next_code += 1
                if width < 12 and next_code + early == 1 << width:
                    width += 1
            previous = True
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


@pytest.mark.parametrize("early", [0, 1])
def test_lzw_width_transitions_and_clear(early):
    payload = bytes(range(256)) * 18
    codes = [256] + list(payload) + [256, 90, 257]
    warnings = []
    assert decode_stream({"Filter": "LZWDecode", "DecodeParms": {"EarlyChange": early}},
                         _pack_codes(codes, early), warnings) == payload + b"Z"
    assert warnings == []


def test_lzw_kwkwk_and_alias():
    assert decode_stream({"Filter": "LZW"}, _pack_codes([256, 65, 258, 257]), []) == b"AAA"


def test_lzw_invalid_code_and_output_limit(monkeypatch):
    import dochan.pdf.filters as filters
    warnings = []
    assert decode_stream({"Filter": "LZWDecode"}, _pack_codes([256, 300, 257]), warnings) == b""
    assert warnings
    monkeypatch.setattr(filters, "MAX_DECODED_SIZE", 2)
    warnings = []
    assert len(decode_stream({"Filter": "LZWDecode"}, _pack_codes([256, 65, 258, 257]), warnings)) <= 2
    assert warnings


def _pack_samples(samples, bits, padding=0):
    value = "".join(format(sample, "0%db" % bits) for sample in samples)
    tail = -len(value) % 8
    value += format(padding, "0%db" % tail) if tail else ""
    return int(value, 2).to_bytes(len(value) // 8, "big")


@pytest.mark.parametrize("bits", [1, 2, 4, 8, 16])
def test_tiff_predictor_samples_colors_rows_and_padding(bits):
    modulus = 1 << bits
    rows = [[(i * 3 + 1) % modulus for i in range(9)],
            [(i * 7 + 2) % modulus for i in range(9)]]
    encoded, expected = b"", b""
    for row in rows:
        diff = [value if i < 3 else (value - row[i - 3]) % modulus
                for i, value in enumerate(row)]
        encoded += _pack_samples(diff, bits)
        expected += _pack_samples(row, bits)
    parms = {"Predictor": 2, "Columns": 3, "Colors": 3, "BitsPerComponent": bits}
    warnings = []
    assert decode_stream({"Filter": "FlateDecode", "DecodeParms": parms},
                         zlib.compress(encoded), warnings) == expected
    assert warnings == []


def test_filter_specific_decode_parms():
    encoded = _pack_codes([256, 10, 10, 10, 257], early=0)
    assert decode_stream({"Filter": ["ASCIIHexDecode", "LZWDecode"],
                          "DecodeParms": [None, {"EarlyChange": 0, "Predictor": 2, "Columns": 3}]},
                         encoded.hex().encode() + b">", []) == bytes([10, 20, 30])


def test_predictor_extreme_dimensions_and_truncated_row_warn():
    for parms in ({"Columns": 10 ** 100}, {"Columns": 3}, {"BitsPerComponent": 7}):
        warnings = []
        assert decode_stream({"Filter": "FlateDecode", "DecodeParms": dict(parms, Predictor=2)},
                             zlib.compress(b"a"), warnings) == b""
        assert warnings


def test_predictor_real_bits_value_warns_instead_of_raising():
    warnings = []
    assert decode_stream({"Filter": "FlateDecode", "DecodeParms": {
        "Predictor": 2, "BitsPerComponent": 8.0}}, zlib.compress(b"x"), warnings) == b""
    assert warnings


def test_lzw_invalid_code_preserves_decoded_prefix():
    warnings = []
    result = decode_stream({"Filter": "LZWDecode"},
                           _pack_codes([256, 65, 66, 400, 257]), warnings)
    assert result == b"AB"
    assert any("사전 코드" in warning for warning in warnings)


def test_lzw_requires_initial_clear_before_partial_recovery():
    warnings = []
    result = decode_stream({"Filter": "LZWDecode"}, _pack_codes([65, 257]), warnings)
    assert result == b""
    assert any("Clear" in warning for warning in warnings)


@pytest.mark.parametrize("bits", [1, 2, 4])
def test_packed_tiff_predictor_work_budget_preserves_complete_rows(bits, monkeypatch):
    import dochan.pdf.filters as filters
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 9, raising=False)
    row = _pack_samples([1, 0, 0, 0], bits)
    expected_row = _pack_samples([1, 1, 1, 1], bits)
    warnings = []
    result = decode_stream({"Filter": "FlateDecode", "DecodeParms": {
        "Predictor": 2, "Columns": 4, "BitsPerComponent": bits}},
        zlib.compress(row * 3), warnings)
    assert result == expected_row * 2
    assert any("연산 한도" in warning for warning in warnings)
