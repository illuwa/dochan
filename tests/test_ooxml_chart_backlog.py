"""합성 ZIP과 차트 XML로 차트 참조 및 chartEx 계약을 검증한다."""
import io
import zipfile

import pytest
from lxml import etree

from dochan.ooxml import charts
from dochan.ooxml.package import OOXMLPackage
from dochan.ooxml.xlsx import XLSXReader
from dochan.output.markdown import to_markdown

C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CX = 'http://schemas.microsoft.com/office/drawing/2014/chartex'


def _workbook_bytes(state='visible'):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="Sheet1" state="%s" r:id="s1"/></sheets></workbook>' % (S, R, state))
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="%s"><Relationship Id="s1" Target="worksheets/sheet1.xml"/></Relationships>' % REL)
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="%s"><sheetData><row r="1"><c r="B1" t="inlineStr"><is><t>Revenue</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Jan</t></is></c><c r="B2"><f>3*4</f><v>12</v></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>Feb</t></is></c><c r="B3"><v>17</v></c></row></sheetData></worksheet>' % S)
    return data.getvalue()


def _uncached_chart():
    return etree.fromstring(('<c:chartSpace xmlns:c="%s" xmlns:r="%s"><c:chart><c:plotArea><c:lineChart><c:ser><c:tx><c:strRef><c:f>Sheet1!$B$1</c:f></c:strRef></c:tx><c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f></c:numRef></c:val></c:ser></c:lineChart></c:plotArea></c:chart></c:chartSpace>' % (C, R)).encode())


def _rows(root):
    reader = XLSXReader()
    reader._errors = []
    return [[cell.text for cell in row] for row in reader._chart_series_table(root).rows]


def test_chart_reference_reads_sparse_cells_and_formula_cached_value(tmp_path):
    path = tmp_path / 'data.xlsx'
    path.write_bytes(_workbook_bytes())
    root = _uncached_chart()
    with OOXMLPackage(str(path)) as package:
        charts.hydrate_chart_references(root, package, 'xl/charts/chart1.xml', [], charts.workbook_chart_resolver(package, []))
    assert _rows(root) == [['Category', 'Revenue'], ['Jan', '12'], ['Feb', '17']]


def test_chart_reference_reads_embedded_workbook_without_external_access(tmp_path):
    path = tmp_path / 'presentation.pptx'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('ppt/embeddings/data.xlsx', _workbook_bytes())
        z.writestr('ppt/charts/_rels/chart1.xml.rels', '<Relationships xmlns="%s"><Relationship Id="rData" Target="../embeddings/data.xlsx"/></Relationships>' % REL)
    root = _uncached_chart()
    etree.SubElement(root, '{%s}externalData' % C).set('{%s}id' % R, 'rData')
    errors = []
    with OOXMLPackage(str(path)) as package:
        charts.hydrate_chart_references(root, package, 'ppt/charts/chart1.xml', errors)
    assert not errors
    assert _rows(root)[1:] == [['Jan', '12'], ['Feb', '17']]


def test_chart_reference_keeps_existing_cache_authoritative():
    root = _uncached_chart()
    ref = root.find('.//{%s}numRef' % C)
    cache = etree.SubElement(ref, '{%s}numCache' % C)
    point = etree.SubElement(cache, '{%s}pt' % C, idx='0')
    etree.SubElement(point, '{%s}v' % C).text = '99'
    charts.hydrate_chart_references(root, None, '', [], lambda formula: {0: '12'})
    assert ref.find('.//{%s}v' % C).text == '99'


def test_unresolved_chart_does_not_emit_header_only_table():
    assert _rows(_uncached_chart()) == []


def test_chart_reference_bounds_and_quoted_sheet_name(tmp_path):
    path = tmp_path / 'data.xlsx'
    path.write_bytes(_workbook_bytes())
    errors = []
    with OOXMLPackage(str(path)) as package:
        resolver = charts.workbook_chart_resolver(package, errors)
        assert resolver("'Sheet1'!$B$2:$B$3") == {0: '12', 1: '17'}
        assert resolver('Sheet1!A1:XFD1048576') == {}
        assert resolver('[outside.xlsx]Sheet1!A1') == {}
    assert any('limit' in error for error in errors)


def test_bubble_size_is_a_fourth_column():
    root = _uncached_chart()
    series = charts.chart_series(root)[0]
    for name, values in [('xVal', ['1', '2']), ('yVal', ['5', '6']), ('bubbleSize', ['10', '20'])]:
        parent = etree.SubElement(series, '{%s}%s' % (C, name))
        cache = etree.SubElement(parent, '{%s}numLit' % C)
        for i, value in enumerate(values):
            point = etree.SubElement(cache, '{%s}pt' % C, idx=str(i))
            etree.SubElement(point, '{%s}v' % C).text = value
    assert _rows(root) == [['Series', 'X', 'Y', 'Bubble size'], ['Series 1', '1', '5', '10'], ['Series 1', '2', '6', '20']]


def test_chartex_normalizes_title_series_and_multilevel_categories():
    root = etree.fromstring(('<cx:chartSpace xmlns:cx="%s" xmlns:a="%s"><cx:chartData><cx:data id="4"><cx:strDim type="cat"><cx:lvl><cx:pt idx="0">Leaf</cx:pt></cx:lvl><cx:lvl><cx:pt idx="0">Branch</cx:pt></cx:lvl></cx:strDim><cx:numDim type="size"><cx:lvl><cx:pt idx="0">22</cx:pt></cx:lvl></cx:numDim></cx:data></cx:chartData><cx:chart><cx:title><cx:tx><cx:rich><a:p><a:r><a:t>Tree</a:t></a:r></a:p></cx:rich></cx:tx></cx:title><cx:plotArea><cx:plotAreaRegion><cx:series layoutId="sunburst"><cx:tx><cx:txData><cx:v>Size</cx:v></cx:txData></cx:tx><cx:dataId val="4"/></cx:series></cx:plotAreaRegion></cx:plotArea></cx:chart></cx:chartSpace>' % (CX, charts.A_NS)).encode())
    root = charts.normalize_chart(root, [])
    assert charts.chart_title(root) == 'Tree'
    assert charts.chart_caption(root) == 'Chart type: sunburst'
    assert _rows(root) == [['Category', 'Size'], ['Branch / Leaf', '22']]


@pytest.mark.parametrize('state, visibility', [('hidden', 1), ('veryHidden', 2)])
def test_hidden_default_named_sheet_keeps_data_metadata_and_heading(tmp_path, state, visibility):
    path = tmp_path / 'hidden.xlsx'
    path.write_bytes(_workbook_bytes(state))
    doc = XLSXReader().read(str(path))
    assert doc.sections[0].provenance.hidden is True
    assert doc.sections[0].provenance.visibility == visibility
    assert 'Revenue' in to_markdown(doc)
    assert '## Sheet1\n\n*Sheet visibility: %s*' % state in to_markdown(doc)


def test_multilevel_classic_category_cache_preserves_hierarchy():
    root = _uncached_chart()
    cat = root.find('.//{%s}cat' % C)
    cat.clear()
    cache = etree.SubElement(etree.SubElement(cat, '{%s}multiLvlStrRef' % C), '{%s}multiLvlStrCache' % C)
    for value in ['Cost', '2005']:
        level = etree.SubElement(cache, '{%s}lvl' % C)
        point = etree.SubElement(level, '{%s}pt' % C, idx='0')
        etree.SubElement(point, '{%s}v' % C).text = value
    ref = root.find('.//{%s}numRef' % C)
    cache = etree.SubElement(ref, '{%s}numCache' % C)
    point = etree.SubElement(cache, '{%s}pt' % C, idx='0')
    etree.SubElement(point, '{%s}v' % C).text = '12'
    assert _rows(root)[1] == ['2005 / Cost', '12']


def test_differing_scatter_x_without_y_data_omits_table():
    root = _uncached_chart()
    group = root.find('.//{%s}lineChart' % C)
    group.clear()
    for value in ['1', '2']:
        series = etree.SubElement(group, '{%s}ser' % C)
        cache = etree.SubElement(etree.SubElement(series, '{%s}xVal' % C), '{%s}numLit' % C)
        point = etree.SubElement(cache, '{%s}pt' % C, idx='0')
        etree.SubElement(point, '{%s}v' % C).text = value
    assert _rows(root) == []


def test_absolute_anchor_chart_is_read_on_chart_sheet(tmp_path):
    path = tmp_path / 'chart-sheet.xlsx'
    with zipfile.ZipFile(path, 'w') as z:
        with zipfile.ZipFile(io.BytesIO(_workbook_bytes())) as workbook:
            for name in workbook.namelist():
                if name != 'xl/worksheets/sheet1.xml':
                    z.writestr(name, workbook.read(name))
        z.writestr('xl/worksheets/sheet1.xml', '<chartsheet xmlns="%s" xmlns:r="%s"><drawing r:id="drawing"/></chartsheet>' % (S, R))
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels', '<Relationships xmlns="%s"><Relationship Id="drawing" Target="../drawings/drawing1.xml"/></Relationships>' % REL)
        z.writestr('xl/drawings/drawing1.xml', '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:c="%s" xmlns:r="%s"><xdr:absoluteAnchor><c:chart r:id="chart"/></xdr:absoluteAnchor></xdr:wsDr>' % (C, R))
        z.writestr('xl/drawings/_rels/drawing1.xml.rels', '<Relationships xmlns="%s"><Relationship Id="chart" Target="../charts/chart1.xml"/></Relationships>' % REL)
        z.writestr('xl/charts/chart1.xml', '<c:chartSpace xmlns:c="%s"><c:chart><c:plotArea><c:lineChart><c:ser><c:val><c:numLit><c:pt idx="0"><c:v>7</c:v></c:pt></c:numLit></c:val></c:ser></c:lineChart></c:plotArea></c:chart></c:chartSpace>' % C)
    assert any(t.rows[-1][-1].text == '7' for t in XLSXReader().read(str(path)).find_all('table'))


def test_unknown_chartex_layout_is_bounded_warning_and_data_preserved():
    root = etree.fromstring(('<cx:chartSpace xmlns:cx="%s"><cx:chartData><cx:data id="1"><cx:numDim type="val"><cx:lvl><cx:pt idx="0">2</cx:pt></cx:lvl></cx:numDim></cx:data></cx:chartData><cx:chart><cx:plotArea><cx:plotAreaRegion><cx:series layoutId="bad layout"><cx:dataId val="1"/></cx:series></cx:plotAreaRegion></cx:plotArea></cx:chart></cx:chartSpace>' % CX).encode())
    errors = []
    normalized = charts.normalize_chart(root, errors)
    assert _rows(normalized)[1][-1] == '2'
    assert any('layout' in e for e in errors)


def test_chart_source_limit_does_not_repeat_sheet_parsing(tmp_path, monkeypatch):
    path = tmp_path / 'data.xlsx'
    path.write_bytes(_workbook_bytes())
    monkeypatch.setattr(charts, 'MAX_REFERENCE_CELLS', 2)
    errors = []
    with OOXMLPackage(str(path)) as package:
        original = package.read_xml_part
        reads = []
        def track(name):
            reads.append(name)
            return original(name)
        monkeypatch.setattr(package, 'read_xml_part', track)
        resolver = charts.workbook_chart_resolver(package, errors)
        assert resolver('Sheet1!A2') == {}
        assert resolver('Sheet1!B2') == {}
        assert reads.count('xl/worksheets/sheet1.xml') == 1
    assert len(errors) == 1


def test_malformed_chart_warns_without_losing_sheet_content(tmp_path):
    path = tmp_path / 'malformed-chart.xlsx'
    with zipfile.ZipFile(path, 'w') as z:
        with zipfile.ZipFile(io.BytesIO(_workbook_bytes())) as workbook:
            for name in workbook.namelist():
                content = workbook.read(name)
                if name == 'xl/worksheets/sheet1.xml':
                    content = content.replace(b'</worksheet>', ('<drawing xmlns:r="%s" r:id="drawing"/></worksheet>' % R).encode())
                z.writestr(name, content)
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels', '<Relationships xmlns="%s"><Relationship Id="drawing" Target="../drawings/drawing1.xml"/></Relationships>' % REL)
        z.writestr('xl/drawings/drawing1.xml', '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:c="%s" xmlns:r="%s"><xdr:oneCellAnchor><c:chart r:id="chart"/></xdr:oneCellAnchor></xdr:wsDr>' % (C, R))
        z.writestr('xl/drawings/_rels/drawing1.xml.rels', '<Relationships xmlns="%s"><Relationship Id="chart" Target="../charts/chart1.xml"/></Relationships>' % REL)
        z.writestr('xl/charts/chart1.xml', '<broken')
    doc = XLSXReader().read(str(path))
    assert 'Revenue' in to_markdown(doc)
    assert any(error.startswith('WARN:') and 'chart' in error for error in doc.errors)


def test_drawing_chart_references_selects_chartex_choice_once():
    mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
    root = etree.fromstring(('<drawing xmlns:mc="%s" xmlns:cx="%s" xmlns:c="%s" xmlns:r="%s"><mc:AlternateContent><mc:Choice Requires="cx"><cx:chart r:id="new"/></mc:Choice><mc:Fallback><c:chart r:id="old"/></mc:Fallback></mc:AlternateContent></drawing>' % (mc, CX, C, R)).encode())
    assert [node.get('{%s}id' % R) for node in charts.chart_drawing_references(root)] == ['new']
