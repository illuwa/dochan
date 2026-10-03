"""Synthetic BIFF8 data-table and DDE formula records."""
import struct

from lxml import etree

from test_xls_formula_extended import formula, namex, record, texts, workbook, xti
from dochan.office_binary.xls import _decode_formula_token_stream
from dochan.ooxml.xlsx import XLSXReader


def table(first_row, last_row, first_col, last_col, flags, first_input, second_input):
    payload = struct.pack('<HHBBH4H', first_row, last_row, first_col, last_col,
                          flags, *first_input, *second_input)
    return record(0x0236, payload)


def table_formula(row, col, anchor_row, anchor_col):
    tokens = b'\x02' + struct.pack('<HH', anchor_row, anchor_col)
    return record(6, struct.pack('<3H', row, col, 0) + struct.pack('<d', 42)
                  + struct.pack('<HIH', 0, 0, len(tokens)) + tokens)


def nonempty_texts(doc):
    return [text for text in texts(doc) if text]


def test_table_row_input_restores_all_cells_after_table_record():
    body = table_formula(26, 2, 26, 2)
    body += table(26, 27, 2, 4, 0x0004, (25, 1), (0xffff, 0))
    body += table_formula(26, 3, 26, 2)
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42 (=TABLE($B$26,))', '42 (=TABLE($B$26,))']


def test_table_column_and_two_input_formulas():
    body = table_formula(32, 2, 32, 2)
    body += table(32, 34, 2, 4, 0, (31, 1), (0xffff, 0))
    body += table_formula(40, 2, 40, 2)
    body += table(40, 45, 2, 5, 0x000c, (37, 1), (38, 1))
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42 (=TABLE(,$B$32))', '42 (=TABLE($B$38,$B$39))']


def test_table_bad_anchor_keeps_cache_and_warns():
    body = table_formula(26, 2, 26, 2)
    body += table(27, 27, 2, 4, 0x0004, (25, 1), (0xffff, 0))
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42']
    assert any('TABLE' in error for error in doc.errors)


def test_table_without_table_record_keeps_cache_and_warns():
    doc = workbook(b'', table_formula(26, 2, 26, 2))
    assert nonempty_texts(doc) == ['42']
    assert any('TABLE' in error for error in doc.errors)


def test_table_with_extra_record_bytes_keeps_cache_and_warns():
    # A BIFF header declaring two extra bytes is not the observed TABLE layout.
    body = table_formula(3, 4, 3, 4) + record(0x0236,
        struct.pack('<HHBBH4H', 3, 3, 4, 4, 3, 4, 0, 1, 0) + b'\0\0')
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42']
    assert any('TABLE' in error for error in doc.errors)


def dde_supbook(service, topic):
    path = (service + '\x03' + topic).encode('latin1')
    return record(0x01ae, struct.pack('<HHB', 0, len(path), 0) + path)


def dde_name(item, flags=0x7fe2, extra=b''):
    raw = item.encode('latin1')
    return record(0x23, struct.pack('<HHHB', flags, 0, 0, len(raw)) + b'\0' + raw + extra)


def test_dde_namex_displays_service_topic_and_item():
    globals_ = dde_supbook('MTX', 'DATA') + dde_name('GOLDS.SON')
    globals_ += xti((0, 0xfffe, 0xfffe))
    doc = workbook(globals_, formula(namex()))
    assert texts(doc) == ['42 (=MTX|DATA!GOLDS.SON)']


def test_dde_name_may_have_bounded_cached_link_data():
    globals_ = dde_supbook('IDT', 'IMKB') + dde_name('Rate_Date', extra=b'\x01\x00\x00')
    globals_ += xti((0, 0xfffe, 0xfffe))
    doc = workbook(globals_, formula(namex()))
    assert texts(doc) == ['42 (=IDT|IMKB!Rate_Date)']


def test_f_ole_std_document_name_is_dde():
    globals_ = dde_supbook('MTX', 'DATA') + dde_name('StdDocumentName', 0x7fea)
    globals_ += xti((0, 0xfffe, 0xfffe))
    doc = workbook(globals_, formula(namex()))
    assert texts(doc) == ['42 (=MTX|DATA!StdDocumentName)']


def test_unknown_elf_subtoken_keeps_cache():
    warnings = []
    assert _decode_formula_token_stream(bytes.fromhex('180a02000180'), errors=warnings) == ''
    assert any('PtgElf' in warning for warning in warnings)


def test_xlsx_data_table_uses_the_same_formula_notation():
    reader = XLSXReader()
    cases = [
        ({'r1': 'B26', 'dtr': '1'}, '42 (=TABLE($B$26,))'),
        ({'r1': 'B32'}, '42 (=TABLE(,$B$32))'),
        ({'r1': 'B38', 'r2': 'B39', 'dt2D': '1'}, '42 (=TABLE($B$38,$B$39))'),
    ]
    for attributes, expected in cases:
        cell = etree.Element('c')
        entry = etree.SubElement(cell, 'f', t='dataTable', **attributes)
        assert reader._with_formula('42', cell, {}, entry) == expected
