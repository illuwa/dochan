"""BIFF formula strings must retain the same names and cache contract as XLSX."""
import struct

from dochan.office_binary.xls import _decode_formula_token_stream, parse_biff_workbook


def _record(kind, data=b''):
    return struct.pack('<HH', kind, len(data)) + data


def _formula_document(tokens, cache, string_cache=None):
    bof = _record(0x0809, struct.pack('<HH', 0x600, 0x10))
    name = b'Formulas'
    bound_size = 12 + len(name)
    boundsheet = _record(0x85, struct.pack('<IBBBB', len(bof) + bound_size, 0, 0, len(name), 0) + name)
    formula = _record(6, struct.pack('<3H', 0, 0, 0) + cache + struct.pack('<HIH', 0, 0, len(tokens)) + tokens)
    string = b''
    if string_cache is not None:
        string = _record(0x207, struct.pack('<HB', len(string_cache), 0) + string_cache.encode('latin1'))
    return parse_biff_workbook(bof + boundsheet + bof + formula + string + _record(10))


def test_xls_formula_concatenate_preserves_function_name_and_string_cache():
    refs = b'\x24' + struct.pack('<HH', 0, 0xC000) + b'\x24' + struct.pack('<HH', 1, 0xC000)
    tokens = refs + b'\x22\x02' + struct.pack('<H', 336)
    doc = _formula_document(tokens, b'\0' * 6 + b'\xff\xff', 'replacemereplaceme')
    assert doc.sections[0].elements[0].rows[0][0].text == 'replacemereplaceme (=CONCATENATE(A1,A2))'


def test_xls_formula_upper_preserves_function_name_and_string_cache():
    tokens = b'\x17\x03\x00xyz\x21' + struct.pack('<H', 113)
    doc = _formula_document(tokens, b'\0' * 6 + b'\xff\xff', 'XYZ')
    assert doc.sections[0].elements[0].rows[0][0].text == 'XYZ (=UPPER("xyz"))'


def test_xls_formula_attr_sum_retains_sum_and_numeric_cache():
    tokens = b'\x25' + struct.pack('<4H', 0, 2, 0xC000, 0xC000) + b'\x19\x10\x00\x00'
    doc = _formula_document(tokens, struct.pack('<d', 6))
    assert doc.sections[0].elements[0].rows[0][0].text == '6 (=SUM(A1:A3))'


def test_xls_formula_attr_volatile_consumes_three_payload_bytes():
    tokens = b'\x1e\x01\x00\x19\x01\x00\x00\x1e\x02\x00\x03'
    assert _decode_formula_token_stream(tokens) == '1+2'


def test_xls_formula_truncated_attr_stops_safely():
    errors = []
    assert _decode_formula_token_stream(b'\x1e\x01\x00\x19\x10\x00', errors=errors) == ''
    assert any('truncated attribute token' in error for error in errors)


def test_xls_shared_formula_refn_preserves_anchor_and_follower_string_caches():
    bof = _record(0x809, struct.pack('<HH', 0x600, 0x10))
    name = b'Label'
    boundsheet = _record(0x85, struct.pack('<IBBBB', len(bof) + 12 + len(name), 0, 0, len(name), 0) + name)
    sheet = bof
    tokens = b'\x4c' + struct.pack('<HH', 0, 0xC001)
    for row, text in [(1, 'Header'), (2, 'Value')]:
        exp = b'\x01' + struct.pack('<HH', 1, 0)
        sheet += _record(6, struct.pack('<HHH', row, 0, 0) + b'\0' * 6 + b'\xff\xff' + struct.pack('<HIH', 8, 0, len(exp)) + exp)
        if row == 1:
            sheet += _record(0x4bc, struct.pack('<HHBBBBH', 1, 2, 0, 0, 0, 2, len(tokens)) + tokens)
        sheet += _record(0x207, struct.pack('<HB', len(text), 0) + text.encode('latin1'))
    doc = parse_biff_workbook(bof + boundsheet + sheet + _record(10))
    table = doc.sections[0].elements[0]
    assert table.rows[1][0].text == 'Header (=B2)'
    assert table.rows[2][0].text == 'Value (=B3)'


def test_xls_shared_formula_refn_resolves_negative_relative_offsets():
    from dochan.office_binary.xls import _decode_shared_formula_for_cell
    tokens = b'\x4c' + struct.pack('<HH', 0xffff, 0xc0ff)
    assert _decode_shared_formula_for_cell(tokens, (1, 1), (2, 2)) == 'B2'


def test_xls_shared_formula_arean_resolves_relative_and_absolute_coordinates():
    from dochan.office_binary.xls import _decode_shared_formula_for_cell
    tokens = b'\x4d' + struct.pack('<4H', 0xffff, 4, 0xc0ff, 3) + b'\x19\x10\0\0'
    assert _decode_shared_formula_for_cell(tokens, (1, 1), (2, 2)) == 'SUM(B2:$D$5)'


def test_xls_formula_empty_cache_uses_xlsx_equals_contract():
    from dochan.utils import safe_xml as etree
    from dochan.ooxml.xlsx import XLSXReader
    tokens = b'\x1e\x01\x00\x1e\x02\x00\x03'
    doc = _formula_document(tokens, b'\x03' + b'\0' * 5 + b'\xff\xff')
    cell = etree.fromstring(b'<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><f>1+2</f></c>')
    expected = XLSXReader()._cell_text(cell, [], [], {})
    assert expected == '=1+2'
    assert doc.sections[0].elements[0].rows[0][0].text == expected
