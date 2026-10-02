"""Synthetic regressions for the DOC/PPT P3 review."""
from dochan.office_binary.ppt import parse_ppt_document_stream
from dochan.office_binary.ppt_text import TextBlock, render_text
from test_ppt_structure import presentation, record, shape, sheet, slide_list


def test_unresolved_slides_supplement_legacy_text_without_guessing_slide():
    data, current = presentation(
        [(2, sheet(shapes=shape(b"OrphanA"))), (3, sheet(shapes=shape(b"OrphanB")))],
        [slide_list([(99, 256, b""), (98, 257, b"")])],
    )
    doc = parse_ppt_document_stream(data, current_user=current)
    paragraphs = doc.find_all("paragraph")
    assert [p.text for p in paragraphs] == ["OrphanA", "OrphanB"]
    assert all(p.provenance.path == "PowerPoint Document#legacy-recovery" for p in paragraphs)
    assert all(p.provenance.slide is None for p in paragraphs)
    assert any("legacy" in warning for warning in doc.errors)


def test_legacy_supplement_deduplicates_structured_and_repeated_text():
    data, current = presentation(
        [(2, sheet(shapes=shape(b"Already rendered"))),
         (3, sheet(shapes=shape(b"Already rendered") + shape(b"Orphan"))),
         (4, sheet(shapes=shape(b"Orphan")))],
        [slide_list([(2, 256, b""), (99, 257, b""), (98, 258, b"")])],
    )
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [p.text for p in doc.find_all("paragraph")] == ["Already rendered", "Orphan"]


def test_legacy_supplement_ignores_cstring_metadata_and_preserves_headings():
    outline = record(3999, (0).to_bytes(4, "little")) + record(4008, b"Title")
    metadata = record(4026, "Not slide text".encode("utf-16le"))
    data, current = presentation(
        [(2, sheet(shapes=shape(b"Title"))), (3, sheet(shapes=shape(b"Salvaged")))],
        [metadata, slide_list([(99, 256, outline), (98, 257, b"")])],
    )
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [p.text for p in doc.find_all("paragraph")] == ["Title", "Salvaged"]
    assert doc.find_all("paragraph")[0].heading_level == 1


def test_legacy_supplement_respects_shared_output_and_record_limits():
    from dochan.model.document import Document
    from dochan.office_binary.ppt import _extract_ppt_text_records, _supplement_legacy_text
    data = record(4008, b"first") + record(4008, b"second")
    budget = [1, 100]
    assert _extract_ppt_text_records(data, recovery_budget=budget) == ["first"]
    assert budget == [0, 95]
    doc = Document(source_format="ppt")
    _supplement_legacy_text(doc, data, "PowerPoint Document", 100, 1)
    assert [p.text for p in doc.find_all("paragraph")] == ["first"]
    assert any("output budget" in warning for warning in doc.errors)


def test_legacy_recovery_omits_master_editing_prompts_and_master_notes():
    import struct
    master_id = 0x80000001
    master_note = record(1008, record(1009, struct.pack("<II", master_id, 0))
                         + record(4008, b"Click to edit Master text styles"), container=True)
    data, current = presentation(
        [(2, sheet(shapes=shape(b"Orphan"))),
         (3, sheet(1016, shape(b"Click to edit Master title style", placeholder=1))),
         (4, master_note)],
        [slide_list([(99, 256, b""), (98, 257, b"")]),
         slide_list([(3, master_id, b"")], 1)],
    )
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [p.text for p in doc.find_all("paragraph")] == ["Orphan"]


def test_legacy_recovery_deduplicates_structured_bullet_prefix():
    from dochan.model.document import Document, Paragraph, Section, TextRun
    from dochan.office_binary.ppt import _supplement_legacy_text
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun(text="• body")])])])
    _supplement_legacy_text(doc, record(4008, b"body"), "PowerPoint Document", 100, 100)
    assert [p.text for p in doc.find_all("paragraph")] == ["• body"]


def test_legacy_recovery_deduplicates_multiline_paragraph_and_line():
    from dochan.model.document import Document, Paragraph, Section, TextRun
    from dochan.office_binary.ppt import _supplement_legacy_text
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun(text="Already\nrendered")])])])
    _supplement_legacy_text(doc, record(4008, b"Already rendered") + record(4008, b"rendered"),
                            "PowerPoint Document", 100, 100)
    assert [p.text for p in doc.find_all("paragraph")] == ["Already\nrendered"]


def test_missing_master_or_notes_reference_triggers_recovery():
    for reference in ({"master": 900}, {"notes": 700}):
        data, current = presentation(
            [(2, sheet(shapes=shape(b"Visible"), **reference)),
             (3, sheet(shapes=shape(b"Orphan")))],
            [slide_list([(2, 256, b"")])],
        )
        doc = parse_ppt_document_stream(data, current_user=current)
        assert [p.text for p in doc.find_all("paragraph")] == ["Visible", "Orphan"]
        assert doc.find_all("paragraph")[-1].provenance.slide is None


def test_master_pictures_are_not_repeated_but_slide_pictures_and_text_survive():
    data, current = presentation(
        [(2, sheet(shapes=shape(pib=1), master=900)),
         (3, sheet(shapes=shape(b"Second slide"), master=900)),
         (4, sheet(1016, shape(b"Master caption") + shape(pib=2)))],
        [slide_list([(2, 256, b""), (3, 257, b"")]), slide_list([(4, 900, b"")], 1)],
    )
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [image.bin_id for image in doc.find_all("image")] == [1]
    assert [p.text for p in doc.find_all("paragraph")].count("Master caption") == 2
    assert len(doc.assets) == 1


def test_large_text_block_preserves_output_after_many_newline_fragments():
    errors = []
    paragraphs = render_text(TextBlock(text="line\r" * 60000 + "tail"), None, errors=errors)
    assert len(paragraphs) == 60001
    assert paragraphs[-1].text == "tail"
    assert errors == []


def test_fragment_budget_is_shared_across_document_blocks():
    from dochan.office_binary.ppt_render import _Renderer
    from dochan.model.document import Document
    renderer = _Renderer(Document(source_format="ppt"), [], {}, "PowerPoint Document")
    renderer.fragment_budget = [5]
    assert [p.text for p in renderer.text(TextBlock(text="a\rb\r"), None)] == ["a", "b"]
    assert [p.text for p in renderer.text(TextBlock(text="c\rd"), None)] == ["c"]
    assert renderer.fragment_budget == [0]
    assert any("fragment" in warning for warning in renderer.doc.errors)
