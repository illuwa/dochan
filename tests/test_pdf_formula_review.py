"""리뷰의 본문 손실·주입·태그 순회 회귀를 합성 바이트로 재현한다."""
from dochan.output.markdown import to_markdown
from dochan.output.json_out import to_dict
from test_pdf_formulas import _read


DISPLAY = (b"BT /F1 12 Tf 50 740 Td (Before) Tj ET "
           b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC "
           b"BT /F1 12 Tf 50 660 Td (After) Tj ET")


def semantic(tmp_path, data=b"<math><msup><mi>x</mi><mn>2</mn></msup></math>",
             content=DISPLAY, extra=None, suffix="xml", kids="0"):
    objects = {8: "<< /F (math.%s) /EF << /F 9 0 R >> >>" % suffix,
               9: b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"}
    objects.update(extra or {})
    return _read(tmp_path, "/AF [8 0 R]", content=content, extra=objects, kids=kids)


def test_inline_formula_preserves_sentence_and_paragraph_boundaries(tmp_path):
    content = (b"BT /F1 12 Tf 50 700 Td (Before) Tj ET "
               b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC "
               b"BT /F1 12 Tf 150 700 Td (After.) Tj ET")
    doc = semantic(tmp_path, content=content)
    assert not doc.find_all("equation")
    assert len(doc.find_all("paragraph")) == 1
    assert "Before GLYPH After." in to_markdown(doc)


def test_code_parent_preserves_even_standalone_formula(tmp_path):
    doc = semantic(tmp_path, extra={
        6: "<< /Type /StructTreeRoot /K 10 0 R >>",
        10: "<< /Type /StructElem /S /Code /K 7 0 R >>"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_alt_and_actualtext_are_not_raw_latex_or_markdown(tmp_path):
    for key in ("Alt", "ActualText"):
        doc = _read(tmp_path, "/%s (price $$ 5\\n\\n# Injected heading\\n\\n<img src=x>)" % key,
                    content=DISPLAY)
        assert not doc.find_all("equation")
        assert "GLYPH" in to_markdown(doc)
        assert "Injected heading" not in to_markdown(doc)


def test_tex_rejects_inner_delimiters_and_blank_line_breakout(tmp_path):
    for data in (b"$x$$\n\n[click](javascript:bad)\n\n$$y$", b"x\n\n# heading", b"x$$y"):
        doc = semantic(tmp_path, data=data, suffix="tex")
        assert not doc.find_all("equation")
        assert "GLYPH" in to_markdown(doc)


def test_long_structure_integer_mcids_do_not_exhaust_formula_budget(tmp_path):
    kids = " ".join(str(i) for i in range(1, 12001))
    doc = semantic(tmp_path, extra={
        6: "<< /Type /StructTreeRoot /K [10 0 R 7 0 R] >>",
        10: "<< /Type /StructElem /S /P /Pg 3 0 R /K [%s] >>" % kids})
    assert len(doc.find_all("equation")) == 1
    assert not any("한도" in error for error in doc.errors)


def test_long_structure_without_formula_is_silent(tmp_path):
    doc = semantic(tmp_path, extra={
        6: "<< /Type /StructTreeRoot /K 10 0 R >>",
        10: "<< /Type /StructElem /S /P /K [%s] >>" % " ".join(str(i) for i in range(12000))})
    assert not doc.find_all("equation")
    assert not any("Formula" in error for error in doc.errors)


def test_formula_does_not_consume_unowned_artifact_between_members(tmp_path):
    content = (b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (x) Tj ET EMC "
               b"/Artifact BMC BT /F1 9 Tf 300 30 Td (Page 7) Tj ET EMC "
               b"/Formula <</MCID 1>> BDC BT /F1 12 Tf 110 700 Td (2) Tj ET EMC")
    doc = semantic(tmp_path, content=content, kids="[0 1]")
    assert len(doc.find_all("equation")) == 1
    assert "Page 7" in to_markdown(doc)


def test_table_cell_formula_keeps_cell_glyphs(tmp_path):
    content = (b"50 600 m 250 600 l S 50 650 m 250 650 l S 50 700 m 250 700 l S "
               b"50 600 m 50 700 l S 150 600 m 150 700 l S 250 600 m 250 700 l S "
               b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 60 675 Td (a) Tj ET EMC "
               b"BT /F1 12 Tf 160 675 Td (b) Tj ET "
               b"BT /F1 12 Tf 60 625 Td (c) Tj ET "
               b"BT /F1 12 Tf 160 625 Td (d) Tj ET")
    doc = semantic(tmp_path, content=content)
    assert not doc.find_all("equation")
    table = doc.find_all("table")[0]
    assert table.rows[0][0].text == "a"


def test_footnote_formula_preserves_note_ownership(tmp_path):
    content = (b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
               b"BT /F1 9 Tf 64 502.5 Td (1\\051) Tj ET "
               b"40 115 m 220 115 l S "
               b"/Formula <</MCID 0>> BDC BT /F1 10.5 Tf 40 100 Td (1\\051 GLYPH) Tj ET EMC")
    doc = semantic(tmp_path, content=content, extra={
        4: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 0 /Widths [" + "500 " * 256 + "] >>"})
    assert not doc.find_all("equation")
    assert [n.text for n in doc.find_all("footnote")] == ["GLYPH"]


def test_equation_json_identifies_source_syntax(tmp_path):
    for data, suffix, kind in ((b"<math><mi>x</mi></math>", "xml", "mathml"),
                               (b"$x$", "tex", "latex")):
        doc = semantic(tmp_path, data=data, suffix=suffix)
        equations = [element for section in to_dict(doc)["sections"] for element in section["elements"]
                     if element["type"] == "equation"]
        assert equations[0]["script_format"] == kind


def test_parent_tree_looks_up_page_without_scanning_unrelated_structure(tmp_path, monkeypatch):
    from dochan.pdf import formulas
    monkeypatch.setattr(formulas, "MAX_NODES", 32)
    unrelated = " ".join("<< /S /P /K %d >>" % i for i in range(12000))
    doc = semantic(tmp_path, extra={
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R /StructParents 0 >>",
        6: "<< /Type /StructTreeRoot /ParentTree 10 0 R /K [%s 7 0 R] >>" % unrelated,
        10: "<< /Kids [11 0 R 12 0 R] >>",
        11: "<< /Limits [0 0] /Nums [0 [7 0 R]] >>",
        12: "<< /Limits [1 1] /Nums [1 [null]] >>"})
    assert len(doc.find_all("equation")) == 1
    assert not doc.errors


def test_parent_tree_follows_ancestors_and_preserves_code_role(tmp_path):
    for role, expected in (("P", 1), ("Code", 0)):
        doc = semantic(tmp_path, extra={
            3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R /StructParents 0 >>",
            6: "<< /Type /StructTreeRoot /ParentTree 10 0 R /K 12 0 R >>",
            7: "<< /S /Formula /Pg 3 0 R /K 11 0 R /P 12 0 R /AF [8 0 R] >>",
            10: "<< /Nums [0 [11 0 R]] >>",
            11: "<< /S /Span /K 0 /P 7 0 R >>",
            12: "<< /S /%s /K 7 0 R /P 6 0 R >>" % role})
        assert len(doc.find_all("equation")) == expected


def test_layout_placement_block_is_explicit_display(tmp_path):
    content = (b"BT /F1 12 Tf 50 700 Td (Label) Tj ET "
               b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC")
    doc = semantic(tmp_path, content=content, extra={
        7: "<< /S /Formula /Pg 3 0 R /K 0 /AF [8 0 R] /A << /O /Layout /Placement /Block >> >>"})
    assert len(doc.find_all("equation")) == 1
    assert "Label" in to_markdown(doc)


def test_mathml_explicit_display_does_not_extract_from_a_table(tmp_path):
    content = (b"50 600 m 250 600 l S 50 650 m 250 650 l S 50 700 m 250 700 l S "
               b"50 600 m 50 700 l S 150 600 m 150 700 l S 250 600 m 250 700 l S "
               b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 60 675 Td (a) Tj ET EMC "
               b"BT /F1 12 Tf 160 675 Td (b) Tj ET "
               b"BT /F1 12 Tf 60 625 Td (c) Tj ET "
               b"BT /F1 12 Tf 160 625 Td (d) Tj ET")
    doc = semantic(tmp_path, data=b"<math display=\"block\"><mi>a</mi></math>", content=content)
    assert not doc.find_all("equation")
    assert doc.find_all("table")[0].rows[0][0].text == "a"


def test_untagged_cover_does_not_hide_later_parent_tree_formula(tmp_path):
    cover = b"BT /F1 12 Tf 50 700 Td (Cover) Tj ET"
    doc = semantic(tmp_path, extra={
        2: "<< /Type /Pages /Kids [14 0 R 3 0 R] /Count 2 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R /StructParents 0 "
           "/MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> >>",
        6: "<< /Type /StructTreeRoot /ParentTree 10 0 R /K 7 0 R >>",
        10: "<< /Nums [0 [7 0 R]] >>",
        14: "<< /Type /Page /Parent 2 0 R /Contents 15 0 R "
            "/MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> >>",
        15: b"<< /Length %d >>\nstream\n" % len(cover) + cover + b"\nendstream"})
    assert len(doc.find_all("equation")) == 1
    assert "Cover" in to_markdown(doc)
