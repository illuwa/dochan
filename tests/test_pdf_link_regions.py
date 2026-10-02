"""각 Link 주석은 다른 위치의 같은 목적지와 독립적으로 검증한다."""
from dochan.pdf.annotations import LinkRegion, attach_links
from dochan.pdf.content import Fragment


URL = 'https://example.test/'


def _region(left, right, bottom=9, top=22):
    return LinkRegion(URL, [[(left, bottom), (right, bottom),
                              (right, top), (left, top)]])


def test_disjoint_same_target_keeps_complete_region_when_other_cuts_glyph():
    first = Fragment(0, 10, 30, 10, 'ABC', 5, char_offsets=(0, 10, 20, 30))
    second = Fragment(100, 10, 30, 10, 'DEF', 5, char_offsets=(0, 10, 20, 30))
    complete, clipped = _region(0, 30), _region(106, 124)
    attach_links([first, second], [complete, clipped], [])
    assert first.link_spans == [(0, 3, URL)]
    assert second.link_spans == []
    assert complete.matched
    assert not clipped.matched


def test_one_annotation_multiple_polygons_is_still_atomic():
    first = Fragment(0, 10, 30, 10, 'ABC', 5, char_offsets=(0, 10, 20, 30))
    second = Fragment(100, 10, 30, 10, 'DEF', 5, char_offsets=(0, 10, 20, 30))
    area = _region(0, 30)
    area.polygons.extend(_region(106, 124).polygons)
    attach_links([first, second], [area], [])
    assert not first.link_spans
    assert not second.link_spans
    assert not area.matched


def test_overlapping_same_target_ambiguous_region_does_not_select_partial_text():
    frag = Fragment(0, 10, 30, 10, 'ABC', 5, char_offsets=(0, 10, 20, 30))
    complete, clipped = _region(0, 30), _region(6, 24)
    attach_links([frag], [complete, clipped], [])
    # Shared glyphs propagate ambiguity to both overlapping annotations.
    assert not frag.link_spans
    assert not complete.matched
    assert not clipped.matched


def test_synthetic_pdf_retains_complete_same_url_body_occurrence(tmp_path):
    from dochan.pdf.reader import PDFReader
    from dochan.output.json_out import to_dict
    from dochan.output.markdown import to_markdown
    from dochan.output.plain_text import to_plain_text
    from test_pdf_structure import _build_pdf, _minimal_objects
    import json

    content = b'BT /F1 10 Tf 0 10 Td (ABC) Tj 100 0 Td (DEF) Tj ET'
    objects = _minimal_objects(content)
    objects[4] = ('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica '
                  '/FirstChar 65 /Widths [1000 1000 1000 1000 1000 1000] >>')
    objects[3] = objects[3][:-2] + ' /Annots [6 0 R 7 0 R] >>'
    for obj, rect in [(6, '0 9 30 22'), (7, '106 9 124 22')]:
        objects[obj] = ('<< /Subtype /Link /Rect [%s] '
                        '/A << /S /URI /URI (%s) >> >>') % (rect, URL)
    path = tmp_path / 'same-destination.pdf'
    path.write_bytes(_build_pdf(objects))
    document = PDFReader().read(str(path))
    linked = [run.text for p in document.find_all('paragraph') for run in p.runs
              if run.link == URL and run.provenance.path != 'annots']
    assert linked == ['ABC']
    for output in (to_markdown(document), to_plain_text(document), json.dumps(to_dict(document))):
        assert URL in output


def test_whitespace_overlap_does_not_propagate_other_links_failure():
    frag = Fragment(0, 10, 50, 10, "A BCD", 5, char_offsets=(0, 10, 20, 30, 40, 50))
    complete, clipped = _region(0, 20), _region(10, 46)
    clipped.target = "https://different.test/"
    attach_links([frag], [complete, clipped], [])
    assert frag.link_spans == [(0, 1, URL)]
    assert complete.matched
    assert not clipped.matched
