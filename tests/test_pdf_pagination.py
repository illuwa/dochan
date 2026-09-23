"""PDF 페이지 사이 표 병합 조건과 행 연결 검증."""
from dochan.conversion import Provenance
from dochan.model.document import Paragraph, TextRun
from dochan.model.table import Cell, Table
from dochan.pdf.content import Fragment
from dochan.pdf.objects import PDFRef
from dochan.pdf.pagination import (HeadInfo, TailInfo, body_between, continues,
                                   header_repeated, merge_continued, page_bounds,
                                   same_columns)
from dochan.pdf.structure import PDFFile
from dochan.pdf.tables import TableCandidate, build_tables
from test_pdf_structure import _build_pdf, _minimal_objects
from test_pdf_tables import _frag, _grid


def _cell(text, row, col, page=1, row_span=1, col_span=1):
    para = Paragraph(runs=[TextRun(text=text)]) if text else None
    return Cell(paragraphs=[para] if para else [], row=row, col=col,
                row_span=row_span, col_span=col_span,
                provenance=Provenance(source_format="pdf", page=page))


def _candidate(rows, xs=(0.0, 50.0, 100.0)):
    return TableCandidate(Table(rows=rows), (0, 0, 100, 100), set(), 0, xs=xs)


def test_build_tables_exposes_top_level_grid_boundaries():
    candidate, = build_tables(_grid(), [_frag("a", 10, 40)])
    assert candidate.xs == (0.0, 50.0, 100.0)
    assert candidate.ys == (60.0, 30.0, 0.0)


def test_same_columns_and_continuation_require_matching_edges():
    assert same_columns((0, 50, 100), (1, 49, 100.5))
    assert not same_columns((0, 50, 100), (0, 50, 75, 100))
    assert not same_columns((0, 50, 100), (0, 53, 100))
    assert not same_columns((0,), (0,))
    prev = _candidate([[_cell("a", 0, 0)]])
    head = _candidate([[_cell("b", 0, 0)]])
    assert continues(TailInfo(prev, True), HeadInfo(head, True))
    assert not continues(TailInfo(prev, False), HeadInfo(head, True))
    assert not continues(TailInfo(prev, True), HeadInfo(head, False))


def test_body_between_ignores_consumed_and_blank_fragments():
    fragments = [Fragment(0, 80, 10, 10, "table", 5, order=1),
                 Fragment(0, 70, 10, 10, "  ", 5, order=2),
                 Fragment(0, 50, 10, 10, "body", 5, order=3)]
    assert not body_between(fragments, {1}, 60, 90)
    assert body_between(fragments, {1}, 40, 60)
    assert not body_between(fragments, {1, 3}, 40, 90)


def test_repeated_header_checks_text_and_span_pattern():
    prev = Table(rows=[[_cell(" Head  one ", 0, 0), _cell("B", 0, 1)]])
    same = Table(rows=[[_cell("Head one", 0, 0, page=2), _cell("B", 0, 1, page=2)]])
    different_text = Table(rows=[[_cell("Other", 0, 0), _cell("B", 0, 1)]])
    different_span = Table(rows=[[_cell("Head one", 0, 0, col_span=2),
                                 _cell("B", 0, 1)]])
    assert header_repeated(prev, same)
    assert not header_repeated(prev, different_text)
    assert not header_repeated(prev, different_span)


def test_merge_continued_offsets_all_cells_and_preserves_provenance():
    prev = Table(rows=[[_cell("A", 0, 0), _cell("B", 0, 1)]])
    next_table = Table(rows=[[_cell("A", 0, 0, page=2), _cell("B", 0, 1, page=2)],
                             [_cell("C", 1, 0, page=2, col_span=2),
                              _cell("", 1, 1, page=2, row_span=0, col_span=0)]])
    merge_continued(prev, next_table, True)
    assert [[c.text for c in row] for row in prev.rows] == [["A", "B"], ["C", ""]]
    assert [c.row for c in prev.rows[1]] == [1, 1]
    assert [(c.row_span, c.col_span) for c in prev.rows[1]] == [(1, 2), (0, 0)]
    assert all(c.provenance.page == 2 for c in prev.rows[1])
    separate = Table(rows=[[_cell("D", 0, 0, page=3)]])
    merge_continued(prev, separate, False)
    assert prev.rows[2][0].row == 2
    assert prev.rows[2][0].provenance.page == 3


def test_page_bounds_direct_inherited_malformed_and_inverted():
    objects = _minimal_objects()
    objects[2] = "<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 10 595 900] >>"
    pdf = PDFFile(_build_pdf(objects))
    page, = [entry[0] for entry in pdf.pages()]
    assert page_bounds(pdf, page) == (10.0, 900.0)
    page["MediaBox"] = [0, 20, 600, 700]
    assert page_bounds(pdf, page) == (20.0, 700.0)
    page["MediaBox"] = [0, "bad", 600, 700]
    assert page_bounds(pdf, page) == (0.0, 842.0)
    page["MediaBox"] = [0, 842, 600, 0]
    assert page_bounds(pdf, page) == (0.0, 842.0)
    page["MediaBox"] = [0, 10, 600]
    assert page_bounds(pdf, page) == (0.0, 842.0)
    assert pdf.resolve(PDFRef(2, 0))["MediaBox"] == [0, 10, 595, 900]
