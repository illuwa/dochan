"""BIFF8 Obj/TxO drawing text and OfficeArt anchor fixtures."""
import struct
from unittest.mock import patch

from dochan.office_binary.xls import parse_biff_workbook
from dochan.model.document import Paragraph
from dochan.output.markdown import to_markdown


def _record(kind, data=b""):
    return struct.pack("<HH", kind, len(data)) + data


def _art(kind, data=b"", version=0, instance=0):
    return struct.pack("<HHI", instance << 4 | version, kind, len(data)) + data


def _shape(spid, row, col):
    return _art(0xF004,
                _art(0xF00A, struct.pack("<II", spid, 0xa00), version=2, instance=1)
                + _art(0xF010, struct.pack("<9H", 0, col, 0, row, 0,
                                          col + 1, 0, row + 1, 0))
                + _art(0xF011) + _art(0xF00D), version=15)


def _shape_anchor(spid, row, col, dx=0, dy=0, client_data=True):
    return _art(0xF004,
                _art(0xF00A, struct.pack("<II", spid, 0xa00), version=2, instance=1)
                + _art(0xF010, struct.pack("<9H", 0, col, dx, row, dy,
                                          col + 1, 0, row + 1, 0))
                + (_art(0xF011) if client_data else b""), version=15)


def _obj(object_type, object_id):
    return _record(0x005D, struct.pack("<HHHHH", 0x0015, 18,
                                      object_type, object_id, 0) + b"\0" * 12)


def _txo(text):
    header = b"\0" * 10 + struct.pack("<HH", len(text), 0) + b"\0" * 4
    return _record(0x01B6, header) + _record(0x003C, b"\0" + text.encode("latin1"))


def _workbook(sheet):
    name = b"Drawing"
    bof = _record(0x0809, struct.pack("<HH", 0x0600, 0x0005))
    bound = _record(0x0085, struct.pack("<IHBB", 0, 0, len(name), 0) + name)
    offset = len(bof) + len(bound)
    bound = _record(0x0085, struct.pack("<IHBB", offset, 0, len(name), 0) + name)
    return bof + bound + sheet


def _sheet(*parts):
    return (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
            + b"".join(parts) + _record(0x000A))


def _paragraphs(doc):
    return [e for e in doc.sections[0].elements if isinstance(e, Paragraph)]


def test_xls_textbox_uses_drawing_anchor_order_and_paragraph_contract():
    drawing = _art(0xF000, _shape(1025, 8, 3) + _shape(1026, 2, 1), version=15)
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _record(0x00EC, drawing)
             + _obj(6, 1) + _txo("Later")
             + _obj(30, 2) + _txo("Earlier")
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    paragraphs = [e for e in doc.sections[0].elements if isinstance(e, Paragraph)]
    assert [p.text for p in paragraphs] == ["Earlier", "Later"]
    assert [p.provenance.sheet for p in paragraphs] == ["Drawing", "Drawing"]
    assert to_markdown(doc) == "## Drawing\n\nEarlier\n\nLater"
    assert doc.errors == []


def test_xls_txo_note_is_only_a_comment_and_unanchored_text_keeps_record_order():
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(25, 1) + _txo("Note body")
             + _obj(6, 2) + _txo("Button text")
             + _obj(30, 3) + _txo("Shape text")
             + _record(0x001C, struct.pack("<HHHHHB", 0, 0, 2, 1, 1, 0) + b"A")
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    paragraphs = [e.text for e in doc.sections[0].elements if isinstance(e, Paragraph)]
    assert paragraphs == ["Button text", "Shape text"]
    assert "[comment: A: Note body]" in to_markdown(doc)
    assert doc.errors == []


def test_xls_textbox_preserves_line_breaks_without_changing_note_format():
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(6, 1) + _txo("First\rSecond")
             + _obj(25, 2) + _txo("Note\rbody")
             + _record(0x001C, struct.pack("<HHHHHB", 0, 0, 2, 2, 1, 0) + b"A")
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    paragraphs = [e.text for e in doc.sections[0].elements if isinstance(e, Paragraph)]
    assert paragraphs == ["First\nSecond"]
    assert "[comment: A: Note body]" in to_markdown(doc)


def test_xls_note_after_non_note_object_limit_is_retained():
    objects = b"".join(_obj(8, i + 1) for i in range(10001))
    note = _record(0x001C, struct.pack("<HHHHHB", 0, 0, 2, 20000, 1, 0) + b"A")
    doc = parse_biff_workbook(_workbook(_sheet(objects, _obj(25, 20000), _txo("late note"), note)))
    assert "[comment: A: late note]" in to_markdown(doc)


def test_xls_note_text_budget_is_separate_from_drawing_text():
    note = _record(0x001C, struct.pack("<HHHHHB", 0, 0, 2, 2, 1, 0) + b"A")
    with patch("dochan.office_binary.xls.MAX_SHEET_NOTE_CHARS", 10):
        doc = parse_biff_workbook(_workbook(_sheet(
            _obj(6, 1), _txo("0123456789"),
            _obj(25, 2), _txo("Note"), note)))
    assert "[comment: A: Note]" in to_markdown(doc)


def test_xls_form_controls_are_not_drawing_paragraphs_but_keep_anchor_alignment():
    drawing = _art(0xF000, _shape(1025, 1, 1) + _shape(1026, 9, 1)
                   + _shape(1027, 3, 1), version=15)
    doc = parse_biff_workbook(_workbook(_sheet(
        _record(0x00EC, drawing), _obj(0x07, 1), _txo("Button"),
        _obj(0x06, 2), _txo("Later"), _obj(0x0C, 3), _txo("Option"),
        _obj(0x1E, 4), _txo("Unanchored"))))
    assert [p.text for p in _paragraphs(doc)] == ["Later", "Unanchored"]


def test_xls_textbox_normalizes_lines_like_xlsx_and_note_keeps_them():
    note = _record(0x001C, struct.pack("<HHHHHB", 0, 0, 2, 2, 1, 0) + b"A")
    doc = parse_biff_workbook(_workbook(_sheet(
        _obj(6, 1), _txo("  First  \r\n \r Last  "),
        _obj(25, 2), _txo("  Note  \r\n \r body  "), note)))
    assert [p.text for p in _paragraphs(doc)] == ["First\nLast"]
    assert doc.sections[0].elements[0].rows[0][0].text == "[comment: A: Note  \n \n body]"


def test_xls_anchor_with_invalid_offset_keeps_valid_cell_and_warns():
    drawing = _art(0xF000, _shape_anchor(1025, 9, 1, dy=296)
                   + _shape_anchor(1026, 3, 1), version=15)
    doc = parse_biff_workbook(_workbook(_sheet(
        _record(0x00EC, drawing), _obj(6, 1), _txo("Later"),
        _obj(6, 2), _txo("Earlier"))))
    assert [p.text for p in _paragraphs(doc)] == ["Earlier", "Later"]
    assert _paragraphs(doc)[1].provenance.cell == "B10"
    assert any("anchor out of bounds" in e for e in doc.errors)


def test_xls_partial_client_data_mismatch_keeps_known_anchors():
    first = _shape_anchor(1025, 8, 1)
    drawing = _art(0xF000, first + _shape_anchor(1026, 2, 1), version=15)
    boundary = 8 + len(first)
    doc = parse_biff_workbook(_workbook(_sheet(
        _record(0x00EC, drawing[:boundary]), _obj(6, 1), _txo("Later"),
        _record(0x00EC, drawing[boundary:]), _obj(6, 2), _txo("Earlier"),
        _obj(6, 3), _txo("Unanchored"))))
    assert [p.text for p in _paragraphs(doc)] == ["Earlier", "Later", "Unanchored"]
    assert [p.provenance.cell for p in _paragraphs(doc)] == ["B3", "B9", None]


def test_xls_unpaired_client_data_does_not_shift_later_anchors():
    # Excel writes each shape in its own MsoDrawing followed by its Obj. A
    # damaged first Obj (no ftCmo) leaves its ClientData unpaired; later Obj
    # records must still take the ClientData that ends right before them.
    rows = [5, 10, 15, 20]
    parts = [_shape(1025 + i, row, 1) for i, row in enumerate(rows)]
    group = _art(0xF004, _art(0xF00A, struct.pack("<II", 1024, 5), version=2), version=15)
    size = len(group) + sum(len(part) for part in parts)
    container = struct.pack("<HHI", 15, 0xF003, size)
    head = struct.pack("<HHI", 15, 0xF002, len(container) + size)
    damaged = _record(0x005D, struct.pack("<HHHH", 0x0099, 18, 6, 1) + b"\0" * 14)
    body = [_record(0x00EC, head + container + group + parts[0]), damaged, _txo("lost")]
    for index, row in enumerate(rows[1:], start=1):
        body += [_record(0x00EC, parts[index]), _obj(6, index + 1), _txo("row%d" % (row + 1))]
    doc = parse_biff_workbook(_workbook(_sheet(*body)))
    cells = {p.text: p.provenance.cell for p in _paragraphs(doc)}
    assert cells["row11"] == "B11"
    assert cells["row16"] == "B16"
    assert cells["row21"] == "B21"


def test_xls_drawing_failure_keeps_decoded_text():
    with patch("dochan.office_binary.xls.XlsDrawingReader", side_effect=ValueError("broken")):
        doc = parse_biff_workbook(_workbook(_sheet(_obj(6, 1), _txo("Kept"))))
    assert [p.text for p in _paragraphs(doc)] == ["Kept"]
    assert any("drawing initialization failed" in e for e in doc.errors)


def test_xls_sheet_drawing_failure_keeps_decoded_text():
    with patch("dochan.office_binary.xls.XlsDrawingReader.read_sheet", side_effect=ValueError("broken")):
        doc = parse_biff_workbook(_workbook(_sheet(_obj(6, 1), _txo("Kept"))))
    assert [p.text for p in _paragraphs(doc)] == ["Kept"]
    assert any("drawing parsing failed" in e for e in doc.errors)


def test_xls_group_child_inherits_parent_anchor():
    parent = _art(0xF004,
                  _art(0xF00A, struct.pack("<II", 1025, 1), version=2, instance=1)
                  + _art(0xF010, struct.pack("<9H", 0, 2, 0, 4, 0, 3, 0, 5, 0)),
                  version=15)
    # A grouped child without its own client anchor inherits the group anchor.
    child = _art(0xF004,
                 _art(0xF00A, struct.pack("<II", 1026, 2), version=2, instance=1)
                 + _art(0xF011), version=15)
    group = _art(0xF003, parent + child, version=15)
    doc = parse_biff_workbook(_workbook(_sheet(_record(0x00EC, _art(0xF000, group, version=15)),
                                           _obj(6, 1), _txo("Grouped"))))
    assert _paragraphs(doc)[0].provenance.cell == "C5"


def test_xls_chart_substream_object_text_is_excluded():
    chart = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0020))
             + _obj(6, 1) + _txo("Chart") + _record(0x000A))
    doc = parse_biff_workbook(_workbook(_sheet(chart, _obj(6, 2), _txo("Sheet"))))
    assert [p.text for p in _paragraphs(doc)] == ["Sheet"]


def test_xls_textbox_utf16_across_multiple_continues():
    text = "가나다😀"
    wide = text.encode("utf-16-le")
    header = b"\0" * 10 + struct.pack("<HH", len(wide) // 2, 0) + b"\0" * 4
    txo = (_record(0x01B6, header) + _record(0x003C, b"\1" + wide[:4])
           + _record(0x003C, b"\1" + wide[4:8])
           + _record(0x003C, b"\1" + wide[8:]))
    doc = parse_biff_workbook(_workbook(_sheet(_obj(6, 1), txo)))
    assert [p.text for p in _paragraphs(doc)] == [text]


def test_xls_same_object_id_as_note_does_not_drop_shape_text():
    note = _record(0x001C, struct.pack("<HHHHHB", 0, 0, 2, 1, 1, 0) + b"A")
    doc = parse_biff_workbook(_workbook(_sheet(_obj(25, 1), _txo("Note"),
                                           _obj(6, 1), _txo("Shape"), note)))
    assert [p.text for p in _paragraphs(doc)] == ["Shape"]
    assert "[comment: A: Note]" in to_markdown(doc)
