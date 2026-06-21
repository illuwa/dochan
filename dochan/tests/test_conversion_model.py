import json

from dochan.conversion import AssetRef, ConversionOptions, ConversionResult, Provenance
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.table import Cell, Table
from dochan.output.json_out import to_json


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
