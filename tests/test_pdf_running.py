from types import SimpleNamespace

import pytest

from dochan.pdf.running import (edge_block, detect_running, is_page_number_like,
                                line_key)


def line(text, y, size=10, segments=()):
    return SimpleNamespace(text=text, y=y, size=size, direction="ltr",
                           segments=segments)


def page(number, *lines, rotation=0):
    return SimpleNamespace(page_number=number, groups=[list(lines)], bounds=(0, 200),
                           rotation=rotation)


def test_contiguous_edge_blocks_stop_at_gap():
    lines = [line("top", 190), line("next", 176), line("body", 146),
             line("bottom", 10), line("above", 24), line("body2", 54)]
    assert [item.text for item in edge_block(lines, (0, 200), "header")] == ["top", "next"]
    assert [item.text for item in edge_block(lines, (0, 200), "footer")] == ["bottom", "above"]


@pytest.mark.parametrize("text", ["3", "- 3 -", "3 / 20", "Page 3", "p. 3",
                                  "3쪽", "(3)", "[3]"])
def test_page_number_like(text):
    assert is_page_number_like(text)


@pytest.mark.parametrize("text", ["제1조", "제3조(목적)", "2024. 8. 20.",
                                  "1.", "2.1", "3,000", "[별지 제1호 서식]"])
def test_non_page_number_like(text):
    assert not is_page_number_like(text)


def test_digits_kept_in_non_page_number_keys():
    assert line_key("header", line("[별지 제1호 서식]", 190)) != line_key(
        "header", line("[별지 제2호 서식]", 190))
    assert line_key("footer", line("Page 3", 10)) == line_key(
        "footer", line("Page 20", 10))


def test_article_numbers_at_top_are_never_running_text():
    drops, emitted = detect_running([page(1, line("제1조", 190)),
                                     page(2, line("제1조", 190))])
    assert drops == {1: set(), 2: set()}
    assert emitted == []


def test_non_finite_font_size_does_not_break_detection():
    drops, emitted = detect_running([page(1, line("Repeat", 190, float("inf"))),
                                     page(2, line("Repeat", 190, float("inf")))])
    assert [hf.text for _, hf in emitted] == ["Repeat"]
    assert all(len(items) == 1 for items in drops.values())


def test_edge_block_takes_only_extreme_three_of_large_zone():
    lines = [line("far%d" % n, 177) for n in range(1000)]
    lines.extend([line("top", 200), line("next", 199), line("third", 198)])
    assert [item.text for item in edge_block(lines, (0, 200), "header")] == [
        "top", "next", "third"]
    lines = [line("far%d" % n, 23) for n in range(1000)]
    lines.extend([line("bottom", 0), line("next", 1), line("third", 2)])
    assert [item.text for item in edge_block(lines, (0, 200), "footer")] == [
        "bottom", "next", "third"]
    assert [item.text for item in edge_block(
        [line("top", 200), line("gap", 177)], (0, 200), "header")] == ["top"]


def test_threshold_and_single_page():
    assert detect_running([page(1, line("Repeat", 190))])[1] == []
    drops, emitted = detect_running([page(1, line("Repeat", 190)),
                                     page(2, line("Repeat", 190))])
    assert [hf.text for _, hf in emitted] == ["Repeat"]
    assert all(len(items) == 1 for items in drops.values())
    ten = [page(n, line("Repeat", 190) if n <= 2 else line("Body %s" % n, 100))
           for n in range(1, 11)]
    assert detect_running(ten)[1] == []
    ten[2] = page(3, line("Repeat", 190))
    assert [hf.text for _, hf in detect_running(ten)[1]] == ["Repeat"]


def test_page_numbers_must_be_non_decreasing():
    assert [hf.text for _, hf in detect_running([
        page(1, line("3", 10)), page(2, line("2", 10))])[1]] == []
    assert [hf.text for _, hf in detect_running([
        page(1, line("2", 10)), page(2, line("3", 10))])[1]] == ["2"]


def test_section_specific_headers_emit_at_first_pages():
    pages = [page(n, line("Alpha" if n <= 2 else "Beta", 190))
             for n in range(1, 5)]
    _, emitted = detect_running(pages)
    assert [(number, hf.type, hf.text) for number, hf in emitted] == [
        (1, "header", "Alpha"), (3, "header", "Beta")]


def test_multiline_header_emits_one_element_with_visual_order():
    pages = [page(n, line("Confidential", 180), line("ACME", 190)) for n in range(1, 4)]
    drops, emitted = detect_running(pages)
    assert [(number, hf.type, hf.text) for number, hf in emitted] == [
        (1, "header", "ACME\nConfidential")]
    assert len(emitted[0][1].paragraphs) == 2
    assert all(len(items) == 2 for items in drops.values())


def test_literal_hash_cannot_share_page_number_key():
    assert line_key("footer", line("- 1 -", 10)) != line_key(
        "footer", line("- # -", 10))
    drops, emitted = detect_running([page(1, line("- 1 -", 10)),
                                     page(2, line("- # -", 10))])
    assert drops == {1: set(), 2: set()}
    assert emitted == []


def test_close_body_lines_are_not_a_running_header():
    pages = [page(n, line("Introduction", 190), line("Body %d" % n, 178),
                  line("More %d" % n, 166), line("End %d" % n, 154))
             for n in (1, 2)]
    drops, emitted = detect_running(pages)
    assert emitted == []
    assert all(not items for items in drops.values())


def test_close_body_lines_are_not_a_running_footer():
    pages = [page(n, line("End %d" % n, 46), line("More %d" % n, 34),
                  line("Body %d" % n, 22), line("Appendix", 10))
             for n in (1, 2)]
    drops, emitted = detect_running(pages)
    assert emitted == []
    assert all(not items for items in drops.values())


def test_header_with_margin_gap_is_detected():
    pages = [page(n, line("Introduction", 190), line("Body %d" % n, 160))
             for n in (1, 2)]
    drops, emitted = detect_running(pages)
    assert [hf.text for _, hf in emitted] == ["Introduction"]
    assert all(len(items) == 1 for items in drops.values())


@pytest.mark.parametrize("space_width", [0, 5])
def test_three_column_repeated_edge_line_is_not_running(space_width):
    segments = [SimpleNamespace(x0=x, x1=x + 20, space_width=space_width)
                for x in (20, 100, 180)]
    pages = [page(n, line("Item Qty Price", 190, segments=segments),
                  line("Body %d" % n, 140)) for n in (1, 2, 3)]
    drops, emitted = detect_running(pages)
    assert emitted == []
    assert all(not items for items in drops.values())


def test_close_font_sizes_group_across_rounding_boundary():
    pages = [page(n, line("Running", 190, size))
             for n, size in enumerate((10.24, 10.26, 10.3), 1)]
    drops, emitted = detect_running(pages)
    assert [hf.text for _, hf in emitted] == ["Running"]
    assert all(len(items) == 1 for items in drops.values())


def test_outlier_title_size_is_preserved():
    pages = [page(1, line("Running", 190, 20)),
             page(2, line("Running", 190, 10)),
             page(3, line("Running", 190, 10))]
    drops, emitted = detect_running(pages)
    assert [hf.text for _, hf in emitted] == ["Running"]
    assert not drops[1]
    assert len(drops[2]) == len(drops[3]) == 1
