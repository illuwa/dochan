"""A link can select complete glyphs by center despite clipped outer edges."""
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
