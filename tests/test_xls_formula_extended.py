"""Synthetic MS-XLS records; public Office files are only used by the probe."""
import struct

import pytest

from dochan.office_binary.xls import _decode_formula_token_stream, parse_biff_workbook


def record(kind, data=b''):
    return struct.pack('<HH', kind, len(data)) + data


def string(text, short=False):
    return struct.pack('<B' if short else '<H', len(text)) + b'\x01' + text.encode('utf-16-le')


def supbook(sheets=('Remote',), path='\x01source.xls'):
    return record(0x1ae, struct.pack('<H', len(sheets)) + string(path)
                  + b''.join(string(s) for s in sheets))


def name(label, scope=0, tokens=b'\x1c\x1d', extra=b''):
    header = struct.pack('<HBBHHH4B', 0, 0, len(label), len(tokens), 0, scope, 0, 0, 0, 0)
    return record(0x18, header + string(label, True)[1:] + tokens + extra)


def externname(label, scope=0, flags=0):
    return record(0x23, struct.pack('<HHH', flags, scope, 0) + string(label, True) + b'\x02\x00\x1c\x17')


def xti(*entries):
    return record(0x17, struct.pack('<H', len(entries)) + b''.join(struct.pack('<3H', *e) for e in entries))


def int_token(n):
    return b'\x1e' + struct.pack('<H', n)


def namex(index=1, ref=0, token=0x39):
    return bytes([token]) + struct.pack('<HI', ref, index)


def udf(count):
    return b'\x42' + struct.pack('<BH', count, 255)


def formula(tokens, extra=b'', row=0):
    return record(6, struct.pack('<3H', row, 0, 0) + struct.pack('<d', 42)
                  + struct.pack('<HIH', 0, 0, len(tokens)) + tokens + extra)


def workbook(globals_, body):
    bof = record(0x809, struct.pack('<HH', 0x600, 0x10))
    label = b'Local'
    start = len(globals_) + len(bof) + 12 + len(label)
    bound = record(0x85, struct.pack('<IBBBB', start, 0, 0, len(label), 0) + label)
    return parse_biff_workbook(bof + bound + globals_ + bof + body + record(10))


def texts(doc):
    return [c.text for s in doc.sections for e in s.elements for r in getattr(e, 'rows', []) for c in r]


@pytest.mark.parametrize('token', [0x3a, 0x5a, 0x7a])
def test_formula_external_supbook_uses_external_link_ordinal(token):
    globals_ = record(0x1ae, b'\x01\x00\x01\x04') + record(0x1ae, b'\x01\x00\x01\x3a')
    globals_ += supbook() + supbook(('Other',), '\x01other.xls') + xti((2, 0, 0), (3, 0, 0))
    doc = workbook(globals_, formula(bytes([token]) + struct.pack('<3H', 0, 2, 0xc001))
                   + formula(bytes([token]) + struct.pack('<3H', 1, 2, 1), row=1))
    assert texts(doc) == ['42 (=[1]Remote!B3)', '42 (=[2]Other!$B$3)']
    assert not doc.errors


def test_formula_external_area_quotes_entire_sheet_range():
    doc = workbook(supbook(("O'Brien", 'Last sheet')) + xti((0, 0, 1)),
                   formula(b'\x3b' + struct.pack('<5H', 0, 0, 2, 0, 1)))
    assert texts(doc) == ["42 (='[1]O''Brien:Last sheet'!$A$1:$B$3)"]


@pytest.mark.parametrize('token', [0x39, 0x59, 0x79])
def test_formula_namex_internal_scope_comes_from_name_record(token):
    globals_ = record(0x1ae, b'\x01\x00\x01\x04') + xti((0, 0xfffe, 0xfffe))
    globals_ += name('Global') + name('Scoped', scope=1)
    doc = workbook(globals_, formula(namex(1, token=token)) + formula(namex(2, token=token), row=1))
    assert texts(doc) == ['42 (=[0]!Global)', '42 (=Local!Scoped)']


def test_formula_namex_external_name_and_scoped_name():
    doc = workbook(supbook(('Remote',)) + externname('Global') + externname('Scoped', 1) + xti((0, 0xfffe, 0xfffe)),
                   formula(namex()) + formula(namex(2), row=1))
    assert texts(doc) == ['42 (=[1]!Global)', '42 (=[1]Remote!Scoped)']


@pytest.mark.parametrize('label,expected', [('DELTA', 'DELTA'), ('_xll.Custom', '_xll.Custom'), ('_xlfn.COUNTIFS', 'COUNTIFS')])
def test_formula_addin_udf_consumes_name_operand_only(label, expected):
    globals_ = record(0x1ae, b'\x01\x00\x01\x3a') + externname(label) + xti((0, 0xfffe, 0xfffe))
    doc = workbook(globals_, formula(int_token(7) + namex() + int_token(2) + udf(2) + b'\x03'))
    assert texts(doc) == ['42 (=7+%s(2))' % expected]
    assert not doc.errors


def test_formula_udf_defined_name_and_prefix_literal_are_distinct():
    tokens = b'\x23\x01\x00\x00\x00' + int_token(2) + udf(2)
    doc = workbook(name('_xlfn.COUNTIFS'), formula(tokens))
    assert texts(doc) == ['42 (=COUNTIFS(2))']
    assert _decode_formula_token_stream(b'\x17\x07\x00_xlfn.X') == '"_xlfn.X"'


def array_extra(rows):
    values = []
    for row in rows:
        for v in row:
            if isinstance(v, bool):
                values.append(b'\x04' + bytes([v]) + b'\0' * 7)
            elif isinstance(v, str):
                values.append(b'\x02' + string(v))
            else:
                values.append(b'\x01' + struct.pack('<d', v))
    return struct.pack('<BH', len(rows[0]) - 1, len(rows) - 1) + b''.join(values)


@pytest.mark.parametrize('token', [0x20, 0x40, 0x60])
def test_formula_array_constant_rgcb_and_multiple_arrays(token):
    arr = bytes([token]) + b'\0' * 7
    doc = workbook(b'', formula(arr + arr + b'\x03', array_extra([[1, 2], [3, 4]]) + array_extra([[5]])))
    assert texts(doc) == ['42 (={1,2;3,4}+{5})']
    assert not doc.errors


def test_formula_array_unicode_quotes_booleans_errors():
    extra = array_extra([['한"글', True]])
    extra = bytes([2]) + extra[1:] + b'\x10\x07' + b'\0' * 7
    doc = workbook(b'', formula(b'\x20' + b'\0' * 7, extra))
    assert texts(doc) == ['42 (={"한""글",TRUE,#DIV/0!})']


def test_formula_array_template_and_followers_receive_extra_data():
    tokens = b'\x60' + b'\0' * 7 + b'\x21\x53\x00'
    template = record(0x221, struct.pack('<HHBB', 0, 1, 0, 0) + b'\0' * 6
                      + struct.pack('<H', len(tokens)) + tokens + array_extra([[1, 2]]))
    exp = b'\x01' + b'\0' * 4
    doc = workbook(b'', formula(exp) + template + formula(exp, row=1))
    assert texts(doc) == ['42 (=TRANSPOSE({1,2}))', '42']


def test_formula_defined_name_array_extra():
    doc = workbook(name('Matrix', tokens=b'\x20' + b'\0' * 7, extra=array_extra([[1, 2]])), formula(int_token(1)))
    assert doc.sections[0].elements[0].text == 'Defined name: Matrix = {1,2}'


@pytest.mark.parametrize('extra', [b'', b'\xff\xff\xff', b'\0\0\0\x01', b'\0\0\0\x77' + b'\0' * 8,
                                  b'\0\0\0\x01' + struct.pack('<d', float('nan'))])
def test_formula_damaged_array_keeps_cache_and_warns(extra):
    doc = workbook(b'', formula(b'\x20' + b'\0' * 7, extra) + formula(int_token(1), row=1))
    assert texts(doc) == ['42', '42 (=1)']
    assert any('WARN' in e and 'array' in e.lower() for e in doc.errors)


@pytest.mark.parametrize('globals_,tokens', [
    (supbook() + xti((0, 9, 9)), b'\x3a' + b'\0' * 6),
    (record(0x1ae, b'\x01') + xti((0, 0, 0)), b'\x3a' + b'\0' * 6),
    (supbook() + xti((0, 0, 0)), namex(99)),
    (supbook() + externname('DDE', flags=0x10) + xti((0, 0, 0)), namex()),
])
def test_formula_damaged_external_metadata_warns_without_local_alias(globals_, tokens):
    doc = workbook(globals_, formula(tokens) + formula(int_token(1), row=1))
    assert 'Local!' not in texts(doc)[0]
    assert texts(doc)[1] == '42 (=1)'
    assert doc.errors and all(e.startswith('WARN') for e in doc.errors)


def test_formula_invalid_name_does_not_shift_following_indexes():
    doc = workbook(record(0x18, b'\0' * 14 + b'\0') + name('Valid'),
                   formula(b'\x23\x02\x00\x00\x00'))
    assert texts(doc) == ['42 (=Valid)']


def test_formula_shared_array_extra_reaches_anchor_and_follower():
    tokens = b'\x20' + b'\0' * 7
    template = record(0x4bc, struct.pack('<HHBBBBH', 0, 1, 0, 0, 0, 2, len(tokens))
                      + tokens + array_extra([[1, 2]]))
    exp = b'\x01' + b'\0' * 4
    doc = workbook(b'', formula(exp) + template + formula(exp, row=1))
    assert texts(doc) == ['42 (={1,2})'] * 2


def test_formula_probe_uses_link_context_and_array_extra():
    from scripts.probe_xls_formula_pairs import workbook_formula_evidence
    globals_ = record(0x1ae, b'\x01\x00\x01\x3a') + externname('DELTA') + xti((0, 0xfffe, 0xfffe))
    bound = record(0x85, struct.pack('<IBBBB', 17 + len(globals_), 0, 0, 5, 0) + b'Local')
    data = bound + globals_ + formula(namex() + int_token(1) + udf(2))
    data += formula(b'\x20' + b'\0' * 7, array_extra([[1, 2]]), row=1)
    evidence, _ = workbook_formula_evidence(data, [('Local', 'A1'), ('Local', 'A2')])
    assert evidence[('Local', 'A1')]['token_warnings'] == []
    assert evidence[('Local', 'A2')]['token_warnings'] == []
    assert evidence[('Local', 'A2')]['extra_data'] == array_extra([[1, 2]]).hex()


def test_formula_probe_distinguishes_external_link_spelling():
    from scripts.probe_xls_formula_pairs import mismatch_cause
    check = {'comparison': 'mismatch', 'sheet': 'Local', 'expected': "['file:///source.xlsx']S!A1",
             'actual': '[1]S!$A$1'}
    # Absolute-reference markers differ too; workbook-only normalization must
    # not conceal that difference (review P3-6).
    assert mismatch_cause(check, {'token_warnings': []}, ['Local']) == 'unclassified mismatch'


def test_formula_array_text_limit_keeps_cached_value():
    # Two valid string values together exceed the rendered-expression budget.
    extra = (struct.pack('<BH', 1, 0) + b'\x02' + struct.pack('<HB', 33000, 0)
             + b'a' * 33000 + b'\x02' + struct.pack('<HB', 33000, 0) + b'b' * 33000)
    errors = []
    assert _decode_formula_token_stream(b'\x20' + b'\0' * 7, extra_data=extra, errors=errors) == ''
    assert any('limit' in e for e in errors)


def test_formula_supbook_limit_does_not_attach_names_to_previous_book(monkeypatch):
    from dochan.office_binary import xls_formula
    monkeypatch.setattr(xls_formula, 'MAX_LINK_ENTRIES', 1)
    context = xls_formula.FormulaContext()
    errors = []
    context.add_supbook(b'\x01\x00\x01\x3a', errors)
    context.add_supbook(b'\x01\x00\x01\x3a', errors)
    context.add_externname(externname('WrongBook')[4:], errors)
    assert context.books[0].names == []
    assert any('limit' in e for e in errors)
