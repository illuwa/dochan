"""Review regressions built solely from synthetic BIFF records."""
import struct

import pytest

from dochan.office_binary.xls import _decode_formula_token_stream, _decode_shared_formula
from test_xls_formula_extended import (
    array_extra, formula, int_token, name, namex, record, texts, workbook, xti,
)


def test_invalid_name_warnings_are_deduplicated():
    doc = workbook(record(0x18, b'') * 1200 + name('Valid'),
                   formula(b'\x23' + struct.pack('<I', 1201)))
    assert texts(doc) == ['42 (=Valid)']
    assert doc.errors == ['WARN: XLS formula invalid NAME record']


def test_empty_name_with_formula_has_no_metadata_paragraph():
    doc = workbook(name('', tokens=int_token(1)) + name('Valid'),
                   formula(b'\x23' + struct.pack('<I', 2)))
    assert texts(doc) == ['42 (=Valid)']
    assert not any(getattr(e, 'text', '').startswith('Defined name:  =')
                   for s in doc.sections for e in s.elements)


@pytest.mark.parametrize('token', [0x23, 0x43, 0x63])
def test_ptgname_nonzero_reserved_high_word_preserves_low_index(token):
    doc = workbook(name('Revenue'), formula(bytes([token]) + struct.pack('<HH', 1, 7)))
    assert texts(doc) == ['42 (=Revenue)']


@pytest.mark.parametrize('code,label', [(6, 'Print_Area'), (7, 'Print_Titles'), (13, '_FilterDatabase')])
def test_builtin_name_is_mapped_for_name_and_namex(code, label):
    builtin = bytearray(name(chr(code), scope=1, tokens=int_token(1)))
    struct.pack_into('<H', builtin, 4, 0x20)  # Lbl.fBuiltin.
    globals_ = record(0x1ae, b'\x01\x00\x01\x04') + xti((0, 0xfffe, 0xfffe)) + builtin
    doc = workbook(globals_, formula(namex()) + formula(b'\x23\x01\0\0\0', row=1))
    assert texts(doc) == ['42 (=Local!%s)' % label, '42 (=%s)' % label]
    assert doc.sections[0].elements[0].text == 'Defined name: %s = 1' % label


@pytest.mark.parametrize('token,size', [(0x2a, 4), (0x2b, 8)])
@pytest.mark.parametrize('operand_class', [0, 0x20, 0x40])
def test_deleted_reference_tokens_preserve_expression_and_cache(token, size, operand_class):
    tokens = bytes([token + operand_class]) + b'\xff' * size + int_token(1) + b'\x03'
    doc = workbook(b'', formula(tokens))
    assert texts(doc) == ['42 (=#REF!+1)']
    assert not doc.errors


@pytest.mark.parametrize('token,size', [(0x3c, 4), (0x3d, 8)])
@pytest.mark.parametrize('operand_class', [0, 0x20, 0x40])
def test_deleted_3d_reference_preserves_sheet_qualifier(token, size, operand_class):
    globals_ = record(0x1ae, b'\x01\x00\x01\x04') + xti((0, 0, 0))
    tokens = bytes([token + operand_class]) + b'\0\0' + b'\xff' * size
    doc = workbook(globals_, formula(tokens))
    assert texts(doc) == ['42 (=Local!#REF!)']
    assert not doc.errors


@pytest.mark.parametrize('token,size', [(0x2a, 4), (0x2b, 8), (0x3c, 6), (0x3d, 10)])
def test_truncated_deleted_reference_keeps_cache_and_warns(token, size):
    doc = workbook(b'', formula(bytes([token]) + b'\0' * (size - 1)))
    assert texts(doc) == ['42']
    assert doc.errors


def test_deleted_3d_sheet_does_not_duplicate_ref_error():
    globals_ = record(0x1ae, b'\x01\x00\x01\x04') + xti((0, 0xffff, 0xffff))
    doc = workbook(globals_, formula(b'\x3c' + b'\0' * 6))
    assert texts(doc) == ['42 (=#REF!)']


@pytest.mark.parametrize('extended', [False, True])
def test_shared_formula_fallback_preserves_array_extra_offset(extended):
    tokens = b'\x20' + b'\0' * 7
    if extended:
        tokens += (int_token(1) + b'\x03') * 62  # 256-byte stream exercises old fallback.
    header = struct.pack('<HHBBB', 0, 1, 0, 0, 0) + b'\x02\0'
    payload = header + struct.pack('<H', len(tokens)) + tokens + array_extra([[1, 2]])
    expected = '{1,2}' + ('+1' * 62 if extended else '')
    assert _decode_shared_formula(payload) == expected
    exp = b'\x01' + b'\0' * 4
    doc = workbook(b'', formula(exp) + record(0x4bc, payload) + formula(exp, row=1))
    assert texts(doc) == ['42 (=%s)' % expected] * 2
