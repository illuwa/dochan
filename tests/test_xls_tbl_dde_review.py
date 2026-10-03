"""Review regressions for BIFF TABLE, ARRAY, and DDE records."""
import struct
import time

from lxml import etree

from test_xls_formula_extended import formula, namex, record, texts, workbook, xti
from test_xls_table_dde import dde_name, dde_supbook, nonempty_texts, table, table_formula
from dochan.office_binary import xls_formula
from dochan.ooxml.xlsx import XLSXReader


def test_table_reserved_bit_does_not_change_row_input():
    body = table_formula(26, 2, 26, 2)
    body += table(26, 26, 2, 2, 0x0006, (25, 1), (0xffff, 0))
    assert nonempty_texts(workbook(b'', body)) == ['42 (=TABLE($B$26,))']


def test_table_duplicate_is_ignored_and_later_outside_cell_keeps_cache():
    body = table_formula(26, 2, 26, 2)
    body += table_formula(28, 2, 26, 2)
    body += table(26, 26, 2, 2, 0x0004, (25, 1), (0xffff, 0))
    body += table(26, 26, 2, 2, 0, (30, 1), (0xffff, 0))
    body += table_formula(27, 2, 26, 2)
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42 (=TABLE($B$26,))', '42', '42']
    assert any('duplicate TABLE' in error for error in doc.errors)
    assert any('outside range' in error for error in doc.errors)


def test_duplicate_table_does_not_replace_first_formula():
    body = table_formula(26, 2, 26, 2)
    body += table(26, 26, 2, 2, 0x0004, (25, 1), (0xffff, 0))
    body += table(26, 26, 2, 2, 0, (30, 1), (0xffff, 0))
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42 (=TABLE($B$26,))']
    assert any('duplicate TABLE' in error for error in doc.errors)


def test_table_truncated_record_warns_with_anchor():
    body = table_formula(26, 2, 26, 2) + record(0x0236, struct.pack('<HHBB', 26, 26, 2, 2))
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42']
    assert any('C27' in error and 'TABLE' in error for error in doc.errors)
    assert not any('unpack' in error for error in doc.errors)


def test_table_deleted_input_keeps_cache():
    body = table_formula(26, 2, 26, 2)
    body += table(26, 26, 2, 2, 0x0014, (25, 1), (0xffff, 0))
    doc = workbook(b'', body)
    assert nonempty_texts(doc) == ['42']
    assert any('deleted input' in error for error in doc.errors)


def test_dde_unsafe_components_are_quoted():
    globals_ = dde_supbook('IDT', 'Rate Topic') + dde_name("A,B 'C'")
    globals_ += xti((0, 0xfffe, 0xfffe))
    assert texts(workbook(globals_, formula(namex()))) == [
        "42 (=IDT|'Rate Topic'!'A,B ''C''')"]
    globals_ = dde_supbook('MTX', 'A!B') + dde_name('ITEM')
    globals_ += xti((0, 0xfffe, 0xfffe))
    assert texts(workbook(globals_, formula(namex()))) == [
        "42 (=MTX|'A!B'!ITEM)"]


def test_dde_f_ole_is_dde_name_and_storage_header_is_checked():
    globals_ = dde_supbook('MTX', 'DATA') + dde_name('StdDocumentName', 0x7fea)
    globals_ += xti((0, 0xfffe, 0xfffe))
    assert texts(workbook(globals_, formula(namex()))) == [
        '42 (=MTX|DATA!StdDocumentName)']
    malformed = dde_supbook('MTX', 'DATA')
    malformed += record(0x23, struct.pack('<HIHB', 0x7fe2, 0x10000, 0, 4) + b'\0DATA')
    malformed += xti((0, 0xfffe, 0xfffe))
    doc = workbook(malformed, formula(namex()))
    assert texts(doc) == ['42']
    assert any('ExternName' in error for error in doc.errors)


def test_dde_f_ole_link_retains_cache():
    globals_ = dde_supbook('MTX', 'DATA') + dde_name('Object', 0x7ff2)
    globals_ += xti((0, 0xfffe, 0xfffe))
    doc = workbook(globals_, formula(namex()))
    assert texts(doc) == ['42']
    assert any('OLE' in error for error in doc.errors)


def test_dde_path_length_and_forbidden_characters_are_rejected():
    for topic in ('A' * 253, 'A:B'):
        globals_ = dde_supbook('MTX', topic) + dde_name('ITEM')
        globals_ += xti((0, 0xfffe, 0xfffe))
        doc = workbook(globals_, formula(namex()))
        assert texts(doc) == ['42']
        assert doc.errors


def test_dde_cumulative_text_budget_retains_cache(monkeypatch):
    monkeypatch.setattr(xls_formula, 'MAX_LINK_TEXT_BYTES', 15)
    globals_ = dde_supbook('MTX', 'DATA') + dde_name('ITEM')
    globals_ += xti((0, 0xfffe, 0xfffe))
    doc = workbook(globals_, formula(namex()))
    assert texts(doc) == ['42']
    assert any('byte limit' in error for error in doc.errors)


def test_xlsx_deleted_table_inputs_keep_cache():
    reader = XLSXReader()
    for attributes in ({'r1': 'B26', 'dtr': '1', 'del1': '1'},
                       {'r1': 'B26', 'r2': 'B27', 'dt2D': '1', 'del2': '1'}):
        cell = etree.Element('c')
        entry = etree.SubElement(cell, 'f', t='dataTable', **attributes)
        assert reader._with_formula('42', cell, {}, entry) == '42'


def test_duplicate_table_records_run_under_one_second():
    body = b''.join(table_formula(26 + i // 200, i % 200, 26, 0)
                    for i in range(20000))
    body += table(26, 125, 0, 199, 0x0004, (25, 1), (0xffff, 0))
    body += table(26, 125, 0, 199, 0x0004, (25, 1), (0xffff, 0)) * 999
    start = time.monotonic()
    doc = workbook(b'', body)
    assert time.monotonic() - start < 1.0
    assert any('duplicate TABLE' in error for error in doc.errors)


def test_duplicate_array_records_run_under_one_second():
    exp = b'\x01' + struct.pack('<HH', 26, 0)
    def array_formula(row, col):
        return record(6, struct.pack('<3H', row, col, 0) + struct.pack('<d', 42)
                      + struct.pack('<HIH', 0, 0, len(exp)) + exp)
    body = b''.join(array_formula(26 + i // 200, i % 200)
                    for i in range(20000))
    tokens = b'\x1e\x01\x00'
    array = record(0x0221, struct.pack('<HHBBHIH', 26, 125, 0, 199,
                                      0, 0, len(tokens)) + tokens)
    body += array * 1000
    start = time.monotonic()
    doc = workbook(b'', body)
    assert time.monotonic() - start < 1.0
    assert any('duplicate ARRAY' in error for error in doc.errors)
