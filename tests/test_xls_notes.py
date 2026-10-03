"""BIFF8 NOTE, Obj and TxO comment text fixtures."""
import struct

from dochan.office_binary.xls import parse_biff_workbook


def _record(kind, data=b""):
    return struct.pack("<HH", kind, len(data)) + data


def _workbook(sheet):
    name = b"Notes"
    bound = _record(0x0085, struct.pack("<IHBB", 0, 0, len(name), 0) + name)
    offset = len(_record(0x0809, struct.pack("<HH", 0x0600, 0x0005))) + len(bound)
    bound = _record(0x0085, struct.pack("<IHBB", offset, 0, len(name), 0) + name)
    return _record(0x0809, struct.pack("<HH", 0x0600, 0x0005)) + bound + sheet


def _note(row, col, obj_id, author, hidden=False):
    raw = author.encode("latin1")
    return _record(0x001C, struct.pack("<HHHHHB", row, col, 0 if hidden else 2,
                                      obj_id, len(raw), 0) + raw)


def _obj(obj_id):
    return _record(0x005D, struct.pack("<HHHHH", 0x0015, 18, 0x0019, obj_id, 0)
                   + b"\0" * 12)


def _txo(char_count, *segments):
    header = b"\0" * 10 + struct.pack("<HH", char_count, 0) + b"\0" * 4
    return _record(0x01B6, header) + b"".join(_record(0x003C, segment) for segment in segments)


def _texts(doc):
    table = doc.sections[0].elements[0]
    return [cell.text for row in table.rows for cell in row]


def test_xls_notes_join_obj_txo_and_note_by_id_with_mixed_continue_encodings():
    body = "Reviewer:\nfirst cell"
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(7) + _record(0x00EC) + _txo(len(body), b"\0Reviewer:\n",
                                                b"\1" + "first cell".encode("utf-16-le"))
             + _obj(8) + _txo(6, b"\0second")
             + _note(0, 0, 8, "Other")
             + _note(1, 0, 7, "Reviewer", hidden=True)
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    # 메모 줄바꿈은 XLSX 메모 모델처럼 \n 으로 보존한다(Markdown 표는 렌더러가 공백으로 바꾼다).
    assert _texts(doc) == ["[comment: Other: second]", "[comment: Reviewer: Reviewer:\nfirst cell]"]
    assert doc.errors == []


def test_xls_notes_ignore_unmatched_and_empty_text_without_warning():
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(9) + _txo(0)
             + _note(0, 0, 9, "Author")
             + _note(1, 0, 10, "Alone")
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    assert _texts(doc) == ["[comment: Author]", "[comment: Alone]"]
    assert doc.errors == []


def test_xls_notes_keep_body_when_author_is_empty():
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(11) + _txo(4, b"\0Text")
             + _note(0, 0, 11, "")
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    assert _texts(doc) == ["[comment: Text]"]
    assert doc.errors == []


def test_xls_notes_warn_and_keep_author_on_truncated_or_oversize_text():
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(1) + _txo(10, b"\0short") + _note(0, 0, 1, "A")
             + _obj(2) + _txo(0xFFFF, b"\0ignored") + _note(1, 0, 2, "B")
             + _record(0x000A))
    doc = parse_biff_workbook(_workbook(sheet))
    assert _texts(doc) == ["[comment: A]", "[comment: B]"]
    assert any("TxO" in error for error in doc.errors)



def test_xls_note_surrogate_pair_split_across_continues_is_kept():
    wide = "😀".encode("utf-16-le")
    sheet = (_record(0x0809, struct.pack("<HH", 0x0600, 0x0010))
             + _obj(7) + _txo(3, b"\0a", b"\1" + wide[:2], b"\1" + wide[2:])
             + _note(0, 0, 7, "Me") + _record(0x000A))
    assert _texts(parse_biff_workbook(_workbook(sheet))) == ["[comment: Me: a😀]"]


def test_xls_note_count_has_no_separate_cap():
    notes = b"".join(_note(row, 0, 0, "A") for row in range(10005))
    sheet = _record(0x0809, struct.pack("<HH", 0x0600, 0x0010)) + notes + _record(0x000A)
    doc = parse_biff_workbook(_workbook(sheet))
    assert sum(1 for text in _texts(doc) if text.startswith("[comment:")) == 10005
    assert not any("note count limit" in error for error in doc.errors)
