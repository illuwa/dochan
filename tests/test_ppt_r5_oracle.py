"""실측 불일치 목록 절단으로 생긴 가짜 회귀를 방지한다."""
from scripts.probe_ppt_r5_oracle import compare, regressions, summary_delta


def para(text, bold=False):
    return {'slide': 1, 'text': text, 'runs': [[text, 18, bold, False, False, False, False]]}


def truth(text):
    return {'slide': 1, 'text': text, 'size': '18', 'b': 'true', 'i': 'false',
            'u': 'false', 'off': '0'}


def test_r5_oracle_retains_mismatches_after_display_limit():
    pp = [truth('paragraph %d' % i) for i in range(55)]
    before = compare(pp, [para(p['text']) for p in pp])
    after = compare(pp, [para(p['text'], i < 40) for i, p in enumerate(pp)])
    assert len(before['mismatches']) == 55
    assert after['stats']['bold'] == [40, 55]
    assert regressions(before, after) == []


def test_r5_oracle_distinguishes_full_text_and_skips_duplicates():
    texts = ['x' * 50 + ' one', 'x' * 50 + ' two', 'duplicate', 'duplicate']
    result = compare([truth(t) for t in texts], [para(t) for t in texts])
    assert result['matched'] == 2
    assert {m['text'] for m in result['mismatches']} == set(texts[:2])


def test_r5_summary_delta_requires_explicit_truth_for_changed_values():
    before, after = [para('known')], [para('known', True)]
    row = {'legacy_mismatches': [{'slide': 1, 'text': 'known', 'prop': 'bold',
                                  'pp': True, 'dochan': False}]}
    delta, unknown = summary_delta(row, before, after)
    assert delta['bold'] == 1 and not unknown
    delta, unknown = summary_delta({'legacy_mismatches': []}, before, after)
    assert delta['bold'] == 0 and len(unknown) == 1
