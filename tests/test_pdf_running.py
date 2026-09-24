from types import SimpleNamespace

import pytest

from dochan.pdf.running import (edge_block, detect_running, is_page_number_like,
                                line_key)


def line(text, y, size=10):
    return SimpleNamespace(text=text, y=y, size=size, direction="ltr")


def page(number, *lines):
    return SimpleNamespace(page_number=number, groups=[list(lines)], bounds=(0, 200))


def test_contiguous_edge_blocks_stop_at_gap():
    lines = [line("top", 190), line("next", 176), line("body", 146),
             line("bottom", 10), line("above", 24), line("body2", 54)]
    assert [item.text for item in edge_block(lines, (0, 200), "header")] == ["top", "next"]
    assert [item.text for item in edge_block(lines, (0, 200), "footer")] == ["bottom", "above"]


@pytest.mark.parametrize("text", ["3", "- 3 -", "3 / 20", "Page 3", "3쪽"])
def test_page_number_like(text):
    assert is_page_number_like(text)


@pytest.mark.parametrize("text", ["[별지 제1호 서식]", "2024. 8. 20."])
def test_non_page_number_like(text):
    assert not is_page_number_like(text)


def test_digits_kept_in_non_page_number_keys():
    assert line_key("header", line("[별지 제1호 서식]", 190)) != line_key(
        "header", line("[별지 제2호 서식]", 190))
    assert line_key("footer", line("Page 3", 10)) == line_key(
        "footer", line("Page 20", 10))


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
