from dochan.model.document import Paragraph, TextRun
from dochan.model.table import Cell, Table
from scripts.probe_pdf_table_boundaries import boundary_matches, compact, borderless_texts


def _table(text):
    return Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun(text=text)])], col=0)]])


def test_boundary_probe_requires_one_answer_cell_and_distinct_fragments():
    assert boundary_matches(_table("first half"), _table("second half"),
                            [compact("first half second half")]) == 1
    assert boundary_matches(_table("first half"), _table("second half"),
                            [compact("first half"), compact("second half")]) == 0
    assert boundary_matches(_table("repeated"), _table("repeated"),
                            [compact("repeated repeated")]) == 0


def test_boundary_probe_rejects_ambiguous_answer_and_column_change():
    left, right = _table("left"), _table("right")
    assert boundary_matches(left, right, ["leftright", "leftright"]) == 0
    right.rows[0][0].col = 1
    assert boundary_matches(left, right, ["leftright"]) == 0


def test_borderless_probe_requires_all_four_explicit_none_borders(tmp_path):
    import zipfile

    header = b'''<root><borderFill id="1"><leftBorder type="NONE"/>
    <rightBorder type="NONE"/><topBorder type="NONE"/><bottomBorder type="NONE"/>
    </borderFill><borderFill id="2"><leftBorder type="NONE"/></borderFill></root>'''
    section = b'''<root><tbl rowCnt="1" colCnt="1"><tr><tc borderFillIDRef="1">
    <p><t>Visible text</t></p></tc></tr></tbl>
    <tbl rowCnt="1" colCnt="1"><tr><tc borderFillIDRef="2"><p><t>Unknown</t></p>
    </tc></tr></tbl></root>'''
    path = tmp_path / "borderless.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)
    assert borderless_texts(str(path)) == ["Visibletext"]


def test_borderless_one_cell_pdf_stays_a_paragraph(tmp_path):
    from dochan.pdf.reader import PDFReader
    from test_pdf_structure import _build_pdf, _minimal_objects

    content = b"BT /F1 12 Tf 72 720 Td (A single unruled text box) Tj ET"
    path = tmp_path / "plain.pdf"
    path.write_bytes(_build_pdf(_minimal_objects(content)))
    for enabled in (False, True):
        document = PDFReader(text_tables=enabled).read(str(path))
        assert not document.find_all("table")
        assert document.find_all("paragraph")[0].text == "A single unruled text box"


def test_boundary_probe_matches_synthetic_pdf_before_row_append(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from dochan import Dochan
    from dochan.model.document import Document, Section
    from scripts import probe_pdf_table_boundaries as probe
    from test_pdf_reader import _ruled
    from test_pdf_structure import _build_pdf

    contents = [_ruled(60, 120, ("Heading", "Other"), ("first half", "Value")),
                _ruled(80, 140, ("second half", "Next"), ("End", "Finish"))]
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 /MediaBox [0 0 200 200] "
           "/Resources << /Font << /F1 20 0 R >> >> >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 10 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 11 0 R >>",
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for number, content in enumerate(contents, 10):
        objects[number] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
    path = tmp_path / "split.pdf"
    path.write_bytes(_build_pdf(objects))
    answer = Document(sections=[Section(elements=[_table("first half second half")])])
    monkeypatch.setattr(probe, "Dochan", lambda source: SimpleNamespace(doc=answer)
                        if source == "answer.hwpx" else Dochan(source))
    monkeypatch.setattr(probe, "borderless_texts", lambda _source: [])
    result = probe.inspect_pair("answer.hwpx", str(path))
    assert result["boundary_exact_cell_positives"] == 1
    assert result["accepted_boundary_exact_cell_positives"] == 1


def test_probe_failure_does_not_disclose_internal_path_or_text(monkeypatch, capsys):
    from scripts import probe_pdf_table_boundaries as probe

    monkeypatch.setattr(probe, "find_pairs", lambda _directory: [("secret", "h", "p")])

    def fail(*_args):
        raise ValueError("private document contents")

    monkeypatch.setattr(probe, "inspect_pair", fail)
    assert probe.main(["pairs"]) == 1
    output = capsys.readouterr().out
    assert '"failed_pairs": 1' in output
    assert "secret" not in output
    assert "private document contents" not in output


def test_boundary_edge_probe_does_not_count_duplicate_strokes_twice():
    from dochan.pdf.paths import Segment
    from scripts.probe_pdf_table_boundaries import _closed_edge

    half = Segment(0, 10, 50, 10)
    assert not _closed_edge([half, half], 0, 100, 10, 1.5)
    assert _closed_edge([half, half, Segment(50, 10, 100, 10)], 0, 100, 10, 1.5)
