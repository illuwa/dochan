"""ToUnicode 없는 CID 폰트의 안전한 문자 복원."""
import struct

from dochan.pdf.cid_unicode import MAX_CMAP_GROUPS, MAX_FONT_BYTES, adobe_cid, reverse_truetype_cmap
from dochan.pdf.reader import PDFReader
from dochan.pdf.objects import PDFRef
from dochan.pdf.structure import PDFFile
from test_pdf_structure import _build_pdf


def _stream(data):
    return b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"


def _document(tmp_path, font, raw, extra=None):
    content = b"BT /F1 12 Tf 72 720 Td <" + raw.hex().encode() + b"> Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        4: font,
        5: _stream(content),
    }
    objects.update(extra or {})
    path = tmp_path / "cid.pdf"
    path.write_bytes(_build_pdf(objects))
    return PDFReader().read(str(path))


def _sfnt_format4():
    # U+0041 -> GID 3, U+0042 -> GID 4. One segment and the sentinel.
    subtable = struct.pack(">HHHHHHH", 4, 32, 0, 4, 4, 1, 0)
    subtable += struct.pack(">HHHHHHHHH", 0x42, 0xffff, 0, 0x41, 0xffff,
                            (3 - 0x41) & 0xffff, 1, 0, 0)
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + subtable
    return (struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
            + b"cmap" + struct.pack(">III", 0, 28, len(cmap)) + cmap)


def test_adobe_japan1_identity_cid_recovers_text(tmp_path):
    font = ("<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>")
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) /Supplement 7 >> >>")
    doc = _document(tmp_path, font, b"\x00\x22\x00\x23", {6: cid})
    assert doc.sections[0].elements[0].text == "AB"
    assert not any("ToUnicode 없는 CID" in e for e in doc.errors)


def test_undefined_adobe_cid_is_dropped_with_warning(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) >> >>")
    doc = _document(tmp_path, font, b"\x00\x00\x00\x22", {6: cid})
    assert doc.sections[0].elements[0].text == "A"
    assert any("일부 문자의 대응" in e for e in doc.errors)


def test_private_use_adobe_cid_is_not_emitted(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType0 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) >> >>")
    doc = _document(tmp_path, font, (15447).to_bytes(2, "big") + b"\x00\x22", {6: cid})
    assert doc.sections[0].elements[0].text == "A"
    assert any("일부 문자의 대응" in e for e in doc.errors)


def test_embedded_truetype_gid_map_recovers_text(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> /CIDToGIDMap 8 0 R "
           "/FontDescriptor << /FontFile2 7 0 R >> >>")
    gid_map = b"\x00\x00\x00\x04\x00\x03"
    doc = _document(tmp_path, font, b"\x00\x02\x00\x01", {
        6: cid, 7: _stream(_sfnt_format4()), 8: _stream(gid_map)})
    assert doc.sections[0].elements[0].text == "AB"


def test_truncated_embedded_font_keeps_warning(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> "
           "/FontDescriptor << /FontFile2 7 0 R >> >>")
    doc = _document(tmp_path, font, b"\x00\x01", {6: cid, 7: _stream(b"bad")})
    assert any("ToUnicode 없는 CID" in e for e in doc.errors)


def test_oversized_cmap_group_count_is_bounded():
    subtable = struct.pack(">HHIII", 12, 0, 16, 0, MAX_CMAP_GROUPS + 1)
    cmap = struct.pack(">HHHHI", 0, 1, 3, 10, 12) + subtable
    font = (struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
            + b"cmap" + struct.pack(">III", 0, 28, len(cmap)) + cmap)
    assert reverse_truetype_cmap(font) == {}


def test_oversized_embedded_font_is_rejected_before_parsing():
    assert reverse_truetype_cmap(b"\0" * (MAX_FONT_BYTES + 1)) == {}


def test_cyclic_fontfile_reference_does_not_abort_document(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> "
           "/FontDescriptor << /FontFile2 7 0 R >> >>")
    doc = _document(tmp_path, font, b"\x00\x01", {6: cid, 7: "7 0 R"})
    assert any("ToUnicode 없는 CID" in e for e in doc.errors)


def test_embedded_identity_gid_does_not_use_adobe_collection(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    for gid_map in ("", "/CIDToGIDMap /Identity "):
        cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
               "<< /Registry (Adobe) /Ordering (Japan1) >> " + gid_map +
               "/FontDescriptor << /FontFile2 7 0 R >> >>")
        doc = _document(tmp_path, font, b"\x00\x22", {6: cid, 7: _stream(_sfnt_format4())})
        assert not any("A" in element.text for element in doc.sections[0].elements)
        assert any("ToUnicode 없는 CID" in e for e in doc.errors)


def test_embedded_explicit_gid_map_can_use_adobe_collection(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Japan1) >> /CIDToGIDMap 8 0 R "
           "/FontDescriptor << /FontFile2 7 0 R >> >>")
    doc = _document(tmp_path, font, b"\x00\x22", {
        6: cid, 7: _stream(_sfnt_format4()), 8: _stream(b"\x00" * 70)})
    assert doc.sections[0].elements[0].text == "A"


def _sfnt_subtable(subtable, encoding=10):
    cmap = struct.pack(">HHHHI", 0, 1, 3, encoding, 12) + subtable
    return (struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
            + b"cmap" + struct.pack(">III", 0, 28, len(cmap)) + cmap)


def test_format12_many_groups_and_gid_zero():
    groups = [(0x10000 + i, 0x10000 + i, i + 1) for i in range(5000)]
    groups.insert(0, (0x41, 0x41, 0))
    subtable = struct.pack(">HHIII", 12, 0, 16 + len(groups) * 12, 0, len(groups))
    subtable += b"".join(struct.pack(">III", *group) for group in groups)
    reverse = reverse_truetype_cmap(_sfnt_subtable(subtable))
    assert 0 not in reverse
    assert reverse[5000] == chr(0x10000 + 4999)


def test_shared_gid_prefers_canonical_character():
    groups = [(0x2f00, 0x2f00, 3), (0x4e00, 0x4e00, 3)]
    subtable = struct.pack(">HHIII", 12, 0, 40, 0, 2)
    subtable += b"".join(struct.pack(">III", *group) for group in groups)
    assert reverse_truetype_cmap(_sfnt_subtable(subtable))[3] == "一"


def test_adobe_variation_selector_stripped_to_base_character():
    assert adobe_cid("Japan1", 230) == "0"
    assert adobe_cid("Japan1", 632) == "0"
    assert adobe_cid("Japan1", 1133) == "\u9022"


def test_noncharacters_are_not_usable():
    from dochan.pdf.cid_unicode import _usable
    assert not _usable("\ufdd0")
    assert not _usable("\U0001fffe")
    assert not _usable("\uffff")
    assert _usable("\u9022")


def test_adobe_cid_with_newer_unicode_scalar_is_stable():
    assert adobe_cid("Japan1", 12269) == "\U0001b132"


def test_format4_understated_length_keeps_valid_segments():
    font = bytearray(_sfnt_format4())
    struct.pack_into(">H", font, 28 + 12 + 2, 28)
    assert reverse_truetype_cmap(bytes(font))[3] == "A"


def test_format4_wrapped_length_keeps_valid_segments():
    subtable = bytearray(struct.pack(">HHHHHHH", 4, 28, 0, 4, 4, 1, 0))
    subtable += struct.pack(">HHHHHHHHH", 65, 0xffff, 0, 65, 0xffff,
                            0, 0, 65534, 0)
    subtable.extend(b"\0" * (65562 - len(subtable)))
    subtable.extend(b"\x00\x03")
    assert len(subtable) == 65564
    assert reverse_truetype_cmap(_sfnt_subtable(bytes(subtable), encoding=1))[3] == "A"


def test_format12_notdef_gid_is_excluded():
    subtable = struct.pack(">HHIII", 12, 0, 28, 0, 1)
    subtable += struct.pack(">III", 65, 65, 0)
    assert reverse_truetype_cmap(_sfnt_subtable(subtable)) == {}


def test_identity_v_and_kr_collection_decoder():
    font = "<< /Subtype /Type0 /Encoding /Identity-V /DescendantFonts [6 0 R] >>"
    cid = "<< /Subtype /CIDFontType0 /CIDSystemInfo << /Registry (Adobe) /Ordering (KR) >> >>"
    pdf = PDFFile(_build_pdf({4: font, 6: cid}))
    decoder = PDFReader()._cid_fallback_decoder(pdf, "F1", pdf.resolve(PDFRef(4, 0)))
    assert decoder.decode(b"\x00\x01") == " "
    assert decoder.space_code == 1


def test_embedded_space_cid_and_shared_cmap_cache(monkeypatch):
    font = "<< /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> /CIDToGIDMap 8 0 R "
           "/FontDescriptor << /FontFile2 7 0 R >> /W [5 [250]] >>")
    groups = [(32, 32, 3), (65, 65, 4)]
    subtable = struct.pack(">HHIII", 12, 0, 40, 0, 2)
    subtable += b"".join(struct.pack(">III", *group) for group in groups)
    gid_map = b"\x00" * 10 + b"\x00\x03\x00\x04"
    pdf = PDFFile(_build_pdf({4: font, 6: cid, 7: _stream(_sfnt_subtable(subtable)),
                              8: _stream(gid_map)}))
    import dochan.pdf.reader as reader_module
    original = reader_module.reverse_truetype_cmap
    calls = []

    def counted(data):
        calls.append(1)
        return original(data)

    monkeypatch.setattr(reader_module, "reverse_truetype_cmap", counted)
    resolved = pdf.resolve(PDFRef(4, 0))
    reader = PDFReader()
    assert reader._build_font_info(pdf, "F1", resolved).space_code == 5
    assert reader._build_font_info(pdf, "F2", resolved).space_code == 5
    assert len(calls) == 1


def test_corrupt_optional_font_stream_keeps_only_cid_warning(tmp_path):
    font = "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> "
           "/FontDescriptor << /FontFile2 7 0 R >> >>")
    broken = b"<< /Length 3 /Filter /FlateDecode >>\nstream\nbad\nendstream"
    doc = _document(tmp_path, font, b"\x00\x01", {6: cid, 7: broken})
    assert any("ToUnicode 없는 CID" in e for e in doc.errors)
    assert not any("FlateDecode 실패" in e for e in doc.errors)


def test_optional_font_failure_keeps_document_budget_warning():
    font = "<< /Subtype /Type0 /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    cid = ("<< /Subtype /CIDFontType2 /CIDSystemInfo "
           "<< /Registry (Adobe) /Ordering (Identity) >> "
           "/FontDescriptor << /FontFile2 7 0 R >> >>")
    pdf = PDFFile(_build_pdf({4: font, 6: cid, 7: _stream(_sfnt_format4())}))
    pdf._decode_budget = 0
    assert PDFReader()._cid_fallback_decoder(pdf, "F1", pdf.resolve(PDFRef(4, 0))) is None
    assert any("문서 스트림 해제 총량" in warning for warning in pdf.warnings)
