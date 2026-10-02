"""합성 표로 병합 지표의 대응 한계와 집계 프로브를 검증한다."""
from dochan.model.document import Paragraph, TextRun
from dochan.model.table import Cell, Table
from scripts.probe_pdf_spans import audit_tables, boundary_differences


def _table(merged, text):
    return Table(rows=[[
        Cell(row=0, col=0, col_span=2 if merged else 1,
             paragraphs=[Paragraph(runs=[TextRun(text=text)])]),
        Cell(row=0, col=1, col_span=0 if merged else 1),
    ]])


def test_span_probe_separates_absent_duplicate_from_different_span():
    answer = [_table(True, 'one'), _table(True, 'two')]
    result = audit_tables(answer, [_table(True, 'one')], {})
    assert result['merged_dims'] == result['merged_exact'] == 1
    assert result['unmatched_with_same_dimensions'] == 1
    assert result['signature_multiplicity_only'] == 1
    assert result['span_difference_candidates'] == 0


def test_span_probe_reports_same_text_and_missing_expected_boundary():
    result = audit_tables([_table(False, 'sample')], [_table(True, 'sample')], {})
    assert result['merged_total'] == 0
    result = audit_tables([_table(True, 'sample')], [_table(False, 'sample')], {})
    assert result['equal_nonempty_text_sets'] == 1
    assert result['present_inside_expected_merge'] == 1


def test_span_probe_does_not_call_unrelated_same_dimensions_correspondence():
    result = audit_tables([_table(True, 'private source')], [_table(False, 'other')], {})
    assert result['no_shared_text_candidates'] == 1
    assert result['equal_nonempty_text_sets'] == 0
    assert 'private' not in str(result)


def test_boundary_differences_counts_missing_rule_without_guessing_thickness():
    assert boundary_differences(_table(False, ''), _table(True, '')) == (1, 0)
    assert boundary_differences(_table(True, ''), _table(False, '')) == (0, 1)
