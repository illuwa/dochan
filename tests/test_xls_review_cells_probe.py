"""독립 정답지 프로브가 문자열 내부를 수식 주석으로 오인하지 않게 한다."""
from scripts.probe_xls_review_cells import _cached_string_matches


def test_string_cache_probe_preserves_embedded_formula_marker():
    expected = 'literal (=not a formula) and tail'
    assert _cached_string_matches(expected + ' (=A1)', expected, True)
    assert not _cached_string_matches('literal (=A1)', expected, True)


def test_string_cache_probe_only_strips_known_formula_coordinates():
    assert not _cached_string_matches('text (=A1)', 'text', False)
    assert _cached_string_matches('text', 'text', False)
    assert not _cached_string_matches(None, '', True)


def test_string_cache_probe_requires_complete_exact_cache():
    assert not _cached_string_matches('\x00text (=A1)', 'text', True)
    assert not _cached_string_matches('text lost (=A1)', 'text', True)
    assert not _cached_string_matches('text (=A1', 'text', True)
