"""독립 리뷰의 DOCX 결함을 재현하는 합성 회귀 테스트."""
import pytest
from dochan.model.table import Table
from dochan.ooxml.docx import DOCXReader
from dochan.output.markdown import to_markdown
from test_docx_remaining import write_docx, paragraph, table, R, C

IMAGE = '<w:drawing><a:blip r:embed="img"/></w:drawing>'
CHART = '<w:drawing><c:chart r:id="chart"/></w:drawing>'
CAPTION = '<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>%s</w:t></w:r></w:p>'
PARTS = {'word/media/a.png': b'PNG', 'word/charts/chart1.xml': '<c:chartSpace xmlns:c="%s"><c:chart><c:plotArea><c:barChart><c:ser><c:val><c:numLit><c:pt idx="0"><c:v>42</c:v></c:pt></c:numLit></c:val></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>' % C}
RELS = '<Relationship Id="img" Type="%s/image" Target="media/a.png"/><Relationship Id="chart" Type="%s/chart" Target="charts/chart1.xml"/><Relationship Id="link" Type="%s/hyperlink" Target="https://example.org/target" TargetMode="External"/>' % (R, R, R)

def read(tmp_path, body):
    path = tmp_path / 'review.docx'
    write_docx(path, body, PARTS, RELS)
    return DOCXReader().read(str(path))

def test_docx_linked_image_keeps_hyperlink_target(tmp_path):
    doc = read(tmp_path, '<w:p><w:hyperlink r:id="link"><w:r>' + IMAGE + '</w:r></w:hyperlink></w:p>')
    assert '<https://example.org/target>' in to_markdown(doc)

@pytest.mark.parametrize('inner', [table(), '<w:p><w:r>' + IMAGE + '</w:r></w:p>'])
def test_docx_cell_caption_stays_original_paragraph(tmp_path, inner):
    doc = read(tmp_path, '<w:tbl><w:tr><w:tc>' + CAPTION % 'inner caption' + inner + '</w:tc></w:tr></w:tbl>')
    cell = doc.sections[0].elements[0].rows[0][0]
    assert cell.paragraphs[0].text == 'inner caption'
    assert 'inner caption' in to_markdown(doc)
    assert not any(getattr(item, 'caption', []) for item in cell.paragraphs)

@pytest.mark.parametrize('nested', [True, False])
def test_docx_group_chart_keeps_textbox_siblings_in_order(tmp_path, nested):
    middle = '<w:p><w:r>' + CHART + '</w:r></w:p>'
    content = '<w:txbxContent>' + paragraph('before') + middle + paragraph('after') + '</w:txbxContent>' if nested else '<w:txbxContent>' + paragraph('before') + '</w:txbxContent>' + CHART + '<w:txbxContent>' + paragraph('after') + '</w:txbxContent>'
    doc = read(tmp_path, '<w:p><w:r><w:drawing>' + content + '</w:drawing></w:r></w:p>')
    elements = doc.sections[0].elements
    assert isinstance(elements[1], Table)
    assert elements[0].text.strip() == 'before'
    assert elements[2].text.strip() == 'after'

@pytest.mark.parametrize('gap', ['', '<w:p/>'])
def test_docx_caption_adjacency_crosses_sdt_only_without_gap(tmp_path, gap):
    doc = read(tmp_path, CAPTION % 'caption' + '<w:sdt><w:sdtContent>' + gap + table() + '</w:sdtContent></w:sdt>')
    target = next(e for e in doc.sections[0].elements if isinstance(e, Table))
    assert bool(target.caption) == (not gap)

def test_docx_textbox_image_is_emitted_once(tmp_path):
    doc = read(tmp_path, '<w:p><w:r><w:drawing><w:txbxContent><w:p><w:r>' + IMAGE + '</w:r></w:p></w:txbxContent></w:drawing></w:r></w:p>')
    assert len(doc.find_all('image')) == 1
    assert sum(e.text.count('![image]') for e in doc.find_all('paragraph')) == 1

def test_docx_inline_image_heading_is_not_repeated(tmp_path):
    doc = read(tmp_path, '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>before</w:t>' + IMAGE + '<w:t>after</w:t></w:r></w:p>')
    assert [e.heading_level for e in doc.find_all('paragraph')] == [1]
    assert doc.find_all('paragraph')[0].text == 'before![image](word/media/a.png)after'

def test_docx_completed_model_does_not_retain_xml_elements(tmp_path):
    doc = read(tmp_path, CAPTION % 'caption' + table())
    for item in doc.find_all('paragraph') + doc.find_all('table'):
        assert not hasattr(item, '_source_element')
        for caption in getattr(item, 'caption', []):
            assert not hasattr(caption, '_source_element')

def test_docx_sequential_captions_skip_already_captioned_target(tmp_path):
    doc = read(tmp_path, CAPTION % 'first' + table() + CAPTION % 'second' + table())
    assert [e.caption_text for e in doc.find_all('table')] == ['first', 'second']

def test_docx_repeated_chart_occurrences_share_output_budget(tmp_path, monkeypatch):
    from dochan.ooxml import xlsx
    monkeypatch.setattr(xlsx, 'MAX_CHART_OUTPUT_CELLS', 5)
    doc = read(tmp_path, ('<w:p><w:r>' + CHART + '</w:r></w:p>') * 12)
    assert sum(len(row) for t in doc.find_all('table') for row in t.rows) <= 5
    assert any('chart' in e.lower() and 'budget' in e.lower() for e in doc.errors)

def test_docx_repeated_chart_occurrences_share_count_limit(tmp_path, monkeypatch):
    from dochan.ooxml import docx
    monkeypatch.setattr(docx, 'MAX_DOCUMENT_CHARTS', 2)
    doc = read(tmp_path, ('<w:p><w:r>' + CHART + '</w:r></w:p>') * 12)
    assert len(doc.find_all('table')) == 2
    assert any('chart count' in e.lower() for e in doc.errors)


def test_docx_repeated_chart_part_hydrates_once(tmp_path, monkeypatch):
    from dochan.ooxml import charts
    calls = []
    original = charts.hydrate_chart_references
    def hydrate(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)
    monkeypatch.setattr(charts, 'hydrate_chart_references', hydrate)
    doc = read(tmp_path, ('<w:p><w:r>' + CHART + '</w:r></w:p>') * 12)
    assert len(doc.find_all('table')) == 12
    assert calls == ['word/charts/chart1.xml']


def test_docx_inline_image_does_not_repeat_numbering(tmp_path):
    numbering = '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
    props = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
    body = '<w:p>' + props + '<w:r><w:t>before</w:t>' + IMAGE + '<w:t>after</w:t></w:r></w:p><w:p>' + props + '<w:r><w:t>next</w:t></w:r></w:p>'
    path = tmp_path / 'numbering.docx'
    parts = dict(PARTS, **{'word/numbering.xml': numbering})
    write_docx(path, body, parts, RELS)
    paragraphs = DOCXReader().read(str(path)).find_all('paragraph')
    assert paragraphs[0].text.startswith('1. before')
    assert paragraphs[0].text.endswith('![image](word/media/a.png)after')
    assert paragraphs[1].text == '2. next'
    assert len(paragraphs) == 2


@pytest.mark.parametrize('one_run', [True, False])
def test_docx_textbox_boundaries_do_not_merge_words(tmp_path, one_run):
    box = '<w:drawing><w:txbxContent>' + paragraph('box') + '</w:txbxContent><w:txbxContent>' + paragraph('second') + '</w:txbxContent></w:drawing>'
    if one_run:
        body = '<w:p><w:r><w:t>before</w:t>' + box + '<w:t>after</w:t></w:r></w:p>'
    else:
        body = '<w:p><w:r><w:t>before</w:t></w:r><w:r>' + box + '</w:r><w:r><w:t>after</w:t></w:r></w:p>'
    assert read(tmp_path, body).sections[0].elements[0].text == 'before box second after'
