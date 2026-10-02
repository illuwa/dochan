"""최종 Office 감수의 DOCX 결함을 합성 OOXML로 재현한다."""
import pytest

from dochan.ooxml.docx import DOCXReader
from test_docx_remaining import A, R, W, paragraph, write_docx

DGM = 'http://schemas.openxmlformats.org/drawingml/2006/diagram'
SMARTART = '<w:drawing><dgm:relIds xmlns:dgm="%s" r:dm="diagram"/></w:drawing>' % DGM


def read(tmp_path, body, parts=None, rels=''):
    path = tmp_path / 'final-review.docx'
    write_docx(path, body, parts, rels)
    return DOCXReader().read(str(path))


@pytest.mark.parametrize('num_id', ['0', 'missing', ''])
def test_inactive_numbering_ignores_out_of_range_level(tmp_path, num_id):
    body = '<w:tbl><w:tr><w:tc><w:p><w:pPr><w:numPr><w:ilvl w:val="9"/><w:numId w:val="%s"/></w:numPr></w:pPr><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>' % num_id
    doc = read(tmp_path, body)
    assert doc.find_all('table')[0].rows[0][0].text == 'Cell'
    assert not doc.errors


def test_position_tab_preserves_word_boundary(tmp_path):
    doc = read(tmp_path, '<w:p><w:r><w:t>Left</w:t><w:ptab w:alignment="center" w:relativeTo="margin" w:leader="none"/><w:t>Center</w:t></w:r></w:p>')
    assert doc.find_all('paragraph')[0].text == 'Left\tCenter'


def test_heading_inherits_run_style_and_direct_false_overrides(tmp_path):
    styles = '<w:styles xmlns:w="%s"><w:style w:type="paragraph" w:styleId="Heading1"><w:rPr><w:b/><w:i/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Custom"><w:basedOn w:val="Heading1"/></w:style></w:styles>' % W
    body = '<w:p><w:pPr><w:pStyle w:val="Custom"/></w:pPr><w:r><w:t>Heading</w:t></w:r><w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t> Plain</w:t></w:r></w:p>'
    doc = read(tmp_path, body, {'word/styles.xml': styles})
    p = doc.find_all('paragraph')[0]
    assert p.heading_level == 1
    assert [(r.bold, r.italic) for r in p.runs] == [(True, True), (False, True)]


def test_style_toggle_chain_and_character_inheritance(tmp_path):
    styles = '<w:styles xmlns:w="%s"><w:style w:type="paragraph" w:styleId="Base"><w:rPr><w:b/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Derived"><w:basedOn w:val="Base"/><w:rPr><w:b/></w:rPr></w:style><w:style w:type="character" w:styleId="Emphasis"><w:rPr><w:i/></w:rPr></w:style><w:style w:type="character" w:styleId="Child"><w:basedOn w:val="Emphasis"/></w:style></w:styles>' % W
    body = '<w:p><w:pPr><w:pStyle w:val="Derived"/></w:pPr><w:r><w:rPr><w:rStyle w:val="Child"/></w:rPr><w:t>Text</w:t></w:r></w:p>'
    run = read(tmp_path, body, {'word/styles.xml': styles}).find_all('paragraph')[0].runs[0]
    assert not run.bold
    assert run.italic


def test_smartart_data_text_keeps_anchor_order_and_provenance(tmp_path):
    data = '<dgm:dataModel xmlns:dgm="%s" xmlns:a="%s"><dgm:ptLst><dgm:pt><dgm:t><a:p><a:r><a:t>Alpha</a:t></a:r></a:p><a:p><a:r><a:t>Beta</a:t></a:r></a:p></dgm:t></dgm:pt></dgm:ptLst></dgm:dataModel>' % (DGM, A)
    body = '<w:p><w:r><w:t>Before</w:t>' + SMARTART + '<w:t>After</w:t></w:r></w:p>'
    doc = read(tmp_path, body, {'word/diagrams/data1.xml': data}, '<Relationship Id="diagram" Type="%s/diagramData" Target="diagrams/data1.xml"/>' % R)
    paragraphs = doc.find_all('paragraph')
    assert [p.text for p in paragraphs] == ['Before', 'Alpha\nBeta', 'After']
    assert paragraphs[1].provenance.path == 'word/diagrams/data1.xml'
    assert not doc.errors


@pytest.mark.parametrize('data', [None, '<broken', '<empty/>'])
def test_unreadable_smartart_warns_without_losing_body(tmp_path, data):
    parts = {} if data is None else {'word/diagrams/data1.xml': data}
    doc = read(tmp_path, paragraph('Body') + '<w:p><w:r>' + SMARTART + '</w:r></w:p>', parts, '<Relationship Id="diagram" Type="%s/diagramData" Target="diagrams/data1.xml"/>' % R)
    assert doc.find_all('paragraph')[0].text == 'Body'
    assert any(e.startswith('WARN: DOCX SmartArt') for e in doc.errors)
    assert not any(e.startswith('ERR:') for e in doc.errors)


def test_undefined_numbering_level_does_not_report_limit(tmp_path):
    numbering = '<w:numbering xmlns:w="%s"><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="%%1."/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num></w:numbering>' % W
    body = '<w:p><w:pPr><w:numPr><w:numId w:val="1"/><w:ilvl w:val="9"/></w:numPr></w:pPr><w:r><w:t>Unnumbered</w:t></w:r></w:p>'
    doc = read(tmp_path, body, {'word/numbering.xml': numbering})
    assert doc.find_all('paragraph')[0].text == 'Unnumbered'
    assert not doc.errors


def test_smartart_repeated_occurrences_have_output_budget(tmp_path, monkeypatch):
    from dochan.ooxml import docx
    monkeypatch.setattr(docx, 'MAX_SMARTART_OUTPUT_CHARS', 6)
    data = '<dgm:dataModel xmlns:dgm="%s" xmlns:a="%s"><dgm:t><a:p><a:r><a:t>Alpha</a:t></a:r></a:p></dgm:t></dgm:dataModel>' % (DGM, A)
    doc = read(tmp_path, ('<w:p><w:r>' + SMARTART + '</w:r></w:p>') * 3, {'word/custom-data.xml': data}, '<Relationship Id="diagram" Type="%s/diagramData" Target="custom-data.xml"/>' % R)
    assert [p.text for p in doc.find_all('paragraph')] == ['Alpha']
    assert any('SmartArt output character limit' in e for e in doc.errors)


def test_missing_smartart_relids_warns(tmp_path):
    doc = read(tmp_path, '<w:p><w:r><w:drawing><a:graphicData uri="%s"/></w:drawing></w:r></w:p>' % DGM)
    assert any('SmartArt diagramData relationship missing' in e for e in doc.errors)


def test_style_inheritance_cycle_is_bounded(tmp_path):
    styles = '<w:styles xmlns:w="%s"><w:style w:type="paragraph" w:styleId="Cycle"><w:basedOn w:val="Cycle"/><w:rPr><w:b/></w:rPr></w:style></w:styles>' % W
    doc = read(tmp_path, '<w:p><w:pPr><w:pStyle w:val="Cycle"/></w:pPr><w:r><w:t>Text</w:t></w:r></w:p>', {'word/styles.xml': styles})
    assert doc.find_all('paragraph')[0].text == 'Text'
    assert any('inheritance cycle' in e for e in doc.errors)
