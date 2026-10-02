"""4차 리뷰의 inline 경계와 입력 크기별 검사 상한을 재현한다."""
import pytest

from dochan.output.markdown import to_markdown
from dochan.pdf.reader import PDFReader
from test_pdf_formula_review import semantic


@pytest.mark.parametrize("offset", [5, -3])
@pytest.mark.parametrize("data,suffix", [
    (b"<math><msup><mrow/><mn>2</mn></msup></math>", "xml"),
    (b"$^2$", "tex"), (br"\(^\circ\)", "tex"),
])
def test_undeclared_inline_script_preserves_paragraph(tmp_path, offset, data, suffix):
    content = (b"BT /F1 12 Tf 50 700 Td (Area 5 m) Tj ET "
               b"/Formula <</MCID 0>> BDC BT /F1 8 Tf 101 %d Td (2) Tj ET EMC "
               b"BT /F1 12 Tf 108 700 Td (is small.) Tj ET") % (700 + offset)
    doc = semantic(tmp_path, data=data, suffix=suffix, content=content)
    assert not doc.find_all("equation")
    assert len(doc.find_all("paragraph")) == 1
    assert all(s in to_markdown(doc) for s in ("Area 5 m", "2", "is small."))


@pytest.mark.parametrize("data", [b"$x$", br"\(x\)"])
def test_tex_inline_declaration_beats_isolation_and_layout(tmp_path, data):
    doc = semantic(tmp_path, data=data, suffix="tex", extra={
        7: "<< /S /Formula /Pg 3 0 R /K 0 /AF [8 0 R] /A << /O /Layout /Placement /Block >> >>"})
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


@pytest.mark.parametrize("data", [b"$$x$$", br"\[x\]", br"\begin{equation*}x\end{equation*}"])
def test_tex_display_wrappers_are_removed(tmp_path, data):
    content = (b"BT /F1 12 Tf 50 700 Td (Label) Tj ET "
               b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (GLYPH) Tj ET EMC")
    doc = semantic(tmp_path, data=data, suffix="tex", content=content)
    equations = doc.find_all("equation")
    assert len(equations) == 1
    assert equations[0].latex == "x"
    assert equations[0].script == data.decode()


def test_formula_geometry_budget_warns_and_preserves_glyphs(tmp_path, monkeypatch):
    from dochan.pdf import formulas
    monkeypatch.setattr(formulas, "MAX_FORMULA_GEOMETRY_CHECKS", 0, raising=False)
    doc = semantic(tmp_path)
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("기하 검사 한도" in e for e in doc.errors)


def test_footnote_formula_does_not_warn_about_owned_glyphs(tmp_path):
    content = (b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
               b"BT /F1 9 Tf 64 502.5 Td (1\\051) Tj ET "
               b"40 115 m 220 115 l S "
               b"/Formula <</MCID 0>> BDC BT /F1 10.5 Tf 40 100 Td (1\\051 GLYPH) Tj ET EMC")
    doc = semantic(tmp_path, content=content, extra={
        4: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 0 /Widths [" + "500 " * 256 + "] >>"})
    assert [n.text for n in doc.find_all("footnote")] == ["GLYPH"]
    assert not any("MCID 글리프 없음" in e for e in doc.errors)


def test_text_table_prepass_skipped_on_page_without_formula(tmp_path, monkeypatch):
    from dochan.pdf import reader
    semantic(tmp_path, extra={6: "<< /Type /StructTreeRoot /K [] >>"})
    calls = []
    original = reader.detect_text_tables

    def observe(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(reader, "detect_text_tables", observe)
    PDFReader(text_tables=True).read(str(tmp_path / "formula.pdf"))
    assert len(calls) == 1  # Final reconstruction only, without a Formula prepass.


def test_flat_parent_tree_numbers_are_indexed_once(tmp_path, monkeypatch):
    from dochan.pdf.formulas import FormulaExtractor
    from dochan.pdf.structure import PDFFile
    semantic(tmp_path)
    extractor = FormulaExtractor(PDFFile((tmp_path / "formula.pdf").read_bytes()))

    class CountedNumbers(list):
        reads = 0

        def __getitem__(self, key):
            self.reads += 1
            return super().__getitem__(key)

    nums = CountedNumbers(v for i in range(100) for v in (i, [i]))
    extractor._parent_tree = {"Nums": nums}
    for key in range(90, 100):
        assert extractor._parents(key) == [key]
    assert nums.reads <= 200
