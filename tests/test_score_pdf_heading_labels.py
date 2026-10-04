import json

import pytest

from scripts.score_pdf_heading_labels import compact, score_rows, load_labels, score_document


def test_unique_prefix_matching_keeps_original_denominator():
    rows = [{'t': '□ 배경', 'label': 'H'}, {'t': '본문', 'label': 'B'},
            {'t': '누락 제목', 'label': 'H'}, {'t': '반복', 'label': 'H'}]
    paragraphs = [('□ 배 경', 3), ('본문입니다', 2), ('반복 하나', 0), ('반복 둘', 3)]
    counts = score_rows(rows, paragraphs)
    assert counts == {'rows': 4, 'heading_rows': 3, 'matched': 2, 'heading_matched': 1,
                      'tp': 1, 'fp': 1, 'unmatched': 1, 'unmatched_headings': 1,
                      'ambiguous': 1, 'ambiguous_headings': 1}


def test_reverse_prefix_requires_four_visible_characters():
    counts = score_rows([{'t': '짧음 이후 내용', 'label': 'H'},
                         {'t': '제목내용 이후', 'label': 'H'}], [('짧음', 3), ('제목내용', 3)])
    assert counts['matched'] == 1
    assert counts['tp'] == 1
    assert compact('a \t b\n') == 'ab'


def test_empty_prefix_does_not_match_any_paragraph():
    counts = score_rows([{'t': '  ', 'label': 'H'}], [('본문', 3)])
    assert counts['unmatched'] == 1


@pytest.mark.parametrize('name', ['../outside.hwpx', 'private.hwpx', '156000001.pdf'])
def test_labels_only_accept_public_newsid(tmp_path, name):
    path = tmp_path / 'labels.json'
    path.write_text(json.dumps([{'doc': name, 't': 'test', 'label': 'H'}]))
    with pytest.raises(ValueError):
        load_labels(path)


def test_missing_document_is_counted_without_exposing_path(tmp_path):
    result = score_document(tmp_path, '156000001', [{'t': '제목', 'label': 'H'}])
    assert result['news_id'] == '156000001'
    assert result['counts']['unmatched_headings'] == 1
    assert result['failure'] == 'missing'


def test_public_hwp_label_names_share_pdf_newsid(tmp_path):
    path = tmp_path / 'labels.json'
    path.write_text(json.dumps([{'doc': '156000001.hwp', 't': 'test', 'label': 'H'}]))
    assert list(load_labels(path)) == ['156000001']
