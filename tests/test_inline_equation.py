"""Synthetic inline equation placement and output contracts."""
import struct
import zipfile

from dochan.constants import (HWPTAG_CTRL_DATA, HWPTAG_CTRL_HEADER, HWPTAG_EQEDIT, HWPTAG_LIST_HEADER,
                              HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_TABLE)
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.equation import Equation
from dochan.ooxml.docx import DOCXReader
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text
from dochan.utils.heading_font import first_visible_font_size, body_font_size


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


def _docx(tmp_path, body, footnotes=None, comments=None):
    path = tmp_path / 'equation.docx'
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document %s><w:body>%s</w:body></w:document>' % (ns, body))
        if footnotes:
            archive.writestr('word/footnotes.xml', '<w:footnotes %s>%s</w:footnotes>' % (ns, footnotes))
        if comments:
            archive.writestr('word/comments.xml', '<w:comments %s>%s</w:comments>' % (ns, comments))
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


def test_hwp_adjacent_equations_keep_source_order_and_style():
    from dochan.hwp.section import _merge_inline_equations
    runs = [TextRun('앞뒤', bold=True, font_size_pt=13)]
    result = _merge_inline_equations(runs, [(1, Equation(script='x')),
                                            (1, Equation(script='y'))])
    assert ''.join(run.text for run in result) == '앞xy뒤'
    assert [run.equation.script for run in result if run.equation] == ['x', 'y']
    assert [(run.bold, run.font_size_pt) for run in result if run.equation] == [(True, 13)] * 2


def test_equation_font_is_not_heading_or_body_sample():
    eq = TextRun('x', equation=Equation(script='x'), font_size_pt=10)
    assert first_visible_font_size([eq, TextRun('글', font_size_pt=9)]) == 9
    paras = [Paragraph(runs=[TextRun('본문 내용' * 4, font_size_pt=9)]) for _ in range(3)]
    paras.append(Paragraph(runs=[eq, TextRun('짧은 문장', font_size_pt=14)]))
    assert body_font_size(paras) == 9


def test_cell_equation_and_empty_equation_markdown():
    from dochan.model.table import Table, Cell
    para = Paragraph(runs=[TextRun('A'), TextRun('x', equation=Equation(script='x')),
                           TextRun('B')])
    doc = Document(sections=[Section(elements=[Table(rows=[[Cell(paragraphs=[para])]])])])
    assert '$x$' in to_markdown(doc)
    empty = Document(sections=[Section(elements=[Paragraph(runs=[
        TextRun('A'), TextRun('', equation=Equation()), TextRun('B')])])])
    assert to_markdown(empty) == 'AB'


def test_equation_newline_and_json_contract():
    eq = Equation(script='x\r\ny')
    para = Paragraph(runs=[TextRun('A'), TextRun(eq.latex, equation=eq)])
    doc = Document(sections=[Section(elements=[para, eq])])
    assert '\n' not in to_markdown(doc).split('$')[1]
    items = to_dict(doc)['sections'][0]['elements']
    assert items[0]['runs'][1]['equation'].keys() == items[1].keys() - {'type'}


def test_hwp_bookmark_does_not_shift_equation_position():
    from dochan.hwp.section import _merge_inline_equations
    runs = _merge_inline_equations([TextRun('앞뒤')], [(1, Equation(script='x'))])
    runs.insert(0, TextRun('[bookmark: B1] '))
    assert ''.join(run.text for run in runs) == '[bookmark: B1] 앞x뒤'


def test_docx_equation_only_bookmark_and_note_stay_block(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    body = ('<w:p><w:bookmarkStart w:id="1" w:name="here"/>%s'
            '<w:r><w:footnoteReference w:id="1"/></w:r></w:p>') % eq
    doc = _docx(tmp_path, body)
    assert any(isinstance(item, Equation) for item in doc.sections[0].elements)


def test_docx_equation_link_suffix_is_visible(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    doc = _docx(tmp_path, '<w:p><w:hyperlink w:anchor="target">%s</w:hyperlink></w:p>' % eq)
    assert '<#target>' in to_markdown(doc)


def test_hwpx_compose_text_makes_equation_inline(tmp_path):
    eq = '<hp:equation><hp:pos treatAsChar="1"/><hp:script>x</hp:script></hp:equation>'
    body = '<hp:p><hp:run><hp:compose composeText="글"/>%s</hp:run></hp:p>' % eq
    doc = _hwpx(tmp_path, body)
    assert len([run for para in doc.find_all('paragraph') for run in para.runs if run.equation]) == 1


def test_hwpx_form_text_makes_equation_inline(tmp_path):
    eq = '<hp:equation><hp:pos treatAsChar="1"/><hp:script>x</hp:script></hp:equation>'
    body = '<hp:p><hp:run><hp:edit><hp:text>글</hp:text></hp:edit>%s</hp:run></hp:p>' % eq
    doc = _hwpx(tmp_path, body)
    assert len([run for para in doc.find_all('paragraph') for run in para.runs if run.equation]) == 1


def test_hwp_adjacent_controls_bookmark_and_failed_equation_keep_offsets(monkeypatch):
    marker = struct.pack('<H', 11) + b'deqe' + bytes(8) + struct.pack('<H', 11)
    text = '앞'.encode('utf-16-le') + marker * 3 + '뒤'.encode('utf-16-le')
    name = 'B1'.encode('utf-16-le')
    bookmark = (bytes(10) + struct.pack('<H', len(name) // 2) + name)
    data = (_record(HWPTAG_PARA_HEADER, 0, bytes(22))
            + _record(HWPTAG_PARA_TEXT, 1, text)
            + _record(HWPTAG_CTRL_HEADER, 1, b'mkob' + bytes(40))
            + _record(HWPTAG_CTRL_DATA, 2, bookmark))
    for script in ('x', 'y', 'z'):
        encoded = script.encode('utf-16-le')
        data += (_record(HWPTAG_CTRL_HEADER, 1, b'deqe' + struct.pack('<I', 1) + bytes(36))
                 + _record(HWPTAG_EQEDIT, 2, bytes(4) + struct.pack('<H', len(script)) + encoded))
    parser = SectionParser()
    original = parser._parse_control
    seen = [0]

    def fail_first(node):
        if node['record'].data[:4] == b'deqe':
            seen[0] += 1
            if seen[0] == 1:
                return None
        return original(node)

    monkeypatch.setattr(parser, '_parse_control', fail_first)
    section = parser.parse_stream(data, is_compressed=False)
    para, = section.elements
    assert para.text == '[bookmark: B1] 앞yz뒤'
    assert [run.equation.script for run in para.runs if run.equation] == ['y', 'z']


def test_docx_equation_inherits_enclosing_run_format(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    body = ('<w:p><w:r><w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'
            '<w:t>A</w:t>%s<w:t>B</w:t></w:r></w:p>') % eq
    para, = _docx(tmp_path, body).sections[0].elements
    formula, = [run for run in para.runs if run.equation]
    assert (formula.bold, formula.font_size_pt) == (True, 14)


def test_hwpx_equation_inherits_enclosing_run_format():
    from dochan.utils.safe_xml import fromstring
    parser = HWPXParser()
    parser._char_shapes_by_id = {7: {
        'bold': True, 'italic': False, 'underline': False,
        'strikeout': False, 'size_pt': 14}}
    run = fromstring((' <hp:run xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
                      'charPrIDRef="7"><hp:t>A</hp:t><hp:equation>'
                      '<hp:pos treatAsChar="1"/><hp:script>x</hp:script>'
                      '</hp:equation></hp:run>').strip())
    formula, = [item for item in parser._parse_run_with_objects(run, True)
                if isinstance(item, TextRun) and item.equation]
    assert (formula.bold, formula.font_size_pt) == (True, 14)


def test_docx_direct_equation_inherits_neighbour_text_format(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    body = ('<w:p><w:r><w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'
            '<w:t>A</w:t></w:r>%s</w:p>') % eq
    para, = _docx(tmp_path, body).sections[0].elements
    formula, = [run for run in para.runs if run.equation]
    assert (formula.bold, formula.font_size_pt) == (True, 14)


def test_docx_equation_comment_range_end_keeps_annotation(tmp_path):
    eq = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>'
    body = ('<w:p><w:r><w:t>A</w:t></w:r>'
            '<w:commentRangeStart w:id="1"/>%s<w:commentRangeEnd w:id="1"/>'
            '</w:p>') % eq
    comment = '<w:comment w:id="1"><w:p><w:r><w:t>설명</w:t></w:r></w:p></w:comment>'
    doc = _docx(tmp_path, body, comments=comment)
    assert '[comment 1: 설명]' in to_markdown(doc)
    para = next(item for item in doc.sections[0].elements if isinstance(item, Paragraph))
    assert para.runs[-1].equation is None


def test_probe_keeps_hashes_without_document_context(tmp_path):
    from scripts.probe_inline_equation import _summary
    eq = '<hp:equation><hp:pos treatAsChar="1"/><hp:script>x</hp:script></hp:equation>'
    _hwpx(tmp_path, '<hp:p><hp:run><hp:t>A</hp:t>%s</hp:run></hp:p>' % eq)
    result = _summary(tmp_path / 'equation.hwpx')
    assert result['inline'] == 1
    assert len(result['inline_paragraph_hashes']) == 1
    assert 'contexts' not in result


def test_hwpx_control_equation_inherits_following_text_style():
    from dochan.utils.safe_xml import fromstring
    parser = HWPXParser()
    parser._char_shapes_by_id = {7: {
        'bold': True, 'italic': False, 'underline': False,
        'strikeout': False, 'size_pt': 14}}
    paragraph = fromstring(
        '<hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:ctrl><hp:equation><hp:pos treatAsChar="1"/>'
        '<hp:script>x</hp:script></hp:equation></hp:ctrl>'
        '<hp:run charPrIDRef="7"><hp:t>글</hp:t></hp:run></hp:p>')
    para, = parser._parse_paragraph_elem(paragraph)
    formula, = [run for run in para.runs if run.equation]
    assert (formula.bold, formula.font_size_pt) == (True, 14)
