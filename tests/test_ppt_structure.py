"""Synthetic MS-PPT persistent objects; no corpus required in CI."""
import struct

from dochan.office_binary.ppt_structure import resolve_presentation


def record(kind, payload=b"", instance=0, container=False):
    return struct.pack("<HHI", (instance << 4) | (15 if container else 0), kind, len(payload)) + payload


def slide_list(entries, instance=0):
    return record(4080, b"".join(record(1011, struct.pack("<5I", pid, 4, 0, sid, 0)) + text
                                 for pid, sid, text in entries), instance, True)


def presentation(objects, lists, previous=None):
    data = bytearray(record(1000, b"".join(lists), container=True))
    offsets = {1: 0}
    for pid, obj in objects:
        offsets[pid] = len(data)
        data.extend(obj)
    directory = len(data)
    data.extend(record(6002, b"".join(struct.pack("<II", (1 << 20) | pid, off)
                                     for pid, off in offsets.items())))
    edit = len(data)
    data.extend(record(4085, struct.pack("<IIIIIIHH", 0, 0x03000000, 0, directory, 1, 100, 1, 0)))
    if previous:
        pid, obj = previous
        replacement = len(data)
        data.extend(obj)
        directory = len(data)
        data.extend(record(6002, struct.pack("<II", (1 << 20) | pid, replacement)))
        newest = len(data)
        data.extend(record(4085, struct.pack("<IIIIIIHH", 0, 0x03000000, edit, directory, 1, 100, 1, 0)))
        edit = newest
    current = record(4086, struct.pack("<IIIHHBBH", 20, 0xE391C05F, edit, 0, 1012, 3, 0, 0))
    return bytes(data), current


def test_latest_persist_replacement_and_slide_list_order():
    data, current = presentation(
        [(2, record(1006, record(4008, b"old"), container=True)),
         (3, record(1006, record(4008, b"second"), container=True))],
        [slide_list([(3, 257, b""), (2, 256, b"")])],
        previous=(2, record(1006, record(4008, b"new"), container=True)),
    )
    result = resolve_presentation(data, current, [])
    assert [s.slide_id for s in result.slides] == [257, 256]
    assert bytes(result.slides[1].record.children[0].data) == b"new"
    assert b"old" not in bytes(result.slides[1].record.data)


def test_resolves_master_notes_and_outline_text_by_persist_id():
    outline = record(3999, struct.pack("<I", 0)) + record(4008, b"Outline title")
    slide = record(1006, record(1007, b"\0" * 12 + struct.pack("<IIHH", 0x80000000, 258, 7, 0)), container=True)
    data, current = presentation(
        [(2, slide), (3, record(1016, container=True)), (4, record(1008, container=True))],
        [slide_list([(2, 256, outline)]), slide_list([(3, 0x80000000, b"")], 1),
         slide_list([(4, 258, b"")], 2)],
    )
    result = resolve_presentation(data, current, [])
    assert result.slides[0].master_id == 0x80000000
    assert result.slides[0].notes_id == 258
    assert result.masters[0x80000000].record.header.rec_type == 1016
    assert result.notes[258].record.header.rec_type == 1008
    assert result.slides[0].text_records[1].header.rec_type == 4008


def test_edit_cycle_and_invalid_offsets_warn_without_hanging():
    data, current = presentation([(2, record(1006, container=True))], [slide_list([(2, 256, b"")])])
    damaged = bytearray(data)
    edit = struct.unpack_from("<I", current, 16)[0]
    struct.pack_into("<I", damaged, edit + 16, edit)
    errors = []
    assert resolve_presentation(bytes(damaged), current, errors).slides
    assert any("cycle" in e for e in errors)
    errors = []
    bad_user = bytearray(current)
    struct.pack_into("<I", bad_user, 16, len(data) + 100)
    assert resolve_presentation(data, bytes(bad_user), errors) is None
    assert errors and all(e.startswith("WARN:") for e in errors)


def test_no_current_user_is_legacy_fallback_without_warning():
    errors = []
    assert resolve_presentation(record(4008, b"legacy"), b"", errors) is None
    assert errors == []


def shape(text=b"", x=0, y=0, placeholder=None, pib=0, description=""):
    properties = []
    complex_data = b""
    if pib:
        properties.append(struct.pack("<HI", 0x4104, pib))
    if description:
        complex_data = (description + "\0").encode("utf-16le")
        properties.append(struct.pack("<HI", 0x8381, len(complex_data)))
    payload = record(0xF00A, struct.pack("<II", 1025, 0xA00))
    payload += record(0xF010, struct.pack("<4h", y, x, x + 100, y + 100))
    if properties:
        payload += record(0xF00B, b"".join(properties) + complex_data, len(properties))
    if placeholder is not None:
        payload += record(0xF011, record(3011, struct.pack("<IBBH", 0, placeholder, 0, 0)))
    if text:
        payload += record(0xF00D, record(3999, struct.pack("<I", 4)) + record(4008, text))
    return record(0xF004, payload, container=True)


def sheet(kind=1006, shapes=b"", master=0, notes=0, flags=7):
    atom = record(1007, b"\0" * 12 + struct.pack("<IIHH", master, notes, flags, 0)) if kind != 1008 else record(1009, b"\0" * 8)
    return record(kind, atom + record(1036, record(0xF002, shapes, container=True), container=True), container=True)


def test_structured_reading_order_master_placeholder_filter_and_notes_association():
    from dochan.office_binary.ppt import parse_ppt_document_stream
    data, current = presentation(
        [(2, sheet(shapes=shape(b"Lower", y=500) + shape(b"Upper", y=100), master=900, notes=700)),
         (3, sheet(1016, shape(b"Master caption") + shape(b"Click to edit", placeholder=1))),
         (4, sheet(1008, shape(b"Speaker note") + shape(b"*", placeholder=8)))],
        [slide_list([(2, 256, b"")]), slide_list([(3, 900, b"")], 1), slide_list([(4, 700, b"")], 2)],
    )
    doc = parse_ppt_document_stream(data, current_user=current)
    paragraphs = doc.find_all("paragraph")
    assert [p.text for p in paragraphs] == ["Master caption", "Upper", "Lower", "Speaker note"]
    assert paragraphs[-1].provenance.path == "PowerPoint Document#slide1#notes"
    assert all(p.provenance.slide == 1 for p in paragraphs)
    assert doc.errors == []


def test_image_pib_delayed_blip_description_asset_and_ocr(monkeypatch):
    from dochan.office_binary.ppt import parse_ppt_document_stream
    png = b"\x89PNG\r\n\x1a\nimage-payload"
    blip = record(0xF01E, b"u" * 16 + b"\xff" + png, 0x6E0)
    bse = record(0xF007, struct.pack("<BB16sHIIIBBBB", 6, 6, b"u" * 16, 255, len(blip), 1, 0, 0, 0, 0, 0))
    drawing = record(1035, record(0xF000, record(0xF001, bse, 1, True), container=True), container=True)
    data, current = presentation([(2, sheet(shapes=shape(pib=1, description="Diagram")))],
                                 [drawing, slide_list([(2, 256, b"")])])
    doc = parse_ppt_document_stream(data, current_user=current, pictures=blip)
    image = doc.find_all("image")[0]
    assert image.image_data == png
    assert image.image_format == "png"
    assert image.alt_text == "Diagram"
    assert len(doc.assets) == 1
    assert doc.assets[0].source_path == image.provenance.path
    assert "![Diagram](" in doc.find_all("paragraph")[0].text
    monkeypatch.setattr("dochan.utils.ocr.ocr_image", lambda data: "diagram words" if data == png else "")
    assert image.run_ocr() == "diagram words"
    assert image.ocr_text == "diagram words"


def test_invalid_persist_pointer_preserves_legacy_text_with_warning():
    from dochan.office_binary.ppt import parse_ppt_document_stream
    data, current = presentation([(2, sheet(shapes=shape(b"Recovered")))], [slide_list([(2, 256, b"")])])
    bad_user = bytearray(current)
    struct.pack_into("<I", bad_user, 16, len(data) + 100)
    doc = parse_ppt_document_stream(data, current_user=bytes(bad_user))
    assert "Recovered" in " ".join(p.text for p in doc.find_all("paragraph"))
    assert any(e.startswith("WARN:") for e in doc.errors)


def test_slide_number_meta_character_is_resolved_in_notes():
    from dochan.office_binary.ppt import parse_ppt_document_stream
    textbox = record(3999, struct.pack("<I", 4)) + record(4000, "*".encode("utf-16le"))
    textbox += record(4056, struct.pack("<I", 0))
    number_shape = record(0xF004, record(0xF00A, struct.pack("<II", 1000, 0xA00)) +
                          record(0xF00D, textbox), container=True)
    data, current = presentation([(2, sheet(notes=700)), (3, sheet(1008, number_shape))],
                                 [slide_list([(2, 256, b"")]), slide_list([(3, 700, b"")], 2)])
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [p.text for p in doc.find_all("paragraph")] == ["1"]


def test_missing_slide_persist_keeps_its_outline_and_slide_position():
    from dochan.office_binary.ppt import parse_ppt_document_stream
    outline = record(3999, struct.pack("<I", 0)) + record(4008, b"Missing slide outline")
    data, current = presentation([(2, sheet(shapes=shape(b"Present")))],
                                 [slide_list([(99, 256, outline), (2, 257, b"")])])
    doc = parse_ppt_document_stream(data, current_user=current)
    assert len(doc.sections) == 2
    assert doc.sections[0].elements[0].text == "Missing slide outline"
    assert doc.sections[1].elements[0].text == "Present"
    assert any("persist reference missing" in e for e in doc.errors)


def test_document_shape_budget_stops_repeated_persist_slides(monkeypatch):
    from dochan.office_binary.ppt import parse_ppt_document_stream
    monkeypatch.setattr("dochan.office_binary.ppt_render.MAX_SHAPES", 1)
    data, current = presentation([(2, sheet(shapes=shape(b"Once")))],
                                 [slide_list([(2, 256 + i, b"") for i in range(10)])])
    doc = parse_ppt_document_stream(data, current_user=current)
    assert len(doc.sections) == 1
    assert any("budget" in e for e in doc.errors)


def test_document_text_budget_applies_to_outline_only_slides(monkeypatch):
    from dochan.office_binary.ppt import parse_ppt_document_stream
    monkeypatch.setattr("dochan.office_binary.ppt_render.MAX_TEXT_CHARS", 4)
    outline = record(3999, struct.pack("<I", 1)) + record(4008, b"Too much text")
    data, current = presentation([(2, sheet())], [slide_list([(2, 256, outline)])])
    doc = parse_ppt_document_stream(data, current_user=current)
    assert doc.find_all("paragraph") == []
    assert any("text budget" in e for e in doc.errors)


def test_record_budget_is_shared_across_persist_objects(monkeypatch):
    monkeypatch.setattr("dochan.office_binary.ppt_structure.MAX_OBJECTS", 8)
    data, current = presentation([(2, sheet(shapes=shape(b"First"))), (3, sheet(shapes=shape(b"Second")))],
                                 [slide_list([(2, 256, b""), (3, 257, b"")])])
    errors = []
    resolve_presentation(data, current, errors)
    assert any("record" in e and ("budget" in e or "limit" in e) for e in errors)


def test_picture_description_obeys_document_output_budget(monkeypatch):
    from dochan.office_binary.ppt import parse_ppt_document_stream
    monkeypatch.setattr("dochan.office_binary.ppt_render.MAX_TEXT_CHARS", 4)
    data, current = presentation([(2, sheet(shapes=shape(pib=1, description="oversized")))],
                                 [slide_list([(2, 256, b"")])])
    doc = parse_ppt_document_stream(data, current_user=current)
    assert not doc.find_all("paragraph")
    assert any("text budget" in e for e in doc.errors)


def directory_chain(payloads, references):
    """Build edits whose directory payloads may repeat persist identifiers."""
    data = bytearray(record(1000, container=True))
    directories = []
    for payload in payloads:
        directories.append(len(data))
        data.extend(record(6002, payload))
    previous = 0
    for index in references:
        offset = len(data)
        data.extend(record(4085, struct.pack("<IIIIIIHH", 0, 0x03000000,
                                           previous, directories[index], 1, 100, 1, 0)))
        previous = offset
    current = record(4086, struct.pack("<IIIHHBBH", 20, 0xE391C05F, previous, 0, 1012, 3, 0, 0))
    return bytes(data), current


def test_persist_directory_is_decoded_once_across_repeated_edit_references(monkeypatch):
    import types
    from dochan.office_binary import ppt_structure
    payload = struct.pack("<II", (1 << 20) | 1, 0) * 3
    data, current = directory_chain([payload], [0, 0, 0, 0])
    calls = []
    original = struct.unpack_from

    def counted(fmt, buffer, offset=0):
        if fmt == "<I" and len(buffer) == len(payload):
            calls.append(offset)
        return original(fmt, buffer, offset)

    monkeypatch.setattr(ppt_structure, "struct", types.SimpleNamespace(unpack_from=counted))
    errors = []
    assert resolve_presentation(data, current, errors) is not None
    assert len(calls) == 6
    assert errors == []


def test_persist_entry_budget_counts_duplicate_ids_across_all_directories(monkeypatch):
    from dochan.office_binary import ppt_structure
    monkeypatch.setattr(ppt_structure, "MAX_DIRECTORY_ENTRIES", 4, raising=False)
    payload = struct.pack("<II", (1 << 20) | 1, 0) * 3
    data, current = directory_chain([payload, payload], [0, 1])
    errors = []
    assert resolve_presentation(data, current, errors) is not None
    assert any("persist directory entry budget" in error for error in errors)


def test_repeated_empty_group_slide_parses_drawing_only_once(monkeypatch):
    from dochan.office_binary import ppt_render
    from dochan.office_binary.ppt import parse_ppt_document_stream
    groups = b"".join(record(0xF003, record(0xF004, record(0xF00A, struct.pack("<II", i, 1)),
                                                       container=True), container=True)
                      for i in range(5))
    data, current = presentation([(2, sheet(shapes=groups))],
                                 [slide_list([(2, 256 + i, b"") for i in range(8)])])
    original = ppt_render.read_shapes
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(ppt_render, "read_shapes", counted)
    doc = parse_ppt_document_stream(data, current_user=current)
    assert not doc.find_all("paragraph")
    assert len(calls) == 1


def test_missing_slide_reference_exposes_unique_latest_unlisted_slide_for_recovery():
    data, current = presentation([(2, sheet(shapes=shape(b"Old edit")))],
                                 [slide_list([(99, 256, b"")])],
                                 previous=(2, sheet(shapes=shape(b"Recovered"))))
    result = resolve_presentation(data, current, [])
    missing = result.slides[0]
    assert missing.unresolved is True
    assert missing.recovery_record is not None
    assert b"Recovered" in bytes(missing.recovery_record.data)
    assert b"Old edit" not in bytes(missing.recovery_record.data)


def test_missing_slide_reference_preserves_recoverable_text_without_old_edits():
    from dochan.office_binary.ppt import parse_ppt_document_stream
    data, current = presentation([(2, sheet(shapes=shape(b"Old edit")))],
                                 [slide_list([(99, 256, b"")])],
                                 previous=(2, sheet(shapes=shape(b"Recovered"))))
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [p.text for p in doc.find_all("paragraph")] == ["Recovered"]
    assert any("recover" in error for error in doc.errors)


def test_unresolved_slide_recovery_does_not_guess_between_multiple_candidates():
    data, current = presentation([(2, sheet(shapes=shape(b"First orphan"))),
                                  (3, sheet(shapes=shape(b"Second orphan")))],
                                 [slide_list([(99, 256, b"")])])
    result = resolve_presentation(data, current, [])
    assert result.slides[0].unresolved is True
    assert result.slides[0].recovery_record is None


def test_normal_empty_slide_and_outline_only_missing_slide_skip_orphan_recovery():
    outline = record(3999, struct.pack("<I", 0)) + record(4008, b"Outline")
    data, current = presentation([(2, sheet()), (3, sheet(shapes=shape(b"Orphan")))],
                                 [slide_list([(2, 256, b""), (99, 257, outline)])])
    result = resolve_presentation(data, current, [])
    assert result.slides[0].unresolved is False
    assert result.slides[0].recovery_record is None
    assert result.slides[1].unresolved is True
    assert result.slides[1].recovery_record is None


def test_missing_slide_does_not_recover_a_referenced_slide_type_master():
    data, current = presentation([(2, sheet(shapes=shape(b"Master content")))],
                                 [slide_list([(99, 256, b"")]),
                                  slide_list([(2, 900, b"")], 1)])
    result = resolve_presentation(data, current, [])
    assert result.slides[0].unresolved is True
    assert result.slides[0].recovery_record is None


def test_recovered_slide_retains_latest_master_notes_and_flags():
    data, current = presentation([(2, sheet(shapes=shape(b"Recovered"), master=900, notes=700, flags=5)),
                                  (3, sheet(1016, shape(b"Master caption"))),
                                  (4, sheet(1008, shape(b"Speaker note")))],
                                 [slide_list([(99, 256, b"")]),
                                  slide_list([(3, 900, b"")], 1),
                                  slide_list([(4, 700, b"")], 2)])
    resolved = resolve_presentation(data, current, [])
    assert resolved.slides[0].recovery_record is not None
    assert (resolved.slides[0].master_id, resolved.slides[0].notes_id, resolved.slides[0].flags) == (900, 700, 5)
    from dochan.office_binary.ppt import parse_ppt_document_stream
    doc = parse_ppt_document_stream(data, current_user=current)
    assert [p.text for p in doc.find_all("paragraph")] == ["Master caption", "Recovered", "Speaker note"]
