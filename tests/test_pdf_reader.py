import zlib

from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf, _minimal_objects


def _write(tmp_path, name, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_reads_single_page_text(tmp_path):
    content = b"BT /F1 12 Tf 72 720 Td (Hello PDF) Tj ET"
    path = _write(tmp_path, "one.pdf", _build_pdf(_minimal_objects(content)))

    doc = PDFReader().read(path)

    assert doc.source_format == "pdf"
    assert len(doc.sections) == 1
    para = doc.sections[0].elements[0]
    assert para.text == "Hello PDF"
    assert para.provenance.source_format == "pdf"
    assert para.provenance.page == 1
    assert doc.sections[0].provenance.page == 1


def test_reads_multiple_pages_in_order(tmp_path):
    c1 = b"BT (Page one) Tj ET"
    c2 = b"BT (Page two) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
    }
    path = _write(tmp_path, "two.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert len(doc.sections) == 2
    assert doc.sections[0].elements[0].text == "Page one"
    assert doc.sections[1].elements[0].text == "Page two"
    assert doc.sections[1].elements[0].provenance.page == 2


def test_flate_compressed_content(tmp_path):
    body = zlib.compress(b"BT (Compressed) Tj ET")
    objects = _minimal_objects()
    objects[5] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream" % (len(body), body)
    path = _write(tmp_path, "flate.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert doc.sections[0].elements[0].text == "Compressed"


def test_contents_array_concatenated(tmp_path):
    c1 = b"BT (First) Tj ET"
    c2 = b"BT (Second) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents [5 0 R 6 0 R] >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
    }
    path = _write(tmp_path, "arr.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    texts = [p.text for p in doc.sections[0].elements]
    assert texts == ["First", "Second"]


def test_tounicode_font_decodes_korean(tmp_path):
    cmap = (
        b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        b"2 beginbfchar\n<0001> <AC00>\n<0002> <B098>\nendbfchar\n"
    )
    content = b"BT /F1 12 Tf <00010002> Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type0 /ToUnicode 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cmap), cmap),
    }
    path = _write(tmp_path, "kr.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert doc.sections[0].elements[0].text == "가나"  # 가나


def test_encrypted_pdf_stops_with_warning(tmp_path):
    data = _build_pdf(_minimal_objects(), trailer_extra="/Encrypt 4 0 R")
    path = _write(tmp_path, "enc.pdf", data)

    doc = PDFReader().read(path)

    assert doc.sections == []
    assert any("암호화" in e for e in doc.errors)


def test_scanned_only_page_warns(tmp_path):
    image = b"\xff\xd8fakejpeg"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im1 5 0 R >> >> "
           "/Contents 6 0 R >>",
        5: b"<< /Length %d /Subtype /Image /Filter /DCTDecode >>\nstream\n%s\nendstream"
           % (len(image), image),
        6: b"<< /Length 10 >>\nstream\nq /Im1 Do Q\nendstream",
    }
    path = _write(tmp_path, "scan.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert any("스캔" in e for e in doc.errors)


def test_non_pdf_file_reports_error(tmp_path):
    path = _write(tmp_path, "junk.pdf", b"this is not a pdf at all")

    doc = PDFReader().read(path)

    assert any("%PDF-" in e for e in doc.errors)
    assert doc.sections == []


def test_dochan_routes_pdf_extension(tmp_path):
    from dochan import Dochan

    content = b"BT (Routed) Tj ET"
    path = _write(tmp_path, "route.pdf", _build_pdf(_minimal_objects(content)))

    doc = Dochan(path)

    assert doc.metadata["source_format"] == "pdf"
    assert doc.to_markdown() == "Routed"


def test_dochan_routes_pdf_magic_without_extension(tmp_path):
    from dochan import Dochan

    content = b"BT (MagicRouted) Tj ET"
    path = _write(tmp_path, "mystery.bin", _build_pdf(_minimal_objects(content)))

    doc = Dochan(path)

    assert doc.metadata["source_format"] == "pdf"
    assert doc.to_markdown() == "MagicRouted"


def test_batch_convert_includes_pdf_by_default(tmp_path):
    from dochan.batch import batch_convert

    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    content = b"BT (Batch PDF) Tj ET"
    (input_dir / "doc.pdf").write_bytes(_build_pdf(_minimal_objects(content)))

    summary = batch_convert(str(input_dir), str(output_dir),
                            output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "doc.md").read_text(encoding="utf-8") == "Batch PDF"
