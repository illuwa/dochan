from scripts.probe_pdf_heading_regression import compare_records, document_record
from dochan.model.document import Document, Paragraph, Section, TextRun


def test_summary_separates_first_change_from_new_first_and_preserves_size_headings():
    before = [{'group': 'public', 'id': 0, 'file': '156000001.pdf', 'hash': 'a', 'chars': 10,
               'heading_count': 1, 'headings': [[2, 'old', 1]], 'first': 'old', 'errors': 'same'},
              {'group': 'private', 'id': 0, 'file': '', 'hash': 'a', 'chars': 10,
               'heading_count': 0, 'headings': [], 'first': None, 'errors': 'same'}]
    after = [dict(before[0], hash='b', heading_count=2, headings=[[0, 'new', 3], [2, 'old', 1]], first='new'),
             dict(before[1], hash='c', heading_count=1, headings=[[0, 'secret-hash', 3]], first='secret-hash')]
    result = compare_records(before, after)
    assert result['public']['first_changed'] == 1
    assert result['public']['new_first'] == 0
    assert result['public']['size_headings_changed'] == 0
    assert result['private']['new_first'] == 1
    assert result['private']['markdown_changed'] == 1


def test_document_record_contains_hashes_and_counts_without_text():
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun(text='private text')], heading_level=3)])],
                   errors=['private warning'])
    result = document_record(doc, 'private text')
    assert result['heading_count'] == 1
    assert len(result['hash']) == len(result['errors']) == 64
    assert 'private' not in str(result)
