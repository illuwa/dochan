from dochan.model.table import Table
from dochan.office_binary.doc_tables import assemble_blocks
from test_doc_tables import definition, rec, render


def test_doc_table_missing_initial_nesting_levels_remain_in_host_cell():
    blocks = assemble_blocks([rec('inner\r', 2, inner_cell=True),
                              rec('\r', 2, inner_row=True),
                              rec('\x07', 1, row_end=True)], render, [])
    assert len(blocks) == 1
    assert isinstance(blocks[0].rows[0][0].paragraphs[0], Table)
    assert blocks[0].rows[0][0].text == 'inner'


def test_doc_table_nesting_jump_from_one_to_three_keeps_all_hosts():
    blocks = assemble_blocks([rec('before\r', 1), rec('deep\r', 3, inner_cell=True),
                              rec('\r', 3, inner_row=True), rec('after\x07', 1),
                              rec('\x07', 1, row_end=True)], render, [])
    outer = blocks[0].rows[0][0]
    middle = outer.paragraphs[1]
    assert isinstance(middle.rows[0][0].paragraphs[0], Table)
    assert outer.text == 'before\ndeep\nafter'


def test_doc_table_deleted_rows_leave_no_skeleton_but_keep_live_rows():
    blocks = assemble_blocks([rec('deleted\x07', 1),
                              rec('\x07', 1, row_end=True, deleted_mark=True),
                              rec('live\x07', 1), rec('\x07', 1, row_end=True)], render, [])
    assert [[c.text for c in row] for row in blocks[0].rows] == [['live']]
    assert assemble_blocks([rec('\x07', 1),
                            rec('\x07', 1, row_end=True, deleted_mark=True)], render, []) == []


def test_doc_table_merged_cells_do_not_duplicate_json_text():
    blocks = assemble_blocks([rec('left\x07', 1), rec('right\x07', 1),
                              rec('\x07', 1, row_end=True,
                                  table_def=definition([0, 100, 200], [1, 2])),
                              rec('top\x07', 1), rec('\x07', 1, row_end=True,
                                  table_def=definition([0, 200], [0x60])),
                              rec('bottom\x07', 1), rec('\x07', 1, row_end=True,
                                  table_def=definition([0, 200], [0x20]))], render, [])
    table = blocks[0]
    assert table.rows[0][0].text == 'left\nright'
    assert table.rows[0][1].paragraphs == []
    assert table.rows[1][0].text == 'top\nbottom'
    assert table.rows[2][0].paragraphs == []


def test_doc_table_cell_limit_degrades_only_oversized_table(monkeypatch):
    import dochan.office_binary.doc_tables as module
    monkeypatch.setattr(module, 'MAX_CELLS', 2)
    warnings = []
    records = [rec('lead\r'), rec('one\x07', 1), rec('two\x07', 1),
               rec('three\x07', 1), rec('\x07', 1, row_end=True), rec('tail\r'),
               rec('small\x07', 1), rec('\x07', 1, row_end=True)]
    blocks = assemble_blocks(records, render, warnings)
    assert [b.text for b in blocks[:-1]] == ['lead', 'one', 'two', 'three', 'tail']
    assert blocks[-1].rows[0][0].text == 'small'
    assert not any(isinstance(b, Table) for b in blocks[:-1])
    assert isinstance(blocks[-1], Table)
    assert len(warnings) == 1


def test_doc_table_grid_expansion_limit_keeps_paragraphs(monkeypatch):
    import dochan.office_binary.doc_tables as module
    monkeypatch.setattr(module, 'MAX_CELLS', 3)
    warnings = []
    records = [rec('one\x07', 1), rec('\x07', 1, row_end=True,
                 table_def=definition([0, 100], [0])),
               rec('two\x07', 1), rec('\x07', 1, row_end=True,
                 table_def=definition([100, 200], [0]))]
    assert [b.text for b in assemble_blocks(records, render, warnings)] == ['one', 'two']
    assert warnings


def test_doc_table_overflow_does_not_resurrect_deleted_current_row(monkeypatch):
    import dochan.office_binary.doc_tables as module
    monkeypatch.setattr(module, 'MAX_CELLS', 1)
    records = [rec('kept\x07', 1), rec('\x07', 1, row_end=True),
               rec('deleted\x07', 1), rec('also deleted\x07', 1),
               rec('\x07', 1, row_end=True, deleted_mark=True)]
    assert [b.text for b in assemble_blocks(records, render, [])] == ['kept']


def test_doc_table_oversized_nested_table_keeps_host_and_later_text(monkeypatch):
    import dochan.office_binary.doc_tables as module
    monkeypatch.setattr(module, 'MAX_CELLS', 2)
    records = [rec('before\r', 1), rec('a\r', 2, inner_cell=True),
               rec('b\r', 2, inner_cell=True), rec('c\r', 2, inner_cell=True),
               rec('\r', 2, inner_row=True), rec('after\x07', 1),
               rec('\x07', 1, row_end=True)]
    blocks = assemble_blocks(records, render, [])
    assert isinstance(blocks[0], Table)
    assert blocks[0].rows[0][0].text == 'before\na\nb\nc\nafter'
