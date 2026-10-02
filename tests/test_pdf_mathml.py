"""Synthetic MathML contracts; no corpus or third-party implementation fixtures."""
import pytest

from dochan.pdf import mathml


@pytest.mark.parametrize("source, expected", [
    ("<mi>x</mi><mo>&gt;</mo><mi>y</mi>", "x>y"),
    ("<msqrt><msup><mi>x</mi><mn>2</mn></msup></msqrt><mo>=</mo>"
     "<mrow><mo>|</mo><mi>x</mi><mo>|</mo></mrow>", r"\sqrt{x^{2}}=|x|"),
    ("<mfrac><mi>a</mi><mi>b</mi></mfrac>", r"\frac{a}{b}"),
    ("<mroot><mi>x</mi><mn>3</mn></mroot>", r"\sqrt[3]{x}"),
    ("<msubsup><mi>x</mi><mi>i</mi><mn>2</mn></msubsup>", "x_{i}^{2}"),
    ("<msup><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><mn>2</mn></msup>",
     "{a+b}^{2}"),
    ("<mi>𝑝</mi><mo>−</mo><mi>α</mi><mo>≤</mo><mi>β</mi>", r"p-\alpha\leq\beta"),
    ('<mi mathvariant="normal">sin</mi><mi>x</mi>', r"\sin x"),
    ('<mi mathvariant="bold">v</mi><mi mathvariant="normal">A</mi>', r"\mathbf{v}\mathrm{A}"),
    ('<mi>𝐯</mi><mi>ℝ</mi>', r"\mathbf{v}\mathbb{R}"),
    ('<mtext> a &amp; b_% </mtext>', r"\text{a \& b\_\%}"),
    ('<mo>{</mo><mo>\\</mo><mo>}</mo>', r"\{\backslash{}\}"),
    ('<mspace width="0.167em"/><mi>x</mi><mspace width="-4.981pt"/>',
     r"\hspace{0.167em}x\hspace{-4.981pt}"),
    ('<mfenced open="[" close="]" separators=";"><mi>x</mi><mi>y</mi></mfenced>',
     r"\left[x;y\right]"),
    ('<mtable><mtr><mtd><mn>1</mn></mtd><mtd><mn>2</mn></mtd></mtr>'
     '<mtr><mtd><mn>3</mn></mtd><mtd><mn>4</mn></mtd></mtr></mtable>',
     r"\begin{matrix}1 & 2 \\ 3 & 4\end{matrix}"),
    ('<mrow intent="_newline"/>', ''),
    ('<munder><mo>∑</mo><mi>i</mi></munder>', r"\sum_{i}"),
    ('<mover><mi>x</mi><mo>¯</mo></mover>', r"\overline{x}"),
])
def test_pdf_mathml_presentation(source, expected):
    assert mathml.mathml_to_latex(("<math>" + source + "</math>").encode()) == expected


def test_pdf_mathml_namespace_and_semantics():
    source = b'<math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mi>x</mi><annotation encoding="application/x-tex">x</annotation></semantics></math>'
    assert mathml.mathml_to_latex(source) == "x"


def test_pdf_mathml_rejects_unrepresentable_combined_unicode_style():
    # MATHEMATICAL SANS-SERIF BOLD SMALL A must not become serif mathbf a.
    with pytest.raises(ValueError):
        mathml.mathml_to_latex("<math><mi>𝗮</mi></math>".encode())


@pytest.mark.parametrize("source", [
    b"<math>", b"<html><mi>x</mi></html>",
    b'<math xmlns="urn:other"><mi>x</mi></math>',
    b'<math><mi><mo>+</mo></mi></math>',
    b'<math><msup><mi>x</mi></msup></math>',
    b'<math><mfrac bevelled="true"><mn>1</mn><mn>2</mn></mfrac></math>',
    b'<math><mfrac linethickness="0"><mn>1</mn><mn>2</mn></mfrac></math>',
    b'<math><menclose notation="updiagonalstrike"><mi>x</mi></menclose></math>',
    b'<math><mspace width="1em}\\input{bad"/></math>',
    b'<math><mi mathvariant="unknown">x</mi></math>',
    b'<math>lost<mi>x</mi></math>', b'<math><mi>x</mi>lost</math>',
    b'<math><mtable><mtr><mtd columnspan="2"><mi>x</mi></mtd></mtr></mtable></math>',
    b'<!DOCTYPE math [<!ENTITY a "expanded">]><math><mi>&a;</mi></math>',
    b'<!DOCTYPE math SYSTEM "file:///etc/passwd"><math><mi>x</mi></math>',
    b'<math><maction actiontype="toggle"><mi>x</mi><mi>y</mi></maction></math>',
])
def test_pdf_mathml_rejects_unsupported_or_malformed(source):
    with pytest.raises(ValueError):
        mathml.mathml_to_latex(source)


@pytest.mark.parametrize("limit, source", [
    ("MAX_MATHML_BYTES", b"<math><mi>x</mi></math>"),
    ("MAX_MATHML_NODES", b"<math><mi>x</mi><mi>y</mi></math>"),
    ("MAX_MATHML_DEPTH", b"<math><mrow><mi>x</mi></mrow></math>"),
    ("MAX_MATHML_OUTPUT", b"<math><mi>long</mi></math>"),
])
def test_pdf_mathml_resource_limits(monkeypatch, limit, source):
    monkeypatch.setattr(mathml, limit, 2)
    with pytest.raises(ValueError):
        mathml.mathml_to_latex(source)


@pytest.mark.parametrize("source, expected", [
    ('<msubsup><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow>'
     '<mi>n</mi></msubsup>', r'\sum_{i=1}^{n}'),
    ('<msubsup><mo>∫</mo><mn>0</mn><mn>1</mn></msubsup>', r'\int_{0}^{1}'),
    ('<msub><mi>α</mi><mi>i</mi></msub>', r'\alpha_{i}'),
    ('<mi>α</mi><mi>x</mi>', r'\alpha x'),
    ('<mi>sin</mi><mi>x</mi>', r'\sin x'),
    ('<mi>log</mi><mi>x</mi>', r'\log x'),
    ('<mi>velocity</mi>', r'\mathrm{velocity}'),
    ('<mi>a</mi><mi>mod</mi><mi>b</mi>', r'a\operatorname{mod}b'),
    ('<munder><mi>lim</mi><mrow><mi>x</mi><mo>→</mo><mn>0</mn></mrow>'
     '</munder><mi>x</mi>', r'\lim_{x\to0}x'),
    ('<munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow>'
     '<mi>n</mi></munderover>', r'\sum_{i=1}^{n}'),
    ('<mtext>α × β</mtext>', r'\text{\ensuremath{\alpha} \ensuremath{\times} \ensuremath{\beta}}'),
    ('<mover><mi>x</mi><mo>^</mo></mover>', r'\hat{x}'),
    ('<mover accent="true"><mi>x</mi><mo>~</mo></mover>', r'\tilde{x}'),
    ('<mover accent="true"><mi>x</mi><mo>→</mo></mover>', r'\vec{x}'),
])
def test_pdf_mathml_review_semantic_latex(source, expected):
    assert mathml.mathml_to_latex(('<math>' + source + '</math>').encode()) == expected


@pytest.mark.parametrize('attribute', ['linethickness="0"', 'bevelled="true"',
                                       'scriptlevel="1"', 'mathvariant="bold"'])
def test_pdf_mathml_rejects_unsupported_inherited_style(attribute):
    source = ('<math><mfenced><mstyle ' + attribute + '><mfrac><mi>n</mi>'
              '<mi>k</mi></mfrac></mstyle></mfenced></math>')
    with pytest.raises(ValueError, match='inherited'):
        mathml.mathml_to_latex(source.encode())
