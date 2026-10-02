"""PPTX 남은 요소의 합성 OOXML 회귀 테스트."""
import zipfile

import pytest

from dochan.ooxml.pptx import PPTXReader
from dochan.output.markdown import to_markdown

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A14 = "http://schemas.microsoft.com/office/drawing/2010/main"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"


def package(tmp_path, shapes, parts=None):
    path = tmp_path / "synthetic.pptx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="mp4" ContentType="video/mp4"/><Default Extension="mp3" ContentType="audio/mpeg"/></Types>')
        z.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="%s" xmlns:r="%s"><p:sldIdLst><p:sldId r:id="slide"/></p:sldIdLst></p:presentation>' % (P, R))
        z.writestr("ppt/_rels/presentation.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="slide" Target="slides/slide1.xml"/></Relationships>')
        z.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="%s" xmlns:a="%s" xmlns:r="%s" xmlns:mc="%s" xmlns:m="%s" xmlns:a14="%s" xmlns:p14="%s"><p:cSld><p:spTree>%s</p:spTree></p:cSld></p:sld>' % (P, A, R, MC, M, A14, P14, shapes))
        for name, data in (parts or {}).items():
            z.writestr(name, data)
    return path


def test_pptx_table_cell_preserves_paragraph_breaks_runs_and_numbering(tmp_path):
    paras = '<a:p><a:r><a:rPr b="1"/><a:t>Intro</a:t></a:r><a:br/><a:r><a:t>next line</a:t></a:r></a:p>'
    for text in ("First", "Second"):
        paras += '<a:p><a:pPr><a:buAutoNum type="arabicPeriod"/></a:pPr><a:r><a:t>%s</a:t></a:r></a:p>' % text
    shapes = '<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody>%s</a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>' % paras
    doc = PPTXReader().read(str(package(tmp_path, shapes)))
    cell = doc.sections[0].elements[0].rows[0][0]
    assert [p.text for p in cell.paragraphs] == ["Intro\nnext line", "1. First", "2. Second"]
    assert cell.paragraphs[0].runs[0].bold
    assert "Intro next line 1. First 2. Second" in to_markdown(doc)


def test_pptx_omml_choice_keeps_anchor_order_and_omits_fallback(tmp_path):
    math = '<a14:m><m:oMath><m:f><m:num><m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath></a14:m>'
    para = '<a:p><a:r><a:t>Before</a:t></a:r><mc:AlternateContent><mc:Choice Requires="a14">%s</mc:Choice><mc:Fallback><a:r><a:t>FALLBACK</a:t></a:r></mc:Fallback></mc:AlternateContent><a:r><a:t>After</a:t></a:r></a:p>' % math
    shapes = '<mc:AlternateContent><mc:Choice Requires="a14"><p:sp><p:txBody>%s</p:txBody></p:sp></mc:Choice><mc:Fallback><p:sp><p:txBody><a:p><a:r><a:t>IMAGE FALLBACK</a:t></a:r></a:p></p:txBody></p:sp></mc:Fallback></mc:AlternateContent>' % para
    doc = PPTXReader().read(str(package(tmp_path, shapes)))
    blocks = doc.sections[0].elements
    assert [type(e).__name__ for e in blocks] == ["Paragraph", "Equation", "Paragraph"]
    assert blocks[0].text == "Before" and blocks[2].text == "After"
    assert blocks[1].latex == r"\frac{x}{2}"
    assert "FALLBACK" not in to_markdown(doc)


@pytest.mark.parametrize("kind,extension", [("video", "mp4"), ("audio", "mp3")])
def test_pptx_media_reference_and_asset_are_deduplicated(tmp_path, kind, extension):
    shape = '<p:pic><p:nvPicPr><p:cNvPr name="Clip"/><p:nvPr><a:%sFile r:link="old"/><p:extLst><p:ext><p14:media r:embed="new"/></p:ext></p:extLst></p:nvPr></p:nvPicPr></p:pic>' % kind
    target = "ppt/media/clip.%s" % extension
    parts = {"ppt/slides/_rels/slide1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="old" Target="../media/clip.%s"/><Relationship Id="new" Target="../media/clip.%s"/></Relationships>' % (extension, extension), target: b"MEDIA"}
    doc = PPTXReader().read(str(package(tmp_path, shape, parts)))
    assert [p.text for p in doc.sections[0].elements] == ["[Clip](%s)" % target]
    assert len(doc.assets) == 1
    assert doc.assets[0].source_path == target
    assert doc.assets[0].metadata["kind"] == kind
    assert not doc.assets[0].metadata["missing"]
    assert doc.assets[0].content_type == ("video/mp4" if kind == "video" else "audio/mpeg")


def test_pptx_missing_media_keeps_reference_and_warns(tmp_path):
    shape = '<p:pic><p:nvPicPr><p:cNvPr name="Lost"/><p:nvPr><p:videoFile r:link="v"/></p:nvPr></p:nvPicPr></p:pic>'
    parts = {"ppt/slides/_rels/slide1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="v" Target="../media/missing.mp4"/></Relationships>'}
    doc = PPTXReader().read(str(package(tmp_path, shape, parts)))
    assert doc.sections[0].elements[0].text == "[Lost](ppt/media/missing.mp4)"
    assert doc.assets[0].metadata["missing"]
    assert "WARN: PPTX media part not found: ppt/media/missing.mp4" in doc.errors


def chart_package(tmp_path, content, parts=None):
    shape = '<p:graphicFrame><a:graphic><a:graphicData><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="chart"/></a:graphicData></a:graphic></p:graphicFrame>'
    extra = {"ppt/slides/_rels/slide1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="chart" Target="../charts/chart1.xml"/></Relationships>',
             "ppt/charts/chart1.xml": content}
    extra.update(parts or {})
    return package(tmp_path, shape, extra)


def test_pptx_bubble_size_kept_in_long_table(tmp_path):
    ns = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    series = '<c:ser><c:tx><c:v>Bubbles</c:v></c:tx>'
    for tag, value in [("xVal", "2"), ("yVal", "3"), ("bubbleSize", "9")]:
        series += '<c:%s><c:numLit><c:pt idx="0"><c:v>%s</c:v></c:pt></c:numLit></c:%s>' % (tag, value, tag)
    series += '</c:ser>'
    chart = '<c:chartSpace xmlns:c="%s"><c:chart><c:plotArea><c:bubbleChart>%s</c:bubbleChart></c:plotArea></c:chart></c:chartSpace>' % (ns, series)
    doc = PPTXReader().read(str(chart_package(tmp_path, chart)))
    assert [[c.text for c in row] for row in doc.find_all("table")[0].rows] == [["Series", "X", "Y", "Bubble size"], ["Bubbles", "2", "3", "9"]]


def test_pptx_uncached_embedded_chart_uses_workbook_values(tmp_path):
    import io
    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="%s"><sheets><sheet name="Data" r:id="s"/></sheets></workbook>' % R)
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="s" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Q1</t></is></c><c r="B1"><v>42</v></c></row></sheetData></worksheet>')
    chart = '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="%s"><c:chart><c:plotArea><c:barChart><c:ser><c:cat><c:strRef><c:f>Data!A1</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>Data!B1</c:f></c:numRef></c:val></c:ser></c:barChart></c:plotArea></c:chart><c:externalData r:id="book"/></c:chartSpace>' % R
    parts = {"ppt/charts/_rels/chart1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="book" Target="../embeddings/book.xlsx"/></Relationships>', "ppt/embeddings/book.xlsx": workbook.getvalue()}
    doc = PPTXReader().read(str(chart_package(tmp_path, chart, parts)))
    assert [[c.text for c in row] for row in doc.find_all("table")[0].rows] == [["Category", "Series 1"], ["Q1", "42"]]


def test_pptx_chart_without_values_does_not_emit_header_only_table(tmp_path):
    chart = '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea><c:barChart><c:ser><c:tx><c:v>Sales</c:v></c:tx><c:val><c:numRef><c:f>Data!B1</c:f></c:numRef></c:val></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>'
    assert PPTXReader().read(str(chart_package(tmp_path, chart))).find_all("table") == []


def test_pptx_malformed_chart_is_warning_and_following_shape_survives(tmp_path):
    path = chart_package(tmp_path, "<broken>")
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    slide = parts["ppt/slides/slide1.xml"].decode().replace('</p:spTree>', '<p:sp><p:txBody><a:p><a:r><a:t>Safe</a:t></a:r></a:p></p:txBody></p:sp></p:spTree>')
    parts["ppt/slides/slide1.xml"] = slide
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    doc = PPTXReader().read(str(path))
    assert [p.text for p in doc.find_all("paragraph")] == ["Safe"]
    assert any(e.startswith("WARN: PPTX chart could not be read:") for e in doc.errors)


def test_pptx_unsupported_alternate_choice_uses_fallback(tmp_path):
    shape = '<mc:AlternateContent xmlns:unknown="urn:unknown"><mc:Choice Requires="unknown"><p:sp><p:txBody><a:p><a:r><a:t>Unsupported</a:t></a:r></a:p></p:txBody></p:sp></mc:Choice><mc:Fallback><p:sp><p:txBody><a:p><a:r><a:t>Fallback</a:t></a:r></a:p></p:txBody></p:sp></mc:Fallback></mc:AlternateContent>'
    doc = PPTXReader().read(str(package(tmp_path, shape)))
    assert [p.text for p in doc.find_all("paragraph")] == ["Fallback"]


def test_pptx_media_reference_limit_warns_without_document_failure(tmp_path, monkeypatch):
    import dochan.ooxml.pptx as pptx
    monkeypatch.setattr(pptx, "MAX_MEDIA_ASSET_REFS", 1)
    shape = '<p:pic><p:nvPicPr><p:nvPr><a:audioFile r:link="a"/><a:videoFile r:link="b"/></p:nvPr></p:nvPicPr></p:pic>'
    parts = {"ppt/slides/_rels/slide1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="a" Target="../media/a.mp3"/><Relationship Id="b" Target="../media/b.mp4"/></Relationships>', "ppt/media/a.mp3": b"A", "ppt/media/b.mp4": b"B"}
    doc = PPTXReader().read(str(package(tmp_path, shape, parts)))
    assert len(doc.assets) == 1
    assert "WARN: PPTX media reference limit exceeded" in doc.errors


def test_pptx_two_scatter_series_without_y_values_do_not_emit_empty_data(tmp_path):
    ser = '<c:ser><c:xVal><c:numLit><c:pt idx="0"><c:v>1</c:v></c:pt></c:numLit></c:xVal><c:yVal><c:numRef><c:f>Missing!B1</c:f></c:numRef></c:yVal></c:ser>'
    different = ser.replace('<c:v>1</c:v>', '<c:v>2</c:v>')
    chart = '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea><c:scatterChart>%s%s</c:scatterChart></c:plotArea></c:chart></c:chartSpace>' % (ser, different)
    assert PPTXReader().read(str(chart_package(tmp_path, chart))).find_all("table") == []


def test_pptx_chartex_relationship_in_graphic_frame_emits_cached_data(tmp_path):
    cx = "http://schemas.microsoft.com/office/drawing/2014/chartex"
    shape = '<p:graphicFrame><a:graphic><a:graphicData><mc:AlternateContent xmlns:cx="%s"><mc:Choice Requires="cx"><cx:chart r:id="chart"/></mc:Choice><mc:Fallback/></mc:AlternateContent></a:graphicData></a:graphic></p:graphicFrame>' % cx
    chart = '<cx:chartSpace xmlns:cx="%s"><cx:chartData><cx:data id="1"><cx:strDim type="cat"><cx:lvl><cx:pt idx="0">A</cx:pt></cx:lvl></cx:strDim><cx:numDim type="val"><cx:lvl><cx:pt idx="0">2</cx:pt></cx:lvl></cx:numDim></cx:data></cx:chartData><cx:chart><cx:plotArea><cx:plotAreaRegion><cx:series layoutId="waterfall"><cx:dataId val="1"/></cx:series></cx:plotAreaRegion></cx:plotArea></cx:chart></cx:chartSpace>' % cx
    parts = {"ppt/slides/_rels/slide1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="chart" Target="../charts/chart1.xml"/></Relationships>', "ppt/charts/chart1.xml": chart}
    doc = PPTXReader().read(str(package(tmp_path, shape, parts)))
    assert [[c.text for c in row] for row in doc.find_all("table")[0].rows] == [["Category", "Series 1"], ["A", "2"]]
