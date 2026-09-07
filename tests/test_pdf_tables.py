"""PDF 괘선 표 복원과 문단 병합 회귀 테스트."""
import pytest

from dochan.pdf.content import ContentTextExtractor, Fragment
from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf, _minimal_objects


def _grid(cols=2, rows=2, omit=()):
    from dochan.pdf.content import Segment

    segments = []
    for r in range(rows + 1):
        for c in range(cols):
            if ('h', r, c) not in omit:
                segments.append(Segment(c * 50, (rows - r) * 30,
                                        (c + 1) * 50, (rows - r) * 30))
    for c in range(cols + 1):
        for r in range(rows):
            if ('v', r, c) not in omit:
                segments.append(Segment(c * 50, (rows - r - 1) * 30,
                                        c * 50, (rows - r) * 30))
    return segments


def _frag(text, x, y, order=0, width=10):
    return Fragment(x, y, width, 10, text, 5, order=order)


def test_full_grid_text_top_to_bottom_and_provenance():
    from dochan.pdf.tables import build_tables

    frags = [_frag(t, x, y, n) for n, (t, x, y) in enumerate(
        [('a', 10, 40), ('b', 60, 40), ('c', 10, 10), ('d', 60, 10)])]
    candidate, = build_tables(_grid(), frags, page_number=3)
    assert [[c.text for c in row] for row in candidate.table.rows] == [['a', 'b'], ['c', 'd']]
    assert candidate.fragment_orders == {0, 1, 2, 3}
    assert candidate.anchor_order == 0
    cell = candidate.table.rows[0][0]
    assert cell.provenance.page == cell.paragraphs[0].provenance.page == 3
    assert cell.provenance.source_format == 'pdf'


def test_horizontal_merged_cell_has_full_grid_placeholders():
    from dochan.pdf.tables import build_tables

    candidate, = build_tables(_grid(3, omit=(('v', 0, 1), ('v', 0, 2))),
                              [_frag('merged', 65, 40, width=40)])
    top = candidate.table.rows[0]
    assert top[0].col_span == 3
    assert top[0].text == 'merged'
    assert all(c.is_merged_away for c in top[1:])
    assert all(len(row) == 3 for row in candidate.table.rows)


def test_vertical_merge_and_l_shape_row_fallback():
    from dochan.pdf.tables import build_tables

    vertical, = build_tables(_grid(omit=(('h', 1, 0),)), [])
    assert vertical.table.rows[0][0].row_span == 2
    assert vertical.table.rows[1][0].is_merged_away
    shape, = build_tables(_grid(omit=(('h', 1, 0), ('v', 0, 1))), [])
    assert shape.table.rows[0][0].col_span == 2
    assert shape.table.rows[0][0].row_span == 1
    assert not shape.table.rows[1][0].is_merged_away


def test_jitter_and_small_gaps_snap_into_one_grid():
    from dochan.pdf.content import Segment
    from dochan.pdf.tables import build_tables

    lines = _grid()
    lines[0] = Segment(0.3, 60.3, 49.5, 60.3)
    candidate, = build_tables(lines, [])
    assert (candidate.table.row_count, candidate.table.col_count) == (2, 2)


def test_small_empty_box_dropped_but_empty_form_kept():
    from dochan.pdf.tables import build_tables

    assert build_tables(_grid(1, 1), []) == []
    assert len(build_tables(_grid(), [])) == 1


def test_grid_page_and_document_budgets_warn_and_skip():
    from dochan.pdf.tables import build_tables, TableBudget

    warnings = []
    assert build_tables(_grid(224, 224), [], warnings=warnings) == []
    assert len(warnings) == 1
    budget = TableBudget(remaining=4)
    assert len(build_tables(_grid(), [], budget=budget)) == 1
    assert build_tables(_grid(), [], budget=budget, warnings=warnings) == []
    assert any('문서' in w for w in warnings)


@pytest.mark.parametrize('first,second,expected', [
    ('대한민국', '국민이다', '대한민국국민이다'),
    ('대한민국', '제2조 목적', '대한민국\n제2조 목적'),
    ('hello world', 'again', 'hello world again'),
])
def test_wrap_merging(first, second, expected):
    from dochan.pdf.layout import merge_lines

    lines = ContentTextExtractor()._assemble_lines([
        _frag(first, 10, 100, 0, width=90), _frag(second, 10, 86, 1, width=40)])
    assert '\n'.join(p.text for p in merge_lines(lines)) == expected


def test_cell_lines_sort_by_position_and_keep_wrapped_runs():
    from dochan.pdf.tables import build_tables

    candidate, = build_tables(_grid(1, 1), [
        _frag('again', 5, 3, 0, 20), _frag('hello', 5, 17, 1, 40)])
    assert candidate.table.rows[0][0].text == 'hello again'


def _read(tmp_path, content, objects=None):
    path = tmp_path / 'table.pdf'
    path.write_bytes(_build_pdf(objects or _minimal_objects(content)))
    return PDFReader().read(str(path))


def _table_content():
    return (b'0 0 100 60 re S 50 0 m 50 60 l S 0 30 m 100 30 l S '
            b'BT /F1 10 Tf 10 40 Td (a) Tj 50 0 Td (b) Tj '
            b'-50 -30 Td (c) Tj 50 0 Td (d) Tj ET ')


def test_reader_stream_order_markdown_and_provenance(tmp_path):
    from dochan.output.markdown import to_markdown
    from dochan.model.table import Table

    doc = _read(tmp_path, b'BT /F1 10 Tf 0 100 Td (before) Tj ET '
                + _table_content() + b'BT /F1 10 Tf 0 -30 Td (after) Tj ET')
    before, table, after = doc.sections[0].elements
    assert (before.text, after.text) == ('before', 'after')
    assert isinstance(table, Table)
    assert doc.find_all('table') == [table]
    assert '| a | b |' in to_markdown(doc)
    assert table.rows[0][0].provenance.page == 1
    assert not doc.errors


def test_reader_warns_on_segment_overflow(tmp_path):
    doc = _read(tmp_path, b'0 0 m 10 0 l S ' * 20001 + b'BT (alive) Tj ET')
    assert doc.sections[0].elements[0].text == 'alive'
    assert sum('선분' in e for e in doc.errors) == 1


def test_reader_graphics_state_spans_content_parts(tmp_path):
    objects = _minimal_objects(b'q 1 0 0 1 20 100 cm BT /F1 10 Tf (left) Tj')
    objects[3] = objects[3].replace('/Contents 5 0 R', '/Contents [5 0 R 6 0 R]')
    part = b'40 0 Td (right) Tj ET Q'
    objects[6] = b'<< /Length %d >>\nstream\n%s\nendstream' % (len(part), part)
    doc = _read(tmp_path, b'', objects)
    assert [p.text for p in doc.sections[0].elements] == ['left right']


@pytest.mark.parametrize('encoding', ['/MacRomanEncoding',
                                     '<< /BaseEncoding /MacRomanEncoding >>'])
def test_macroman_quotes(tmp_path, encoding):
    objects = _minimal_objects(b'BT /F1 10 Tf <D261D3> Tj ET')
    objects[4] = '<< /Type /Font /Subtype /Type1 /Encoding %s >>' % encoding
    doc = _read(tmp_path, b'', objects)
    assert doc.sections[0].elements[0].text == '“a”'


def test_detached_nested_table_keeps_only_outer_and_consumes_text():
    from dochan.pdf.tables import build_tables
    from dochan.pdf.content import Segment

    segments = _grid(1, 1) + [Segment(10, 5, 40, 5), Segment(10, 25, 40, 25),
                             Segment(10, 5, 10, 25), Segment(40, 5, 40, 25)]
    outer, = build_tables(segments, [_frag('inner', 15, 10, 7)])
    assert (outer.table.row_count, outer.table.col_count) == (1, 1)
    assert outer.table.rows[0][0].text == 'inner'
    assert outer.fragment_orders == {7}


def test_multiple_tables_share_page_budget(monkeypatch):
    from dochan.pdf import tables
    from dochan.pdf.content import Segment

    monkeypatch.setattr(tables, 'MAX_PAGE_CELLS', 4)
    shifted = [Segment(s.x0 + 200, s.y0, s.x1 + 200, s.y1) for s in _grid()]
    warnings = []
    assert len(tables.build_tables(_grid() + shifted, [], warnings=warnings)) == 1
    assert len(warnings) == 1


def test_component_line_limit_warns_before_allocating_grid():
    from dochan.pdf.tables import build_tables
    from dochan.pdf.content import Segment

    segments = [Segment(0, y * 3, 20, y * 3) for y in range(2001)]
    segments += [Segment(x, 0, x, 6000) for x in (0, 20)]
    warnings = []
    assert build_tables(segments, [], warnings=warnings) == []
    assert len(warnings) == 1 and '선 수' in warnings[0]


def test_reader_grid_limit_warns_without_losing_body(tmp_path, monkeypatch):
    from dochan.pdf import tables

    monkeypatch.setattr(tables, 'MAX_PAGE_CELLS', 3)
    doc = _read(tmp_path, _table_content())
    assert not doc.find_all('table')
    assert 'a b' in doc.sections[0].elements[0].text
    assert sum('셀 수' in e for e in doc.errors) == 1


def test_empty_form_anchor_follows_stream_before_lower_body(tmp_path):
    from dochan.model.table import Table

    doc = _read(tmp_path, b'BT /F1 10 Tf 0 100 Td (before) Tj ET '
                b'0 0 100 60 re S 50 0 m 50 60 l S 0 30 m 100 30 l S '
                b'BT /F1 10 Tf 0 -30 Td (after) Tj ET')
    before, table, after = doc.sections[0].elements
    assert (before.text, after.text) == ('before', 'after')
    assert isinstance(table, Table)


def test_heading_median_excludes_table_fonts(tmp_path):
    body = (b'BT /F1 15 Tf 0 100 Td (Title) Tj ET '
            b'BT /F1 10 Tf 0 70 Td (body) Tj ET ')
    doc = _read(tmp_path, body + _table_content().replace(b'/F1 10 Tf', b'/F1 3 Tf')
                + b'BT /F1 10 Tf 0 -30 Td (tail) Tj ET')
    paragraphs = [p for p in doc.sections[0].elements if hasattr(p, 'text')]
    assert [p.heading_level for p in paragraphs] == [1, 0, 0]


def test_table_failure_warns_and_keeps_body(tmp_path, monkeypatch):
    from dochan.pdf import reader

    def broken(*args, **kwargs):
        raise ValueError('damaged rules')

    monkeypatch.setattr(reader, 'build_tables', broken)
    doc = _read(tmp_path, b'BT /F1 10 Tf (preserved) Tj ET')
    assert doc.sections[0].elements[0].text == 'preserved'
    assert any('표' in e for e in doc.errors)


def test_zero_size_table_text_is_not_duplicated_in_body(tmp_path):
    doc = _read(tmp_path, _table_content().replace(b'/F1 10 Tf ', b''))
    assert len(doc.find_all('table')) == 1
    assert len(doc.sections[0].elements) == 1


def test_wrapped_paragraph_runs_use_exactly_one_separator():
    from dochan.pdf.layout import merge_lines

    lines = ContentTextExtractor()._assemble_lines([
        _frag('hello ', 10, 100, 0, 90), _frag(' world', 10, 86, 1, 40)])
    block, = merge_lines(lines)
    assert block.paragraph(1).text == block.text == 'hello world'


def test_open_sided_table_extends_grid_to_rule_extents():
    # 바깥 세로 괘선이 없는 표(개정 이력 표 등): 가로 괘선이 뻗은 범위까지 열을 만든다
    from dochan.pdf.tables import build_tables

    segments = _grid(3, omit=(('v', 0, 0), ('v', 1, 0), ('v', 0, 3), ('v', 1, 3)))
    frags = [_frag(t, x, y, n) for n, (t, x, y) in enumerate(
        [('연번', 10, 40), ('내용', 60, 40), ('일자', 110, 40),
         ('1', 10, 10), ('제정', 60, 10), ('2007', 110, 10)])]
    candidate, = build_tables(segments, frags)
    assert candidate.table.col_count == 3
    assert [[c.text for c in row] for row in candidate.table.rows] == [
        ['연번', '내용', '일자'], ['1', '제정', '2007']]
    assert candidate.fragment_orders == set(range(6))


def test_number_split_across_lines_is_not_a_block_marker():
    # "[개정 202" / "3.12.19.]" 처럼 줄 끝에서 잘린 숫자는 항목 표식이 아니다
    from dochan.pdf.layout import merge_lines

    ex = ContentTextExtractor()
    lines = ex._assemble_lines([
        _frag('의결한다.[개정 202', 0, 100, 0, width=200),
        _frag('3.12.19.] 다음', 0, 88, 1, width=60),
    ])
    blocks = merge_lines(lines)
    assert [b.text for b in blocks] == ['의결한다.[개정 2023.12.19.] 다음']
    lines = ex._assemble_lines([
        _frag('앞 문단이 꽉 찬 줄이다 끝', 0, 100, 0, width=200),
        _frag('2. 새 항목', 0, 88, 1, width=60),
    ])
    assert [b.text for b in merge_lines(lines)] == ['앞 문단이 꽉 찬 줄이다 끝', '2. 새 항목']


def test_repeated_content_references_are_capped_by_page_byte_budget(tmp_path, monkeypatch):
    # /Contents 배열이 같은 스트림을 수백 번 참조하면 결합 시 메모리가 곱절로 는다 — 합계 상한
    import dochan.pdf.reader as reader_mod

    monkeypatch.setattr(reader_mod, 'MAX_PAGE_CONTENT_BYTES', 120)
    content = b"BT /F1 12 Tf 72 720 Td (part) Tj ET"
    objects = _minimal_objects(content)
    objects[3] = "<< /Type /Page /Parent 2 0 R /Contents [" + " ".join(["5 0 R"] * 40) + "] >>"
    path = tmp_path / "repeat.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert any('콘텐츠 합계' in e for e in doc.errors)
    assert 'part' in doc.sections[0].elements[0].text


def test_intersection_work_budget_skips_dense_rulings(monkeypatch):
    import dochan.pdf.tables as tables_mod
    from dochan.pdf.tables import build_tables

    monkeypatch.setattr(tables_mod, 'MAX_INTERSECTION_CHECKS', 10)
    warnings = []
    assert build_tables(_grid(5, 5), [], warnings=warnings) == []
    assert any('교차' in w for w in warnings)


def test_rotated_180_text_keeps_writing_direction():
    from test_pdf_layout import _mono

    content = b"-1 0 0 -1 200 700 cm BT /F1 10 Tf (a) Tj (b) Tj (c) Tj ET"
    ex = ContentTextExtractor.from_fonts({"F1": _mono()})
    assert ex.extract(content) == ["abc"]


def test_filled_polygon_rectangle_is_not_a_ruling_but_thin_one_is():
    ex = ContentTextExtractor()
    big = ex.extract_page(b"0 0 m 100 0 l 100 60 l 0 60 l h f")
    assert big.segments == []
    thin = ex.extract_page(b"0 0 m 100 0 l 100 1 l 0 1 l h f")
    assert len(thin.segments) == 2  # 긴 변만
    stroked = ex.extract_page(b"0 0 m 100 0 l 100 60 l 0 60 l h S")
    assert len(stroked.segments) == 4


def test_bowed_curves_do_not_become_rulings():
    ex = ContentTextExtractor()
    bowed = ex.extract_page(b"0 0 m 0 40 100 40 100 0 c S")
    assert bowed.segments == []
    almost_straight = ex.extract_page(b"0 0 m 30 0.2 70 0.2 100 0 c S")
    assert len(almost_straight.segments) == 1


def test_unpainted_subpaths_are_bounded_and_warn():
    # 칠하기 연산자 없이 m/l 만 반복하는 스트림이 메모리를 선형으로 먹지 않아야 한다 (Opus 감수 Critical)
    from dochan.pdf.paths import MAX_SEGMENTS, PathCollector

    collector = PathCollector()
    identity = (1, 0, 0, 1, 0, 0)
    for i in range(MAX_SEGMENTS + 50):
        collector.operate(b"m", [i, i], identity)
        collector.operate(b"l", [i + 5, i], identity)
    assert len(collector._groups) == MAX_SEGMENTS
    assert collector.warnings and '한도' in collector.warnings[0]


def test_vertical_rule_overshoot_does_not_add_a_row():
    # 세로 괘선 하나가 위로 튀어나와도 가짜 첫 행이 생겨 본문을 흡수하면 안 된다 (Opus 감수 Major)
    from dochan.pdf.content import Segment
    from dochan.pdf.tables import build_tables

    segments = _grid() + [Segment(0, 60, 0, 90)]
    frags = [_frag('바깥본문', 10, 75, 0), _frag('a', 10, 40, 1), _frag('b', 60, 40, 2),
             _frag('c', 10, 10, 3), _frag('d', 60, 10, 4)]
    candidate, = build_tables(segments, frags)
    assert candidate.table.row_count == 2
    assert 0 not in candidate.fragment_orders


def test_single_outlier_horizontal_rule_does_not_add_a_column():
    # 가로 괘선 하나만 왼쪽으로 길어도 열을 보태지 않는다 — 두 개 이상이 같은 범위에 닿아야 한다
    from dochan.pdf.content import Segment
    from dochan.pdf.tables import build_tables

    segments = [s for s in _grid() if not (s.y0 == 60 and s.x0 == 0)] + [Segment(-30, 60, 50, 60)]
    candidate, = build_tables(segments, [_frag('a', 10, 40, 0)])
    assert candidate.table.col_count == 2


def test_thin_filled_rectangle_emits_only_its_long_edges():
    ex = ContentTextExtractor()
    thin = ex.extract_page(b"0 40 20 1 re f")
    assert len(thin.segments) == 2
    assert all(s.x1 - s.x0 == 20 for s in thin.segments)


def test_wrap_merge_compares_adjacent_fragment_sizes_not_line_max():
    # 본문(14pt) 줄 끝의 작은 각주형 주석([개정 202, 9pt)이 다음 줄(3.12.19.], 9pt)과 이어져야 한다.
    # 줄의 최대 크기(14)로 비교하면 병합이 막힌다 — 인접한 조각끼리 비교한다.
    from dochan.pdf.layout import merge_lines

    frags = [Fragment(70, 565, 400, 14.0, '소집하여야 한다.', 5, order=0),
             Fragment(470, 565, 60, 9.0, '[개정 202', 4, order=1),
             Fragment(70, 549, 36, 9.0, '3.12.19.]', 4, order=2)]
    lines = ContentTextExtractor()._assemble_lines(frags)
    assert [b.text for b in merge_lines(lines)] == ['소집하여야 한다.[개정 2023.12.19.]']
    # 큰 제목 다음의 본문은 여전히 새 문단
    frags = [Fragment(70, 700, 480, 20.0, '제1장 총칙', 8, order=0),
             Fragment(70, 680, 100, 12.0, '이 규정은', 5, order=1)]
    lines = ContentTextExtractor()._assemble_lines(frags)
    assert [b.text for b in merge_lines(lines)] == ['제1장 총칙', '이 규정은']
