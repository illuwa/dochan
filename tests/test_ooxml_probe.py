"""차트 검증 프로브가 실제 문서 출력과 누락을 구분하는지 확인한다."""
import zipfile

from scripts.probe_ooxml_charts import probe


def test_chart_probe_compares_emitted_document_table(tmp_path):
    folder = tmp_path / 'document'
    folder.mkdir()
    w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    c = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
    rel = 'http://schemas.openxmlformats.org/package/2006/relationships'
    chart = ('<c:chartSpace xmlns:c="%s"><c:chart><c:plotArea><c:barChart><c:ser>'
             '<c:tx><c:v>Sales</c:v></c:tx><c:cat><c:strLit><c:pt idx="0"><c:v>Q1</c:v></c:pt></c:strLit></c:cat>'
             '<c:val><c:numLit><c:pt idx="0"><c:v>42</c:v></c:pt></c:numLit></c:val>'
             '</c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>') % c
    with zipfile.ZipFile(folder / 'chart.docx', 'w') as archive:
        archive.writestr('word/document.xml',
                         '<w:document xmlns:w="%s" xmlns:r="%s" xmlns:c="%s"><w:body><w:p><w:r><w:drawing><c:chart r:id="chart"/></w:drawing></w:r></w:p></w:body></w:document>' % (w, r, c))
        archive.writestr('word/_rels/document.xml.rels',
                         '<Relationships xmlns="%s"><Relationship Id="chart" Type="%s/chart" Target="charts/chart1.xml"/></Relationships>' % (rel, r))
        archive.writestr('word/charts/chart1.xml', chart)
        archive.writestr('word/charts/chart2.xml', chart)
    rows = probe(tmp_path)
    assert len(rows) == 2
    emitted = next(row for row in rows if row['part'] == 'word/charts/chart1.xml')
    orphan = next(row for row in rows if row['part'] == 'word/charts/chart2.xml')
    assert emitted['emitted'] is True
    assert orphan['emitted'] is False
    assert emitted['cached_values'] == emitted['matched'] == 1
    assert not emitted['failures']
