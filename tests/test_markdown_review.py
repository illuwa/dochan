"""Shared writer regression tests for emphasis crossing physical lines."""

import pytest

from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.output.markdown import _run_to_md, to_markdown


@pytest.mark.parametrize('style,marker', [
    ({'bold': True}, '**'),
    ({'italic': True}, '*'),
    ({'bold': True, 'italic': True}, '***'),
])
def test_emphasis_closes_and_reopens_at_line_break(style, marker):
    run = TextRun(text='First\nsecond', **style)
    doc = Document(sections=[Section(elements=[Paragraph(runs=[run], heading_level=1)])])
    assert to_markdown(doc) == '# {0}First{0}\n{0}second{0}'.format(marker)
    assert run.text == 'First\nsecond'


def test_multiline_emphasis_preserves_whitespace_and_empty_lines():
    run = TextRun(text=' \tFirst \r\n\n \t\n second\t \n', bold=True)
    assert _run_to_md(run) == ' \t**First** \r\n\n \t\n **second**\t \n'


def test_multiline_emphasis_preserves_other_inline_wrappers():
    run = TextRun(text='First\nsecond', bold=True, underline=True, superscript=True)
    assert _run_to_md(run) == '<sup><u>**First**\n**second**</u></sup>'


def test_multiline_emphasis_keeps_link_and_note_reference_contract():
    doc = Document(sections=[Section(elements=[Paragraph(runs=[
        TextRun(text='First\nsecond', italic=True, link='https://example.org'),
        TextRun(text='ignored\ntext', bold=True, note_ref=7),
    ])])])
    assert to_markdown(doc) == '[*First*\n*second*](https://example.org)[^7]'


def test_plain_multiline_run_is_unchanged():
    assert _run_to_md(TextRun(text=' First \n second\n')) == ' First \n second\n'


def test_table_cell_preserves_image_reference_and_escapes_pipes():
    image = Image(filename='picture.wmf', alt_text='first|second')
    table = Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun('before')]), image])]])
    doc = Document(sections=[Section(elements=[table])])
    assert to_markdown(doc) == '| before ![first\\|second](picture.wmf) |\n| --- |'


def test_table_cell_does_not_duplicate_inline_image_reference():
    image = Image(filename='picture.wmf', inline_reference=True)
    table = Table(rows=[[Cell(paragraphs=[
        Paragraph(runs=[TextRun('![이미지](picture.wmf)')]), image,
    ])]])
    doc = Document(sections=[Section(elements=[table])])
    assert to_markdown(doc).count('picture.wmf') == 1
