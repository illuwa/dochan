import struct

from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import _cmd_info
from dochan.office_binary.xls import XLSReader, parse_biff_workbook
from dochan.output.markdown import to_markdown


def _record(record_type, data=b""):
    return struct.pack("<HH", record_type, len(data)) + data


def _xl_unicode(text):
    encoded = text.encode("latin1")
    return struct.pack("<HB", len(text), 0) + encoded


def _xl_unicode_rich(text, run_count=1):
    encoded = text.encode("latin1")
    formatting_runs = b"".join(struct.pack("<HH", 0, 0) for _ in range(run_count))
    return struct.pack("<HBH", len(text), 0x08, run_count) + encoded + formatting_runs


def _bof():
    return _record(0x0809, b"\x00" * 8)


def _boundsheet(offset, name):
    return _record(0x0085, struct.pack("<IBBBB", offset, 0, 0, len(name), 0) + name.encode("latin1"))


def _boundsheet_with_flags(offset, name, flags):
    name_bytes = name.encode("latin1")
    return _record(0x0085, struct.pack("<I", offset) + struct.pack("<H", flags) + struct.pack("<BB", len(name), 0) + name_bytes)


def _externsheet(entries):
    body = struct.pack("<H", len(entries))
    for supbook_index, first_sheet, last_sheet in entries:
        body += struct.pack("<HHH", supbook_index, first_sheet, last_sheet)
    return _record(0x0017, body)


def _name_record(name, formula_tokens=b""):
    encoded = name.encode("latin1")
    body = (
        struct.pack("<HBBHHHBBBB", 0, 0, len(encoded), len(formula_tokens), 0, 0, 0, 0, 0, 0)
        + bytes([0])
        + encoded
        + formula_tokens
    )
    return _record(0x0018, body)


def _sst(strings):
    body = struct.pack("<II", len(strings), len(strings))
    for text in strings:
        body += _xl_unicode(text)
    return _record(0x00FC, body)


def _sst_raw(strings):
    body = struct.pack("<II", len(strings), len(strings))
    for payload in strings:
        body += payload
    return _record(0x00FC, body)


def _continue(data):
    return _record(0x003C, data)


def _format_record(index, text):
    encoded = text.encode("latin1")
    return _record(0x041E, struct.pack("<H", index) + struct.pack("<HB", len(encoded), 0) + encoded)


def _xf(format_index):
    return _record(0x00E0, struct.pack("<HH", 0, format_index) + b"\x00" * 16)


def _labelsst(row, col, sst_index):
    return _record(0x00FD, struct.pack("<HHHI", row, col, 0, sst_index))


def _label(row, col, text):
    encoded = text.encode("latin1")
    return _record(0x0204, struct.pack("<HHH", row, col, 0) + struct.pack("<H", len(encoded)) + encoded)


def _old_label(row, col, text):
    encoded = text.encode("latin1")
    return _record(0x0004, struct.pack("<HHH", row, col, 0) + bytes([len(encoded)]) + encoded)


def _label_unicode(row, col, text):
    encoded = text.encode("utf-16-le")
    return _record(0x0204, struct.pack("<HHH", row, col, 0) + struct.pack("<HB", len(text), 1) + encoded)


def _rstring(row, col, text, run_count=1):
    encoded = text.encode("latin1")
    formatting_runs = b"".join(struct.pack("<HH", 0, 0) for _ in range(run_count))
    return (
        _record(
            0x00D6,
            struct.pack("<HHH", row, col, 0)
            + struct.pack("<HB", len(text), 0)
            + encoded
            + struct.pack("<H", run_count)
            + formatting_runs,
        )
    )


def _header(text):
    return _record(0x0014, _xl_unicode(text))


def _footer(text):
    return _record(0x0015, _xl_unicode(text))


def _blank(row, col):
    return _record(0x0201, struct.pack("<HHH", row, col, 0))


def _old_blank(row, col):
    return _record(0x0001, struct.pack("<HHH", row, col, 0))


def _mulblank(row, first_col, last_col):
    body = struct.pack("<HH", row, first_col)
    for _ in range(first_col, last_col + 1):
        body += struct.pack("<H", 0)
    body += struct.pack("<H", last_col)
    return _record(0x00BE, body)


def _row_record(row):
    return _record(0x0208, struct.pack("<HHHHHH", row, 0, 0, 0, 0, 0) + b"\x00" * 4)


def _colinfo(first_col, last_col):
    return _record(0x007D, struct.pack("<HHHHH", first_col, last_col, 0, 0, 0) + b"\x00\x00")


def _dimension(first_row, last_row_exclusive, first_col, last_col_exclusive):
    return _record(0x0200, struct.pack("<IIHHH", first_row, last_row_exclusive, first_col, last_col_exclusive, 0))


def _number(row, col, value):
    return _record(0x0203, struct.pack("<HHHd", row, col, 0, value))


def _old_number(row, col, value):
    return _record(0x0003, struct.pack("<HHHd", row, col, 0, value))


def _integer(row, col, value):
    return _record(0x0002, struct.pack("<HHHH", row, col, 0, value))


def _rk(row, col, value):
    return _record(0x027E, struct.pack("<HHHI", row, col, 0, _rk_int(value)))


def _mulrk(row, first_col, values):
    body = struct.pack("<HH", row, first_col)
    for value in values:
        body += struct.pack("<HI", 0, _rk_int(value))
    body += struct.pack("<H", first_col + len(values) - 1)
    return _record(0x00BD, body)


def _rk_int(value):
    return (int(value) << 2) | 0x02


def _styled_number(row, col, xf_index, value):
    return _record(0x0203, struct.pack("<HHHd", row, col, xf_index, value))


def _boolerr(row, col, value, is_error=False):
    return _record(0x0205, struct.pack("<HHHBB", row, col, 0, value, 1 if is_error else 0))


def _old_boolerr(row, col, value, is_error=False):
    return _record(0x0005, struct.pack("<HHHBB", row, col, 0, value, 1 if is_error else 0))


def _formula(row, col, value):
    return _record(0x0006, struct.pack("<HHHdH", row, col, 0, value, 0) + b"\x00\x00")


def _formula_with_tokens(row, col, value, tokens):
    payload = struct.pack("<HHHdHIH", row, col, 0, value, 0, 0, len(tokens)) + tokens
    return _record(0x0006, payload)


def _formula_bool_with_tokens(row, col, value, tokens):
    cached = bytes([0x01, 0x00, 1 if value else 0, 0x00, 0x00, 0x00, 0xFF, 0xFF])
    payload = struct.pack("<HHH", row, col, 0) + cached + struct.pack("<HIH", 0, 0, len(tokens)) + tokens
    return _record(0x0006, payload)


def _formula_error_with_tokens(row, col, error_code, tokens):
    cached = bytes([0x02, 0x00, error_code, 0x00, 0x00, 0x00, 0xFF, 0xFF])
    payload = struct.pack("<HHH", row, col, 0) + cached + struct.pack("<HIH", 0, 0, len(tokens)) + tokens
    return _record(0x0006, payload)


def _formula_blank_with_tokens(row, col, tokens):
    cached = bytes([0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF])
    payload = struct.pack("<HHH", row, col, 0) + cached + struct.pack("<HIH", 0, 0, len(tokens)) + tokens
    return _record(0x0006, payload)


def _formula_string(text):
    return _record(0x0207, _xl_unicode(text))


def _old_formula_string(text):
    return _record(0x0007, _xl_unicode(text))


def _old_formula_byte_string(text):
    encoded = text.encode("latin1")
    return _record(0x0007, bytes([len(encoded)]) + encoded)


def _ptg_ref(row, col):
    return bytes([0x24]) + struct.pack("<HH", row, col | 0xC000)


def _ptg_ref_v(row, col):
    return bytes([0x44]) + struct.pack("<HH", row, col | 0xC000)


def _ptg_ref_flags(row, col, row_relative=True, col_relative=True):
    flags = (0x8000 if row_relative else 0) | (0x4000 if col_relative else 0)
    return bytes([0x24]) + struct.pack("<HH", row, col | flags)


def _ptg_ref3d(xti_index, row, col):
    return bytes([0x3A]) + struct.pack("<HHH", xti_index, row, col | 0xC000)


def _ptg_area3d(xti_index, first_row, last_row, first_col, last_col):
    return bytes([0x3B]) + struct.pack("<HHHHH", xti_index, first_row, last_row, first_col | 0xC000, last_col | 0xC000)


def _ptg_name(name_index):
    return bytes([0x23]) + struct.pack("<HH", name_index, 0)


def _ptg_add():
    return bytes([0x03])


def _ptg_mul():
    return bytes([0x05])


def _ptg_power():
    return bytes([0x07])


def _ptg_concat():
    return bytes([0x08])


def _ptg_gt():
    return bytes([0x0D])


def _ptg_str(text):
    encoded = text.encode("latin1")
    return bytes([0x17, len(text), 0]) + encoded


def _ptg_bool(value):
    return bytes([0x1D, 1 if value else 0])


def _ptg_err(error_code):
    return bytes([0x1C, error_code])


def _ptg_ne():
    return bytes([0x0E])


def _ptg_uminus():
    return bytes([0x13])


def _ptg_percent():
    return bytes([0x14])


def _ptg_paren():
    return bytes([0x15])


def _ptg_exp(row, col):
    return bytes([0x01]) + struct.pack("<HH", row, col)


def _ptg_int(value):
    return bytes([0x1E]) + struct.pack("<H", value)


def _ptg_num(value):
    return bytes([0x1F]) + struct.pack("<d", value)


def _ptg_area(first_row, last_row, first_col, last_col):
    return bytes([0x25]) + struct.pack("<HHHH", first_row, last_row, first_col | 0xC000, last_col | 0xC000)


def _ptg_area_v(first_row, last_row, first_col, last_col):
    return bytes([0x45]) + struct.pack("<HHHH", first_row, last_row, first_col | 0xC000, last_col | 0xC000)


def _ptg_area_flags(first_row, last_row, first_col, last_col, row_relative=True, col_relative=True):
    flags = (0x8000 if row_relative else 0) | (0x4000 if col_relative else 0)
    return bytes([0x25]) + struct.pack("<HHHH", first_row, last_row, first_col | flags, last_col | flags)


def _ptg_func_var(argument_count, function_index):
    return bytes([0x22, argument_count]) + struct.pack("<H", function_index)


def _ptg_func_var_v(argument_count, function_index):
    return bytes([0x42, argument_count]) + struct.pack("<H", function_index)


def _ptg_func(function_index):
    return bytes([0x21]) + struct.pack("<H", function_index)


def _shrfmla(first_row, last_row, first_col, last_col, tokens):
    return _record(0x04BC, struct.pack("<HHHHH", first_row, last_row, first_col, last_col, len(tokens)) + tokens)


def _merged_cells(ranges):
    body = struct.pack("<H", len(ranges))
    for first_row, last_row, first_col, last_col in ranges:
        body += struct.pack("<HHHH", first_row, last_row, first_col, last_col)
    return _record(0x00E5, body)


def _hlink(first_row, last_row, first_col, last_col, url):
    return _record(
        0x01B8,
        struct.pack("<HHHH", first_row, last_row, first_col, last_col)
        + b"\x00" * 24
        + url.encode("utf-16-le")
        + b"\x00\x00",
    )


def _note(row, col, author):
    encoded = author.encode("latin1")
    return _record(0x001C, struct.pack("<HHHHHB", row, col, 0, 1, len(author), 0) + encoded)


def _eof():
    return _record(0x000A)


def _minimal_biff_workbook():
    globals_part = _bof()
    worksheet = _bof() + _labelsst(0, 0, 0) + _labelsst(0, 1, 1) + _labelsst(1, 0, 2) + _number(1, 1, 10) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Sheet1")) + len(_sst(["Name", "Value", "A"]))
    return globals_part + _boundsheet(offset, "Sheet1") + _sst(["Name", "Value", "A"]) + worksheet


def test_parse_biff_workbook_reads_labels_and_numbers():
    doc = parse_biff_workbook(_minimal_biff_workbook())
    table = doc.sections[0].elements[0]

    assert doc.source_format == "xls"
    assert doc.sections[0].provenance.sheet == "Sheet1"
    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[0][0].text == "Name"
    assert table.rows[0][1].text == "Value"
    assert table.rows[1][0].text == "A"
    assert table.rows[1][1].text == "10"
    assert table.rows[1][1].provenance.cell == "B2"
    assert table.rows[0][0].row == 0
    assert table.rows[0][0].col == 0
    assert table.rows[0][1].row == 0
    assert table.rows[0][1].col == 1
    assert table.rows[1][1].row == 1
    assert table.rows[1][1].col == 1


def test_parse_biff_workbook_tracks_sheet_and_cell_provenance_paths():
    doc = parse_biff_workbook(_minimal_biff_workbook(), "LegacyWorkbook")
    table = doc.sections[0].elements[0]

    assert doc.sections[0].provenance.path == "LegacyWorkbook#Sheet1"
    assert doc.sections[0].provenance.sheet == "Sheet1"
    assert table.rows[0][0].provenance.path == "LegacyWorkbook#Sheet1"
    assert table.rows[1][1].provenance.path == "LegacyWorkbook#Sheet1"
    assert table.rows[0][0].provenance.sheet == "Sheet1"
    assert table.rows[1][1].provenance.sheet == "Sheet1"
    assert table.rows[0][0].paragraphs[0].runs[0].provenance.path == "LegacyWorkbook#Sheet1"
    assert table.rows[0][0].paragraphs[0].runs[0].provenance.cell == "A1"


def test_parse_biff_workbook_tracks_defined_name_provenance_path():
    globals_part = _bof() + _externsheet([(0, 0, 0)]) + _name_record("SalesRange", _ptg_area3d(0, 1, 2, 0, 0))
    worksheet = (
        _bof()
        + _label(0, 0, "Metric")
        + _number(1, 0, 10)
        + _number(2, 0, 20)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Summary"))
    workbook = globals_part + _boundsheet(offset, "Summary") + worksheet

    doc = parse_biff_workbook(workbook, "Book")

    assert doc.sections[0].provenance.path == "Book#Summary"
    assert doc.sections[0].elements[0].text == "Defined name: SalesRange = Summary!A2:A3"
    assert doc.sections[0].elements[0].provenance.path == "Book"
    assert doc.sections[0].elements[0].runs[0].provenance.path == "Book"
    assert doc.sections[0].elements[1].rows[0][0].provenance.path == "Book#Summary"


def test_parse_biff_workbook_reads_rich_text_shared_strings_without_offset_drift():
    globals_part = _bof()
    worksheet = _bof() + _labelsst(0, 0, 0) + _labelsst(0, 1, 1) + _labelsst(1, 0, 2) + _eof()
    sst = _sst_raw([_xl_unicode_rich("Name"), _xl_unicode("Value"), _xl_unicode("A")])
    offset = len(globals_part) + len(_boundsheet(0, "Rich")) + len(sst)
    workbook = globals_part + _boundsheet(offset, "Rich") + sst + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert [cell.text for cell in table.rows[0]] == ["Name", "Value"]
    assert table.rows[1][0].text == "A"


def test_parse_biff_workbook_reads_rstring_rich_text_labels():
    globals_part = _bof()
    worksheet = _bof() + _label(0, 0, "Name") + _rstring(1, 0, "Rich Label") + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "RichText"))
    workbook = globals_part + _boundsheet(offset, "RichText") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "Rich Label"


def test_parse_biff_workbook_reads_older_biff_label_records():
    globals_part = _bof()
    worksheet = _bof() + _old_label(0, 0, "Legacy") + _old_label(1, 0, "BIFF") + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "OldLabel"))
    workbook = globals_part + _boundsheet(offset, "OldLabel") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[0][0].text == "Legacy"
    assert table.rows[1][0].text == "BIFF"


def test_parse_biff_workbook_reads_sst_continue_records():
    globals_part = _bof()
    worksheet = _bof() + _labelsst(0, 0, 0) + _labelsst(0, 1, 1) + _labelsst(1, 0, 2) + _eof()
    sst_prefix = _record(0x00FC, struct.pack("<II", 3, 3) + _xl_unicode("Name"))
    sst_tail = _continue(_xl_unicode("Value") + _xl_unicode("A"))
    offset = len(globals_part) + len(_boundsheet(0, "Continue")) + len(sst_prefix) + len(sst_tail)
    workbook = globals_part + _boundsheet(offset, "Continue") + sst_prefix + sst_tail + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert [cell.text for cell in table.rows[0]] == ["Name", "Value"]
    assert table.rows[1][0].text == "A"


def test_parse_biff_workbook_reads_sst_continue_split_inside_string_data():
    globals_part = _bof()
    worksheet = _bof() + _labelsst(0, 0, 0) + _eof()
    sst_prefix = _record(0x00FC, struct.pack("<II", 1, 1) + struct.pack("<HB", 9, 0) + b"Long")
    sst_tail = _continue(b"\x00Value")
    offset = len(globals_part) + len(_boundsheet(0, "Split")) + len(sst_prefix) + len(sst_tail)
    workbook = globals_part + _boundsheet(offset, "Split") + sst_prefix + sst_tail + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[0][0].text == "LongValue"


def test_parse_biff_workbook_tracks_hidden_sheet_visibility():
    globals_part = _bof()
    visible_sheet = _bof() + _labelsst(0, 0, 0) + _eof()
    hidden_sheet = _bof() + _labelsst(0, 0, 1) + _eof()
    visible_boundsheet = _boundsheet_with_flags(0, "Visible", 0x0000)
    hidden_boundsheet = _boundsheet_with_flags(0, "Hidden", 0x0001)
    visible_offset = len(globals_part) + len(visible_boundsheet) + len(hidden_boundsheet)
    hidden_offset = visible_offset + len(visible_sheet)
    visible_boundsheet = _boundsheet_with_flags(visible_offset, "Visible", 0x0000)
    hidden_boundsheet = _boundsheet_with_flags(hidden_offset, "Hidden", 0x0001)
    workbook = (
        globals_part
        + visible_boundsheet
        + hidden_boundsheet
        + visible_sheet
        + hidden_sheet
    )

    doc = parse_biff_workbook(workbook)

    assert len(doc.sections) == 2
    assert doc.sections[0].provenance.sheet == "Visible"
    assert doc.sections[0].provenance.hidden is False
    assert doc.sections[1].provenance.sheet == "Hidden"
    assert doc.sections[1].provenance.hidden is True
    assert doc.sections[0].elements[0].rows[0][0].text == ""
    assert doc.sections[1].elements[0].rows[0][0].text == ""


def test_parse_biff_workbook_preserves_cp1252_punctuation_in_shared_strings():
    globals_part = _bof()
    worksheet = _bof() + _labelsst(0, 0, 0) + _eof()
    sst = _sst_raw([struct.pack("<HB", 15, 0) + b'Quote \x93Q4\x94 \x96 ok'])
    offset = len(globals_part) + len(_boundsheet(0, "Cp1252")) + len(sst)
    workbook = globals_part + _boundsheet(offset, "Cp1252") + sst + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[0][0].text == 'Quote “Q4” – ok'


def test_parse_biff_workbook_preserves_cp1252_punctuation_in_label_records():
    globals_part = _bof()
    raw_label = _record(0x0204, struct.pack("<HHH", 0, 0, 0) + struct.pack("<H", 15) + b'Quote \x93Q4\x94 \x96 ok')
    worksheet = _bof() + raw_label + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Labels"))
    workbook = globals_part + _boundsheet(offset, "Labels") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[0][0].text == 'Quote “Q4” – ok'


def test_parse_biff_workbook_restores_more_cell_types():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Name")
        + _label(0, 1, "Active")
        + _label(0, 2, "Total")
        + _label(1, 0, "A")
        + _boolerr(1, 1, 1)
        + _formula(1, 2, 42)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Data"))
    workbook = globals_part + _boundsheet(offset, "Data") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert doc.sections[0].provenance.sheet == "Data"
    assert table.rows[1][0].text == "A"
    assert table.rows[1][1].text == "TRUE"
    assert table.rows[1][2].text == "42"
    assert table.rows[1][2].provenance.cell == "C2"
    assert to_markdown(doc).startswith("## Data\n\n| Name | Active | Total |")


def test_parse_biff_workbook_reads_older_biff_integer_cells():
    globals_part = _bof()
    worksheet = _bof() + _old_label(0, 0, "Count") + _integer(1, 0, 42) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "Integer"))
    workbook = globals_part + _boundsheet(offset, "Integer") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "42"


def test_parse_biff_workbook_reads_older_biff_number_cells():
    globals_part = _bof()
    worksheet = _bof() + _old_label(0, 0, "Amount") + _old_number(1, 0, 12.5) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "OldNumber"))
    workbook = globals_part + _boundsheet(offset, "OldNumber") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "12.5"


def test_parse_biff_workbook_reads_older_biff_boolerr_cells():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _old_label(0, 0, "Active")
        + _old_label(0, 1, "Error")
        + _old_boolerr(1, 0, 1)
        + _old_boolerr(1, 1, 0x07, is_error=True)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "OldBoolErr"))
    workbook = globals_part + _boundsheet(offset, "OldBoolErr") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "TRUE"
    assert table.rows[1][1].text == "#DIV/0!"


def test_parse_biff_workbook_reads_older_biff_blank_cells():
    globals_part = _bof()
    worksheet = _bof() + _old_label(0, 0, "Left") + _old_blank(0, 2) + _eof()
    offset = len(globals_part) + len(_boundsheet(0, "OldBlank"))
    workbook = globals_part + _boundsheet(offset, "OldBlank") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert [cell.text for cell in table.rows[0]] == ["Left", "", ""]


def test_parse_biff_workbook_restores_unicode_labels_blanks_and_merged_cells():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label_unicode(0, 0, "분기")
        + _blank(0, 1)
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _merged_cells([(0, 0, 0, 1)])
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Report"))
    workbook = globals_part + _boundsheet(offset, "Report") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[0][0].text == "분기"
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away
    assert table.rows[1][0].text == "10"
    assert table.rows[1][1].text == "20"
    assert table.rows[0][0].row == 0
    assert table.rows[0][0].col == 0
    assert table.rows[0][1].row == 0
    assert table.rows[0][1].col == 1
    assert table.rows[1][0].row == 1
    assert table.rows[1][0].col == 0
    assert table.rows[1][1].row == 1
    assert table.rows[1][1].col == 1
    assert table.rows[0][0].provenance.cell == "A1"
    assert table.rows[0][1].provenance.cell == "B1"
    assert table.rows[1][0].provenance.cell == "A2"
    assert table.rows[1][1].provenance.cell == "B2"
    assert to_markdown(doc) == "## Report\n\n| 분기 |  |\n| --- | --- |\n| 10 | 20 |"


def test_parse_biff_workbook_preserves_mulblank_cell_coordinates():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _number(0, 0, 10)
        + _mulblank(0, 1, 2)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Sparse"))
    workbook = globals_part + _boundsheet(offset, "Sparse") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.row_count == 1
    assert table.col_count == 3
    assert [cell.text for cell in table.rows[0]] == ["10", "", ""]
    assert table.rows[0][0].row == 0
    assert table.rows[0][0].col == 0
    assert table.rows[0][1].row == 0
    assert table.rows[0][1].col == 1
    assert table.rows[0][2].row == 0
    assert table.rows[0][2].col == 2


def test_parse_biff_workbook_preserves_row_and_colinfo_extents():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _number(0, 0, 10)
        + _row_record(2)
        + _colinfo(2, 3)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Extents"))
    workbook = globals_part + _boundsheet(offset, "Extents") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.row_count == 3
    assert table.col_count == 4
    assert [cell.text for cell in table.rows[0]] == ["10", "", "", ""]
    assert [cell.text for cell in table.rows[2]] == ["", "", "", ""]


def test_parse_biff_workbook_preserves_dimension_used_range():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _dimension(0, 4, 0, 3)
        + _number(0, 0, 10)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Dimensions"))
    workbook = globals_part + _boundsheet(offset, "Dimensions") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.row_count == 4
    assert table.col_count == 3
    assert [cell.text for cell in table.rows[0]] == ["10", "", ""]
    assert [cell.text for cell in table.rows[3]] == ["", "", ""]


def test_parse_biff_workbook_applies_format_and_xf_number_formats():
    globals_part = (
        _bof()
        + _format_record(200, "m/d/yy")
        + _format_record(201, "0%")
        + _format_record(202, "$#,##0.00")
        + _xf(0)
        + _xf(200)
        + _xf(201)
        + _xf(202)
    )
    worksheet = (
        _bof()
        + _label(0, 0, "Date")
        + _label(0, 1, "Rate")
        + _label(0, 2, "Amount")
        + _styled_number(1, 0, 1, 45292)
        + _styled_number(1, 1, 2, 0.125)
        + _styled_number(1, 2, 3, 1234.5)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Formatted"))
    workbook = globals_part + _boundsheet(offset, "Formatted") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "2024-01-01"
    assert table.rows[1][1].text == "12.5%"
    assert table.rows[1][2].text == "$1,234.50"


def test_parse_biff_workbook_restores_basic_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "B")
        + _label(0, 2, "Total")
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _formula_with_tokens(1, 2, 30, _ptg_ref(1, 0) + _ptg_ref(1, 1) + _ptg_add())
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Formula"))
    workbook = globals_part + _boundsheet(offset, "Formula") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "30 (=A2+B2)"


def test_parse_biff_workbook_restores_cross_sheet_formula_references():
    globals_part = _bof() + _externsheet([(0, 0, 0)])
    data_sheet = (
        _bof()
        + _label(0, 0, "Amount")
        + _number(1, 0, 10)
        + _eof()
    )
    summary_sheet = (
        _bof()
        + _label(0, 0, "Metric")
        + _label(0, 1, "Double")
        + _label(1, 0, "Amount")
        + _formula_with_tokens(1, 1, 20, _ptg_ref3d(0, 1, 0) + _ptg_int(2) + _ptg_mul())
        + _eof()
    )
    data_boundsheet = _boundsheet(0, "Data")
    summary_boundsheet = _boundsheet(0, "Summary")
    data_offset = len(globals_part) + len(data_boundsheet) + len(summary_boundsheet)
    summary_offset = data_offset + len(data_sheet)
    workbook = (
        globals_part
        + _boundsheet(data_offset, "Data")
        + _boundsheet(summary_offset, "Summary")
        + data_sheet
        + summary_sheet
    )

    doc = parse_biff_workbook(workbook)
    summary_table = doc.sections[1].elements[0]

    assert summary_table.rows[1][1].text == "20 (=Data!A2*2)"


def test_parse_biff_workbook_restores_named_range_formula_tokens():
    globals_part = _bof() + _name_record("SalesTotal")
    worksheet = (
        _bof()
        + _label(0, 0, "Metric")
        + _label(0, 1, "Value")
        + _label(1, 0, "Sales")
        + _formula_with_tokens(1, 1, 100, _ptg_name(1) + _ptg_func_var(1, 4))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Summary"))
    workbook = globals_part + _boundsheet(offset, "Summary") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "100 (=SUM(SalesTotal))"


def test_parse_biff_workbook_restores_defined_name_targets_as_paragraphs():
    globals_part = _bof() + _externsheet([(0, 0, 0)]) + _name_record("SalesRange", _ptg_area3d(0, 1, 2, 0, 0))
    worksheet = (
        _bof()
        + _label(0, 0, "Sales")
        + _number(1, 0, 10)
        + _number(2, 0, 20)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Data"))
    workbook = globals_part + _boundsheet(offset, "Data") + worksheet

    doc = parse_biff_workbook(workbook)

    assert doc.sections[0].elements[0].text == "Defined name: SalesRange = Data!A2:A3"
    assert doc.sections[0].elements[1].rows[1][0].text == "10"


def test_parse_biff_workbook_restores_absolute_and_mixed_formula_references():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "B")
        + _label(0, 2, "Mixed")
        + _label(0, 3, "Range")
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _formula_with_tokens(
            1,
            2,
            30,
            _ptg_ref_flags(1, 0, row_relative=False, col_relative=False)
            + _ptg_ref_flags(1, 1, row_relative=False, col_relative=True)
            + _ptg_add(),
        )
        + _formula_with_tokens(1, 3, 30, _ptg_area_flags(1, 1, 0, 1, row_relative=False, col_relative=False) + _ptg_func_var(1, 4))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaRefs"))
    workbook = globals_part + _boundsheet(offset, "FormulaRefs") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "30 (=$A$2+B$2)"
    assert table.rows[1][3].text == "30 (=SUM($A$2:$B$2))"


def test_parse_biff_workbook_restores_comparison_and_concat_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "First")
        + _label(0, 1, "Second")
        + _label(0, 2, "Combined")
        + _label(0, 3, "Compare")
        + _label(1, 0, "A")
        + _label(1, 1, "B")
        + _formula_with_tokens(1, 2, 0, _ptg_ref(1, 0) + _ptg_ref(1, 1) + _ptg_concat())
        + _formula_string("AB")
        + _formula_bool_with_tokens(1, 3, True, _ptg_ref(1, 1) + _ptg_ref(1, 0) + _ptg_gt())
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaOps"))
    workbook = globals_part + _boundsheet(offset, "FormulaOps") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "AB (=A2&B2)"
    assert table.rows[1][3].text == "TRUE (=B2>A2)"


def test_parse_biff_workbook_restores_formula_string_literal_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Code")
        + _label(0, 1, "Display")
        + _label(1, 0, "2024")
        + _formula_with_tokens(1, 1, 0, _ptg_str("FY-") + _ptg_ref(1, 0) + _ptg_concat())
        + _formula_string("FY-2024")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaString"))
    workbook = globals_part + _boundsheet(offset, "FormulaString") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == 'FY-2024 (="FY-"&A2)'


def test_parse_biff_workbook_restores_formula_boolean_and_error_literal_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Flag")
        + _label(0, 1, "IsTrue")
        + _label(0, 2, "HasValue")
        + _boolerr(1, 0, 1)
        + _formula_bool_with_tokens(1, 1, True, _ptg_ref(1, 0) + _ptg_bool(True) + bytes([0x0B]))
        + _formula_bool_with_tokens(1, 2, True, _ptg_ref(1, 1) + _ptg_err(0x2A) + _ptg_ne())
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaLiteral"))
    workbook = globals_part + _boundsheet(offset, "FormulaLiteral") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "TRUE (=A2=TRUE)"
    assert table.rows[1][2].text == "TRUE (=B2<>#N/A)"


def test_parse_biff_workbook_restores_unary_percent_and_parenthesized_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "Negative")
        + _label(0, 2, "Rate")
        + _label(0, 3, "Grouped")
        + _number(1, 0, 10)
        + _formula_with_tokens(1, 1, -10, _ptg_ref(1, 0) + _ptg_uminus())
        + _formula_with_tokens(1, 2, 0.1, _ptg_ref(1, 0) + _ptg_percent())
        + _formula_with_tokens(1, 3, -30, _ptg_ref(1, 0) + _ptg_int(20) + _ptg_add() + _ptg_paren() + _ptg_uminus())
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaUnary"))
    workbook = globals_part + _boundsheet(offset, "FormulaUnary") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "-10 (=-A2)"
    assert table.rows[1][2].text == "0.1 (=A2%)"
    assert table.rows[1][3].text == "-30 (=-(A2+20))"


def test_parse_biff_workbook_restores_power_formula_token():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "Squared")
        + _number(1, 0, 12)
        + _formula_with_tokens(1, 1, 144, _ptg_ref(1, 0) + _ptg_int(2) + _ptg_power())
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaPower"))
    workbook = globals_part + _boundsheet(offset, "FormulaPower") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "144 (=A2^2)"


def test_parse_biff_workbook_restores_sum_range_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Q1")
        + _label(0, 1, "Q2")
        + _label(0, 2, "Total")
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _formula_with_tokens(1, 2, 30, _ptg_area(1, 1, 0, 1) + _ptg_func_var(1, 4))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Formula"))
    workbook = globals_part + _boundsheet(offset, "Formula") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "30 (=SUM(A2:B2))"


def test_parse_biff_workbook_restores_if_formula_function_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Score")
        + _label(0, 1, "Band")
        + _number(1, 0, 12)
        + _formula_with_tokens(
            1,
            1,
            0,
            _ptg_ref(1, 0)
            + _ptg_int(10)
            + _ptg_gt()
            + _ptg_str("High")
            + _ptg_str("Low")
            + _ptg_func_var(3, 1),
        )
        + _formula_string("High")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaIf"))
    workbook = globals_part + _boundsheet(offset, "FormulaIf") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == 'High (=IF(A2>10,"High","Low"))'


def test_parse_biff_workbook_restores_and_or_formula_function_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "B")
        + _label(0, 2, "All")
        + _label(0, 3, "Any")
        + _boolerr(1, 0, 1)
        + _boolerr(1, 1, 0)
        + _formula_bool_with_tokens(1, 2, False, _ptg_ref(1, 0) + _ptg_ref(1, 1) + _ptg_func_var(2, 36))
        + _formula_bool_with_tokens(1, 3, True, _ptg_ref(1, 0) + _ptg_ref(1, 1) + _ptg_func_var(2, 37))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaLogic"))
    workbook = globals_part + _boundsheet(offset, "FormulaLogic") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "FALSE (=AND(A2,B2))"
    assert table.rows[1][3].text == "TRUE (=OR(A2,B2))"


def test_parse_biff_workbook_restores_count_and_not_formula_function_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "B")
        + _label(0, 2, "Count")
        + _label(0, 3, "Negated")
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _formula_with_tokens(1, 2, 2, _ptg_ref(1, 0) + _ptg_ref(1, 1) + _ptg_func_var(2, 0))
        + _formula_bool_with_tokens(1, 3, False, _ptg_bool(True) + _ptg_func(38))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaCountNot"))
    workbook = globals_part + _boundsheet(offset, "FormulaCountNot") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "2 (=COUNT(A2,B2))"
    assert table.rows[1][3].text == "FALSE (=NOT(TRUE))"


def test_parse_biff_workbook_restores_operand_class_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Q1")
        + _label(0, 1, "Q2")
        + _label(0, 2, "Total")
        + _label(0, 3, "Double")
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _formula_with_tokens(1, 2, 30, _ptg_area_v(1, 1, 0, 1) + _ptg_func_var_v(1, 4))
        + _formula_with_tokens(1, 3, 20, _ptg_ref_v(1, 0) + _ptg_int(2) + _ptg_mul())
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaClass"))
    workbook = globals_part + _boundsheet(offset, "FormulaClass") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "30 (=SUM(A2:B2))"
    assert table.rows[1][3].text == "20 (=A2*2)"


def test_parse_biff_workbook_restores_fixed_arg_function_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Q1")
        + _label(0, 1, "Q2")
        + _label(0, 2, "Average")
        + _number(1, 0, 10)
        + _number(1, 1, 20)
        + _formula_with_tokens(1, 2, 15, _ptg_area(1, 1, 0, 1) + _ptg_func(5))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Formula"))
    workbook = globals_part + _boundsheet(offset, "Formula") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][2].text == "15 (=AVERAGE(A2:B2))"


def test_parse_biff_workbook_restores_multi_arg_fixed_function_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Input")
        + _label(0, 1, "Remainder")
        + _number(1, 0, 14)
        + _formula_with_tokens(1, 1, 2, _ptg_ref(1, 0) + _ptg_int(3) + _ptg_func(39))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaMod"))
    workbook = globals_part + _boundsheet(offset, "FormulaMod") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "2 (=MOD(A2,3))"


def test_parse_biff_workbook_restores_zero_and_two_arg_fixed_function_formula_tokens():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Always")
        + _label(0, 1, "Never")
        + _label(0, 2, "Rounded")
        + _formula_bool_with_tokens(1, 0, True, _ptg_func(34))
        + _formula_bool_with_tokens(1, 1, False, _ptg_func(35))
        + _formula_with_tokens(1, 2, 12.35, _ptg_num(12.345) + _ptg_int(2) + _ptg_func(27))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaFixed"))
    workbook = globals_part + _boundsheet(offset, "FormulaFixed") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "TRUE (=TRUE())"
    assert table.rows[1][1].text == "FALSE (=FALSE())"
    assert table.rows[1][2].text == "12.35 (=ROUND(12.345,2))"


def test_parse_biff_workbook_restores_formula_string_result_record():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Input")
        + _label(0, 1, "Status")
        + _label(1, 0, "A")
        + _formula_with_tokens(1, 1, 0, _ptg_ref(1, 0))
        + _formula_string("Approved")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaText"))
    workbook = globals_part + _boundsheet(offset, "FormulaText") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "Approved (=A2)"


def test_parse_biff_workbook_restores_older_formula_string_result_record():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _old_label(0, 0, "Input")
        + _old_label(0, 1, "Status")
        + _old_label(1, 0, "A")
        + _formula_with_tokens(1, 1, 0, _ptg_ref(1, 0))
        + _old_formula_string("Approved")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "OldFormulaText"))
    workbook = globals_part + _boundsheet(offset, "OldFormulaText") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "Approved (=A2)"


def test_parse_biff_workbook_restores_older_formula_byte_string_result_record():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _old_label(0, 0, "Input")
        + _old_label(0, 1, "Status")
        + _old_label(1, 0, "A")
        + _formula_with_tokens(1, 1, 0, _ptg_ref(1, 0))
        + _old_formula_byte_string("Approved")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "OldFormulaByteText"))
    workbook = globals_part + _boundsheet(offset, "OldFormulaByteText") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "Approved (=A2)"


def test_parse_biff_workbook_restores_formula_boolean_cached_result():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Input")
        + _label(0, 1, "Valid")
        + _label(1, 0, "A")
        + _formula_bool_with_tokens(1, 1, True, _ptg_ref(1, 0))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaBool"))
    workbook = globals_part + _boundsheet(offset, "FormulaBool") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "TRUE (=A2)"


def test_parse_biff_workbook_restores_standard_error_names_for_boolerr_and_formula():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Input")
        + _label(0, 1, "DirectError")
        + _label(0, 2, "FormulaError")
        + _label(1, 0, "A")
        + _boolerr(1, 1, 0x07, is_error=True)
        + _formula_error_with_tokens(1, 2, 0x0F, _ptg_ref(1, 0))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaError"))
    workbook = globals_part + _boundsheet(offset, "FormulaError") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "#DIV/0!"
    assert table.rows[1][2].text == "#VALUE! (=A2)"


def test_parse_biff_workbook_restores_formula_blank_cached_result_without_leading_space():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Input")
        + _label(0, 1, "Computed")
        + _label(1, 0, "A")
        + _formula_blank_with_tokens(1, 1, _ptg_ref(1, 0))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "FormulaBlank"))
    workbook = globals_part + _boundsheet(offset, "FormulaBlank") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "(=A2)"


def test_parse_biff_workbook_restores_shared_formula_template_tokens():
    globals_part = _bof()
    shared_formula_tokens = _ptg_ref(1, 0) + _ptg_int(2) + _ptg_mul()
    worksheet = (
        _bof()
        + _label(0, 0, "Input")
        + _label(0, 1, "Double")
        + _number(1, 0, 10)
        + _formula_with_tokens(1, 1, 20, _ptg_exp(1, 1))
        + _shrfmla(1, 2, 1, 1, shared_formula_tokens)
        + _number(2, 0, 20)
        + _formula_with_tokens(2, 1, 40, _ptg_exp(1, 1))
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "SharedFormula"))
    workbook = globals_part + _boundsheet(offset, "SharedFormula") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][1].text == "20 (=A2*2)"
    assert table.rows[2][1].text == "40 (=A3*2)"


def test_parse_biff_workbook_restores_rk_and_mulrk_numbers():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "A")
        + _label(0, 1, "B")
        + _label(0, 2, "C")
        + _rk(1, 0, 10)
        + _mulrk(1, 1, [20, 30])
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Compressed"))
    workbook = globals_part + _boundsheet(offset, "Compressed") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert [cell.text for cell in table.rows[1]] == ["10", "20", "30"]


def test_parse_biff_workbook_restores_hyperlink_urls():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Site")
        + _hlink(0, 0, 0, 0, "https://example.com/report")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Links"))
    workbook = globals_part + _boundsheet(offset, "Links") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[0][0].text == "Site <https://example.com/report>"


def test_parse_biff_workbook_restores_note_comment_authors():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Item")
        + _label(1, 0, "Revenue")
        + _note(1, 0, "Reviewer")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Notes"))
    workbook = globals_part + _boundsheet(offset, "Notes") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]

    assert table.rows[1][0].text == "Revenue [comment: Reviewer]"


def test_parse_biff_workbook_restores_sheet_headers_and_footers():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _header("Confidential")
        + _footer("Page 1")
        + _label(0, 0, "Revenue")
        + _number(1, 0, 10)
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Report"))
    workbook = globals_part + _boundsheet(offset, "Report") + worksheet

    doc = parse_biff_workbook(workbook)
    section = doc.sections[0]

    assert section.elements[0].text == "Header: Confidential"
    assert section.elements[1].text == "Footer: Page 1"
    assert section.elements[2].rows[1][0].text == "10"
    assert section.elements[0].runs[0].provenance.path == "Workbook#Report"
    assert section.elements[1].runs[0].provenance.path == "Workbook#Report"
    assert section.elements[2].rows[0][0].paragraphs[0].runs[0].provenance.path == "Workbook#Report"


def test_parse_biff_workbook_tracks_run_provenance_in_hyperlink_comment_cells():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _label(0, 0, "Report")
        + _hlink(0, 0, 0, 0, "https://example.com/report")
        + _label(1, 0, "Revenue")
        + _note(1, 0, "Reviewer")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Links"))
    workbook = globals_part + _boundsheet(offset, "Links") + worksheet

    doc = parse_biff_workbook(workbook)
    table = doc.sections[0].elements[0]
    assert table.rows[0][0].text == "Report <https://example.com/report>"
    assert table.rows[1][0].text == "Revenue [comment: Reviewer]"
    assert table.rows[0][0].paragraphs[0].runs[0].provenance.path == "Workbook#Links"
    assert table.rows[0][0].paragraphs[0].runs[0].provenance.cell == "A1"
    assert table.rows[1][0].paragraphs[0].runs[0].provenance.path == "Workbook#Links"
    assert table.rows[1][0].paragraphs[0].runs[0].provenance.cell == "A2"


def test_parse_biff_workbook_decodes_header_footer_control_codes():
    globals_part = _bof()
    worksheet = (
        _bof()
        + _header("&LInternal&CQuarterly&R2026")
        + _footer("&CPage &P")
        + _label(0, 0, "Revenue")
        + _eof()
    )
    offset = len(globals_part) + len(_boundsheet(0, "Report"))
    workbook = globals_part + _boundsheet(offset, "Report") + worksheet

    doc = parse_biff_workbook(workbook)
    section = doc.sections[0]

    assert section.elements[0].text == "Header: Internal Quarterly 2026"
    assert section.elements[1].text == "Footer: Page #"


def test_xls_reader_reads_workbook_stream(monkeypatch, tmp_path):
    class FakeOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == "Workbook"

        def openstream(self, name):
            class Stream:
                def read(self):
                    return _minimal_biff_workbook()

            return Stream()

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.xls.olefile.OleFileIO", FakeOle)

    path = tmp_path / "book.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = XLSReader().read(str(path))

    assert doc.metadata["source_format"] == "xls"
    assert doc.sections[0].provenance.path == "Workbook#Sheet1"
    assert to_markdown(doc) == "| Name | Value |\n| --- | --- |\n| A | 10 |"


def test_xls_reader_reads_legacy_book_stream(monkeypatch, tmp_path):
    class BookOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == "Book"

        def openstream(self, name):
            class Stream:
                def read(self):
                    return _minimal_biff_workbook()

            return Stream()

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.xls.olefile.OleFileIO", BookOle)

    path = tmp_path / "legacy.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = XLSReader().read(str(path))

    assert doc.sections[0].provenance.path == "Book#Sheet1"


def test_dochan_routes_xls_to_native_reader(monkeypatch, tmp_path):
    class FakeOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == "Workbook"

        def openstream(self, name):
            class Stream:
                def read(self):
                    return _minimal_biff_workbook()

            return Stream()

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.xls.olefile.OleFileIO", FakeOle)

    path = tmp_path / "book.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "xls"
    assert doc.to_plain_text() == "Name\tValue\nA\t10"


def test_batch_convert_includes_xls_by_default(monkeypatch, tmp_path):
    class FakeOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == "Workbook"

        def openstream(self, name):
            class Stream:
                def read(self):
                    return _minimal_biff_workbook()

            return Stream()

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.xls.olefile.OleFileIO", FakeOle)

    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    path = input_dir / "book.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    summary = batch_convert(str(input_dir), str(output_dir), output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "book.md").read_text(encoding="utf-8") == "| Name | Value |\n| --- | --- |\n| A | 10 |"


def test_cli_info_reports_xls_format(monkeypatch, tmp_path, capsys):
    class FakeOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == "Workbook"

        def openstream(self, name):
            class Stream:
                def read(self):
                    return _minimal_biff_workbook()

            return Stream()

        def close(self):
            pass

    class Args:
        pass

    monkeypatch.setattr("dochan.office_binary.xls.olefile.OleFileIO", FakeOle)
    path = tmp_path / "info.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "xls"' in out
