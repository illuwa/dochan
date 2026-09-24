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
    data = lambda page=None: [_cell("x", 1, 0, page=page), _cell("y", 1, 1, page=page)]  # noqa: E731
    prev = Table(rows=[[_cell(" Head  one ", 0, 0), _cell("B", 0, 1)], data()])
    same = Table(rows=[[_cell("Head one", 0, 0, page=2), _cell("B", 0, 1, page=2)], data(2)])
    different_text = Table(rows=[[_cell("Other", 0, 0), _cell("B", 0, 1)], data()])
    different_span = Table(rows=[[_cell("Head one", 0, 0, col_span=2),
                                 _cell("B", 0, 1)], data()])
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


def _rows(*texts_rows):
    from dochan.model.table import Cell
    from dochan.model.document import Paragraph, TextRun

    rows = []
    for r, texts in enumerate(texts_rows):
        rows.append([Cell(paragraphs=[Paragraph(runs=[TextRun(text=t)])] if t else [], row=r, col=c)
                     for c, t in enumerate(texts)])
    return rows


def test_multi_row_repeated_header_is_dropped_whole():
    from dochan.model.table import Table
    from dochan.pdf.pagination import merge_continued, repeated_header_rows

    prev = Table(rows=_rows(("H", "Top"), ("", "Sub"), ("a", "b")))
    prev.rows[0][0].row_span = 2
    prev.rows[1][0].row_span = prev.rows[1][0].col_span = 0
    nxt = Table(rows=_rows(("H", "Top"), ("", "Sub"), ("c", "d")))
    nxt.rows[0][0].row_span = 2
    nxt.rows[1][0].row_span = nxt.rows[1][0].col_span = 0
    assert repeated_header_rows(prev, nxt) == 2
    merge_continued(prev, nxt, 2)
    assert [[c.text for c in row] for row in prev.rows] == [["H", "Top"], ["", "Sub"], ["a", "b"], ["c", "d"]]
    assert [c.row for c in prev.rows[-1]] == [3, 3]


def test_empty_first_rows_are_not_a_repeated_header():
    from dochan.model.table import Table
    from dochan.pdf.pagination import repeated_header_rows

    prev = Table(rows=_rows(("", ""), ("a", "b")))
    nxt = Table(rows=_rows(("", ""), ("c", "d")))
    assert repeated_header_rows(prev, nxt) == 0


def test_header_only_next_table_is_not_a_repeat():
    from dochan.model.table import Table
    from dochan.pdf.pagination import repeated_header_rows

    prev = Table(rows=_rows(("H", "T"), ("a", "b")))
    nxt = Table(rows=_rows(("H", "T")))
    assert repeated_header_rows(prev, nxt) == 0


def test_continues_requires_the_gap_below_the_tail_to_be_smaller_than_the_next_row():
    from dochan.model.table import Table
    from dochan.pdf.pagination import HeadInfo, TailInfo, continues
    from dochan.pdf.tables import TableCandidate

    def cand(ys):
        return TableCandidate(Table(rows=_rows(("a", "b"), ("c", "d"))), (0, ys[-1], 100, ys[0]), set(), 0,
                              xs=(0.0, 50.0, 100.0), ys=tuple(ys))

    head = HeadInfo(cand((140.0, 110.0, 80.0)), starts_top=True)  # 첫 행 높이 30
    assert continues(TailInfo(cand((180.0, 150.0, 120.0)), True, gap_below=20.0, page_height=200.0), head)
    assert not continues(TailInfo(cand((180.0, 150.0, 120.0)), True, gap_below=60.0, page_height=200.0), head)
    # 페이지 높이의 12% 까지는 행 높이와 무관하게 허용
    assert continues(TailInfo(cand((180.0, 150.0, 120.0)), True, gap_below=90.0, page_height=842.0), head)


def test_two_row_header_using_only_col_span_is_dropped_whole():
    from dochan.model.table import Table
    from dochan.pdf.pagination import repeated_header_rows

    def header_table(data_row):
        table = Table(rows=_rows(("점수", "", "등급", ""), ("국어", "영어", "A", "B"), data_row))
        table.rows[0][0].col_span = table.rows[0][2].col_span = 2
        table.rows[0][1].row_span = table.rows[0][1].col_span = 0
        table.rows[0][3].row_span = table.rows[0][3].col_span = 0
        return table

    prev = header_table(("90", "80", "a", "b"))
    nxt = header_table(("70", "60", "c", "d"))
    assert repeated_header_rows(prev, nxt) == 2


def test_partially_repeated_row_span_header_is_not_dropped():
    from dochan.model.table import Table
    from dochan.pdf.pagination import repeated_header_rows

    prev = Table(rows=_rows(("H", "Top"), ("", "Sub"), ("a", "b")))
    prev.rows[0][0].row_span = 2
    nxt = Table(rows=_rows(("H", "Top"), ("x", "y"), ("c", "d")))
    nxt.rows[0][0].row_span = 2
    assert repeated_header_rows(prev, nxt) == 0


def test_identical_first_data_row_is_not_treated_as_header():
    # 두 페이지의 첫 데이터 행이 우연히 같아도(Anonymous | 0) 제목이 아니다 (관문 리뷰 P1)
    from dochan.model.table import Table
    from dochan.pdf.pagination import repeated_header_rows

    prev = Table(rows=_rows(("Name", "Age"), ("Anonymous", "0"), ("x", "1")))
    nxt = Table(rows=_rows(("Name", "Age"), ("Anonymous", "0"), ("y", "2")))
    assert repeated_header_rows(prev, nxt) == 1


def test_empty_form_rows_after_a_header_are_not_absorbed():
    from dochan.model.table import Table
    from dochan.pdf.pagination import repeated_header_rows

    prev = Table(rows=_rows(("번호", "내용"), ("", ""), ("", ""), ("", "")))
    nxt = Table(rows=_rows(("번호", "내용"), ("", ""), ("", ""), ("", "x")))
    assert repeated_header_rows(prev, nxt) == 1
