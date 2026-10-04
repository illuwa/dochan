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


def test_endnote_numeric_table_cells_do_not_exhaust_reference_limit():
    # 표의 숫자 셀은 형태만 미주 표지처럼 보여도 위첨자 참조가 아니다.
    fragments = [fragment("1", 40 + (n % 11) * 30, 50 + (n // 11) * 7, 10, n)
                 for n in range(1001)]
    warnings = []
    assert endnote_references(fragments, warnings) == []
    assert warnings == []


def test_endnote_confirmed_reference_limit_remains():
    fragments = []
    for number in range(1001):
        y = number * 20
        fragments.extend((fragment("Body", 40, y, 12, number * 2),
                          fragment("1", 64, y + 4, 8, number * 2 + 1)))
    warnings = []
    assert endnote_references(fragments, warnings) == []
    assert warnings == ["WARN: PDF 미주 표지 수 한도 초과 — 참조 복원 생략"]


def test_endnote_geometry_budget_warning_names_endnotes(monkeypatch):
    import dochan.pdf.notes as notes

    monkeypatch.setattr(notes, "MAX_NOTE_GEOMETRY_CHECKS", 0)
    warnings = []
    assert endnote_references([fragment("Body", 40, 500, 12, 0),
                               fragment("1)", 64, 503, 8, 1)], warnings) == []
    assert len(warnings) == 1 and "미주 기하 검사" in warnings[0]


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


def chapter_pages():
    return [draft(1, [fragment("Contents", 40, 700, 16, 0),
                       fragment("Alpha 1", 40, 650, 10, 1),
                       fragment("Beta 2", 40, 630, 10, 2),
                       fragment("Notes 3", 40, 610, 10, 3),
                       fragment("Index 4", 40, 590, 10, 4)]),
            draft(2, [fragment("Alpha", 40, 700, 16, 0),
                       fragment("Body", 40, 500, 12, 1),
                       fragment("1", 64, 504, 8, 2)]),
            draft(3, [fragment("Beta", 40, 700, 16, 0),
                       fragment("More", 40, 500, 12, 1),
                       fragment("1", 64, 504, 8, 2)]),
            draft(4, [fragment("Notes", 40, 700, 16, 0),
                       fragment("Notes introduction.", 40, 650, 10, 1),
                       fragment("ALPHA", 40, 620, 10, 2),
                       fragment("1. First chapter definition", 50, 600, 10, 3),
                       fragment("BETA", 40, 560, 10, 4),
                       fragment("1. Second chapter definition", 50, 540, 10, 5)]),
            draft(5, [fragment("Index", 40, 700, 16, 0),
                       fragment("Unrelated index", 40, 650, 10, 1)])]


def test_chapter_endnotes_restart_and_stop_at_contents_heading():
    drafts = chapter_pages()
    drops = {}
    assert detect_endnotes(drafts, drops, 7) == 9
    assert [n.text for d in drafts for n in d.notes] == [
        "First chapter definition", "Second chapter definition"]
    assert 5 not in drops
    assert all(id(line) not in drops.get(4, set()) for line in drafts[3].groups[0]
               if line.text == "Notes introduction.")
    refs = [r[4] for d in drafts for g in d.groups for line in g for r in line.runs if len(r) > 4]
    assert refs == [7, 8]


def test_chapter_endnotes_reject_missing_toc_and_ambiguous_reference():
    for change in ("toc", "reference", "sequence"):
        drafts = chapter_pages()
        if change == "toc":
            drafts[0].groups = []
        elif change == "reference":
            drafts[1].note_markers *= 2
        else:
            for line in drafts[3].groups[0]:
                if line.text.startswith("1. Second"):
                    line.text = "2. Second chapter definition"
        assert detect_endnotes(drafts, {}, 1) == 1
        assert not any(d.notes for d in drafts)


def test_endnote_superscript_fits_inside_host_em_box():
    assert endnote_references([fragment("Body", 40, 500, 12, 0),
                               fragment("1", 64, 504, 8, 1)]) == [(1, "1")]
    assert endnote_references([fragment("Body", 40, 500, 12, 0),
                               fragment("1", 64, 505, 8, 1)]) == []


def test_endnote_reference_accepts_kerned_host_fragments_on_one_baseline():
    assert endnote_references([fragment("Body", 40, 500, 12, 0),
                               fragment(".", 63, 500, 12, 1),
                               fragment("1", 69, 504, 8, 2)]) == [(2, "1")]
    assert endnote_references([fragment("Body", 40, 500, 12, 0),
                               fragment("Other", 40, 501, 12, 1),
                               fragment("1", 69, 504, 8, 2)]) == []


def test_chapter_endnotes_fragment_budget_rejects_without_mutation(monkeypatch):
    import dochan.pdf.notes as notes
    drafts = chapter_pages()
    monkeypatch.setattr(notes, "MAX_NOTE_GEOMETRY_CHECKS", 1)
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 1
    assert drops == {}
    assert not any(d.notes for d in drafts)


def test_chapter_endnotes_preserve_margin_artifacts_and_cross_page_definition():
    drafts = chapter_pages()
    drafts[3].groups[0].append(assemble_lines([fragment("Proof line", 10, 530, 12, 10)])[0])
    continuation = draft(5, [fragment("Continued second definition", 50, 700, 10, 0),
                             fragment("Printed folio", 50, 20, 8, 1)])
    drafts[-1].page_number = 6
    drafts.insert(-1, continuation)
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 3
    assert drafts[3].notes[-1].text == "Second chapter definition\nContinued second definition"
    assert len(drops[5]) == 1
    assert all(id(line) not in drops[4] for line in drafts[3].groups[0] if line.text == "Proof line")


def test_endnote_character_budget_warns_and_preserves_body(monkeypatch):
    import dochan.pdf.notes as notes
    drafts = chapter_pages()
    monkeypatch.setattr(notes, "MAX_ENDNOTE_CHARACTERS", 10, raising=False)
    warnings, drops = [], {}
    assert detect_endnotes(drafts, drops, 1, warnings) == 1
    assert warnings and drops == {}
    assert not any(d.notes for d in drafts)


def test_chapter_toc_whitespace_is_linear():
    import time
    drafts = chapter_pages()
    drafts[0].groups[0].insert(1, assemble_lines([
        fragment("A" + " " * 16000 + "B", 40, 670, 10, 20)])[0])
    started = time.monotonic()
    assert detect_endnotes(drafts, {}, 1) == 3
    assert time.monotonic() - started < .5


def test_chapter_endnotes_include_smaller_continuation_in_body_column():
    drafts = chapter_pages()
    drafts[-1].page_number = 6
    drafts.insert(-1, draft(5, [fragment("Quoted continuation", 50, 700, 9, 0)]))
    assert detect_endnotes(drafts, {}, 1) == 3
    assert drafts[3].notes[-1].text.endswith("\nQuoted continuation")


def test_endnote_superscript_preserves_legacy_rise_range():
    drafts = pages()
    drafts[0] = draft(1, [fragment("Body", 40, 500, 12, 0),
                          fragment("1)", 64, 503.5, 9, 1)])
    assert detect_endnotes(drafts, {}, 1) == 2
    assert len(drafts[1].notes) == 1


def test_chapter_endnotes_preserve_chapter_subheadings():
    drafts = chapter_pages()
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 3
    headings = [line for line in drafts[3].groups[0] if line.text in ("ALPHA", "BETA")]
    assert len(headings) == 2
    assert all(id(line) not in drops.get(4, set()) for line in headings)


def test_chapter_endnotes_preserve_folios_and_outside_column_proof_marks():
    drafts = chapter_pages()
    margin = assemble_lines([fragment("Proof", 500, 520, 12, 20)])[0]
    folio = assemble_lines([fragment("4 NOTES", 50, 90, 8, 21)])[0]
    drafts[3].groups[0].extend([margin, folio])
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 3
    assert id(margin) not in drops[4]
    assert id(folio) not in drops[4]


def test_chapter_endnotes_include_small_top_paragraph_without_truncation():
    drafts = chapter_pages()
    drafts[-1].page_number = 6
    continuation = draft(5, [fragment("Quoted first line", 50, 750, 9, 0),
                             fragment("Quoted second line", 50, 738, 9, 1)])
    drafts.insert(-1, continuation)
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 3
    assert drafts[3].notes[-1].text == (
        "Second chapter definition\nQuoted first line\nQuoted second line")
    assert drops[5] == {id(line) for line in continuation.groups[0]}


def test_chapter_endnotes_defer_ambiguous_small_top_line_atomically():
    drafts = chapter_pages()
    drafts[-1].page_number = 6
    drafts.insert(-1, draft(5, [fragment("Possible header", 50, 750, 9, 0),
                                fragment("Separated text", 50, 700, 9, 1)]))
    original_runs = [list(line.runs) for d in drafts for group in d.groups for line in group]
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 1
    assert not any(d.notes for d in drafts)
    assert drops == {}
    assert [line.runs for d in drafts for group in d.groups for line in group] == original_runs


def test_chapter_endnotes_respect_detected_running_header_before_top_paragraph():
    from dochan.pdf.running import detect_running

    drafts = chapter_pages()
    drafts[-1].page_number = 6
    continuation = draft(5, [fragment("Running header", 50, 780, 8, 0),
                             fragment("Quoted first line", 50, 750, 9, 1),
                             fragment("Quoted second line", 50, 738, 9, 2)])
    drafts.insert(-1, continuation)
    header = continuation.groups[0][0]
    for d in drafts[:2]:
        d.groups[0].insert(0, assemble_lines([fragment("Running header", 50, 780, 8, 20)])[0])
    drops, _emitted = detect_running(drafts)
    assert id(header) in drops[5]
    assert detect_endnotes(drafts, drops, 1) == 3
    assert drafts[3].notes[-1].text == (
        "Second chapter definition\nQuoted first line\nQuoted second line")
    assert drops[5] == {id(line) for line in continuation.groups[0]}


def test_chapter_endnotes_include_small_paragraph_crossing_bottom_zone():
    for top in (82, 58):
        drafts = chapter_pages()
        drafts[-1].page_number = 6
        continuation = draft(5, [fragment("Quoted first line", 50, top, 9, 0),
                                 fragment("Quoted second line", 50, top - 12, 9, 1),
                                 fragment("Quoted last line", 50, top - 24, 9, 2)])
        drafts.insert(-1, continuation)
        drops = {}
        assert detect_endnotes(drafts, drops, 1) == 3
        assert drafts[3].notes[-1].text == (
            "Second chapter definition\nQuoted first line\nQuoted second line\nQuoted last line")
        assert drops[5] == {id(line) for line in continuation.groups[0]}


def test_chapter_endnotes_defer_ambiguous_small_bottom_line_atomically():
    drafts = chapter_pages()
    drafts[-1].page_number = 6
    drafts.insert(-1, draft(5, [fragment("Possible continuation", 50, 58, 9, 0)]))
    original_runs = [list(line.runs) for d in drafts for group in d.groups for line in group]
    drops = {}
    assert detect_endnotes(drafts, drops, 1) == 1
    assert not any(d.notes for d in drafts)
    assert drops == {}
    assert [line.runs for d in drafts for group in d.groups for line in group] == original_runs
