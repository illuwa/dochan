"""리뷰에서 지적한 손상 ZIP, 차트 참조 예산과 chartEx 회귀를 재현한다."""
import io
import zipfile
import zlib
from collections import Counter

import pytest
from lxml import etree

from dochan.ooxml import charts
from dochan.ooxml.package import OOXMLPackage
from dochan.ooxml.xlsx import XLSXReader

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def _zip(parts):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return stream.getvalue()


def _workbook(cells='<row r="1"><c r="A1"><v>7</v></c></row>'):
    return _zip({
        'xl/workbook.xml': '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="Data" r:id="s"/></sheets></workbook>' % (S, R),
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="%s"><Relationship Id="s" Target="worksheets/s.xml"/></Relationships>' % REL,
        'xl/worksheets/s.xml': '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (S, cells),
    })


def _chart(formula='Data!A1'):
    return etree.fromstring(('<c:chartSpace xmlns:c="%s" xmlns:r="%s"><c:chart><c:plotArea><c:lineChart><c:ser><c:val><c:numRef><c:f>%s</c:f></c:numRef></c:val></c:ser></c:lineChart></c:plotArea></c:chart><c:externalData r:id="data"/></c:chartSpace>' % (charts.C_NS, R, formula)).encode())


def _outer(workbooks):
    parts = {}
    for index, data in enumerate(workbooks, 1):
        parts['ppt/embeddings/data%s.xlsx' % index] = data
        parts['ppt/charts/_rels/chart%s.xml.rels' % index] = '<Relationships xmlns="%s"><Relationship Id="data" Target="../embeddings/data%s.xlsx"/></Relationships>' % (REL, index)
    return OOXMLPackage(io.BytesIO(_zip(parts)))


@pytest.mark.parametrize('error', [zlib.error('damaged'), RuntimeError('encrypted'), NotImplementedError('compression'), EOFError('truncated')])
def test_package_normalizes_member_decode_errors(monkeypatch, error):
    with OOXMLPackage(io.BytesIO(_zip({'part.xml': '<root/>'}))) as package:
        def fail(*args, **kwargs):
            raise error
        monkeypatch.setattr(package._zip, 'read', fail)
        with pytest.raises(ValueError, match='part.xml'):
            package.read_part('part.xml')


def test_chart_infers_missing_cell_coordinates_without_fatal_errors():
    errors = []
    cells = '<row r="2"><c t="inlineStr"><is><t>Category</t></is></c><c><v>23</v></c></row><row><c r="A3"><v>5</v></c><c><v>42</v></c></row>'
    with OOXMLPackage(io.BytesIO(_workbook(cells))) as package:
        resolve = charts.workbook_chart_resolver(package, errors)
        assert resolve('Data!B2:B3') == {0: '23', 1: '42'}
    assert not errors


def test_embedded_chart_resolver_reuses_sheet_across_charts(monkeypatch):
    calls = Counter()
    original = OOXMLPackage.read_xml_part
    def track(self, name, *args, **kwargs):
        calls[name] += 1
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(OOXMLPackage, 'read_xml_part', track)
    with _outer([_workbook()]) as package:
        for _ in range(4):
            charts.hydrate_chart_references(_chart(), package, 'ppt/charts/chart1.xml', [])
    assert calls['xl/worksheets/s.xml'] == 1
    assert calls['xl/workbook.xml'] == 1


def test_embedded_workbooks_share_source_cell_budget(monkeypatch):
    monkeypatch.setattr(charts, 'MAX_REFERENCE_CELLS', 3)
    errors = []
    data = _workbook('<row r="1"><c r="A1"><v>7</v></c><c r="B1"><v>8</v></c></row>')
    with _outer([data, data]) as package:
        first, second = _chart(), _chart()
        charts.hydrate_chart_references(first, package, 'ppt/charts/chart1.xml', errors)
        charts.hydrate_chart_references(second, package, 'ppt/charts/chart2.xml', errors)
    assert first.find('.//{%s}numCache' % charts.C_NS) is not None
    assert second.find('.//{%s}numCache' % charts.C_NS) is None
    assert any('source cell limit' in item for item in errors)


def test_embedded_workbook_bytes_have_document_budget(monkeypatch):
    monkeypatch.setattr(charts, 'MAX_REFERENCE_BYTES_TOTAL', 1, raising=False)
    errors = []
    with _outer([_workbook()]) as package:
        root = _chart()
        charts.hydrate_chart_references(root, package, 'ppt/charts/chart1.xml', errors)
    assert root.find('.//{%s}numCache' % charts.C_NS) is None
    assert any('byte limit' in item for item in errors)


@pytest.mark.parametrize('layout,label', [('clusteredColumn', 'histogram'), ('paretoLine', 'Pareto')])
def test_chartex_schema_layouts_and_linked_title(layout, label):
    root = etree.fromstring(('<cx:chartSpace xmlns:cx="%s"><cx:chart><cx:title><cx:tx><cx:txData><cx:f>Data!A1</cx:f><cx:v>Linked title</cx:v></cx:txData></cx:tx></cx:title><cx:plotArea><cx:plotAreaRegion><cx:series layoutId="%s"/></cx:plotAreaRegion></cx:plotArea></cx:chart></cx:chartSpace>' % (charts.CX_NS, layout)).encode())
    errors = []
    normalized = charts.normalize_chart(root, errors)
    assert charts.chart_title(normalized) == 'Linked title'
    assert charts.chart_caption(normalized) == 'Chart type: ' + label
    assert not errors


def test_xlsx_chart_choice_omits_fallback_text_but_keeps_regular_shape():
    root = etree.fromstring(('<xdr:absoluteAnchor xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:mc="%s" xmlns:cx="%s" xmlns:a="%s"><xdr:sp><xdr:txBody><a:p><a:r><a:t>Note</a:t></a:r></a:p></xdr:txBody></xdr:sp><mc:AlternateContent><mc:Choice Requires="cx"><cx:chart/></mc:Choice><mc:Fallback><xdr:sp><xdr:txBody><a:p><a:r><a:t>This chart is unavailable</a:t></a:r></a:p></xdr:txBody></xdr:sp></mc:Fallback></mc:AlternateContent></xdr:absoluteAnchor>' % (charts.MC_NS, charts.CX_NS, charts.A_NS)).encode())
    assert XLSXReader()._drawing_texts(root) == ['Note']


def _damaged_workbook():
    data = bytearray(_workbook())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        member = archive.getinfo('xl/workbook.xml')
        offset = member.header_offset + 30 + len(member.filename.encode()) + len(member.extra)
    # DEFLATE 첫 블록의 BTYPE=3은 예약값이며 해제 시 zlib.error를 일으킨다.
    data[offset] |= 6
    return bytes(data)


@pytest.mark.parametrize('kind', ['docx', 'pptx'])
def test_damaged_embedded_deflate_keeps_document_body(tmp_path, kind):
    from dochan.ooxml.docx import DOCXReader
    from dochan.ooxml.pptx import PPTXReader
    from dochan.output.markdown import to_markdown
    directory = 'word' if kind == 'docx' else 'ppt'
    parts = {
        directory + '/charts/chart1.xml': etree.tostring(_chart()),
        directory + '/charts/_rels/chart1.xml.rels': '<Relationships xmlns="%s"><Relationship Id="data" Target="../embeddings/data.xlsx"/></Relationships>' % REL,
        directory + '/embeddings/data.xlsx': _damaged_workbook(),
    }
    if kind == 'docx':
        parts['word/document.xml'] = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="%s" xmlns:c="%s"><w:body><w:p><w:r><w:t>Important body text</w:t></w:r></w:p><w:p><w:r><w:drawing><c:chart r:id="chart"/></w:drawing></w:r></w:p></w:body></w:document>' % (R, charts.C_NS)
        parts['word/_rels/document.xml.rels'] = '<Relationships xmlns="%s"><Relationship Id="chart" Type="%s/chart" Target="charts/chart1.xml"/></Relationships>' % (REL, R)
    else:
        p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
        parts['ppt/presentation.xml'] = '<p:presentation xmlns:p="%s" xmlns:r="%s"><p:sldIdLst><p:sldId r:id="slide"/></p:sldIdLst></p:presentation>' % (p, R)
        parts['ppt/_rels/presentation.xml.rels'] = '<Relationships xmlns="%s"><Relationship Id="slide" Target="slides/slide1.xml"/></Relationships>' % REL
        parts['ppt/slides/slide1.xml'] = '<p:sld xmlns:p="%s" xmlns:r="%s" xmlns:a="%s" xmlns:c="%s"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Important body text</a:t></a:r></a:p></p:txBody></p:sp><p:graphicFrame><a:graphic><a:graphicData><c:chart r:id="chart"/></a:graphicData></a:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>' % (p, R, charts.A_NS, charts.C_NS)
        parts['ppt/slides/_rels/slide1.xml.rels'] = '<Relationships xmlns="%s"><Relationship Id="chart" Target="../charts/chart1.xml"/></Relationships>' % REL
    path = tmp_path / ('damaged.' + kind)
    path.write_bytes(_zip(parts))
    doc = (DOCXReader() if kind == 'docx' else PPTXReader()).read(str(path))
    assert 'Important body text' in to_markdown(doc)
    assert any('WARN:' in item and 'could not be decoded' in item for item in doc.errors)
    assert not any(item.startswith('ERR:') for item in doc.errors)


def test_embedded_workbooks_share_reference_output_budget(monkeypatch):
    monkeypatch.setattr(charts, 'MAX_REFERENCE_CELLS', 3)
    errors = []
    # 각 원본은 한 셀뿐이다. 조회 범위는 빈 셀까지 포함해 두 셀을 소비한다.
    with _outer([_workbook(), _workbook()]) as package:
        first, second = _chart('Data!A1:B1'), _chart('Data!A1:B1')
        charts.hydrate_chart_references(first, package, 'ppt/charts/chart1.xml', errors)
        charts.hydrate_chart_references(second, package, 'ppt/charts/chart2.xml', errors)
    assert first.find('.//{%s}numCache' % charts.C_NS) is not None
    assert second.find('.//{%s}numCache' % charts.C_NS) is None
    assert any('reference cell limit' in item for item in errors)


def test_cached_resolver_loads_new_sheet_after_embedded_zip_reopens():
    with zipfile.ZipFile(io.BytesIO(_workbook())) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts['xl/workbook.xml'] = parts['xl/workbook.xml'].replace(b'</sheets>', b'<sheet name="Other" r:id="other"/></sheets>')
    parts['xl/_rels/workbook.xml.rels'] = parts['xl/_rels/workbook.xml.rels'].replace(b'</Relationships>', b'<Relationship Id="other" Target="worksheets/other.xml"/></Relationships>')
    parts['xl/worksheets/other.xml'] = '<worksheet xmlns="%s"><sheetData><row><c><v>19</v></c></row></sheetData></worksheet>' % S
    errors = []
    with _outer([_zip(parts)]) as package:
        charts.hydrate_chart_references(_chart(), package, 'ppt/charts/chart1.xml', errors)
        other = _chart('Other!A1')
        charts.hydrate_chart_references(other, package, 'ppt/charts/chart1.xml', errors)
    assert other.find('.//{%s}numCache/{%s}pt/{%s}v' % (charts.C_NS, charts.C_NS, charts.C_NS)).text == '19'
    assert not errors


def test_exhausted_document_source_budget_skips_new_sheet_xml(monkeypatch):
    monkeypatch.setattr(charts, 'MAX_REFERENCE_CELLS', 2)
    original = OOXMLPackage.read_xml_part
    reads = []
    def track(self, name, *args, **kwargs):
        reads.append(name)
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(OOXMLPackage, 'read_xml_part', track)
    data = _workbook('<row><c><v>1</v></c><c><v>2</v></c></row>')
    with _outer([data, data]) as package:
        charts.hydrate_chart_references(_chart(), package, 'ppt/charts/chart1.xml', [])
        charts.hydrate_chart_references(_chart(), package, 'ppt/charts/chart2.xml', [])
    assert reads.count('xl/worksheets/s.xml') == 1
