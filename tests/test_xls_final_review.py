"""Final review regressions built solely from synthetic BIFF records."""
import struct

import pytest

from dochan.office_binary import xls, xls_formula
from test_xls_formula_extended import formula, int_token, record, supbook, texts, workbook, xti


def test_xls_invalid_cell_diagnostics_are_bounded_and_deduplicated():
    bad = b''.join(record(0x27e, struct.pack('<HHHI', row, 300, 0, 2))
                   for row in range(4000))
    doc = workbook(b'', bad + bad)
    assert len(doc.errors) <= 101
    assert any('diagnostics omitted' in error for error in doc.errors)
    assert len(doc.errors) == len(set(doc.errors))


def test_xls_error_collection_uses_bounded_membership_set():
    sheet = xls._SheetInfo('S', 0)
    for index in range(4000):
        xls._append_sheet_error_once(sheet, 'ERR: bad %d' % index)
    assert len(sheet.errors) <= 101
    assert len(sheet.errors.seen) <= 100
    assert 'ERR: bad 0' in sheet.errors


def test_xls_partial_rpn_retains_cache_and_reports_cell():
    doc = workbook(b'', formula(int_token(1) + b'\x05', row=18))
    assert [text for text in texts(doc) if text] == ['42']
    assert any('A19' in error and 'expression omitted' in error for error in doc.errors)


@pytest.mark.parametrize('path,sheets', [
    ('folder\x03subfolder\x03book.xls', ('Remote',)),
    ('folder\x03book.xls', ('Remote',)),
    ('folder\x03subfolder\x03book.xls', ()),
    ('\x02Users\x03book.xls', ()),
    ('\x04other\x03book.xls', ()),
])
def test_supbook_virtual_path_is_not_dde(path, sheets):
    context, errors = xls_formula.FormulaContext(), []
    context.add_supbook(supbook(sheets, path)[4:], errors)
    assert context.books[0].kind == 'external'
    assert not errors


def test_external_multisegment_virtual_path_formula_is_retained():
    doc = workbook(supbook(('Remote',), 'folder\x03subfolder\x03book.xls')
                   + xti((0, 0, 0)), formula(b'\x3a' + b'\0' * 6))
    assert texts(doc) == ['42 (=[1]Remote!$A$1)']
    assert not doc.errors


@pytest.mark.parametrize('tail', [b'\x19', b'\x19\x04\x02\x00\x00'])
def test_xls_truncated_attribute_cannot_salvage_partial_expression(tail):
    doc = workbook(b'', formula(int_token(1) + tail))
    assert texts(doc) == ['42']
    assert any('A1:' in error and 'expression omitted' in error for error in doc.errors)



def test_xls_sheet_error_summary_keeps_omitted_count_when_merged():
    errors = xls_formula.BoundedErrors(limit=2)
    errors.extend(['a', 'a', 'b', 'c', 'd'])
    workbook_errors = xls_formula.BoundedErrors(limit=3)
    workbook_errors.extend(errors)
    workbook_errors.append('e')
    assert workbook_errors == ['a', 'b', 'e', 'WARN: XLS 2 additional diagnostics omitted']
    assert len(workbook_errors.seen) == 3


def test_xls_error_cap_preserves_first_fatal_after_warning_flood():
    errors = xls_formula.BoundedErrors(limit=2)
    errors.extend(['WARN: first', 'WARN: second', 'WARN: third'])
    errors.append('ERR: broken workbook')
    errors.append('ERR: broken workbook')
    errors.append('ERR: another problem')
    assert errors == ['WARN: first', 'ERR: broken workbook',
                      'WARN: XLS 3 additional diagnostics omitted']
    assert errors.seen == {'WARN: first', 'ERR: broken workbook'}
    assert 'WARN: second' not in errors


def test_xls_public_errors_are_an_ordinary_mutable_list():
    bad = b''.join(record(0x27e, struct.pack('<HHHI', row, 300, 0, 2))
                   for row in range(150))
    doc = workbook(b'', bad)
    assert len(doc.errors) == 101
    doc.errors.clear()
    doc.errors.append('WARN: caller diagnostic')
    doc.errors.append('WARN: caller diagnostic')
    assert doc.errors == ['WARN: caller diagnostic', 'WARN: caller diagnostic']
    assert type(doc.errors) is list
