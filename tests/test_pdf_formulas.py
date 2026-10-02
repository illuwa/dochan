"""Tagged PDF equations use existing Equation blocks and explicit MCID ownership."""
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.reader import PDFReader
from dochan.model.equation import Equation
from dochan.output.markdown import to_markdown
from test_pdf_structure import _build_pdf, _minimal_objects


def _read(tmp_path, formula="/AF [12 0 R]", kids="0", extra=None, content=None):
    if content is None:
        content = (b"BT /F1 12 Tf 50 740 Td (Before) Tj ET "
                   b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC "
                   b"BT /F1 12 Tf 150 660 Td (After) Tj ET")
    objects = _minimal_objects(content)
    objects[1] = "<< /Type /Catalog /Pages 2 0 R /StructTreeRoot 6 0 R >>"
    objects[6] = "<< /Type /StructTreeRoot /K 7 0 R >>"
    objects[7] = "<< /Type /StructElem /S /Formula /Pg 3 0 R /K %s %s >>" % (kids, formula)
    data = b"x^{2}"
    objects[12] = "<< /F (math.tex) /EF << /F 13 0 R >> >>"
    objects[13] = b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"
    objects.update(extra or {})
    path = tmp_path / "formula.pdf"
    path.write_bytes(_build_pdf(objects))
    return PDFReader().read(str(path))


def test_formula_tex_is_original_source_at_body_position(tmp_path):
    doc = _read(tmp_path)
    before, equation, after = doc.sections[0].elements
    assert isinstance(equation, Equation)
    assert (before.text, equation.script, after.text) == ("Before", "x^{2}", "After")
    assert "GLYPH" not in to_markdown(doc)


def test_formula_rolemap_uses_declared_tex_source(tmp_path):
    doc = _read(tmp_path, extra={
        6: "<< /Type /StructTreeRoot /RoleMap << /Math /Formula >> /K 7 0 R >>",
        7: "<< /Type /StructElem /S /Math /Pg 3 0 R /K 0 /AF [12 0 R] >>"})
    assert doc.find_all("equation")[0].script == "x^{2}"


def test_formula_mathml_associated_file(tmp_path):
    data = b"<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"
    doc = _read(tmp_path, "/AF [8 0 R]", extra={
        8: "<< /Type /Filespec /AFRelationship /Supplement /F (math.xml) /EF << /F 9 0 R >> >>",
        9: b"<< /Type /EmbeddedFile /Subtype /application#2Fmathml+xml /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"})
    assert doc.find_all("equation")[0].latex == r"\frac{a}{b}"
    assert "GLYPH" not in to_markdown(doc)


def test_formula_mcid_ownership_is_not_adjacent_text(tmp_path):
    doc = _read(tmp_path, kids="99")
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("Formula" in error for error in doc.errors)


def test_formula_unsupported_mathml_preserves_glyphs(tmp_path):
    data = b"<math><unknown>x</unknown></math>"
    doc = _read(tmp_path, "/AF [8 0 R]", extra={
        8: "<< /F (math.xml) /EF << /F 9 0 R >> >>",
        9: b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("Formula" in error for error in doc.errors)


def test_marked_content_nested_scopes_preserve_mcid_and_artifact():
    frags = ContentTextExtractor().extract_fragments(
        b"/Formula <</MCID 4>> BDC /Span BMC BT (A) Tj ET EMC "
        b"/Artifact BMC BT (B) Tj ET EMC EMC BT (C) Tj ET")
    assert [frag.mcids for frag in frags] == [(4,), (4,), ()]
    assert [frag.artifact for frag in frags] == [False, True, False]


def test_formula_structure_cycle_does_not_drop_body(tmp_path):
    doc = _read(tmp_path, extra={6: "<< /Type /StructTreeRoot /K [6 0 R 7 0 R] >>"})
    assert len(doc.find_all("equation")) == 1
    assert "Before" in to_markdown(doc)


def test_formula_named_properties_and_nested_span(tmp_path):
    doc = _read(tmp_path, content=(
        b"BT /F1 12 Tf 50 740 Td (Before) Tj ET "
        b"/Formula /MC0 BDC /Span BMC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC EMC "
        b"BT /F1 12 Tf 150 660 Td (After) Tj ET"), extra={
            3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> /Properties << /MC0 8 0 R >> >> >>",
            8: "<< /MCID 0 >>"})
    assert len(doc.find_all("equation")) == 1
    assert "GLYPH" not in to_markdown(doc)


def test_formula_duplicate_mcid_owners_keep_original(tmp_path):
    doc = _read(tmp_path, extra={
        6: "<< /Type /StructTreeRoot /K [7 0 R 8 0 R] >>",
        8: "<< /Type /StructElem /S /Formula /Pg 3 0 R /K 0 /Alt (other) >>"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_form_xobject_mcid_is_separate_namespace(tmp_path):
    doc = _read(tmp_path, kids="<< /Type /MCR /MCID 0 /Stm 5 0 R >>")
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_struct_tree_budget_retains_body(tmp_path, monkeypatch):
    from dochan.pdf import formulas
    monkeypatch.setattr(formulas, "MAX_NODES", 0)
    doc = _read(tmp_path)
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("한도" in warning for warning in doc.errors)


def test_formula_associated_data_budget_retains_body(tmp_path, monkeypatch):
    from dochan.pdf import formulas
    monkeypatch.setattr(formulas, "MAX_SOURCE_BYTES", 4)
    doc = _read(tmp_path)
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_namespace_mathml_struct_elements_use_token_mcids(tmp_path):
    doc = _read(tmp_path, formula="", kids="8 0 R", extra={
        8: "<< /S /math /NS 9 0 R /K 10 0 R >>",
        9: "<< /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >>",
        10: "<< /S /mi /NS 9 0 R /K << /Type /MCR /Pg 3 0 R /MCID 0 >> >>"})
    assert doc.find_all("equation")[0].latex == r"\mathrm{GLYPH}"
    assert sum("GLYPH" in p.text for p in doc.find_all("paragraph")) == 0


def test_formula_empty_mathml_without_mcid_does_not_invent_location(tmp_path):
    data = b"<math><mrow intent=\"_newline\"/></math>"
    doc = _read(tmp_path, formula="/AF [8 0 R]", kids="null", extra={
        8: "<< /F (newline.xml) /EF << /F 9 0 R >> >>",
        9: b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_struct_mathml_obeys_document_source_budget(tmp_path, monkeypatch):
    from dochan.pdf import formulas
    monkeypatch.setattr(formulas, "MAX_TOTAL_SOURCE", 1)
    doc = _read(tmp_path, formula="", kids="8 0 R", extra={
        8: "<< /S /math /NS 9 0 R /K 10 0 R >>",
        9: "<< /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >>",
        10: "<< /S /mi /NS 9 0 R /K << /Type /MCR /Pg 3 0 R /MCID 0 >> >>"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("한도" in warning for warning in doc.errors)


def test_formula_reused_content_mcid_does_not_consume_unrelated_prose(tmp_path):
    doc = _read(tmp_path, content=(
        b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC "
        b"/P <</MCID 0>> BDC BT /F1 12 Tf 50 680 Td (ordinary prose) Tj ET EMC"))
    assert not doc.find_all("equation")
    assert "ordinary prose" in to_markdown(doc)
    assert "GLYPH" in to_markdown(doc)


def test_formula_foreign_mathml_child_preserves_whole_equation(tmp_path):
    doc = _read(tmp_path, formula="", kids="8 0 R", extra={
        8: "<< /S /math /NS 9 0 R /K [10 0 R 11 0 R] >>",
        9: "<< /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >>",
        10: "<< /S /mi /NS 9 0 R /ActualText (x) >>",
        11: "<< /S /Span /K << /Type /MCR /Pg 3 0 R /MCID 0 >> >>"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_struct_mathml_retains_attributes_for_conservative_conversion(tmp_path):
    doc = _read(tmp_path, formula="", kids="8 0 R", extra={
        8: "<< /S /math /NS 9 0 R /K 10 0 R >>",
        9: "<< /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >>",
        10: "<< /S /mfrac /NS 9 0 R /A << /O /NSO /bevelled (true) >> /K [11 0 R 12 0 R] >>",
        11: "<< /S /mi /NS 9 0 R /K << /Type /MCR /Pg 3 0 R /MCID 0 >> >>",
        12: "<< /S /mi /NS 9 0 R /ActualText (y) >>"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_struct_mathml_supported_attributes_still_convert(tmp_path):
    doc = _read(tmp_path, formula="", kids="8 0 R", extra={
        8: "<< /S /math /NS 9 0 R /K 10 0 R >>",
        9: "<< /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >>",
        10: "<< /S /mi /NS 9 0 R /A << /O /NSO /mathvariant (normal) >> /K << /Type /MCR /Pg 3 0 R /MCID 0 >> >>"})
    assert doc.find_all("equation")[0].latex == r"\mathrm{GLYPH}"


def test_formula_plain_text_attachment_is_not_tex_source(tmp_path):
    data = b"unrelated notes"
    doc = _read(tmp_path, "/AF [8 0 R]", extra={
        8: "<< /F (notes.txt) /EF << /F 9 0 R >> >>",
        9: b"<< /Subtype /text#2Fplain /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_formula_replacement_preserves_heading_size_baseline(tmp_path):
    doc = _read(tmp_path, content=(
        b"BT /F1 18 Tf 50 720 Td (Heading) Tj ET "
        b"/Formula <</MCID 0>> BDC BT /F1 10 Tf 50 680 Td (GLYPH) Tj ET EMC "
        b"BT /F1 10 Tf 50 650 Td (Body) Tj ET"))
    assert doc.find_all("paragraph")[0].heading_level == 1
