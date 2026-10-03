"""XLS parity regressions using synthetic BIFF and OLE property bytes."""
import struct

from dochan.office_binary import xls
from dochan.conversion import Provenance
from dochan.model.document import Document, Section
from dochan.model.document import Paragraph, TextRun
from dochan.output.markdown import to_markdown
from test_xls_reader import (
    _blank, _bof, _boundsheet, _dimension, _eof, _label,
    _mulblank, _name_record, _number, _record, _row_record, _colinfo,
)


def _workbook(globals_part, sheet_part):
    offset = len(globals_part) + len(_boundsheet(0, "Sheet1"))
    return globals_part + _boundsheet(offset, "Sheet1") + sheet_part


def _table(doc):
    return next(element for element in doc.sections[0].elements
                if hasattr(element, "rows"))


def test_xls_trims_only_trailing_empty_rows_and_columns():
    sheet = (_bof() + _dimension(0, 5, 0, 5)
             + _label(0, 0, "left") + _blank(0, 1)
             + _number(1, 2, 3) + _mulblank(2, 0, 4)
             + _row_record(4) + _colinfo(4, 4) + _eof())
    doc = xls.parse_biff_workbook(_workbook(_bof(), sheet))
    table = _table(doc)
    assert (table.row_count, table.col_count) == (2, 3)
    assert table.rows[0][1].text == ""
    assert table.rows[1][2].text == "3"


def test_xls_hidden_names_are_output_like_xlsx_but_xlfn_placeholders_are_not():
    visible = _name_record("Visible", b"\x1e\x01\x00")
    hidden = bytearray(_name_record("Hidden", b"\x1e\x02\x00"))
    struct.pack_into("<H", hidden, 4, 0x0001)
    future = _name_record("_xlfn.COUNTIFS", b"\x1e\x03\x00")
    globals_part = _bof() + visible + bytes(hidden) + future
    doc = xls.parse_biff_workbook(_workbook(globals_part, _bof() + _eof()))
    text = [element.text for element in doc.sections[0].elements]
    assert text == ["Defined name: Visible = 1", "Defined name: Hidden = 2"]


def test_xls_array_formula_follower_uses_only_cached_value():
    anchor = _record(0x0006, struct.pack("<HHH", 0, 1, 0)
                     + b"\0\0\0\0\0\0\xff\xff"
                     + b"\0\0\0\0\0\0" + struct.pack("<H", 5)
                     + b"\x01\x00\x00\x01\x00")
    array = _record(0x0221, struct.pack("<HHBB", 0, 1, 1, 1)
                    + b"\0" * 6 + struct.pack("<H", 5)
                    + b"\x44\x00\x00\x00\xc0")
    follower = _record(0x0006, struct.pack("<HHH", 1, 1, 0)
                       + b"\0\0\0\0\0\0\xff\xff"
                       + b"\0\0\0\0\0\0" + struct.pack("<H", 5)
                       + b"\x01\x00\x00\x01\x00")
    sheet = (_bof() + _label(0, 0, "one") + anchor + array
             + _record(0x0207, b"\x03\x00\x00one")
             + _label(1, 0, "two") + follower
             + _record(0x0207, b"\x03\x00\x00one") + _eof())
    doc = xls.parse_biff_workbook(_workbook(_bof(), sheet))
    table = _table(doc)
    assert table.rows[0][1].text == "one (=A1)"
    assert table.rows[1][1].text == "one"


def _summary_stream(title, author):
    values = []
    entries = []
    for identifier, text in ((2, title), (4, author)):
        encoded = (text + "\0").encode("utf-16-le")
        entries.append((identifier, 8 + 2 * 8 + sum(map(len, values))))
        values.append(struct.pack("<II", 31, len(text) + 1) + encoded)
    section = (struct.pack("<II", 8 + 2 * 8 + sum(map(len, values)), 2)
               + b"".join(struct.pack("<II", *entry) for entry in entries)
               + b"".join(values))
    return (b"\xfe\xff\x00\x00" + b"\0" * 20
            + struct.pack("<I", 1) + bytes.fromhex("e0859ff2f94f6810ab9108002b27b3d9")
            + struct.pack("<I", 48) + section)


def test_xls_summary_information_reads_title_and_author_safely():
    assert xls._parse_summary_information(_summary_stream("Budget", "Alice")) == {
        "title": "Budget", "creator": "Alice"}
    assert xls._parse_summary_information(_summary_stream("Budget", "Alice")[:-3]) == {}


def test_xls_summary_information_rejects_wrong_fmtid():
    valid = _summary_stream("Budget", "Alice")
    assert xls._parse_summary_information(valid[:28] + b"\0" * 16 + valid[44:]) == {}


def test_xls_unknown_codepage_keeps_existing_warning_policy():
    valid = _summary_stream("Budget", "Alice")
    # Insert a code-page property with an unknown ID while retaining valid values.
    section = valid[48:]
    count = struct.unpack_from("<I", section, 4)[0]
    assert count == 2
    first = struct.unpack_from("<I", section, 12)[0]
    second = struct.unpack_from("<I", section, 20)[0]
    values = section[first:]
    cp_value = struct.pack("<IH", 2, 0) + b"\0\0"
    table = (struct.pack("<II", 1, 32)
             + struct.pack("<II", 2, 40)
             + struct.pack("<II", 4, 40 + second - first))
    rebuilt = valid[:48] + struct.pack("<II", 40 + len(values), 3) + table + cp_value + values
    errors = []
    assert xls._parse_summary_information(rebuilt, errors) == {
        "title": "Budget", "creator": "Alice"}
    assert errors == []


def test_xls_summary_preamble_precedes_meaningful_sheet_heading():
    elements = xls._summary_elements({"title": "Budget", "creator": "Alice"})
    elements.append(Paragraph(runs=[TextRun("Defined name: Sales = Data!$A$1")],
                              provenance=Provenance(source_format="xls", path="Workbook")))
    section = Section(elements=elements,
                      provenance=Provenance(source_format="xls", sheet="Data"))
    doc = Document(sections=[section], source_format="xls")
    assert to_markdown(doc) == ("# Budget\n\nAuthor: Alice\n\n"
                                "Defined name: Sales = Data!$A$1\n\n## Data")
