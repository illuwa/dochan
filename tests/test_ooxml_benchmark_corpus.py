import json
import zipfile

from dochan import Dochan
from scripts.generate_ooxml_benchmark_corpus import generate_corpus
from dochan.ooxml.docx import DOCXReader
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.xlsx import XLSXReader


def test_generate_corpus_writes_ooxml_files_and_expected_manifest(tmp_path):
    generate_corpus(tmp_path)

    expected = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))

    assert sorted(expected) == [
        "sample.docx",
        "sample.pptx",
        "sample.xlsx",
    ]
    for name in expected:
        with zipfile.ZipFile(tmp_path / name) as zf:
            assert zf.namelist()
            content_types = zf.read("[Content_Types].xml").decode("utf-8")
            assert "<Override" in content_types
            rels = "\n".join(
                zf.read(part).decode("utf-8")
                for part in zf.namelist()
                if part.endswith(".rels")
            )
            assert "Type=" in rels
    assert "Report Header" in expected["sample.docx"]["expected_text"]
    assert "Quarterly Report" in expected["sample.docx"]["expected_text"]
    assert "Strategic Update" in expected["sample.docx"]["expected_text"]
    assert "# Board Report" in expected["sample.docx"]["expected_markdown"]
    assert "Author: Alice Analyst" in expected["sample.docx"]["expected_markdown"]
    assert "# Strategic Update" in expected["sample.docx"]["expected_markdown"]
    assert "![Revenue Chart ARR increased 42 percent Revenue chart](word/media/image1.png)" in expected["sample.docx"]["expected_markdown"]
    assert "Example Link <https://example.com/docx-report>" in expected["sample.docx"]["expected_markdown"]
    assert "Internal Link <#Summary>" in expected["sample.docx"]["expected_markdown"]
    assert "<u>Underlined decision</u> and ~~Deprecated note~~" in expected["sample.docx"]["expected_markdown"]
    assert "CO<sub>2</sub> target<sup>1</sup>" in expected["sample.docx"]["expected_markdown"]
    assert "***Styled emphasis*** <u>Styled action</u> ~~Styled obsolete~~ <sub>2</sub>" in expected["sample.docx"]["expected_markdown"]
    assert "Tracked Insert" in expected["sample.docx"]["expected_text"]
    assert "Controlled Smart" in expected["sample.docx"]["expected_text"]
    assert "Boxed insight" in expected["sample.docx"]["expected_text"]
    assert "Revenue Chart ARR increased 42 percent" in expected["sample.docx"]["expected_text"]
    assert "Field Date 2026-06-20" in expected["sample.docx"]["expected_text"]
    assert "Field Page 5" in expected["sample.docx"]["expected_text"]
    assert "[bookmark: Summary] Summary Target" in expected["sample.docx"]["expected_text"]
    assert "1. First item" in expected["sample.docx"]["expected_text"]
    assert "a) Alpha item" in expected["sample.docx"]["expected_text"]
    assert "X. Roman item" in expected["sample.docx"]["expected_text"]
    assert "1.a) Child alpha" in expected["sample.docx"]["expected_text"]
    assert "2.a) Child reset" in expected["sample.docx"]["expected_text"]
    assert "Footnote detail" in expected["sample.docx"]["expected_text"]
    assert "Endnote detail" in expected["sample.docx"]["expected_text"]
    assert "Body comment [comment 1: Comment detail]" in expected["sample.docx"]["expected_text"]
    assert "Comment detail" in expected["sample.docx"]["expected_text"]
    assert "Reply from Approver: Approved after legal review" in expected["sample.docx"]["expected_text"]
    assert "Report Footer" in expected["sample.docx"]["expected_text"]
    assert ["Region", "Q1"] in expected["sample.docx"]["expected_tables"][1]
    assert ["", "Q2"] in expected["sample.docx"]["expected_tables"][1]
    assert ["", "Q3"] in expected["sample.docx"]["expected_tables"][1]
    assert expected["sample.docx"]["expected_tables"][2] == [["Parent cell Nested value"]]
    assert "Slide Title" in expected["sample.pptx"]["expected_text"]
    assert "Deck link <https://example.com/deck>" in expected["sample.pptx"]["expected_text"]
    assert "Summary jump <#ppt/slides/slide1.xml>" in expected["sample.pptx"]["expected_text"]
    assert "Open dashboard <https://example.com/dashboard>" in expected["sample.pptx"]["expected_text"]
    assert "Revenue Chart ARR up 42 percent" in expected["sample.pptx"]["expected_text"]
    assert "Revenue Chart" in expected["sample.pptx"]["expected_text"]
    assert "• Bullet point" in expected["sample.pptx"]["expected_text"]
    assert "3. Third item" in expected["sample.pptx"]["expected_text"]
    assert "4. Fourth item" in expected["sample.pptx"]["expected_text"]
    assert "Plan" in expected["sample.pptx"]["expected_text"]
    assert "Build" in expected["sample.pptx"]["expected_text"]
    assert "Grouped insight" in expected["sample.pptx"]["expected_text"]
    assert "Grouped coordinate insight" in expected["sample.pptx"]["expected_text"]
    assert "Footer note" in expected["sample.pptx"]["expected_text"]
    assert "Layout Footer" in expected["sample.pptx"]["expected_text"]
    assert "Speaker note detail" in expected["sample.pptx"]["expected_text"]
    assert "Appendix" in expected["sample.pptx"]["expected_text"]
    assert "# Board Update Deck" in expected["sample.pptx"]["expected_markdown"]
    assert "Author: Alice Analyst" in expected["sample.pptx"]["expected_markdown"]
    assert "## Slide 1" in expected["sample.pptx"]["expected_markdown"]
    assert "## Slide 2" in expected["sample.pptx"]["expected_markdown"]
    assert (
        "![Revenue Chart ARR up 42 percent Picture 1](ppt/media/image1.png)"
        in expected["sample.pptx"]["expected_markdown"]
    )
    assert (
        "**Bold insight** *Italic caveat* <u>Underlined action</u> ~~Deprecated slide note~~"
        in expected["sample.pptx"]["expected_markdown"]
    )
    assert "Grouped coordinate insight\n\nFooter note" in expected["sample.pptx"]["expected_markdown"]
    assert expected["sample.pptx"]["expected_tables"][1] == [
        ["Merged Header", ""],
        ["Merged Row", "Q1"],
        ["", "Q2"],
    ]
    assert expected["sample.pptx"]["expected_tables"][2] == [
        ["Category", "ARR", "Profit"],
        ["Q1", "10", "3"],
        ["Q2", "20", "8"],
    ]
    assert expected["sample.xlsx"]["expected_tables"][0][0] == ["Merged Header", "", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][3] == ["2024-01-01", "12.50%", "12.35"]
    assert expected["sample.xlsx"]["expected_tables"][0][4] == ["Example <https://example.com/report>", "", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][5] == ["2 (=A2*2)", "4 (=B2*2)", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][6] == ["Shared Rich", "Inline Rich", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][7] == ["#N/A", "#DIV/0! (=1/0)", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][8] == [
        "Range One <https://example.com/range>",
        "Range Two <https://example.com/range>",
        "",
    ]
    assert expected["sample.xlsx"]["expected_tables"][0][9] == [
        "Reviewed [comment: Analyst: Confirm before release]",
        "",
        "",
    ]
    assert expected["sample.xlsx"]["expected_tables"][0][10] == ["Sparse Left", "", "Sparse Right"]
    assert expected["sample.xlsx"]["expected_tables"][0][11] == ["Jump to Data <#Data!A1>", "", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][12] == ["$1,234.50", "1,234", "1,234.6"]
    assert expected["sample.xlsx"]["expected_tables"][0][13] == [
        "General Information",
        "Business Description",
        "ABC Company manufactures native converters.",
    ]
    assert expected["sample.xlsx"]["expected_tables"][0][14] == ["($1,234.50)", "(1,234)", "(12.5%)"]
    assert expected["sample.xlsx"]["expected_tables"][0][15] == ["12:00", "36:00:00", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][16] == ["00123", "123-4567", ""]
    assert expected["sample.xlsx"]["expected_tables"][0][17] == ["Financials", "Revenue", "809127967.92"]
    assert expected["sample.xlsx"]["expected_tables"][0][18] == ["", "EBITDA", "847831.96"]
    assert expected["sample.xlsx"]["expected_tables"][0][19] == [
        "Formula Ranges",
        "10 (=SUM(A:A)+SUM(1:1))",
        "",
    ]
    assert expected["sample.xlsx"]["expected_tables"][0][20] == ["", "", "20 (=SUM(B:B)+SUM(2:2))"]
    assert expected["sample.xlsx"]["expected_tables"][0][21] == ["12 kg", "3.5x", "SKU-0042"]
    assert expected["sample.xlsx"]["expected_tables"][0][22] == ["1/2", "3 1/4", "-1 1/8"]
    assert expected["sample.xlsx"]["expected_tables"][0][23] == ["1.23E+04", "1.20E-03", "-9.9E+03"]
    assert "# Financial Workbook" in expected["sample.xlsx"]["expected_markdown"]
    assert "Author: Finance Team" in expected["sample.xlsx"]["expected_markdown"]
    assert "Defined name: SalesRange = Data!$A$1:$C$24" in expected["sample.xlsx"]["expected_markdown"]
    assert "Defined name: Print_Area = Data!$A$1:$C$24" in expected["sample.xlsx"]["expected_markdown"]
    assert "![Workbook revenue snapshot Picture 1](xl/media/image1.png)" in expected["sample.xlsx"]["expected_markdown"]
    assert "## Data" in expected["sample.xlsx"]["expected_markdown"]
    assert "## Summary" in expected["sample.xlsx"]["expected_markdown"]
    assert expected["sample.xlsx"]["expected_tables"][1] == [["Summary Metric", "42"]]
    assert expected["sample.xlsx"]["expected_tables"][2] == [
        ["Category", "ARR", "Profit"],
        ["Q1", "10", "3"],
        ["Q2", "20", "8"],
    ]
    assert ["Reviewed [comment: Analyst: Confirm before release]", "", ""] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["Sparse Left", "", "Sparse Right"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["Jump to Data <#Data!A1>", "", ""] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["$1,234.50", "1,234", "1,234.6"] in expected["sample.xlsx"]["expected_table_rows"]
    assert [
        "General Information",
        "Business Description",
        "ABC Company manufactures native converters.",
    ] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["($1,234.50)", "(1,234)", "(12.5%)"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["12:00", "36:00:00", ""] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["00123", "123-4567", ""] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["Financials", "Revenue", "809127967.92"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["", "EBITDA", "847831.96"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["Formula Ranges", "10 (=SUM(A:A)+SUM(1:1))", ""] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["", "", "20 (=SUM(B:B)+SUM(2:2))"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["1/2", "3 1/4", "-1 1/8"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["1.23E+04", "1.20E-03", "-9.9E+03"] in expected["sample.xlsx"]["expected_table_rows"]
    assert ["Summary Metric", "42"] in expected["sample.xlsx"]["expected_table_rows"]
    with zipfile.ZipFile(tmp_path / "sample.pptx") as zf:
        slide_xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        slide2_xml = zf.read("ppt/slides/slide2.xml").decode("utf-8")
        presentation_xml = zf.read("ppt/presentation.xml").decode("utf-8")
        presentation_rels_xml = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        slide_rels_xml = zf.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
        layout_xml = zf.read("ppt/slideLayouts/slideLayout1.xml").decode("utf-8")
        chart_xml = zf.read("ppt/charts/chart1.xml").decode("utf-8")
        diagram_xml = zf.read("ppt/diagrams/data1.xml").decode("utf-8")
        core_xml = zf.read("docProps/core.xml").decode("utf-8")
        content_types_xml = zf.read("[Content_Types].xml").decode("utf-8")
        image_bytes = zf.read("ppt/media/image1.png")
        assert 'r:id="rId2"' in presentation_xml
        assert "slides/slide2.xml" in presentation_rels_xml
        assert "Appendix" in slide2_xml
        assert "<p:nvSpPr" in slide_xml
        assert "<p:nvGraphicFramePr" in slide_xml
        assert "<p:nvPicPr" in slide_xml
        assert "<p:grpSp>" in slide_xml
        assert "<p:spPr" in slide_xml
        assert "<p:xfrm" in slide_xml
        assert "rIdDeckLink" in slide_xml
        assert "rIdSummarySlide" in slide_xml
        assert "rIdDashboardLink" in slide_xml
        assert "rIdChart" in slide_xml
        assert "rIdDiagramData" in slide_xml
        assert "<c:chart" in slide_xml
        assert "<dgm:relIds" in slide_xml
        assert 'title="Revenue Chart"' in slide_xml
        assert 'descr="ARR up 42 percent"' in slide_xml
        assert "https://example.com/deck" in slide_rels_xml
        assert "https://example.com/dashboard" in slide_rels_xml
        assert "ppaction://hlinksldjump" in slide_xml
        assert "rIdSummarySlide" in slide_rels_xml
        assert "charts/chart1.xml" in slide_rels_xml
        assert "diagrams/data1.xml" in slide_rels_xml
        assert "Plan" in diagram_xml
        assert "Build" in diagram_xml
        assert "Revenue Chart" in chart_xml
        assert "<c:v>ARR</c:v>" in chart_xml
        assert "<c:v>Q1</c:v>" in chart_xml
        assert "<c:v>20</c:v>" in chart_xml
        assert "slideLayout" in slide_rels_xml
        assert "Layout Footer" in layout_xml
        assert "Click to add text" in layout_xml
        assert "/ppt/slideLayouts/slideLayout1.xml" in content_types_xml
        assert "/ppt/charts/chart1.xml" in content_types_xml
        assert "/ppt/diagrams/data1.xml" in content_types_xml
        assert "/ppt/slides/slide2.xml" in content_types_xml
        assert "/docProps/core.xml" in content_types_xml
        assert 'Extension="png"' in content_types_xml
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert "Board Update Deck" in core_xml
        assert "Alice Analyst" in core_xml
        assert '<a:rPr b="1"' in slide_xml
        assert '<a:rPr i="1"' in slide_xml
        assert '<a:rPr u="sng"' in slide_xml
        assert '<a:rPr strike="sngStrike"' in slide_xml
        assert 'gridSpan="2"' in slide_xml
        assert 'rowSpan="2"' in slide_xml
        assert 'hMerge="1"' in slide_xml
        assert 'vMerge="1"' in slide_xml
    with zipfile.ZipFile(tmp_path / "sample.docx") as zf:
        styles_xml = zf.read("word/styles.xml").decode("utf-8")
        rels_xml = zf.read("word/_rels/document.xml.rels").decode("utf-8")
        document_xml = zf.read("word/document.xml").decode("utf-8")
        content_types_xml = zf.read("[Content_Types].xml").decode("utf-8")
        comments_xml = zf.read("word/comments.xml").decode("utf-8")
        comments_extended_xml = zf.read("word/commentsExtended.xml").decode("utf-8")
        core_xml = zf.read("docProps/core.xml").decode("utf-8")
        header_xml = zf.read("word/header1.xml").decode("utf-8")
        footer_xml = zf.read("word/footer1.xml").decode("utf-8")
        image_bytes = zf.read("word/media/image1.png")
        assert "CustomTitle" in styles_xml
        assert "<w:basedOn w:val=\"Heading1\"" in styles_xml
        assert 'w:type="character" w:styleId="StrongEmphasis"' in styles_xml
        assert 'w:type="character" w:styleId="UnderlinedStyle"' in styles_xml
        assert 'w:type="character" w:styleId="StrikeStyle"' in styles_xml
        assert 'w:type="character" w:styleId="SubtleRef"' in styles_xml
        assert "rIdDocxLink" in rels_xml
        assert "https://example.com/docx-report" in rels_xml
        assert "rIdDocxImage" in rels_xml
        assert "media/image1.png" in rels_xml
        assert 'Extension="png"' in content_types_xml
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert "Nested value" in document_xml
        assert 'w:anchor="Summary"' in document_xml
        assert "Tracked Insert" in document_xml
        assert "Tracked Delete" in document_xml
        assert "<w:sdt>" in document_xml
        assert "<w:smartTag>" in document_xml
        assert "<w:txbxContent>" in document_xml
        assert "<wp:docPr" in document_xml
        assert 'descr="ARR increased 42 percent"' in document_xml
        assert "<w:fldSimple" in document_xml
        assert "<w:instrText>" in document_xml
        assert 'w:name="Summary"' in document_xml
        assert "<w:bookmarkStart" in document_xml
        assert "<w:gridBefore" in document_xml
        assert "<w:commentRangeStart" in document_xml
        assert "<w:commentRangeEnd" in document_xml
        assert "/word/commentsExtended.xml" in content_types_xml
        assert "<w:u" in document_xml
        assert "<w:strike" in document_xml
        assert 'w:vertAlign w:val="subscript"' in document_xml
        assert 'w:vertAlign w:val="superscript"' in document_xml
        assert 'w:rStyle w:val="StrongEmphasis"' in document_xml
        assert 'w:rStyle w:val="UnderlinedStyle"' in document_xml
        assert "/word/comments.xml" in content_types_xml
        assert "/docProps/core.xml" in content_types_xml
        assert "Board Report" in core_xml
        assert "Alice Analyst" in core_xml
        assert "/word/header1.xml" in content_types_xml
        assert "/word/footer1.xml" in content_types_xml
        assert "Comment detail" in comments_xml
        assert "Approved after legal review" in comments_xml
        assert 'w15:paraIdParent="AAAA1111"' in comments_extended_xml
        assert "Report Header" in header_xml
        assert "Report Footer" in footer_xml
    docx_doc = DOCXReader().read(str(tmp_path / "sample.docx"))
    assert len(docx_doc.assets) == 1
    assert docx_doc.assets[0].source_path == "word/media/image1.png"
    assert docx_doc.assets[0].content_type == "image/png"
    assert docx_doc.assets[0].metadata["label"] == "Revenue Chart ARR increased 42 percent Revenue chart"
    pptx_doc = PPTXReader().read(str(tmp_path / "sample.pptx"))
    assert len(pptx_doc.assets) == 1
    assert pptx_doc.assets[0].source_path == "ppt/media/image1.png"
    assert pptx_doc.assets[0].content_type == "image/png"
    assert pptx_doc.assets[0].metadata["label"] == "Revenue Chart ARR up 42 percent Picture 1"
    assert pptx_doc.assets[0].metadata["slide"] == 1
    xlsx_doc = XLSXReader().read(str(tmp_path / "sample.xlsx"))
    assert len(xlsx_doc.assets) == 1
    assert xlsx_doc.assets[0].source_path == "xl/media/image1.png"
    assert xlsx_doc.assets[0].content_type == "image/png"
    assert xlsx_doc.assets[0].metadata["label"] == "Workbook revenue snapshot Picture 1"
    assert xlsx_doc.assets[0].metadata["sheet"] == "Data"
    docx_json = json.loads(Dochan(str(tmp_path / "sample.docx")).to_json())
    pptx_json = json.loads(Dochan(str(tmp_path / "sample.pptx")).to_json())
    xlsx_json = json.loads(Dochan(str(tmp_path / "sample.xlsx")).to_json())
    assert docx_json["assets"][0]["source_path"] == "word/media/image1.png"
    assert pptx_json["assets"][0]["metadata"]["slide"] == 1
    assert xlsx_json["assets"][0]["metadata"]["sheet"] == "Data"
    assert docx_json["sections"][0]["provenance"]["path"] == "word/document.xml"
    assert pptx_json["sections"][0]["provenance"]["slide"] == 1
    assert xlsx_json["sections"][0]["provenance"]["sheet"] == "Data"
    docx_heading = next(
        element for element in docx_json["sections"][0]["elements"]
        if element.get("type") == "paragraph" and element.get("text") == "Board Report"
    )
    assert docx_heading["heading_level"] == 1
    formatted_run = next(
        run
        for element in docx_json["sections"][0]["elements"]
        if element.get("type") == "paragraph"
        for run in element.get("runs", [])
        if run["text"] == "Underlined decision"
    )
    assert formatted_run["underline"] is True
    xlsx_table = next(element for element in xlsx_json["sections"][0]["elements"] if element["type"] == "table")
    assert xlsx_table["rows"][0][0]["provenance"]["cell"] == "A1"
    assert xlsx_table["row_count"] >= 18
    assert xlsx_table["col_count"] == 3
    xlsx_cell_paragraph = xlsx_table["rows"][0][0]["paragraphs"][0]
    assert xlsx_cell_paragraph["text"] == "Merged Header"
    assert xlsx_cell_paragraph["runs"][0]["text"] == "Merged Header"
    assert xlsx_cell_paragraph["runs"][0]["provenance"]["cell"] == "A1"
    with zipfile.ZipFile(tmp_path / "sample.pptx") as zf:
        slide_xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "Grouped coordinate insight" in slide_xml
        assert '<a:chOff x="0" y="5000000"/>' in slide_xml
        assert '<a:chExt cx="4000000" cy="300000"/>' in slide_xml
    with zipfile.ZipFile(tmp_path / "sample.xlsx") as zf:
        content_types_xml = zf.read("[Content_Types].xml").decode("utf-8")
        shared_strings_xml = zf.read("xl/sharedStrings.xml").decode("utf-8")
        styles_xml = zf.read("xl/styles.xml").decode("utf-8")
        sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        sheet2_xml = zf.read("xl/worksheets/sheet2.xml").decode("utf-8")
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")
        workbook_rels_xml = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        sheet_rels_xml = zf.read("xl/worksheets/_rels/sheet1.xml.rels").decode("utf-8")
        drawing_rels_xml = zf.read("xl/drawings/_rels/drawing1.xml.rels").decode("utf-8")
        comments_xml = zf.read("xl/comments1.xml").decode("utf-8")
        core_xml = zf.read("docProps/core.xml").decode("utf-8")
        image_bytes = zf.read("xl/media/image1.png")
        assert "/xl/sharedStrings.xml" in content_types_xml
        assert "/xl/comments1.xml" in content_types_xml
        assert "/xl/worksheets/sheet2.xml" in content_types_xml
        assert "/docProps/core.xml" in content_types_xml
        assert 'Extension="png"' in content_types_xml
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert "Financial Workbook" in core_xml
        assert "Finance Team" in core_xml
        assert 'name="Data"' in workbook_xml
        assert 'name="Summary"' in workbook_xml
        assert "worksheets/sheet2.xml" in workbook_rels_xml
        assert "<r><t>Shared </t></r>" in shared_strings_xml
        assert "<r><t>Inline </t></r>" in sheet_xml
        assert "Summary Metric" in sheet2_xml
        assert "<v>42</v>" in sheet2_xml
        assert 'r="A10"' in sheet_xml
        assert "rIdComments" in sheet_rels_xml
        assert "comments1.xml" in sheet_rels_xml
        assert "drawing1.xml" in sheet_rels_xml
        assert "rIdImage" in drawing_rels_xml
        assert "media/image1.png" in drawing_rels_xml
        assert 'ref="A10"' in comments_xml
        assert "Confirm before release" in comments_xml
        assert 'r="A11"' in sheet_xml
        assert 'r="C11"' in sheet_xml
        assert 'formatCode="00000"' in styles_xml
        assert 'formatCode="000-0000"' in styles_xml
        assert 'formatCode="0 &quot;kg&quot;"' in styles_xml
        assert 'formatCode="0.0&quot;x&quot;"' in styles_xml
        assert 'formatCode="&quot;SKU-&quot;0000' in styles_xml
        assert 'formatCode="0.0E+00"' in styles_xml
        assert 'r="A17" s="12"' in sheet_xml
        assert 'r="B17" s="13"' in sheet_xml
        assert 'r="A22" s="14"' in sheet_xml
        assert 'r="B22" s="15"' in sheet_xml
        assert 'r="C22" s="16"' in sheet_xml
        assert 'r="A23" s="17"' in sheet_xml
        assert 'r="B23" s="18"' in sheet_xml
        assert 'r="C23" s="18"' in sheet_xml
        assert 'r="A24" s="19"' in sheet_xml
        assert 'r="B24" s="19"' in sheet_xml
        assert 'r="C24" s="20"' in sheet_xml
        assert 't="e"' in sheet_xml
        assert 'ref="A9:B9"' in sheet_xml
        assert "rIdRangeLink" in sheet_xml
        assert 'ref="A12"' in sheet_xml
        assert 'location="Data!A1"' in sheet_xml
        assert 'r="A14"' in sheet_xml
        assert "Business Description" in sheet_xml
        assert 'r="A16"' in sheet_xml
        assert "Financials" in sheet_xml
        assert 'ref="B20:C21"' in sheet_xml
        assert "SUM(A:A)+SUM(1:1)" in sheet_xml
