"""Synthetic regressions for text semantics and older/newer MTEF encodings."""
import struct

import pytest

from dochan.office_binary.mtef import MTEFError, parse_mtef


def char(text, face=0x83, version=5, options=0, suffix=b''):
    return b''.join(bytes((2, options, face)) + struct.pack('<H', ord(c)) + suffix
                    if version == 5 else bytes((2, face, ord(c))) for c in text)


def equation(body, version=5):
    return (b'\x05\x01\x00\x05\x00DSMT5\0\0\x01\0' + body + b'\0\0'
            if version == 5 else bytes((version, 0, 1, 10, 0, 10, 1)) + body + b'\0\0')


def test_fntext_runs_preserve_spaces_and_math_boundaries():
    assert parse_mtef(equation(char('for all ', 0x81) + char('x'))) == r'\text{for all }x'
    assert parse_mtef(equation(char('a~b%_{', 0x81))) == r'\text{a\textasciitilde{}b\%\_\{}'


def test_math_literal_tilde_stays_visible():
    assert parse_mtef(equation(char('a~b'))) == r'a\sim b'


@pytest.mark.parametrize('version', [2, 3, 5])
def test_fntext_in_each_mtef_version(version):
    body = char('a b', 0x81, version=2)
    if version == 3:
        body = b''.join(b'\x02\x81' + struct.pack('<H', ord(c)) for c in 'a b')
    elif version == 5:
        body = char('a b', 0x81)
    assert parse_mtef(equation(body, version)) == r'\text{a b}'


def test_v2_single_byte_symbol_and_fraction():
    assert parse_mtef(equation(char('\xc7', 0x86, 2), 2)) == r'\cap'
    assert parse_mtef(equation(char('\xc4', 0x86, 2), 2)) == r'\otimes'
    body = b'\x03\x0e\0\0\x01' + char('a', version=2) + b'\0\x01' + char('b', version=2) + b'\0\0'
    assert parse_mtef(equation(body, 2)) == r'\frac{a}{b}'


def test_v2_unknown_font_is_not_guessed_as_ascii():
    with pytest.raises(MTEFError):
        parse_mtef(equation(char('K', 0x8b, 2), 2))


def test_v2_symbol_radical_extension_is_not_ascii_backtick():
    with pytest.raises(MTEFError):
        parse_mtef(equation(char('`', 0x86, 2), 2))


def test_v5_definition_records_and_packed_preferences():
    # Preference dimensions end in nibble F.
    prefs = b'\x12\0\x02\x21\x2f\x2f\x01\x41\x0f\x02\x01\0\0'
    defs = b'\x13WinAllBasicCodePages\0\x11\x05Times New Roman\0' + prefs
    assert parse_mtef(equation(defs + char('x'))) == 'x'
    # Two sizes share a byte: 2,1,F,2,F,padding. Consume padding only at list end.
    shared = b'\x12\0\x02\x21\xf2\xf0\0\0'
    assert parse_mtef(equation(shared + char('x'))) == 'x'


@pytest.mark.parametrize('record', [b'\x13unterminated', b'\x11\x05unterminated',
                                    b'\x12\0\xff', b'\x12\0\x01\x22'])
def test_truncated_v5_definitions_fail_closed(record):
    with pytest.raises(MTEFError):
        parse_mtef(b'\x05\x01\0\x05\0DSMT5\0\0' + record)


def test_v5_font_position_is_metadata_when_mtcode_present():
    assert parse_mtef(equation(char('×', 0x86, options=4, suffix=b'\xb4'))) == r'\times'
    assert parse_mtef(equation(char('x', options=16, suffix=b'\x34\x12'))) == 'x'
    with pytest.raises(MTEFError):
        parse_mtef(equation(b'\x02\x20\x83'))


def test_v5_fence_and_full_size_fraction():
    slot = lambda b: b'\x01\0' + b + b'\0'
    frac = b'\x03\0\x0b\x02\0' + slot(char('a')) + slot(char('b')) + b'\0'
    fence = b'\x03\0\x01\x03\0' + slot(frac) + char('(', 0x96) + char(')', 0x96) + b'\0'
    assert parse_mtef(equation(fence)) == r'\left(\frac{a}{b}\right)'


def test_mathtype_private_spacing_codes():
    # Preserve explicit spacing semantically; typography widths are not inferred.
    assert parse_mtef(equation(char('x\ueb01y\ueb02z\ueb04w'))) == r'x{\ }y{\ }z{\ }w'
    assert parse_mtef(equation(char('x\ueb01'))) == r'x{\ }'
    with pytest.raises(MTEFError):
        parse_mtef(equation(char('\uebff')))
