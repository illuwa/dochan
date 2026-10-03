"""Form XObject text is drawn in page order with bounded expansion."""
import zlib

from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf, _minimal_objects


def _stream(body, extra="", compress=False):
    encoded = zlib.compress(body) if compress else body
    filter_name = " /Filter /FlateDecode" if compress else ""
    return ("<< /Length %d %s%s >>\nstream\n" %
            (len(encoded), extra, filter_name)).encode("ascii") + encoded + b"\nendstream"


def _read(tmp_path, page_content, forms, page_resources="/F 6 0 R", tag=""):
    objects = _minimal_objects(page_content)
    objects[3] = ("<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> "
                  "/XObject << %s >> >> /Contents 5 0 R %s >>" % (page_resources, tag))
    objects.update(forms)
    path = tmp_path / "form.pdf"
    path.write_bytes(_build_pdf(objects))
    return PDFReader().read(str(path))


def _texts(doc):
    return [e.text for e in doc.sections[0].elements if hasattr(e, "text")]


def test_form_text_uses_own_font_resources_and_matrix(tmp_path):
    form = b"BT /F2 10 Tf 0 0 Td (FORM) Tj ET"
    doc = _read(tmp_path, b"BT /F1 10 Tf 40 700 Td (BEFORE) Tj ET /F Do "
                b"BT /F1 10 Tf 40 600 Td (AFTER) Tj ET", {
                    6: _stream(form, "/Subtype /Form /Matrix [1 0 0 1 40 650] "
                               "/Resources << /Font << /F2 7 0 R >> >>"),
                    7: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"})
    assert _texts(doc) == ["BEFORE", "FORM", "AFTER"]
    assert doc.sections[0].elements[1].runs[0].bold
    assert not doc.sections[0].elements[2].runs[0].bold


def test_nested_form_without_resources_inherits_caller(tmp_path):
    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"/G Do", "/Subtype /Form /Resources << /Font << /F1 4 0 R >> "
                   "/XObject << /G 7 0 R >> >>"),
        7: _stream(b"BT /F1 10 Tf 40 500 Td (NESTED) Tj ET", "/Subtype /Form"),
    })
    assert _texts(doc) == ["NESTED"]


def test_form_mcid_does_not_enter_page_space(tmp_path):
    body = b"/P <</MCID 0>> BDC BT /F1 10 Tf 40 500 Td (FORM) Tj ET EMC"
    doc = _read(tmp_path, b"/F Do", {6: _stream(body, "/Subtype /Form")})
    assert _texts(doc) == ["FORM"]
    # The page-level structure machinery must not claim the Form's MCID.
    assert not any("MCID" in error for error in doc.errors)


def test_form_stm_mcid_is_not_claimed_as_page_formula(tmp_path):
    body = b"/Formula <</MCID 0>> BDC BT /F1 10 Tf 40 500 Td (FORM) Tj ET EMC"
    doc = _read(tmp_path, b"/F Do", {
        1: "<< /Type /Catalog /Pages 2 0 R /StructTreeRoot 7 0 R >>",
        6: _stream(body, "/Subtype /Form"),
        7: "<< /Type /StructTreeRoot /K 8 0 R >>",
        8: "<< /Type /StructElem /S /Formula /Pg 3 0 R "
           "/K << /Type /MCR /Pg 3 0 R /Stm 6 0 R /MCID 0 >> >>",
    })
    assert _texts(doc) == ["FORM"]
    assert doc.find_all("equation") == []


def test_self_and_mutual_form_cycles_warn_once(tmp_path):
    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"BT /F1 10 Tf 40 500 Td (SAFE) Tj ET /G Do",
                   "/Subtype /Form /Resources << /Font << /F1 4 0 R >> "
                   "/XObject << /G 7 0 R >> >>"),
        7: _stream(b"/F Do", "/Subtype /Form /Resources << /XObject << /F 6 0 R >> >>"),
    })
    assert _texts(doc) == ["SAFE"]
    assert sum("Form" in error and "순환" in error for error in doc.errors) == 1

    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"/F Do", "/Subtype /Form /Resources << /XObject << /F 6 0 R >> >>")})
    assert sum("Form" in error and "순환" in error for error in doc.errors) == 1


def test_repeated_compressed_form_has_page_budget(tmp_path):
    doc = _read(tmp_path, b"/F Do " * 10000, {
        6: _stream(b"BT /F1 10 Tf 40 500 Td (X) Tj ET", "/Subtype /Form",
                   compress=True),
    })
    assert len("".join(_texts(doc))) < 10000
    assert sum("Form" in error and "한도" in error for error in doc.errors) == 1


def test_form_depth_limit_and_singular_matrix(tmp_path):
    forms = {}
    for num in range(6, 1006):
        body = (b"/F Do" if num == 1005 else b"/F Do")
        forms[num] = _stream(body, "/Subtype /Form /Resources << /XObject << /F %d 0 R >> >>" %
                             (num + 1))
    doc = _read(tmp_path, b"/F Do", forms)
    assert sum("Form" in error and "깊이 한도" in error for error in doc.errors) == 1

    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"BT (HIDDEN) Tj ET", "/Subtype /Form /Matrix [0 0 0 0 0 0]")})
    assert _texts(doc) == []
    assert any("특이 행렬" in error for error in doc.errors)

    huge = "9" * 300
    doc = _read(tmp_path, b"/F Do", {
        6: _stream(b"BT /F1 10 Tf 0 0 Td (HIDDEN) Tj ET",
                   "/Subtype /Form /Matrix [%s 0 0 %s 0 0]" % (huge, huge))})
    assert _texts(doc) == []
    assert any("좌표" in error or "행렬" in error for error in doc.errors)


def test_form_cache_and_expansion_bytes_are_bounded(tmp_path, monkeypatch):
    from dochan.pdf import content

    monkeypatch.setattr(content, "MAX_FORM_EXPANDED_BYTES", 50)
    body = b"BT /F1 10 Tf 40 500 Td (ONCE) Tj ET"
    doc = _read(tmp_path, b"/F Do /F Do", {6: _stream(body, "/Subtype /Form")})
    assert "".join(_texts(doc)).count("ONCE") == 1
    assert sum("Form 확장 한도" in error for error in doc.errors) == 1

    monkeypatch.setattr(content, "MAX_FORM_CACHE_BYTES", 10)
    from dochan.pdf import reader
    monkeypatch.setattr(reader, "MAX_FORM_CACHE_BYTES", 10)
    doc = _read(tmp_path, b"/F Do", {6: _stream(body, "/Subtype /Form")})
    assert _texts(doc) == []
    assert sum("Form 디코드 캐시 한도" in error for error in doc.errors) == 1


def test_repeated_form_decodes_once(tmp_path, monkeypatch):
    from dochan.pdf.structure import PDFFile

    original = PDFFile.decode_form_bytes
    calls = []
    def counted(pdf, stream):
        if str(stream.dictionary.get("Subtype")) == "Form":
            calls.append(1)
        return original(pdf, stream)
    monkeypatch.setattr(PDFFile, "decode_form_bytes", counted)
    doc = _read(tmp_path, b"/F Do " * 50, {
        6: _stream(b"BT /F1 10 Tf 40 500 Td (X) Tj ET", "/Subtype /Form")})
    assert len(calls) == 1
    assert _texts(doc)


def test_form_graphics_and_font_state_do_not_leak(tmp_path):
    doc = _read(tmp_path,
                b"q 1 0 0 1 20 0 cm /F Do Q BT /F1 10 Tf 40 400 Td (PAGE) Tj ET",
                {6: _stream(b"q 1 0 0 1 10 0 cm BT /F1 10 Tf 40 500 Td (FORM) Tj ET",
                            "/Subtype /Form")})
    assert _texts(doc) == ["FORM", "PAGE"]


def test_form_glyph_edge_rounding_does_not_discard_link():
    from dochan.pdf.annotations import LinkRegion, attach_links
    from dochan.pdf.content import Fragment

    fragment = Fragment(x=0, y=0, width=10, size=10, text="hi", space_width=5,
                        char_offsets=(0, 5, 10))
    region = LinkRegion("https://example.org", [
        [(-0.000046, 0), (10, 0), (10, 10), (-0.000046, 10)]])
    attach_links([fragment], [region], [])
    assert fragment.link_spans == [(0, 2, "https://example.org")]


def test_graphics_only_form_does_not_create_empty_table(tmp_path):
    grid = b" ".join(b"%d 0 m %d 80 l S" % (x, x) for x in (10, 30, 50, 70))
    grid += b" " + b" ".join(b"10 %d m 70 %d l S" % (y, y) for y in (0, 20, 40, 60, 80))
    doc = _read(tmp_path, b"/F Do", {6: _stream(grid, "/Subtype /Form")})
    assert doc.find_all("table") == []


def test_form_text_does_not_turn_unrelated_form_grid_into_table(tmp_path):
    grid = b" ".join(b"%d 0 m %d 80 l S" % (x, x) for x in (10, 30, 50, 70))
    grid += b" " + b" ".join(b"10 %d m 70 %d l S" % (y, y) for y in (0, 20, 40, 60, 80))
    body = grid + b" BT /F1 10 Tf 200 500 Td (BODY) Tj ET"
    doc = _read(tmp_path, b"/F Do", {6: _stream(body, "/Subtype /Form")})
    assert _texts(doc) == ["BODY"]
    assert doc.find_all("table") == []


def test_repeated_form_header_uses_existing_running_detection(tmp_path):
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 "
           "/MediaBox [0 0 600 800] /Resources << /Font << /F1 20 0 R >> "
           "/XObject << /F 21 0 R >> >> >>",
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        21: _stream(b"BT /F1 10 Tf 30 730 Td (RUNNING) Tj ET", "/Subtype /Form"),
    }
    for index in range(3):
        content = (b"/F Do BT /F1 10 Tf 30 400 Td (BODY%d) Tj ET" % (index + 1))
        objects[3 + index] = "<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (10 + index)
        objects[10 + index] = _stream(content)
    path = tmp_path / "running-forms.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert [(item.type, item.text) for item in doc.find_all("header_footer")] == [
        ("header", "RUNNING")]
    assert all("BODY%d" % index in " ".join(e.text for e in doc.sections[index - 1].elements
                                                  if hasattr(e, "text")) for index in (1, 2, 3))


def test_repeated_control_glyphs_are_not_promoted_to_header(tmp_path):
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 "
           "/MediaBox [0 0 600 800] /Resources << /Font << /F1 20 0 R >> "
           "/XObject << /F 21 0 R >> >> >>",
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        21: _stream(b"BT /F1 10 Tf 30 730 Td (\x02\x03\x04\x05) Tj ET", "/Subtype /Form"),
    }
    for index in range(3):
        content = b"/F Do BT /F1 10 Tf 30 400 Td (BODY) Tj ET"
        objects[3 + index] = "<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (10 + index)
        objects[10 + index] = _stream(content)
    path = tmp_path / "control-forms.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert doc.find_all("header_footer") == []


def test_replacement_glyph_is_not_running_header():
    from types import SimpleNamespace
    from dochan.pdf.running import edge_block

    line = SimpleNamespace(text="\ufffd", direction="ltr", y=730, size=10)
    assert edge_block([line], (0, 800), "header") == []
