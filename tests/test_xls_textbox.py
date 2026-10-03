"""BIFF8 Obj/TxO drawing text and OfficeArt anchor fixtures."""
import struct

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
