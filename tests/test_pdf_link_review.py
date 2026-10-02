import json

import pytest

from dochan.pdf.content import ContentTextExtractor, FontInfo, Fragment, assemble_lines
from dochan.pdf.widths import WidthMap
from dochan.pdf.annotations import LinkRegion, attach_links
from dochan.pdf.reader import PDFReader
from dochan.pdf.text_tables import detect_text_tables
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text
from dochan.output.json_out import to_dict
from test_pdf_structure import _build_pdf, _minimal_objects

URL = "https://review.example/"


def _document(tmp_path, content, rect, text_tables=False, widths=True, pages=1):
    objects = _minimal_objects(content)
    if widths:
        objects[4] = ("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 0 "
                      "/Widths [%s] >>" % " ".join(["500"] * 256))
    objects[6] = "<< /Subtype /Link /Rect [%s] /A << /S /URI /URI (%s) >> >>" % (rect, URL)
    objects[3] = objects[3][:-2] + " /MediaBox [0 0 612 792] /Annots [6 0 R] >>"
    if pages > 1:
        objects[2] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (
            " ".join("%d 0 R" % number for number in [3] + list(range(7, 7 + pages - 1))), pages)
        for number in range(7, 7 + pages - 1):
            objects[number] = objects[3]
    path = tmp_path / "links.pdf"
    path.write_bytes(_build_pdf(objects))
    return PDFReader(text_tables=text_tables).read(str(path))


@pytest.mark.parametrize("mode", ["text_table", "ruled_table", "running_footer"])
def test_fallback_survives_all_outputs_after_finalization(tmp_path, mode):
    if mode == "text_table":
        content = b" ".join(b"BT /F1 10 Tf 72 %d Td (%s) Tj ET BT /F1 10 Tf 300 %d Td (%s) Tj ET" %
                            (y, a, y, b) for y, a, b in [(700, b"Alpha", b"One"),
                                                       (680, b"Beta", b"Two"), (660, b"Gamma", b"Three")])
        doc = _document(tmp_path, content, "70 698 99 712", text_tables=True)
        assert doc.find_all("table")
    elif mode == "ruled_table":
        content = (b"0 600 200 100 re S 100 600 m 100 700 l S 0 650 m 200 650 l S "
                   b"BT /F1 10 Tf 10 660 Td (Cell) Tj ET BT /F1 10 Tf 120 660 Td (Other) Tj ET")
        doc = _document(tmp_path, content, "10 657 30 672")
        assert doc.find_all("table")
    else:
        content = (b"BT /F1 12 Tf 72 700 Td (Body text.) Tj ET "
                   b"BT /F1 9 Tf 72 30 Td (Footer link) Tj ET")
        doc = _document(tmp_path, content, "70 27 140 40", pages=4)
        assert doc.find_all("header_footer")
    for output in (to_markdown(doc), to_plain_text(doc), json.dumps(to_dict(doc))):
        assert URL in output


def test_default_width_link_is_deferred_with_fallback(tmp_path):
    doc = _document(tmp_path, b"BT /F1 12 Tf 72 720 Td (www.example.org) Tj ET",
                    "72 716 150 733", widths=False)
    runs = [run for p in doc.find_all("paragraph") for run in p.runs if run.link]
    assert runs and all(run.provenance.path == "annots" for run in runs)


def test_default_advance_invalidates_following_text_until_position_reset():
    fonts = {"Bad": FontInfo(lambda b: b.decode(), WidthMap({}, 500)),
             "Good": FontInfo(lambda b: b.decode(), WidthMap({ord("A"): 600}, 500))}
    frags = ContentTextExtractor.from_fonts(fonts, track_char_positions=True).extract_fragments(
        b"BT /Bad 12 Tf 72 720 Td (W) Tj /Good 12 Tf (A) Tj 0 -20 Td (A) Tj ET")
    regions = [LinkRegion(URL, [[(70, 699), (100, 699), (100, 714), (70, 714)]])]
    attach_links(frags, regions, [])
    assert not frags[0].link_spans
    assert not frags[1].link_spans
    assert frags[2].link_spans


def test_link_region_with_unresolved_glyph_is_wholly_deferred():
    fonts = {"F": FontInfo(lambda b: b.decode(), WidthMap({65: 600}, 500))}
    frags = ContentTextExtractor.from_fonts(fonts, track_char_positions=True).extract_fragments(
        b"BT /F 12 Tf 72 720 Td (A) Tj (B) Tj ET")
    region = LinkRegion(URL, [[(70, 716), (100, 716), (100, 734), (70, 734)]])
    attach_links(frags, [region], [])
    assert not any(f.link_spans for f in frags)
    assert not region.matched


def test_partial_overlap_between_destinations_defers_whole_regions():
    fragment = Fragment(0, 10, 30, 10, "ABC", 5, char_offsets=(0, 10, 20, 30))
    regions = [LinkRegion(URL, [[(0, 9), (30, 9), (30, 22), (0, 22)]]),
               LinkRegion("https://other.example", [[(0, 9), (10, 9), (10, 22), (0, 22)]])]
    attach_links([fragment], regions, [])
    assert not fragment.link_spans


def test_boundary_inside_glyph_advance_defers_region():
    fragment = Fragment(0, 10, 30, 10, "[2]", 5, char_offsets=(0, 10, 20, 30))
    region = LinkRegion(URL, [[(6, 9), (24, 9), (24, 22), (6, 22)]])
    attach_links([fragment], [region], [])
    assert not fragment.link_spans


def test_nonuniform_text_transform_is_not_used_for_link_geometry():
    fonts = {"F": FontInfo(lambda b: b.decode(), WidthMap({65: 600}, 500))}
    fragment = ContentTextExtractor.from_fonts(fonts, track_char_positions=True).extract_fragments(
        b"BT /F 1 Tf 12 0 0 39.6 72 720 Tm (A) Tj ET")[0]
    assert not fragment.link_geometry_reliable


def test_unresolved_font_differences_are_not_used_for_link_geometry():
    from dochan.pdf.structure import PDFFile
    from dochan.pdf.objects import PDFName
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    info = PDFReader()._build_font_info(pdf, "F", {
        "Subtype": PDFName("Type1"), "BaseFont": PDFName("CustomFont"),
        "FirstChar": 65, "Widths": [500],
        "Encoding": {"BaseEncoding": PDFName("WinAnsiEncoding"), "Differences": [65, PDFName("B")]}})
    assert not info.link_metrics_reliable


def test_note_marker_keeps_link_and_adjacent_link_gap_is_joined():
    frags = [Fragment(0, 10, 5, 10, "1", 5, link_spans=[(0, 1, URL)], note_ref=1),
             Fragment(20, 10, 20, 10, "Name", 5, order=1, link_spans=[(0, 4, URL)]),
             Fragment(45, 10, 20, 10, "Here", 5, order=2, link_spans=[(0, 4, URL)])]
    line = assemble_lines(frags)[0]
    assert line.runs[0][3:] == (URL, 1)
    assert any(run[0] == " Name Here" and run[3] == URL for run in line.runs)


def test_text_table_preserves_link_and_note_reference_runs():
    lines = []
    for i, word in enumerate(["Alpha", "Beta", "Gamma"]):
        frags = [Fragment(0, 100 - i * 20, 30, 10, word, 5,
                          link_spans=[(0, len(word), URL)]),
                 Fragment(30, 100 - i * 20, 3, 8, "1", 4, order=1, note_ref=i + 1),
                 Fragment(100, 100 - i * 20, 30, 10, "Other%d" % i, 5, order=2)]
        lines.extend(assemble_lines(frags))
    table = detect_text_tables(lines, 1)[0][0]
    for i, row in enumerate(table.rows):
        runs = row[0].paragraphs[0].runs
        assert runs[0].link == URL
        assert runs[-1].note_ref == i + 1


def test_page_destination_marker_reuses_existing_body_paragraph(tmp_path):
    objects = _minimal_objects(b"BT /F1 12 Tf 72 720 Td (Body) Tj ET")
    objects[3] = objects[3][:-2] + " /Annots [6 0 R] >>"
    objects[6] = "<< /Subtype /Link /Dest [3 0 R /Fit] >>"
    path = tmp_path / "destination.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    paragraph = doc.sections[0].elements[0]
    assert paragraph.runs[0].text == "[bookmark: page-1] "
    assert paragraph.runs[1].text == "Body"
