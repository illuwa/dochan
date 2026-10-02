"""3차 리뷰의 의미 손실을 합성 PDF 바이트로 재현한다."""
import pytest

from dochan.output.markdown import to_markdown
from dochan.pdf.mathml import mathml_to_latex
from dochan.pdf.reader import PDFReader
from test_pdf_formula_review import semantic


@pytest.mark.parametrize("placement", ["", "/A << /O /Layout /Placement /Block >>"])
@pytest.mark.parametrize("source", ["associated", "structure"])
def test_explicit_inline_superscript_preserves_glyphs(tmp_path, placement, source):
    content = (b"BT /F1 12 Tf 50 700 Td (Body) Tj ET "
               b"/Formula <</MCID 0>> BDC BT /F1 8 Tf 78 704 Td (2) Tj ET EMC "
               b"BT /F1 12 Tf 90 700 Td (continues.) Tj ET")
    extra = {7: "<< /S /Formula /Pg 3 0 R /K 0 /AF [8 0 R] %s >>" % placement}
    if source == "structure":
        extra = {
            7: "<< /S /Formula /Pg 3 0 R /K 10 0 R %s >>" % placement,
            10: "<< /S /math /NS 12 0 R /A << /display (inline) >> /K 11 0 R >>",
            11: "<< /S /mn /NS 12 0 R /K 0 >>",
            12: "<< /NS (http://www.w3.org/1998/Math/MathML) >>",
        }
    doc = semantic(tmp_path, data=b'<math display="inline"><mn>2</mn></math>',
                   content=content, extra=extra)
    assert not doc.find_all("equation")
    assert len(doc.find_all("paragraph")) == 1
    assert all(text in to_markdown(doc) for text in ("Body", "2", "continues."))


def test_text_table_formula_preserves_complete_cells(tmp_path):
    content = (b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 50 700 Td (a) Tj ET EMC "
               b"BT /F1 12 Tf 200 700 Td (b) Tj ET "
               b"BT /F1 12 Tf 50 680 Td (c) Tj ET "
               b"BT /F1 12 Tf 200 680 Td (d) Tj ET "
               b"BT /F1 12 Tf 50 660 Td (e) Tj ET "
               b"BT /F1 12 Tf 200 660 Td (f) Tj ET")
    semantic(tmp_path, data=b'<math display="block"><mi>a</mi></math>', content=content)
    doc = PDFReader(text_tables=True).read(str(tmp_path / "formula.pdf"))
    assert not doc.find_all("equation")
    tables = doc.find_all("table")
    assert len(tables) == 1
    assert [[cell.text for cell in row] for row in tables[0].rows] == [
        ["a", "b"], ["c", "d"], ["e", "f"]]


@pytest.mark.parametrize("source, expected", [
    (b"x % comment\n + y", "x + y"),
    (b"x % comment\r\n + y", "x + y"),
    (b"x % comment\r + y", "x + y"),
    (b"x \\% % comment\n + y", r"x \% + y"),
    (b"x \\\\% comment\n + y", r"x \\+ y"),
    (b"\\alpha% comment\nx", r"\alpha x"),
    (b"\\alpha% comment\n% another\nx", r"\alpha x"),
    (b"\\text{a% comment\nb}", r"\text{ab}"),
    (b"% leading\n$$x % trailing\n+y$$ % end", "x +y"),
])
def test_tex_comments_are_removed_before_normalizing_lines(tmp_path, source, expected):
    doc = semantic(tmp_path, data=source, suffix="tex")
    equations = doc.find_all("equation")
    assert len(equations) == 1
    assert equations[0].latex_override == expected
    assert equations[0].script == source.decode().strip()


@pytest.mark.parametrize("source", [b"x^^25 hidden", b"\\verb|%|", b"\\catcode37=12 x%y"])
def test_tex_unsupported_comment_lexing_preserves_glyphs(tmp_path, source):
    doc = semantic(tmp_path, data=source, suffix="tex")
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("Formula" in error for error in doc.errors)


@pytest.mark.parametrize("attribute, body", [
    ('linethickness="0"', '<mfenced><mfrac><mi>n</mi><mi>k</mi></mfrac></mfenced>'),
    ('mathvariant="bold"', '<mi>v</mi>'),
    ('displaystyle="false"', '<munder><mo>sum</mo><mi>i</mi></munder>'),
    ('scriptlevel="1"', '<mi>x</mi>'),
    ('bevelled="true"', '<mfrac><mi>a</mi><mi>b</mi></mfrac>'),
])
def test_math_root_inherited_style_is_rejected_and_glyphs_survive(tmp_path, attribute, body):
    source = ('<math %s>%s</math>' % (attribute, body)).encode()
    with pytest.raises(ValueError, match="inherited style"):
        mathml_to_latex(source)
    doc = semantic(tmp_path, data=source)
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_math_root_metadata_does_not_block_supported_formula():
    assert mathml_to_latex(b'<math display="block" id="m1" class="equation" '
                          b'intent=":equation"><mi>x</mi></math>') == "x"


def test_namespace_math_root_cannot_drop_inherited_attributes(tmp_path):
    doc = semantic(tmp_path, extra={
        7: "<< /S /Formula /Pg 3 0 R /K 10 0 R >>",
        10: "<< /S /math /NS 12 0 R /A << /O /MathML /mathsize (small) >> /K 11 0 R >>",
        11: "<< /S /mi /NS 12 0 R /K 0 >>",
        12: "<< /NS (http://www.w3.org/1998/Math/MathML) >>",
    })
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)


def test_namespace_mspace_linebreak_preserves_glyphs(tmp_path):
    # AF 없이 구조 트리 namespace MathML 만 있을 때도 줄바꿈 mspace 는 변환을 거부하고 두 줄의 글리프를 보존한다.
    content = (b"/Formula <</MCID 0>> BDC BT /F1 12 Tf 100 700 Td (XLEFT) Tj ET EMC "
               b"/Formula <</MCID 1>> BDC BT /F1 12 Tf 100 680 Td (YRIGHT) Tj ET EMC")
    doc = semantic(tmp_path, content=content, kids="[0 1]", extra={
        7: "<< /S /Formula /Pg 3 0 R /K 10 0 R >>",
        10: "<< /S /math /NS 12 0 R /K [11 0 R 13 0 R 14 0 R] >>",
        11: "<< /S /mi /NS 12 0 R /K 0 >>",
        12: "<< /NS (http://www.w3.org/1998/Math/MathML) >>",
        13: "<< /S /mspace /NS 12 0 R /A << /O /NSO /linebreak (newline) >> >>",
        14: "<< /S /mi /NS 12 0 R /K 1 >>",
    })
    markdown = to_markdown(doc)
    assert not doc.find_all("equation")
    assert "XLEFT" in markdown and "YRIGHT" in markdown
