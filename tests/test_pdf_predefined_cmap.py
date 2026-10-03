"""Encoding CMap의 코드 길이와 CID 대응을 검증한다."""
import random

from dochan.pdf.cmap import MAX_ENCODING_BYTES, parse_encoding_cmap
from dochan.pdf.content import ContentTextExtractor, FontInfo, VerticalMetrics
from dochan.pdf.widths import WidthMap
from test_pdf_cid_unicode import _document, _stream


def test_embedded_cmap_splits_variable_codes_and_maps_cids():
    data = (b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 0 >> def\n"
            b"2 begincodespacerange <00> <7f> <8140> <81ff> endcodespacerange\n"
            b"1 begincidrange <20> <22> 231 endcidrange\n"
            b"1 begincidchar <8140> 34 endcidchar\n")
    cmap = parse_encoding_cmap(data)
    assert list(cmap.iter_codes(b"\x20\x21\x81\x40")) == [(b"\x20", 231),
                                                               (b"\x21", 232),
                                                               (b"\x81\x40", 34)]
    assert cmap.registry == "Adobe" and cmap.ordering == "Japan1"


def test_predefined_rksj_maps_ascii_and_double_byte():
    from dochan.pdf.cmap import predefined_cmap

    cmap = predefined_cmap("90ms-RKSJ-H")
    assert list(cmap.iter_codes(b"\x41\x81\x40")) == [(b"A", 264),
                                                          (b"\x81\x40", 633)]


def test_invalid_or_truncated_code_consumes_bounded_input():
    data = b"1 begincodespacerange <8140> <81ff> endcodespacerange"
    cmap = parse_encoding_cmap(data)
    warnings = []
    assert list(cmap.iter_codes(b"\xff\x81", warnings)) == [(b"\xff", 0), (b"\x81", 0)]
    assert warnings


def test_cyclic_parent_is_bounded():
    data = b"/Loop usecmap 1 begincodespacerange <00> <ff> endcodespacerange"
    cmap = parse_encoding_cmap(data, parents={"Loop": data})
    assert list(cmap.iter_codes(b"A")) == [(b"A", 0)]


def test_embedded_compact_cmap_tokens_and_four_byte_codespace():
    cmap = parse_encoding_cmap(b"1 begincodespacerange <f0808080><f7bfbfbf> endcodespacerange\n"
                               b"1 begincidrange <f0a2ad8f><f0a2ad90>17671 endcidrange\n"
                               b"1 begincidchar <e0>151 endcidchar")
    assert list(cmap.iter_codes(bytes.fromhex("f0a2ad8ff0a2ad90"))) == [
        (bytes.fromhex("f0a2ad8f"), 17671), (bytes.fromhex("f0a2ad90"), 17672)]


def test_notdef_range_and_predefined_parent():
    cmap = parse_encoding_cmap(b"/90ms-RKSJ-H usecmap\n"
                               b"1 begincidchar <41> 34 endcidchar")
    assert list(cmap.iter_codes(b"A\x82\xa0")) == [(b"A", 34), (b"\x82\xa0", 843)]
    notdef = parse_encoding_cmap(b"1 begincodespacerange <00> <ff> endcodespacerange\n"
                                 b"1 beginnotdefrange <01> <1f> 12 endnotdefrange")
    assert list(notdef.iter_codes(b"\x02")) == [(b"\x02", 12)]


def test_tw_only_on_single_byte_space():
    cmap = parse_encoding_cmap(b"2 begincodespacerange <20> <7f> <0020> <0020> endcodespacerange\n"
                               b"3 begincidchar <20> 231 <0020> 231 <41> 232 endcidchar")
    font = FontInfo(decode=lambda raw: "x", widths=WidthMap({231: 500, 232: 500}, 500),
                    code_bytes=2, encoding_cmap=cmap)
    assert ContentTextExtractor._iter_codes(b"\x20\x00\x20", 2, cmap) == [231, 231]
    extractor = ContentTextExtractor.from_fonts({"F": font})
    one = extractor.extract_fragments(b"BT /F 10 Tf 10 Tw 72 700 Td <20> Tj <41> Tj ET")
    two = extractor.extract_fragments(b"BT /F 10 Tf 10 Tw 72 700 Td <0020> Tj <41> Tj ET")
    assert one[1].x - one[0].x == 15
    assert two[1].x - two[0].x == 5


def test_horizontal_and_vertical_metrics_use_cid():
    from dochan.pdf.cmap import predefined_cmap

    cmap = predefined_cmap("90ms-RKSJ-H")
    widths = WidthMap({264: 1000}, 500)
    horizontal = FontInfo(decode=lambda raw: "A", widths=widths,
                          code_bytes=2, encoding_cmap=cmap)
    fragment = ContentTextExtractor.from_fonts({"F": horizontal}).extract_fragments(
        b"BT /F 10 Tf 72 700 Td <41> Tj ET")[0]
    assert fragment.width == 10
    vertical = FontInfo(decode=lambda raw: "A", widths=widths, code_bytes=2,
                        wmode=1, encoding_cmap=cmap,
                        vertical_metrics=VerticalMetrics([264, [-1200, 300, 900]], None, widths))
    fragment = ContentTextExtractor.from_fonts({"F": vertical}).extract_fragments(
        b"BT /F 10 Tf 72 700 Td <41> Tj ET")[0]
    assert fragment.width == 12


def test_large_and_random_cmaps_do_not_escape_bounds():
    warnings = []
    assert not parse_encoding_cmap(b"x" * (MAX_ENCODING_BYTES + 1), warnings).codespaces
    assert warnings
    rng = random.Random(43)
    for _ in range(100):
        data = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 2000)))
        cmap = parse_encoding_cmap(data)
        assert len(list(cmap.iter_codes(data[:100]))) <= 100


def test_predefined_font_recovers_without_tounicode(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /90ms-RKSJ-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) /Supplement 7 >> "
           "/DW 1000 /W [264 [500] 843 [750]] >>")
    doc = _document(tmp_path, font, b"A\x82\xa0", {6: cid})
    assert doc.sections[0].elements[0].text == "Aあ"
    assert not any("ToUnicode 없는 CID" in message for message in doc.errors)


def test_embedded_cmap_uses_original_code_for_tounicode(tmp_path):
    encoding = (b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 0 >> def\n"
                b"1 begincodespacerange <20> <7e> endcodespacerange\n"
                b"1 begincidchar <41> 34 endcidchar\n")
    unicode = (b"1 begincodespacerange <41> <41> endcodespacerange\n"
               b"1 beginbfchar <41> <005A> endbfchar\n")
    font = ("<< /Type /Font /Subtype /Type0 /Encoding 7 0 R /ToUnicode 8 0 R "
            "/DescendantFonts [6 0 R] >>")
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) >> >>")
    doc = _document(tmp_path, font, b"A", {6: cid, 7: _stream(encoding), 8: _stream(unicode)})
    assert doc.sections[0].elements[0].text == "Z"


def test_mismatched_collection_is_not_guessed(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /90ms-RKSJ-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (GB1) >> >>")
    doc = _document(tmp_path, font, b"A", {6: cid})
    assert any("CIDSystemInfo 불일치" in message for message in doc.errors)
    assert not doc.sections[0].elements
