"""Synthetic MTEF records; public corpus documents never enter CI fixtures."""

import struct

import pytest

from dochan.office_binary.mtef import parse_equation_native, parse_mtef


def char(text):
    return b"".join(b"\x02\x83" + struct.pack("<H", ord(c)) for c in text)


def line(body=b""):
    return b"\x01" + body + b"\x00"


def template(selector, *slots, variation=0):
    return bytes((3, selector, variation, 0)) + b"".join(slots) + b"\x00"


def mtef(body):
    return b"\x03\x01\x01\x03\x00\x0a" + line(body) + b"\x00"


def native(body):
    return struct.pack("<HHII", 28, 0, 0x20000, len(body)) + bytes(16) + body


def test_mtef_v3_characters_and_native_header():
    raw = mtef(char("x=α+2"))
    assert parse_mtef(raw) == r"x=\alpha +2"
    assert parse_equation_native(native(raw)) == r"x=\alpha +2"


def test_mtef_bullet_is_distinct_from_multiplication_dot():
    assert parse_mtef(mtef(char("a•b⋅c"))) == r"a\bullet b\cdot c"


def test_mtef_v3_fraction_and_root():
    fraction = template(14, line(char("a")), line(char("b")))
    root = template(13, line(fraction), b"\x11")
    assert parse_mtef(mtef(root)) == r"\sqrt{\frac{a}{b}}"


@pytest.mark.parametrize("variation,slots,expected", [
    (0, [b"\x11", line(char("2"))], "x^{2}"),
    (1, [line(char("i")), b"\x11"], "x_{i}"),
    (2, [line(char("i")), line(char("2"))], "x_{i}^{2}"),
])
def test_mtef_v3_scripts(variation, slots, expected):
    assert parse_mtef(mtef(char("x") + template(15, *slots, variation=variation))) == expected


def test_mtef_v3_fence_and_overbar():
    bar = template(17, line(char("x")))
    fence = template(1, line(bar), char("("), char(")"))
    assert parse_mtef(mtef(fence)) == r"\left(\overline{x}\right)"


def test_mtef_v5_char_and_fraction():
    def c(s):
        return b"".join(b"\x02\x00\x83" + struct.pack("<H", ord(x)) for x in s)
    def ln(b):
        return b"\x01\x00" + b + b"\x00"
    raw = b"\x05\x01\x00\x06\x00DSMT6\x00\x00" + ln(
        b"\x03\x00\x0b\x00\x00" + ln(c("a")) + ln(c("b")) + b"\x00") + b"\x00"
    assert parse_mtef(raw) == r"\frac{a}{b}"


@pytest.mark.parametrize("raw", [
    b"", b"\x04\x01\x01\x03\x00", mtef(b"\x07"),
    mtef(template(127, line(char("x")))), mtef(char("\uef00")),
    mtef(b"\x02\x83x"), mtef(char("x"))[:-1],
])
def test_mtef_unknown_or_damaged_fails_for_image_fallback(raw):
    with pytest.raises(ValueError):
        parse_mtef(raw)


def test_mtef_rejects_trailing_records_but_allows_zero_padding():
    assert parse_mtef(mtef(char("x")) + bytes(3)) == "x"
    with pytest.raises(ValueError):
        parse_mtef(mtef(char("x")) + char("y"))


def test_mtef_limits_input_depth_and_records():
    with pytest.raises(ValueError, match="size"):
        parse_mtef(bytes(1024 * 1024 + 1))
    nested = char("x")
    for _ in range(70):
        nested = line(nested)
    with pytest.raises(ValueError, match="depth"):
        parse_mtef(mtef(nested))
    with pytest.raises(ValueError, match="record"):
        parse_mtef(mtef(b"\x0a" * 10001))


def test_mtef_output_limit_and_nudge_metadata():
    nested = char("a" * 2000)
    for _ in range(55):
        nested = line(nested)
    with pytest.raises(ValueError, match="output"):
        parse_mtef(mtef(nested))
    nudged = b"\x82\x01\x02\x83x\x00"
    font = b"\x08\x01\x00Times New Roman\x00"
    assert parse_mtef(mtef(font + nudged)) == "x"


def test_mtef_rejects_unknown_template_option_and_character_encoding():
    with pytest.raises(ValueError, match="template options"):
        parse_mtef(mtef(b"\x03\x0f\x01\x01" + line(char("i")) + b"\x11\x00"))
    with pytest.raises(ValueError, match="CHAR options"):
        parse_mtef(mtef(b"\x22\x83x\x00\x00"))


@pytest.mark.parametrize("data", [b"", native(mtef(char("x")))[:-2],
                                      b"\x1b" + native(mtef(char("x")))[1:]])
def test_equation_native_rejects_invalid_header_or_length(data):
    with pytest.raises(ValueError):
        parse_equation_native(data)
