"""각주 정의 조각과 바닥글 경계를 독립적으로 검증한다."""
import pytest

from dochan.output.markdown import to_markdown
from dochan.pdf.content import Fragment
from dochan.pdf.notes import detect_notes
from dochan.pdf.paths import Segment
from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf


def _fragment(text, x, y, size, order):
    return Fragment(x, y, len(text) * size / 2, size, text, size / 3,
                    order=order)


def _body():
    return [_fragment("Body", 40, 500, 12, 0),
            _fragment("1)", 64, 502.5, 9, 1)]


def test_note_consumes_exact_fragments_when_definition_font_sizes_differ():
    fragments = _body() + [_fragment("1) ", 40, 100, 10.5, 2),
                           _fragment("Detail", 56, 100, 10, 3)]
    notes, consumed, references, following = detect_notes(
        fragments, [Segment(40, 115, 180, 115)], (0, 800), 1)
    assert notes[0].text == "Detail"
    assert consumed == {2, 3}
    assert references == {1: 1} and following == 2


@pytest.mark.parametrize("footer", ["ACME Annual Report", "Page 3 of 10"])
def test_note_continuation_does_not_consume_same_size_footer(footer):
    fragments = _body() + [_fragment("1) Detail", 40, 62, 9, 2),
                           _fragment(footer, 40, 48, 9, 3)]
    notes, consumed, _references, _following = detect_notes(
        fragments, [Segment(40, 77, 180, 77)], (0, 800), 1)
    assert notes[0].text == "Detail"
    assert consumed == {2}


def test_note_continuation_requires_matching_left_margin():
    fragments = _body() + [_fragment("1) Detail", 40, 130, 10.5, 2),
                           _fragment("Unrelated", 200, 115, 10.5, 3)]
    notes, consumed, _references, _following = detect_notes(
        fragments, [Segment(40, 145, 180, 145)], (0, 800), 1)
    assert notes[0].text == "Detail"
    assert consumed == {2}


def test_note_continuation_accepts_observed_definition_text_indent():
    fragments = _body() + [_fragment("1)", 40, 130, 10.5, 2),
                           _fragment("Detail", 55, 130, 10.5, 3),
                           _fragment("Continued", 55.5, 115, 10.5, 4)]
    notes, consumed, _references, _following = detect_notes(
        fragments, [Segment(40, 145, 180, 145)], (0, 800), 1)
    assert notes[0].text == "Detail\nContinued"
    assert consumed == {2, 3, 4}


def test_note_continuation_requires_consistent_observed_spacing():
    fragments = _body() + [_fragment("1) Detail", 40, 150, 10.5, 2),
                           _fragment("Continued", 40, 140, 10.5, 3),
                           _fragment("Unrelated", 40, 120, 10.5, 4)]
    notes, consumed, _references, _following = detect_notes(
        fragments, [Segment(40, 165, 180, 165)], (0, 800), 1)
    assert notes[0].text == "Detail\nContinued"
    assert consumed == {2, 3}


def test_pdf_reader_mixed_size_note_definition_is_output_once(tmp_path):
    content = (b"40 115 m 180 115 l S "
               b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
               b"BT /F1 9 Tf 64 502.5 Td (1\\051) Tj ET "
               b"BT /F1 10.5 Tf 40 100 Td (1\\051 ) Tj ET "
               b"BT /F1 10 Tf 56 100 Td (Detail) Tj ET")
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 600 800] "
           "/Resources << /Font << /F1 5 0 R >> >> >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>",
        4: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
           "/FirstChar 0 /Widths [" + "500 " * 256 + "] >>",
    }
    path = tmp_path / "mixed-size-note.pdf"
    path.write_bytes(_build_pdf(objects))
    document = PDFReader().read(str(path))
    markdown = to_markdown(document)
    assert markdown.count("Detail") == 1
    assert "Body[^1]" in markdown
    assert "[^1]: Detail" in markdown


def test_pdf_reader_running_footer_stays_outside_note_definitions(tmp_path):
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        7: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
           "/FirstChar 0 /Widths [" + "500 " * 256 + "] >>",
    }
    kids = []
    for page in range(4):
        content = (b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
                   b"BT /F1 12 Tf 40 400 Td (More text) Tj ET ")
        if page < 3:
            content += (b"BT /F1 9 Tf 64 502.5 Td (1\\051) Tj ET "
                        b"40 77 m 180 77 l S "
                        b"BT /F1 9 Tf 40 62 Td (1\\051 Detail) Tj ET ")
        content += b"BT /F1 9 Tf 40 48 Td (ACME Annual Report) Tj ET"
        page_id = 10 + 2 * page
        objects[page_id] = "<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (page_id + 1)
        objects[page_id + 1] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
        kids.append("%d 0 R" % page_id)
    objects[2] = ("<< /Type /Pages /Kids [%s] /Count 4 /MediaBox [0 0 600 800] "
                  "/Resources << /Font << /F1 7 0 R >> >> >>") % " ".join(kids)
    path = tmp_path / "notes-running-footer.pdf"
    path.write_bytes(_build_pdf(objects))
    document = PDFReader().read(str(path))
    assert [note.text for note in document.find_all("footnote")] == ["Detail"] * 3
    assert any(footer.text == "ACME Annual Report"
               for footer in document.find_all("footer"))
