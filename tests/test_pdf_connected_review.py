"""연결형 분리의 원자성·모호성·페이지 검사 비용 회귀를 검증한다."""
import pytest

from dochan.model.table import Table
from dochan.pdf import connected_tables, tables
from dochan.pdf.content import ContentTextExtractor, Fragment
from test_pdf_connected_tables import runs
from test_pdf_tables import _read


def _nested(table):
    return [block for row in table.rows for cell in row for block in cell.paragraphs
            if isinstance(block, Table)]


def test_dash_split_rejection_restores_all_child_rules(tmp_path):
    content = [b'0 0 200 200 re S 0 40 100 100 re S '
               b'0 90 m 100 90 l S 50 40 m 50 140 l S 50 0 m 50 20 l S']
    content.extend(('50 %.2f m 50 %.2f l S' % (i * .72, i * .72 + .36)).encode()
                   for i in range(278))
    content.append(b'BT /F1 10 Tf 10 115 Td (A) Tj 50 0 Td (B) Tj '
                   b'-50 -50 Td (C) Tj 50 0 Td (D) Tj ET')
    doc = _read(tmp_path, b' '.join(content))
    outer, = doc.sections[0].elements
    assert not _nested(outer)
    assert [cell.text for row in outer.rows for cell in row if cell.text] == list('ABCD')
    assert not doc.errors


def test_multiple_valid_connected_children_leave_component_unchanged(tmp_path):
    content = (b'0 0 400 200 re S 200 0 m 200 200 l S '
               b'0 40 80 80 re S 200 40 80 80 re S '
               b'BT /F1 10 Tf 20 60 Td (C1) Tj 200 0 Td (C2) Tj ET')
    hs, vs = runs(content)
    page = ContentTextExtractor().extract_page(content)
    assert connected_tables.split_connected(hs, vs, 1.5,
                                            tables._fragment_index(page.fragments)) == [(hs, vs)]
    doc = _read(tmp_path, content)
    outer, = doc.sections[0].elements
    assert not _nested(outer)
    text = ' '.join(cell.text for row in outer.rows for cell in row)
    assert text.count('C1') == text.count('C2') == 1


@pytest.mark.parametrize('content', [
    b'50 50 300 200 re S 70 230 60 20 re S 250 230 60 20 re S '
    b'BT /F1 10 Tf 80 236 Td (L1) Tj 180 0 Td (L2) Tj -200 -116 Td (body) Tj ET',
    b'50 50 300 200 re S 50 180 m 120 180 l S 80 130 30 50 re S '
    b'BT /F1 10 Tf 85 150 Td (dd) Tj 115 -50 Td (body) Tj ET',
    b'50 50 300 200 re S 150 250 m 150 150 l 250 150 l S 200 150 m 200 200 l S '
    b'BT /F1 10 Tf 160 200 Td (p) Tj 50 0 Td (q) Tj -150 -100 Td (body) Tj ET',
    b'0 0 200 200 re S 0 150 m 80 150 l S 30 100 30 50 re S '
    b'BT /F1 8 Tf 40 120 Td (p) Tj ET',
    b'0 0 200 200 re S 50 200 m 50 100 l 150 100 l S 150 100 m 150 150 l S '
    b'BT /F1 10 Tf 60 120 Td (p) Tj ET',
], ids=['two_boxes_on_one_edge', 'floating_support', 'open_partition',
        'support_shorter_than_half_cell', 'one_open_side'])
def test_connected_geometry_guards_keep_ambiguous_drawings_flat(tmp_path, content):
    doc = _read(tmp_path, content)
    assert doc.find_all('table')
    assert all(not _nested(table) for table in doc.find_all('table'))
    assert not doc.errors


def _rejected_boxes(count):
    content = ['0 0 300 %d re S' % (40 * count + 40)]
    for i in range(count):
        y = 40 * i + 20
        content.append('0 %d 100 20 re S 0 %d m 100 %d l S' % (y, y + 10, y + 10))
        content.append('BT /F1 4 Tf 10 %d Td (x) Tj ET' % (y + 2))
    return ContentTextExtractor().extract_page(' '.join(content).encode())


def test_rejected_children_do_not_rebuild_parent_grid(monkeypatch):
    page = _rejected_boxes(30)
    original = tables._make_grid
    parent_grids = []

    def measure(hs, vs, xs, ys, *args):
        if len(ys) > 4:
            parent_grids.append(len(ys))
        return original(hs, vs, xs, ys, *args)

    monkeypatch.setattr(tables, '_make_grid', measure)
    found = tables.build_tables(page.segments, page.fragments)
    assert len(found) == 1
    assert not _nested(found[0].table)
    assert len(parent_grids) == 1


def test_connected_page_budget_is_shared_between_components(monkeypatch):
    seen = []
    original = tables.split_connected

    def observe(*args, **kwargs):
        budget = kwargs.get('split_budget')
        seen.append(budget)
        return original(*args, **kwargs)

    monkeypatch.setattr(tables, 'split_connected', observe)
    page = ContentTextExtractor().extract_page(
        b'0 0 200 200 re S 0 40 100 100 re S '
        b'300 0 200 200 re S 300 40 100 100 re S '
        b'BT /F1 10 Tf 10 60 Td (a) Tj 300 0 Td (b) Tj ET')
    tables.build_tables(page.segments, page.fragments)
    assert len(seen) == 2
    assert seen[0] is not None and seen[0] is seen[1]


def test_oversize_component_skips_connected_graph_walk(monkeypatch):
    def forbidden(_adjacency):
        pytest.fail('unusable component must be rejected before graph traversal')

    monkeypatch.setattr(connected_tables, '_articulations', forbidden)
    # 각 축에 500개 이상의 좌표를 가진 단일 연결 나무다.
    from dochan.pdf.paths import Segment

    segments = []
    for i in range(250):
        x = y = 10 * i
        segments.extend([Segment(x, y, x + 10, y), Segment(x + 10, y, x + 10, y + 10),
                         Segment(x + 5, y - 3, x + 5, y),
                         Segment(x + 10, y + 5, x + 13, y + 5)])
    warnings = []
    assert tables.build_tables(segments, [Fragment(3, 50, 5, 8, 't', 3)],
                               warnings=warnings) == []
    assert any('셀 수 한도' in message for message in warnings)


def test_page_budget_exhaustion_keeps_later_component_flat(monkeypatch):
    monkeypatch.setattr(connected_tables, 'MAX_SPLIT_CHECKS', 100)
    page = ContentTextExtractor().extract_page(
        b'0 0 200 200 re S 0 40 100 100 re S '
        b'300 0 200 200 re S 300 40 100 100 re S '
        b'BT /F1 10 Tf 10 60 Td (a) Tj 300 0 Td (b) Tj ET')
    warnings = []
    found = tables.build_tables(page.segments, page.fragments, warnings=warnings)
    assert len(found) == 2
    assert len(_nested(found[0].table)) == 1
    assert not _nested(found[1].table)
    assert len(warnings) == 1 and '연결형 중첩 표 검사 한도' in warnings[0]
    assert 'b' in ' '.join(cell.text for row in found[1].table.rows for cell in row)


def test_grid_budget_covers_all_segment_visits(monkeypatch):
    hs = [(0, 0, 200), (100, 0, 200)]
    vs = [(0, 0, 100), (200, 0, 100)]
    vs.extend((100, y, y + 2) for y in range(0, 100, 4))
    xs, ys = [0, 100, 200], list(range(100, -1, -10))
    visits = []
    original = tables._covered

    def observe(parts, *args):
        visits.append(len(parts))
        return original(parts, *args)

    monkeypatch.setattr(tables, '_covered', observe)
    tables._make_grid(hs, vs, xs, ys, 1.5, None)
    assert sum(visits) == 250
    assert connected_tables._grid_cost(hs, vs, xs, ys) >= sum(visits) + 20
