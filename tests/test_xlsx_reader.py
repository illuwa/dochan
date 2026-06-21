import zipfile

import dochan.ooxml.xlsx as xlsx_module
from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import _cmd_info
from dochan.ooxml.xlsx import XLSXReader
from dochan.output.markdown import to_markdown


def _write_xlsx(
    path,
    workbook_xml,
    sheet_xmls,
    shared_strings_xml=None,
    workbook_rels_xml=None,
    styles_xml=None,
    extra_parts=None,
):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            workbook_rels_xml
            or """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
            </Relationships>
            """,
        )
        if shared_strings_xml:
            zf.writestr("xl/sharedStrings.xml", shared_strings_xml)
        if styles_xml:
            zf.writestr("xl/styles.xml", styles_xml)
        for name, data in sheet_xmls.items():
            zf.writestr(name, data)
        for name, data in (extra_parts or {}).items():
            zf.writestr(name, data)


def test_reads_xlsx_shared_strings_as_table(tmp_path):
    path = tmp_path / "simple.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1" t="s"><v>1</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="s"><v>2</v></c>
                  <c r="B2"><v>10</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        """
        <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <si><t>Name</t></si>
          <si><t>Value</t></si>
          <si><t>A</t></si>
        </sst>
        """,
    )

    doc = XLSXReader().read(str(path))
    table = doc.sections[0].elements[0]

    assert doc.source_format == "xlsx"
    assert doc.sections[0].provenance.sheet == "Sheet1"
    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[0][0].text == "Name"
    assert table.rows[0][1].text == "Value"
    assert table.rows[1][0].text == "A"
    assert table.rows[1][1].text == "10"
    assert table.rows[1][1].provenance.cell == "B2"
    assert table.rows[1][1].paragraphs[0].runs[0].provenance.cell == "B2"


def test_reads_large_xlsx_sheet_with_streaming_preview(tmp_path, monkeypatch):
    path = tmp_path / "large-sheet.xlsx"
    rows = "\n".join(
        f"""
        <row r="{row_index}">
          <c r="A{row_index}" t="inlineStr"><is><t>Large row {row_index}</t></is></c>
          <c r="B{row_index}"><v>{row_index}</v></c>
        </row>
        """
        for row_index in range(1, 6)
    )
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Huge" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": f"""
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>{rows}</sheetData>
            </worksheet>
            """
        },
    )
    monkeypatch.setattr(xlsx_module, "MAX_PART_SIZE", 128)
    monkeypatch.setattr(xlsx_module, "STREAMING_ROW_LIMIT", 3)

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "Large row 1" in markdown
    assert "Large row 3" in markdown
    assert "Large row 4" not in markdown


def test_reads_xlsx_shared_strings_with_dtd_entity_bomb_neutralized(tmp_path):
    path = tmp_path / "entity-bomb.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="s"><v>0</v></c></row>
              </sheetData>
            </worksheet>
            """
        },
        """<?xml version="1.0"?>
        <!DOCTYPE lolz [
          <!ENTITY lol "lol">
          <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
          <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
        ]>
        <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <si><t>Test &lol2; Spreadsheet</t></si>
        </sst>
        """,
    )

    doc = XLSXReader().read(str(path))
    table = doc.sections[0].elements[0]

    assert table.rows[0][0].text == "Test  Spreadsheet"


def test_reads_xlsx_package_absolute_sheet_relationship(tmp_path):
    path = tmp_path / "absolute-sheet.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Absolute sheet</t></is></c></row>
              </sheetData>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/>
        </Relationships>
        """,
    )

    doc = XLSXReader().read(str(path))

    assert doc.sections[0].elements[0].rows[0][0].text == "Absolute sheet"


def test_reads_xlsx_backslash_package_entries(tmp_path):
    path = tmp_path / "backslash-entries.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr(
            "xl\\workbook.xml",
            """
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets>
                <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
              </sheets>
            </workbook>
            """,
        )
        zf.writestr(
            "xl\\_rels\\workbook.xml.rels",
            """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/>
            </Relationships>
            """,
        )
        zf.writestr(
            "xl\\worksheets\\sheet1.xml",
            """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Backslash package</t></is></c></row>
              </sheetData>
            </worksheet>
            """,
        )

    doc = XLSXReader().read(str(path))

    assert doc.sections[0].elements[0].rows[0][0].text == "Backslash package"


def test_reads_xlsx_workbook_defined_names_as_metadata(tmp_path):
    path = tmp_path / "defined-names.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Data" sheetId="1" r:id="rId1"/>
          </sheets>
          <definedNames>
            <definedName name="SalesRange">Data!$A$1:$B$2</definedName>
            <definedName name="_xlnm.Print_Area" localSheetId="0">Data!$A$1:$B$2</definedName>
          </definedNames>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Revenue</t></is></c></row>
              </sheetData>
            </worksheet>
            """
        },
    )

    doc = XLSXReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.sections[0].elements[0].text == "Defined name: SalesRange = Data!$A$1:$B$2"
    assert doc.sections[0].elements[1].text == "Defined name: Print_Area = Data!$A$1:$B$2"
    assert "Revenue" in markdown


def test_reads_xlsx_sheet_headers_and_footers(tmp_path):
    path = tmp_path / "headers-footers.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Body</t></is></c></row>
              </sheetData>
              <headerFooter>
                <oddHeader>&amp;L&amp;"Calibri,Regular"&amp;K000000top left&amp;Ctop center&amp;Rtop right</oddHeader>
                <oddFooter>&amp;Lbottom left&amp;Cbottom center&amp;Rbottom right</oddFooter>
              </headerFooter>
            </worksheet>
            """
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "<!-- header: top left | top center | top right -->" in markdown
    assert "| Body |" in markdown
    assert "<!-- footer: bottom left | bottom center | bottom right -->" in markdown


def test_decodes_xlsx_header_footer_literal_ampersands(tmp_path):
    path = tmp_path / "ampersand-header.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData/>
              <headerFooter>
                <oddHeader>&amp;Cone &amp;&amp; two &amp;&amp;&amp;&amp;</oddHeader>
              </headerFooter>
            </worksheet>
            """
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "<!-- header: one & two && -->" in markdown


def test_decodes_xlsx_header_footer_text_after_color_codes(tmp_path):
    path = tmp_path / "color-header.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData/>
              <headerFooter>
                <oddHeader>&amp;L&amp;K000000bottom left&amp;C&amp;K03+000ArialBlue</oddHeader>
              </headerFooter>
            </worksheet>
            """
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "<!-- header: bottom left | ArialBlue -->" in markdown


def test_reads_strict_xlsx_namespace_shared_strings_as_table(tmp_path):
    path = tmp_path / "strict.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main"
          xmlns:r="http://purl.oclc.org/ooxml/officeDocument/relationships">
          <sheets>
            <sheet name="Strict" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1"><v>42</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        """
        <sst xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main">
          <si><t>Strict Label</t></si>
        </sst>
        """,
    )

    doc = XLSXReader().read(str(path))
    table = doc.sections[0].elements[0]

    assert doc.sections[0].provenance.sheet == "Strict"
    assert table.rows[0][0].text == "Strict Label"
    assert table.rows[0][1].text == "42"


def test_reads_xlsx_core_properties_as_markdown_metadata(tmp_path):
    path = tmp_path / "core-props.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Revenue</t></is></c></row></sheetData>
            </worksheet>
            """,
        },
        extra_parts={
            "docProps/core.xml": """
            <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
              xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>Financial Workbook</dc:title>
              <dc:creator>Finance Team</dc:creator>
            </cp:coreProperties>
            """,
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert markdown.startswith("# Financial Workbook\n\nAuthor: Finance Team\n\n## Data\n\n| Revenue |")


def test_reads_xlsx_rich_text_shared_and_inline_strings(tmp_path):
    path = tmp_path / "rich-text.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Rich" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1" t="inlineStr">
                    <is>
                      <r><t>Inline </t></r>
                      <r><t>Rich</t></r>
                    </is>
                  </c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        """
        <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <si>
            <r><t>Shared </t></r>
            <r><t>Rich</t></r>
          </si>
        </sst>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Shared Rich"
    assert table.rows[0][1].text == "Inline Rich"


def test_reads_multiple_xlsx_sheets_in_order(tmp_path):
    path = tmp_path / "multi.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="First" sheetId="1" r:id="rId1"/>
            <sheet name="Second" sheetId="2" r:id="rId2"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1"><v>1</v></c></row></sheetData>
            </worksheet>
            """,
            "xl/worksheets/sheet2.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1"><v>2</v></c></row></sheetData>
            </worksheet>
            """,
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
          <Relationship Id="rId2" Target="worksheets/sheet2.xml"/>
        </Relationships>
        """,
    )

    doc = XLSXReader().read(str(path))

    assert [section.provenance.sheet for section in doc.sections] == ["First", "Second"]
    assert doc.sections[0].elements[0].rows[0][0].text == "1"
    assert doc.sections[1].elements[0].rows[0][0].text == "2"


def test_xlsx_markdown_preserves_multiple_sheet_names(tmp_path):
    path = tmp_path / "multi-sheet-markdown.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Revenue" sheetId="1" r:id="rId1"/>
            <sheet name="Costs" sheetId="2" r:id="rId2"/>
          </sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>ARR</t></is></c></row></sheetData>
            </worksheet>
            """,
            "xl/worksheets/sheet2.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>COGS</t></is></c></row></sheetData>
            </worksheet>
            """,
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
          <Relationship Id="rId2" Target="worksheets/sheet2.xml"/>
        </Relationships>
        """,
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert markdown == (
        "## Revenue\n\n"
        "| ARR |\n"
        "| --- |\n\n"
        "## Costs\n\n"
        "| COGS |\n"
        "| --- |"
    )


def test_reads_xlsx_drawing_textboxes_and_image_references(tmp_path):
    path = tmp_path / "drawing.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Drawing" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData/>
              <drawing r:id="rIdDrawing"/>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdDrawing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
            </Relationships>
            """,
            "xl/drawings/drawing1.xml": """
            <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <xdr:twoCellAnchor>
                <xdr:from><xdr:col>1</xdr:col><xdr:row>2</xdr:row></xdr:from>
                <xdr:sp>
                  <xdr:nvSpPr><xdr:cNvPr id="2" name="TextBox 1"/><xdr:cNvSpPr txBox="1"/></xdr:nvSpPr>
                  <xdr:txBody>
                    <a:bodyPr/><a:lstStyle/>
                    <a:p><a:r><a:t>Line 1</a:t></a:r></a:p>
                    <a:p><a:r><a:t>Line </a:t></a:r><a:r><a:t>2</a:t></a:r></a:p>
                  </xdr:txBody>
                </xdr:sp>
                <xdr:clientData/>
              </xdr:twoCellAnchor>
              <xdr:oneCellAnchor>
                <xdr:from><xdr:col>3</xdr:col><xdr:row>5</xdr:row></xdr:from>
                <xdr:pic>
                  <xdr:nvPicPr><xdr:cNvPr id="3" name="Picture 2" descr="Revenue chart"/></xdr:nvPicPr>
                  <xdr:blipFill><a:blip r:embed="rIdImage"/></xdr:blipFill>
                </xdr:pic>
                <xdr:clientData/>
              </xdr:oneCellAnchor>
            </xdr:wsDr>
            """,
            "xl/drawings/_rels/drawing1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
            </Relationships>
            """,
            "xl/media/image1.png": b"fake-png",
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "Line 1\nLine 2" in markdown
    assert "![Revenue chart Picture 2](xl/media/image1.png)" in markdown


def test_records_xlsx_drawing_image_relationship_as_asset(tmp_path):
    path = tmp_path / "drawing-asset.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Drawing" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData/>
              <drawing r:id="rIdDrawing"/>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdDrawing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
            </Relationships>
            """,
            "xl/drawings/drawing1.xml": """
            <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <xdr:oneCellAnchor>
                <xdr:from><xdr:col>3</xdr:col><xdr:row>5</xdr:row></xdr:from>
                <xdr:pic>
                  <xdr:nvPicPr><xdr:cNvPr id="3" name="Picture 2" descr="Revenue chart"/></xdr:nvPicPr>
                  <xdr:blipFill><a:blip r:embed="rIdImage"/></xdr:blipFill>
                </xdr:pic>
                <xdr:clientData/>
              </xdr:oneCellAnchor>
            </xdr:wsDr>
            """,
            "xl/drawings/_rels/drawing1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
            </Relationships>
            """,
            "xl/media/image1.png": b"PNG",
        },
    )

    doc = XLSXReader().read(str(path))

    assert len(doc.assets) == 1
    asset = doc.assets[0]
    assert asset.id == "rIdImage"
    assert asset.source_path == "xl/media/image1.png"
    assert asset.filename == "image1.png"
    assert asset.content_type == "image/png"
    assert asset.metadata["label"] == "Revenue chart Picture 2"
    assert asset.metadata["source_format"] == "xlsx"
    assert asset.metadata["sheet"] == "Drawing"


def test_reads_xlsx_vml_ole_preview_image_and_records_asset(tmp_path):
    path = tmp_path / "vml-ole-preview.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
              xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing">
              <sheetData/>
              <legacyDrawing r:id="rIdVML"/>
              <oleObjects>
                <mc:AlternateContent>
                  <mc:Choice Requires="x14">
                    <oleObject progId="Acrobat Document" shapeId="1025" r:id="rIdOle">
                      <objectPr r:id="rIdPreview"/>
                    </oleObject>
                  </mc:Choice>
                  <mc:Fallback>
                    <oleObject progId="Acrobat Document" shapeId="1025" r:id="rIdOle"/>
                  </mc:Fallback>
                </mc:AlternateContent>
              </oleObjects>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdVML" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing" Target="../drawings/vmlDrawing1.vml"/>
              <Relationship Id="rIdPreview" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.emf"/>
              <Relationship Id="rIdOle" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="../embeddings/oleObject1.bin"/>
            </Relationships>
            """,
            "xl/drawings/vmlDrawing1.vml": """
            <xml xmlns:v="urn:schemas-microsoft-com:vml"
              xmlns:o="urn:schemas-microsoft-com:office:office">
              <v:shape id="_x0000_s1025">
                <v:imagedata o:relid="rIdImage" o:title="Embedded PDF preview"/>
              </v:shape>
            </xml>
            """,
            "xl/drawings/_rels/vmlDrawing1.vml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.emf"/>
            </Relationships>
            """,
            "xl/media/image1.emf": b"EMF",
            "xl/embeddings/oleObject1.bin": b"OLE",
        },
    )

    doc = XLSXReader().read(str(path))
    markdown = to_markdown(doc)

    assert "![Embedded PDF preview](xl/media/image1.emf)" in markdown
    assert len(doc.assets) == 2
    assert {asset.source_path for asset in doc.assets} == {
        "xl/media/image1.emf",
        "xl/embeddings/oleObject1.bin",
    }
    preview = next(asset for asset in doc.assets if asset.source_path == "xl/media/image1.emf")
    assert preview.content_type == "image/x-emf"
    assert preview.metadata["label"] == "Embedded PDF preview"
    embedded = next(asset for asset in doc.assets if asset.source_path == "xl/embeddings/oleObject1.bin")
    assert embedded.content_type == "application/vnd.openxmlformats-officedocument.oleObject"
    assert embedded.metadata["relationship_type"] == "oleObject"


def test_reads_xlsx_with_malformed_vml_button_markup(tmp_path):
    path = tmp_path / "malformed-vml-button.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData/>
              <legacyDrawing r:id="rIdVML"/>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdVML" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing" Target="../drawings/vmlDrawing1.vml"/>
            </Relationships>
            """,
            "xl/drawings/vmlDrawing1.vml": """
            <xml xmlns:v="urn:schemas-microsoft-com:vml"
              xmlns:o="urn:schemas-microsoft-com:office:office"
              xmlns:x="urn:schemas-microsoft-com:office:excel">
              <v:shape id="_x0000_s1025">
                <v:textbox><div><font><b>Multi<br>
                  Line<br>
                  Text</b></font></div></v:textbox>
                <x:ClientData ObjectType="Button"/>
              </v:shape>
            </xml>
            """,
        },
    )

    doc = XLSXReader().read(str(path))

    assert doc.source_format == "xlsx"
    assert doc.sections[0].provenance.sheet == "Sheet1"


def test_reads_xlsx_chart_title_and_cached_series_data(tmp_path):
    path = tmp_path / "chart.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="ChartData" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData/>
              <drawing r:id="rIdDrawing"/>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdDrawing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
            </Relationships>
            """,
            "xl/drawings/drawing1.xml": """
            <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">
              <xdr:twoCellAnchor>
                <xdr:from><xdr:col>1</xdr:col><xdr:row>2</xdr:row></xdr:from>
                <xdr:graphicFrame>
                  <a:graphic><a:graphicData><c:chart r:id="rIdChart"/></a:graphicData></a:graphic>
                </xdr:graphicFrame>
              </xdr:twoCellAnchor>
            </xdr:wsDr>
            """,
            "xl/drawings/_rels/drawing1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
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
                  </c:lineChart>
                </c:plotArea>
              </c:chart>
            </c:chartSpace>
            """,
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "### Revenue Chart" in markdown
    assert "| Category | ARR |" in markdown
    assert "| Q1 | 10 |" in markdown
    assert "| Q2 | 20 |" in markdown


def test_reads_xlsx_multi_series_chart_as_single_table(tmp_path):
    path = tmp_path / "multi-series-chart.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="ChartData" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData/>
              <drawing r:id="rIdDrawing"/>
            </worksheet>
            """
        },
        workbook_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdDrawing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
            </Relationships>
            """,
            "xl/drawings/drawing1.xml": """
            <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">
              <xdr:twoCellAnchor>
                <xdr:from><xdr:col>1</xdr:col><xdr:row>2</xdr:row></xdr:from>
                <xdr:graphicFrame>
                  <a:graphic><a:graphicData><c:chart r:id="rIdChart"/></a:graphicData></a:graphic>
                </xdr:graphicFrame>
              </xdr:twoCellAnchor>
            </xdr:wsDr>
            """,
            "xl/drawings/_rels/drawing1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
            </Relationships>
            """,
            "xl/charts/chart1.xml": """
            <c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">
              <c:chart><c:plotArea><c:lineChart>
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
              </c:lineChart></c:plotArea></c:chart>
            </c:chartSpace>
            """,
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "| Category | ARR | Profit |" in markdown
    assert "| Q1 | 10 | 3 |" in markdown
    assert "| Q2 | 20 | 8 |" in markdown


def test_reads_xlsx_sparse_rows_and_columns_by_cell_references(tmp_path):
    path = tmp_path / "sparse-grid.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Sparse" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Top Left</t></is></c>
                  <c r="C1" t="inlineStr"><is><t>Top Right</t></is></c>
                </row>
                <row r="3">
                  <c r="A3" t="inlineStr"><is><t>Bottom Left</t></is></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 3
    assert table.col_count == 3
    assert table.rows[0][0].text == "Top Left"
    assert table.rows[0][1].text == ""
    assert table.rows[0][2].text == "Top Right"
    assert [cell.text for cell in table.rows[1]] == ["", "", ""]
    assert table.rows[2][0].text == "Bottom Left"


def test_reads_xlsx_implicit_rows_and_columns_without_cell_references(tmp_path):
    path = tmp_path / "implicit-grid.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Implicit" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row>
                  <c t="inlineStr"><is><t>Description</t></is></c>
                  <c t="inlineStr"><is><t>Rate</t></is></c>
                </row>
                <row>
                  <c t="inlineStr"><is><t>Prime</t></is></c>
                  <c t="inlineStr"><is><t>0.032500</t></is></c>
                </row>
                <row>
                  <c t="inlineStr"><is><t>10 Year Treasury</t></is></c>
                  <c t="inlineStr"><is><t>0.026480</t></is></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    markdown = to_markdown(XLSXReader().read(str(path)))

    assert "| Description | Rate |" in markdown
    assert "| Prime | 0.032500 |" in markdown
    assert "| 10 Year Treasury | 0.026480 |" in markdown


def test_ignores_blank_styled_cells_when_calculating_xlsx_table_width(tmp_path):
    path = tmp_path / "blank-styled-cells.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Only value</t></is></c>
                  <c r="Z1" s="1"/>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.col_count == 1
    assert table.rows[0][0].text == "Only value"


def test_skips_blank_styled_xlsx_cells_before_value_parsing(tmp_path, monkeypatch):
    path = tmp_path / "skip-blank-styled-cells.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Only value</t></is></c>
                  <c r="Z1" s="1"/>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )
    reader = XLSXReader()
    original_cell_text = reader._cell_text
    calls = []

    def counting_cell_text(cell_elem, shared_strings, styles, shared_formulas, cell_children=None):
        calls.append(cell_elem.get("r"))
        return original_cell_text(cell_elem, shared_strings, styles, shared_formulas, cell_children)

    monkeypatch.setattr(reader, "_cell_text", counting_cell_text)

    table = reader.read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Only value"
    assert calls == ["A1"]


def test_skips_unreferenced_empty_xlsx_cells_before_child_scanning(tmp_path, monkeypatch):
    import dochan.ooxml.xlsx as xlsx_module

    path = tmp_path / "skip-empty-before-child-scan.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <mergeCells count="1"><mergeCell ref="A2:B2"/></mergeCells>
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Only value</t></is></c>
                  <c r="Z1" s="1"/>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )
    reader = XLSXReader()
    original_cell_children = reader._cell_children
    original_column_index = xlsx_module._column_index

    def guarded_cell_children(cell_elem):
        if cell_elem.get("r") == "Z1":
            raise AssertionError("empty unreferenced cells should be skipped before child scanning")
        return original_cell_children(cell_elem)

    def guarded_column_index(cell_ref):
        if cell_ref == "Z1":
            raise AssertionError("empty unreferenced cells should be skipped before column parsing")
        return original_column_index(cell_ref)

    monkeypatch.setattr(reader, "_cell_children", guarded_cell_children)
    monkeypatch.setattr(xlsx_module, "_column_index", guarded_column_index)

    table = reader.read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Only value"


def test_ignores_trailing_blank_styled_xlsx_rows(tmp_path):
    path = tmp_path / "trailing-blank-styled-row.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Only value</t></is></c>
                </row>
                <row r="10">
                  <c r="A10" s="1"/>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 1
    assert table.rows[0][0].text == "Only value"


def test_reads_xlsx_booleans_and_cached_formula_values(tmp_path):
    path = tmp_path / "typed.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="b"><v>1</v></c>
                  <c r="B1"><f>SUM(1,2)</f><v>3</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="b"><v>0</v></c>
                  <c r="B2" t="str"><f>CONCAT(&quot;A&quot;,&quot;B&quot;)</f><v>AB</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "TRUE"
    assert table.rows[0][1].text == "3 (=SUM(1,2))"
    assert table.rows[1][0].text == "FALSE"
    assert table.rows[1][1].text == 'AB (=CONCAT("A","B"))'


def test_reads_xlsx_formula_metadata_with_cached_values(tmp_path):
    path = tmp_path / "formula-metadata.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Formulas" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1"><f>SUM(1,2)</f><v>3</v></c>
                  <c r="B1" t="str"><f>CONCAT(&quot;A&quot;,&quot;B&quot;)</f><v>AB</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "3 (=SUM(1,2))"
    assert table.rows[0][1].text == 'AB (=CONCAT("A","B"))'


def test_xlsx_cell_text_uses_single_child_scan_for_value_and_formula():
    class FakeChild:
        def __init__(self, tag, text=None, attrs=None):
            self.tag = tag
            self.text = text
            self._attrs = attrs or {}

        def get(self, name, default=None):
            return self._attrs.get(name, default)

    class FakeCell:
        tag = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"

        def __init__(self):
            self.children = [
                FakeChild("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f", "SUM(1,2)"),
                FakeChild("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v", "3"),
            ]

        def __iter__(self):
            return iter(self.children)

        def get(self, name, default=None):
            return default

        def find(self, *args, **kwargs):
            raise AssertionError("cell child lookup should use one scan, not repeated find()")

    text = XLSXReader()._cell_text(FakeCell(), [], [], {})

    assert text == "3 (=SUM(1,2))"


def test_reads_xlsx_error_cells_and_formula_errors(tmp_path):
    path = tmp_path / "error-cells.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Errors" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="e"><v>#N/A</v></c>
                  <c r="B1" t="e"><f>1/0</f><v>#DIV/0!</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "#N/A"
    assert table.rows[0][1].text == "#DIV/0! (=1/0)"


def test_reads_xlsx_shared_formula_metadata(tmp_path):
    path = tmp_path / "shared-formula.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Formulas" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1"><v>1</v></c>
                  <c r="B1"><f t="shared" si="0" ref="B1:B2">A1*2</f><v>2</v></c>
                </row>
                <row r="2">
                  <c r="A2"><v>2</v></c>
                  <c r="B2"><f t="shared" si="0"/><v>4</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][1].text == "2 (=A1*2)"
    assert table.rows[1][1].text == "4 (=A2*2)"


def test_reads_xlsx_shared_formula_whole_column_and_row_ranges(tmp_path):
    path = tmp_path / "shared-formula-ranges.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Formulas" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1"><v>1</v></c>
                  <c r="B1"><f t="shared" si="0" ref="B1:C2">SUM(A:A)+SUM(1:1)</f><v>10</v></c>
                </row>
                <row r="2">
                  <c r="A2"><v>2</v></c>
                  <c r="C2"><f t="shared" si="0"/><v>20</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][1].text == "10 (=SUM(A:A)+SUM(1:1))"
    assert table.rows[1][2].text == "20 (=SUM(B:B)+SUM(2:2))"


def test_reads_xlsx_shared_formula_without_prescanning_sheet_cells(tmp_path, monkeypatch):
    path = tmp_path / "shared-formula-single-pass.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Formulas" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1"><v>1</v></c>
                  <c r="B1"><f t="shared" si="0" ref="B1:B2">A1*2</f><v>2</v></c>
                </row>
                <row r="2">
                  <c r="A2"><v>2</v></c>
                  <c r="B2"><f t="shared" si="0"/><v>4</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
    )
    reader = XLSXReader()

    def fail_prescan(root):
        raise AssertionError("shared formulas should be collected while reading cells")

    monkeypatch.setattr(reader, "_read_shared_formulas", fail_prescan)

    table = reader.read(str(path)).sections[0].elements[0]

    assert table.rows[0][1].text == "2 (=A1*2)"
    assert table.rows[1][1].text == "4 (=A2*2)"


def test_reads_xlsx_merged_cells_as_spans(tmp_path):
    path = tmp_path / "merged.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Merged Header</t></is></c></row>
                <row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>2</v></c></row>
              </sheetData>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Merged Header"
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away
    assert table.rows[1][0].text == "1"
    assert table.rows[1][1].text == "2"


def test_reads_xlsx_dates_percentages_and_decimals_from_styles(tmp_path):
    path = tmp_path / "styled.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>45292</v></c>
                  <c r="B1" s="2"><v>0.125</v></c>
                  <c r="C1" s="3"><v>12.345</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="1">
            <numFmt numFmtId="165" formatCode="0.00%"/>
          </numFmts>
          <cellXfs count="4">
            <xf numFmtId="0"/>
            <xf numFmtId="14"/>
            <xf numFmtId="165"/>
            <xf numFmtId="2"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "2024-01-01"
    assert table.rows[0][1].text == "12.50%"
    assert table.rows[0][2].text == "12.35"


def test_reads_xlsx_time_and_duration_number_formats(tmp_path):
    path = tmp_path / "time-duration.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Times" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/styles.xml": """
            <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <numFmts count="2">
                <numFmt numFmtId="165" formatCode="h:mm"/>
                <numFmt numFmtId="166" formatCode="[h]:mm:ss"/>
              </numFmts>
              <cellXfs count="2">
                <xf numFmtId="165"/>
                <xf numFmtId="166"/>
              </cellXfs>
            </styleSheet>
            """,
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="0"><v>0.5</v></c>
                  <c r="B1" s="1"><v>1.5</v></c>
                </row>
              </sheetData>
            </worksheet>
            """,
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "12:00"
    assert table.rows[0][1].text == "36:00:00"


def test_reads_xlsx_currency_and_thousands_number_formats(tmp_path):
    path = tmp_path / "number-formats.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>1234.5</v></c>
                  <c r="B1" s="2"><v>1234</v></c>
                  <c r="C1" s="3"><v>1234.56</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="3">
            <numFmt numFmtId="165" formatCode="$#,##0.00"/>
            <numFmt numFmtId="166" formatCode="#,##0"/>
            <numFmt numFmtId="167" formatCode="#,##0.0"/>
          </numFmts>
          <cellXfs count="4">
            <xf numFmtId="0"/>
            <xf numFmtId="165"/>
            <xf numFmtId="166"/>
            <xf numFmtId="167"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "$1,234.50"
    assert table.rows[0][1].text == "1,234"
    assert table.rows[0][2].text == "1,234.6"


def test_reads_xlsx_negative_accounting_number_formats(tmp_path):
    path = tmp_path / "negative-accounting.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>-1234.5</v></c>
                  <c r="B1" s="2"><v>-1234</v></c>
                  <c r="C1" s="3"><v>-0.125</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="3">
            <numFmt numFmtId="165" formatCode="$#,##0.00;[Red]($#,##0.00)"/>
            <numFmt numFmtId="166" formatCode="#,##0;(#,##0)"/>
            <numFmt numFmtId="167" formatCode="0.0%;[Red](0.0%)"/>
          </numFmts>
          <cellXfs count="4">
            <xf numFmtId="0"/>
            <xf numFmtId="165"/>
            <xf numFmtId="166"/>
            <xf numFmtId="167"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "($1,234.50)"
    assert table.rows[0][1].text == "(1,234)"
    assert table.rows[0][2].text == "(12.5%)"


def test_reads_xlsx_zero_padded_identifier_number_formats(tmp_path):
    path = tmp_path / "zero-padded-identifiers.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>123</v></c>
                  <c r="B1" s="2"><v>1234567</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="2">
            <numFmt numFmtId="165" formatCode="00000"/>
            <numFmt numFmtId="166" formatCode="000-0000"/>
          </numFmts>
          <cellXfs count="3">
            <xf numFmtId="0"/>
            <xf numFmtId="165"/>
            <xf numFmtId="166"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "00123"
    assert table.rows[0][1].text == "123-4567"


def test_reads_xlsx_literal_prefix_and_suffix_number_formats(tmp_path):
    path = tmp_path / "literal-number-formats.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>12</v></c>
                  <c r="B1" s="2"><v>3.5</v></c>
                  <c r="C1" s="3"><v>42</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="3">
            <numFmt numFmtId="165" formatCode="0 &quot;kg&quot;"/>
            <numFmt numFmtId="166" formatCode="0.0&quot;x&quot;"/>
            <numFmt numFmtId="167" formatCode="&quot;SKU-&quot;0000"/>
          </numFmts>
          <cellXfs count="4">
            <xf numFmtId="0"/>
            <xf numFmtId="165"/>
            <xf numFmtId="166"/>
            <xf numFmtId="167"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "12 kg"
    assert table.rows[0][1].text == "3.5x"
    assert table.rows[0][2].text == "SKU-0042"


def test_reads_xlsx_fraction_number_formats(tmp_path):
    path = tmp_path / "fraction-number-formats.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>0.5</v></c>
                  <c r="B1" s="2"><v>3.25</v></c>
                  <c r="C1" s="2"><v>-1.125</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <cellXfs count="3">
            <xf numFmtId="0"/>
            <xf numFmtId="12"/>
            <xf numFmtId="13"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "1/2"
    assert table.rows[0][1].text == "3 1/4"
    assert table.rows[0][2].text == "-1 1/8"


def test_reads_xlsx_scientific_number_formats(tmp_path):
    path = tmp_path / "scientific-number-formats.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" s="1"><v>12345</v></c>
                  <c r="B1" s="1"><v>0.0012</v></c>
                  <c r="C1" s="2"><v>-9876</v></c>
                </row>
              </sheetData>
            </worksheet>
            """
        },
        styles_xml="""
        <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <numFmts count="1">
            <numFmt numFmtId="165" formatCode="0.0E+00"/>
          </numFmts>
          <cellXfs count="3">
            <xf numFmtId="0"/>
            <xf numFmtId="11"/>
            <xf numFmtId="165"/>
          </cellXfs>
        </styleSheet>
        """,
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "1.23E+04"
    assert table.rows[0][1].text == "1.20E-03"
    assert table.rows[0][2].text == "-9.9E+03"


def test_caches_xlsx_number_format_metadata(monkeypatch):
    reader = XLSXReader()
    original_decimal_places = reader._decimal_places
    calls = []

    def counting_decimal_places(fmt):
        calls.append(fmt)
        return original_decimal_places(fmt)

    monkeypatch.setattr(reader, "_decimal_places", counting_decimal_places)

    assert reader._format_cell_value("12.345", "0.00") == "12.35"
    assert reader._format_cell_value("67.891", "0.00") == "67.89"

    assert calls == ["0.00"]


def test_reads_xlsx_external_hyperlinks_with_targets(tmp_path):
    path = tmp_path / "hyperlink.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Links" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Example</t></is></c></row>
              </sheetData>
              <hyperlinks><hyperlink ref="A1" r:id="rIdLink"/></hyperlinks>
            </worksheet>
            """
        },
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/report" TargetMode="External"/>
            </Relationships>
            """,
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Example <https://example.com/report>"


def test_reads_xlsx_range_hyperlinks_with_targets(tmp_path):
    path = tmp_path / "range-hyperlink.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Links" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>First</t></is></c>
                  <c r="B1" t="inlineStr"><is><t>Second</t></is></c>
                </row>
              </sheetData>
              <hyperlinks><hyperlink ref="A1:B1" r:id="rIdRangeLink"/></hyperlinks>
            </worksheet>
            """
        },
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdRangeLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/range" TargetMode="External"/>
            </Relationships>
            """,
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "First <https://example.com/range>"
    assert table.rows[0][1].text == "Second <https://example.com/range>"


def test_reads_xlsx_internal_hyperlinks_with_display_and_location(tmp_path):
    path = tmp_path / "internal-hyperlink.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Links" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1"/></row>
              </sheetData>
              <hyperlinks><hyperlink ref="A1" location="Data!A1" display="Jump to Data"/></hyperlinks>
            </worksheet>
            """
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Jump to Data <#Data!A1>"


def test_reads_xlsx_cell_comments_from_comment_relationship(tmp_path):
    path = tmp_path / "comments.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Comments" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Revenue</t></is></c></row>
              </sheetData>
            </worksheet>
            """
        },
        extra_parts={
            "xl/worksheets/_rels/sheet1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments1.xml"/>
            </Relationships>
            """,
            "xl/comments1.xml": """
            <comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <authors><author>Analyst</author></authors>
              <commentList>
                <comment ref="A1" authorId="0">
                  <text>
                    <r><t>Check source</t></r>
                    <r><t> before release</t></r>
                  </text>
                </comment>
              </commentList>
            </comments>
            """,
        },
    )

    table = XLSXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Revenue [comment: Analyst: Check source before release]"


def test_dochan_routes_xlsx_to_native_reader(tmp_path):
    path = tmp_path / "integrated.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Hello</t></is></c></row>
              </sheetData>
            </worksheet>
            """
        },
    )

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "xlsx"
    assert doc.to_markdown() == "## Data\n\n| Hello |\n| --- |"


def test_xlsx_markdown_preserves_single_meaningful_sheet_name(tmp_path):
    path = tmp_path / "single-named-sheet.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Hello</t></is></c></row>
              </sheetData>
            </worksheet>
            """
        },
    )

    assert to_markdown(XLSXReader().read(str(path))) == "## Report\n\n| Hello |\n| --- |"


def test_batch_convert_includes_xlsx_by_default(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    path = input_dir / "book.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1"><v>42</v></c></row></sheetData>
            </worksheet>
            """
        },
    )

    summary = batch_convert(str(input_dir), str(output_dir), output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "book.md").read_text(encoding="utf-8") == "## Data\n\n| 42 |\n| --- |"


def test_cli_info_reports_xlsx_format(tmp_path, capsys):
    class Args:
        pass

    path = tmp_path / "info.xlsx"
    _write_xlsx(
        path,
        """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        {
            "xl/worksheets/sheet1.xml": """
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1"><v>1</v></c></row></sheetData>
            </worksheet>
            """
        },
    )
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "xlsx"' in out
