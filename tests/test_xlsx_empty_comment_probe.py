"""독립 XLSX 메모 정답지는 제품 코드 없이 셀 유무와 관계를 판정한다."""
import builtins
from copy import deepcopy
from types import SimpleNamespace
import zipfile

from dochan.model.table import Cell
from scripts.probe_xlsx_empty_comments import compare_cells, unchanged_content_sha256, xlsx_oracle
from test_xlsx_empty_comments import workbook_with_comments


def test_xlsx_comment_oracle_without_product_import(tmp_path, monkeypatch):
    path = tmp_path / 'notes.xlsx'
    workbook_with_comments(path, ['C4', 'A1', 'B1'],
                           '<row r="1"><c r="B1"><v>7</v></c></row>')
    original = builtins.__import__

    def reject_product(name, *args, **kwargs):
        if name == 'dochan' or name.startswith('dochan.'):
            raise AssertionError('product imported by oracle')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', reject_product)
    raw = xlsx_oracle(path)
    assert raw['raw_count'] == 3
    assert [(c['cell'], c['empty_cell'], c['absent_cell'], c['absent_row'])
            for c in raw['comments']] == [('A1', True, True, False),
                                        ('B1', False, False, False),
                                        ('C4', True, True, True)]
    assert [(c['author'], c['body']) for c in raw['comments']] == [
        ('Writer', 'first line\nsecond')] * 3


def test_xlsx_oracle_ignores_unlinked_comment_parts(tmp_path):
    path = tmp_path / 'notes.xlsm'
    workbook_with_comments(path, ['A1'])
    with zipfile.ZipFile(path, 'a') as package:
        package.writestr('xl/comments999.xml', '<broken')
    assert xlsx_oracle(path)['raw_count'] == 1


def test_xlsx_oracle_accepts_backslash_package_part_names(tmp_path):
    path = tmp_path / 'notes.xlsx'
    workbook_with_comments(path, ['A1'])
    with zipfile.ZipFile(path) as package:
        parts = {name.replace('/', '\\'): package.read(name) for name in package.namelist()}
    with zipfile.ZipFile(path, 'w') as package:
        for name, body in parts.items():
            package.writestr(name, body)
    assert xlsx_oracle(path)['raw_count'] == 1


def test_xlsx_comparison_detects_missing_cell_and_text_even_when_order_changes():
    expected = [{'sheet': 'Notes', 'cell': 'A1', 'annotation': '[comment: A: one]'},
                {'sheet': 'Notes', 'cell': 'C4', 'annotation': '[comment: A: two]'}]
    assert compare_cells(expected, list(reversed(expected)))['exact']
    result = compare_cells(expected, [dict(expected[1], annotation='[comment: wrong]')])
    assert result['missing'] == [{'sheet': 'Notes', 'cell': 'A1'}]
    assert result['mismatches'][0]['cell'] == 'C4'


def test_content_digest_ignores_only_added_notes_and_detects_existing_cell_change(tmp_path, monkeypatch):
    import dochan
    path = tmp_path / 'notes.xlsx'
    workbook_with_comments(path, ['A1', 'C4'], '<row r="1"><c r="B1"><v>7</v></c></row>')
    expected = xlsx_oracle(path)['comments']
    doc = dochan.Dochan(str(path)).doc
    after = unchanged_content_sha256(path, expected)
    before = deepcopy(doc)
    table = before.find_all('table')[0]
    table.rows = [[Cell(), table.rows[0][1]]]
    monkeypatch.setattr(dochan, 'Dochan', lambda _path: SimpleNamespace(doc=before))
    assert unchanged_content_sha256(path, expected) == after
    table.rows[0][1].paragraphs[0].runs[0].text = '8'
    assert unchanged_content_sha256(path, expected) != after


def test_content_digest_ignores_new_table_containing_only_absent_cell_notes(tmp_path, monkeypatch):
    import dochan
    path = tmp_path / 'notes.xlsx'
    workbook_with_comments(path, ['C4'])
    expected = xlsx_oracle(path)['comments']
    doc = dochan.Dochan(str(path)).doc
    after = unchanged_content_sha256(path, expected)
    doc.sections[0].elements = []
    monkeypatch.setattr(dochan, 'Dochan', lambda _path: SimpleNamespace(doc=doc))
    assert unchanged_content_sha256(path, expected) == after
