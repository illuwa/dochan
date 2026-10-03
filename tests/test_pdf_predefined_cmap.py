"""Encoding CMap의 코드 길이와 CID 대응을 검증한다."""
import random
import time

from dochan.pdf.cmap import MAX_ENCODING_BYTES, parse_encoding_cmap, parse_tounicode
from dochan.pdf.content import ContentTextExtractor, FontInfo, VerticalMetrics
from dochan.pdf.objects import PDFRef
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from dochan.pdf.widths import WidthMap
from test_pdf_cid_unicode import _document, _stream
from test_pdf_structure import _build_pdf


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


def test_two_byte_space_uses_explicit_unicode_cid_width():
    encoding = (b"1 begincodespacerange <0000> <ffff> endcodespacerange\n"
                b"1 begincidrange <0020> <0021> 1 endcidrange\n")
    unicode = (b"2 beginbfchar <0020> <0020> <0021> <0041> endbfchar")
    font = ("<< /Type /Font /Subtype /Type0 /Encoding 7 0 R /ToUnicode 8 0 R "
            "/DescendantFonts [6 0 R] >>")
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> /DW 1000 /W [1 [181]] >>")
    pdf = PDFFile(_build_pdf({4: font, 6: cid, 7: _stream(encoding),
                              8: _stream(unicode)}))
    info = PDFReader()._build_font_info(pdf, "F", pdf.resolve(PDFRef(4, 0)))
    assert info.space_code == 1
    assert info.widths.advance(info.space_code) == 181


def test_one_byte_unicode_space_wins_over_literal_0x20():
    encoding = (b"1 begincodespacerange <00> <ff> endcodespacerange\n"
                b"2 begincidchar <01> 1 <20> 32 endcidchar")
    unicode = (b"1 beginbfchar <01> <0020> endbfchar")
    font = ("<< /Type /Font /Subtype /Type0 /Encoding 7 0 R /ToUnicode 8 0 R "
            "/DescendantFonts [6 0 R] >>")
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> "
           "/DW 1000 /W [1 [277] 32 [666]] >>")
    pdf = PDFFile(_build_pdf({4: font, 6: cid, 7: _stream(encoding),
                              8: _stream(unicode)}))
    info = PDFReader()._build_font_info(pdf, "F", pdf.resolve(PDFRef(4, 0)))
    assert info.space_code == 1


def test_many_codespaces_have_bounded_lookup_cost():
    data = (b"10000 begincodespacerange\n" +
            b"<10000000> <10000000>\n" * 10000 +
            b"endcodespacerange")
    cmap = parse_encoding_cmap(data)
    start = time.monotonic()
    assert len(list(cmap.iter_codes(b"\xff" * 1000))) == 1000
    assert time.monotonic() - start < 1.0


def test_empty_embedded_cmap_preserves_two_byte_tounicode(tmp_path):
    unicode = (b"1 begincodespacerange <0000> <ffff> endcodespacerange\n"
               b"3 beginbfchar <0024> <0041> <0025> <0042> <0026> <0043> endbfchar")
    font = ("<< /Type /Font /Subtype /Type0 /Encoding 7 0 R /ToUnicode 8 0 R "
            "/DescendantFonts [6 0 R] >>")
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> /DW 500 >>")
    cases = (b"/Identity-H usecmap", b"unusable",
             b"/Parent usecmap", b"/Parent usecmap")
    for index, source in enumerate(cases):
        if index == 1:
            encoding = b"<< /Length 4 /Filter /JBIG2Decode >>\nstream\nabcd\nendstream"
        elif index == 3:
            encoding = (b"<< /Length 16 /UseCMap 9 0 R >>\nstream\n" +
                        source.ljust(16) + b"\nendstream")
        else:
            encoding = _stream(source)
        doc = _document(tmp_path, font, b"\x00\x24\x00\x25\x00\x26",
                        {6: cid, 7: encoding, 8: _stream(unicode),
                         9: _stream(b"1 begincodespacerange <0000> <ffff> endcodespacerange")})
        assert doc.sections[0].elements[0].text == "ABC"


def test_overlapping_cid_and_notdef_ranges_keep_uncovered_values():
    cmap = parse_encoding_cmap(
        b"1 begincodespacerange <0000> <ffff> endcodespacerange\n"
        b"1 begincidrange <0000> <ffff> 0 endcidrange\n"
        b"1 begincidchar <0041> 100 endcidchar")
    assert list(cmap.iter_codes(b"\x00\x41\x00\x42")) == [
        (b"\x00\x41", 100), (b"\x00\x42", 66)]
    notdef = parse_encoding_cmap(
        b"1 begincodespacerange <0000> <00ff> endcodespacerange\n"
        b"1 beginnotdefrange <0000> <00ff> 7 endnotdefrange\n"
        b"1 beginnotdefchar <0041> 9 endnotdefchar")
    assert list(notdef.iter_codes(b"\x00\x41\x00\x42")) == [
        (b"\x00\x41", 9), (b"\x00\x42", 7)]


def test_incomplete_blocks_do_not_rescan_entire_tail():
    source = b"begincidrange " * 10000
    start = time.monotonic()
    assert not parse_encoding_cmap(source).codespaces
    assert time.monotonic() - start < 1.0


def test_odd_hex_tokens_are_not_accepted_as_encoding_codes():
    cmap = parse_encoding_cmap(
        b"1 begincodespacerange <0> <f> endcodespacerange\n"
        b"1 begincidchar <1> 42 endcidchar")
    assert not cmap.codespaces and not cmap.cidranges


def test_use_cmap_dictionary_name_and_registry(tmp_path):
    font = ("<< /Type /Font /Subtype /Type0 /Encoding 7 0 R "
            "/DescendantFonts [6 0 R] >>")
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) >> >>")
    encoding = (b"<< /Length 0 /UseCMap /90ms-RKSJ-H "
                b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) >> >>\n"
                b"stream\n\nendstream")
    doc = _document(tmp_path, font, b"A", {6: cid, 7: encoding})
    assert doc.sections[0].elements[0].text == "A"


def test_invalid_partial_code_consumes_attempted_length():
    cmap = parse_encoding_cmap(
        b"1 begincodespacerange <8140> <81ff> endcodespacerange")
    assert list(cmap.iter_codes(b"\x81\x00\x81\x40")) == [
        (b"\x81\x00", 0), (b"\x81\x40", 0)]


def test_invalid_single_byte_space_does_not_apply_tw():
    cmap = parse_encoding_cmap(
        b"1 begincodespacerange <8140> <81ff> endcodespacerange")
    font = FontInfo(decode=lambda raw: "A", widths=WidthMap({}, 500),
                    code_bytes=2, encoding_cmap=cmap)
    fragments = ContentTextExtractor.from_fonts({"F": font}).extract_fragments(
        b"BT /F 10 Tf 10 Tw 72 700 Td <20> Tj <8140> Tj ET")
    assert fragments[1].x - fragments[0].x == 5


def test_repeated_bad_codes_warn_once_per_document():
    warnings = []
    cmap = parse_encoding_cmap(
        b"1 begincodespacerange <8140> <81ff> endcodespacerange")
    for _ in range(100):
        list(cmap.iter_codes(b"\xff", warnings))
    assert len(warnings) == 1


def test_linear_tounicode_blocks_preserve_range_precedence():
    source = (b"1 beginbfrange <41> <41> <0041> endbfrange\n"
              b"1 beginbfchar <41> <005A> endbfchar")
    assert parse_tounicode(source).decode(b"A") == "A"
    start = time.monotonic()
    parse_tounicode(b"beginbfchar " * 10000)
    assert time.monotonic() - start < 1.0


def test_shared_encoding_stream_is_parsed_once(monkeypatch):
    font = "<< /Type /Font /Subtype /Type0 /Encoding 7 0 R /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) >> >>")
    encoding = (b"1 begincodespacerange <00> <ff> endcodespacerange\n"
                b"1 begincidchar <41> 34 endcidchar")
    pdf = PDFFile(_build_pdf({4: font, 6: cid, 7: _stream(encoding)}))
    resolved = pdf.resolve(PDFRef(4, 0))
    import dochan.pdf.reader as reader_module
    original = reader_module.parse_encoding_cmap
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(reader_module, "parse_encoding_cmap", counted)
    reader = PDFReader()
    reader._build_font_info(pdf, "F1", resolved)
    reader._build_font_info(pdf, "F2", resolved)
    assert len(calls) == 1
