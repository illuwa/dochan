"""PDF layout work scales with input fragments, without changing output."""
from unittest.mock import patch

from dochan.pdf import tables
from dochan.pdf.content import Fragment, Segment


def test_table_reference_points_once_per_fragment():
    xs, ys = [0, 50, 100, 150], [0, 30, 60, 90]
    segments = [Segment(0, y, 150, y) for y in ys]
    segments += [Segment(x, 0, x, 90) for x in xs]
    fragments = [Fragment(x + 10, y + 10, 10, 10, str(i), 5, order=i)
                 for i, (x, y) in enumerate((x, y) for y in ys[:-1] for x in xs[:-1])]
    with patch.object(tables, '_reference_point', wraps=tables._reference_point) as reference:
        result = tables.build_tables(segments, fragments)
    assert [[cell.text for cell in row] for row in result[0].table.rows] == [
        ['6', '7', '8'], ['3', '4', '5'], ['0', '1', '2']]
    assert reference.call_count == len(fragments)


def test_no_rules_need_no_reference_points():
    fragment = Fragment(10, 10, 10, 10, 'body', 5)
    with patch.object(tables, '_reference_point', wraps=tables._reference_point) as reference:
        assert tables.build_tables([], [fragment]) == []
    assert reference.call_count == 0


def test_page_paragraphs_match_document_order_cycles_and_depth():
    from dochan.model.document import Document, Paragraph, Section, TextRun
    from dochan.model.table import Cell, Table
    from dochan.model.image import Image
    from dochan.model.header_footer import Footnote, HeaderFooter
    from dochan.pdf import reader

    paragraphs = [Paragraph(runs=[TextRun(text=str(i))]) for i in range(6)]
    table = Table(rows=[[Cell(paragraphs=[paragraphs[0], paragraphs[1]])]],
                  caption=[paragraphs[2]])
    image = Image(caption=[paragraphs[3]])
    note = Footnote(paragraphs=[paragraphs[4], table])
    header = HeaderFooter(paragraphs=[paragraphs[5], note])
    table.rows[0][0].paragraphs.append(table)
    elements = [None, header, image, table, paragraphs[0]]
    deep = Paragraph(runs=[TextRun(text='too deep')])
    for _ in range(34):
        deep = Footnote(paragraphs=[deep])
    elements.append(deep)
    expected = Document(sections=[Section(elements=elements)]).find_all('paragraph')
    actual = list(reader._page_paragraphs(elements))
    assert [id(p) for p in actual] == [id(p) for p in expected]


def test_prepared_note_geometry_reuses_horizontal_classification():
    from dochan.pdf import notes

    fragments = [Fragment(10, 100, 20, 10, 'body', 5),
                 Fragment(30, 102, 3, 6, '1', 3, order=1)]
    expected_notes = notes.detect_notes(fragments, [], (0, 200), 1)
    expected_refs = notes.endnote_references(fragments)
    with patch.object(notes, 'writing_direction', wraps=notes.writing_direction) as direction:
        horizontal = notes.horizontal_note_fragments(fragments)
        assert notes.detect_notes(fragments, [], (0, 200), 1,
                                  _horizontal=horizontal) == expected_notes
        assert notes.endnote_references(fragments, _horizontal=horizontal) == expected_refs
    assert direction.call_count == len(fragments)


def test_cmap_reuses_code_length_order_and_observes_mutation():
    from dochan.pdf.cmap import ToUnicodeCMap

    cmap = ToUnicodeCMap()
    cmap.code_lengths = {1}
    cmap.mapping = {(1, 65): 'A', (2, 0x4142): 'pair'}
    with patch('builtins.sorted', wraps=sorted) as sort:
        assert cmap.decode(b'A') == 'A'
        assert cmap.decode(b'A') == 'A'
        assert sort.call_count == 1
        cmap.code_lengths.add(2)
        assert cmap.decode(b'AB') == 'pair'
        cmap.code_lengths.remove(2)
        assert cmap.decode(b'AB') == 'A�'
        cmap.code_lengths = {2}  # Same cardinality, different lengths.
        assert cmap.decode(b'AB') == 'pair'


def test_bmp_cmap_range_does_not_decode_each_utf16_scalar():
    from dochan.pdf import cmap

    with patch.object(cmap, '_int_to_text', wraps=cmap._int_to_text) as convert:
        mapping = cmap.parse_tounicode(b'1 beginbfrange <00> <02> <0041> endbfrange')
    assert mapping.decode(b'\x00\x01\x02') == 'ABC'
    assert convert.call_count == 0


def test_cmap_range_utf16_boundaries_and_limit(monkeypatch):
    from dochan.pdf import cmap

    for token in ('D7FF', 'DFFF', 'FFFF', '00410042', 'FFFFFE', '00041'):
        result = cmap.parse_tounicode(('1 beginbfrange <00> <02> <%s> endbfrange' % token).encode())
        assert result.mapping == {(1, i): cmap._int_to_text(int(token, 16) + i, len(token))
                                  for i in range(3)}
    monkeypatch.setattr(cmap, 'MAX_MAPPING_ENTRIES', 2)
    warnings = []
    result = cmap.parse_tounicode(b'1 beginbfrange <00> <02> <0041> endbfrange', warnings)
    assert result.mapping == {(1, 0): 'A', (1, 1): 'B'}
    assert result.truncated and len(warnings) == 1


def test_distant_link_does_not_scan_glyphs():
    from dochan.pdf.annotations import LinkRegion, _attach_unique_links

    class CountedText(str):
        scans = 0

        def __iter__(self):
            self.scans += 1
            return super().__iter__()

    text = CountedText('body')
    fragment = Fragment(0, 0, 20, 10, text, 5, char_offsets=[0, 5, 10, 15, 20])
    region = LinkRegion('https://example.org', [[(100, 100), (120, 100), (120, 110), (100, 110)]])
    warnings = []
    _attach_unique_links([fragment], [region], warnings, True)
    assert fragment.link_spans == [] and not region.matched and warnings == []
    assert text.scans == 0


def test_segment_normalization_does_not_sort():
    with patch('builtins.sorted', wraps=sorted) as sort:
        segment = Segment(5, 8, 1, 2)
        assert (segment.x0, segment.y0, segment.x1, segment.y1) == (1, 2, 5, 8)
    assert sort.call_count == 0
