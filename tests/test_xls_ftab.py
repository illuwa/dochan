"""Ftab facts and synthetic BIFF tokens; no external corpus needed in CI."""
import struct

import pytest

from dochan.office_binary.xls import _decode_formula_token_stream


def integer(value):
    return b'\x1e' + struct.pack('<H', value)


@pytest.mark.parametrize('index,name,count', [
    (3, 'ISERROR', 1), (15, 'SIN', 1), (19, 'PI', 0),
    (40, 'DCOUNT', 3), (48, 'TEXT', 2), (65, 'DATE', 3),
    (117, 'EXACT', 2), (165, 'MMULT', 2), (252, 'FREQUENCY', 2),
    (273, 'BINOMDIST', 4), (337, 'POWER', 2), (358, 'GETPIVOTDATA', None),
    (378, 'THAIYEAR', 1), (379, 'RTD', None),
])
def test_ftab_spec_samples_preserve_outer_operand(index, name, count):
    # PtgFunc has no arity byte; PtgFuncVar supplies it even for optional args.
    argc = 4 if count is None else count
    token = (b'\x22' + bytes([argc]) if count is None else b'\x21')
    tokens = integer(99) + b''.join(integer(i) for i in range(argc))
    tokens += token + struct.pack('<H', index) + b'\x03'
    errors = []
    assert _decode_formula_token_stream(tokens, errors=errors) == (
        '99+' + name + '(' + ','.join(str(i) for i in range(argc)) + ')')
    assert errors == []


@pytest.mark.parametrize('grammar,expected', [
    ('This function takes no parameters', (0, 0)),
    ('x-params = ref, (ref / val), (ref / val)', (3, 3)),
    ('x-params = val, *2(ref / val)', (1, 3)),
    ('x-params = [val, [(ref / val), [ref]]]', (0, 3)),
    ('x-params = (ref / val), (ref / val), [val, [val, *13(val, val)]]', (2, 30)),
])
def test_ftab_grammar_counts_arguments(grammar, expected):
    from scripts.generate_xls_ftab import argument_bounds
    assert argument_bounds(grammar) == expected


@pytest.mark.parametrize('grammar', [
    'x-params = unknown', 'x-params = val,', 'x-params = [val',
    'x-params = val garbage', 'x-params =', 'x-params = *999999(val)',
    'x-params = ' + '(' * 40 + 'val' + ')' * 40,
])
def test_ftab_generator_rejects_unrecognized_or_unbounded_grammar(grammar):
    from scripts.generate_xls_ftab import argument_bounds
    with pytest.raises(ValueError):
        argument_bounds(grammar)


def test_ftab_generator_extracts_rows_and_keeps_variable_out_of_fixed_table():
    from scripts.generate_xls_ftab import parse_rows, render_module
    rows = [['Value', 'Meaning'], ['0x0013', 'PI'],
            ['', 'This function takes no parameters'],
            ['0x0028', 'DCOUNT'], ['', 'dcount-params = ref, (ref / val), (ref / val)'],
            ['0x0005', 'AVERAGE'], ['', 'average-params = (ref / val), *29(ref / val)']]
    entries = parse_rows(rows)
    scope = {}
    exec(render_module(entries, 'synthetic'), scope)
    assert scope['FUNCTION_NAMES'] == {19: 'PI', 40: 'DCOUNT', 5: 'AVERAGE'}
    assert scope['FIXED_ARGUMENT_COUNTS'] == {19: 0, 40: 3}


@pytest.mark.parametrize('rows', [
    [['0x0001', 'IF']],
    [['0x0001', 'IF'], ['', 'sum-params = val']],
    [['0x0001', 'IF'], ['', 'if-params = val'], ['0x0001', 'IF'], ['', 'if-params = val']],
    [['0xFFFFF', 'BAD'], ['', 'bad-params = val']],
])
def test_ftab_generator_rejects_incomplete_or_conflicting_rows(rows):
    from scripts.generate_xls_ftab import parse_rows
    with pytest.raises(ValueError):
        parse_rows(rows)


def test_ftab_generated_table_coverage():
    from dochan.office_binary.xls_ftab import FUNCTION_NAMES, FIXED_ARGUMENT_COUNTS
    # All rows in the supplied MS-XLS Ftab table, including macro functions/UDF.
    assert len(FUNCTION_NAMES) == 373
    assert FUNCTION_NAMES[255] == 'User Defined Function'
    assert FUNCTION_NAMES[379] == 'RTD'
    assert 5 not in FIXED_ARGUMENT_COUNTS
    assert 255 not in FIXED_ARGUMENT_COUNTS


def test_ftab_udf_keeps_existing_unknown_warning_and_stack_contract():
    errors = []
    tokens = integer(99) + integer(1) + b'\x22\x01\xff\x00\x03'
    assert _decode_formula_token_stream(tokens, errors=errors) == '99+F255(1)'
    assert any('unknown variable function 255' in error for error in errors)


def test_ftab_all_fixed_functions_decode_all_token_classes():
    from dochan.office_binary.xls_ftab import FUNCTION_NAMES, FIXED_ARGUMENT_COUNTS
    for index, count in FIXED_ARGUMENT_COUNTS.items():
        arguments = b''.join(integer(i) for i in range(count))
        expected = '99+' + FUNCTION_NAMES[index] + '(' + ','.join(map(str, range(count))) + ')'
        for token in (0x21, 0x41, 0x61):
            errors = []
            tokens = integer(99) + arguments + bytes([token]) + struct.pack('<H', index) + b'\x03'
            assert _decode_formula_token_stream(tokens, errors=errors) == expected
            assert errors == []


def test_ftab_resume_is_known_variable_function():
    errors = []
    assert _decode_formula_token_stream(b'\x22\x00\xfb\x00', errors=errors) == 'RESUME()'
    assert errors == []


@pytest.mark.parametrize('source,expected', [
    ('SUM( A1 , B1 ) + 2', 'SUM(A1,B1)+2'),
    ('SUM(A1) B1', 'SUM(A1) B1'),
    ('A1 (B1)', 'A1 (B1)'),
    ('(A1) (B1)', '(A1) (B1)'),
    ('IF(A1="a + b",Table1[A + B],\'a + b\'!C1)', 'IF(A1="a + b",Table1[A + B],\'a + b\'!C1)'),
])
def test_ftab_probe_spacing_preserves_intersections_and_identifiers(source, expected):
    from scripts.probe_xls_formula_pairs import normalize_formula_presentation
    assert normalize_formula_presentation(source) == expected


@pytest.mark.parametrize('expected,actual,category', [
    ('SUM(A1)', 'SUM(A1)', 'exact'),
    ('TEXT(C2, B2)', 'TEXT(C2,B2)', 'whitespace'),
    ('Sheet1!A1', "'Sheet1'!A1", 'sheet quotes or function prefix'),
    ('Sheet1:Sheet2!A1', "'Sheet1:Sheet2'!A1", 'sheet quotes or function prefix'),
    ('_xlfn.COUNTIFS(A1,1)', 'COUNTIFS(A1,1)', 'sheet quotes or function prefix'),
    ('A1+$B$2', '$A$1+B2', 'absolute reference markers only'),
    ('A1', 'B1', 'mismatch'),
    ('COUNTIFS(A1,1)', 'F255(_xlfn.COUNTIFS,A1,1)', 'mismatch'),
    ('SUM(A1 B1)', 'SUM(A1B1)', 'mismatch'),
    ('"$A$1"', '"A1"', 'mismatch'),
    ('"_xlfn.FOO()"', '"FOO()"', 'mismatch'),
    ('Table1[$A$1]', 'Table1[A1]', 'mismatch'),
])
def test_ftab_probe_classifies_normalization_without_masking_missing_structure(expected, actual, category):
    from scripts.probe_xls_formula_pairs import formula_comparison
    assert formula_comparison(expected, actual) == category


def test_ftab_probe_raw_source_distinguishes_absent_formula_from_missing_sheet():
    from scripts.probe_xls_formula_pairs import workbook_formula_evidence
    def record(kind, payload):
        return struct.pack('<HH', kind, len(payload)) + payload
    # A single BOUNDSHEET followed by one FORMULA at B2.
    bound = record(0x85, struct.pack('<IBBBB', 18, 0, 0, 6, 0) + b'Sheet1')
    tokens = integer(3)
    formula = struct.pack('<HHH', 1, 1, 0) + b'\0' * 14 + struct.pack('<H', len(tokens)) + tokens
    data = bound + record(6, formula)
    wanted = [('Sheet1', 'B2'), ('Sheet1', 'C3'), ('Absent', 'A1')]
    found, sheets = workbook_formula_evidence(data, wanted)
    assert sheets == ['Sheet1']
    assert found[('Sheet1', 'B2')]['tokens'] == tokens.hex()
    assert ('Sheet1', 'C3') not in found
    assert ('Absent', 'A1') not in found


def test_ftab_probe_raw_source_resolves_array_anchor_evidence():
    from scripts.probe_xls_formula_pairs import workbook_formula_evidence
    def record(kind, payload):
        return struct.pack('<HH', kind, len(payload)) + payload
    bound = record(0x85, struct.pack('<IBBBB', 18, 0, 0, 6, 0) + b'Sheet1')
    exp = b'\x01' + struct.pack('<HH', 1, 1)
    formula = struct.pack('<HHH', 1, 1, 0) + b'\0' * 14 + struct.pack('<H', len(exp)) + exp
    template = b'\x20' + b'\0' * 7
    array = struct.pack('<HHBB', 1, 1, 1, 1) + b'\0' * 6 + struct.pack('<H', len(template)) + template
    found, _ = workbook_formula_evidence(bound + record(6, formula) + record(0x221, array), [('Sheet1', 'B2')])
    assert found[('Sheet1', 'B2')]['array_template'] == template.hex()
    assert any('token 0x20' in warning for warning in found[('Sheet1', 'B2')]['token_warnings'])
