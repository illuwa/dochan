"""열 시작점을 넘는 셀 조각의 텍스트와 서식을 함께 보존한다."""
from collections import Counter

from dochan.pdf.content import Fragment, assemble_lines
from dochan.pdf.text_tables import detect_text_tables
from dochan.pdf.reader import PDFReader
from dochan.output.markdown import to_markdown
from test_pdf_structure import _build_pdf, _minimal_objects


def test_crossing_column_fragment_stays_in_its_merged_cell():
    fragments = []
    rows = [[(72, "Name"), (200, "Kind"), (330, "Value")],
            [(72, "Twentycharacterslong"), (198, "Spill"), (330, "One")],
            [(72, "Gamma"), (200, "Fruit"), (330, "Two")],
            [(72, "Delta"), (200, "Stone"), (330, "Three")]]
    for row, cells in enumerate(rows):
        for x, value in cells:
            fragment = Fragment(x, 700 - 14 * row, 6 * len(value), 10, value, 6,
                                order=len(fragments), bold=value == "Spill")
            if value == "Spill":
                fragment.link_spans = [(0, len(value), "https://example.org/spill")]
            fragments.append(fragment)
    table, consumed = detect_text_tables(assemble_lines(fragments))[0]
    assert consumed == {0, 1, 2, 3}
    assert [c.text for c in table.rows[1]] == ["Twentycharacterslong Spill", "", "One"]
    runs = table.rows[1][0].paragraphs[0].runs
    spill = next(run for run in runs if run.text == "Spill")
    assert spill.bold and spill.link == "https://example.org/spill"
    expected = Counter(ch for f in fragments for ch in f.text if not ch.isspace())
    actual = Counter(ch for row in table.rows for c in row for ch in c.text if not ch.isspace())
    assert actual == expected


def test_crossing_column_adjacent_digits_are_not_split():
    fragments = []
    for row, digits in enumerate(("12345", "67890", "24680")):
        values = [(20, "Row" + str(row), 20), (100, "Label", 20),
                  (300, "Tail" + str(row), 20)]
        if row == 1:
            values = [(20 + 20 * index, char, 20) for index, char in enumerate(digits)]
            values.append((300, "Tail1", 20))
        for x, value, width in values:
            fragments.append(Fragment(x, 700 - 14 * row, width, 10, value, 5,
                                      order=len(fragments)))
    table, _ = detect_text_tables(assemble_lines(fragments))[0]
    assert table.rows[1][0].text == "67890"
    assert table.rows[1][1].text == ""


def test_reader_keeps_spill_in_markdown_table(tmp_path):
    rows = [[(72, b"Name"), (200, b"Kind"), (330, b"Value")],
            [(72, b"Twentycharacterslong"), (198, b"Spill"), (330, b"One")],
            [(72, b"Gamma"), (200, b"Fruit"), (330, b"Two")],
            [(72, b"Delta"), (200, b"Stone"), (330, b"Three")]]
    content = b" ".join(b"BT /F1 10 Tf %d %d Td (%s) Tj ET" % (x, 700 - row * 14, value)
                        for row, cells in enumerate(rows) for x, value in cells)
    objects = _minimal_objects(content)
    objects[3] = objects[3][:-2] + " /MediaBox [0 0 612 792] >>"
    objects[4] = ("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /FirstChar 32 "
                  "/LastChar 126 /Widths [%s] >>" % " ".join(["600"] * 95))
    path = tmp_path / "spill.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader(text_tables=True).read(str(path))
    assert doc.errors == []
    assert "| Twentycharacterslong Spill |  | One |" in to_markdown(doc)
