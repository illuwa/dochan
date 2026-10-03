"""실물 프로브의 변경 허용 범위를 작은 모델 추적으로 검사한다."""

from scripts.probe_hwpx_picture_flow import _compare_traces, _only_heading_levels_changed


def test_picture_probe_accepts_one_paragraph_forward_move_and_heading():
    before = [[['P', 0, '밖 앞'], ['P', 0, '상자 앞상자 뒤'],
               ['P', 0, '밖 뒤'], ['I', 'image1']]]
    after = [[['P', 0, '밖 앞'], ['P', 0, '상자 앞상자 뒤'],
              ['I', 'image1'], ['P', 1, '밖 뒤']]]
    assert _compare_traces(before, after) == {
        'valid': True, 'reasons': [], 'heading_changes': 1, 'image_moves': 1}


def test_picture_probe_rejects_structure_text_and_image_order_changes():
    before = [[['P', 0, '앞'], ['I', 'one'], ['I', 'two'], ['P', 0, '뒤']]]
    assert not _compare_traces(before, [[['P', 0, '앞'], ['I', 'two'],
                                         ['I', 'one'], ['P', 0, '뒤']]])['valid']
    assert not _compare_traces(before, [[['P', 0, '앞'], ['T<'], ['I', 'one'],
                                         ['I', 'two'], ['P', 0, '뒤']]])['valid']
    assert not _compare_traces(before, [[['P', 0, '앞!'], ['I', 'one'],
                                         ['I', 'two'], ['P', 0, '뒤']]])['valid']


def test_picture_probe_rejects_more_than_one_paragraph_move():
    before = [[['P', 0, '하나'], ['P', 0, '둘'], ['P', 0, '셋'], ['I', 'one']]]
    after = [[['P', 0, '하나'], ['I', 'one'], ['P', 0, '둘'], ['P', 0, '셋']]]
    assert not _compare_traces(before, after)['valid']


def test_picture_probe_maps_merged_paragraph_before_measuring_move():
    before = [[['P', 0, '앞'], ['P', 0, '중'], ['P', 0, '뒤'], ['I', 'one']]]
    after = [[['P', 0, '앞중뒤'], ['I', 'one']]]
    assert _compare_traces(before, after)['valid']


def test_picture_probe_keeps_caption_attached_to_moving_image():
    before = [[['P', 0, '앞'], ['I', 'one'], ['CAP<'],
               ['P', 0, '그림 설명'], ['CAP>'], ['P', 0, '뒤']]]
    after = [[['P', 0, '앞뒤'], ['I', 'one'], ['CAP<'],
              ['P', 0, '그림 설명'], ['CAP>']]]
    assert _compare_traces(before, after)['valid']


def test_heading_only_label_requires_identical_text_and_image_positions():
    before = [[['P', 3, '제목'], ['I', 'one'], ['P', 0, '본문']]]
    assert _only_heading_levels_changed(
        before, [[['P', 1, '제목'], ['I', 'one'], ['P', 0, '본문']]])
    assert not _only_heading_levels_changed(
        before, [[['P', 1, '제목'], ['P', 0, '본문'], ['I', 'one']]])
