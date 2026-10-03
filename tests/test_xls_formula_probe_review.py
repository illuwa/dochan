"""Regression checks for conservative formula evidence classification."""
import pytest
import struct

from scripts.probe_xls_formula_pairs import mismatch_cause


def cause(expected, actual):
    return mismatch_cause(
        {'comparison': 'mismatch', 'sheet': 'Local',
         'expected': expected, 'actual': actual},
        {'token_warnings': []}, ['Local'])


@pytest.mark.parametrize('expected,actual', [
    ('[2]S!A1', '[1]Other!A1'),
    ('[2]S!A1', '[1]S!A2'),
    ('[2]S!A1', '[1]S!$A$1'),
    ('[2]S!A1', '[External1]Other!A1'),
    ('[2]S!A1+1', '[1]S!A1+2'),
    ('"[2]S!A1"', '"[1]S!A1"'),
    ('Table[Old]', 'Table[New]'),
    ("Table[Old]+'S'!A1", "Table[New]+'S'!A1"),
])
def test_external_cause_does_not_hide_other_formula_differences(expected, actual):
    assert not cause(expected, actual).startswith('external ')


@pytest.mark.parametrize('expected,actual', [
    ("['file:///source.xlsx']S!A1", '[1]S!A1'),
    ('[2]S!A1', '[1]S!A1'),
    ("'[source.xlsx]Sheet 1'!$A$1", "'[1]Sheet 1'!$A$1"),
])
def test_external_cause_requires_identical_sheet_cell_and_expression(expected, actual):
    assert cause(expected, actual) == 'external workbook qualifier only'


def test_formula_corpus_inventory_counts_coordinates_without_decoding_tokens():
    from scripts.probe_xls_formula_corpus import formula_coordinates
    def record(kind, payload):
        return struct.pack('<HH', kind, len(payload)) + payload
    sheet_name = b'Public'
    start = 4 + 8 + len(sheet_name)
    boundsheet = record(0x85, struct.pack('<IBBBB', start, 0, 0, len(sheet_name), 0)
                        + sheet_name)
    # The denominator includes undecodable/truncated formula payloads and counts
    # duplicate records at a cell only once; unrelated numeric cells do not count.
    formula = record(6, struct.pack('<HHH', 2, 3, 0))
    numeric = record(0x203, struct.pack('<HHHd', 1, 0, 0, 1.0))
    assert formula_coordinates(boundsheet + formula * 2 + numeric) == {('Public', 'D3')}


def test_formula_corpus_inventory_uses_workbook_biff5_sheet_encoding():
    """A BIFF5 BOF 00 05 and BOUNDSHEET 06 46 65 75 69 6c 31 encode Feuil1.

    The public testEXCEL_5.xls has this BOUNDSHEET payload at stream offset
    0x3b9. The first byte is a legacy byte count, not a Unicode flag.
    """
    from scripts.probe_xls_formula_corpus import formula_coordinates
    def record(kind, payload):
        return struct.pack('<HH', kind, len(payload)) + payload
    bof = record(0x809, struct.pack('<HH', 0x500, 0x10))
    label = b'Feuil1'
    start = len(bof) + 4 + 7 + len(label)
    bound = record(0x85, struct.pack('<IBBB', start, 0, 0, len(label)) + label)
    formula = record(6, struct.pack('<HHH', 5, 1, 0))
    assert formula_coordinates(bof + bound + formula) == {('Feuil1', 'B6')}


def test_formula_corpus_inventory_excludes_encrypted_denominator():
    from scripts.probe_xls_formula_corpus import formula_coordinates
    with pytest.raises(ValueError, match='encrypted FILEPASS'):
        formula_coordinates(struct.pack('<HHH', 0x2f, 2, 0))


def test_formula_corpus_name_inventory_excludes_empty_and_truncated_names():
    from scripts.probe_xls_formula_corpus import named_formula_count
    def name_record(name, tokens, claimed_length=None):
        header = bytearray(15)
        header[3] = len(name)
        struct.pack_into('<H', header, 4, len(tokens) if claimed_length is None else claimed_length)
        payload = bytes(header) + name + tokens
        return struct.pack('<HH', 0x18, len(payload)) + payload
    stream = name_record(b'valid', b'\x1e\x01\x00')
    stream += name_record(b'', b'\x1e\x01\x00')
    stream += name_record(b'truncated', b'\x1e', claimed_length=3)
    stream += name_record(b'no_formula', b'')
    assert named_formula_count(stream) == 1


def test_formula_corpus_name_inventory_uses_biff5_fourteen_byte_header():
    """The public biff5.xls NAME at 0xb4 has 14 header bytes before its name."""
    from scripts.probe_xls_formula_corpus import named_formula_count
    def record(kind, payload):
        return struct.pack('<HH', kind, len(payload)) + payload
    bof = record(0x809, struct.pack('<HH', 0x0500, 0x0005))
    header = bytes.fromhex('01 00 00 0f 15 00 01 00 01 00 00 00 00 00')
    tokens = bytes.fromhex('3b ff ff 00 00 00 00 00 00 01 00 00 00 00 00 04 00 77 01 00 05')
    assert named_formula_count(bof + record(0x18, header + b'_FilterDatabase' + tokens)) == 1


def test_formula_probe_recognizes_formula_before_comment_annotation():
    from scripts.probe_xls_formula_pairs import split_formula
    assert split_formula('2,830.07 (=OFFSET(B45,MEP-MNR-1,0,1)) [comment: Marian]') == (
        '2,830.07', 'OFFSET(B45,MEP-MNR-1,0,1)')
