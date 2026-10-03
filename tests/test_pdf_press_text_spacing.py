"""글자마다 절대 좌표를 쓰는 PDF의 줄 내부 띄어쓰기."""

from dochan.pdf.content import Fragment, assemble_lines


def _glyphs(text, starts, width=14.0):
    return [Fragment(x, 700.0, width, 14.0, char, width, order=index)
            for index, (char, x) in enumerate(zip(text, starts))]


def test_single_glyph_positioning_recovers_word_gap_from_local_tracking():
    # 같은 폭 한글 글리프가 12.5pt 간격으로 배치되고 어절 사이만 17.5pt다.
    text = "조달청직원들이참여"
    starts = [0, 12.5, 25, 37.5, 50, 62.5, 75, 92.5, 105]
    line = assemble_lines(_glyphs(text, starts))[0]
    assert line.text == "조달청직원들이 참여"
    assert "".join(run[0] for run in line.runs) == line.text


def test_uniform_condensed_positioning_does_not_invent_spaces():
    text = "조달청직원들이참여"
    starts = [12.5 * index for index in range(len(text))]
    assert assemble_lines(_glyphs(text, starts))[0].text == text


def test_tracking_change_within_one_line_does_not_split_every_glyph():
    starts = [13.4 * index for index in range(12)]
    second_start = starts[-1]
    starts.extend(second_start + 12.0 * index for index in range(1, 13))
    glyphs = _glyphs("가" * 24, starts)
    for glyph in glyphs:
        glyph.space_width = 4.7
    assert assemble_lines(glyphs)[0].text == "가" * 24


def test_overprinted_glyphs_do_not_create_word_gaps():
    glyphs = _glyphs("풍" * 8 + "력" * 8,
                     [0.1 * index for index in range(8)] +
                     [16 + 0.1 * index for index in range(8)], width=16)
    assert assemble_lines(glyphs)[0].text == "풍" * 8 + "력" * 8


def test_short_or_mixed_width_line_preserves_existing_gap_rule():
    fragments = _glyphs("한글", [0, 16], width=14)
    assert assemble_lines(fragments)[0].text == "한글"
