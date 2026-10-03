"""Regressions found by the independent Form XObject reviews."""
from types import SimpleNamespace

from dochan.pdf.annotations import LinkRegion, attach_links
from dochan.pdf.content import ContentTextExtractor, Fragment, _clip_form_fragments
from dochan.pdf.reader import PDFReader
from dochan.pdf.running import edge_block
from dochan.pdf.structure import PDFFile

from test_pdf_forms import _read, _stream, _texts
from test_pdf_structure import _build_pdf, _minimal_objects
from test_pdf_content import _vertical_font


def _extract(tmp_path, page_content, forms, track_positions=False):
    objects = _minimal_objects(page_content)
    objects[3] = ("<< /Type /Page /Parent 2 0 R /Resources << "
                  "/Font << /F1 4 0 R >> /XObject << /F 6 0 R >> >> "
                  "/Contents 5 0 R >>")
    objects.update(forms)
    path = tmp_path / "review.pdf"
    path.write_bytes(_build_pdf(objects))
    pdf = PDFFile(path.read_bytes())
    page, resources = pdf.pages()[0]
    reader = PDFReader()
    extractor = ContentTextExtractor.from_fonts(
        reader._font_infos(pdf, resources, {}), track_char_positions=track_positions)
    reader._configure_form_extractor(extractor, pdf, resources, {})
    content = pdf.decode_stream_bytes(pdf.resolve(page["Contents"]))
    return pdf, extractor.extract_page(content)


def test_form_operator_scan_is_shared_across_callers(tmp_path, monkeypatch):
    calls = []
    original = ContentTextExtractor._count_operators.__func__

    def counted(cls, data):
        if len(data) > 1000000:
            calls.append(1)
        return original(cls, data)

    monkeypatch.setattr(ContentTextExtractor, "_count_operators", classmethod(counted))
    large = b" " * (1024 * 1024) + b"0 0 m"
    wrappers = {}
    for number in range(7, 1007):
        wrappers[number] = _stream(
            b"/X Do", "/Subtype /Form /Resources << /Font << /F1 4 0 R >> "
            "/XObject << /X 6 0 R >> /Properties << /P %d >> >>" % number)
    page_resources = " ".join("/W%d %d 0 R" % (n, n) for n in range(7, 1007))
    _read(tmp_path, b" ".join(b"/W%d Do" % n for n in range(7, 1007)),
          {6: _stream(large, "/Subtype /Form"), **wrappers}, page_resources)
    assert len(calls) == 1


def test_repeated_form_font_resources_are_built_once(tmp_path, monkeypatch):
    original = PDFReader._font_infos
    calls = []

    def counted(self, pdf, resources, font_cache):
        calls.append(1)
        return original(self, pdf, resources, font_cache)

    monkeypatch.setattr(PDFReader, "_font_infos", counted)
    doc = _read(tmp_path, b"/F Do " * 50, {
        6: _stream(b"BT /F1 10 Tf 40 500 Td (X) Tj ET", "/Subtype /Form")})
    assert _texts(doc)
    assert len(calls) == 2  # one page font map and one cached Form font map


def test_form_surviving_fragment_orders_are_unique(tmp_path):
    huge = b"1" + b"0" * 160
    form = (b"BT /F1 10 Tf " + huge + b" 0 0 " + huge +
            b" 0 0 Tm (BAD) Tj 1 0 0 1 40 500 Tm (GOOD) Tj ET")
    _pdf, result = _extract(tmp_path, b"/F Do BT /F1 10 Tf 40 400 Td (BODY) Tj ET",
                            {6: _stream(form, "/Subtype /Form")})
    assert [frag.text for frag in result.fragments] == ["GOOD", "BODY"]
    assert [frag.order for frag in result.fragments] == [0, 1]


def test_form_geometry_failure_keeps_page_text(tmp_path):
    huge = b"1" + b"0" * 300
    form = b"BT /F1 10 Tf " + huge + b" 0 0 " + huge + b" 0 0 Tm (STAMP) Tj ET"
    doc = _read(tmp_path, b"BT /F1 10 Tf 40 600 Td (BEFORE) Tj ET "
                b"/F Do BT /F1 10 Tf 40 400 Td (AFTER) Tj ET",
                {6: _stream(form, "/Subtype /Form")})
    assert _texts(doc) == ["BEFORE", "AFTER"]
    assert any("비유한 텍스트 좌표" in error for error in doc.errors)


def test_form_exception_keeps_page_text(tmp_path, monkeypatch):
    original = ContentTextExtractor._show

    def failing(self, raw, *args):
        if raw == b"STAMP":
            raise OverflowError("malformed Form geometry")
        return original(self, raw, *args)

    monkeypatch.setattr(ContentTextExtractor, "_show", failing)
    doc = _read(tmp_path, b"BT /F1 10 Tf 40 600 Td (BEFORE) Tj ET "
                b"/F Do BT /F1 10 Tf 40 400 Td (AFTER) Tj ET",
                {6: _stream(b"BT /F1 10 Tf 40 500 Td (STAMP) Tj ET", "/Subtype /Form")})
    assert _texts(doc) == ["BEFORE", "AFTER"]
    assert any("Form 해석 실패" in error for error in doc.errors)


def test_mixed_readable_running_header_survives_one_bad_code():
    good = SimpleNamespace(text="ACME Annual Report \x81 2026", direction="ltr",
                           y=730, size=10)
    bad = SimpleNamespace(text="\x81\x82\x83AB", direction="ltr", y=720, size=10)
    assert edge_block([good, bad], (0, 800), "header") == [good]


def test_form_inherits_text_state_at_do(tmp_path):
    _pdf, result = _extract(tmp_path,
                            b"BT /F1 10 Tf 3 Tc ET /F Do",
                            {6: _stream(b"BT 40 500 Td (AB) Tj ET", "/Subtype /Form")})
    assert [frag.text for frag in result.fragments] == ["AB"]
    assert result.fragments[0].size == 10
    assert result.fragments[0].width > 10


def test_form_inherits_page_marked_content_and_artifact(tmp_path):
    _pdf, result = _extract(tmp_path,
                            b"/P <</MCID 7>> BDC /Artifact BMC /F Do EMC EMC",
                            {6: _stream(b"/P <</MCID 3>> BDC "
                                        b"BT /F1 10 Tf 40 500 Td (A) Tj ET EMC",
                                        "/Subtype /Form")})
    assert [(f.mcids, f.artifact) for f in result.fragments] == [((7,), True)]
    _pdf, separate = _extract(tmp_path, b"/P <</MCID 7>> BDC /F Do EMC",
                              {6: _stream(b"BT /F1 10 Tf 40 500 Td (A) Tj ET",
                                          "/Subtype /Form /StructParents 3")})
    assert separate.fragments[0].mcids == ()


def test_form_glyphs_outside_transformed_bbox_are_clipped(tmp_path):
    form = (b"BT /F1 10 Tf 5 5 Td (IN) Tj "
            b"1 0 0 1 100 100 Tm (OUT) Tj ET")
    doc = _read(tmp_path, b"/F Do", {
        6: _stream(form, "/Subtype /Form /BBox [0 0 20 20] "
                   "/Matrix [1 0 0 1 40 600]")})
    assert _texts(doc) == ["IN"]


def test_form_bbox_clips_partial_run_after_rotation(tmp_path):
    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"BT /F1 10 Tf 0 0 Td (AB) Tj ET",
                   "/Subtype /Form /BBox [0 0 6 20] /Matrix [0 1 -1 0 100 100]")})
    assert _texts(doc) == ["A"]


def test_parent_form_bbox_clips_nested_form_glyphs(tmp_path):
    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"/G Do", "/Subtype /Form /BBox [0 0 20 20] "
                   "/Resources << /Font << /F1 4 0 R >> /XObject << /G 7 0 R >> >>"),
        7: _stream(b"BT /F1 10 Tf 5 5 Td (IN) Tj "
                   b"1 0 0 1 100 100 Tm (OUT) Tj ET", "/Subtype /Form"),
    })
    assert _texts(doc) == ["IN"]


def test_rejected_large_shared_form_keeps_every_page_body(tmp_path, monkeypatch):
    from dochan.pdf import reader, structure

    monkeypatch.setattr(reader, "MAX_FORM_CACHE_BYTES", 512 * 1024)
    monkeypatch.setattr(structure, "MAX_TOTAL_DECODED", 2 * 1024 * 1024 + 100 * 1024)
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R 6 0 R 7 0 R] /Count 5 >>",
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        21: _stream(b" " * (1024 * 1024) + b"BT /F1 10 Tf (HIDDEN) Tj ET",
                    "/Subtype /Form"),
    }
    for index in range(5):
        objects[3 + index] = (
            "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 20 0 R >> "
            "/XObject << /F 21 0 R >> >> /Contents %d 0 R >>" % (10 + index))
        body = b"/F Do BT /F1 10 Tf 40 500 Td (PAGE%d) Tj ET" % (index + 1)
        objects[10 + index] = _stream(body)
    path = tmp_path / "shared.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert [[e.text for e in section.elements if hasattr(e, "text")]
            for section in doc.sections] == [["PAGE%d" % (index + 1)] for index in range(5)]
    assert not any("문서 스트림 해제 총량" in error for error in doc.errors)


def test_vertical_form_run_overlapping_bbox_is_kept():
    font = _vertical_font()
    extractor = ContentTextExtractor.from_fonts({"F1": font})
    fragments = extractor.extract_fragments(
        b"BT /F1 20 Tf 50 105 Td <00010001000100010001> Tj ET")
    assert len(fragments) == 1
    assert fragments[0].char_offsets == ()
    assert [frag.text for frag in _clip_form_fragments(
        fragments, (0, 0, 100, 300), (1, 0, 0, 1, 0, 0))] == ["AAAAA"]


def test_shared_inline_form_fonts_are_built_once_across_callers(tmp_path, monkeypatch):
    original = PDFReader._font_infos
    calls = []

    def counted(self, pdf, resources, font_cache):
        calls.append(resources)
        return original(self, pdf, resources, font_cache)

    monkeypatch.setattr(PDFReader, "_font_infos", counted)
    wrappers = {
        number: _stream(b"/X Do", "/Subtype /Form /Resources << "
                        "/XObject << /X 6 0 R >> >>")
        for number in range(7, 17)
    }
    page_resources = " ".join("/W%d %d 0 R" % (n, n) for n in wrappers)
    doc = _read(tmp_path, b" ".join(b"/W%d Do" % n for n in wrappers), {
        6: _stream(b"BT /F1 10 Tf 40 500 Td (X) Tj ET",
                   "/Subtype /Form /Resources << /Font << /F1 4 0 R >> >>"),
        **wrappers}, page_resources)
    assert _texts(doc)
    assert len(calls) == 2


def test_indirect_structparents_separates_form_mcid_from_page(tmp_path):
    _pdf, result = _extract(tmp_path, b"/P <</MCID 7>> BDC /F Do EMC", {
        6: _stream(b"BT /F1 10 Tf 40 500 Td (A) Tj ET",
                   "/Subtype /Form /StructParents 7 0 R"),
        7: "3",
    })
    assert [frag.mcids for frag in result.fragments] == [()]


def test_rejected_form_is_not_decoded_again_for_other_callers(tmp_path, monkeypatch):
    from dochan.pdf import reader, content

    monkeypatch.setattr(reader, "MAX_FORM_CACHE_BYTES", 100)
    monkeypatch.setattr(content, "MAX_FORM_CACHE_BYTES", 100)
    original = PDFFile.decode_stream_bytes
    calls = []

    def counted(pdf, stream):
        if str(stream.dictionary.get("Subtype")) == "Form" and len(stream.raw) > 100:
            calls.append(1)
        return original(pdf, stream)

    monkeypatch.setattr(PDFFile, "decode_stream_bytes", counted)
    wrappers = {7: _stream(b"/X Do", "/Subtype /Form /Resources << "
                           "/XObject << /X 6 0 R >> >>"),
                8: _stream(b"/X Do", "/Subtype /Form /Resources << "
                           "/XObject << /X 6 0 R >> /Properties << /P 1 >> >>")}
    _read(tmp_path, b"/A Do /B Do", {
        6: _stream(b" " * 101 + b"BT (X) Tj ET", "/Subtype /Form"), **wrappers},
        page_resources="/A 7 0 R /B 8 0 R")
    assert len(calls) == 1


def test_form_char_position_budget_is_shared(tmp_path):
    form = b"BT /F1 10 Tf 0 500 Td (" + b"A" * 10000 + b") Tj ET"
    _pdf, result = _extract(tmp_path, b"/F Do " * 21,
                            {6: _stream(form, "/Subtype /Form")}, track_positions=True)
    assert sum(len(f.char_offsets) - 1 for f in result.fragments if f.char_offsets) <= 200000


def test_link_boundary_inside_glyph_is_ambiguous():
    fragment = Fragment(x=0, y=0, width=10, size=10, text="A", space_width=5,
                        char_offsets=(0, 10))
    region = LinkRegion("https://example.org", [
        [(0.00005, 0), (10, 0), (10, 10), (0.00005, 10)]])
    attach_links([fragment], [region], [])
    assert fragment.link_spans == []


def test_link_boundary_within_existing_rounding_allowance():
    fragment = Fragment(x=0, y=0, width=10, size=10, text="A", space_width=5,
                        char_offsets=(0, 10))
    region = LinkRegion("https://example.org", [
        [(0.000006, 0), (10, 0), (10, 10), (0.000006, 10)]])
    attach_links([fragment], [region], [])
    assert fragment.link_spans == [(0, 1, "https://example.org")]


def test_short_link_edge_does_not_magnify_rounding_allowance():
    fragment = Fragment(x=0.05, y=0.04505, width=10, size=0.01, text="A", space_width=5,
                        char_offsets=(0, 10))
    region = LinkRegion("https://example.org", [
        [(0, 0), (11, 0), (11, 0.1), (0.1, 0.1)]])
    attach_links([fragment], [region], [])
    assert fragment.link_spans == []


def _per_page_form_pdf(tmp_path, pages, form_padding, first_drawing=0):
    """Each page draws its own Form; optionally page 1 also draws a large text-free Form."""
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [%s] /Count %d >>" % (
            " ".join("%d 0 R" % (100 + i) for i in range(pages)), pages),
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    if first_drawing:
        objects[21] = _stream(b"0 0 m 1 1 l S " * (first_drawing // 14), "/Subtype /Form")
    for i in range(pages):
        drawing = " /D 21 0 R" if first_drawing and i == 0 else ""
        objects[100 + i] = (
            "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 20 0 R >> "
            "/XObject << /F %d 0 R%s >> >> /Contents %d 0 R >>" % (300 + i, drawing, 200 + i))
        objects[200 + i] = _stream(b"/D Do /F Do" if drawing else b"/F Do")
        objects[300 + i] = _stream(b" " * form_padding + b"BT /F1 10 Tf 40 500 Td (P%d) Tj ET" % (i + 1),
                                   "/Subtype /Form")
    path = tmp_path / "per-page.pdf"
    path.write_bytes(_build_pdf(objects))
    return PDFReader().read(str(path))


def test_distinct_forms_across_many_pages_all_keep_text(tmp_path, monkeypatch):
    # 3차 감수 P2: Form 바이트 상한은 페이지 단위다. 문서 전체 합계로 걸면 뒤 페이지 Form 글자가 빠진다.
    from dochan.pdf import reader
    monkeypatch.setattr(reader, "MAX_FORM_CACHE_BYTES", 64 * 1024)
    doc = _per_page_form_pdf(tmp_path, 12, 16 * 1024)
    assert [[e.text for e in section.elements if hasattr(e, "text")]
            for section in doc.sections] == [["P%d" % (i + 1)] for i in range(12)]


def test_large_drawing_form_on_first_page_does_not_starve_later_pages(tmp_path, monkeypatch):
    from dochan.pdf import reader
    monkeypatch.setattr(reader, "MAX_FORM_CACHE_BYTES", 64 * 1024)
    doc = _per_page_form_pdf(tmp_path, 6, 8 * 1024, first_drawing=62 * 1024)
    assert [[e.text for e in section.elements if hasattr(e, "text")]
            for section in doc.sections][1:] == [["P%d" % (i + 1)] for i in range(1, 6)]
