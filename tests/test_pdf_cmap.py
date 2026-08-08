from dochan.pdf.cmap import parse_tounicode


CMAP_KOREAN = b"""
/CIDInit /ProcSet findresource begin
begincmap
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
2 beginbfchar
<0001> <AC00>
<0002> <D55C>
endbfchar
1 beginbfrange
<0010> <0012> <0041>
endbfrange
endcmap
"""


def test_bfchar_maps_korean_codes():
    cmap = parse_tounicode(CMAP_KOREAN)
    assert cmap.decode(b"\x00\x01\x00\x02") == "가한"  # 가한


def test_bfrange_contiguous():
    cmap = parse_tounicode(CMAP_KOREAN)
    assert cmap.decode(b"\x00\x10\x00\x11\x00\x12") == "ABC"


def test_bfrange_array_form():
    data = b"""
    1 begincodespacerange
    <00> <FF>
    endcodespacerange
    1 beginbfrange
    <20> <22> [<0058> <0059> <005A>]
    endbfrange
    """
    cmap = parse_tounicode(data)
    assert cmap.decode(b"\x20\x21\x22") == "XYZ"


def test_multibyte_destination():
    data = b"""
    1 begincodespacerange
    <00> <FF>
    endcodespacerange
    1 beginbfchar
    <01> <00480069>
    endbfchar
    """
    cmap = parse_tounicode(data)
    assert cmap.decode(b"\x01") == "Hi"


def test_unmapped_code_becomes_replacement_char():
    cmap = parse_tounicode(CMAP_KOREAN)
    assert cmap.decode(b"\x99\x99") == "�"


def test_empty_cmap_defaults_to_single_byte():
    cmap = parse_tounicode(b"nothing here")
    assert cmap.code_lengths == {1}
