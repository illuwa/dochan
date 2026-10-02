"""Synthetic BIFF tokens for formula review regressions."""
import struct

from dochan.office_binary.xls import _decode_formula_token_stream, _decode_shared_formula_for_cell


def integer(value):
    return b'\x1e' + struct.pack('<H', value)


def function(index):
    return b'\x21' + struct.pack('<H', index)


def test_formula_ftab_fixed_function_preserves_outer_operands():
    # 102 is VLOOKUP, which requires PtgFuncVar; 2 is one-argument ISNA.
    assert _decode_formula_token_stream(integer(7) + integer(1) + function(2) + b'\x03') == '7+ISNA(1)'


def test_formula_zero_arg_function_does_not_consume_outer_operand():
    assert _decode_formula_token_stream(integer(7) + function(34) + b'\x03') == '7+TRUE()'


def test_formula_unknown_fixed_function_warns_and_drops_incomplete_expression():
    errors = []
    assert _decode_formula_token_stream(integer(7) + integer(1) + function(0x7fff), errors=errors) == ''
    assert any('WARN' in message and 'function' in message for message in errors)


def test_formula_unknown_token_warns_and_drops_incomplete_expression():
    errors = []
    assert _decode_formula_token_stream(integer(7) + b'\xff', errors=errors) == ''
    assert any('WARN' in message and 'token' in message for message in errors)


def test_formula_unsigned_integer_preserves_biff_range():
    assert _decode_formula_token_stream(integer(65535)) == '65535'


def test_formula_shared_3d_reference_keeps_stored_coordinate():
    # PtgRef3d uses RgceLoc even in shared formulas, not relative RgceLocRel.
    tokens = b'\x3a' + struct.pack('<3H', 0, 3, 0xc002)
    assert _decode_shared_formula_for_cell(tokens, (1, 1), (2, 2), [(0, 0)], ['Sheet1']) == 'Sheet1!C4'


def test_formula_shared_3d_area_keeps_stored_coordinates():
    tokens = b'\x3b' + struct.pack('<5H', 0, 3, 4, 0xc002, 0xc003)
    assert _decode_shared_formula_for_cell(tokens, (1, 1), (2, 2), [(0, 0)], ['Sheet1']) == 'Sheet1!C4:D5'


def test_formula_external_reference_does_not_masquerade_as_local():
    errors = []
    tokens = b'\x3a' + struct.pack('<3H', 0, 0, 0)
    result = _decode_formula_token_stream(tokens, external_sheets=[(1, 0, 0)], sheet_names=['Local'], internal_supbooks={0}, errors=errors)
    assert 'Local' not in result
    assert errors and 'WARN' in errors[0]


def test_formula_missing_argument_preserves_function_structure():
    tokens = integer(1) + b'\x16' + integer(3) + b'\x22\x03\x01\x00'
    assert _decode_formula_token_stream(tokens) == 'IF(1,,3)'


def test_formula_unknown_variable_function_does_not_consume_outer_operand():
    errors = []
    tokens = integer(7) + integer(1) + b'\x22\x01\xfe\x7f\x03'
    assert _decode_formula_token_stream(tokens, errors=errors) == '7+F32766(1)'
    assert errors


def test_formula_name_value_class_preserves_defined_name():
    assert _decode_formula_token_stream(b'\x43\x01\x00\x00\x00', defined_names=['Revenue']) == 'Revenue'


def test_formula_reference_union_preserves_structure():
    tokens = b'\x24' + struct.pack('<HH', 0, 0xc000) + b'\x24' + struct.pack('<HH', 0, 0xc001) + b'\x10'
    assert _decode_formula_token_stream(tokens) == 'A1,B1'


def test_formula_damaged_operator_warns():
    errors = []
    assert _decode_formula_token_stream(integer(1) + b'\x03', errors=errors) == ''
    assert errors


def test_formula_probe_shared_translation_preserves_literals_and_absolute_refs():
    from scripts.probe_xls_formula_pairs import translate_shared_formula
    assert translate_shared_formula('IF(A1="A1",\'S1\'!$B1+C$2,$D$3)', 'A1', 'B3') == 'IF(B3="A1",\'S1\'!$B3+D$2,$D$3)'


def test_formula_truncated_string_after_header_warns():
    errors = []
    assert _decode_formula_token_stream(integer(1) + b'\x17\x01\x00', errors=errors) == ''
    assert any('truncated string' in message for message in errors)


def test_formula_probe_cache_comparison_distinguishes_formats_and_values():
    from scripts.probe_xls_formula_pairs import classify_cache
    assert classify_cache('2', {'type': 2, 'value': 2.0}) == 'exact'
    assert classify_cache('21.7%', {'type': 2, 'value': 0.217}) == 'number-format equivalent'
    assert classify_cache('1,000.00', {'type': 2, 'value': 1000.0}) == 'number-format equivalent'
    assert classify_cache('0', {'type': 2, 'value': 0.217}) == 'mismatch'


def test_formula_probe_normalization_keeps_intersection_and_strings():
    from scripts.probe_xls_formula_pairs import normalize_formula_presentation
    assert normalize_formula_presentation('TEXT(C2, B2)') == 'TEXT(C2,B2)'
    assert normalize_formula_presentation('SUM(A1 B1) + " A1 + B1 "') == 'SUM(A1 B1)+" A1 + B1 "'


def test_formula_known_variable_function_in_fixed_token_does_not_guess_arity():
    errors = []
    assert _decode_formula_token_stream(integer(7) + integer(1) + function(4), errors=errors) == ''
    assert any('fixed function 4' in message for message in errors)
