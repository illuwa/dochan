import struct
from types import SimpleNamespace

from dochan.model.document import Paragraph, TextRun
from dochan.model.table import Table
from dochan.office_binary.doc_tables import assemble_blocks


def rec(text, depth=0, **props):
    return SimpleNamespace(text=text, start=0, end=len(text),
                           props=dict(in_table=depth > 0, itap=depth, **props))


def render(record):
    return [Paragraph(runs=[TextRun(record.text.rstrip('\r\x07'))])]


def definition(edges, flags):
    return bytes([len(flags)]) + struct.pack('<%dh' % len(edges), *edges) + b''.join(
        struct.pack('<H', f) + bytes(18) for f in flags)


def test_doc_tables_preserve_empty_cells_and_rows():
    records = [rec('A\x07', 1), rec('\x07', 1), rec('\x07', 1, row_end=True),
               rec('\x07', 1), rec('B\x07', 1), rec('\x07', 1, row_end=True)]
    table = assemble_blocks(records, render, [])[0]
    assert [[c.text for c in row] for row in table.rows] == [['A', ''], ['', 'B']]
    assert [(c.row, c.col) for row in table.rows for c in row] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_doc_tables_merge_geometry_horizontal_and_vertical():
    records = [rec('Wide\x07', 1), rec('\x07', 1, row_end=True,
                   table_def=definition([0, 200], [0])),
               rec('Top\x07', 1), rec('Side\x07', 1), rec('\x07', 1, row_end=True,
                   table_def=definition([0, 100, 200], [0x60, 0])),
               rec('\x07', 1), rec('Bottom\x07', 1), rec('\x07', 1, row_end=True,
                   table_def=definition([0, 100, 200], [0x20, 0]))]
    table = assemble_blocks(records, render, [])[0]
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away
    assert table.rows[1][0].row_span == 2
    assert table.rows[2][0].is_merged_away
    assert table.rows[2][1].text == 'Bottom'


def test_doc_tables_tc_horizontal_merge():
    records = [rec('Wide\x07', 1), rec('\x07', 1), rec('\x07', 1, row_end=True,
                   table_def=definition([0, 100, 200], [1, 2]))]
    table = assemble_blocks(records, render, [])[0]
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away


def test_doc_tables_vertical_merge_matches_final_horizontal_span():
    records = [rec('Top\x07', 1), rec('\x07', 1), rec('\x07', 1, row_end=True,
                   table_def=definition([0, 100, 200], [0x61, 0x62])),
               rec('\x07', 1), rec('\x07', 1, row_end=True,
                   table_def=definition([0, 200], [0x20]))]
    table = assemble_blocks(records, render, [])[0]
    assert table.rows[0][0].row_span == 2
    assert table.rows[0][0].col_span == 2
    assert table.rows[1][0].is_merged_away


def test_doc_tables_nested_table_stays_inside_host_cell_in_order():
    records = [rec('before\r', 1), rec('inner\r', 2, inner_cell=True),
               rec('\r', 2, inner_row=True), rec('after\x07', 1),
               rec('\x07', 1, row_end=True), rec('tail\r')]
    blocks = assemble_blocks(records, render, [])
    cell = blocks[0].rows[0][0]
    assert isinstance(cell.paragraphs[1], Table)
    assert cell.text == 'before\ninner\nafter'
    assert blocks[1].text == 'tail'


def test_doc_tables_malformed_definition_warns_and_preserves_text():
    warnings = []
    table = assemble_blocks([rec('text\x07', 1), rec('\x07', 1, row_end=True,
                             table_def=b'\xff')], render, warnings)[0]
    assert table.rows[0][0].text == 'text'
    assert warnings


def test_doc_tables_depth_bound_preserves_deep_text():
    warnings = []
    blocks = assemble_blocks([rec('deep\r', 1000)], render, warnings)
    assert blocks[0].text == 'deep'
    assert warnings


def test_doc_tables_padding_budget_checked_before_accumulating_rows(monkeypatch):
    import dochan.office_binary.doc_tables as module
    monkeypatch.setattr(module, 'MAX_CELLS', 3)
    seen = []
    allocated = []
    original = module._TableBuilder.row
    def checked_row(builder, props):
        original(builder, props)
        allocated.append(sum(len(cells) for cells, _, _ in builder.rows))
    monkeypatch.setattr(module._TableBuilder, 'row', checked_row)
    def records():
        for i in range(100):
            seen.append(i)
            yield rec('\x07', 1, row_end=True, table_def=definition([0, 100, 200], [0, 0]))
    warnings = []
    assert assemble_blocks(records(), render, warnings) == []
    assert seen == list(range(100))
    assert max(allocated) == 2
    assert len(warnings) == 1
