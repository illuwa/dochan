"""중첩 표 검증은 같은 서명만으로 내용·위치 일치를 주장하지 않는다."""
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.table import Cell, Table
from scripts.probe_pdf_connected_tables import nested_identities, summarize


def document(first, second):
    inner = Table(rows=[[
        Cell(row=0, col=0, paragraphs=[Paragraph(runs=[TextRun(text=first)])]),
        Cell(row=0, col=1, paragraphs=[Paragraph(runs=[TextRun(text=second)])]),
    ]])
    outer = Table(rows=[[Cell(paragraphs=[inner])]])
    return Document(sections=[Section(elements=[outer])])


def test_probe_distinguishes_same_shape_with_swapped_cell_text():
    answer = nested_identities(document('left', 'right'))
    candidate = nested_identities(document('right', 'left'))
    assert sum(answer.values()) == 1
    assert not answer & candidate
    assert sum((answer & nested_identities(document('left', 'right'))).values()) == 1


def test_probe_keeps_failed_document_out_of_negative_success_count():
    result = summarize({'a': {'connected_candidates': 0, 'hwpx_nested': 0},
                        'b': {'exception_type': 'ValueError'}}, 'pairs')
    assert result['files'] == 2
    assert result['completed'] == result['failed'] == 1
    assert result['negative_documents'] == 1
    assert result['negative_fired_documents'] == 0
