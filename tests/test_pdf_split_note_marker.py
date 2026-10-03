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


def caption_page(segments=None):
    """쪽 최빈 크기는 15pt 제목이고 표지는 12pt 캡션에 붙는다(공개 156784165 7쪽의 크기 구성)."""
    fragments = [frag("Heading %d" % index, 40, 700 - 20 * index, size=15, order=index) for index in range(6)]
    fragments += [frag("Caption", 40, 500, order=20),
                  frag("1", 82, 502.5, size=9, order=21),
                  frag(")", 86.5, 502.5, size=9, order=22),
                  frag("1) Detail", 40, 100, size=10, order=23)]
    return detect_notes(fragments, [Segment(40, 115, 180, 115)] if segments is None else segments,
                        (0, 800), 3, 1)


def test_marker_host_may_be_smaller_than_page_mode_but_larger_than_definition():
    notes, _consumed, references, _following = caption_page()
    assert [note.text for note in notes] == ["Detail"] and references == {21: 1}


def test_table_bottom_border_is_not_a_footnote_separator():
    """표 아래 주석: 하단선 위로 같은 폭의 괘선이 쌓여 있으면 표 테두리다(감수 재현)."""
    table = [Segment(40, 160, 400, 160), Segment(40, 182, 400, 182), Segment(40, 200, 400, 200),
             Segment(140, 160, 140, 200)]
    fragments = [frag("Body text line %d" % index, 40, 760 - 14 * index, size=10, order=index)
                 for index in range(20)]
    fragments += [frag("Growth", 150, 188, size=8, order=30),
                  frag("1)", 174, 189.6, size=6, order=31),
                  frag("1) year over year change", 40, 148, size=7, order=32)]
    assert detect_notes(fragments, table, (0, 800), 3, 1)[0] == []
    # 같은 쪽이라도 짧은 단독 구분선이면 각주다.
    assert len(detect_notes(fragments, [Segment(40, 160, 180, 160)], (0, 800), 3, 1)[0]) == 1


def test_parenthesised_number_is_not_split_into_marker():
    fragments = split_sample()
    fragments.insert(1, frag("(", 59.5, 502.5, size=9, order=1, width=4.5))
    for index, fragment in enumerate(fragments[2:4], start=2):
        fragment.order = index
    fragments[0].width = 19.5
    assert detect(fragments)[0] == []


def test_two_digit_split_marker_has_no_phantom_suffix():
    fragments = split_sample()
    fragments[1:3] = [frag("1", 64, 502.5, size=9, order=1, width=4.5),
                      frag("2", 68.5, 502.5, size=9, order=2, width=4.5),
                      frag(")", 73, 502.5, size=9, order=3, width=2.7)]
    fragments[4].text = "12) Detail"
    fragments[4].order = 4
    notes, consumed, references, _following = detect(fragments)
    assert [note.number for note in notes] == [1] and references == {1: 1}
    assert {2, 3} <= consumed


def test_marker_detection_does_not_mutate_fragments():
    fragments = split_sample()
    fragments[1:3] = [frag("1)", 64, 502.5, size=9, order=1)]
    assert len(detect(fragments)[0]) == 1
    assert not any(hasattr(fragment, "extra_orders") for fragment in fragments)
