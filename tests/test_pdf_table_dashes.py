"""1pt 미만의 실제 stroke 조각도 표 분할 괘선으로 보존한다."""
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf, _minimal_objects


def _dashed_pdf(vertical=True, irregular=False):
    content = [b'0 0 m 100 0 l 100 60 l 0 60 l h S']
    if vertical:
        content.append(b'0 30 m 100 30 l S 50 30 m 50 60 l S')
        for i in range(42):
            start = i * .72 + (i % 2 * .12 if irregular else 0)
            content.append(('50 %.2f m 50 %.2f l S' % (start, start + .36)).encode())
    else:
        content.append(b'50 0 m 50 60 l S 0 30 m 50 30 l S')
        content.extend(('%.2f 30 m %.2f 30 l S' % (50 + i * .72, 50 + i * .72 + .36)).encode()
                       for i in range(69))
    for x, y, text in [(10, 40, 'a'), (60, 40, 'b'), (10, 10, 'c'), (60, 10, 'd')]:
        content.append(('BT /F1 10 Tf %d %d Td (%s) Tj ET' % (x, y, text)).encode())
    return _build_pdf(_minimal_objects(b'\n'.join(content)))


def test_subpoint_vertical_dash_pdf_preserves_four_cells(tmp_path):
    source = tmp_path / 'vertical-dashes.pdf'
    source.write_bytes(_dashed_pdf())
    doc = PDFReader().read(str(source))
    table, = doc.find_all('table')
    assert [[cell.text for cell in row] for row in table.rows] == [['a', 'b'], ['c', 'd']]
    assert all(cell.row_span == cell.col_span == 1 for row in table.rows for cell in row)


def test_subpoint_horizontal_dash_pdf_preserves_four_cells(tmp_path):
    source = tmp_path / 'horizontal-dashes.pdf'
    source.write_bytes(_dashed_pdf(vertical=False))
    doc = PDFReader().read(str(source))
    table, = doc.find_all('table')
    assert [[cell.text for cell in row] for row in table.rows] == [['a', 'b'], ['c', 'd']]


def test_irregular_short_strokes_do_not_split_existing_merged_cell(tmp_path):
    source = tmp_path / 'irregular-short-strokes.pdf'
    source.write_bytes(_dashed_pdf(irregular=True))
    doc = PDFReader().read(str(source))
    table, = doc.find_all('table')
    assert table.rows[1][0].col_span == 2
    assert table.rows[1][0].text == 'c d'


def test_overlapping_short_and_long_rules_do_not_double_count_coverage(tmp_path):
    content = [b'0 0 m 100 0 l 100 60 l 0 60 l h S',
               b'0 30 m 100 30 l S 50 30 m 50 60 l S 50 0 m 50 8 l S',
               b'BT /F1 10 Tf 10 10 Td (left) Tj 50 0 Td (right) Tj ET']
    content.extend(('50 %.2f m 50 %.2f l S' % (i * .72, i * .72 + .36)).encode()
                   for i in range(11))
    source = tmp_path / 'overlapping-dash-support.pdf'
    source.write_bytes(_build_pdf(_minimal_objects(b'\n'.join(content))))
    doc = PDFReader().read(str(source))
    table, = doc.find_all('table')
    assert table.rows[1][0].col_span == 2
    assert table.rows[1][0].text == 'left right'


def test_zero_length_and_subpoint_diagonal_are_not_table_rules():
    content = ContentTextExtractor({}).extract_page(
        b'0 0 m 0 0 l S 1 1 m 1.36 1.36 l S 2 2 m 2 2.36 l S')
    assert not content.segments
    assert len(content.short_segments) == 1
    assert content.short_segments[0].y1 - content.short_segments[0].y0 > 0


def test_subpoint_strokes_keep_segment_budget(monkeypatch):
    from dochan.pdf import paths

    monkeypatch.setattr(paths, 'MAX_SEGMENTS', 4)
    content = ContentTextExtractor({}).extract_page(
        b' '.join(b'0 0 m 0 .36 l S' for _ in range(10)) + b' 0 0 m 100 0 l S')
    assert len(content.segments) == 1
    assert not content.short_segments
    assert not content.warnings


def test_subpoint_strokes_cannot_create_new_table_axes(tmp_path):
    content = b'0 0 m 100 0 l 100 60 l 0 60 l h S BT /F1 10 Tf 10 40 Td (text) Tj ET '
    content += b' '.join(('50 %.2f m 50 %.2f l S' % (i * .72, i * .72 + .36)).encode()
                         for i in range(84))
    source = tmp_path / 'no-established-divider.pdf'
    source.write_bytes(_build_pdf(_minimal_objects(content)))
    doc = PDFReader().read(str(source))
    table, = doc.find_all('table')
    assert (table.row_count, table.col_count) == (1, 1)


def test_short_strokes_do_not_spend_long_path_edge_budget(monkeypatch):
    from dochan.pdf import paths

    monkeypatch.setattr(paths, 'MAX_SEGMENTS', 4)
    content = ContentTextExtractor({}).extract_page(
        b'0 0 m ' + b'0 .36 l 0 0 l ' * 5 + b'100 0 l S')
    assert len(content.segments) == 1
    assert not content.short_segments
    assert not content.warnings
