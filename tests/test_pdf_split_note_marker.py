"""각주 표지 `1)` 이 숫자와 괄호 두 조각으로 나뉘어도 같은 기준선에 맞닿으면 한 표지다.

공개 정책브리핑 보도자료 PDF(korea.kr 156784165, 7쪽)는 본문 `퍼센타일` 뒤 위첨자 `1` 과 `)` 를
따로 그린다. 하단 정의·구분선은 기존 규칙 그대로다.
"""
from dochan.pdf.content import Fragment
from dochan.pdf.notes import detect_notes
from dochan.pdf.paths import Segment


def frag(text, x, y, size=12, order=0, width=None):
    return Fragment(x, y, len(text) * size / 2 if width is None else width, size, text, size / 3, order=order)


def split_sample(gap=0.0, close_y=502.5, close_size=9):
    return [frag("Body", 40, 500, order=0),
            frag("1", 64, 502.5, size=9, order=1),
            frag(")", 68.5 + gap, close_y, size=close_size, order=2),
            frag("1) Detail", 40, 100, size=10.5, order=3),
            frag("More body", 40, 480, order=10),
            frag("Last body", 40, 460, order=11)]


def detect(fragments):
    return detect_notes(fragments, [Segment(40, 115, 180, 115)], (0, 800), 3, 1)


def test_split_digit_and_parenthesis_form_one_marker():
    notes, consumed, references, following = detect(split_sample())
    assert [note.text for note in notes] == ["Detail"]
    assert references == {1: 1} and following == 2
    # 닫는 괄호 조각은 본문에 `)` 로 남지 않도록 소비한다.
    assert consumed == {2, 3}


def test_split_marker_requires_touching_fragments():
    assert detect(split_sample(gap=6.0))[0] == []


def test_split_marker_requires_same_baseline_and_size():
    assert detect(split_sample(close_y=500.0))[0] == []
    assert detect(split_sample(close_size=12))[0] == []


def test_split_marker_does_not_join_across_other_fragment():
    fragments = split_sample()
    fragments.insert(2, frag("x", 68.5, 502.5, size=9, order=2))
    fragments[3].order = 4
    fragments[4].order = 5
    assert detect(fragments)[0] == []


def test_digit_alone_is_not_a_marker():
    fragments = split_sample()
    del fragments[2]
    assert detect(fragments)[0] == []


def test_hanging_indent_after_per_glyph_marker_keeps_continuation():
    """정의 줄이 글자마다 조각이면 `1`·`)` 를 합친 표지 다음 글자 x 가 내어쓰기 기준이다(같은 공개 문서)."""
    fragments = split_sample()
    del fragments[3]
    fragments += [frag("1", 40, 100, size=10, order=3, width=4.7),
                  frag(")", 44.7, 100, size=10, order=4, width=4.7),
                  frag("Detail", 54.3, 100, size=10, order=5),
                  frag("continued", 53.1, 87, size=10, order=6)]
    notes, consumed, references, _following = detect(fragments)
    assert [note.text for note in notes] == ["Detail\ncontinued"]
    assert consumed == {2, 3, 4, 5, 6}
