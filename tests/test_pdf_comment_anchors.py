"""Comment anchors use the same conservative glyph geometry as links."""
import pytest

from dochan.output.markdown import to_markdown
from test_pdf_annotations import _read


def _body(doc):
    return [p for p in doc.find_all('paragraph')
            if getattr(p.provenance, 'path', '') != 'annots']


def _markers(doc):
    return [(p.text, r.note_reference_number) for p in _body(doc)
            for r in p.runs if r.note_reference_type == 'comment']


@pytest.mark.parametrize('subtype', ['Highlight', 'Underline', 'StrikeOut', 'Squiggly'])
def test_pdf_markup_comment_anchors_at_selected_run_end(tmp_path, subtype):
    doc = _read(tmp_path, [
        '<< /Subtype /%s /Rect [72 716 138 732] '
        '/QuadPoints [96 732 114 732 96 716 114 716] /Contents (Review) >>' % subtype,
    ], content=b'BT /F1 12 Tf 72 720 Td (abc def ghi) Tj ET')
    assert _markers(doc) == [('abc def[comment 1] ghi', 1)]
    assert 'abc def[comment 1] ghi' in to_markdown(doc)
    assert to_markdown(doc).count('[comment 1]') == 1
    assert to_markdown(doc).count('[^comment-1]: Review') == 1
    assert doc.find_all('comment')[0].text == 'Review'


def test_pdf_text_comment_anchors_using_rect_and_retains_link(tmp_path):
    doc = _read(tmp_path, [
        '<< /Subtype /Text /Rect [96 716 114 732] /Contents (Review) >>',
        '<< /Subtype /Link /Rect [96 716 114 732] /A << /S /URI /URI (https://example.org) >> >>',
    ], content=b'BT /F1 12 Tf 72 720 Td (abc def ghi) Tj ET')
    assert _markers(doc) == [('abc def[comment 1] ghi', 1)]
    assert [(r.text, r.link) for p in _body(doc) for r in p.runs if r.link] == [('def', 'https://example.org')]


@pytest.mark.parametrize('geometry', [
    '/QuadPoints [97 732 114 732 97 716 114 716]',  # cuts a glyph
    '/QuadPoints [400 732 420 732 400 716 420 716]',
    '/QuadPoints [1 2 3]',
    '',
])
def test_pdf_comment_unmatched_or_ambiguous_geometry_keeps_fallback(tmp_path, geometry):
    doc = _read(tmp_path, [
        '<< /Subtype /Highlight /Rect [96 716 114 732] %s /Contents (Review) >>' % geometry,
    ], content=b'BT /F1 12 Tf 72 720 Td (abc def ghi) Tj ET')
    assert not _markers(doc)
    assert any(p.text == '[comment 1]' for p in doc.find_all('paragraph'))


def test_pdf_comment_unknown_font_widths_defer(tmp_path):
    doc = _read(tmp_path, [
        '<< /Subtype /Text /Rect [72 716 138 732] /Contents (Review) >>',
    ], extra={4: '<< /Type /Font /Subtype /Type1 /BaseFont /Unknown >>'},
        content=b'BT /F1 12 Tf 72 720 Td (abc def ghi) Tj ET')
    assert not _markers(doc)
    assert any(p.text == '[comment 1]' for p in doc.find_all('paragraph'))


def test_pdf_comment_transformed_table_anchor_survives(tmp_path):
    content = (b'0 600 200 100 re S 100 600 m 100 700 l S 0 650 m 200 650 l S '
               b'q 2 0 0 2 10 610 cm BT /F1 10 Tf (Cell) Tj ET Q '
               b'BT /F1 10 Tf 120 660 Td (Other) Tj ET')
    doc = _read(tmp_path, [
        '<< /Subtype /Text /Rect [10 607 50 630] /Contents (Review) >>',
    ], content=content)
    assert _markers(doc) == [('Cell[comment 1]', 1)]
    assert not any(p.text == '[comment 1]' for p in doc.find_all('paragraph'))


def test_pdf_multiline_comment_anchors_once_after_last_selected_run(tmp_path):
    content = (b'BT /F1 12 Tf 72 720 Td (first) Tj ET '
               b'BT /F1 12 Tf 72 700 Td (second) Tj ET')
    doc = _read(tmp_path, [
        '<< /Subtype /Highlight /QuadPoints [72 732 102 732 72 716 102 716 '
        '72 712 108 712 72 696 108 696] /Contents (Review) >>',
    ], content=content)
    assert len(_markers(doc)) == 1
    assert _markers(doc)[0][0].endswith('second[comment 1]')


def test_pdf_comment_survives_note_paragraph_conversion():
    from dochan.pdf.content import Fragment, _Line
    from dochan.pdf.notes import _paragraph
    fragment = Fragment(72, 80, 48, 10, 'note text', 5,
                        comment_markers=[(9, 2)])
    paragraph = _paragraph(_Line([fragment]), 1)
    marker = paragraph.runs[-1]
    assert marker.text == '[comment 2]'
    assert marker.note_reference_type == 'comment'
    assert marker.note_reference_number == 2
    assert marker.note_ref == 0


def test_pdf_page_content_failure_preserves_comment_fallback(tmp_path, monkeypatch):
    from dochan.pdf.reader import PDFReader

    def fail(*_args, **_kwargs):
        raise ValueError('bad page content')

    monkeypatch.setattr(PDFReader, '_page_content_parts', fail)
    doc = _read(tmp_path, ['<< /Subtype /Text /Rect [72 716 96 732] /Contents (Review) >>'])
    assert doc.find_all('comment')[0].text == 'Review'
    assert any(p.text == '[comment 1]' for p in doc.find_all('paragraph'))
    assert any('파싱 실패' in error for error in doc.errors)


def test_pdf_overlapping_different_comments_defer_both(tmp_path):
    doc = _read(tmp_path, [
        '<< /Subtype /Text /Rect [72 716 96 732] /Contents (First) >>',
        '<< /Subtype /Text /Rect [72 716 96 732] /Contents (Second) >>',
    ])
    assert not _markers(doc)
    assert [(c.number, c.text) for c in doc.find_all('comment')] == [(1, 'First'), (2, 'Second')]
    assert [p.text for p in doc.find_all('paragraph') if p.text.startswith('[comment ')] == [
        '[comment 1]', '[comment 2]']
