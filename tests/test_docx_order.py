"""DOCX의 XML 앵커 순서를 재현하는 합성 픽스처다."""
import pytest

from dochan.model.document import Paragraph
from dochan.model.equation import Equation
from dochan.ooxml.docx import DOCXReader
from test_docx_remaining import write_docx, paragraph

M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
MATH = '<m:oMath xmlns:m="%s"><m:r><m:t>x</m:t></m:r></m:oMath>' % M


def read(tmp_path, body):
    path = tmp_path / 'order.docx'
    write_docx(path, body)
    return DOCXReader().read(str(path))


def test_docx_carriage_return_keeps_word_boundary(tmp_path):
    doc = read(tmp_path, '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Before</w:t>'
               '<w:cr/><w:t>After</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
    assert doc.find_all('paragraph')[0].text == 'Before\nAfter'


@pytest.mark.parametrize('container', ['body', 'cell', 'textbox'])
def test_docx_equations_follow_exact_inline_anchor(tmp_path, container):
    body = '<w:p>' + MATH + '<w:r><w:t>middle</w:t></w:r>' + MATH + '</w:p>'
    if container == 'cell':
        body = '<w:tbl><w:tr><w:tc>' + body + '</w:tc></w:tr></w:tbl>'
    elif container == 'textbox':
        body = '<w:p><w:r><w:drawing><w:txbxContent>' + body + '</w:txbxContent></w:drawing></w:r></w:p>'
    doc = read(tmp_path, body)
    elements = doc.sections[0].elements
    if container == 'cell':
        elements = elements[0].rows[0][0].paragraphs
    assert [type(e) for e in elements] == [Equation, Paragraph, Equation]
    assert elements[1].text.strip() == 'middle'
    assert [e.latex for e in doc.find_all('equation')] == ['x', 'x']


def test_docx_equations_ignore_deleted_and_inactive_alternatives(tmp_path):
    body = '<w:p><w:del>' + MATH + '</w:del><mc:AlternateContent xmlns:mc="%s">' % MC
    body += '<mc:Choice>' + MATH + '</mc:Choice><mc:Fallback>' + MATH + '</mc:Fallback></mc:AlternateContent></w:p>'
    doc = read(tmp_path, body)
    assert len(doc.find_all('equation')) == 1


def test_docx_hyperlink_content_control_keeps_anchor_text(tmp_path):
    doc = read(tmp_path, '<w:p><w:hyperlink w:anchor="target"><w:sdt><w:sdtContent>'
               '<w:r><w:t>label</w:t></w:r></w:sdtContent></w:sdt></w:hyperlink></w:p>')
    assert doc.find_all('paragraph')[0].text == 'label <#target>'


def test_docx_textbox_table_keeps_structure_at_anchor(tmp_path):
    body = '<w:p><w:r><w:t>before</w:t><w:drawing><w:txbxContent>'
    body += paragraph('box') + '<w:tbl><w:tr><w:tc>' + paragraph('cell')
    body += '</w:tc></w:tr></w:tbl>' + paragraph('tail')
    body += '</w:txbxContent></w:drawing><w:t>after</w:t></w:r></w:p>'
    doc = read(tmp_path, body)
    assert len(doc.find_all('table')) == 1
    elements = doc.sections[0].elements
    assert elements[0].text.strip() == 'before box'
    assert elements[1].rows[0][0].text == 'cell'
    assert elements[2].text.strip() == 'tail after'


def test_docx_numbering_in_cells_follows_body_counter(tmp_path):
    props = '<w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr>'
    numbered = '<w:p>' + props + '<w:r><w:t>item</w:t></w:r></w:p>'
    numbering = ('<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
        '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')
    path = tmp_path / 'numbered.docx'
    write_docx(path, numbered + '<w:tbl><w:tr><w:tc>' + numbered + '</w:tc></w:tr></w:tbl>' + numbered,
               {'word/numbering.xml': numbering})
    doc = DOCXReader().read(str(path))
    assert [p.text for p in doc.find_all('paragraph')] == ['1. item', '2. item', '3. item']


@pytest.mark.parametrize('in_cell', [False, True])
def test_docx_block_comment_range_end_emits_annotation_once(tmp_path, in_cell):
    path = tmp_path / 'block-comment.docx'
    comments = ('<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:comment w:id="0">' + paragraph('explanation') + '</w:comment></w:comments>')
    body = paragraph('before') + '<w:commentRangeEnd w:id="0"/>'
    body += '<w:p><w:r><w:commentReference w:id="0"/><w:t>after</w:t></w:r></w:p>'
    if in_cell:
        body = '<w:tbl><w:tr><w:tc>' + body + '</w:tc></w:tr></w:tbl>'
    write_docx(path, body, {'word/comments.xml': comments})
    doc = DOCXReader().read(str(path))
    elements = doc.sections[0].elements
    if in_cell:
        elements = elements[0].rows[0][0].paragraphs
    assert [e.text for e in elements if isinstance(e, Paragraph)] == ['before', '[comment 1: explanation]', 'after']


@pytest.mark.parametrize('kind', ['footnote', 'header'])
def test_docx_story_textbox_table_is_not_lost(tmp_path, kind):
    from test_docx_remaining import R, W
    path = tmp_path / 'story-table.docx'
    box = '<w:p><w:r><w:drawing><w:txbxContent>' + paragraph('BOX')
    box += '<w:tbl><w:tr><w:tc>' + paragraph('CELL') + '</w:tc></w:tr></w:tbl>'
    box += '</w:txbxContent></w:drawing></w:r></w:p>'
    if kind == 'footnote':
        body = '<w:p><w:r><w:footnoteReference w:id="1"/></w:r></w:p>'
        parts = {'word/footnotes.xml': '<w:footnotes xmlns:w="%s"><w:footnote w:id="1">%s</w:footnote></w:footnotes>' % (W, box)}
        rels = ''
    else:
        body = paragraph('body') + '<w:sectPr><w:headerReference r:id="h"/></w:sectPr>'
        parts = {'word/header1.xml': '<w:hdr xmlns:w="%s">%s</w:hdr>' % (W, box)}
        rels = '<Relationship Id="h" Type="%s/header" Target="header1.xml"/>' % R
    write_docx(path, body, parts, rels)
    doc = DOCXReader().read(str(path))
    story = doc.find_all(kind)[0]
    assert story.text == 'BOX\n\nCELL' or story.text == 'BOX\nCELL'
    assert len(doc.find_all('table')) == 1


def test_docx_numbered_host_precedes_numbered_textbox(tmp_path):
    from test_docx_remaining import W
    path = tmp_path / 'numbered-box.docx'
    props = '<w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr>'
    numbering = '<w:numbering xmlns:w="%s"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="%%1."/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>' % W
    body = '<w:p>' + props + '<w:r><w:t>HOST</w:t><w:drawing><w:txbxContent><w:p>'
    body += props + '<w:r><w:t>BOX</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r></w:p>'
    write_docx(path, body, {'word/numbering.xml': numbering})
    doc = DOCXReader().read(str(path))
    assert doc.find_all('paragraph')[0].text == '1. HOST 2. BOX'
    import zipfile
    from scripts.verify_ooxml_docx import logical_body_text, align_tokens
    with zipfile.ZipFile(path) as package:
        assert align_tokens(logical_body_text(package), '1. HOST 2. BOX')['exact']
