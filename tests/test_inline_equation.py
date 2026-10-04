"""Synthetic inline equation placement and output contracts."""
import struct
import zipfile

from dochan.constants import (HWPTAG_CTRL_HEADER, HWPTAG_EQEDIT, HWPTAG_LIST_HEADER,
                              HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_TABLE)
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.equation import Equation
from dochan.ooxml.docx import DOCXReader
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text


def _record(tag, level, data):
    return struct.pack('<I', (len(data) << 20) | (level << 10) | tag) + data


def _hwp_paragraph(before, after, inline=True):
    marker = struct.pack('<H', 11) + b'deqe' + bytes(8) + struct.pack('<H', 11)
    text = before.encode('utf-16-le') + marker + after.encode('utf-16-le') + struct.pack('<H', 13)
    script = 'a over b'.encode('utf-16-le')
    equation = bytes(4) + struct.pack('<H', len(script) // 2) + script
    flags = 1 if inline else 0  # object common property bit 0: treat as character
    data = (_record(HWPTAG_PARA_HEADER, 0, bytes(22))
            + _record(HWPTAG_PARA_TEXT, 1, text)
            + _record(HWPTAG_CTRL_HEADER, 1, b'deqe' + struct.pack('<I', flags) + bytes(36))
            + _record(HWPTAG_EQEDIT, 2, equation))
    return SectionParser().parse_stream(data, is_compressed=False)


def _hwpx(tmp_path, body):
    path = tmp_path / 'equation.hwpx'
    ns = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
          'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('Contents/section0.xml', '<hs:sec %s>%s</hs:sec>' % (ns, body))
    return HWPXParser().parse(path)


def _docx(tmp_path, body, footnotes=None):
    path = tmp_path / 'equation.docx'
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document %s><w:body>%s</w:body></w:document>' % (ns, body))
        if footnotes:
            archive.writestr('word/footnotes.xml', '<w:footnotes %s>%s</w:footnotes>' % (ns, footnotes))
    return DOCXReader().read(str(path))


def test_hwp_inline_equation_follows_control_position_and_block_rule():
    section = _hwp_paragraph('앞', '뒤')
    para, = section.elements
    assert para.text == r'앞\frac{a}{b}뒤'
    assert [bool(run.equation) for run in para.runs] == [False, True, False]
    assert to_markdown(Document(sections=[section])) == r'앞$\frac{a}{b}$뒤'
    assert [type(item).__name__ for item in _hwp_paragraph(' ', ' ').elements] == ['Equation']
    assert [type(item).__name__ for item in _hwp_paragraph('앞', '뒤', inline=False).elements] == ['Paragraph', 'Equation']


def test_hwp_table_cell_inline_and_display_equations():
    marker = struct.pack('<H', 11) + b'deqe' + bytes(8) + struct.pack('<H', 11)
    equation_script = 'x'.encode('utf-16-le')
    equation = bytes(4) + struct.pack('<H', len(equation_script) // 2) + equation_script
    prefix = (_record(HWPTAG_PARA_HEADER, 0, bytes(22))
              + _record(HWPTAG_PARA_TEXT, 1, '표'.encode('utf-16-le') + struct.pack('<H', 13))
              + _record(HWPTAG_CTRL_HEADER, 1, b' lbt' + bytes(4))
              + _record(HWPTAG_TABLE, 2, bytes(4) + struct.pack('<HH', 1, 1))
              + _record(HWPTAG_LIST_HEADER, 2, bytes(8) + struct.pack('<HHHH', 0, 0, 1, 1)))
    for before, after, flags, expected in [('A', 'B', 1, ['Paragraph']),
                                           ('', '', 0, ['Equation'])]:
        text = before.encode('utf-16-le') + marker + after.encode('utf-16-le') + struct.pack('<H', 13)
        data = (prefix + _record(HWPTAG_PARA_HEADER, 2, bytes(22))
                + _record(HWPTAG_PARA_TEXT, 3, text)
                + _record(HWPTAG_CTRL_HEADER, 3, b'deqe' + struct.pack('<I', flags) + bytes(36))
                + _record(HWPTAG_EQEDIT, 4, equation))
        section = SectionParser().parse_stream(data, is_compressed=False)
        cell_items = section.elements[-1].rows[0][0].paragraphs
        assert [type(item).__name__ for item in cell_items] == expected
        if flags:
            assert cell_items[0].text == 'AxB'


def test_hwpx_inline_equation_preserves_sentence_and_block_rule(tmp_path):
    eq = '<hp:equation><hp:pos treatAsChar="1"/><hp:script>a over b</hp:script></hp:equation>'
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % eq
    doc = _hwpx(tmp_path, body)
    para, = doc.sections[0].elements
    assert para.text == r'앞\frac{a}{b}뒤'
    assert to_markdown(doc) == r'앞$\frac{a}{b}$뒤'
    assert [type(item).__name__ for item in _hwpx(tmp_path, '<hp:p><hp:run>%s</hp:run></hp:p>' % eq).sections[0].elements] == ['Equation']
    block = eq.replace('treatAsChar="1"', 'treatAsChar="0"')
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % block
    assert [type(item).__name__ for item in _hwpx(tmp_path, body).sections[0].elements] == ['Paragraph', 'Equation', 'Paragraph']


def test_docx_inline_equation_preserves_sentence_and_display_math(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    body = '<w:p><w:r><w:t>앞</w:t></w:r>%s<w:r><w:t>뒤</w:t></w:r></w:p>' % eq
    doc = _docx(tmp_path, body)
    para, = doc.sections[0].elements
    assert para.text == '앞x뒤'
    assert to_markdown(doc) == '앞$x$뒤'
    assert [type(item).__name__ for item in _docx(tmp_path, '<w:p>%s</w:p>' % eq).sections[0].elements] == ['Equation']
    display = '<w:p><w:r><w:t>앞</w:t></w:r><m:oMathPara>%s</m:oMathPara></w:p>' % eq
    assert [type(item).__name__ for item in _docx(tmp_path, display).sections[0].elements] == ['Paragraph', 'Equation']


def test_equation_run_output_contract():
    equation = Equation(script='a over b', script_format='hwp')
    para = Paragraph(runs=[TextRun('앞'), TextRun(equation.latex, bold=True, equation=equation), TextRun('뒤')])
    doc = Document(sections=[Section(elements=[para])])
    assert to_markdown(doc) == r'앞$\frac{a}{b}$뒤'
    assert to_plain_text(doc) == r'앞\frac{a}{b}뒤'
    runs = to_dict(doc)['sections'][0]['elements'][0]['runs']
    assert 'equation' not in runs[0]
    assert runs[1]['equation'] == {'latex': r'\frac{a}{b}', 'script': 'a over b', 'script_format': 'hwp'}


def test_docx_table_footnote_and_textbox_inline_math(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    cell = '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r>%s<w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>' % eq
    textbox = '<w:p><w:r><w:drawing><w:txbxContent><w:p><w:r><w:t>C</w:t></w:r>%s<w:r><w:t>D</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r></w:p>' % eq
    note = '<w:footnote w:id="1"><w:p><w:r><w:t>E</w:t></w:r>%s<w:r><w:t>F</w:t></w:r></w:p></w:footnote>' % eq
    body = cell + textbox + '<w:p><w:r><w:footnoteReference w:id="1"/></w:r></w:p>'
    doc = _docx(tmp_path, body, note)
    texts = [para.text for para in doc.find_all('paragraph')]
    assert 'AxB' in texts
    assert any('CxD' in text for text in texts)
    assert 'ExF' in texts
    assert len([equation for equation in doc.find_all('equation') if equation.latex == 'x']) == 3


def test_hwpx_table_cell_inline_math(tmp_path):
    eq = '<hp:equation><hp:pos treatAsChar="1"/><hp:script>x</hp:script></hp:equation>'
    cell = ('<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
            '<hp:subList><hp:p><hp:run><hp:t>A</hp:t>%s<hp:t>B</hp:t>'
            '</hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/>'
            '<hp:cellSpan colSpan="1" rowSpan="1"/></hp:tc></hp:tr></hp:tbl>') % eq
    doc = _hwpx(tmp_path, '<hp:p><hp:run>%s</hp:run></hp:p>' % cell)
    assert 'AxB' in [para.text for para in doc.find_all('paragraph')]


def test_hwpx_footnote_inline_math(tmp_path):
    eq = '<hp:equation><hp:pos treatAsChar="1"/><hp:script>x</hp:script></hp:equation>'
    note = ('<hp:ctrl><hp:footNote><hp:subList><hp:p><hp:run>'
            '<hp:t>A</hp:t>%s<hp:t>B</hp:t>'
            '</hp:run></hp:p></hp:subList></hp:footNote></hp:ctrl>') % eq
    doc = _hwpx(tmp_path, '<hp:p><hp:run><hp:t>본문</hp:t>%s</hp:run></hp:p>' % note)
    assert 'AxB' in [para.text for para in doc.find_all('paragraph')]
    assert len(doc.find_all('equation')) == 1
