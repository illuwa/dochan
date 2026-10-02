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


def test_unmapped_code_advances_min_size_preserving_next_char():
    # 2차 감수 M2: max(sizes) 만큼 전진하면 미매핑 1바이트가 뒤 문자를 삼킨다
    data = b"""
    2 begincodespacerange
    <00> <80>
    <8100> <FFFF>
    endcodespacerange
    2 beginbfchar
    <41> <0041>
    <42> <0042>
    endbfchar
    """
    cmap = parse_tounicode(data)
    assert cmap.decode(b"\x41\x99\x42") == "A�B"  # 'B' 가 살아남아야 한다


def test_longest_code_length_matched_first():
    # 2차 감수 M3: 짧은 코드 우선 매칭이면 2바이트 코드가 1바이트로 오매칭된다
    data = b"""
    2 begincodespacerange
    <00> <FF>
    <0000> <FFFF>
    endcodespacerange
    2 beginbfchar
    <81> <0058>
    <8140> <D55C>
    endbfchar
    """
    cmap = parse_tounicode(data)
    assert cmap.decode(b"\x81\x40") == "한"
    assert cmap.decode(b"\x81") == "X"


def test_encoding_wmode_named_and_embedded_cmaps():
    from dochan.pdf.cmap import encoding_wmode
    assert encoding_wmode("Identity-V") == 1
    assert encoding_wmode("UniJIS-UTF16-V") == 1
    assert encoding_wmode("Identity-H") == 0
    assert encoding_wmode(data=b"/WMode 1 def") == 1
    assert encoding_wmode(data=b"/Identity-V usecmap") == 1
    assert encoding_wmode(data=b"/Identity-V usecmap /WMode 0 def") == 0
    assert encoding_wmode(data=b"% /WMode 1 def\n/WMode 0 def") == 0
    assert encoding_wmode(dictionary_mode=1) == 1
    assert encoding_wmode("Custom-V") == 0
