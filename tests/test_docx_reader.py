import zipfile

import dochan.ooxml.docx as docx_module
from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import _cmd_info
from dochan.ooxml.docx import DOCXReader
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.quality.checker import check_quality


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


def test_reads_docx_tracked_move_destination_once(tmp_path):
    path = tmp_path / "tracked-move.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:moveFrom w:id="1" w:author="Author">
            <w:r><w:t>Moved text</w:t></w:r>
          </w:moveFrom>
          <w:moveTo w:id="1" w:author="Author">
            <w:r><w:t>Moved text</w:t></w:r>
          </w:moveTo>
          <w:del w:id="3" w:author="Author">
            <w:r><w:delText>Deleted text</w:delText></w:r>
          </w:del>
        </w:p>
      </w:body>
    </w:document>
    """)

    markdown = to_markdown(DOCXReader().read(str(path)))

    assert markdown.count("Moved text") == 1
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


def _wrap_in_nested_textboxes(content, depth):
    for _ in range(depth):
        content = (
            "<w:r><w:drawing><w:txbxContent><w:p>"
            f"{content}"
            "</w:p></w:txbxContent></w:drawing></w:r>"
        )
    return content


def _nested_textbox_run(depth, leaf_text="Nested leaf"):
    return _wrap_in_nested_textboxes(
        f"<w:r><w:t>{leaf_text}</w:t></w:r>",
        depth,
    )


def test_reads_deeply_nested_docx_textbox_leaf_once(tmp_path):
    path = tmp_path / "nested-textbox-once.docx"
    nested_run = _nested_textbox_run(10)
    _write_docx(path, f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p>{nested_run}</w:p></w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Nested leaf"


def test_nested_docx_textboxes_preserve_text_order_and_host_run_style(tmp_path):
    path = tmp_path / "nested-textbox-style.docx"
    nested_run = _nested_textbox_run(2, "Inner")
    _write_docx(path, f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>Before </w:t></w:r>
          <w:r>
            <w:rPr><w:b/></w:rPr>
            <w:t>Box: </w:t>
            <w:drawing>
              <w:txbxContent><w:p>{nested_run}</w:p></w:txbxContent>
            </w:drawing>
            <w:t> tail</w:t>
          </w:r>
          <w:r><w:t> After</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Before Box: Inner tail After"
    assert para.runs[1].text == "Box: Inner tail"
    assert para.runs[1].bold is True


def test_docx_textbox_structure_depth_boundary_is_included(tmp_path):
    path = tmp_path / "textbox-depth-boundary.docx"
    nested_run = _nested_textbox_run(64, "Boundary leaf")
    _write_docx(path, f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p>{nested_run}</w:p></w:body>
    </w:document>
    """)

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Boundary leaf"
    assert not [error for error in doc.errors if "structure depth limit" in error]


def test_docx_textbox_over_depth_branch_is_omitted_and_sibling_survives(tmp_path):
    path = tmp_path / "textbox-over-depth.docx"
    deepest_content = (
        f'{_nested_textbox_run(1, "Too deep")}'
        "<w:r><w:t>Safe sibling</w:t></w:r>"
    )
    nested_run = _wrap_in_nested_textboxes(deepest_content, 64)
    _write_docx(path, f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p>{nested_run}</w:p></w:body>
    </w:document>
    """)

    doc = DOCXReader().read(str(path))
    para = doc.sections[0].elements[0]
    depth_errors = [error for error in doc.errors if "structure depth limit" in error]

    assert para.text == "Safe sibling"
    assert "Too deep" not in para.text
    assert depth_errors == ["ERR: DOCX structure depth limit exceeded (64)"]


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
    assert asset.metadata["missing"] is False


def test_records_missing_docx_image_part_once_for_quality(tmp_path):
    path = tmp_path / "missing-image-part.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body><w:p>
            <w:r><w:drawing><a:blip r:embed="rIdMissing"/></w:drawing></w:r>
            <w:r><w:drawing><a:blip r:embed="rIdMissing"/></w:drawing></w:r>
          </w:p></w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdMissing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/missing.png"/>
        </Relationships>
        """,
    )

    doc = DOCXReader().read(str(path))
    report = check_quality(doc)

    assert len(doc.assets) == 1
    assert doc.assets[0].source_path == "word/media/missing.png"
    assert doc.assets[0].metadata["missing"] is True
    assert doc.errors == [
        "WARN: DOCX image part not found: word/media/missing.png"
    ]
    assert report.total_images == 1
    assert report.missing_images == 1
    assert report.parse_errors == 0


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


def test_skips_unsafe_docx_document_image_relationship_target(tmp_path):
    path = tmp_path / "unsafe-image-target.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Safe body</w:t></w:r>
              <w:r><w:drawing><a:blip r:embed="rIdImage"/></w:drawing></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../../outside.png"/>
        </Relationships>
        """,
    )

    doc = DOCXReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.sections[0].elements[0].text == "Safe body"
    assert "outside.png" not in markdown
    assert doc.errors == [
        "ERR: DOCX unsafe internal relationship target skipped: "
        "word/_rels/document.xml.rels#rIdImage"
    ]


def test_skips_unsafe_docx_header_and_part_relationship_targets(tmp_path):
    path = tmp_path / "unsafe-header-targets.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p><w:r><w:t>Safe body</w:t></w:r></w:p>
            <w:sectPr>
              <w:headerReference w:type="default" r:id="rIdHeader"/>
              <w:footerReference w:type="default" r:id="rIdUnsafeFooter"/>
            </w:sectPr>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
          <Relationship Id="rIdUnsafeFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="../../outside.xml"/>
        </Relationships>
        """,
        extra_parts={
            "word/header1.xml": """
            <w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <w:p>
                <w:r><w:t>Safe header</w:t></w:r>
                <w:r><w:drawing><a:blip r:embed="rIdHeaderImage"/></w:drawing></w:r>
              </w:p>
            </w:hdr>
            """,
            "word/_rels/header1.xml.rels": """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rIdHeaderImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../../outside.png"/>
            </Relationships>
            """,
        },
    )

    doc = DOCXReader().read(str(path))
    markdown = to_markdown(doc)

    assert "Safe body" in markdown
    assert "Safe header" in markdown
    assert "outside" not in markdown
    assert doc.errors == [
        "ERR: DOCX unsafe internal relationship target skipped: "
        "word/_rels/document.xml.rels#rIdUnsafeFooter",
        "ERR: DOCX unsafe internal relationship target skipped: "
        "word/_rels/header1.xml.rels#rIdHeaderImage",
    ]


def test_skips_unsafe_docx_alt_chunk_and_embedded_targets(tmp_path):
    path = tmp_path / "unsafe-other-targets.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:altChunk r:id="rIdChunk"/>
            <w:p><w:r><w:t>Safe body</w:t></w:r></w:p>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdChunk" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk" Target="../../outside.html"/>
          <Relationship Id="rIdEmbedded" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="../../outside.bin"/>
        </Relationships>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].text == "Safe body"
    assert doc.assets == []
    assert doc.errors == [
        "ERR: DOCX unsafe internal relationship target skipped: "
        "word/_rels/document.xml.rels#rIdChunk",
        "ERR: DOCX unsafe internal relationship target skipped: "
        "word/_rels/document.xml.rels#rIdEmbedded",
    ]


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


def test_docx_table_wrapper_depth_is_independent_from_nested_table_depth(tmp_path):
    path = tmp_path / "table-wrapper-depth-independence.docx"
    wrapped_paragraph = _deep_sdt(
        "<w:p><w:r><w:t>Within structure limit</w:t></w:r></w:p>",
        depth=64,
    )
    _write_docx(
        path,
        f"""
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:tbl><w:tr><w:tc>{wrapped_paragraph}</w:tc></w:tr></w:tbl>
          </w:body>
        </w:document>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert doc.sections[0].elements[0].rows[0][0].text == "Within structure limit"
    assert doc.errors == []


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


def test_rejects_docx_numbering_value_above_output_limit(tmp_path, monkeypatch):
    path = tmp_path / "oversized-numbering.docx"
    monkeypatch.setattr(docx_module, "MAX_NUMBERING_VALUE", 9, raising=False)
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Bounded item</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        numbering_xml="""
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="0">
              <w:start w:val="10"/>
              <w:numFmt w:val="upperRoman"/>
              <w:lvlText w:val="%1."/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert any("DOCX numbering value limit exceeded" in error for error in doc.errors)
    assert len(doc.sections[0].elements[0].text) < 100


def test_rejects_docx_numbering_level_above_supported_limit(tmp_path, monkeypatch):
    path = tmp_path / "oversized-numbering-level.docx"
    monkeypatch.setattr(docx_module, "MAX_NUMBERING_LEVEL", 1, raising=False)
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Bounded item</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        numbering_xml="""
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="2">
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="%3."/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert any("DOCX numbering level limit exceeded" in error for error in doc.errors)
    assert doc.sections[0].elements[0].text == "Bounded item"


def test_rejects_docx_numbering_template_above_output_limit(tmp_path, monkeypatch):
    path = tmp_path / "oversized-numbering-template.docx"
    monkeypatch.setattr(docx_module, "MAX_NUMBERING_TEMPLATE_CHARS", 8, raising=False)
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
              <w:r><w:t>Bounded item</w:t></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        numbering_xml="""
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="0">
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """,
    )

    doc = DOCXReader().read(str(path))

    assert any("DOCX numbering marker template limit exceeded" in error for error in doc.errors)
    assert doc.sections[0].elements[0].text == "1. Bounded item"


def test_docx_false_run_properties_disable_formatting(tmp_path):
    path = tmp_path / "false-run-properties.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r>
              <w:rPr>
                <w:rStyle w:val="EnabledFormatting"/>
                <w:b w:val="0"/>
                <w:i w:val="false"/>
                <w:u w:val="none"/>
                <w:strike w:val="off"/>
              </w:rPr>
              <w:t>Plain text</w:t>
            </w:r></w:p>
          </w:body>
        </w:document>
        """,
        styles_xml="""
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="character" w:styleId="EnabledFormatting">
            <w:rPr><w:b/><w:i/><w:u w:val="single"/><w:strike/></w:rPr>
          </w:style>
        </w:styles>
        """,
    )

    doc = DOCXReader().read(str(path))
    run = doc.sections[0].elements[0].runs[0]

    assert not run.bold
    assert not run.italic
    assert not run.underline
    assert not run.strikeout
    assert to_markdown(doc) == "Plain text"


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

    paragraph, footnote, endnote = doc.sections[0].elements
    assert paragraph.text == "Body with note[1] and endnote[2]"
    assert paragraph.runs[1].note_reference_type == "footnote"
    assert paragraph.runs[1].note_reference_number == 1
    assert paragraph.runs[3].note_reference_type == "endnote"
    assert paragraph.runs[3].note_reference_number == 2
    assert footnote.type == "footnote"
    assert footnote.number == 1
    assert footnote.text == "Footnote detail"
    assert endnote.type == "endnote"
    assert endnote.number == 2
    assert endnote.text == "Endnote detail"
    assert "Body with note[^1] and endnote[^2]" in to_markdown(doc)


def test_docx_note_reference_splits_mixed_run_and_preserves_literal_text_and_style(tmp_path):
    path = tmp_path / "mixed-note-reference-run.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r>
                <w:rPr><w:b/><w:i/></w:rPr>
                <w:t>literal [1] / </w:t>
                <w:footnoteReference w:id="2"/>
                <w:t> tail</w:t>
              </w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        footnotes_xml="""
        <w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:footnote w:id="2"><w:p><w:r><w:t>Detail</w:t></w:r></w:p></w:footnote>
        </w:footnotes>
        """,
    )

    doc = DOCXReader().read(str(path))
    runs = doc.sections[0].elements[0].runs
    payload_runs = to_dict(doc)["sections"][0]["elements"][0]["runs"]

    assert [run.text for run in runs] == ["literal [1] / ", "[1]", " tail"]
    assert all(run.bold and run.italic for run in runs)
    assert runs[0].note_reference_type == ""
    assert runs[0].note_reference_number is None
    assert runs[1].note_reference_type == "footnote"
    assert runs[1].note_reference_number == 1
    assert runs[2].note_reference_type == ""
    assert runs[2].note_reference_number is None
    assert "note_reference_type" not in payload_runs[0]
    assert payload_runs[1]["note_reference_type"] == "footnote"
    assert payload_runs[1]["note_reference_number"] == 1
    assert "***literal [1] / ***[^1]*** tail***" in to_markdown(doc)


def test_docx_empty_first_note_does_not_renumber_second_definition(tmp_path):
    path = tmp_path / "empty-first-note.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>First</w:t><w:footnoteReference w:id="2"/></w:r>
              <w:r><w:t> Second</w:t><w:footnoteReference w:id="3"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        footnotes_xml="""
        <w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:footnote w:id="2"><w:p/></w:footnote>
          <w:footnote w:id="3"><w:p><w:r><w:t>Second detail</w:t></w:r></w:p></w:footnote>
        </w:footnotes>
        """,
    )

    doc = DOCXReader().read(str(path))
    markdown = to_markdown(doc)
    second_note = doc.sections[0].elements[1]

    assert second_note.number == 2
    assert "First[^1] Second[^2]" in markdown
    assert "[^2]: Second detail" in markdown
    assert "[^1]:" not in markdown


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


def test_reads_multiple_docx_comments_with_unique_numbers_authors_and_notes(tmp_path):
    path = tmp_path / "multiple-comments.docx"
    _write_docx(
        path,
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:r><w:t>Reviews </w:t></w:r>
              <w:r><w:commentReference w:id="7"/></w:r>
              <w:r><w:t> and </w:t></w:r>
              <w:r><w:commentReference w:id="9"/></w:r>
            </w:p>
          </w:body>
        </w:document>
        """,
        comments_xml="""
        <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:comment w:id="7" w:author="Alice">
            <w:p><w:r><w:t>First review</w:t></w:r></w:p>
          </w:comment>
          <w:comment w:id="9" w:author="Bob">
            <w:p><w:r><w:t>Second review</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """,
    )

    doc = DOCXReader().read(str(path))
    paragraph = doc.sections[0].elements[0]
    comments = doc.find_all("comment")
    markdown = to_markdown(doc)
    payload_comments = to_dict(doc)["sections"][0]["elements"][1:]

    assert paragraph.text == "Reviews [comment 1] and [comment 2]"
    assert [run.note_reference_type for run in paragraph.runs] == [
        "",
        "comment",
        "",
        "comment",
    ]
    assert [comment.number for comment in comments] == [1, 2]
    assert [comment.author for comment in comments] == ["Alice", "Bob"]
    assert "Reviews [^comment-1] and [^comment-2]" in markdown
    assert markdown.count("[^comment-1]: First review") == 1
    assert markdown.count("[^comment-2]: Second review") == 1
    assert "[^미주]" not in markdown
    assert [item["number"] for item in payload_comments] == [1, 2]
    assert [item["author"] for item in payload_comments] == ["Alice", "Bob"]


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


def test_docx_deep_structure_branches_are_omitted_with_one_diagnostic(tmp_path):
    path = tmp_path / "deep-structures.docx"
    depth = 1100

    def nested(tag, content):
        return f"<w:{tag}>" * depth + content + f"</w:{tag}>" * depth

    deep_block = nested("sdt", "<w:p><w:r><w:t>Deep block</w:t></w:r></w:p>")
    deep_run = nested("smartTag", "<w:r><w:t>Deep run</w:t></w:r>")
    deep_note = nested("sdt", "<w:p><w:r><w:t>Deep note</w:t></w:r></w:p>")
    deep_footer = nested("smartTag", "<w:p><w:r><w:t>Deep footer</w:t></w:r></w:p>")

    _write_docx(
        path,
        f"""
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            {deep_block}
            <w:p>{deep_run}</w:p>
            <w:p>
              <w:r><w:t>Safe body</w:t><w:footnoteReference w:id="2"/></w:r>
            </w:p>
            <w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/></w:sectPr>
          </w:body>
        </w:document>
        """,
        document_rels_xml="""
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer.xml"/>
        </Relationships>
        """,
        footnotes_xml=f"""
        <w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:footnote w:id="2">
            {deep_note}
            <w:p><w:r><w:t>Safe note</w:t></w:r></w:p>
          </w:footnote>
        </w:footnotes>
        """,
        extra_parts={
            "word/footer.xml": f"""
            <w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              {deep_footer}
              <w:p><w:r><w:t>Safe footer</w:t></w:r></w:p>
            </w:ftr>
            """,
        },
    )

    doc = DOCXReader().read(str(path))
    text = "\n".join(element.text for element in doc.sections[0].elements)
    depth_errors = [error for error in doc.errors if "structure depth limit" in error]

    assert "Safe body[1]" in text
    assert "Safe note" in text
    assert "Safe footer" in text
    assert "Deep block" not in text
    assert "Deep run" not in text
    assert "Deep note" not in text
    assert "Deep footer" not in text
    assert depth_errors == ["ERR: DOCX structure depth limit exceeded (64)"]


def _deep_sdt(content, depth=1100):
    return "<w:sdt>" * depth + content + "</w:sdt>" * depth


def _assert_deep_table_wrapper_is_omitted(path, table_xml, safe_text, deep_text):
    _write_docx(
        path,
        f"""
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>{table_xml}</w:body>
        </w:document>
        """,
    )

    doc = DOCXReader().read(str(path))
    table = doc.sections[0].elements[0]
    depth_errors = [error for error in doc.errors if "structure depth limit" in error]

    assert safe_text in table.rows[0][0].text
    assert deep_text not in to_markdown(doc)
    assert depth_errors == ["ERR: DOCX structure depth limit exceeded (64)"]


def test_docx_deep_table_row_wrapper_omits_branch_and_keeps_following_row(tmp_path):
    deep_row = _deep_sdt(
        "<w:tr><w:tc><w:p><w:r><w:t>Deep row</w:t></w:r></w:p></w:tc></w:tr>",
    )
    safe_row = (
        "<w:tr><w:tc><w:p><w:r><w:t>Safe row</w:t></w:r></w:p></w:tc></w:tr>"
    )

    _assert_deep_table_wrapper_is_omitted(
        tmp_path / "deep-table-row-wrapper.docx",
        f"<w:tbl>{deep_row}{safe_row}</w:tbl>",
        "Safe row",
        "Deep row",
    )


def test_docx_deep_table_cell_wrapper_omits_branch_and_keeps_following_cell(tmp_path):
    deep_cell = _deep_sdt(
        "<w:tc><w:p><w:r><w:t>Deep cell</w:t></w:r></w:p></w:tc>",
    )
    safe_cell = "<w:tc><w:p><w:r><w:t>Safe cell</w:t></w:r></w:p></w:tc>"

    _assert_deep_table_wrapper_is_omitted(
        tmp_path / "deep-table-cell-wrapper.docx",
        f"<w:tbl><w:tr>{deep_cell}{safe_cell}</w:tr></w:tbl>",
        "Safe cell",
        "Deep cell",
    )


def test_docx_deep_cell_paragraph_wrapper_omits_branch_and_keeps_following_paragraph(
    tmp_path,
):
    deep_paragraph = _deep_sdt(
        "<w:p><w:r><w:t>Deep paragraph</w:t></w:r></w:p>",
    )
    safe_paragraph = "<w:p><w:r><w:t>Safe paragraph</w:t></w:r></w:p>"

    _assert_deep_table_wrapper_is_omitted(
        tmp_path / "deep-cell-paragraph-wrapper.docx",
        (
            "<w:tbl><w:tr><w:tc>"
            f"{deep_paragraph}{safe_paragraph}"
            "</w:tc></w:tr></w:tbl>"
        ),
        "Safe paragraph",
        "Deep paragraph",
    )


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
