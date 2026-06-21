import zipfile

from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import _cmd_info
from dochan.ooxml.docx import DOCXReader
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown


def _write_docx(
    path,
    document_xml,
    styles_xml=None,
    numbering_xml=None,
    footnotes_xml=None,
    endnotes_xml=None,
    comments_xml=None,
    document_rels_xml=None,
    extra_parts=None,
):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", document_xml)
        if document_rels_xml:
            zf.writestr("word/_rels/document.xml.rels", document_rels_xml)
        if styles_xml:
            zf.writestr("word/styles.xml", styles_xml)
        if numbering_xml:
            zf.writestr("word/numbering.xml", numbering_xml)
        if footnotes_xml:
            zf.writestr("word/footnotes.xml", footnotes_xml)
        if endnotes_xml:
            zf.writestr("word/endnotes.xml", endnotes_xml)
        if comments_xml:
            zf.writestr("word/comments.xml", comments_xml)
        for name, data in (extra_parts or {}).items():
            zf.writestr(name, data)


def test_reads_simple_docx_paragraph(tmp_path):
    path = tmp_path / "simple.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    doc = DOCXReader().read(str(path))

    assert doc.source_format == "docx"
    assert doc.sections[0].elements[0].text == "Hello DOCX"
    assert doc.sections[0].elements[0].provenance.source_format == "docx"
    assert doc.sections[0].elements[0].provenance.path == "word/document.xml"
    assert doc.sections[0].elements[0].runs[0].provenance.path == "word/document.xml"


def test_reads_docx_html_alt_chunk_text(tmp_path):
    path = tmp_path / "alt-chunk-html.docx"
    _write_docx(
        path,
        """
        <w:document
          xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p><w:r><w:t>Before chunk</w:t></w:r></w:p>
            <w:altChunk r:id="htmlDoc"/>
            <w:p><w:r><w:t>After chunk</w:t></w:r></w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship
            Id="htmlDoc"
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk"
            Target="/word/htmlDoc.html"/>
        </Relationships>
        """,
        extra_parts={
            "word/htmlDoc.html": b"""
            <!DOCTYPE html>
            <html>
              <head><style>p { color: red; }</style></head>
              <body>
                <p>Simple paragraph with <strong>emphasis</strong>.</p>
                <table>
                  <tr><th>Col 1</th><th>Col 2</th></tr>
                  <tr><td>ROW 1</td><td>ROW 2</td></tr>
                </table>
              </body>
            </html>
            """,
        },
    )

    markdown = to_markdown(DOCXReader().read(str(path)))

    assert "Before chunk" in markdown
    assert "Simple paragraph with emphasis." in markdown
    assert "Col 1 | Col 2" in markdown
    assert "ROW 1 | ROW 2" in markdown
    assert "After chunk" in markdown


def test_reads_docx_mhtml_alt_chunk_text_and_image_alt(tmp_path):
    path = tmp_path / "alt-chunk-mhtml.docx"
    _write_docx(
        path,
        """
        <w:document
          xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:altChunk r:id="htmlDoc"/>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship
            Id="htmlDoc"
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk"
            Target="htmlDoc.mht"/>
        </Relationships>
        """,
        extra_parts={
            "word/htmlDoc.mht": b"""Subject: HTML import
MIME-Version: 1.0
Content-Type: multipart/related; boundary="chunk-boundary"

--chunk-boundary
Content-Type: text/html; charset="windows-1252"
Content-Transfer-Encoding: quoted-printable

<html><body>
<p>Simple paragraph with an image.</p>
<table><tr><td>ROW 1</td><td><img src=3D"file:///dot.png" alt=3D"Red dot"></td></tr></table>
</body></html>
--chunk-boundary--
""",
        },
    )

    markdown = to_markdown(DOCXReader().read(str(path)))

    assert "Simple paragraph with an image." in markdown
    assert "ROW 1 | Red dot" in markdown


def test_reads_docx_tracked_move_text(tmp_path):
    path = tmp_path / "tracked-move.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:moveFrom w:id="1" w:author="Author">
            <w:ins w:id="2" w:author="Author">
              <w:r><w:t>Moved text</w:t></w:r>
            </w:ins>
          </w:moveFrom>
          <w:del w:id="3" w:author="Author">
            <w:r><w:delText>Deleted text</w:delText></w:r>
          </w:del>
        </w:p>
      </w:body>
    </w:document>
    """)

    markdown = to_markdown(DOCXReader().read(str(path)))

    assert "Moved text" in markdown
    assert "Deleted text" not in markdown


def test_reads_deeply_nested_docx_table_without_crashing(tmp_path):
    path = tmp_path / "deep-table.docx"
    nested = ""
    for level in range(700):
        nested += f"""
        <w:tbl>
          <w:tr>
            <w:tc>
              <w:p><w:r><w:t>Nested level {level}</w:t></w:r></w:p>
        """
    nested += "<w:p><w:r><w:t>Deep leaf</w:t></w:r></w:p>"
    for _ in range(700):
        nested += """
            </w:tc>
          </w:tr>
        </w:tbl>
        """
    _write_docx(path, f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>{nested}</w:body>
    </w:document>
    """)

    markdown = to_markdown(DOCXReader().read(str(path)))

    assert "Nested level 0" in markdown
    assert "Nested level 31" in markdown
    assert "[nested table omitted: depth limit exceeded]" in markdown


def test_reads_docx_core_properties_as_markdown_metadata(tmp_path):
    path = tmp_path / "core-properties.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Body text</w:t></w:r></w:p>
          </w:body>
        </w:document>
        """,
        extra_parts={
            "docProps/core.xml": """
            <cp:coreProperties
              xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
              xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>Board Report</dc:title>
              <dc:creator>Alice Analyst</dc:creator>
            </cp:coreProperties>
            """,
        },
    )

    doc = DOCXReader().read(str(path))

    assert to_markdown(doc) == "# Board Report\n\nAuthor: Alice Analyst\n\nBody text"


def test_reads_bold_and_italic_runs(tmp_path):
    path = tmp_path / "runs.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:rPr><w:b/></w:rPr><w:t>Bold</w:t></w:r>
          <w:r><w:t> and </w:t></w:r>
          <w:r><w:rPr><w:i/></w:rPr><w:t>Italic</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.runs[0].text == "Bold"
    assert para.runs[0].bold
    assert para.runs[1].text == " and "
    assert para.runs[2].text == "Italic"
    assert para.runs[2].italic


def test_docx_markdown_preserves_run_formatting(tmp_path):
    path = tmp_path / "formatted-runs.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:rPr><w:b/></w:rPr><w:t>Bold</w:t></w:r>
          <w:r><w:t> </w:t></w:r>
          <w:r><w:rPr><w:i/></w:rPr><w:t>Italic</w:t></w:r>
          <w:r><w:t> </w:t></w:r>
          <w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>Underlined</w:t></w:r>
          <w:r><w:t> </w:t></w:r>
          <w:r><w:rPr><w:strike/></w:rPr><w:t>Struck</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    doc = DOCXReader().read(str(path))

    assert to_markdown(doc) == "**Bold** *Italic* <u>Underlined</u> ~~Struck~~"


def test_docx_markdown_preserves_vertical_alignment_runs(tmp_path):
    path = tmp_path / "vertical-runs.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>CO</w:t></w:r>
          <w:r><w:rPr><w:vertAlign w:val="subscript"/></w:rPr><w:t>2</w:t></w:r>
          <w:r><w:t> target</w:t></w:r>
          <w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>1</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    doc = DOCXReader().read(str(path))

    assert to_markdown(doc) == "CO<sub>2</sub> target<sup>1</sup>"


def test_docx_markdown_preserves_character_style_run_formatting(tmp_path):
    path = tmp_path / "character-style-runs.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:rPr><w:rStyle w:val="StrongEmphasis"/></w:rPr><w:t>Styled bold</w:t></w:r>
              <w:r><w:t> </w:t></w:r>
              <w:r><w:rPr><w:rStyle w:val="UnderlinedStyle"/></w:rPr><w:t>Styled underline</w:t></w:r>
              <w:r><w:t> </w:t></w:r>
              <w:r><w:rPr><w:rStyle w:val="StrikeStyle"/></w:rPr><w:t>Styled strike</w:t></w:r>
              <w:r><w:t> </w:t></w:r>
              <w:r><w:rPr><w:rStyle w:val="SubtleRef"/></w:rPr><w:t>2</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        styles_xml="""
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
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
    )

    doc = DOCXReader().read(str(path))

    assert to_markdown(doc) == (
        "***Styled bold*** <u>Styled underline</u> ~~Styled strike~~ <sub>2</sub>"
    )


def test_reads_docx_inserted_text_and_ignores_deleted_text(tmp_path):
    path = tmp_path / "tracked-changes.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>Base </w:t></w:r>
          <w:ins w:id="1" w:author="Reviewer">
            <w:r><w:t>Inserted</w:t></w:r>
          </w:ins>
          <w:del w:id="2" w:author="Reviewer">
            <w:r><w:delText>Deleted</w:delText></w:r>
          </w:del>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Base Inserted"


def test_reads_docx_text_inside_sdt_and_smart_tag_wrappers(tmp_path):
    path = tmp_path / "wrapped-text.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
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
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Controlled Smart"


def test_reads_docx_field_results_without_instructions(tmp_path):
    path = tmp_path / "fields.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:fldSimple w:instr="DATE">
            <w:r><w:t>2026-06-20</w:t></w:r>
          </w:fldSimple>
        </w:p>
        <w:p>
          <w:r><w:fldChar w:fldCharType="begin"/></w:r>
          <w:r><w:instrText> PAGE </w:instrText></w:r>
          <w:r><w:fldChar w:fldCharType="separate"/></w:r>
          <w:r><w:t>5</w:t></w:r>
          <w:r><w:fldChar w:fldCharType="end"/></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert [element.text for element in elements] == ["2026-06-20", "5"]


def test_reads_docx_legacy_form_checkboxes(tmp_path):
    path = tmp_path / "checkboxes.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>Unchecked </w:t></w:r>
          <w:r>
            <w:fldChar w:fldCharType="begin">
              <w:ffData>
                <w:name w:val="Check1"/>
                <w:checkBox><w:default w:val="0"/></w:checkBox>
              </w:ffData>
            </w:fldChar>
          </w:r>
        </w:p>
        <w:p>
          <w:r><w:t>Checked </w:t></w:r>
          <w:r>
            <w:fldChar w:fldCharType="begin">
              <w:ffData>
                <w:name w:val="Check2"/>
                <w:checkBox><w:default w:val="1"/></w:checkBox>
              </w:ffData>
            </w:fldChar>
          </w:r>
        </w:p>
        <w:p>
          <w:r><w:t>Explicit </w:t></w:r>
          <w:r>
            <w:fldChar w:fldCharType="begin">
              <w:ffData>
                <w:name w:val="Check3"/>
                <w:checkBox><w:checked/></w:checkBox>
              </w:ffData>
            </w:fldChar>
          </w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert [element.text for element in elements] == [
        "Unchecked [ ]",
        "Checked [x]",
        "Explicit [x]",
    ]


def test_reads_docx_text_inside_textbox_content(tmp_path):
    path = tmp_path / "textbox.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>Before </w:t></w:r>
          <w:r>
            <w:drawing>
              <w:txbxContent>
                <w:p><w:r><w:t>Boxed insight</w:t></w:r></w:p>
              </w:txbxContent>
            </w:drawing>
          </w:r>
          <w:r><w:t> After</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Before Boxed insight After"


def test_reads_docx_body_level_content_controls_in_order(tmp_path):
    path = tmp_path / "body-sdt.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Objective</w:t></w:r></w:p>
        <w:sdt>
          <w:sdtPr/>
          <w:sdtContent>
            <w:p><w:r><w:t>Getting the perfect job might be challenging.</w:t></w:r></w:p>
            <w:sdt>
              <w:sdtPr/>
              <w:sdtContent>
                <w:p><w:r><w:t>Nested repeating-section item</w:t></w:r></w:p>
              </w:sdtContent>
            </w:sdt>
          </w:sdtContent>
        </w:sdt>
        <w:p><w:r><w:t>References</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert [element.text for element in elements] == [
        "Objective",
        "Getting the perfect job might be challenging.",
        "Nested repeating-section item",
        "References",
    ]


def test_reads_docx_alternate_content_textbox_once(tmp_path):
    path = tmp_path / "alternate-textbox.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
      <w:body>
        <w:p>
          <w:r>
            <mc:AlternateContent>
              <mc:Choice Requires="wps">
                <w:drawing>
                  <w:txbxContent>
                    <w:p><w:r><w:t>Modern box</w:t></w:r></w:p>
                  </w:txbxContent>
                </w:drawing>
              </mc:Choice>
              <mc:Fallback>
                <w:pict>
                  <w:txbxContent>
                    <w:p><w:r><w:t>Legacy duplicate box</w:t></w:r></w:p>
                  </w:txbxContent>
                </w:pict>
              </mc:Fallback>
            </mc:AlternateContent>
          </w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Modern box"


def test_separates_docx_anchored_textboxes(tmp_path):
    path = tmp_path / "anchored-textboxes.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
      <w:body>
        <w:p>
          <w:r>
            <w:drawing>
              <wp:anchor>
                <w:txbxContent>
                  <w:p><w:r><w:t>First box</w:t></w:r></w:p>
                </w:txbxContent>
              </wp:anchor>
            </w:drawing>
          </w:r>
          <w:r>
            <w:drawing>
              <wp:anchor>
                <w:txbxContent>
                  <w:p><w:r><w:t>Second box</w:t></w:r></w:p>
                </w:txbxContent>
              </wp:anchor>
            </w:drawing>
          </w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "First box\nSecond box\n"


def test_reads_docx_drawing_alt_text_from_docpr(tmp_path):
    path = tmp_path / "image-alt.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
      <w:body>
        <w:p>
          <w:r><w:t>Chart: </w:t></w:r>
          <w:r>
            <w:drawing>
              <wp:inline>
                <wp:docPr id="1" name="Chart image" title="Revenue Chart" descr="ARR increased 42 percent"/>
              </wp:inline>
            </w:drawing>
          </w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Chart: Revenue Chart ARR increased 42 percent"


def test_reads_docx_embedded_image_relationship_as_markdown_reference(tmp_path):
    path = tmp_path / "image-reference.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p>
              <w:r>
                <w:drawing>
                  <wp:inline>
                    <wp:docPr id="1" name="Picture 1"/>
                    <a:graphic>
                      <a:graphicData>
                        <a:pic>
                          <a:blipFill>
                            <a:blip r:embed="rIdImage"/>
                          </a:blipFill>
                        </a:pic>
                      </a:graphicData>
                    </a:graphic>
                  </wp:inline>
                </w:drawing>
              </w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
        </Relationships>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert to_markdown(doc) == "![Picture 1](word/media/image1.png)"


def test_records_docx_embedded_image_relationship_as_asset(tmp_path):
    path = tmp_path / "image-asset.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p>
              <w:r>
                <w:drawing>
                  <wp:inline>
                    <wp:docPr id="1" name="Picture 1" title="Revenue Chart" descr="ARR increased"/>
                    <a:graphic><a:graphicData><a:pic><a:blipFill>
                      <a:blip r:embed="rIdImage"/>
                    </a:blipFill></a:pic></a:graphicData></a:graphic>
                  </wp:inline>
                </w:drawing>
              </w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
        </Relationships>
        """,
        extra_parts={"word/media/image1.png": b"PNG"},
    )

    doc = DOCXReader().read(str(path))

    assert len(doc.assets) == 1
    asset = doc.assets[0]
    assert asset.id == "rIdImage"
    assert asset.source_path == "word/media/image1.png"
    assert asset.filename == "image1.png"
    assert asset.content_type == "image/png"
    assert asset.metadata["label"] == "Revenue Chart ARR increased Picture 1"
    assert asset.metadata["source_format"] == "docx"


def test_records_docx_embedded_object_relationships_as_assets(tmp_path):
    path = tmp_path / "embedded-assets.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Document with attachments</w:t></w:r></w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdOle" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/oleObject1.bin"/>
          <Relationship Id="rIdPackage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/package" Target="embeddings/workbook.xlsx"/>
        </Relationships>
        """,
        extra_parts={
            "word/embeddings/oleObject1.bin": b"OLE",
            "word/embeddings/workbook.xlsx": b"PK",
        },
    )

    doc = DOCXReader().read(str(path))

    assert [(asset.id, asset.source_path) for asset in doc.assets] == [
        ("rIdOle", "word/embeddings/oleObject1.bin"),
        ("rIdPackage", "word/embeddings/workbook.xlsx"),
    ]
    assert doc.assets[0].content_type == "application/vnd.ms-office.oleObject"
    assert doc.assets[1].content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert doc.assets[0].metadata["kind"] == "embedded"
    assert doc.assets[1].metadata["source_format"] == "docx"


def test_reads_docx_vml_object_preview_image_as_markdown_reference(tmp_path):
    path = tmp_path / "vml-object-preview.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:o="urn:schemas-microsoft-com:office:office"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:v="urn:schemas-microsoft-com:vml">
          <w:body>
            <w:p><w:r><w:t>Before object</w:t></w:r></w:p>
            <w:p>
              <w:r>
                <w:object>
                  <v:shape id="_x0000_i1025" type="#_x0000_t75" o:ole="">
                    <v:imagedata r:id="rIdPreview" o:title=""/>
                  </v:shape>
                  <o:OLEObject Type="Embed" ProgID="Excel.Sheet.8" ShapeID="_x0000_i1025" r:id="rIdOle"/>
                </w:object>
              </w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdPreview" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.emf"/>
          <Relationship Id="rIdOle" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/worksheet.xls"/>
        </Relationships>
        """,
        extra_parts={
            "word/media/image1.emf": b"EMF",
            "word/embeddings/worksheet.xls": b"OLE",
        },
    )

    doc = DOCXReader().read(str(path))
    markdown = to_markdown(doc)

    assert "![image](word/media/image1.emf)" in markdown
    assert [(asset.id, asset.source_path) for asset in doc.assets] == [
        ("rIdOle", "word/embeddings/worksheet.xls"),
        ("rIdPreview", "word/media/image1.emf"),
    ]
    assert doc.assets[1].content_type == "image/x-emf"


def test_reads_docx_tabs_line_breaks_and_hyperlink_text(tmp_path):
    path = tmp_path / "inline-controls.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>Name</w:t></w:r>
          <w:r><w:tab/></w:r>
          <w:hyperlink w:anchor="target">
            <w:r><w:t>Link Text</w:t></w:r>
          </w:hyperlink>
          <w:r><w:br/></w:r>
          <w:r><w:t>Next line</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Name\tLink Text <#target>\nNext line"


def test_reads_docx_external_hyperlink_target(tmp_path):
    path = tmp_path / "external-link.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p>
              <w:r><w:t>See </w:t></w:r>
              <w:hyperlink r:id="rIdLink">
                <w:r><w:t>Report</w:t></w:r>
              </w:hyperlink>
            </w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/report" TargetMode="External"/>
        </Relationships>
        """,
    )

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "See Report <https://example.com/report>"


def test_reads_docx_visible_bookmark_anchor_names(tmp_path):
    path = tmp_path / "bookmark-anchor.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:bookmarkStart w:id="1" w:name="Summary"/>
          <w:r><w:t>Summary Target</w:t></w:r>
          <w:bookmarkEnd w:id="1"/>
        </w:p>
        <w:p>
          <w:bookmarkStart w:id="2" w:name="_GoBack"/>
          <w:r><w:t>Hidden Bookmark Target</w:t></w:r>
          <w:bookmarkEnd w:id="2"/>
        </w:p>
      </w:body>
    </w:document>
    """)

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert elements[0].text == "[bookmark: Summary] Summary Target"
    assert elements[1].text == "Hidden Bookmark Target"


def test_detects_heading_from_paragraph_style(tmp_path):
    path = tmp_path / "heading.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
          <w:r><w:t>Title</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Title"
    assert para.heading_level == 1


def test_detects_title_paragraph_style_as_heading(tmp_path):
    path = tmp_path / "title-style.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:pPr><w:pStyle w:val="Title"/></w:pPr>
          <w:r><w:t>Document Title</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Document Title"
    assert para.heading_level == 1


def test_detects_heading_from_based_on_paragraph_style(tmp_path):
    path = tmp_path / "derived-heading.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:pStyle w:val="CustomTitle"/></w:pPr>
              <w:r><w:t>Inherited Title</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        styles_xml="""
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="paragraph" w:styleId="Heading1">
            <w:name w:val="heading 1"/>
          </w:style>
          <w:style w:type="paragraph" w:styleId="CustomTitle">
            <w:name w:val="Custom Title"/>
            <w:basedOn w:val="Heading1"/>
          </w:style>
        </w:styles>
        """,
    )

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Inherited Title"
    assert para.heading_level == 1


def test_reads_docx_table_as_document_table(tmp_path):
    path = tmp_path / "table.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:tr>
            <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[0][0].text == "Name"
    assert table.rows[0][0].provenance.source_format == "docx"
    assert table.rows[0][0].provenance.cell == "R1C1"
    assert table.rows[0][0].provenance.path == "word/document.xml"
    assert table.rows[1][1].text == "1"


def test_reads_docx_table_rows_and_cells_inside_content_controls(tmp_path):
    path = tmp_path / "table-sdt.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Note</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Details</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:sdt>
            <w:sdtContent>
              <w:tr>
                <w:sdt>
                  <w:sdtContent>
                    <w:tc><w:p><w:r><w:t>Choose an item.</w:t></w:r></w:p></w:tc>
                  </w:sdtContent>
                </w:sdt>
                <w:tc><w:p><w:r><w:t>Here is just a sample</w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:sdtContent>
          </w:sdt>
        </w:tbl>
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 2
    assert table.rows[1][0].text == "Choose an item."
    assert table.rows[1][1].text == "Here is just a sample"


def test_reads_docx_gridspan_as_col_span(tmp_path):
    path = tmp_path / "merged-table.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:tbl>
          <w:tr>
            <w:tc>
              <w:tcPr><w:gridSpan w:val="2"/></w:tcPr>
              <w:p><w:r><w:t>Merged Header</w:t></w:r></w:p>
            </w:tc>
          </w:tr>
          <w:tr>
            <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Merged Header"
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away
    assert table.rows[1][0].text == "A"
    assert table.rows[1][1].text == "B"


def test_reads_docx_vmerge_as_row_span(tmp_path):
    path = tmp_path / "vertical-merged-table.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
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
        </w:tbl>
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Region"
    assert table.rows[0][0].row_span == 2
    assert table.rows[1][0].is_merged_away
    assert table.rows[0][1].text == "Q1"
    assert table.rows[1][1].text == "Q2"


def test_reads_docx_grid_before_as_leading_empty_cells(tmp_path):
    path = tmp_path / "grid-before-table.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Region</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Q1</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:tr>
            <w:trPr><w:gridBefore w:val="1"/></w:trPr>
            <w:tc><w:p><w:r><w:t>Q2</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[1][0].text == ""
    assert table.rows[1][1].text == "Q2"


def test_reads_docx_nested_table_text_inside_parent_cell(tmp_path):
    path = tmp_path / "nested-table.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
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
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.rows[0][0].text == "Parent cell\nNested value"


def test_reads_docx_numbered_list_from_numbering_xml(tmp_path):
    path = tmp_path / "numbered.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>First item</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Second item</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        numbering_xml="""
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="0">
              <w:start w:val="1"/>
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="%1."/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert [elem.text for elem in doc.sections[0].elements] == [
        "1. First item",
        "2. Second item",
    ]


def test_reads_docx_letter_and_roman_numbering_formats(tmp_path):
    path = tmp_path / "formatted-numbering.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Alpha first</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Alpha second</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Roman tenth</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        numbering_xml="""
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="0">
              <w:start w:val="1"/>
              <w:numFmt w:val="lowerLetter"/>
              <w:lvlText w:val="%1)"/>
            </w:lvl>
            <w:lvl w:ilvl="1">
              <w:start w:val="10"/>
              <w:numFmt w:val="upperRoman"/>
              <w:lvlText w:val="%2."/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert [elem.text for elem in doc.sections[0].elements] == [
        "a) Alpha first",
        "b) Alpha second",
        "X. Roman tenth",
    ]


def test_reads_docx_multilevel_numbering_with_parent_markers(tmp_path):
    path = tmp_path / "multilevel-numbering.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Section one</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Child alpha</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Child beta</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Section two</w:t></w:r>
            </w:p>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Child reset</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        numbering_xml="""
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
              <w:lvlText w:val="%1.%2)"/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert [elem.text for elem in doc.sections[0].elements] == [
        "1. Section one",
        "1.a) Child alpha",
        "1.b) Child beta",
        "2. Section two",
        "2.a) Child reset",
    ]


def test_reads_docx_footnotes_and_endnotes(tmp_path):
    path = tmp_path / "notes.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Body with note</w:t></w:r>
              <w:r><w:footnoteReference w:id="2"/></w:r>
              <w:r><w:t> and endnote</w:t></w:r>
              <w:r><w:endnoteReference w:id="3"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        footnotes_xml="""
        <w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:footnote w:id="-1" w:type="separator"/>
          <w:footnote w:id="2"><w:p><w:r><w:t>Footnote detail</w:t></w:r></w:p></w:footnote>
        </w:footnotes>
        """,
        endnotes_xml="""
        <w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:endnote w:id="3"><w:p><w:r><w:t>Endnote detail</w:t></w:r></w:p></w:endnote>
        </w:endnotes>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Body with note[1] and endnote[2]"
    assert doc.sections[0].elements[1].type == "footnote"
    assert doc.sections[0].elements[1].text == "Footnote detail"
    assert doc.sections[0].elements[2].type == "endnote"
    assert doc.sections[0].elements[2].text == "Endnote detail"


def test_reads_docx_tables_inside_endnotes(tmp_path):
    path = tmp_path / "endnote-table.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Body</w:t></w:r>
              <w:r><w:endnoteReference w:id="3"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        endnotes_xml="""
        <w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:endnote w:id="3">
            <w:p><w:r><w:t>Endnote intro</w:t></w:r></w:p>
            <w:tbl>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Endnote table text</w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:tbl>
          </w:endnote>
        </w:endnotes>
        """,
    )

    doc = DOCXReader().read(str(path))
    endnote = doc.sections[0].elements[1]
    markdown = to_markdown(doc)

    assert endnote.type == "endnote"
    assert endnote.paragraphs[0].text == "Endnote intro"
    assert endnote.paragraphs[1].rows[0][0].text == "Endnote table text"
    assert "Endnote table text" in markdown
    assert "| Endnote table text |" in markdown
    endnote_json = to_dict(doc)["sections"][0]["elements"][1]
    assert endnote_json["elements"][1]["type"] == "table"
    assert endnote_json["elements"][1]["rows"][0][0]["text"] == "Endnote table text"


def test_reads_docx_comments_and_comment_reference_marker(tmp_path):
    path = tmp_path / "comments.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Needs review</w:t></w:r>
              <w:r><w:commentReference w:id="4"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        comments_xml="""
        <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:comment w:id="4" w:author="Reviewer">
            <w:p><w:r><w:t>Clarify this section</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Needs review[comment 1]"
    assert doc.sections[0].elements[1].type == "comment"
    assert doc.sections[0].elements[1].text == "Clarify this section"


def test_reads_docx_comment_range_as_inline_annotated_text(tmp_path):
    path = tmp_path / "comment-range.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Approve </w:t></w:r>
              <w:commentRangeStart w:id="4"/>
              <w:r><w:t>discount policy</w:t></w:r>
              <w:commentRangeEnd w:id="4"/>
              <w:r><w:commentReference w:id="4"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        comments_xml="""
        <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:comment w:id="4" w:author="Reviewer">
            <w:p><w:r><w:t>Confirm with legal</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Approve discount policy [comment 1: Confirm with legal]"
    assert doc.sections[0].elements[1].type == "comment"
    assert doc.sections[0].elements[1].text == "Confirm with legal"


def test_reads_docx_comment_replies_from_comments_extended(tmp_path):
    path = tmp_path / "comment-replies.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Needs approval</w:t></w:r>
              <w:r><w:commentReference w:id="4"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        comments_xml="""
        <w:comments
          xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
          <w:comment w:id="4" w:author="Reviewer">
            <w:p w15:paraId="AAAA1111"><w:r><w:t>Clarify this section</w:t></w:r></w:p>
          </w:comment>
          <w:comment w:id="5" w:author="Approver">
            <w:p w15:paraId="BBBB2222"><w:r><w:t>Approved after legal review</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """,
        extra_parts={
            "word/commentsExtended.xml": """
            <w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
              <w15:commentEx w15:paraId="AAAA1111"/>
              <w15:commentEx w15:paraId="BBBB2222" w15:paraIdParent="AAAA1111"/>
            </w15:commentsEx>
            """,
        },
    )

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Needs approval[comment 1]"
    assert doc.sections[0].elements[1].type == "comment"
    assert doc.sections[0].elements[1].text == (
        "Clarify this section\nReply from Approver: Approved after legal review"
    )


def test_reads_docx_headers_and_footers_from_section_relationships(tmp_path):
    path = tmp_path / "header-footer.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p><w:r><w:t>Body text</w:t></w:r></w:p>
            <w:sectPr>
              <w:headerReference w:type="default" r:id="rIdHeader"/>
              <w:footerReference w:type="default" r:id="rIdFooter"/>
            </w:sectPr>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
          <Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "word/header1.xml": """
            <w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:p><w:r><w:t>Header text</w:t></w:r></w:p>
            </w:hdr>
            """,
            "word/footer1.xml": """
            <w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:p><w:r><w:t>Footer text</w:t></w:r></w:p>
            </w:ftr>
            """,
        },
    )

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert elements[0].type == "header"
    assert elements[0].text == "Header text"
    assert elements[1].text == "Body text"
    assert elements[2].type == "footer"
    assert elements[2].text == "Footer text"


def test_reads_docx_header_embedded_image_relationship(tmp_path):
    path = tmp_path / "header-image.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:sectPr>
              <w:headerReference w:type="default" r:id="rIdHeader"/>
            </w:sectPr>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
        </Relationships>
        """,
        extra_parts={
            "word/header1.xml": """
            <w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
              xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <w:p>
                <w:r>
                  <w:drawing>
                    <wp:inline>
                      <wp:docPr id="1" name="Header Picture"/>
                      <a:graphic>
                        <a:graphicData>
                          <a:pic>
                            <a:blipFill>
                              <a:blip r:embed="rIdHeaderImage"/>
                            </a:blipFill>
                          </a:pic>
                        </a:graphicData>
                      </a:graphic>
                    </wp:inline>
                  </w:drawing>
                </w:r>
              </w:p>
            </w:hdr>
            """,
            "word/_rels/header1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdHeaderImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
            </Relationships>
            """,
            "word/media/image1.png": b"PNG",
        },
    )

    doc = DOCXReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.sections[0].elements[0].type == "header"
    assert doc.sections[0].elements[0].text == "![Header Picture](word/media/image1.png)"
    assert "<!-- header: ![Header Picture](word/media/image1.png) -->" in markdown
    assert [(asset.id, asset.source_path) for asset in doc.assets] == [
        ("rIdHeaderImage", "word/media/image1.png")
    ]


def test_reads_docx_package_absolute_footer_relationship(tmp_path):
    path = tmp_path / "absolute-footer.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p><w:r><w:t>Body text</w:t></w:r></w:p>
            <w:sectPr>
              <w:footerReference w:type="default" r:id="rIdFooter"/>
            </w:sectPr>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="/word/footer.xml"/>
        </Relationships>
        """,
        extra_parts={
            "word/footer.xml": """
            <w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:p><w:r><w:t>Absolute footer</w:t></w:r></w:p>
            </w:ftr>
            """,
        },
    )

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert elements[0].text == "Body text"
    assert elements[1].type == "footer"
    assert elements[1].text == "Absolute footer"


def test_reads_docx_footer_paragraphs_inside_content_controls(tmp_path):
    path = tmp_path / "nested-footer.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:sectPr>
              <w:footerReference w:type="default" r:id="rIdFooter"/>
            </w:sectPr>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="/word/footer.xml"/>
        </Relationships>
        """,
        extra_parts={
            "word/footer.xml": """
            <w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:sdt>
                <w:sdtContent>
                  <w:sdt>
                    <w:sdtContent>
                      <w:p>
                        <w:r><w:t>Page </w:t></w:r>
                        <w:r><w:t>2</w:t></w:r>
                        <w:r><w:t> of </w:t></w:r>
                        <w:r><w:t>2</w:t></w:r>
                      </w:p>
                    </w:sdtContent>
                  </w:sdt>
                </w:sdtContent>
              </w:sdt>
            </w:ftr>
            """,
        },
    )

    elements = DOCXReader().read(str(path)).sections[0].elements

    assert elements[0].type == "footer"
    assert elements[0].text == "Page 2 of 2"


def test_dochan_routes_docx_to_native_reader(tmp_path):
    path = tmp_path / "integrated.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
          <w:r><w:t>Office Title</w:t></w:r>
        </w:p>
        <w:p><w:r><w:t>Body text</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "docx"
    assert doc.to_markdown() == "# Office Title\n\nBody text"


def test_batch_convert_includes_docx_by_default(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    path = input_dir / "doc.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Batch DOCX</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    summary = batch_convert(str(input_dir), str(output_dir), output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "doc.md").read_text(encoding="utf-8") == "Batch DOCX"


def test_cli_info_reports_docx_format(tmp_path, capsys):
    class Args:
        pass

    path = tmp_path / "info.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Info DOCX</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "docx"' in out
