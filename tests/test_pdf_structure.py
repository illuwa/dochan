from dochan.pdf.objects import PDFRef, PDFStream
from dochan.pdf.structure import PDFFile


def _build_pdf(objects, trailer_extra=""):
    """{번호: 본문 str|bytes} 로 고전 xref PDF 를 조립한다. Root 는 1번 가정."""
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        body = objects[num]
        if isinstance(body, str):
            body = body.encode("latin-1")
        out += b"%d 0 obj\n" % num
        out += body
        out += b"\nendobj\n"
    xref_pos = len(out)
    max_num = max(objects)
    out += b"xref\n0 %d\n" % (max_num + 1)
    out += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        if num in offsets:
            out += ("%010d 00000 n \n" % offsets[num]).encode("ascii")
        else:
            out += b"0000000000 65535 f \n"
    trailer = "<< /Size %d /Root 1 0 R %s >>" % (max_num + 1, trailer_extra)
    out += b"trailer\n" + trailer.encode("latin-1") + b"\n"
    out += b"startxref\n%d\n%%%%EOF\n" % xref_pos
    return bytes(out)


def _minimal_objects(content=b"BT (x) Tj ET"):
    return {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    }


def test_parses_xref_and_returns_objects():
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    catalog = pdf.resolve(pdf.trailer["Root"])
    assert catalog["Type"] == "Catalog"
    stream = pdf.resolve(PDFRef(5, 0))
    assert isinstance(stream, PDFStream)
    assert stream.raw == b"BT (x) Tj ET"


def test_pages_traversal_with_inherited_resources():
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 "
           "/Resources << /Font << /F1 6 0 R >> >> >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R "
           "/Resources << /Font << /F2 6 0 R >> >> >>",
        5: b"<< /Length 4 >>\nstream\nBT E\nendstream",
        6: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    pdf = PDFFile(_build_pdf(objects))
    pages = pdf.pages()
    assert len(pages) == 2
    assert "F1" in pages[0][1]["Font"]
    assert "F2" in pages[1][1]["Font"]


def test_broken_startxref_falls_back_to_scan():
    data = _build_pdf(_minimal_objects())
    data = data.replace(b"startxref", b"startxrfX")
    pdf = PDFFile(data)
    assert any("스캔" in w for w in pdf.warnings)
    assert len(pdf.pages()) == 1


def test_xref_stream_detected_and_scan_fallback():
    data = _build_pdf(_minimal_objects())
    # startxref 가 xref 테이블이 아닌 객체(1번)를 가리키게 조작
    xref_pos = data.rindex(b"startxref")
    obj1_pos = data.index(b"1 0 obj")
    tail = b"startxref\n%d\n%%%%EOF\n" % obj1_pos
    pdf = PDFFile(data[:xref_pos] + tail)
    assert any("xref 스트림" in w for w in pdf.warnings)
    assert len(pdf.pages()) == 1


def test_encrypted_trailer_sets_flag_and_warning():
    pdf = PDFFile(_build_pdf(_minimal_objects(), trailer_extra="/Encrypt 4 0 R"))
    assert pdf.encrypted
    assert any("암호화" in w for w in pdf.warnings)


def test_missing_root_reports_warning():
    objects = {1: "<< /Type /NotACatalog >>"}
    data = _build_pdf(objects)
    data = data.replace(b"/Root 1 0 R", b"")
    pdf = PDFFile(data)
    assert pdf.pages() == []
    assert any("Root" in w or "카탈로그" in w for w in pdf.warnings)


def test_circular_page_tree_terminates():
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [2 0 R] /Count 1 >>",
    }
    pdf = PDFFile(_build_pdf(objects))
    assert pdf.pages() == []
