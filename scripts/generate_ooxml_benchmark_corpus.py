"""Generate a small deterministic OOXML benchmark corpus."""
import argparse
import json
import zipfile
from pathlib import Path

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_zip(path: Path, parts: dict):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(name, data)


def generate_corpus(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_docx(output_dir / "sample.docx")
    _write_pptx(output_dir / "sample.pptx")
    _write_xlsx(output_dir / "sample.xlsx")
    (output_dir / "expected.json").write_text(json.dumps({
        "sample.docx": {
            "expected_text": [
                "Report Header",
                "Quarterly Report",
                "Strategic Update",
                "Revenue\tGrowth",
                "Example Link",
                "Internal Link",
                "Next line",
                "Tracked Insert",
                "Controlled Smart",
                "Boxed insight",
                "Revenue Chart ARR increased 42 percent",
                "Field Date 2026-06-20",
                "Field Page 5",
                "[bookmark: Summary] Summary Target",
                "1. First item",
                "2. Second item",
                "a) Alpha item",
                "X. Roman item",
                "1. Section parent",
                "1.a) Child alpha",
                "1.b) Child beta",
                "2. Section reset",
                "2.a) Child reset",
                "Footnote detail",
                "Endnote detail",
                "Body comment [comment 1: Comment detail]",
                "Comment detail",
                "Reply from Approver: Approved after legal review",
                "Report Footer",
            ],
            "expected_markdown": [
                "# Board Report",
                "Author: Alice Analyst",
                "# Strategic Update",
                "![Revenue Chart ARR increased 42 percent Revenue chart](word/media/image1.png)",
                "Example Link <https://example.com/docx-report>",
                "Internal Link <#Summary>",
                "<u>Underlined decision</u> and ~~Deprecated note~~",
                "CO<sub>2</sub> target<sup>1</sup>",
                "***Styled emphasis*** <u>Styled action</u> ~~Styled obsolete~~ <sub>2</sub>",
            ],
            "expected_tables": [
                [["Merged Metric", ""], ["ARR", "10"]],
                [["Region", "Q1"], ["", "Q2"], ["", "Q3"]],
                [["Parent cell Nested value"]],
            ],
        },
        "sample.pptx": {
            "expected_text": [
                "Slide Title",
                "Subtitle",
                "1",
                "Deck link <https://example.com/deck>",
                "Summary jump <#ppt/slides/slide1.xml>",
                "Open dashboard <https://example.com/dashboard>",
                "Revenue Chart ARR up 42 percent",
                "Revenue Chart",
                "• Bullet point",
                "3. Third item",
                "4. Fourth item",
                "Plan",
                "Build",
                "Grouped insight",
                "Grouped coordinate insight",
                "Footer note",
                "Layout Footer",
                "Speaker note detail",
                "Appendix",
            ],
            "expected_markdown": [
                "# Board Update Deck",
                "Author: Alice Analyst",
                "## Slide 1",
                "## Slide 2",
                "![Revenue Chart ARR up 42 percent Picture 1](ppt/media/image1.png)",
                "**Bold insight** *Italic caveat* <u>Underlined action</u> ~~Deprecated slide note~~",
                "Grouped coordinate insight\n\nFooter note",
            ],
            "expected_tables": [
                [["Name", "Value"], ["ARR", "10"]],
                [["Merged Header", ""], ["Merged Row", "Q1"], ["", "Q2"]],
                [["Category", "ARR", "Profit"], ["Q1", "10", "3"], ["Q2", "20", "8"]],
            ],
        },
        "sample.xlsx": {
            "expected_text": [],
            "expected_markdown": [
                "# Financial Workbook",
                "Author: Finance Team",
                "Defined name: SalesRange = Data!$A$1:$C$24",
                "Defined name: Print_Area = Data!$A$1:$C$24",
                "![Workbook revenue snapshot Picture 1](xl/media/image1.png)",
                "## Data",
                "### Revenue Chart",
                "## Summary",
            ],
            "expected_tables": [
                [
                    ["Merged Header", "", ""],
                    ["TRUE", "3 (=SUM(1,2))", ""],
                    ["FALSE", "AB (=CONCAT(\"A\",\"B\"))", ""],
                    ["2024-01-01", "12.50%", "12.35"],
                    ["Example <https://example.com/report>", "", ""],
                    ["2 (=A2*2)", "4 (=B2*2)", ""],
                    ["Shared Rich", "Inline Rich", ""],
                    ["#N/A", "#DIV/0! (=1/0)", ""],
                    ["Range One <https://example.com/range>", "Range Two <https://example.com/range>", ""],
                    ["Reviewed [comment: Analyst: Confirm before release]", "", ""],
                    ["Sparse Left", "", "Sparse Right"],
                    ["Jump to Data <#Data!A1>", "", ""],
                    ["$1,234.50", "1,234", "1,234.6"],
                    ["General Information", "Business Description", "ABC Company manufactures native converters."],
                    ["($1,234.50)", "(1,234)", "(12.5%)"],
                    ["12:00", "36:00:00", ""],
                    ["00123", "123-4567", ""],
                    ["Financials", "Revenue", "809127967.92"],
                    ["", "EBITDA", "847831.96"],
                    ["Formula Ranges", "10 (=SUM(A:A)+SUM(1:1))", ""],
                    ["", "", "20 (=SUM(B:B)+SUM(2:2))"],
                    ["12 kg", "3.5x", "SKU-0042"],
                    ["1/2", "3 1/4", "-1 1/8"],
                    ["1.23E+04", "1.20E-03", "-9.9E+03"],
                ],
                [
                    ["Summary Metric", "42"],
                ],
                [
                    ["Category", "ARR", "Profit"],
                    ["Q1", "10", "3"],
                    ["Q2", "20", "8"],
                ],
            ],
            "expected_table_rows": [
                ["Reviewed [comment: Analyst: Confirm before release]", "", ""],
                ["Sparse Left", "", "Sparse Right"],
                ["Jump to Data <#Data!A1>", "", ""],
                ["$1,234.50", "1,234", "1,234.6"],
                ["General Information", "Business Description", "ABC Company manufactures native converters."],
                ["($1,234.50)", "(1,234)", "(12.5%)"],
                ["12:00", "36:00:00", ""],
                ["00123", "123-4567", ""],
                ["Financials", "Revenue", "809127967.92"],
                ["", "EBITDA", "847831.96"],
                ["Formula Ranges", "10 (=SUM(A:A)+SUM(1:1))", ""],
                ["", "", "20 (=SUM(B:B)+SUM(2:2))"],
                ["1/2", "3 1/4", "-1 1/8"],
                ["1.23E+04", "1.20E-03", "-9.9E+03"],
                ["Summary Metric", "42"],
            ],
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_docx(path: Path):
    _write_zip(path, {
        "[Content_Types].xml": """
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Default Extension="png" ContentType="image/png"/>
          <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
          <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
          <Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
          <Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"/>
          <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
          <Override PartName="/word/commentsExtended.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"/>
          <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
          <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
          <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
        </Types>
        """,
        "_rels/.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
          <Relationship Id="rIdCore" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
        </Relationships>
        """,
        "docProps/core.xml": """
        <cp:coreProperties
          xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
          xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Board Report</dc:title>
          <dc:creator>Alice Analyst</dc:creator>
        </cp:coreProperties>
        """,
        "word/styles.xml": """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="paragraph" w:styleId="Heading1">
            <w:name w:val="heading 1"/>
          </w:style>
          <w:style w:type="paragraph" w:styleId="CustomTitle">
            <w:name w:val="Custom Title"/>
            <w:basedOn w:val="Heading1"/>
          </w:style>
          <w:style w:type="character" w:styleId="StrongEmphasis">
            <w:rPr><w:b/><w:i/></w:rPr>
          </w:style>
          <w:style w:type="character" w:styleId="UnderlinedStyle">
            <w:rPr><w:u w:val="single"/></w:rPr>
          </w:style>
          <w:style w:type="character" w:styleId="StrikeStyle">
            <w:rPr><w:strike/></w:rPr>
          </w:style>
          <w:style w:type="character" w:styleId="SubtleRef">
            <w:rPr><w:vertAlign w:val="subscript"/></w:rPr>
          </w:style>
        </w:styles>
        """,
        "word/_rels/document.xml.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdFootnotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>
          <Relationship Id="rIdEndnotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes" Target="endnotes.xml"/>
          <Relationship Id="rIdDocxLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/docx-report" TargetMode="External"/>
          <Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
          <Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
          <Relationship Id="rIdDocxImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
        </Relationships>
        """,
        "word/numbering.xml": """
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="0">
              <w:start w:val="1"/>
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="%1."/>
            </w:lvl>
            <w:lvl w:ilvl="1">
              <w:start w:val="1"/>
              <w:numFmt w:val="lowerLetter"/>
              <w:lvlText w:val="%2)"/>
            </w:lvl>
            <w:lvl w:ilvl="2">
              <w:start w:val="10"/>
              <w:numFmt w:val="upperRoman"/>
              <w:lvlText w:val="%3."/>
            </w:lvl>
          </w:abstractNum>
          <w:abstractNum w:abstractNumId="8">
            <w:lvl w:ilvl="0">
              <w:start w:val="1"/>
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="%1."/>
            </w:lvl>
            <w:lvl w:ilvl="1">
              <w:start w:val="1"/>
              <w:numFmt w:val="lowerLetter"/>
              <w:lvlText w:val="%1.%2)"/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
          <w:num w:numId="2"><w:abstractNumId w:val="8"/></w:num>
        </w:numbering>
        """,
        "word/document.xml": """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
              <w:r><w:t>Quarterly Report</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:pStyle w:val="CustomTitle"/></w:pPr>
              <w:r><w:t>Strategic Update</w:t></w:r>
            </w:p>
            <w:p>
              <w:r><w:t>Revenue</w:t></w:r>
              <w:r><w:tab/></w:r>
              <w:r><w:t>Growth</w:t></w:r>
              <w:r><w:br/></w:r>
              <w:hyperlink r:id="rIdDocxLink"><w:r><w:t>Example Link</w:t></w:r></w:hyperlink>
              <w:r><w:br/></w:r>
              <w:hyperlink w:anchor="Summary"><w:r><w:t>Internal Link</w:t></w:r></w:hyperlink>
              <w:r><w:br/></w:r>
              <w:r><w:t>Next line</w:t></w:r>
            </w:p>
            <w:p>
              <w:ins w:id="9" w:author="Reviewer">
                <w:r><w:t>Tracked Insert</w:t></w:r>
              </w:ins>
              <w:del w:id="10" w:author="Reviewer">
                <w:r><w:delText>Tracked Delete</w:delText></w:r>
              </w:del>
            </w:p>
            <w:p>
              <w:sdt>
                <w:sdtContent>
                  <w:r><w:t>Controlled</w:t></w:r>
                </w:sdtContent>
              </w:sdt>
              <w:r><w:t> </w:t></w:r>
              <w:smartTag>
                <w:r><w:t>Smart</w:t></w:r>
              </w:smartTag>
            </w:p>
            <w:p>
              <w:r>
                <w:drawing>
                  <w:txbxContent>
                    <w:p><w:r><w:t>Boxed insight</w:t></w:r></w:p>
                  </w:txbxContent>
                </w:drawing>
              </w:r>
            </w:p>
            <w:p>
              <w:r>
                <w:drawing>
                  <wp:inline>
                    <wp:docPr id="14" name="Revenue chart" title="Revenue Chart" descr="ARR increased 42 percent"/>
                    <a:graphic>
                      <a:graphicData>
                        <a:pic>
                          <a:blipFill>
                            <a:blip r:embed="rIdDocxImage"/>
                          </a:blipFill>
                        </a:pic>
                      </a:graphicData>
                    </a:graphic>
                  </wp:inline>
                </w:drawing>
              </w:r>
            </w:p>
            <w:p>
              <w:r><w:t>Field Date </w:t></w:r>
              <w:fldSimple w:instr="DATE">
                <w:r><w:t>2026-06-20</w:t></w:r>
              </w:fldSimple>
            </w:p>
            <w:p>
              <w:r><w:t>Field Page </w:t></w:r>
              <w:r><w:fldChar w:fldCharType="begin"/></w:r>
              <w:r><w:instrText> PAGE </w:instrText></w:r>
              <w:r><w:fldChar w:fldCharType="separate"/></w:r>
              <w:r><w:t>5</w:t></w:r>
              <w:r><w:fldChar w:fldCharType="end"/></w:r>
            </w:p>
            <w:p>
              <w:bookmarkStart w:id="12" w:name="Summary"/>
              <w:r><w:t>Summary Target</w:t></w:r>
              <w:bookmarkEnd w:id="12"/>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>First item</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Second item</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Alpha item</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Roman item</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>
              <w:r><w:t>Section parent</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr></w:pPr>
              <w:r><w:t>Child alpha</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr></w:pPr>
              <w:r><w:t>Child beta</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>
              <w:r><w:t>Section reset</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr></w:pPr>
              <w:r><w:t>Child reset</w:t></w:r>
            </w:p>
            <w:p>
              <w:r><w:t>Body with note</w:t></w:r>
              <w:r><w:footnoteReference w:id="2"/></w:r>
              <w:r><w:t> and endnote</w:t></w:r>
              <w:r><w:endnoteReference w:id="3"/></w:r>
            </w:p>
            <w:p>
              <w:commentRangeStart w:id="4"/>
              <w:r><w:t>Body comment</w:t></w:r>
              <w:commentRangeEnd w:id="4"/>
              <w:r><w:commentReference w:id="4"/></w:r>
            </w:p>
            <w:p>
              <w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>Underlined decision</w:t></w:r>
              <w:r><w:t> and </w:t></w:r>
              <w:r><w:rPr><w:strike/></w:rPr><w:t>Deprecated note</w:t></w:r>
            </w:p>
            <w:p>
              <w:r><w:t>CO</w:t></w:r>
              <w:r><w:rPr><w:vertAlign w:val="subscript"/></w:rPr><w:t>2</w:t></w:r>
              <w:r><w:t> target</w:t></w:r>
              <w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>1</w:t></w:r>
            </w:p>
            <w:p>
              <w:r><w:rPr><w:rStyle w:val="StrongEmphasis"/></w:rPr><w:t>Styled emphasis</w:t></w:r>
              <w:r><w:t> </w:t></w:r>
              <w:r><w:rPr><w:rStyle w:val="UnderlinedStyle"/></w:rPr><w:t>Styled action</w:t></w:r>
              <w:r><w:t> </w:t></w:r>
              <w:r><w:rPr><w:rStyle w:val="StrikeStyle"/></w:rPr><w:t>Styled obsolete</w:t></w:r>
              <w:r><w:t> </w:t></w:r>
              <w:r><w:rPr><w:rStyle w:val="SubtleRef"/></w:rPr><w:t>2</w:t></w:r>
            </w:p>
            <w:tbl>
              <w:tr>
                <w:tc>
                  <w:tcPr><w:gridSpan w:val="2"/></w:tcPr>
                  <w:p><w:r><w:t>Merged Metric</w:t></w:r></w:p>
                </w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>ARR</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>10</w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:tbl>
            <w:tbl>
              <w:tr>
                <w:tc>
                  <w:tcPr><w:vMerge w:val="restart"/></w:tcPr>
                  <w:p><w:r><w:t>Region</w:t></w:r></w:p>
                </w:tc>
                <w:tc><w:p><w:r><w:t>Q1</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc>
                  <w:tcPr><w:vMerge/></w:tcPr>
                  <w:p/>
                </w:tc>
                <w:tc><w:p><w:r><w:t>Q2</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:trPr><w:gridBefore w:val="1"/></w:trPr>
                <w:tc><w:p><w:r><w:t>Q3</w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:tbl>
            <w:tbl>
              <w:tr>
                <w:tc>
                  <w:p><w:r><w:t>Parent cell</w:t></w:r></w:p>
                  <w:tbl>
                    <w:tr>
                      <w:tc><w:p><w:r><w:t>Nested value</w:t></w:r></w:p></w:tc>
                    </w:tr>
                  </w:tbl>
                </w:tc>
              </w:tr>
            </w:tbl>
            <w:sectPr>
              <w:headerReference w:type="default" r:id="rIdHeader"/>
              <w:footerReference w:type="default" r:id="rIdFooter"/>
            </w:sectPr>
          </w:body>
        </w:document>
        """,
        "word/header1.xml": """
        <w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:p><w:r><w:t>Report Header</w:t></w:r></w:p>
        </w:hdr>
        """,
        "word/footer1.xml": """
        <w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:p><w:r><w:t>Report Footer</w:t></w:r></w:p>
        </w:ftr>
        """,
        "word/media/image1.png": MINIMAL_PNG,
        "word/footnotes.xml": """
        <w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:footnote w:id="-1" w:type="separator"/>
          <w:footnote w:id="2"><w:p><w:r><w:t>Footnote detail</w:t></w:r></w:p></w:footnote>
        </w:footnotes>
        """,
        "word/endnotes.xml": """
        <w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:endnote w:id="3"><w:p><w:r><w:t>Endnote detail</w:t></w:r></w:p></w:endnote>
        </w:endnotes>
        """,
        "word/comments.xml": """
        <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
          <w:comment w:id="4" w:author="Reviewer">
            <w:p w15:paraId="AAAA1111"><w:r><w:t>Comment detail</w:t></w:r></w:p>
          </w:comment>
          <w:comment w:id="5" w:author="Approver">
            <w:p w15:paraId="BBBB2222"><w:r><w:t>Approved after legal review</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """,
        "word/commentsExtended.xml": """
        <w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
          <w15:commentEx w15:paraId="AAAA1111"/>
          <w15:commentEx w15:paraId="BBBB2222" w15:paraIdParent="AAAA1111"/>
        </w15:commentsEx>
        """,
    })


def _write_pptx(path: Path):
    _write_zip(path, {
        "[Content_Types].xml": """
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Default Extension="png" ContentType="image/png"/>
          <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
          <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
          <Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
          <Override PartName="/ppt/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>
          <Override PartName="/ppt/diagrams/data1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml"/>
          <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
          <Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>
          <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
        </Types>
        """,
        "_rels/.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
          <Relationship Id="rIdCore" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
        </Relationships>
        """,
        "docProps/core.xml": """
        <cp:coreProperties
          xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
          xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Board Update Deck</dc:title>
          <dc:creator>Alice Analyst</dc:creator>
        </cp:coreProperties>
        """,
        "ppt/presentation.xml": """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst>
            <p:sldId id="256" r:id="rId1"/>
            <p:sldId id="257" r:id="rId2"/>
          </p:sldIdLst>
        </p:presentation>
        """,
        "ppt/_rels/presentation.xml.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
          <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>
        </Relationships>
        """,
        "ppt/slides/_rels/slide1.xml.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdNotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/>
          <Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
          <Relationship Id="rIdDeckLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/deck" TargetMode="External"/>
          <Relationship Id="rIdSummarySlide" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slide1.xml"/>
          <Relationship Id="rIdDashboardLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/dashboard" TargetMode="External"/>
          <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
          <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
          <Relationship Id="rIdDiagramData" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData" Target="../diagrams/data1.xml"/>
        </Relationships>
        """,
        "ppt/slides/slide1.xml": """
        <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
          xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:cSld><p:spTree>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="2" name="Title"/>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="4000000" cy="1000000"/></a:xfrm></p:spPr>
              <p:txBody><a:p>
                <a:r><a:t>Slide Title</a:t></a:r>
                <a:br/>
                <a:r><a:t>Subtitle</a:t></a:r>
                <a:br/>
                <a:fld id="{1}" type="slidenum"><a:t>1</a:t></a:fld>
                <a:br/>
                <a:r>
                  <a:rPr><a:hlinkClick r:id="rIdDeckLink"/></a:rPr>
                  <a:t>Deck link</a:t>
                </a:r>
                <a:br/>
                <a:r>
                  <a:rPr><a:hlinkClick r:id="rIdSummarySlide" action="ppaction://hlinksldjump"/></a:rPr>
                  <a:t>Summary jump</a:t>
                </a:r>
                <a:br/>
                <a:r><a:rPr b="1"/><a:t>Bold insight</a:t></a:r>
                <a:r><a:t> </a:t></a:r>
                <a:r><a:rPr i="1"/><a:t>Italic caveat</a:t></a:r>
                <a:r><a:t> </a:t></a:r>
                <a:r><a:rPr u="sng"/><a:t>Underlined action</a:t></a:r>
                <a:r><a:t> </a:t></a:r>
                <a:r><a:rPr strike="sngStrike"/><a:t>Deprecated slide note</a:t></a:r>
              </a:p></p:txBody>
            </p:sp>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="9" name="Dashboard Link">
                  <a:hlinkClick r:id="rIdDashboardLink"/>
                </p:cNvPr>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:spPr><a:xfrm><a:off x="0" y="1050000"/><a:ext cx="4000000" cy="250000"/></a:xfrm></p:spPr>
              <p:txBody><a:p><a:r><a:t>Open dashboard</a:t></a:r></a:p></p:txBody>
            </p:sp>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="12" name="List"/>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:spPr><a:xfrm><a:off x="0" y="1120000"/><a:ext cx="4000000" cy="250000"/></a:xfrm></p:spPr>
              <p:txBody>
                <a:p>
                  <a:pPr><a:buChar char="•"/></a:pPr>
                  <a:r><a:t>Bullet point</a:t></a:r>
                </a:p>
                <a:p>
                  <a:pPr><a:buAutoNum type="arabicPeriod" startAt="3"/></a:pPr>
                  <a:r><a:t>Third item</a:t></a:r>
                </a:p>
                <a:p>
                  <a:pPr><a:buAutoNum type="arabicPeriod"/></a:pPr>
                  <a:r><a:t>Fourth item</a:t></a:r>
                </a:p>
              </p:txBody>
            </p:sp>
            <p:graphicFrame>
              <p:nvGraphicFramePr>
                <p:cNvPr id="3" name="Table"/>
                <p:cNvGraphicFramePr/>
                <p:nvPr/>
              </p:nvGraphicFramePr>
              <p:xfrm><a:off x="0" y="1200000"/><a:ext cx="4000000" cy="1200000"/></p:xfrm>
              <a:graphic><a:graphicData>
              <a:tbl>
                <a:tr>
                  <a:tc><a:txBody><a:p><a:r><a:t>Name</a:t></a:r></a:p></a:txBody></a:tc>
                  <a:tc><a:txBody><a:p><a:r><a:t>Value</a:t></a:r></a:p></a:txBody></a:tc>
                </a:tr>
                <a:tr>
                  <a:tc><a:txBody><a:p><a:r><a:t>ARR</a:t></a:r></a:p></a:txBody></a:tc>
                  <a:tc><a:txBody><a:p><a:r><a:t>10</a:t></a:r></a:p></a:txBody></a:tc>
                </a:tr>
              </a:tbl>
            </a:graphicData></a:graphic></p:graphicFrame>
            <p:pic>
              <p:nvPicPr>
                <p:cNvPr id="10" name="Picture 1" title="Revenue Chart" descr="ARR up 42 percent"/>
                <p:cNvPicPr/>
                <p:nvPr/>
              </p:nvPicPr>
              <p:blipFill>
                <a:blip r:embed="rIdImage"/>
              </p:blipFill>
              <p:spPr><a:xfrm><a:off x="0" y="2350000"/><a:ext cx="4000000" cy="300000"/></a:xfrm></p:spPr>
            </p:pic>
            <p:graphicFrame>
              <p:nvGraphicFramePr>
                <p:cNvPr id="11" name="Revenue Chart Frame"/>
                <p:cNvGraphicFramePr/>
                <p:nvPr/>
              </p:nvGraphicFramePr>
              <p:xfrm><a:off x="0" y="2380000"/><a:ext cx="4000000" cy="300000"/></p:xfrm>
              <a:graphic><a:graphicData>
                <c:chart r:id="rIdChart"/>
              </a:graphicData></a:graphic>
            </p:graphicFrame>
            <p:graphicFrame>
              <p:nvGraphicFramePr>
                <p:cNvPr id="12" name="SmartArt"/>
                <p:cNvGraphicFramePr/>
                <p:nvPr/>
              </p:nvGraphicFramePr>
              <p:xfrm><a:off x="0" y="2390000"/><a:ext cx="4000000" cy="300000"/></p:xfrm>
              <a:graphic><a:graphicData>
                <dgm:relIds r:dm="rIdDiagramData"/>
              </a:graphicData></a:graphic>
            </p:graphicFrame>
            <p:grpSp>
              <p:nvGrpSpPr>
                <p:cNvPr id="6" name="Grouped Insight"/>
                <p:cNvGrpSpPr/>
                <p:nvPr/>
              </p:nvGrpSpPr>
              <p:grpSpPr><a:xfrm><a:off x="0" y="2400000"/><a:ext cx="4000000" cy="400000"/></a:xfrm></p:grpSpPr>
              <p:sp>
                <p:nvSpPr>
                  <p:cNvPr id="7" name="Grouped Text"/>
                  <p:cNvSpPr/>
                  <p:nvPr/>
                </p:nvSpPr>
                <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="4000000" cy="400000"/></a:xfrm></p:spPr>
                <p:txBody><a:p><a:r><a:t>Grouped insight</a:t></a:r></a:p></p:txBody>
              </p:sp>
            </p:grpSp>
            <p:grpSp>
              <p:nvGrpSpPr>
                <p:cNvPr id="16" name="Grouped Coordinate Insight"/>
                <p:cNvGrpSpPr/>
                <p:nvPr/>
              </p:nvGrpSpPr>
              <p:grpSpPr>
                <a:xfrm>
                  <a:off x="0" y="2450000"/>
                  <a:ext cx="4000000" cy="300000"/>
                  <a:chOff x="0" y="5000000"/>
                  <a:chExt cx="4000000" cy="300000"/>
                </a:xfrm>
              </p:grpSpPr>
              <p:sp>
                <p:nvSpPr>
                  <p:cNvPr id="17" name="Grouped Coordinate Text"/>
                  <p:cNvSpPr/>
                  <p:nvPr/>
                </p:nvSpPr>
                <p:spPr><a:xfrm><a:off x="0" y="5000000"/><a:ext cx="4000000" cy="300000"/></a:xfrm></p:spPr>
                <p:txBody><a:p><a:r><a:t>Grouped coordinate insight</a:t></a:r></a:p></p:txBody>
              </p:sp>
            </p:grpSp>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="5" name="Footer"/>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:spPr><a:xfrm><a:off x="0" y="2600000"/><a:ext cx="4000000" cy="600000"/></a:xfrm></p:spPr>
              <p:txBody><a:p><a:r><a:t>Footer note</a:t></a:r></a:p></p:txBody>
            </p:sp>
            <p:graphicFrame>
              <p:nvGraphicFramePr>
                <p:cNvPr id="8" name="Merged Table"/>
                <p:cNvGraphicFramePr/>
                <p:nvPr/>
              </p:nvGraphicFramePr>
              <p:xfrm><a:off x="0" y="3200000"/><a:ext cx="4000000" cy="1200000"/></p:xfrm>
              <a:graphic><a:graphicData>
              <a:tbl>
                <a:tr>
                  <a:tc gridSpan="2"><a:txBody><a:p><a:r><a:t>Merged Header</a:t></a:r></a:p></a:txBody></a:tc>
                  <a:tc hMerge="1"><a:txBody><a:p/></a:txBody></a:tc>
                </a:tr>
                <a:tr>
                  <a:tc rowSpan="2"><a:txBody><a:p><a:r><a:t>Merged Row</a:t></a:r></a:p></a:txBody></a:tc>
                  <a:tc><a:txBody><a:p><a:r><a:t>Q1</a:t></a:r></a:p></a:txBody></a:tc>
                </a:tr>
                <a:tr>
                  <a:tc vMerge="1"><a:txBody><a:p/></a:txBody></a:tc>
                  <a:tc><a:txBody><a:p><a:r><a:t>Q2</a:t></a:r></a:p></a:txBody></a:tc>
                </a:tr>
              </a:tbl>
            </a:graphicData></a:graphic></p:graphicFrame>
          </p:spTree></p:cSld>
        </p:sld>
        """,
        "ppt/slides/slide2.xml": """
        <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:cSld><p:spTree>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="30" name="Appendix"/>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:txBody><a:p><a:r><a:t>Appendix</a:t></a:r></a:p></p:txBody>
            </p:sp>
          </p:spTree></p:cSld>
        </p:sld>
        """,
        "ppt/charts/chart1.xml": """
        <c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <c:chart>
            <c:title><c:tx><c:rich><a:p><a:r><a:t>Revenue Chart</a:t></a:r></a:p></c:rich></c:tx></c:title>
            <c:plotArea>
              <c:barChart>
                <c:ser>
                  <c:tx><c:strRef><c:strCache>
                    <c:pt idx="0"><c:v>ARR</c:v></c:pt>
                  </c:strCache></c:strRef></c:tx>
                  <c:cat><c:strRef><c:strCache>
                    <c:pt idx="0"><c:v>Q1</c:v></c:pt>
                    <c:pt idx="1"><c:v>Q2</c:v></c:pt>
                  </c:strCache></c:strRef></c:cat>
                  <c:val><c:numRef><c:numCache>
                    <c:pt idx="0"><c:v>10</c:v></c:pt>
                    <c:pt idx="1"><c:v>20</c:v></c:pt>
                  </c:numCache></c:numRef></c:val>
                </c:ser>
                <c:ser>
                  <c:tx><c:strRef><c:strCache>
                    <c:pt idx="0"><c:v>Profit</c:v></c:pt>
                  </c:strCache></c:strRef></c:tx>
                  <c:cat><c:strRef><c:strCache>
                    <c:pt idx="0"><c:v>Q1</c:v></c:pt>
                    <c:pt idx="1"><c:v>Q2</c:v></c:pt>
                  </c:strCache></c:strRef></c:cat>
                  <c:val><c:numRef><c:numCache>
                    <c:pt idx="0"><c:v>3</c:v></c:pt>
                    <c:pt idx="1"><c:v>8</c:v></c:pt>
                  </c:numCache></c:numRef></c:val>
                </c:ser>
              </c:barChart>
            </c:plotArea>
          </c:chart>
        </c:chartSpace>
        """,
        "ppt/diagrams/data1.xml": """
        <dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <dgm:ptLst>
            <dgm:pt modelId="1">
              <dgm:t><a:p><a:r><a:t>Plan</a:t></a:r></a:p></dgm:t>
            </dgm:pt>
            <dgm:pt modelId="2">
              <dgm:t><a:p><a:r><a:t>Build</a:t></a:r></a:p></dgm:t>
            </dgm:pt>
          </dgm:ptLst>
        </dgm:dataModel>
        """,
        "ppt/media/image1.png": MINIMAL_PNG,
        "ppt/slideLayouts/slideLayout1.xml": """
        <p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:cSld><p:spTree>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="20" name="Layout Footer"/>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:spPr><a:xfrm><a:off x="0" y="4500000"/><a:ext cx="4000000" cy="400000"/></a:xfrm></p:spPr>
              <p:txBody><a:p><a:r><a:t>Layout Footer</a:t></a:r></a:p></p:txBody>
            </p:sp>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="21" name="Body Placeholder"/>
                <p:cNvSpPr/>
                <p:nvPr><p:ph type="body"/></p:nvPr>
              </p:nvSpPr>
              <p:txBody><a:p><a:r><a:t>Click to add text</a:t></a:r></a:p></p:txBody>
            </p:sp>
          </p:spTree></p:cSld>
        </p:sldLayout>
        """,
        "ppt/notesSlides/notesSlide1.xml": """
        <p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:cSld><p:spTree>
            <p:sp>
              <p:nvSpPr>
                <p:cNvPr id="4" name="Notes Placeholder"/>
                <p:cNvSpPr/>
                <p:nvPr/>
              </p:nvSpPr>
              <p:txBody><a:p><a:r><a:t>Speaker note detail</a:t></a:r></a:p></p:txBody>
            </p:sp>
          </p:spTree></p:cSld>
        </p:notes>
        """,
    })


def _write_xlsx(path: Path):
    _write_zip(path, {
        "[Content_Types].xml": """
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Default Extension="png" ContentType="image/png"/>
          <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
          <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
          <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
          <Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>
          <Override PartName="/xl/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>
          <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
          <Override PartName="/xl/comments1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"/>
          <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
        </Types>
        """,
        "_rels/.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
          <Relationship Id="rIdCore" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
        </Relationships>
        """,
        "docProps/core.xml": """
        <cp:coreProperties
          xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
          xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Financial Workbook</dc:title>
          <dc:creator>Finance Team</dc:creator>
        </cp:coreProperties>
        """,
        "xl/workbook.xml": """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Data" sheetId="1" r:id="rId1"/>
            <sheet name="Summary" sheetId="2" r:id="rId2"/>
          </sheets>
          <definedNames>
            <definedName name="SalesRange">Data!$A$1:$C$24</definedName>
            <definedName name="_xlnm.Print_Area" localSheetId="0">Data!$A$1:$C$24</definedName>
          </definedNames>
        </workbook>
        """,
        "xl/_rels/workbook.xml.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
          <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
        </Relationships>
        """,
        "xl/worksheets/_rels/sheet1.xml.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/report" TargetMode="External"/>
          <Relationship Id="rIdRangeLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/range" TargetMode="External"/>
          <Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments1.xml"/>
          <Relationship Id="rIdDrawing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
        </Relationships>
        """,
        "xl/styles.xml": """
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="15">
            <numFmt numFmtId="165" formatCode="0.00%"/>
            <numFmt numFmtId="166" formatCode="$#,##0.00"/>
            <numFmt numFmtId="167" formatCode="#,##0"/>
            <numFmt numFmtId="168" formatCode="#,##0.0"/>
            <numFmt numFmtId="169" formatCode="$#,##0.00;[Red]($#,##0.00)"/>
            <numFmt numFmtId="170" formatCode="#,##0;(#,##0)"/>
            <numFmt numFmtId="171" formatCode="0.0%;[Red](0.0%)"/>
            <numFmt numFmtId="172" formatCode="h:mm"/>
            <numFmt numFmtId="173" formatCode="[h]:mm:ss"/>
            <numFmt numFmtId="174" formatCode="00000"/>
            <numFmt numFmtId="175" formatCode="000-0000"/>
            <numFmt numFmtId="176" formatCode="0 &quot;kg&quot;"/>
            <numFmt numFmtId="177" formatCode="0.0&quot;x&quot;"/>
            <numFmt numFmtId="178" formatCode="&quot;SKU-&quot;0000"/>
            <numFmt numFmtId="179" formatCode="0.0E+00"/>
          </numFmts>
          <cellXfs count="21">
            <xf numFmtId="0"/>
            <xf numFmtId="14"/>
            <xf numFmtId="165"/>
            <xf numFmtId="2"/>
            <xf numFmtId="166"/>
            <xf numFmtId="167"/>
            <xf numFmtId="168"/>
            <xf numFmtId="169"/>
            <xf numFmtId="170"/>
            <xf numFmtId="171"/>
            <xf numFmtId="172"/>
            <xf numFmtId="173"/>
            <xf numFmtId="174"/>
            <xf numFmtId="175"/>
            <xf numFmtId="176"/>
            <xf numFmtId="177"/>
            <xf numFmtId="178"/>
            <xf numFmtId="12"/>
            <xf numFmtId="13"/>
            <xf numFmtId="11"/>
            <xf numFmtId="179"/>
          </cellXfs>
        </styleSheet>
        """,
        "xl/sharedStrings.xml": """
        <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <si>
            <r><t>Shared </t></r>
            <r><t>Rich</t></r>
          </si>
        </sst>
        """,
        "xl/worksheets/sheet1.xml": """
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>
          <sheetData>
            <row r="1"><c r="A1" t="inlineStr"><is><t>Merged Header</t></is></c></row>
            <row r="2">
              <c r="A2" t="b"><v>1</v></c>
              <c r="B2"><f>SUM(1,2)</f><v>3</v></c>
            </row>
            <row r="3">
              <c r="A3" t="b"><v>0</v></c>
              <c r="B3" t="str"><f>CONCAT(&quot;A&quot;,&quot;B&quot;)</f><v>AB</v></c>
            </row>
            <row r="4">
              <c r="A4" s="1"><v>45292</v></c>
              <c r="B4" s="2"><v>0.125</v></c>
              <c r="C4" s="3"><v>12.345</v></c>
            </row>
            <row r="5">
              <c r="A5" t="inlineStr"><is><t>Example</t></is></c>
            </row>
            <row r="6">
              <c r="A6"><f t="shared" si="1" ref="A6:B6">A2*2</f><v>2</v></c>
              <c r="B6"><f t="shared" si="1"/><v>4</v></c>
            </row>
            <row r="7">
              <c r="A7" t="s"><v>0</v></c>
              <c r="B7" t="inlineStr"><is><r><t>Inline </t></r><r><t>Rich</t></r></is></c>
            </row>
            <row r="8">
              <c r="A8" t="e"><v>#N/A</v></c>
              <c r="B8" t="e"><f>1/0</f><v>#DIV/0!</v></c>
            </row>
            <row r="9">
              <c r="A9" t="inlineStr"><is><t>Range One</t></is></c>
              <c r="B9" t="inlineStr"><is><t>Range Two</t></is></c>
            </row>
            <row r="10">
              <c r="A10" t="inlineStr"><is><t>Reviewed</t></is></c>
            </row>
            <row r="11">
              <c r="A11" t="inlineStr"><is><t>Sparse Left</t></is></c>
              <c r="C11" t="inlineStr"><is><t>Sparse Right</t></is></c>
            </row>
            <row r="12">
              <c r="A12"/>
            </row>
            <row r="13">
              <c r="A13" s="4"><v>1234.5</v></c>
              <c r="B13" s="5"><v>1234</v></c>
              <c r="C13" s="6"><v>1234.56</v></c>
            </row>
            <row r="14">
              <c r="A14" t="inlineStr"><is><t>General Information</t></is></c>
              <c r="B14" t="inlineStr"><is><t>Business Description</t></is></c>
              <c r="C14" t="inlineStr"><is><t>ABC Company manufactures native converters.</t></is></c>
            </row>
            <row r="15">
              <c r="A15" s="7"><v>-1234.5</v></c>
              <c r="B15" s="8"><v>-1234</v></c>
              <c r="C15" s="9"><v>-0.125</v></c>
            </row>
            <row r="16">
              <c r="A16" s="10"><v>0.5</v></c>
              <c r="B16" s="11"><v>1.5</v></c>
            </row>
            <row r="17">
              <c r="A17" s="12"><v>123</v></c>
              <c r="B17" s="13"><v>1234567</v></c>
            </row>
            <row r="18">
              <c r="A18" t="inlineStr"><is><t>Financials</t></is></c>
              <c r="B18" t="inlineStr"><is><t>Revenue</t></is></c>
              <c r="C18" s="3"><v>809127967.91789377</v></c>
            </row>
            <row r="19">
              <c r="B19" t="inlineStr"><is><t>EBITDA</t></is></c>
              <c r="C19" s="3"><v>847831.96449385432</v></c>
            </row>
            <row r="20">
              <c r="A20" t="inlineStr"><is><t>Formula Ranges</t></is></c>
              <c r="B20"><f t="shared" si="2" ref="B20:C21">SUM(A:A)+SUM(1:1)</f><v>10</v></c>
            </row>
            <row r="21">
              <c r="C21"><f t="shared" si="2"/><v>20</v></c>
            </row>
            <row r="22">
              <c r="A22" s="14"><v>12</v></c>
              <c r="B22" s="15"><v>3.5</v></c>
              <c r="C22" s="16"><v>42</v></c>
            </row>
            <row r="23">
              <c r="A23" s="17"><v>0.5</v></c>
              <c r="B23" s="18"><v>3.25</v></c>
              <c r="C23" s="18"><v>-1.125</v></c>
            </row>
            <row r="24">
              <c r="A24" s="19"><v>12345</v></c>
              <c r="B24" s="19"><v>0.0012</v></c>
              <c r="C24" s="20"><v>-9876</v></c>
            </row>
          </sheetData>
          <hyperlinks>
            <hyperlink ref="A5" r:id="rIdLink"/>
            <hyperlink ref="A9:B9" r:id="rIdRangeLink"/>
            <hyperlink ref="A12" location="Data!A1" display="Jump to Data"/>
          </hyperlinks>
          <drawing r:id="rIdDrawing"/>
        </worksheet>
        """,
        "xl/drawings/drawing1.xml": """
        <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <xdr:twoCellAnchor>
            <xdr:from><xdr:col>4</xdr:col><xdr:row>1</xdr:row></xdr:from>
            <xdr:graphicFrame>
              <a:graphic><a:graphicData><c:chart r:id="rIdChart"/></a:graphicData></a:graphic>
            </xdr:graphicFrame>
            <xdr:clientData/>
          </xdr:twoCellAnchor>
          <xdr:oneCellAnchor>
            <xdr:from><xdr:col>4</xdr:col><xdr:row>0</xdr:row></xdr:from>
            <xdr:pic>
              <xdr:nvPicPr><xdr:cNvPr id="3" name="Picture 1" descr="Workbook revenue snapshot"/></xdr:nvPicPr>
              <xdr:blipFill><a:blip r:embed="rIdImage"/></xdr:blipFill>
            </xdr:pic>
            <xdr:clientData/>
          </xdr:oneCellAnchor>
        </xdr:wsDr>
        """,
        "xl/drawings/_rels/drawing1.xml.rels": """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
          <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
        </Relationships>
        """,
        "xl/charts/chart1.xml": """
        <c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <c:chart>
            <c:title><c:tx><c:rich><a:p><a:r><a:t>Revenue Chart</a:t></a:r></a:p></c:rich></c:tx></c:title>
            <c:plotArea>
              <c:lineChart>
                <c:ser>
                  <c:tx><c:v>ARR</c:v></c:tx>
                  <c:cat><c:strRef><c:strCache>
                    <c:pt idx="0"><c:v>Q1</c:v></c:pt>
                    <c:pt idx="1"><c:v>Q2</c:v></c:pt>
                  </c:strCache></c:strRef></c:cat>
                  <c:val><c:numRef><c:numCache>
                    <c:pt idx="0"><c:v>10</c:v></c:pt>
                    <c:pt idx="1"><c:v>20</c:v></c:pt>
                  </c:numCache></c:numRef></c:val>
                </c:ser>
                <c:ser>
                  <c:tx><c:v>Profit</c:v></c:tx>
                  <c:cat><c:strRef><c:strCache>
                    <c:pt idx="0"><c:v>Q1</c:v></c:pt>
                    <c:pt idx="1"><c:v>Q2</c:v></c:pt>
                  </c:strCache></c:strRef></c:cat>
                  <c:val><c:numRef><c:numCache>
                    <c:pt idx="0"><c:v>3</c:v></c:pt>
                    <c:pt idx="1"><c:v>8</c:v></c:pt>
                  </c:numCache></c:numRef></c:val>
                </c:ser>
              </c:lineChart>
            </c:plotArea>
          </c:chart>
        </c:chartSpace>
        """,
        "xl/worksheets/sheet2.xml": """
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>
            <row r="1">
              <c r="A1" t="inlineStr"><is><t>Summary Metric</t></is></c>
              <c r="B1"><v>42</v></c>
            </row>
          </sheetData>
        </worksheet>
        """,
        "xl/comments1.xml": """
        <comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <authors><author>Analyst</author></authors>
          <commentList>
            <comment ref="A10" authorId="0">
              <text><r><t>Confirm before release</t></r></text>
            </comment>
          </commentList>
        </comments>
        """,
        "xl/media/image1.png": MINIMAL_PNG,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic OOXML benchmark fixtures.")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    generate_corpus(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
