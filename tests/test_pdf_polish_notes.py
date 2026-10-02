"""하단 영역의 각주 연속 줄과 독립 바닥글을 구분한다."""
import pytest

from dochan.output.markdown import to_markdown
from dochan.pdf.content import Fragment
from dochan.pdf.notes import detect_notes
from dochan.pdf.paths import Segment
from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf


def _fragment(text, y, size, order, x=40):
    return Fragment(x, y, len(text) * size / 2, size, text, size / 3,
                    order=order)


@pytest.mark.parametrize("bottom", [0, 20])
@pytest.mark.parametrize("third_y", [50, 60])
def test_note_observed_spacing_continues_into_footer_zone(bottom, third_y):
    fragments = [_fragment("Body", bottom + 500, 12, 0),
                 _fragment("1)", bottom + 502.5, 9, 1, x=64),
                 _fragment("1) Detail", bottom + third_y + 22, 9, 2),
                 _fragment("Continued", bottom + third_y + 11, 9, 3),
                 _fragment("Final line", bottom + third_y, 9, 4),
                 _fragment("Footer", bottom + third_y - 17, 9, 5)]
    notes, consumed, references, following = detect_notes(
        fragments, [Segment(40, bottom + third_y + 37,
                            180, bottom + third_y + 37)],
        (bottom, bottom + 800), 1)
    assert [note.text for note in notes] == ["Detail\nContinued\nFinal line"]
    assert consumed == {2, 3, 4}
    assert references == {1: 1} and following == 2


def test_reader_preserves_wrapped_note_below_sixty_points(tmp_path):
    content = (b"40 87 m 180 87 l S "
               b"BT /F1 12 Tf 40 500 Td (Body) Tj ET "
               b"BT /F1 12 Tf 40 400 Td (More text here) Tj ET "
               b"BT /F1 9 Tf 64 502.5 Td (1\\051) Tj ET "
               b"BT /F1 9 Tf 40 72 Td (1\\051 Detail note that is long and wraps) Tj ET "
               b"BT /F1 9 Tf 40 61 Td (onto a second line of the note) Tj ET "
               b"BT /F1 9 Tf 40 50 Td (and a third line ending here.) Tj ET")
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 600 800] "
           "/Resources << /Font << /F1 5 0 R >> >> >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>",
        4: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    path = tmp_path / "wrapped-note.pdf"
    path.write_bytes(_build_pdf(objects))
    document = PDFReader().read(str(path))
    assert [note.text for note in document.find_all("footnote")] == [
        "Detail note that is long and wraps\nonto a second line of the note\n"
        "and a third line ending here."]
    markdown = to_markdown(document)
    assert markdown.count("[^1]") == 2
    assert markdown.count("and a third line ending here.") == 1
    assert markdown.index("[^1]:") < markdown.index("and a third line ending here.")
