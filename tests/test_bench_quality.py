"""Synthetic metric checks; no document bodies or corpus fixtures."""
import pytest

from scripts.bench_quality import score, summarize


def payload(text='', tables=None, headings=None):
    return {'text': text, 'tables': tables, 'headings': headings}


def test_normalization_and_partial_token_match():
    result = score(payload('가  나\n다', []), payload('가 나 라', []))
    assert result['token_ratio'] == pytest.approx(2 / 3)
    assert score(payload('가\n나'), payload('가 나'))['token_ratio'] == 1


def test_cells_normalized_and_duplicate_shapes_consumed():
    reference = payload('x', [[['가  나', '다']], [['라', '마']]], 2)
    candidate = payload('x', [[['가\n나', '다']]], 1)
    result = score(reference, candidate)
    assert result['cell_hit'] == 0.5
    assert result['table_shape_matches'] == 1
    assert result['reference_tables'] == 2
    assert result['candidate_tables'] == 1
    assert result['candidate_headings'] == 1


def test_unsupported_is_not_empty():
    ref = payload('a', [[['a']]], 1)
    assert score(ref, payload('a'))['cell_hit'] is None
    assert score(ref, payload('a', []))['cell_hit'] == 0
    assert score(ref, payload('a'))['candidate_headings'] is None
    assert score(payload('', []), payload('', []))['cell_hit'] is None


def test_summary_excludes_failed_rows_and_uses_reference_denominator():
    good = score(payload('a', [[['a']], [['b']]]), payload('a', [[['a']]]))
    result = summarize([good, {'failed': 1}])
    assert result['failures'] == 1
    assert result['successes'] == 1
    assert result['token_mean'] == 1
    assert result['table_shape_recall'] == 0.5
    assert summarize([{'failed': 1}])['token_mean'] is None
