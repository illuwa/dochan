"""r2 강조 경계 회귀. 실물 없이 조립한 런과 DOCX로 재현한다."""

import pytest

from dochan.model.document import TextRun
from dochan.output.markdown import _run_to_md, to_markdown


@pytest.mark.parametrize('style,marker', [
    ({'bold': True}, '**'), ({'italic': True}, '*'),
    ({'bold': True, 'italic': True}, '***'),
])
@pytest.mark.parametrize('slashes', [1, 2, 3, 4])
def test_r2_backslash_cannot_escape_emphasis_closer(style, marker, slashes):
    text = 'path' + '\\' * slashes + ' \nnext'
    rendered = _run_to_md(TextRun(text=text, **style))
    # Existing paired escapes stay paired; an unmatched escape needs its mate.
    expected = marker + 'path' + '\\' * (slashes + slashes % 2) + marker
    assert rendered == expected + ' \n' + marker + 'next' + marker


@pytest.mark.parametrize('syntax', [
    '![first\nsecond](word/media/image1.png)',
    '[first\nsecond](https://example.org)',
    '![first [nested]\nsecond](image(1).png)',
    '![first\\]\nsecond](<image (1).png>)',
    '[first\nsecond](url "a\ntitle")',
])
def test_r2_inline_syntax_is_not_split_at_internal_newline(syntax):
    run = TextRun(text='before\n' + syntax + '\nafter', bold=True)
    assert _run_to_md(run) == '**before**\n**' + syntax + '**\n**after**'


def test_r2_docx_bold_multiline_image_alt(tmp_path):
    from test_docx_review_fixes import read
    drawing = ('<w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/'
               'drawingml/2006/wordprocessingDrawing">'
               '<wp:docPr descr="first&#10;second"/><a:blip r:embed="img"/>'
               '</wp:inline></w:drawing>')
    doc = read(tmp_path, '<w:p><w:r><w:rPr><w:b/></w:rPr>' + drawing + '</w:r></w:p>')
    assert to_markdown(doc) == '**![first\nsecond](word/media/a.png)**'


def test_r2_commonmark_interpretation():
    # Already installed locally. CI without it still runs every exact-output test.
    parser = pytest.importorskip('markdown_it').MarkdownIt('commonmark')
    text = _run_to_md(TextRun(text='path\\ \nnext', bold=True))
    assert parser.render(text) == '<p><strong>path\\</strong>\n<strong>next</strong></p>\n'
    text = _run_to_md(TextRun(text='![first\nsecond](image.png)', bold=True))
    assert parser.render(text) == '<p><strong><img src="image.png" alt="first\nsecond" /></strong></p>\n'
