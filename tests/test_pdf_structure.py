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


# ── PDF 1.5+ xref 스트림 / 객체 스트림 ──

def _build_pdf_with_xref_stream(encrypt=False):
    """xref 스트림 + ObjStm 을 쓰는 현대식 PDF 를 수동 조립.

    객체 6(폰트)은 ObjStm(객체 4) 안에 압축 저장 — type-2 엔트리 검증용.
    """
    import zlib as _zlib

    out = bytearray(b"%PDF-1.5\n")
    offsets = {}

    def _add(num, body):
        offsets[num] = len(out)
        out.extend(b"%d 0 obj\n" % num)
        out.extend(body if isinstance(body, bytes) else body.encode("latin-1"))
        out.extend(b"\nendobj\n")

    content = b"BT (Modern) Tj ET"
    _add(1, "<< /Type /Catalog /Pages 2 0 R >>")
    _add(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    _add(3, "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 6 0 R >> >> "
            "/Contents 5 0 R >>")
    _add(5, b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))

    # ObjStm: 객체 6 을 내장
    inner = b"<< /Type /Font /Subtype /Type0 /BaseFont /Batang >>"
    header = b"6 0 "
    objstm_payload = header + inner
    objstm_raw = _zlib.compress(objstm_payload)
    _add(4, b"<< /Type /ObjStm /N 1 /First %d /Length %d /Filter /FlateDecode >>"
            b"\nstream\n%s\nendstream" % (len(header), len(objstm_raw), objstm_raw))

    # XRef 스트림 (객체 7): W [1 2 1]
    xref_pos = len(out)
    max_obj = 7

    def _entry(t, f2, f3):
        return bytes([t]) + f2.to_bytes(2, "big") + bytes([f3])

    rows = b"".join([
        _entry(0, 0, 255),                 # obj 0: free
        _entry(1, offsets[1], 0),          # obj 1
        _entry(1, offsets[2], 0),          # obj 2
        _entry(1, offsets[3], 0),          # obj 3
        _entry(1, offsets[4], 0),          # obj 4 (ObjStm)
        _entry(1, offsets[5], 0),          # obj 5
        _entry(2, 4, 0),                   # obj 6: ObjStm 4 의 0번째
        _entry(1, xref_pos, 0),            # obj 7: XRef 자신
    ])
    xref_raw = _zlib.compress(rows)
    encrypt_part = " /Encrypt 5 0 R" if encrypt else ""
    _add(7, b"<< /Type /XRef /Size %d /W [1 2 1] /Root 1 0 R%s /Length %d "
            b"/Filter /FlateDecode >>\nstream\n%s\nendstream"
            % (max_obj + 1, encrypt_part.encode("ascii"), len(xref_raw), xref_raw))

    out.extend(b"startxref\n%d\n%%%%EOF\n" % xref_pos)
    return bytes(out)


def test_xref_stream_resolves_objects_without_scan_fallback():
    pdf = PDFFile(_build_pdf_with_xref_stream())

    assert not any("스캔" in w for w in pdf.warnings)
    catalog = pdf.resolve(pdf.trailer["Root"])
    assert catalog["Type"] == "Catalog"
    assert len(pdf.pages()) == 1


def test_object_stream_compressed_object_loads():
    pdf = PDFFile(_build_pdf_with_xref_stream())

    font = pdf.resolve(PDFRef(6, 0))

    assert isinstance(font, dict)
    assert font["Type"] == "Font"
    assert font["BaseFont"] == "Batang"


def test_xref_stream_trailer_encrypt_detected():
    pdf = PDFFile(_build_pdf_with_xref_stream(encrypt=True))

    assert pdf.encrypted
    assert any("암호화" in w for w in pdf.warnings)
