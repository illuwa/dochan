"""Repeated layout work must not change model reachability or geometry."""
from unittest.mock import patch

from dochan.model.document import Document, Paragraph, Section
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.utils.heading_font import _sample_exclusions


def test_font_sample_uses_one_bounded_traversal():
    body, caption, header, note = [Paragraph() for _ in range(4)]
    table = Table(rows=[[Cell(paragraphs=[body])]], caption=[caption])
    image = Image(caption=[caption])
    unknown = Footnote(type='unknown', paragraphs=[body])
    doc = Document(sections=[Section(elements=[
        table, image, HeaderFooter(paragraphs=[header]),
        Footnote(paragraphs=[note]), unknown, table,
    ])])
    # Shared nodes, cycles and the existing depth cap use Document's contract.
    table.rows[0][0].paragraphs.append(table)
    expected_reachable = {id(p) for p in doc.find_all('paragraph')}
    expected_excluded = {id(caption), id(header), id(note)}
    with patch.object(doc, '_find_recursive', wraps=doc._find_recursive) as walk:
        assert _sample_exclusions(doc) == (expected_reachable, expected_excluded)
    # One traversal visits the root and six child lists; the cycle is skipped.
    assert walk.call_count == 7


def test_table_numeric_probe_reuses_cell_line_assembly():
    from dochan.pdf import tables
    from dochan.pdf.content import Fragment, Segment

    xs, ys = [0, 50, 100, 150], [0, 30, 60, 90]
    segments = [Segment(0, y, 150, y) for y in ys]
    segments += [Segment(x, 0, x, 90) for x in xs]
    fragments = [Fragment(x + 10, y + 10, 10, 10, str(i), 5, order=i)
                 for i, (x, y) in enumerate((x, y) for y in ys[:-1] for x in xs[:-1])]
    with patch.object(tables, 'assemble_lines', wraps=tables.assemble_lines) as assemble:
        result = tables.build_tables(segments, fragments)
    assert [[cell.text for cell in row] for row in result[0].table.rows] == [
        ['6', '7', '8'], ['3', '4', '5'], ['0', '1', '2']]
    assert assemble.call_count == 9


def test_no_link_regions_need_no_fragment_geometry():
    from dochan.pdf import annotations
    from dochan.pdf.content import Fragment

    fragment = Fragment(0, 0, 10, 10, 'a', 5, char_offsets=[0, 10])
    warnings = []
    with patch.object(annotations.math, 'hypot', wraps=annotations.math.hypot) as norm:
        annotations.attach_links([fragment], [], warnings)
    assert fragment.link_spans == [] and warnings == []
    assert norm.call_count == 0


def test_endnote_repeated_baseline_keeps_geometry_budget(monkeypatch):
    from dochan.pdf import notes
    from dochan.pdf.content import Fragment

    fragments = [Fragment(0, 100, 10, 12, 'body', 5)]
    fragments += [Fragment(10, 103, 5, 8, str(i), 3, order=i) for i in (1, 2)]
    assert notes.endnote_references(fragments) == [(1, '1'), (2, '2')]
    # Each marker still spends three nearby candidates, even on cache hits.
    monkeypatch.setattr(notes, 'MAX_NOTE_GEOMETRY_CHECKS', 5)
    warnings = []
    assert notes.endnote_references(fragments, warnings) == []
    assert len(warnings) == 1 and '미주 기하 검사' in warnings[0]


def test_note_without_definition_delimiter_needs_no_line_assembly():
    from dochan.pdf import notes
    from dochan.pdf.content import Fragment

    fragments = [Fragment(0, 500, 30, 12, 'body', 5),
                 Fragment(0, 100, 30, 8, '1. plain footer', 5, order=1)]
    with patch.object(notes, 'assemble_lines', wraps=notes.assemble_lines) as assemble:
        assert notes.detect_notes(fragments, [], (0, 800), 1) == ([], set(), {}, 1)
    assert assemble.call_count == 0


def test_reference_point_axes_are_normalized_once_per_page():
    from dochan.pdf import tables
    from dochan.pdf.content import Fragment

    class Direction(float):
        powers = 0

        def __pow__(self, exponent):
            type(self).powers += 1
            return super().__pow__(exponent)

    fragments = [Fragment(i, i * 2, 10, 9, 'body', 5,
                          dir_x=Direction(3), dir_y=Direction(4),
                          up_x=Direction(-2), up_y=Direction(5)) for i in range(20)]
    expected = [tables._reference_point(f) for f in fragments]
    Direction.powers = 0
    points, _ = tables._fragment_index(fragments)
    assert [point for point, _ in points] == expected
    assert Direction.powers == 4


def test_note_uniform_size_cannot_have_smaller_definition():
    from dochan.pdf import notes
    from dochan.pdf.content import Fragment

    fragments = [Fragment(0, 500, 30, 12, 'body)', 5),
                 Fragment(0, 100, 30, 12, '1) footer', 5, order=1)]
    with patch.object(notes, 'assemble_lines', wraps=notes.assemble_lines) as assemble:
        assert notes.detect_notes(fragments, [], (0, 800), 1) == ([], set(), {}, 1)
    assert assemble.call_count == 0


def test_note_size_upper_bound_keeps_body_rounding_boundary():
    from dochan.pdf import notes
    from dochan.pdf.content import Fragment

    fragments = [Fragment(0, 500, 30, 10.0006, 'body', 5),
                 Fragment(0, 100, 30, 9.0007, '1) footer', 5, order=1)]
    with patch.object(notes, 'assemble_lines', wraps=notes.assemble_lines) as assemble:
        notes.detect_notes(fragments, [], (0, 800), 1)
    # 9.0007 < round(10.0006, 3) * .9, although it exceeds 10.0006 * .9.
    assert assemble.call_count == 1
