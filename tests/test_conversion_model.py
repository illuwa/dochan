import json
import re

from dochan.conversion import AssetRef, ConversionResult, Provenance
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.equation import Equation
from dochan.model.header_footer import Comment, Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.output.json_out import to_dict, to_json
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text


def test_provenance_defaults_are_empty_and_serializable():
    prov = Provenance(source_format="docx", section=1, paragraph=2, path="word/document.xml")

    assert prov.source_format == "docx"
    assert prov.section == 1
    assert prov.paragraph == 2
    assert prov.path == "word/document.xml"
    assert prov.page is None
    assert prov.slide is None
    assert prov.sheet is None
    assert prov.cell is None
    assert prov.visibility == 0
    assert prov.hidden is False


def test_json_output_preserves_explicit_visible_provenance_values():
    doc = Document(
        sections=[
            Section(
                provenance=Provenance(source_format="xls", visibility=0, hidden=False),
                elements=[
                    Paragraph(
                        runs=[TextRun(text="Hidden")],
                        provenance=Provenance(source_format="xls", visibility=2, hidden=True),
                    )
                ],
            )
        ]
    )

    payload = json.loads(to_json(doc))

    assert payload["sections"][0]["provenance"]["visibility"] == 0
    assert payload["sections"][0]["provenance"]["hidden"] is False
    assert payload["sections"][0]["elements"][0]["provenance"]["visibility"] == 2
    assert payload["sections"][0]["elements"][0]["provenance"]["hidden"] is True


def test_conversion_result_wraps_document_without_output_side_effects():
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun(text="Hello")])])])
    result = ConversionResult(document=doc, source_path="/tmp/sample.docx", source_format="docx")

    assert result.document.sections[0].elements[0].text == "Hello"
    assert result.source_path == "/tmp/sample.docx"
    assert result.source_format == "docx"
    assert result.metadata == {}
    assert result.assets == []
    assert result.warnings == []


def test_document_metadata_includes_source_format_when_set():
    doc = Document(source_format="docx")

    assert doc.metadata["source_format"] == "docx"


def test_document_metadata_errors_are_a_snapshot():
    doc = Document(errors=["ERR: original"])

    metadata = doc.metadata
    payload = to_dict(doc)
    metadata["errors"].append("ERR: metadata mutation")
    payload["metadata"]["errors"].append("ERR: payload mutation")

    assert doc.errors == ["ERR: original"]


def test_asset_ref_records_package_relationship():
    asset = AssetRef(
        id="rId5",
        source_path="word/media/image1.png",
        filename="image1.png",
        content_type="image/png",
    )

    assert asset.id == "rId5"
    assert asset.source_path == "word/media/image1.png"
    assert asset.filename == "image1.png"
    assert asset.content_type == "image/png"


def test_json_output_includes_asset_references():
    doc = Document(
        source_format="pptx",
        assets=[
            AssetRef(
                id="rIdImage",
                source_path="ppt/media/image1.png",
                filename="image1.png",
                content_type="image/png",
                metadata={"label": "Revenue Chart", "slide": 1, "source_format": "pptx"},
            )
        ],
    )

    payload = json.loads(to_json(doc))

    assert payload["metadata"]["assets"] == 1
    assert payload["assets"] == [
        {
            "id": "rIdImage",
            "source_path": "ppt/media/image1.png",
            "filename": "image1.png",
            "content_type": "image/png",
            "metadata": {"label": "Revenue Chart", "slide": 1, "source_format": "pptx"},
        }
    ]


def test_json_asset_metadata_is_a_detached_snapshot():
    asset = AssetRef(
        id="rIdNested",
        metadata={"nested": {"value": 1}, "labels": ["original"]},
    )
    payload = to_dict(Document(assets=[asset]))

    payload["assets"][0]["metadata"]["nested"]["value"] = 99
    payload["assets"][0]["metadata"]["labels"].append("mutated")

    assert asset.metadata == {
        "nested": {"value": 1},
        "labels": ["original"],
    }


def test_json_output_preserves_image_dimensions_and_ocr_text_without_binary_data():
    doc = Document(
        sections=[
            Section(
                elements=[
                    Image(
                        bin_id=3,
                        filename="scan.png",
                        width=640,
                        height=480,
                        image_data=b"raw image bytes",
                        ocr_text="인식된 본문",
                    )
                ]
            )
        ]
    )

    image = json.loads(to_json(doc))["sections"][0]["elements"][0]

    assert image == {
        "type": "image",
        "bin_id": 3,
        "filename": "scan.png",
        "width": 640,
        "height": 480,
        "ocr_text": "인식된 본문",
    }
    assert "image_data" not in image


def test_json_output_preserves_provenance_and_rich_structure():
    doc = Document(
        source_format="xlsx",
        sections=[
            Section(
                provenance=Provenance(source_format="xlsx", sheet="Data", path="xl/worksheets/sheet1.xml"),
                elements=[
                    Paragraph(
                        runs=[
                            TextRun(
                                text="Revenue",
                                bold=True,
                                underline=True,
                                strikeout=True,
                                superscript=True,
                                subscript=True,
                                provenance=Provenance(source_format="xlsx", sheet="Data", cell="A1"),
                            )
                        ],
                        heading_level=2,
                        provenance=Provenance(source_format="xlsx", sheet="Data", path="xl/worksheets/sheet1.xml"),
                    ),
                    Table(
                        rows=[
                            [
                                Cell(
                                    row=1,
                                    col=1,
                                    paragraphs=[Paragraph(runs=[TextRun(text="Cell")])],
                                    row_span=2,
                                    col_span=3,
                                    provenance=Provenance(source_format="xlsx", sheet="Data", cell="B2"),
                                )
                            ]
                        ]
                    ),
                ],
            )
        ],
    )

    payload = json.loads(to_json(doc))

    section = payload["sections"][0]
    assert section["provenance"] == {
        "source_format": "xlsx",
        "sheet": "Data",
        "path": "xl/worksheets/sheet1.xml",
        "visibility": 0,
        "hidden": False,
    }
    paragraph = section["elements"][0]
    assert paragraph["heading_level"] == 2
    assert paragraph["provenance"]["sheet"] == "Data"
    run = paragraph["runs"][0]
    assert run["underline"] is True
    assert run["strikeout"] is True
    assert run["superscript"] is True
    assert run["subscript"] is True
    assert run["provenance"]["cell"] == "A1"
    cell = section["elements"][1]["rows"][0][0]
    assert cell["row_span"] == 2
    assert cell["col_span"] == 3
    assert cell["row"] == 1
    assert cell["col"] == 1
    assert cell["provenance"]["cell"] == "B2"


def test_json_output_preserves_table_cell_paragraph_structure():
    doc = Document(
        source_format="docx",
        sections=[
            Section(
                elements=[
                    Table(
                        rows=[
                            [
                                Cell(
                                    paragraphs=[
                                        Paragraph(
                                            runs=[
                                                TextRun(
                                                    text="Cell heading",
                                                    bold=True,
                                                    provenance=Provenance(
                                                        source_format="docx",
                                                        path="word/document.xml",
                                                    ),
                                                )
                                            ],
                                            heading_level=3,
                                            provenance=Provenance(
                                                source_format="docx",
                                                path="word/document.xml",
                                            ),
                                        )
                                    ],
                                    provenance=Provenance(
                                        source_format="docx",
                                        path="word/document.xml",
                                    ),
                                )
                            ]
                        ]
                    )
                ]
            )
        ],
    )

    payload = json.loads(to_json(doc))

    table = payload["sections"][0]["elements"][0]
    assert table["row_count"] == 1
    assert table["col_count"] == 1
    cell = table["rows"][0][0]
    assert cell["text"] == "Cell heading"
    paragraph = cell["paragraphs"][0]
    assert paragraph["heading_level"] == 3
    assert paragraph["provenance"]["path"] == "word/document.xml"
    run = paragraph["runs"][0]
    assert run["text"] == "Cell heading"
    assert run["bold"] is True
    assert run["provenance"]["source_format"] == "docx"


def test_document_find_all_recurses_through_notes_headers_and_tables_without_duplicates():
    shared_paragraph = Paragraph(runs=[TextRun(text="Shared")])
    nested_image = Image(bin_id=1, filename="nested.png")
    nested_table = Table(
        rows=[[Cell(paragraphs=[shared_paragraph, nested_image])]],
    )
    header_paragraph = Paragraph(runs=[TextRun(text="Header")])
    header = HeaderFooter(type="header", paragraphs=[header_paragraph])
    footer = HeaderFooter(type="footer", paragraphs=[])
    footnote = Footnote(
        type="footnote",
        paragraphs=[shared_paragraph, nested_table],
    )
    endnote = Footnote(type="endnote", paragraphs=[])
    doc = Document(
        sections=[Section(elements=[header, footer, footnote, endnote])],
    )

    assert doc.find_all("header") == [header]
    assert doc.find_all("footer") == [footer]
    assert doc.find_all("footnote") == [footnote]
    assert doc.find_all("endnote") == [endnote]
    assert doc.find_all("table") == [nested_table]
    assert doc.find_all("image") == [nested_image]
    assert doc.find_all("paragraph") == [header_paragraph, shared_paragraph]


def test_markdown_renders_unique_numeric_note_definitions_and_matching_docx_references():
    first_note = Footnote(
        type="footnote",
        paragraphs=[Paragraph(runs=[TextRun(text="First detail")])],
    )
    second_note = Footnote(
        type="endnote",
        paragraphs=[Paragraph(runs=[TextRun(text="Second detail")])],
    )
    doc = Document(
        source_format="docx",
        sections=[
            Section(
                elements=[
                    Paragraph(
                        runs=[
                            TextRun(text="Body"),
                            TextRun(
                                text="[1]",
                                superscript=True,
                                note_reference_type="footnote",
                                note_reference_number=1,
                            ),
                            TextRun(text=", end"),
                            TextRun(
                                text="[2]",
                                note_reference_type="endnote",
                                note_reference_number=2,
                            ),
                        ]
                    ),
                    first_note,
                    second_note,
                ]
            )
        ]
    )

    markdown = to_markdown(doc)
    definitions = re.findall(r"^\[\^(\d+)\]:", markdown, flags=re.MULTILINE)

    assert definitions == ["1", "2"]
    assert "Body[^1], end[^2]" in markdown
    assert "<sup>[^1]</sup>" not in markdown
    assert "[^1]: First detail" in markdown
    assert "[^2]: Second detail" in markdown


def test_markdown_preserves_literal_bracket_number_and_serializes_semantic_reference():
    reference = TextRun(
        text="[1]",
        note_reference_type="footnote",
        note_reference_number=1,
    )
    doc = Document(
        sections=[
            Section(
                elements=[
                    Paragraph(runs=[TextRun(text="literal [1], note "), reference]),
                    Footnote(
                        type="footnote",
                        number=1,
                        paragraphs=[Paragraph(runs=[TextRun(text="Detail")])],
                    ),
                ]
            )
        ]
    )

    markdown = to_markdown(doc)
    run_payload = to_dict(doc)["sections"][0]["elements"][0]["runs"][1]

    assert "literal [1], note [^1]" in markdown
    assert run_payload["note_reference_type"] == "footnote"
    assert run_payload["note_reference_number"] == 1


def test_markdown_preserves_unique_explicit_note_numbers_and_resolves_collisions():
    notes = [
        Footnote(
            type="footnote",
            number=7,
            paragraphs=[Paragraph(runs=[TextRun(text="First detail")])],
        ),
        Footnote(
            type="endnote",
            number=7,
            paragraphs=[Paragraph(runs=[TextRun(text="Second detail")])],
        ),
        Footnote(
            type="footnote",
            paragraphs=[Paragraph(runs=[TextRun(text="Third detail")])],
        ),
    ]
    doc = Document(sections=[Section(elements=notes)])

    definitions = re.findall(
        r"^\[\^(\d+)\]:", to_markdown(doc), flags=re.MULTILINE,
    )

    assert definitions == ["7", "1", "2"]


def test_json_output_preserves_explicit_footnote_number():
    doc = Document(
        sections=[
            Section(
                elements=[
                    Footnote(
                        type="footnote",
                        number=12,
                        paragraphs=[Paragraph(runs=[TextRun(text="Detail")])],
                    )
                ]
            )
        ]
    )

    note = json.loads(to_json(doc))["sections"][0]["elements"][0]

    assert note["number"] == 12


def test_plain_text_preserves_table_only_footnote():
    note = Footnote(
        paragraphs=[
            Table(
                rows=[
                    [
                        Cell(paragraphs=[Paragraph(runs=[TextRun(text="A")])]),
                        Cell(paragraphs=[Paragraph(runs=[TextRun(text="B")])]),
                    ]
                ]
            )
        ]
    )
    doc = Document(sections=[Section(elements=[note])])

    assert note.text == "A\tB"
    assert to_plain_text(doc) == "A\tB"


def test_table_cell_preserves_equation_and_image_ocr_in_text_outputs():
    cell = Cell(
        paragraphs=[
            Equation(script="x over y"),
            Image(filename="scan.png", ocr_text="OCR_BODY"),
        ]
    )
    doc = Document(sections=[Section(elements=[Table(rows=[[cell]])])])

    assert "수식" in cell.text
    assert "OCR_BODY" in cell.text
    assert "[수식: \\frac{x}{y}]" in to_plain_text(doc)
    markdown = to_markdown(doc)
    assert "$\\frac{x}{y}$" in markdown
    assert "OCR_BODY" in markdown


def test_markdown_renders_nested_note_definition_once_without_inline_body():
    reference = Paragraph(
        runs=[
            TextRun(text="Cell note "),
            TextRun(
                text="[1]",
                note_reference_type="footnote",
                note_reference_number=1,
            ),
        ]
    )
    note = Footnote(
        type="footnote",
        number=1,
        paragraphs=[Paragraph(runs=[TextRun(text="Nested detail")])],
    )
    table = Table(rows=[[Cell(paragraphs=[reference, note])]])
    doc = Document(
        sections=[
            Section(elements=[table]),
            # Reusing the same model object must not duplicate its definition.
            Section(elements=[note]),
        ]
    )

    markdown = to_markdown(doc)

    assert "| Cell note [^1] |" in markdown
    assert "Cell note [^1] Nested detail" not in markdown
    assert markdown.count("[^1]: Nested detail") == 1


def test_header_footer_json_preserves_nested_runs_and_provenance():
    header = HeaderFooter(
        type="header",
        paragraphs=[
            Paragraph(
                runs=[
                    TextRun(
                        text="Header",
                        bold=True,
                        provenance=Provenance(
                            source_format="docx",
                            path="word/header1.xml",
                        ),
                    )
                ],
                provenance=Provenance(
                    source_format="docx",
                    path="word/header1.xml",
                ),
            )
        ],
    )

    payload = to_dict(Document(sections=[Section(elements=[header])]))
    serialized = payload["sections"][0]["elements"][0]

    assert serialized["text"] == "Header"
    assert serialized["elements"][0]["runs"][0]["bold"] is True
    assert serialized["elements"][0]["runs"][0]["provenance"]["path"] == (
        "word/header1.xml"
    )


def test_comment_model_has_distinct_markdown_labels_and_json_contract():
    footnote = Footnote(
        type="footnote",
        number=1,
        paragraphs=[Paragraph(runs=[TextRun(text="Footnote detail")])],
    )
    first_comment = Comment(
        number=1,
        author="Alice",
        paragraphs=[Paragraph(runs=[TextRun(text="First review")])],
    )
    second_comment = Comment(
        number=2,
        author="Bob",
        paragraphs=[Paragraph(runs=[TextRun(text="Second review")])],
    )
    doc = Document(
        sections=[
            Section(
                elements=[
                    Paragraph(
                        runs=[
                            TextRun(text="Footnote"),
                            TextRun(
                                text="[1]",
                                note_reference_type="footnote",
                                note_reference_number=1,
                            ),
                            TextRun(text=" comments "),
                            TextRun(
                                text="[comment 1]",
                                note_reference_type="comment",
                                note_reference_number=1,
                            ),
                            TextRun(text=" and "),
                            TextRun(
                                text="[comment 2]",
                                note_reference_type="comment",
                                note_reference_number=2,
                            ),
                        ]
                    ),
                    footnote,
                    first_comment,
                    second_comment,
                ]
            )
        ]
    )

    markdown = to_markdown(doc)
    payload = to_dict(doc)
    comments = payload["sections"][0]["elements"][2:]

    assert doc.find_all("comment") == [first_comment, second_comment]
    assert doc.find_all("note") == [footnote, first_comment, second_comment]
    assert "Footnote[^1] comments [^comment-1] and [^comment-2]" in markdown
    assert markdown.count("[^comment-1]: First review") == 1
    assert markdown.count("[^comment-2]: Second review") == 1
    assert "[^미주]" not in markdown
    assert [
        (item["type"], item["text"], item["number"], item["author"])
        for item in comments
    ] == [
        ("comment", "First review", 1, "Alice"),
        ("comment", "Second review", 2, "Bob"),
    ]
    assert [item["elements"][0]["type"] for item in comments] == [
        "paragraph",
        "paragraph",
    ]
