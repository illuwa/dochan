"""Simple-font ToUnicode spaces must use their own measured glyph width."""
import pytest

from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from dochan.pdf.objects import PDFRef
from dochan.output.plain_text import to_plain_text
from test_pdf_structure import _build_pdf, _minimal_objects


def _pdf(mapping, widths, subtype='TrueType'):
    content = b'BT /F1 10 Tf 72 720 Td <01> Tj 12 0 Td <02> Tj ET'
    objects = _minimal_objects(content)
    objects[4] = ('<< /Type /Font /Subtype /%s /BaseFont /Subset '
                  '/FirstChar 0 /LastChar 32 /Widths [%s] /ToUnicode 6 0 R >>'
                  % (subtype, ' '.join(str(w) for w in widths)))
    cmap = ('1 begincodespacerange <00> <ff> endcodespacerange '
            '%d beginbfchar %s endbfchar' % (len(mapping), ' '.join(
                '<%02x> <%04x>' % (code, unicode) for code, unicode in mapping))).encode()
    objects[6] = b'<< /Length %d >>\nstream\n%s\nendstream' % (len(cmap), cmap)
    return _build_pdf(objects)


@pytest.mark.parametrize('subtype', ['TrueType', 'Type1', 'MMType1'])
def test_simple_font_recovers_space_width_and_word_boundary(tmp_path, subtype):
    widths = [250] + [1000] * 32
    data = _pdf([(0, 32), (1, 0xac00), (2, 0xb098), (32, 0xb2e4)], widths, subtype)
    path = tmp_path / 'space.pdf'
    path.write_bytes(data)
    pdf = PDFFile(data)
    info = PDFReader()._build_font_info(pdf, 'F1', pdf.resolve(PDFRef(4, 0)))
    assert info.space_code == 0
    assert to_plain_text(PDFReader().read(str(path))).strip() == '가 나'


@pytest.mark.parametrize('mapping,widths', [
    ([(1, 0xac00), (2, 0xb098)], [1000] * 33),
    ([(0, 32), (3, 32), (1, 0xac00), (2, 0xb098)], [250] + [1000] * 32),
    ([(256, 32), (1, 0xac00), (2, 0xb098)], [250] + [1000] * 32),
])
def test_missing_ambiguous_or_non_byte_space_keeps_default(mapping, widths):
    pdf = PDFFile(_pdf(mapping, widths))
    info = PDFReader()._build_font_info(pdf, 'F1', pdf.resolve(PDFRef(4, 0)))
    assert info.space_code == 32
