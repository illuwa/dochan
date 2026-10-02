"""Fourth review: emphasis boundaries, missing image assets and PPT headers."""
import struct

import pytest

from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.output.markdown import _emphasis_parts, _run_to_md, to_markdown
from dochan.office_binary.officeart import parse_records
from dochan.office_binary.ppt_text import render_text, text_blocks
from dochan.office_binary.ppt_styles import read_master_styles
from test_ppt_legacy_styles import master
from test_ppt_text import cf, pf, rec


@pytest.mark.parametrize('code', ['`a\nb`', '``a`\nb``', '`a\\`', '``[a\nb](x)``'])
def test_r4_code_span_is_atomic(code):
    text = 'run ' + code + ' here\nnext'
    assert _run_to_md(TextRun(text, bold=True)) == '**run ' + code + ' here**\n**next**'


@pytest.mark.parametrize('style', [{'bold': True}, {'italic': True}, {'bold': True, 'italic': True}])
def test_r4_multiline_code_commonmark(style):
    parser = pytest.importorskip('markdown_it').MarkdownIt()
    rendered = parser.render(_run_to_md(TextRun('run ``a`\nb`` here', **style)))
    assert '<code>a` b</code>' in rendered
    assert '**' not in rendered


@pytest.mark.parametrize('text,parts', [
    ('unmatched `a\nb', ['unmatched `a', 'b']),
    ('unequal ``a\nb`', ['unequal ``a', 'b`']),
    ('escaped \\`a\nb`', ['escaped \\`a', 'b`']),
    ('partial \\``a\nb`\nnext', ['partial \\``a\nb`', 'next']),
    ('code `a\\`\nnext', ['code `a\\`', 'next']),
    ('code `[a\nb`\nnext', ['code `[a\nb`', 'next']),
    ('[label `a\nb`](url)\nnext', ['[label `a\nb`](url)', 'next']),
])
def test_r4_code_span_delimiters_and_escapes(text, parts):
    assert list(_emphasis_parts(text)) == parts


def test_r4_many_unmatched_backtick_lengths():
    pieces = ['`' * size + ' text' for size in range(1, 300)]
    assert list(_emphasis_parts('\n'.join(pieces))) == pieces


@pytest.mark.parametrize('text,escaped', [
    ('* la Formation,', r'\* la Formation,'),
    ('note *', r'note \*'), ('_ label _', r'\_ label \_'),
    ('** hello __', r'\*\* hello \_\_'),
    (r'hello\*', r'hello\*'),
])
@pytest.mark.parametrize('style,marker', [({'italic': True}, '*'), ({'bold': True}, '**')])
def test_r4_literal_boundary_markers(text, escaped, style, marker):
    assert _run_to_md(TextRun(text, **style)) == marker + escaped + marker


def test_r4_literal_star_list_commonmark():
    parser = pytest.importorskip('markdown_it').MarkdownIt()
    result = parser.render(_run_to_md(TextRun('intro :\n* one\n* two', italic=True)))
    assert result == '<p><em>intro :</em>\n<em>* one</em>\n<em>* two</em></p>\n'


@pytest.mark.parametrize('text', ['*title*', '_label_', '*reference', 'note*', '*', '**'])
def test_r4_preserves_existing_emphasis_syntax_and_cross_run_delimiters(text):
    # TextRun also carries generated inline Markdown, potentially spanning runs.
    # Unlike a star followed by whitespace, these edges can be delimiters.
    assert _run_to_md(TextRun(text, bold=True)) == '**' + text + '**'


@pytest.mark.parametrize('in_cell', [True, False])
def test_r4_missing_image_asset_preserves_description_ocr_caption(in_cell):
    img = Image(alt_text='drawing [one]', ocr_text='readable',
                caption=[Paragraph(runs=[TextRun('caption')])])
    elem = Table(rows=[[Cell(paragraphs=[img])]]) if in_cell else img
    text = to_markdown(Document(sections=[Section(elements=[elem])]))
    assert '![' not in text
    assert 'drawing' in text and 'readable' in text and 'caption' in text


def test_r4_empty_cell_image_is_omitted():
    table = Table(rows=[[Cell(paragraphs=[Image()])]])
    assert to_markdown(Document(sections=[Section(elements=[table])])) == '|  |\n| --- |'


@pytest.mark.parametrize('img', [Image(filename='external.png'), Image(image_data=b'bytes')])
def test_r4_image_with_target_or_data_keeps_reference(img):
    assert '![' in to_markdown(Document(sections=[Section(elements=[img])]))


@pytest.mark.parametrize('prefix', [b'', rec(3999, b'\x01')])
@pytest.mark.parametrize('kind,payload', [(4008, b'No header'), (4000, 'No header'.encode('utf-16le'))])
def test_r4_missing_ppt_header_uses_other_style(prefix, kind, payload):
    styles = read_master_styles(parse_records(
        master(1, [(0, 3, struct.pack('<H', 3))]) +
        master(4, [(0, 0x20000, struct.pack('<H', 17))])))
    errors = []
    block = text_blocks(parse_records(prefix + rec(kind, payload)), errors)[0]
    run = render_text(block, None, default_styles=styles)[0].runs[0]
    assert block.text_type == 4
    assert not run.bold and not run.italic and run.font_size_pt == 17
    assert bool(errors) == bool(prefix)


def test_r4_missing_ppt_header_keeps_explicit_character_style():
    data = rec(4008, b'A') + rec(4001, pf(2) + cf(2, 1, struct.pack('<H', 1)))
    block = text_blocks(parse_records(data))[0]
    assert render_text(block, None)[0].runs[0].bold
