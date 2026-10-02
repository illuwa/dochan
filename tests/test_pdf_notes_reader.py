from dochan.output.markdown import to_markdown
from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf


def test_pdf_reader_moves_note_definitions_and_numbers_repeated_page_markers(tmp_path):
    content = (b"40 115 m 180 115 l S "
               b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
               b"BT /F1 9 Tf 64 502.5 Td (1\\051) Tj ET "
               b"BT /F1 12 Tf 40 400 Td (More text) Tj ET "
               b"BT /F1 10.5 Tf 40 100 Td (1\\051 Detail) Tj ET")
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 /MediaBox [0 0 600 800] "
           "/Resources << /Font << /F1 7 0 R >> >> >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        7: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
           "/FirstChar 0 /Widths [" + "500 " * 256 + "] >>",
    }
    path = tmp_path / "notes.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    notes = doc.find_all("footnote")
    assert [(note.number, note.text) for note in notes] == [(1, "Detail"), (2, "Detail")]
    assert [[r.note_ref for p in section.elements for r in getattr(p, "runs", []) if r.note_ref]
            for section in doc.sections] == [[1], [2]]
    markdown = to_markdown(doc)
    assert "Body[^1]" in markdown and "Body[^2]" in markdown
    assert markdown.count("[^1]: Detail") == markdown.count("[^2]: Detail") == 1
    assert "1) Detail" not in markdown
