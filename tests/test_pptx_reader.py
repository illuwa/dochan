import zipfile

from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import _cmd_info
from dochan.ooxml.pptx import PPTXReader
from dochan.output.markdown import to_markdown


def _write_pptx(path, presentation_xml, slide_xmls, presentation_rels_xml=None, extra_parts=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("ppt/presentation.xml", presentation_xml)
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            presentation_rels_xml
            or """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Target="slides/slide1.xml"/>
            </Relationships>
            """,
        )
        for name, data in slide_xmls.items():
            zf.writestr(name, data)
        for name, data in (extra_parts or {}).items():
            zf.writestr(name, data)


def test_reads_pptx_slide_text_in_order(tmp_path):
    path = tmp_path / "slides.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst>
            <p:sldId id="256" r:id="rId1"/>
            <p:sldId id="257" r:id="rId2"/>
          </p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>First slide</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/slide2.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Second slide</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
        """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="slides/slide1.xml"/>
          <Relationship Id="rId2" Target="slides/slide2.xml"/>
        </Relationships>
        """,
    )

    doc = PPTXReader().read(str(path))

    assert doc.source_format == "pptx"
    assert [section.provenance.slide for section in doc.sections] == [1, 2]
    assert doc.sections[0].elements[0].text == "First slide"
    assert doc.sections[1].elements[0].text == "Second slide"


def test_reads_pptx_package_absolute_slide_relationship(tmp_path):
    path = tmp_path / "absolute-slide.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst>
            <p:sldId id="256" r:id="rId1"/>
          </p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Absolute slide</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
        """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="/ppt/slides/slide1.xml"/>
        </Relationships>
        """,
    )

    doc = PPTXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Absolute slide"


def test_pptx_markdown_preserves_multiple_slide_boundaries(tmp_path):
    path = tmp_path / "multi-slide-markdown.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst>
            <p:sldId id="256" r:id="rId1"/>
            <p:sldId id="257" r:id="rId2"/>
          </p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Overview</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/slide2.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Appendix</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
        """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="slides/slide1.xml"/>
          <Relationship Id="rId2" Target="slides/slide2.xml"/>
        </Relationships>
        """,
    )

    markdown = to_markdown(PPTXReader().read(str(path)))

    assert markdown == "## Slide 1\n\nOverview\n\n## Slide 2\n\nAppendix"


def test_reads_pptx_title_placeholder_as_markdown_heading(tmp_path):
    path = tmp_path / "title-placeholder.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
                  <p:txBody><a:p><a:r><a:t>Presentation Title Text</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:sp>
                  <p:nvSpPr><p:cNvPr id="3" name="Subtitle 2"/><p:cNvSpPr/><p:nvPr><p:ph type="subTitle"/></p:nvPr></p:nvSpPr>
                  <p:txBody><a:p><a:r><a:t>Subtitle Text</a:t></a:r></a:p></p:txBody>
                </p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
    )

    doc = PPTXReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.sections[0].elements[0].heading_level == 1
    assert markdown == "# Presentation Title Text\n\nSubtitle Text"


def test_pptx_markdown_preserves_run_formatting(tmp_path):
    path = tmp_path / "formatted-runs.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p>
                  <a:r><a:rPr b="1"/><a:t>Bold</a:t></a:r>
                  <a:r><a:t> </a:t></a:r>
                  <a:r><a:rPr i="1"/><a:t>Italic</a:t></a:r>
                  <a:r><a:t> </a:t></a:r>
                  <a:r><a:rPr u="sng"/><a:t>Underlined</a:t></a:r>
                  <a:r><a:t> </a:t></a:r>
                  <a:r><a:rPr strike="sngStrike"/><a:t>Struck</a:t></a:r>
                </a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
    )

    doc = PPTXReader().read(str(path))

    assert to_markdown(doc) == "**Bold** *Italic* <u>Underlined</u> ~~Struck~~"


def test_reads_pptx_bullets_and_auto_numbered_paragraphs(tmp_path):
    path = tmp_path / "lists.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
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
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
    )

    markdown = to_markdown(PPTXReader().read(str(path)))

    assert markdown == "• Bullet point\n\n3. Third item\n\n4. Fourth item"


def test_reads_pptx_core_properties_as_markdown_metadata(tmp_path):
    path = tmp_path / "core-props.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Quarterly highlights</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
        extra_parts={
            "docProps/core.xml": """
            <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
              xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>Board Update Deck</dc:title>
              <dc:creator>Alice Analyst</dc:creator>
            </cp:coreProperties>
            """,
        },
    )

    markdown = to_markdown(PPTXReader().read(str(path)))

    assert markdown.startswith("# Board Update Deck\n\nAuthor: Alice Analyst\n\nQuarterly highlights")


def test_reads_pptx_breaks_and_field_text(tmp_path):
    path = tmp_path / "field.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p>
                  <a:r><a:t>Slide</a:t></a:r>
                  <a:br/>
                  <a:fld id="{1}" type="slidenum"><a:t>1</a:t></a:fld>
                </a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    para = PPTXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Slide\n1"


def test_reads_pptx_static_text_from_slide_layout(tmp_path):
    path = tmp_path / "layout-text.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Slide Body</a:t></a:r></a:p></p:txBody>
                </p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
        },
        extra_parts={
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
            </Relationships>
            """,
            "ppt/slideLayouts/slideLayout1.xml": """
            <p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:nvSpPr><p:cNvPr id="2" name="Layout Footer"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
                  <p:spPr><a:xfrm><a:off x="0" y="2000000"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Layout Footer</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:sp>
                  <p:nvSpPr>
                    <p:cNvPr id="3" name="Placeholder"/>
                    <p:cNvSpPr/>
                    <p:nvPr><p:ph type="body"/></p:nvPr>
                  </p:nvSpPr>
                  <p:txBody><a:p><a:r><a:t>Click to add text</a:t></a:r></a:p></p:txBody>
                </p:sp>
              </p:spTree></p:cSld>
            </p:sldLayout>
            """,
        },
    )

    texts = [element.text for element in PPTXReader().read(str(path)).sections[0].elements]

    assert "Slide Body" in texts
    assert "Layout Footer" in texts
    assert "Click to add text" not in texts


def test_reads_pptx_table_as_document_table(tmp_path):
    path = tmp_path / "table.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:graphicFrame><a:graphic><a:graphicData>
                  <a:tbl>
                    <a:tr>
                      <a:tc><a:txBody><a:p><a:r><a:t>Name</a:t></a:r></a:p></a:txBody></a:tc>
                      <a:tc><a:txBody><a:p><a:r><a:t>Value</a:t></a:r></a:p></a:txBody></a:tc>
                    </a:tr>
                    <a:tr>
                      <a:tc><a:txBody><a:p><a:r><a:t>A</a:t></a:r></a:p></a:txBody></a:tc>
                      <a:tc><a:txBody><a:p><a:r><a:t>1</a:t></a:r></a:p></a:txBody></a:tc>
                    </a:tr>
                  </a:tbl>
                </a:graphicData></a:graphic></p:graphicFrame>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    table = PPTXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[0][0].text == "Name"
    assert table.rows[1][1].text == "1"


def test_reads_pptx_merged_table_cells_as_spans(tmp_path):
    path = tmp_path / "merged-table.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:graphicFrame><a:graphic><a:graphicData>
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
            """
        },
    )

    table = PPTXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Merged Header"
    assert table.rows[0][0].provenance.source_format == "pptx"
    assert table.rows[0][0].provenance.slide == 1
    assert table.rows[0][0].provenance.cell == "R1C1"
    assert table.rows[0][0].provenance.path == "ppt/slides/slide1.xml"
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away
    assert table.rows[1][0].text == "Merged Row"
    assert table.rows[1][0].row_span == 2
    assert table.rows[2][0].is_merged_away
    assert table.rows[2][1].text == "Q2"


def test_reads_pptx_elements_by_vertical_position(tmp_path):
    path = tmp_path / "ordered.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Title</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="1000000"/></p:xfrm>
                  <a:graphic><a:graphicData><a:tbl>
                    <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Middle table</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
                  </a:tbl></a:graphicData></a:graphic>
                </p:graphicFrame>
                <p:sp>
                  <p:spPr><a:xfrm><a:off x="0" y="2000000"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Footer</a:t></a:r></a:p></p:txBody>
                </p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert elements[0].text == "Title"
    assert elements[1].rows[0][0].text == "Middle table"
    assert elements[2].text == "Footer"


def test_reads_pptx_graphic_frame_position_before_lower_shape(tmp_path):
    path = tmp_path / "frame-position.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:spPr><a:xfrm><a:off x="0" y="1000000"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Lower text</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="0"/></p:xfrm>
                  <a:graphic><a:graphicData><a:tbl>
                    <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Top table</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
                  </a:tbl></a:graphicData></a:graphic>
                </p:graphicFrame>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert elements[0].rows[0][0].text == "Top table"
    assert elements[1].text == "Lower text"


def test_reads_pptx_graphic_frames_by_position(tmp_path):
    path = tmp_path / "frame-frame-position.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="1000000"/></p:xfrm>
                  <a:graphic><a:graphicData><a:tbl>
                    <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Lower table</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
                  </a:tbl></a:graphicData></a:graphic>
                </p:graphicFrame>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="0"/></p:xfrm>
                  <a:graphic><a:graphicData><a:tbl>
                    <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Top table</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
                  </a:tbl></a:graphicData></a:graphic>
                </p:graphicFrame>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert elements[0].rows[0][0].text == "Top table"
    assert elements[1].rows[0][0].text == "Lower table"


def test_reads_pptx_text_inside_grouped_shape(tmp_path):
    path = tmp_path / "grouped-shape.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Slide title</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:grpSp>
                  <p:grpSpPr><a:xfrm><a:off x="0" y="1000000"/></a:xfrm></p:grpSpPr>
                  <p:sp>
                    <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                    <p:txBody><a:p><a:r><a:t>Grouped insight</a:t></a:r></a:p></p:txBody>
                  </p:sp>
                </p:grpSp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert [elem.text for elem in elements] == ["Slide title", "Grouped insight"]


def test_reads_pptx_grouped_shape_position_from_child_coordinate_space(tmp_path):
    path = tmp_path / "grouped-shape-child-offset.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:spPr><a:xfrm><a:off x="0" y="2000000"/></a:xfrm></p:spPr>
                  <p:txBody><a:p><a:r><a:t>Lower standalone</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:grpSp>
                  <p:grpSpPr>
                    <a:xfrm>
                      <a:off x="0" y="1000000"/>
                      <a:ext cx="1000000" cy="1000000"/>
                      <a:chOff x="0" y="5000000"/>
                      <a:chExt cx="1000000" cy="1000000"/>
                    </a:xfrm>
                  </p:grpSpPr>
                  <p:sp>
                    <p:spPr><a:xfrm><a:off x="0" y="5000000"/></a:xfrm></p:spPr>
                    <p:txBody><a:p><a:r><a:t>Grouped top</a:t></a:r></a:p></p:txBody>
                  </p:sp>
                </p:grpSp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert [elem.text for elem in elements] == ["Grouped top", "Lower standalone"]


def test_reads_pptx_speaker_notes_from_slide_relationship(tmp_path):
    path = tmp_path / "notes.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Slide title</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdNotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/>
            </Relationships>
            """,
            "ppt/notesSlides/notesSlide1.xml": """
            <p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Speaker note detail</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:notes>
            """,
        },
    )

    section = PPTXReader().read(str(path)).sections[0]

    assert [elem.text for elem in section.elements] == ["Slide title", "Speaker note detail"]
    assert section.elements[1].provenance.path == "ppt/notesSlides/notesSlide1.xml"
    assert section.elements[1].runs[0].provenance.path == "ppt/notesSlides/notesSlide1.xml"


def test_reads_pptx_slide_comments_from_relationship(tmp_path):
    path = tmp_path / "comments.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Slide title</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments/comment1.xml"/>
            </Relationships>
            """,
            "ppt/commentAuthors.xml": """
            <p:cmAuthorLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
              <p:cmAuthor id="0" name="Reviewer"/>
            </p:cmAuthorLst>
            """,
            "ppt/comments/comment1.xml": """
            <p:cmLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
              <p:cm authorId="0" idx="1"><p:text>Needs review</p:text></p:cm>
            </p:cmLst>
            """,
        },
    )

    section = PPTXReader().read(str(path)).sections[0]
    markdown = to_markdown(PPTXReader().read(str(path)))

    assert [elem.text for elem in section.elements] == ["Slide title", "[comment: Reviewer: Needs review]"]
    assert section.elements[1].provenance.path == "ppt/comments/comment1.xml"
    assert section.elements[1].runs[0].provenance.path == "ppt/comments/comment1.xml"
    assert "[comment: Reviewer: Needs review]" in markdown


def test_reads_pptx_external_hyperlink_target(tmp_path):
    path = tmp_path / "hyperlink.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p>
                  <a:r>
                    <a:rPr><a:hlinkClick r:id="rIdDeckLink"/></a:rPr>
                    <a:t>Deck link</a:t>
                  </a:r>
                </a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdDeckLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/deck" TargetMode="External"/>
            </Relationships>
            """,
        },
    )

    para = PPTXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Deck link <https://example.com/deck>"
    assert para.runs[0].provenance.source_format == "pptx"
    assert para.runs[0].provenance.slide == 1
    assert para.runs[0].provenance.path == "ppt/slides/slide1.xml"


def test_reads_pptx_shape_level_hyperlink_target(tmp_path):
    path = tmp_path / "shape-hyperlink.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:sp>
                  <p:nvSpPr>
                    <p:cNvPr id="2" name="Linked Button">
                      <a:hlinkClick r:id="rIdButtonLink"/>
                    </p:cNvPr>
                    <p:cNvSpPr/>
                    <p:nvPr/>
                  </p:nvSpPr>
                  <p:txBody><a:p><a:r><a:t>Open dashboard</a:t></a:r></a:p></p:txBody>
                </p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdButtonLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/dashboard" TargetMode="External"/>
            </Relationships>
            """,
        },
    )

    para = PPTXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Open dashboard <https://example.com/dashboard>"


def test_reads_pptx_picture_alt_text_from_cnvpr(tmp_path):
    path = tmp_path / "picture-alt-text.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:pic>
                  <p:nvPicPr>
                    <p:cNvPr id="2" name="Picture 1" title="Revenue Chart" descr="ARR up 42 percent"/>
                    <p:cNvPicPr/>
                    <p:nvPr/>
                  </p:nvPicPr>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                </p:pic>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    para = PPTXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Revenue Chart ARR up 42 percent"


def test_reads_pptx_embedded_image_relationship_as_markdown_reference(tmp_path):
    path = tmp_path / "picture-reference.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:pic>
                  <p:nvPicPr>
                    <p:cNvPr id="2" name="Picture 1" title="Revenue Chart" descr="ARR up 42 percent"/>
                    <p:cNvPicPr/>
                    <p:nvPr/>
                  </p:nvPicPr>
                  <p:blipFill>
                    <a:blip r:embed="rIdImage"/>
                  </p:blipFill>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                </p:pic>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
            </Relationships>
            """,
            "ppt/media/image1.png": b"fake",
        },
    )

    para = PPTXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "![Revenue Chart ARR up 42 percent Picture 1](ppt/media/image1.png)"


def test_records_pptx_embedded_image_relationship_as_asset(tmp_path):
    path = tmp_path / "picture-asset.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:pic>
                  <p:nvPicPr>
                    <p:cNvPr id="2" name="Picture 1" title="Revenue Chart" descr="ARR up 42 percent"/>
                    <p:cNvPicPr/>
                    <p:nvPr/>
                  </p:nvPicPr>
                  <p:blipFill>
                    <a:blip r:embed="rIdImage"/>
                  </p:blipFill>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                </p:pic>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
            </Relationships>
            """,
            "ppt/media/image1.png": b"PNG",
        },
    )

    doc = PPTXReader().read(str(path))

    assert len(doc.assets) == 1
    asset = doc.assets[0]
    assert asset.id == "rIdImage"
    assert asset.source_path == "ppt/media/image1.png"
    assert asset.filename == "image1.png"
    assert asset.content_type == "image/png"
    assert asset.metadata["label"] == "Revenue Chart ARR up 42 percent Picture 1"
    assert asset.metadata["source_format"] == "pptx"
    assert asset.metadata["slide"] == 1


def test_reads_pptx_linked_external_image_reference_without_asset(tmp_path):
    path = tmp_path / "linked-image.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:pic>
                  <p:nvPicPr>
                    <p:cNvPr id="2" name="Linked Logo" descr="/Users/example/logo.jpg"/>
                    <p:cNvPicPr/>
                    <p:nvPr/>
                  </p:nvPicPr>
                  <p:blipFill><a:blip r:link="rIdLinkedImage"/></p:blipFill>
                  <p:spPr><a:xfrm><a:off x="0" y="0"/></a:xfrm></p:spPr>
                </p:pic>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdLinkedImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="file://localhost/Users/example/logo.jpg" TargetMode="External"/>
            </Relationships>
            """,
        },
    )

    doc = PPTXReader().read(str(path))

    assert to_markdown(doc) == "![/Users/example/logo.jpg Linked Logo](file://localhost/Users/example/logo.jpg)"
    assert doc.assets == []


def test_reads_pptx_chart_title_and_cached_series_data(tmp_path):
    path = tmp_path / "chart.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="0"/></p:xfrm>
                  <a:graphic><a:graphicData>
                    <c:chart r:id="rIdChart"/>
                  </a:graphicData></a:graphic>
                </p:graphicFrame>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
            </Relationships>
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
                        <c:pt idx="0"><c:v>Sales</c:v></c:pt>
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
                  </c:barChart>
                </c:plotArea>
              </c:chart>
            </c:chartSpace>
            """,
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert elements[0].text == "Revenue Chart"
    assert elements[0].heading_level == 3
    assert elements[1].rows[0][0].text == "Category"
    assert elements[1].rows[0][1].text == "Sales"
    assert elements[1].rows[1][0].text == "Q1"
    assert elements[1].rows[1][1].text == "10"
    assert elements[1].rows[2][0].text == "Q2"
    assert elements[1].rows[2][1].text == "20"


def test_reads_pptx_multi_series_chart_as_single_table(tmp_path):
    path = tmp_path / "multi-series-chart.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="0"/></p:xfrm>
                  <a:graphic><a:graphicData><c:chart r:id="rIdChart"/></a:graphicData></a:graphic>
                </p:graphicFrame>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
            </Relationships>
            """,
            "ppt/charts/chart1.xml": """
            <c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <c:chart>
                <c:plotArea>
                  <c:barChart>
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
                  </c:barChart>
                </c:plotArea>
              </c:chart>
            </c:chartSpace>
            """,
        },
    )

    table = PPTXReader().read(str(path)).sections[0].elements[0]

    assert [[cell.text for cell in row] for row in table.rows] == [
        ["Category", "ARR", "Profit"],
        ["Q1", "10", "3"],
        ["Q2", "20", "8"],
    ]


def test_reads_pptx_smartart_diagram_text(tmp_path):
    path = tmp_path / "smartart.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:graphicFrame>
                  <p:xfrm><a:off x="0" y="0"/></p:xfrm>
                  <a:graphic><a:graphicData>
                    <dgm:relIds r:dm="rIdDiagramData"/>
                  </a:graphicData></a:graphic>
                </p:graphicFrame>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdDiagramData" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData" Target="../diagrams/data1.xml"/>
            </Relationships>
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
        },
    )

    elements = PPTXReader().read(str(path)).sections[0].elements

    assert [element.text for element in elements] == ["Plan", "Build"]
    assert [element.provenance.path for element in elements] == [
        "ppt/diagrams/data1.xml",
        "ppt/diagrams/data1.xml",
    ]


def test_reads_pptx_internal_slide_hyperlink_target(tmp_path):
    path = tmp_path / "internal-hyperlink.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst>
            <p:sldId id="256" r:id="rId1"/>
            <p:sldId id="257" r:id="rId2"/>
          </p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p>
                  <a:r>
                    <a:rPr>
                      <a:hlinkClick r:id="rIdTargetSlide" action="ppaction://hlinksldjump"/>
                    </a:rPr>
                    <a:t>Jump to summary</a:t>
                  </a:r>
                </a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/slide2.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Summary</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """,
            "ppt/slides/_rels/slide1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdTargetSlide" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slide2.xml"/>
            </Relationships>
            """,
        },
        """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="slides/slide1.xml"/>
          <Relationship Id="rId2" Target="slides/slide2.xml"/>
        </Relationships>
        """,
    )

    para = PPTXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Jump to summary <#ppt/slides/slide2.xml>"


def test_dochan_routes_pptx_to_native_reader(tmp_path):
    path = tmp_path / "integrated.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Hello deck</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "pptx"
    assert doc.to_markdown() == "Hello deck"


def test_batch_convert_includes_pptx_by_default(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    path = input_dir / "deck.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Batch deck</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )

    summary = batch_convert(str(input_dir), str(output_dir), output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "deck.md").read_text(encoding="utf-8") == "Batch deck"


def test_cli_info_reports_pptx_format(tmp_path, capsys):
    class Args:
        pass

    path = tmp_path / "info.pptx"
    _write_pptx(
        path,
        """
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
        </p:presentation>
        """,
        {
            "ppt/slides/slide1.xml": """
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:txBody><a:p><a:r><a:t>Info deck</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>
            """
        },
    )
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "pptx"' in out
