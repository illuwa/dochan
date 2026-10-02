"""DOCX 차트 앵커·캡션·읽기 순서의 합성 회귀 테스트."""
import zipfile

from dochan.model.document import Paragraph
from dochan.model.image import Image
from dochan.model.table import Table
from dochan.ooxml.docx import DOCXReader

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def write_docx(path, body, parts=None, rels=''):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<w:document xmlns:w="%s" xmlns:r="%s" xmlns:c="%s" xmlns:a="%s"><w:body>%s</w:body></w:document>' % (W, R, C, A, body))
        z.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="%s">%s</Relationships>' % (REL, rels))
        for name, data in (parts or {}).items():
            z.writestr(name, data)


def paragraph(text):
    return '<w:p><w:r><w:t>%s</w:t></w:r></w:p>' % text


def table():
    return '<w:tbl><w:tr><w:tc>%s</w:tc></w:tr></w:tbl>' % paragraph('cell')


def test_docx_chart_is_inserted_at_exact_run_anchor(tmp_path):
    path = tmp_path / 'chart.docx'
    chart = '<c:chartSpace xmlns:c="%s" xmlns:a="%s"><c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>Sales</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:barChart><c:ser><c:tx><c:v>Revenue</c:v></c:tx><c:cat><c:strLit><c:pt idx="0"><c:v>Q1</c:v></c:pt></c:strLit></c:cat><c:val><c:numLit><c:pt idx="0"><c:v>42</c:v></c:pt></c:numLit></c:val></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>' % (C, A)
    write_docx(path, '<w:p><w:r><w:t>before</w:t></w:r><w:r><w:drawing><c:chart r:id="chart"/></w:drawing></w:r><w:r><w:t>after</w:t></w:r></w:p>', {'word/charts/chart1.xml': chart}, '<Relationship Id="chart" Type="%s/chart" Target="charts/chart1.xml"/>' % R)
    doc = DOCXReader().read(str(path))
    elements = doc.sections[0].elements
    assert [type(e) for e in elements] == [Paragraph, Paragraph, Table, Paragraph]
    assert [elements[0].text, elements[1].text, elements[3].text] == ['before', 'Sales', 'after']
    assert elements[1].heading_level == 3
    assert elements[2].caption_text == 'Chart type: column'
    assert elements[2].rows[1][1].text == '42'
    assert not doc.errors


def test_docx_caption_style_and_seq_attach_to_adjacent_table(tmp_path):
    path = tmp_path / 'captions.docx'
    cap = '<w:p><w:pPr><w:pStyle w:val="CustomCaption"/></w:pPr><w:r><w:t>Table one</w:t></w:r></w:p>'
    seq = '<w:p><w:fldSimple w:instr=" SEQ Table "><w:r><w:t>Table two</w:t></w:r></w:fldSimple></w:p>'
    styles = '<w:styles xmlns:w="%s"><w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/></w:style><w:style w:type="paragraph" w:styleId="CustomCaption"><w:basedOn w:val="Caption"/></w:style></w:styles>' % W
    write_docx(path, cap + table() + paragraph('separator') + table() + seq, {'word/styles.xml': styles})
    elements = DOCXReader().read(str(path)).sections[0].elements
    assert [type(e) for e in elements] == [Table, Paragraph, Table]
    assert [(e.caption_text, e.caption_side) for e in elements if isinstance(e, Table)] == [('Table one', 'TOP'), ('Table two', 'BOTTOM')]


def test_docx_nonadjacent_caption_and_other_seq_are_not_attached(tmp_path):
    path = tmp_path / 'noncaption.docx'
    body = '<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>far</w:t></w:r></w:p>' + paragraph('body') + table() + '<w:p><w:fldSimple w:instr=" SEQ Equation "><w:r><w:t>Equation 1</w:t></w:r></w:fldSimple></w:p>'
    write_docx(path, body)
    elements = DOCXReader().read(str(path)).sections[0].elements
    assert len(elements) == 4
    assert not elements[2].caption


def test_docx_seq_figure_caption_and_image_stay_at_anchor(tmp_path):
    path = tmp_path / 'image.docx'
    body = paragraph('before') + '<w:p><w:r><w:drawing><a:blip r:embed="img"/></w:drawing></w:r></w:p>' + '<w:p><w:r><w:instrText> SEQ Figure </w:instrText></w:r><w:r><w:t>Figure 1</w:t></w:r></w:p>' + paragraph('after')
    write_docx(path, body, {'word/media/a.png': b'PNG'}, '<Relationship Id="img" Type="%s/image" Target="media/a.png"/>' % R)
    elements = DOCXReader().read(str(path)).sections[0].elements
    image = next(e for e in elements if isinstance(e, Image))
    assert (image.caption_text, image.caption_side) == ('Figure 1', 'BOTTOM')
    assert elements.index(image) < next(i for i, e in enumerate(elements) if isinstance(e, Paragraph) and e.text == 'after')
    assert not [e for e in elements if isinstance(e, Paragraph) and e.text == 'Figure 1']


def test_docx_damaged_chart_warns_without_losing_body(tmp_path):
    path = tmp_path / 'damaged-chart.docx'
    write_docx(path, paragraph('before') + '<w:p><w:r><w:drawing><c:chart r:id="chart"/></w:drawing></w:r></w:p>' + paragraph('after'), {'word/charts/chart1.xml': '<broken'}, '<Relationship Id="chart" Type="%s/chart" Target="charts/chart1.xml"/>' % R)
    doc = DOCXReader().read(str(path))
    assert [e.text for e in doc.sections[0].elements] == ['before', 'after']
    assert any('chart' in e.lower() for e in doc.errors)


def test_docx_localized_seq_split_across_runs_attaches_caption(tmp_path):
    path = tmp_path / 'localized.docx'
    cap = '<w:p><w:r><w:instrText> SE</w:instrText></w:r><w:r><w:instrText>Q Tableau </w:instrText></w:r><w:r><w:t>Tableau 1</w:t></w:r></w:p>'
    write_docx(path, '<w:sdt><w:sdtContent>' + cap + table() + '</w:sdtContent></w:sdt>')
    elements = DOCXReader().read(str(path)).sections[0].elements
    assert len(elements) == 1 and isinstance(elements[0], Table)
    assert (elements[0].caption_text, elements[0].caption_side) == ('Tableau 1', 'TOP')


def test_docx_caption_between_two_tables_remains_ambiguous(tmp_path):
    path = tmp_path / 'ambiguous.docx'
    cap = '<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>caption</w:t></w:r></w:p>'
    write_docx(path, table() + cap + table())
    elements = DOCXReader().read(str(path)).sections[0].elements
    assert len(elements) == 3
    assert not elements[0].caption and not elements[2].caption


def test_docx_localized_caption_style_before_figure_attaches(tmp_path):
    path = tmp_path / 'localized-figure.docx'
    body = '<w:p><w:pPr><w:pStyle w:val="Localized"/></w:pPr><w:r><w:t>illustration</w:t></w:r></w:p><w:p><w:r><w:drawing><a:blip r:embed="img"/></w:drawing></w:r></w:p>'
    styles = '<w:styles xmlns:w="%s"><w:style w:type="paragraph" w:styleId="Localized"><w:name w:val="Caption"/></w:style></w:styles>' % W
    write_docx(path, body, {'word/media/a.png': b'PNG', 'word/styles.xml': styles}, '<Relationship Id="img" Type="%s/image" Target="media/a.png"/>' % R)
    image = next(e for e in DOCXReader().read(str(path)).sections[0].elements if isinstance(e, Image))
    assert (image.caption_text, image.caption_side) == ('illustration', 'TOP')


def test_docx_nested_table_caption_keeps_model_contract(tmp_path):
    path = tmp_path / 'nested-caption.docx'
    cap = '<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>inner caption</w:t></w:r></w:p>'
    write_docx(path, '<w:tbl><w:tr><w:tc>' + cap + table() + '</w:tc></w:tr></w:tbl>')
    outer = DOCXReader().read(str(path)).sections[0].elements[0]
    nested = next(e for e in outer.rows[0][0].paragraphs if isinstance(e, Table))
    assert not nested.caption
    assert outer.rows[0][0].paragraphs[0].text == 'inner caption'
    assert outer.rows[0][0].text == 'inner caption\ncell'


def test_docx_textbox_content_controls_preserve_anchor_order_once(tmp_path):
    path = tmp_path / 'boxed-controls.docx'
    box = '<w:drawing><w:txbxContent><w:sdt><w:sdtContent>' + paragraph('inside') + '</w:sdtContent></w:sdt></w:txbxContent></w:drawing>'
    write_docx(path, '<w:p><w:r><w:t>before </w:t></w:r><w:r>' + box + '</w:r><w:r><w:t> after</w:t></w:r></w:p>')
    elements = DOCXReader().read(str(path)).sections[0].elements
    assert elements[0].text == 'before inside after'


def test_docx_caption_does_not_cross_an_empty_paragraph(tmp_path):
    path = tmp_path / 'caption-gap.docx'
    body = '<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>far</w:t></w:r></w:p><w:p/>' + table()
    write_docx(path, body)
    elements = DOCXReader().read(str(path)).sections[0].elements
    assert not next(e for e in elements if isinstance(e, Table)).caption


def test_docx_same_image_two_anchors_gets_separate_captions(tmp_path):
    path = tmp_path / 'repeated-image.docx'
    drawing = '<w:p><w:r><w:drawing><a:blip r:embed="img"/></w:drawing></w:r></w:p>'
    cap = '<w:p><w:r><w:instrText>SEQ Figure</w:instrText></w:r><w:r><w:t>%s</w:t></w:r></w:p>'
    write_docx(path, drawing + cap % 'first' + paragraph('between') + drawing + cap % 'second', {'word/media/a.png': b'PNG'}, '<Relationship Id="img" Type="%s/image" Target="media/a.png"/>' % R)
    doc = DOCXReader().read(str(path))
    images = [e for e in doc.sections[0].elements if isinstance(e, Image)]
    assert [i.caption_text for i in images] == ['first', 'second']
    assert len(doc.assets) == 1
