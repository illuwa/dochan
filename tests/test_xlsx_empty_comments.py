"""시트 XML의 셀/행 유무와 무관하게 메모의 좌표를 보존한다."""
import json
from xml.sax.saxutils import escape  # nosemgrep: use-defused-xml -- text escaping helper only; no XML is parsed

import pytest

from dochan.ooxml import xlsx as xlsx_module
from dochan.ooxml.xlsx import XLSXReader, S_NS, R_NS, REL_NS
from dochan.output.json_out import to_json
from dochan.output.markdown import to_markdown
from test_xlsx_reader import _write_xlsx


def workbook_with_comments(path, refs, data='', dimension='A1', merges='', state='', threaded=False):
    book = (f'<workbook xmlns="{S_NS}" xmlns:r="{R_NS}"><sheets>'
            f'<sheet name="Notes" sheetId="1" r:id="s" state="{state}"/>'
            '</sheets></workbook>')
    sheet = (f'<worksheet xmlns="{S_NS}"><dimension ref="{dimension}"/>'
             f'<sheetData>{data}</sheetData>{merges}</worksheet>')
    comments = ''.join(f'<comment ref="{escape(ref)}" authorId="0"><text>'
                       '<r><t>first </t></r><r><t>line&#10;second</t></r>'
                       '</text></comment>' for ref in refs)
    rels = (f'<Relationships xmlns="{REL_NS}"><Relationship Id="c" '
            f'Type="{R_NS}/comments" Target="../comments1.xml"/>'
            + (f'<Relationship Id="t" Type="{R_NS}/threadedComments" '
               'Target="../threadedComments/threadedComment1.xml"/>' if threaded else '')
            + '</Relationships>')
    parts = {'xl/worksheets/_rels/sheet1.xml.rels': rels,
             'xl/comments1.xml': f'<comments xmlns="{S_NS}"><authors><author>Writer</author>'
                                 f'</authors><commentList>{comments}</commentList></comments>'}
    if threaded:
        parts['xl/threadedComments/threadedComment1.xml'] = (
            '<ThreadedComments xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments">'
            '<threadedComment ref="A1" personId="p"><text>thread body</text>'
            '</threadedComment></ThreadedComments>')
    _write_xlsx(path, book, {'xl/worksheets/sheet1.xml': sheet},
                workbook_rels_xml=f'<Relationships xmlns="{REL_NS}">'
                                  '<Relationship Id="s" Target="worksheets/sheet1.xml"/>'
                                  '</Relationships>', extra_parts=parts)


@pytest.mark.parametrize('data', [
    '<row r="1"><c r="B1"><v>7</v></c></row>',
    '<row r="1"/>',
    '',
    '<row r="1"><c r="A1"/></row>',
])
def test_comment_without_cell_or_row_keeps_original_location(tmp_path, data):
    path = tmp_path / 'notes.xlsx'
    workbook_with_comments(path, ['A1', 'C4'], data)
    doc = XLSXReader().read(str(path))
    assert doc.errors == []
    table = doc.find_all('table')[0]
    assert len(table.rows) == 4
    assert all(len(row) == 3 for row in table.rows)
    for row, col, ref in [(0, 0, 'A1'), (3, 2, 'C4')]:
        cell = table.rows[row][col]
        assert cell.text == '[comment: Writer: first line\nsecond]'
        assert cell.provenance.cell == ref
        assert cell.provenance.sheet == 'Notes'
        assert cell.provenance.path == 'xl/worksheets/sheet1.xml'
        assert cell.paragraphs[0].provenance == cell.provenance
        assert cell.paragraphs[0].runs[0].provenance == cell.provenance
    assert to_markdown(doc).count('[comment: Writer: first line second]') == 2
    encoded = next(e for e in json.loads(to_json(doc))['sections'][0]['elements']
                   if e['type'] == 'table')
    assert encoded['rows'][0][0]['text'] == '[comment: Writer: first line\nsecond]'
    assert encoded['rows'][3][2]['text'] == '[comment: Writer: first line\nsecond]'


@pytest.mark.parametrize('ref', ['A1', 'B1', 'A2', 'B2'])
def test_absent_comment_cell_keeps_merge_span_contract(tmp_path, ref):
    path = tmp_path / 'merged-notes.xlsx'
    workbook_with_comments(path, [ref], '<row r="1"><c r="A1"><v>7</v></c></row>',
                           merges='<mergeCells><mergeCell ref="A1:B2"/></mergeCells>')
    doc = XLSXReader().read(str(path))
    cell = next(cell for row in doc.find_all('table')[0].rows for cell in row
                if cell.provenance and cell.provenance.cell == ref)
    assert '[comment: Writer: first line\nsecond]' in cell.text
    assert (cell.row_span, cell.col_span) == ((2, 2) if ref == 'A1' else (0, 0))
    # Markdown renders only merge anchors; JSON retains covered-cell contents.
    assert ('[comment: Writer:' in to_markdown(doc)) == (ref == 'A1')
    assert '[comment: Writer:' in to_json(doc)


@pytest.mark.parametrize('state', ['hidden', 'veryHidden'])
def test_empty_comment_on_hidden_sheet_retains_visibility(tmp_path, state):
    path = tmp_path / 'hidden-notes.xlsx'
    workbook_with_comments(path, ['B3'], state=state)
    doc = XLSXReader().read(str(path))
    assert doc.sections[0].provenance.hidden
    assert doc.sections[0].provenance.visibility == (1 if state == 'hidden' else 2)
    assert f'Sheet visibility: {state}' in to_markdown(doc)
    assert doc.find_all('table')[0].rows[2][1].provenance.cell == 'B3'


def test_large_sheet_preview_still_omits_empty_comments_with_warning(tmp_path, monkeypatch):
    path = tmp_path / 'preview.xlsx'
    workbook_with_comments(path, ['A1', 'C4'], '<row r="1"><c r="B1"><v>7</v></c></row>')
    monkeypatch.setattr(xlsx_module, 'MAX_XML_PART_SIZE', 1)
    doc = XLSXReader().read(str(path))
    assert '[comment:' not in to_markdown(doc)
    assert any('large-sheet preview omits merges, hyperlinks, comments,' in e for e in doc.errors)
    assert doc.find_all('table')[0].rows[0][1].text == '7'


def test_empty_comment_expansion_obeys_dense_grid_limit(tmp_path):
    path = tmp_path / 'limit.xlsx'
    workbook_with_comments(path, ['B100001'], '<row r="1"><c r="A1"><v>7</v></c></row>')
    doc = XLSXReader().read(str(path))
    assert doc.find_all('table') == []
    assert doc.errors == ['ERR: XLSX dense cell limit exceeded: 200002 > 200000']


def test_empty_comment_expansion_accepts_exact_dense_limit(tmp_path, monkeypatch):
    # Same boundary arithmetic, without allocating 200,000 fixture cells.
    monkeypatch.setattr(xlsx_module, 'MAX_DENSE_TABLE_CELLS', 6)
    path = tmp_path / 'exact-limit.xlsx'
    workbook_with_comments(path, ['B3'])
    doc = XLSXReader().read(str(path))
    assert doc.errors == []
    assert len(doc.find_all('table')[0].rows) == 3


@pytest.mark.parametrize('ref', ['A0', 'XFE1', 'A1048577', 'A1:B2', '!' * 20])
def test_invalid_absent_comment_reference_warns_and_preserves_values(tmp_path, ref):
    path = tmp_path / 'invalid-note.xlsx'
    workbook_with_comments(path, [ref], '<row r="1"><c r="A1"><v>7</v></c></row>')
    doc = XLSXReader().read(str(path))
    assert doc.find_all('table')[0].rows[0][0].text == '7'
    assert any('cell reference' in e for e in doc.errors)


@pytest.mark.parametrize('data', ['', '<row r="1"><c r="A1"><v>7</v></c></row>'])
def test_threaded_comment_same_cell_does_not_change_legacy_annotation(tmp_path, data):
    path = tmp_path / 'threaded.xlsx'
    workbook_with_comments(path, ['A1'], data, threaded=True)
    doc = XLSXReader().read(str(path))
    cell = doc.find_all('table')[0].rows[0][0]
    prefix = '7 ' if data else ''
    assert cell.text == prefix + '[comment: Writer: first line\nsecond]'
    assert 'thread body' not in json.dumps(json.loads(to_json(doc)))
