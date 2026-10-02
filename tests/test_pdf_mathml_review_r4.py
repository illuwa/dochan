"""Fourth-review MathML regressions built from synthetic presentation trees."""
import pytest

from dochan.pdf.mathml import mathml_to_latex


def _latex(source):
    return mathml_to_latex(("<math>" + source + "</math>").encode())


@pytest.mark.parametrize("source, expected", [
    ("<mi>a</mi><mo>mod</mo><mi>b</mi>", r"a\operatorname{mod}b"),
    ("<munder><mo>lim</mo><mi>n</mi></munder><mi>x</mi>", r"\lim_{n}x"),
    ("<mi>a</mi><mo>custom</mo><mi>b</mi>", r"a\operatorname{custom}b"),
    ('<mo mathvariant="normal">sin</mo><mi>x</mi>', r"\sin x"),
])
def test_multi_character_mo_is_an_operator(source, expected):
    assert _latex(source) == expected


@pytest.mark.parametrize("source, expected", [
    ("<msup><mi>sin</mi><mn>2</mn></msup><mi>x</mi>", r"\sin^{2}x"),
    ("<msub><mi>log</mi><mn>2</mn></msub><mi>x</mi>", r"\log_{2}x"),
    ("<msubsup><mo>lim</mo><mi>n</mi><mi>k</mi></msubsup>", r"\lim_{n}^{k}"),
])
def test_function_scripts_retain_operator_atom(source, expected):
    assert _latex(source) == expected


@pytest.mark.parametrize("prime, expected", [
    ("<mo>′</mo>", r"\prime"),
    ("<mo>″</mo>", r"\prime\prime"),
    ("<mo>′</mo><mo>′</mo>", r"\prime\prime"),
])
def test_postfix_prime_is_a_superscript(prime, expected):
    assert _latex("<mi>f</mi>" + prime + "<mo>(</mo><mi>x</mi><mo>)</mo>") == (
        "f^{" + expected + "}(x)"
    )


def test_explicit_prime_superscript_is_not_raised_twice():
    assert _latex("<msup><mi>f</mi><mo>′</mo></msup>") == r"f^{\prime}"
    assert _latex("<msup><mi>f</mi><mrow><mo>′</mo><mo>′</mo></mrow></msup>") == (
        r"f^{\prime\prime}"
    )


def test_postfix_prime_after_script_has_no_double_tex_superscript():
    assert _latex("<msup><mi>f</mi><mn>2</mn></msup><mo>′</mo>") == r"{f^{2}}^{\prime}"


def test_postfix_prime_after_wrapped_script_has_no_double_tex_superscript():
    assert _latex("<mrow><msup><mi>f</mi><mn>2</mn></msup></mrow><mo>′</mo>") == (
        r"{f^{2}}^{\prime}"
    )


def test_newline_mspace_declines_lossy_horizontal_space_conversion():
    with pytest.raises(ValueError, match="linebreak"):
        _latex('<mi>x</mi><mspace linebreak="newline"/><mi>y</mi>')


def test_mspace_preserves_width_without_forced_linebreak():
    assert _latex('<mspace width="1em" linebreak="nobreak"/>') == r"\hspace{1em}"


def test_newline_mspace_preserves_pdf_glyphs(tmp_path):
    from dochan.output.markdown import to_markdown
    from test_pdf_formula_review import semantic

    doc = semantic(tmp_path, data=b'<math><mi>x</mi><mspace linebreak="newline"/><mi>y</mi></math>')
    assert not doc.find_all("equation")
    assert "GLYPH" in to_markdown(doc)
    assert any("linebreak" in error for error in doc.errors)
