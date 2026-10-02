"""Synthetic regressions for SupBook classification and bounded link metadata."""
import struct

import pytest

from dochan.office_binary import xls_formula
from test_xls_formula_extended import (
    externname, formula, int_token, namex, supbook, texts, workbook, xti,
)


@pytest.mark.parametrize('path', ['\x00', ' '])
def test_supbook_current_and_unused_do_not_shift_external_ordinal(path):
    doc = workbook(supbook((), path) + supbook() + xti((1, 0, 0)),
                   formula(bytes.fromhex('3a000000000000')))
    assert texts(doc) == ['42 (=[1]Remote!$A$1)']
    assert not doc.errors


def test_supbook_external_without_sheets_retains_name_and_ordinal():
    globals_ = supbook(()) + externname('Macro.tri_ambiance')
    globals_ += supbook() + xti((0, 0xfffe, 0xfffe), (1, 0, 0))
    doc = workbook(globals_, formula(namex())
                   + formula(b'\x3a' + struct.pack('<3H', 1, 0, 0), row=1))
    assert texts(doc) == ['42 (=[1]!Macro.tri_ambiance)', '42 (=[2]Remote!$A$1)']
    assert not doc.errors


@pytest.mark.parametrize('path', ['IDT\x03IMKB', 'MTX\x03DATA'])
def test_supbook_dde_path_is_not_an_external_name_book(path):
    context, errors = xls_formula.FormulaContext(), []
    context.add_supbook(supbook((), path)[4:], errors)
    context.add_externname(externname('Rate_Date', flags=0x7fe2)[4:], errors)
    context.add_supbook(supbook()[4:], errors)
    context.xtis = [(1, 0, 0)]
    assert context.books[0].kind == 'dde'
    assert context.books[0].names[0].name == ''
    assert context.prefix(0) == '[2]Remote!'


@pytest.mark.parametrize('path', ['Class1', 'Object', '\x01folder\x03book.xls'])
def test_supbook_plain_and_encoded_external_paths_remain_external(path):
    context, errors = xls_formula.FormulaContext(), []
    context.add_supbook(supbook(('Remote',), path)[4:], errors)
    context.xtis = [(0, 0, 0)]
    assert context.books[0].kind == 'external'
    assert context.prefix(0) == '[1]Remote!'
    assert not errors


@pytest.mark.parametrize('flags', [0x02, 0x04, 0x08, 0x10, 0x7fe2])
def test_externname_dde_ole_flags_do_not_become_workbook_names(flags):
    doc = workbook(supbook() + externname('DDE', flags=flags)
                   + externname('Valid') + xti((0, 0xfffe, 0xfffe)),
                   formula(namex()) + formula(namex(2), row=1))
    assert texts(doc) == ['42', '42 (=[1]!Valid)']
    assert any('DDE/OLE' in error for error in doc.errors)


def test_supbook_sheet_bytes_are_cumulative_and_preserve_book_indices(monkeypatch):
    # Each UTF-16 sheet string costs 3 header bytes + 6 payload bytes.
    monkeypatch.setattr(xls_formula, 'MAX_LINK_TEXT_BYTES', 18, raising=False)
    context, errors = xls_formula.FormulaContext(), []
    context.add_supbook(supbook(('One',))[4:], errors)
    context.add_supbook(supbook(('TooLong',))[4:], errors)
    context.add_supbook(supbook(('Two',))[4:], errors)
    context.xtis = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    assert context.prefix(0) == '[1]One!'
    with pytest.raises(xls_formula.FormulaDataError):
        context.prefix(1)
    assert context.prefix(2) == '[3]Two!'
    assert len(context.books) == 3
    assert len(errors) == 1 and 'byte limit' in errors[0]


def test_supbook_sheet_budget_keeps_cache_and_deduplicates_warning(monkeypatch):
    monkeypatch.setattr(xls_formula, 'MAX_LINK_TEXT_BYTES', 0, raising=False)
    globals_ = supbook() * 40 + xti((0, 0, 0))
    doc = workbook(globals_, formula(b'\x3a' + b'\0' * 6)
                   + formula(int_token(1), row=1))
    assert texts(doc) == ['42', '42 (=1)']
    assert sum('SupBook sheet name byte limit' in e for e in doc.errors) == 1
