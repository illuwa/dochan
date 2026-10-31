"""Unruled numeric rows inside a ruled table remain separate records."""
import pytest

from dochan.pdf.reader import PDFReader
from dochan.output.plain_text import to_plain_text
from test_pdf_structure import _build_pdf, _minimal_objects


def _read(tmp_path, rows, offsets=None, cols=4, open_sides=False):
    content = (b'0 0 m 240 0 l S 0 90 m 240 90 l S ' if open_sides
               else b'0 0 240 90 re S ')
    for c in range(1, cols):
        content += b'%d 0 m %d 90 l S ' % (c * 60, c * 60)
    for r, row in enumerate(rows):
        for c, label in enumerate(row):
            y = 70 - r * 20 + (offsets.get((r, c), 0) if offsets else 0)
            content += b'BT /F1 10 Tf %d %d Td (%s) Tj ET ' % (
                c * 60 + 8, y, label.encode())
    path = tmp_path / 'numeric.pdf'
    path.write_bytes(_build_pdf(_minimal_objects(content)))
    return PDFReader().read(str(path))


def test_aligned_numeric_columns_supply_missing_row_rules(tmp_path):
    rows = [('North', '123', '456', '789'), ('South', '234', '567', '890'),
            ('West', '345', '678', '901')]
    doc = _read(tmp_path, rows)
    table, = doc.find_all('table')
    assert [[c.text for c in row] for row in table.rows] == [list(row) for row in rows]
    text = to_plain_text(doc)
    assert text.index('South') > text.index('789')


@pytest.mark.parametrize('rows,offsets', [
    ([('Label', 'long prose', 'other prose', 'last prose')] * 3, None),
    ([('Label', '123', 'words', 'text')] * 3, None),
    ([('Label', '123', '456', '789')] * 3, {(1, 2): 7}),
    ([('Label', '123', '456', '789')], None),
])
def test_prose_sparse_or_unaligned_columns_are_not_split(tmp_path, rows, offsets):
    table, = _read(tmp_path, rows, offsets).find_all('table')
    assert table.row_count == 1


def test_numeric_rows_with_open_outer_edges(tmp_path):
    rows = [('North', '123', '456', '789'), ('South', '234', '567', '890'),
            ('West', '345', '678', '901')]
    table, = _read(tmp_path, rows, open_sides=True).find_all('table')
    assert [[c.text for c in row] for row in table.rows] == [list(row) for row in rows]
