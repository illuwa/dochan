"""A link can select complete glyphs by center despite clipped outer edges."""
import pytest

from dochan.pdf import annotations
from dochan.pdf.annotations import LinkRegion, attach_comments, attach_links
from dochan.pdf.content import Fragment
from test_pdf_link_review import _document


def _fragment(text="ABC", y=10):
    return Fragment(0, y, len(text) * 10, 10, text, 5,
                    char_offsets=tuple(range(0, len(text) * 10 + 1, 10)))


def _region(left, right, target="https://example.org"):
    return LinkRegion(target, [[(left, 9), (right, 9),
                                (right, 22), (left, 22)]])


def test_clipped_outer_glyph_edges_attach_selected_centers():
    fragment = _fragment()
    region = _region(1, 29)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == [(0, 3, region.target)]
    assert region.matched


def test_clipped_boundary_touching_unselected_word_stays_deferred():
    fragment = _fragment()
    region = _region(1, 19)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == []


def _split(text, start, y=10, space_width=5):
    return Fragment(start, y, len(text) * 10, 10, text, space_width,
                    char_offsets=tuple(range(0, len(text) * 10 + 1, 10)))


def test_clipped_boundary_across_tj_split_stays_deferred():
    # [(AB) 0 (C)] TJ: the word continues in the next run.
    first, second = _split("AB", 0), _split("C", 20)
    region = _region(1, 19)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [] and second.link_spans == []


def test_clipped_left_boundary_across_tj_split_stays_deferred():
    first, second = _split("A", 0), _split("BC", 10)
    region = _region(11, 29)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [] and second.link_spans == []


def test_clipped_boundary_before_spaced_run_can_attach_url():
    # A gap wider than half a space is a word boundary, as in line assembly.
    first, second = _split("AB", 0), _split("C", 24)
    region = _region(1, 19)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [(0, 2, region.target)]
    assert second.link_spans == []


def test_clipped_boundary_before_run_on_other_line_can_attach_url():
    first, second = _split("AB", 0), _split("C", 20, y=30)
    region = _region(1, 19)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [(0, 2, region.target)]


def test_clipped_boundary_before_delimiter_run_can_attach_url():
    first, second = _split("AB", 0), _split(")", 20)
    region = _region(1, 19)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [(0, 2, region.target)]


@pytest.mark.parametrize("text", ["www.example.com", "3.14", "1,000", "e.g."])
def test_clipped_boundary_before_mark_inside_token_stays_deferred(text):
    # The link selects only the part before the first ASCII mark.
    fragment = _split(text, 0)
    cut = text.index(next(c for c in text if c in ".,")) * 10
    region = _region(0, cut - 1)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == []


@pytest.mark.parametrize("text", ["site. more", "site, more", "site.", "site.)"])
def test_clipped_boundary_before_sentence_mark_can_attach_url(text):
    fragment = _split(text, 0)
    region = _region(1, 39)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == [(0, 4, region.target)]


def test_sentence_mark_followed_by_word_in_touching_run_stays_deferred():
    first, second = _split("www.", 0), _split("example", 40)
    region = _region(1, 29)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == []


def test_clipped_boundary_before_fullwidth_colon_can_attach_url():
    fragment = _split("링크：설명", 0)
    region = _region(1, 19)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == [(0, 2, region.target)]


@pytest.mark.parametrize("first_text, second_text, second_x, region", [
    ("AB", "C", 20, (1, 19)), ("A", "BC", 10, (11, 29))])
def test_tj_split_without_space_metric_stays_deferred(first_text, second_text, second_x, region):
    first = _split(first_text, 0, space_width=0)
    second = _split(second_text, second_x, space_width=0)
    link = _region(*region)
    attach_links([first, second], [link], [], allow_clipped_edges=True)
    assert first.link_spans == [] and second.link_spans == []


def test_overlapping_run_continues_the_word():
    # Line assembly joins overlapping runs, so the output reads "ABC" even
    # when the overlap exceeds half a space.
    first, second = _split("AB", 0, space_width=0.5), _split("C", 19.6, space_width=0.5)
    region = _region(1, 19.5)
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [] and second.link_spans == []


def test_clipped_boundary_after_open_bracket_can_attach_url():
    fragment = _fragment("<AB>")
    region = _region(11, 39)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == [(1, 4, region.target)]


def test_center_only_sliver_stays_deferred():
    fragment = _fragment("A")
    region = _region(3, 7)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == []


def test_edge_without_center_stays_deferred():
    fragment = _fragment()
    region = _region(6, 14)
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == []


def test_multiple_quad_lines_attach_only_selected_centers():
    first = _fragment("AB", y=30)
    second = _fragment("CD", y=10)
    region = LinkRegion("https://example.org", [
        [(1, 29), (19, 29), (19, 42), (1, 42)],
        [(1, 9), (19, 9), (19, 22), (1, 22)],
    ])
    attach_links([first, second], [region], [], allow_clipped_edges=True)
    assert first.link_spans == [(0, 2, region.target)]
    assert second.link_spans == [(0, 2, region.target)]


def test_comment_anchor_keeps_conservative_boundary_rule():
    fragment = _fragment("<AB>")
    region = _region(11, 39, target="1")
    attach_comments([fragment], [region], [])
    assert fragment.comment_spans == []


def test_body_link_replaces_annotation_fallback(tmp_path):
    document = _document(tmp_path,
                         b"BT /F1 10 Tf 72 720 Td (<AB>) Tj ET",
                         "78 716 92 734")
    runs = [run for paragraph in document.find_all("paragraph")
            for run in paragraph.runs if run.link]
    assert len(runs) == 1
    assert runs[0].text == "AB>"
    assert runs[0].provenance.path != "annots"


def test_tj_split_word_keeps_annotation_fallback(tmp_path):
    document = _document(tmp_path,
                         b"BT /F1 10 Tf 72 720 Td [(exam) 0 (ple and more)] TJ ET",
                         "93 716 106 734")
    runs = [run for paragraph in document.find_all("paragraph")
            for run in paragraph.runs if run.link]
    assert all(run.provenance.path == "annots" for run in runs)
    assert "example and more" in "".join(paragraph.text for paragraph in document.find_all("paragraph"))


def _dense_page(lines):
    """One glyph per run; every fifth word link has exact edges, the rest a clipped left edge."""
    text = "word " * 12
    fragments, regions = [], []
    for line in range(lines):
        y = 1000 - line * 14
        for index, char in enumerate(text):
            fragments.append(Fragment(10 * index, y, 10, 10, char, 5, order=len(fragments),
                                      char_offsets=(0, 10)))
        for word in range(12):
            x0 = 50 * word + (-1 if word % 5 == 0 else 3)
            target = ("full%d-%d" if word % 5 == 0 else "clip%d-%d") % (line, word)
            regions.append(LinkRegion(target, [[(x0, y - 2), (50 * word + 41, y - 2),
                                                (50 * word + 41, y + 12), (x0, y + 12)]]))
    return fragments, regions


def _linked(fragments, prefix):
    return {target for fragment in fragments for _, _, target in fragment.link_spans
            if target.startswith(prefix)}


def test_dense_clipped_links_connect_after_space_neighbours():
    fragments, regions = _dense_page(3)
    warnings = []
    attach_links(fragments, regions, warnings, allow_clipped_edges=True)
    assert len(_linked(fragments, "full")) == 9
    assert len(_linked(fragments, "clip")) == 27
    assert not warnings


def test_exhausted_neighbour_budget_defers_only_clipped_links(monkeypatch):
    monkeypatch.setattr(annotations, "_NEIGHBOR_CHECK_LIMIT", 500)
    fragments, regions = _dense_page(3)
    warnings = []
    attach_links(fragments, regions, warnings, allow_clipped_edges=True)
    assert len(_linked(fragments, "full")) == 9
    assert len(_linked(fragments, "clip")) < 27
    assert any("이웃 글자 검사 한도" in warning for warning in warnings)


def test_exhausted_neighbour_budget_warns_with_multi_rect_links(monkeypatch):
    # Polygon checks advance the budget by several steps at once.
    fragments, regions = _dense_page(3)
    for region in regions:
        region.polygons.extend([region.polygons[0], region.polygons[0]])
    for limit in range(355, 366):
        monkeypatch.setattr(annotations, "_NEIGHBOR_CHECK_LIMIT", limit)
        copies = [Fragment(f.x, f.y, f.width, f.size, f.text, f.space_width, order=f.order,
                           char_offsets=f.char_offsets) for f in fragments]
        warnings = []
        attach_links(copies, regions, warnings, allow_clipped_edges=True)
        if len(_linked(copies, "clip")) < 27:
            assert any("이웃 글자 검사 한도" in warning for warning in warnings), limit
