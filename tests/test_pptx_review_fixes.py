"""독립 리뷰의 PPTX 결함을 합성 패키지로 재현한다."""
from unittest.mock import patch

from dochan.model.equation import Equation
from dochan.ooxml.pptx import PPTXReader
from scripts.probe_ooxml_pptx import probe
from test_pptx_remaining import package, chart_package

MATH = '<a14:m><m:oMath><m:f><m:num><m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath></a14:m>'
CHART = '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea><c:barChart><c:ser><c:cat><c:strLit><c:pt idx="0"><c:v>A</c:v></c:pt></c:strLit></c:cat><c:val><c:numLit><c:pt idx="0"><c:v>3</c:v></c:pt></c:numLit></c:val></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>'


def test_math_only_numbered_paragraph_consumes_and_displays_marker(tmp_path):
    paras = '<a:p><a:pPr><a:buAutoNum type="arabicPeriod"/></a:pPr>%s</a:p>' % MATH
    paras += '<a:p><a:pPr><a:buAutoNum type="arabicPeriod"/></a:pPr><a:r><a:t>Next</a:t></a:r></a:p>'
    doc = PPTXReader().read(str(package(tmp_path, '<p:sp><p:txBody>%s</p:txBody></p:sp>' % paras)))
    blocks = doc.sections[0].elements
    assert len(blocks) == 3
    assert blocks[0].text == '1.'
    assert isinstance(blocks[1], Equation) and blocks[1].latex == r'\frac{x}{2}'
    assert blocks[2].text == '2. Next'


def test_math_first_numbered_paragraph_prefix_precedes_math_once(tmp_path):
    para = '<a:p><a:pPr><a:buAutoNum type="arabicPeriod"/></a:pPr>%s<a:r><a:t>tail</a:t></a:r>%s</a:p>' % (MATH, MATH)
    blocks = PPTXReader().read(str(package(tmp_path, '<p:sp><p:txBody>%s</p:txBody></p:sp>' % para))).sections[0].elements
    assert [type(e).__name__ for e in blocks] == ['Paragraph', 'Equation', 'Paragraph', 'Equation']
    assert blocks[0].text == '1.' and blocks[2].text == 'tail'


def test_pptx_probe_equation_cell_compares_raw_omml(tmp_path):
    shape = '<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p>%s</a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>' % MATH
    package(tmp_path, shape)
    result = probe(tmp_path)
    assert result['results'][0]['cells'] == result['results'][0]['matched_cells'] == 1
    assert result['math_samples'][0]['expected_scripts'] == ['x2']
    assert result['math_samples'][0]['actual_scripts'] == ['x2']
    assert result['math_samples'][0]['matched'] is True


def test_pptx_cx1_alternate_choice_preserves_chart(tmp_path):
    shape = '<mc:AlternateContent xmlns:cx1="http://schemas.microsoft.com/office/drawing/2015/9/8/chartex"><mc:Choice Requires="cx1"><p:graphicFrame><a:graphic><a:graphicData><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="chart"/></a:graphicData></a:graphic></p:graphicFrame></mc:Choice><mc:Fallback><p:sp><p:txBody><a:p><a:r><a:t>fallback</a:t></a:r></a:p></p:txBody></p:sp></mc:Fallback></mc:AlternateContent>'
    parts = {'ppt/slides/_rels/slide1.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="chart" Target="../charts/chart1.xml"/></Relationships>', 'ppt/charts/chart1.xml': CHART}
    doc = PPTXReader().read(str(package(tmp_path, shape, parts)))
    assert len(doc.find_all('table')) == 1
    assert not any(p.text == 'fallback' for p in doc.find_all('paragraph'))


def repeated_chart(tmp_path):
    import zipfile
    path = chart_package(tmp_path, CHART)
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    slide = parts['ppt/slides/slide1.xml'].decode()
    frame = slide[slide.index('<p:graphicFrame>'):slide.index('</p:graphicFrame>') + len('</p:graphicFrame>')]
    parts['ppt/slides/slide1.xml'] = slide.replace(frame, frame * 8)
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def test_repeated_chart_hydrates_once_but_charges_each_output(tmp_path, monkeypatch):
    import dochan.ooxml.pptx as pptx
    monkeypatch.setattr(pptx, 'MAX_CHART_OUTPUT_CELLS', 8)
    with patch.object(pptx, 'hydrate_chart_references', wraps=pptx.hydrate_chart_references) as hydrate:
        doc = PPTXReader().read(str(repeated_chart(tmp_path)))
    assert hydrate.call_count == 1
    assert sum(len(row) for table in doc.find_all('table') for row in table.rows) == 8
    assert any('output cell limit exceeded' in e for e in doc.errors)


def test_chart_reference_count_limits_empty_charts_before_parsing(tmp_path, monkeypatch):
    import dochan.ooxml.pptx as pptx
    monkeypatch.setattr(pptx, 'MAX_CHART_REFERENCES', 2)
    doc = PPTXReader().read(str(repeated_chart(tmp_path)))
    assert len(doc.find_all('table')) == 2
    assert any('chart reference limit exceeded' in e for e in doc.errors)


def test_probe_keeps_unsupported_numbering_in_comparison_denominator(tmp_path):
    shape = '<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:pPr><a:buAutoNum type="alphaLcPeriod"/></a:pPr><a:r><a:t>value</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>'
    package(tmp_path, shape)
    row = probe(tmp_path)['results'][0]
    assert row['cells'] == 1 and row['matched_cells'] == 0
    assert row['mismatches']


def test_probe_xml_comments_do_not_skip_document(tmp_path):
    package(tmp_path, '<!-- exporter note --><p:sp><p:txBody><a:p>%s</a:p></p:txBody></p:sp>' % MATH)
    result = probe(tmp_path)
    assert result['math_samples'][0]['matched']
    assert not any('error' in row for row in result['results'])


def test_probe_repeated_identical_table_requires_each_emitted_copy(tmp_path, monkeypatch):
    shape = '<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>same</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>'
    path = package(tmp_path, shape * 2)
    doc = PPTXReader().read(str(path))
    doc.sections[0].elements.pop()
    monkeypatch.setattr(PPTXReader, 'read', lambda self, path: doc)
    row = probe(tmp_path)['results'][0]
    assert row['cells'] == 2 and row['matched_cells'] == 1
