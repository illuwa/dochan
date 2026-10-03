"""ToUnicode 없는 CID 폰트의 안전한 문자 복원."""
import struct

from dochan.pdf.cid_unicode import MAX_CMAP_GROUPS, MAX_FONT_BYTES, reverse_truetype_cmap
from dochan.pdf.reader import PDFReader
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
