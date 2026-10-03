"""BIFF5 3D token observations from a public LibreOffice workbook."""
import random
import struct

import pytest

from dochan.office_binary.xls import _decode_formula_token_stream, parse_biff_workbook
from dochan.office_binary.xls_formula import FormulaContext


def record(kind, payload=b''):
    return struct.pack('<HH', kind, len(payload)) + payload


# shared-formula/biff5.xls NAME at stream offset 0xb4: rgce starts 3b at
# payload offset 29. Its 14-byte qualifier and six-byte area end in
# rows 0004..0177 and columns 00..05; BOUNDSHEET names Sheet1 at 0x1921.
QUALIFIER = bytes.fromhex('ff ff 00 00 00 00 00 00 01 00 00 00 00 00')
AREA = bytes.fromhex('04 00 77 01 00 05')


def legacy_context():
    context = FormulaContext()
    context.biff_version = 0x0500
    context.sheets = ['Sheet1']
    context.legacy_extern_count = 1
    context.legacy_externs = ['Sheet1']
    return context


def test_biff5_area3d_public_name_bytes_decode_sheet_and_area():
    tokens = b'\x3b' + QUALIFIER + AREA
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context()) == (
        'Sheet1!$A$5:$F$376')


@pytest.mark.parametrize('token', [0x3a, 0x5a, 0x7a])
def test_biff5_ref3d_class_variants_use_legacy_ref_width(token):
    tokens = bytes([token]) + QUALIFIER + struct.pack('<HB', 4, 0)
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context()) == 'Sheet1!$A$5'


@pytest.mark.parametrize('token', [0x3b, 0x5b, 0x7b])
def test_biff5_area3d_class_variants_use_legacy_area_width(token):
    tokens = bytes([token]) + QUALIFIER + AREA
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context()) == (
        'Sheet1!$A$5:$F$376')


def test_biff5_name_uses_externcount_and_externsheet_record():
    """Global 0016=01 00, 0017=06 03 Sheet1 precede the public NAME bytes."""
    bof = record(0x809, struct.pack('<HH', 0x0500, 0x0005))
    externs = record(0x16, b'\x01\x00') + record(0x17, b'\x06\x03Sheet1')
    header = bytes.fromhex('01 00 00 0f 15 00 01 00 01 00 00 00 00 00')
    name = record(0x18, header + b'_FilterDatabase' + b'\x3b' + QUALIFIER + AREA)
    sheet_start = len(bof) + len(externs) + len(name) + 4 + 7 + 6 + 4
    bound = record(0x85, struct.pack('<IBBB', sheet_start, 0, 0, 6) + b'Sheet1')
    doc = parse_biff_workbook(bof + externs + name + bound + record(10)
                              + record(0x809, struct.pack('<HH', 0x0500, 0x0010)) + record(10))
    assert any('Defined name: _FilterDatabase = Sheet1!$A$5:$F$376' in e.text
               for s in doc.sections for e in s.elements if hasattr(e, 'text'))


@pytest.mark.parametrize('tokens', [
    b'\x3b' + QUALIFIER + AREA[:-1],
    b'\x3a' + QUALIFIER + b'\x04\x00',
    b'\x3b' + b'\x00' * 14 + AREA,
    b'\x3b' + QUALIFIER[:8] + b'\x02\x00' + QUALIFIER[10:] + AREA,
])
def test_biff5_3d_truncated_or_unresolved_keeps_cached_expression_omitted(tokens):
    errors = []
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context(), errors=errors) == ''
    assert errors


def test_biff5_3d_malformed_record_fuzz_never_raises():
    randomizer = random.Random(503)
    for _ in range(500):
        size = randomizer.randrange(0, 38)
        token = randomizer.choice((0x3a, 0x3b, 0x5a, 0x5b, 0x7a, 0x7b))
        payload = bytes(randomizer.randrange(256) for _ in range(size))
        errors = []
        result = _decode_formula_token_stream(bytes([token]) + payload,
                                              formula_context=legacy_context(), errors=errors)
        assert result == ''
        assert errors
