"""명시적인 문서 끝 미주 구역과 앞선 위첨자 참조를 함께 확인한다."""
from types import SimpleNamespace

from dochan.pdf.content import Fragment, assemble_lines
from dochan.pdf.notes import detect_endnotes, endnote_references


def fragment(text, x, y, size=10, order=0):
    return Fragment(x, y, len(text) * size / 2, size, text, size / 3, order=order)


def draft(page, fragments):
    return SimpleNamespace(page_number=page, groups=[assemble_lines(fragments)],
                           ordered=[], notes=[], bounds=(0, 800), rotation=0,
                           note_markers=endnote_references(fragments))


def pages(title="Endnotes"):
    return [draft(1, [fragment("Body", 40, 500, 12, 0),
                      fragment("1)", 64, 503, 8, 1)]),
            draft(2, [fragment(title, 40, 700, 14, 0),
                      fragment("1) First definition", 40, 100, 10, 1)]),
            draft(3, [fragment("Continued definition", 40, 700, 10, 0),
                      fragment("Final line", 40, 686, 10, 1)])]


def test_endnote_cross_page_definition_uses_existing_model():
    drafts = pages()
    drops = {}
    assert detect_endnotes(drafts, drops, 7) == 8
    assert drafts[1].notes[0].type == "endnote"
    assert drafts[1].notes[0].number == 7
    assert drafts[1].notes[0].text == "First definition\nContinued definition\nFinal line"
    assert [p.provenance.page for p in drafts[1].notes[0].paragraphs] == [2, 3, 3]
    assert len(drops[2]) == 2 and len(drops[3]) == 2
    assert any(len(run) > 5 and run[4:] == (7, "endnote")
               for line in drafts[0].groups[0] for run in line.runs)


def test_endnote_requires_explicit_section_and_unambiguous_superscript():
    for title in ("References", "Ordinary chapter"):
        drafts = pages(title)
        assert detect_endnotes(drafts, {}, 1) == 1
        assert not any(d.notes for d in drafts)
    drafts = pages()
    drafts[0].note_markers = []
    assert detect_endnotes(drafts, {}, 1) == 1
    drafts = pages()
    drafts[0].note_markers *= 2
    assert detect_endnotes(drafts, {}, 1) == 1


def test_endnote_does_not_consume_unrelated_later_body_or_tables():
    drafts = pages()
    drafts[-1].groups[0].append(assemble_lines([fragment("New chapter", 40, 600, 18, 2)])[0])
    assert detect_endnotes(drafts, {}, 1) == 1
    assert not any(d.notes for d in drafts)
    drafts = pages()
    drafts[-1].ordered.append((0, 0, object()))
    assert detect_endnotes(drafts, {}, 1) == 1


def test_endnote_ignores_running_headers_and_retains_existing_footnotes():
    drafts = pages("미주")
    header = assemble_lines([fragment("Running header", 100, 780, 12, 9)])[0]
    drafts[-1].groups[0].insert(0, header)
    drops = {3: {id(header)}}
    assert detect_endnotes(drafts, drops, 2) == 3
    assert id(header) in drops[3]


def test_endnote_marker_limits_and_baseline_numbers():
    assert endnote_references([fragment("Body", 40, 500, 12, 0),
                               fragment("1)", 64, 500, 8, 1)]) == []
    warnings = []
    assert endnote_references([fragment("1)", 64, 503, 8, n) for n in range(50001)], warnings) == []
    assert warnings


def test_reader_endnote_markdown_and_json_contract(tmp_path):
    from dochan.output.markdown import to_markdown
    from dochan.pdf.reader import PDFReader
    from test_pdf_structure import _build_pdf

    streams = [b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
               b"BT /F1 8 Tf 64 503 Td (1\\051) Tj ET",
               b"BT /F1 14 Tf 40 700 Td (Endnotes) Tj ET "
               b"BT /F1 10 Tf 40 100 Td (1\\051 First definition) Tj ET",
               b"BT /F1 10 Tf 40 700 Td (Continued definition) Tj ET"]
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 /MediaBox [0 0 600 800] "
           "/Resources << /Font << /F1 9 0 R >> >> >>",
        9: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 0 "
           "/Widths [" + "500 " * 256 + "] >>",
    }
    for offset, stream in enumerate(streams):
        objects[3 + offset] = "<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (6 + offset)
        objects[6 + offset] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
    path = tmp_path / "endnotes.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert not doc.errors
    assert [n.text for n in doc.find_all("endnote")] == ["First definition\nContinued definition"]
    refs = [run for section in doc.sections for p in section.elements
            for run in getattr(p, "runs", []) if run.note_ref]
    assert [(r.note_reference_type, r.note_reference_number) for r in refs] == [("endnote", 1)]
    markdown = to_markdown(doc)
    assert "Body[^1]" in markdown
    assert markdown.count("[^1]: First definition") == 1
    assert markdown.count("Continued definition") == 1


def test_multiple_endnote_references_in_one_body_line_are_preserved():
    drafts = [draft(1, [fragment("Body", 40, 500, 12, 0),
                       fragment("1)", 64, 503, 8, 1),
                       fragment("More", 90, 500, 12, 2),
                       fragment("2)", 114, 503, 8, 3)]),
              draft(2, [fragment("Notes", 40, 700, 14, 0),
                        fragment("1) First", 40, 650, 10, 1),
                        fragment("2) Second", 40, 630, 10, 2)])]
    assert detect_endnotes(drafts, {}, 1) == 3
    refs = [run[4] for line in drafts[0].groups[0] for run in line.runs if len(run) > 4]
    assert refs == [1, 2]
