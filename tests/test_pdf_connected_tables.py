"""한 변을 공유하는 내부 격자와 일반 병합 표의 구분이다."""
import pytest

from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.tables import _snap_runs, _fragment_index
from dochan.pdf.content import Fragment


def text_index():
    return _fragment_index([Fragment(10, 60, 20, 10, 'inside', 5)])


def runs(content):
    page = ContentTextExtractor().extract_page(content)
    hs = [(s.y0, s.x0, s.x1) for s in page.segments if s.y0 == s.y1]
    vs = [(s.x0, s.y0, s.y1) for s in page.segments if s.x0 == s.x1]
    return _snap_runs(hs, 1.5), _snap_runs(vs, 1.5)


def test_single_shared_edge_splits_closed_inset_grid():
    from dochan.pdf.connected_tables import split_connected

    hs, vs = runs(b'0 0 200 200 re S 0 40 100 100 re S '
                  b'0 90 m 100 90 l S 50 40 m 50 140 l S')
    groups = split_connected(hs, vs, 1.5, text_index())
    assert len(groups) == 2
    assert sorted((len(h), len(v)) for h, v in groups) == [(2, 2), (3, 3)]


def test_partial_dividers_and_corner_inset_remain_flat():
    from dochan.pdf.connected_tables import split_connected

    for content in (b'0 0 200 200 re S 0 100 m 200 100 l S '
                    b'100 0 m 100 100 l S',
                    b'0 0 200 200 re S 0 0 100 100 re S',
                    b'0 0 200 200 re S 0 100 m 100 100 l S'):
        hs, vs = runs(content)
        assert split_connected(hs, vs, 1.5, text_index()) == [(hs, vs)]


def test_connected_analysis_budget_falls_back():
    from dochan.pdf.connected_tables import split_connected

    hs, vs = runs(b'0 0 200 200 re S 0 40 100 100 re S')
    warnings = []
    assert split_connected(hs, vs, 1.5, text_index(), max_checks=1,
                           warnings=warnings) == [(hs, vs)]
    assert len(warnings) == 1 and warnings[0].startswith('WARN:')


def test_empty_drawing_and_rejected_one_text_cell_leave_grid_unchanged():
    from dochan.pdf.connected_tables import split_connected

    hs, vs = runs(b'0 0 200 200 re S 0 40 100 100 re S '
                  b'0 90 m 100 90 l S')
    assert split_connected(hs, vs, 1.5, _fragment_index([])) == [(hs, vs)]
    # 두 셀 중 하나만 채운 작은 후보는 기존 중첩 채택 기준에도 못 미친다.
    assert split_connected(hs, vs, 1.5, text_index()) == [(hs, vs)]


@pytest.mark.parametrize('matrix', [b'1 0 0 1 0 0', b'-1 0 0 1 200 0',
                                   b'0 1 -1 0 200 0', b'0 -1 1 0 0 200'])
def test_reader_shared_edge_preserves_nested_contract(tmp_path, matrix):
    from dochan.model.table import Table
    from dochan.output.markdown import to_markdown
    from test_pdf_tables import _read

    content = (b'q ' + matrix + b' cm 0 0 200 200 re S 0 40 100 100 re S '
               b'0 90 m 100 90 l S 50 40 m 50 140 l S '
               b'BT /F1 10 Tf 10 115 Td (A) Tj 50 0 Td (B) Tj '
               b'-50 -50 Td (C) Tj 50 0 Td (D) Tj ET Q')
    doc = _read(tmp_path, content)
    outer, = doc.sections[0].elements
    assert (outer.row_count, outer.col_count) == (1, 1)
    inner, = outer.rows[0][0].paragraphs
    assert isinstance(inner, Table)
    assert (inner.row_count, inner.col_count) == (2, 2)
    assert sorted(c.text for row in inner.rows for c in row) == ['A', 'B', 'C', 'D']
    assert all(outer.rows[0][0].text.count(t) == 1 for t in 'ABCD')
    markdown = to_markdown(doc)
    assert markdown.count(' / ') == 2 and markdown.count(' ; ') == 1
    assert all(c.provenance.page == 1 for row in inner.rows for c in row)
    assert not doc.errors


def test_connected_cells_share_document_budget():
    from dochan.pdf.tables import TableBudget, build_tables

    page = ContentTextExtractor().extract_page(
        b'0 0 200 200 re S 0 40 100 100 re S '
        b'0 90 m 100 90 l S 50 40 m 50 140 l S '
        b'BT /F1 10 Tf 10 60 Td (inside) Tj ET')
    budget = TableBudget(remaining=5)
    assert len(build_tables(page.segments, page.fragments, budget=budget)) == 1
    assert budget.remaining == 0
    warnings = []
    assert build_tables(page.segments, page.fragments, budget=TableBudget(remaining=4),
                        warnings=warnings) == []
    assert warnings


def test_connected_budget_fallback_is_atomic_with_other_components():
    from dochan.pdf.tables import TableBudget, build_tables

    page = ContentTextExtractor().extract_page(
        b'0 0 200 200 re S 0 40 100 100 re S '
        b'0 90 m 100 90 l S 50 40 m 50 140 l S '
        b'300 0 300 300 re S BT /F1 10 Tf 10 60 Td (inside) Tj '
        b'300 0 Td (other) Tj ET')
    found = build_tables(page.segments, page.fragments, budget=TableBudget(remaining=5))
    assert len(found) == 1
    assert found[0].table.rows[0][0].text == 'other'


def test_articulation_walk_handles_deep_graph_without_recursion():
    from dochan.pdf.connected_tables import _articulations

    graph = [set() for _ in range(2000)]
    for i in range(1999):
        graph[i].add(i + 1)
        graph[i + 1].add(i)
    assert _articulations(graph) == list(range(1, 1999))
    graph[0].add(1999)
    graph[1999].add(0)
    assert _articulations(graph) == []
