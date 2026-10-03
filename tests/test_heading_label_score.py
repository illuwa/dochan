"""외부 제목 라벨의 인덱스 검증과 형식별 채점."""

import pytest

from scripts.score_heading_labels import evaluate, validate_labels


def test_validate_heading_labels_rejects_unsafe_or_duplicate_rows():
    with pytest.raises(ValueError):
        validate_labels([{'doc': '../other.hwp', 'i': 0, 't': '제목', 'label': 'H'}])
    with pytest.raises(ValueError):
        validate_labels([{'doc': 'a.hwp', 'i': 0, 't': '제목', 'label': 'H'}] * 2)


def test_external_heading_score_skips_mismatches_and_reports_errors():
    labels = validate_labels([
        {'doc': 'a.hwp', 'i': 0, 't': '□ 제목', 'label': 'H'},
        {'doc': 'a.hwp', 'i': 1, 't': '□ 목록', 'label': 'B'},
        {'doc': 'a.hwp', 'i': 2, 't': '없는 줄', 'label': 'H'},
        {'doc': 'b.hwpx', 'i': 0, 't': '□ 제목', 'label': 'H'},
        {'doc': 'b.hwpx', 'i': 1, 't': '□ 본문', 'label': 'B'},
        {'doc': 'b.hwpx', 'i': 2, 't': '중첩', 'label': 'B'},
    ])
    baseline = {
        'a.hwp': {'0': {'path': 's0.elements0', 'text': '□ 제목', 'level': 0},
                  '1': {'path': 's0.elements1', 'text': '□ 목록', 'level': 0}},
        'b.hwpx': {'0': {'path': 's0.elements0', 'text': '□ 제목', 'level': 0},
                   '1': {'path': 's0.elements1', 'text': '□ 본문', 'level': 0},
                   '2': {'path': 's0.elements2.rows0.c0.paragraphs0',
                         'text': '중첩', 'level': 0}},
    }
    current = {
        'a.hwp': {'0': {'path': 's0.elements0', 'text': '□ 제목', 'level': 3},
                  '1': {'path': 's0.elements1', 'text': '□ 목록', 'level': 3}},
        'b.hwpx': {'0': {'path': 's0.elements0', 'text': '□ 제목', 'level': 0},
                   '1': {'path': 's0.elements1', 'text': '□ 본문', 'level': 0},
                   '2': {'path': 's0.elements2.rows0.c0.paragraphs0',
                         'text': '중첩', 'level': 0}},
    }
    result = evaluate(labels, baseline, current)
    assert result['skipped'] == 2
    assert result['formats']['.hwp']['current'] == {
        'N': 2, 'H': 1, 'TP': 1, 'FP': 1, 'FN': 0,
        'precision': 0.5, 'recall': 1.0,
    }
    assert result['formats']['.hwpx']['current']['FN'] == 1
    assert result['formats']['.hwpx']['baseline']['FN'] == 1
    assert [(row['version'], row['kind'], row['text']) for row in result['errors']] == [
        ('baseline', 'FN', '□ 제목'), ('current', 'FP', '□ 목록'),
        ('baseline', 'FN', '□ 제목'), ('current', 'FN', '□ 제목')]


def test_external_heading_score_compares_prefix_with_collapsed_whitespace():
    # 판독 목록은 공백을 접어 만든다. 원문에 겹친 공백·줄바꿈이 있어도 같은 문단이다.
    labels = validate_labels([{'doc': 'a.hwpx', 'i': 0, 't': '□ 세부 프로그램(안) ※ 행사', 'label': 'H'}])
    snapshot = {'a.hwpx': {'0': {'path': 's0.elements0',
                                 'text': '□  세부 프로그램(안)\n   ※ 행사 전체 공개', 'level': 3}}}
    result = evaluate(labels, snapshot, snapshot)
    assert result['skipped'] == 0
    assert result['formats']['.hwpx']['current']['TP'] == 1
