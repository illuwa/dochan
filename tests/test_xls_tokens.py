"""Synthetic RPN memory expressions and legacy BIFF regression fixtures."""
import struct

import pytest

from dochan.office_binary.xls import _decode_formula_token_stream, parse_biff_workbook
from dochan.office_binary.xls_formula import FormulaContext
from test_xls_formula_extended import array_extra, formula, int_token, record, string, texts, workbook


def memory(token, expression):
    padding = b'\0' * 4 if token & 0x1f in (6, 7, 8) else b''
    return bytes([token]) + padding + struct.pack('<H', len(expression)) + expression


def ref(row, col):
    return b'\x24' + struct.pack('<HH', row, col)


@pytest.mark.parametrize('token', [0x26, 0x46, 0x66, 0x27, 0x47, 0x67,
                                   0x28, 0x48, 0x68, 0x29, 0x49, 0x69])
def test_memory_tokens_evaluate_the_contained_rpn_once(token):
    expression = ref(0, 0) + ref(1, 1) + b'\x10'
    extra = struct.pack('<H4H', 1, 0, 1, 0, 1) if token & 0x1f == 6 else b''
    errors = []
    assert _decode_formula_token_stream(
        memory(token, expression) + b'\x19\x10\0\0',
        extra_data=extra, errors=errors,
    ) == 'SUM($A$1,$B$2)'
    assert not errors


def test_nested_memory_keeps_outer_stack_and_array_extra_order():
    arr = b'\x20' + b'\0' * 7
    expression = memory(0x26, ref(0, 0) + ref(1, 1) + b'\x10') + ref(2, 2) + b'\x10'
    total = b'\x19\x10\0\0'
    tokens = int_token(9) + memory(0x29, expression) + total + b'\x03' + arr + total + b'\x03'
    extra = struct.pack('<H4H', 1, 0, 1, 0, 1) + array_extra([[2]])
    assert _decode_formula_token_stream(tokens, extra_data=extra) == '9+SUM($A$1,$B$2,$C$3)+SUM({2})'


@pytest.mark.parametrize('tokens,extra', [
    (b'\x29\x05\0' + ref(0, 0)[:-1], b''),
    (b'\x29\x04\0' + ref(0, 0), b''),
    (memory(0x29, b''), b''),
    (memory(0x29, ref(0, 0) + ref(0, 1)), b''),
    (int_token(1) + memory(0x29, int_token(2) + b'\x03') + int_token(3), b''),
    (memory(0x26, ref(0, 0)), b''),
    (memory(0x26, ref(0, 0)), b'\x01\0' + b'\0' * 7),
    (b'\x26\0\0', b''),
    (memory(0x29, b'\x29\xff\xff'), b''),
    (int_token(1) + memory(0x29, b'\x19\x10\0\0' + ref(0, 0)) + b'\x03', b''),
])
def test_bad_memory_keeps_cache_and_warns_without_losing_next_cell(tokens, extra):
    doc = workbook(b'', formula(tokens, extra) + formula(int_token(7), row=1))
    assert texts(doc) == ['42', '42 (=7)']
    assert any('WARN' in error for error in doc.errors)


def test_memory_nesting_is_bounded_without_python_recursion():
    tokens = ref(0, 0)
    for _ in range(300):
        tokens = memory(0x29, tokens)
    errors = []
    assert _decode_formula_token_stream(tokens, errors=errors) == ''
    assert any('limit' in error for error in errors)


def legacy_context():
    context = FormulaContext()
    context.biff_version = 0x0500
    context.codepage = 'cp1252'
    return context


@pytest.mark.parametrize('token', [0x24, 0x44, 0x64])
@pytest.mark.parametrize('flags,expected', [(0, '$C$19'), (0x4000, 'C$19'),
                                          (0x8000, '$C19'), (0xc000, 'C19')])
def test_biff5_ref_stores_relative_flags_in_row_word(token, flags, expected):
    tokens = bytes([token]) + struct.pack('<HB', 18 | flags, 2) + int_token(10) + b'\x05'
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context()) == expected + '*10'


def test_biff5_area_and_relative_offsets_wrap_at_16384_rows():
    area = b'\x25' + struct.pack('<HHBB', 0xc000, 0x8001, 1, 2)
    assert _decode_formula_token_stream(area, formula_context=legacy_context()) == 'B1:$C2'
    relative = b'\x2c' + struct.pack('<HB', 0xffff, 0xff)
    assert _decode_formula_token_stream(relative, base_row=0, base_col=0,
                                        formula_context=legacy_context()) == 'IV16384'


def test_biff5_arean_relative_offsets_use_current_cell():
    tokens = b'\x2d' + struct.pack('<HHBB', 0xffff, 0xc001, 0xfe, 1)
    assert _decode_formula_token_stream(tokens, base_row=2, base_col=3,
                                        formula_context=legacy_context()) == 'B2:E4'


@pytest.mark.parametrize('token,size', [(0x2a, 3), (0x4a, 3), (0x6a, 3),
                                       (0x2b, 6), (0x4b, 6), (0x6b, 6)])
def test_biff5_deleted_reference_width_preserves_next_operator(token, size):
    tokens = bytes([token]) + b'\0' * size + int_token(1) + b'\x03'
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context()) == '#REF!+1'


def test_biff5_string_uses_workbook_codepage_without_unicode_flag():
    context = legacy_context()
    context.codepage = 'cp949'
    raw = '한글'.encode('cp949')
    tokens = b'\x17' + bytes([len(raw)]) + raw
    assert _decode_formula_token_stream(tokens, formula_context=context) == '"한글"'


def test_biff5_workbook_version_reaches_cell_decoder():
    bof = record(0x809, struct.pack('<HH', 0x500, 0x10))
    tokens = b'\x44' + struct.pack('<HB', 18, 2) + int_token(10) + b'\x05'
    doc = parse_biff_workbook(bof + formula(tokens) + record(10))
    assert texts(doc) == ['42 (=$C$19*10)']


def test_biff5_reference_does_not_swallow_following_unary_plus():
    tokens = b'\x44' + struct.pack('<HB', 5, 1) + b'\x12' + int_token(1) + b'\x03'
    assert _decode_formula_token_stream(tokens, formula_context=legacy_context()) == '+$B$6+1'


@pytest.mark.parametrize('token,payload', [(0x39, b'\0' * 24), (0x3a, b'\0' * 17),
                                         (0x20, b'\0' * 7)])
def test_unresolved_biff5_links_and_arrays_do_not_use_biff8_layout(token, payload):
    errors = []
    assert _decode_formula_token_stream(bytes([token]) + payload,
                                        formula_context=legacy_context(), errors=errors) == ''
    assert any('BIFF5' in error for error in errors)


@pytest.mark.parametrize('flags,expected', [(0, 'Revenue'), (1, "'Revenue'")])
def test_elf_lel_uses_deleted_label_index_and_quote_flag(flags, expected):
    tokens = b'\x18\x01' + struct.pack('<HH', 2, flags)
    doc = workbook(record(0x1b9, string('Revenue')), formula(tokens))
    assert texts(doc) == ['42 (=' + expected + ')']
    assert not doc.errors


def test_elf_lel_keeps_invalid_record_slot_and_escapes_apostrophe():
    tokens = b'\x18\x01' + struct.pack('<HH', 3, 1)
    doc = workbook(record(0x1b9, b'\x05') + record(0x1b9, string("O'Brien")), formula(tokens))
    assert texts(doc) == ["42 (='O''Brien')"]
    assert any('Lel' in error for error in doc.errors)


@pytest.mark.parametrize('tokens', [b'\x18', b'\x18\x01\x02\0\0',
                                   b'\x18\x01\0\0\0\0', b'\x18\x01\x03\0\0\0',
                                   b'\x18\x02\x02\0\0\0'])
def test_unresolved_elf_labels_warn_and_preserve_cache(tokens):
    doc = workbook(record(0x1b9, string('Revenue')), formula(tokens))
    assert texts(doc) == ['42']
    assert any('WARN' in error for error in doc.errors)


@pytest.mark.parametrize('bounds', [(2, 1, 0, 0), (0, 0, 2, 1), (0, 0, 0, 256)])
def test_memory_extra_rejects_invalid_ranges(bounds):
    extra = struct.pack('<H4H', 1, *bounds)
    doc = workbook(b'', formula(memory(0x26, ref(0, 0) + ref(1, 1) + b'\x10'), extra))
    assert texts(doc) == ['42']
    assert any('invalid memory reference range' in error for error in doc.errors)


def test_elf_lel_table_count_is_bounded_without_shifting_indices():
    context = FormulaContext()
    errors = []
    for _ in range(2047):
        context.add_deleted_label(string('Last'), errors)
    context.add_deleted_label(string('Overflow'), errors)
    assert len(context.deleted_labels) == 2047
    assert context.deleted_label(2048, False) == 'Last'
    assert len(errors) == 1 and 'limit' in errors[0]


def test_biff5_shared_formula_context_reaches_anchor_and_follower():
    bof = record(0x809, struct.pack('<HH', 0x500, 0x10))
    tokens = b'\x4c\x00\xc0\xfe\x4c\x00\xc0\xff\x03'
    exp = b'\x01' + struct.pack('<HH', 5, 4)
    def cell(row):
        data = bytearray(formula(exp, row=row))
        struct.pack_into('<H', data, 6, 4)
        return bytes(data)
    shared = record(0x4bc, struct.pack('<HHBBBBH', 5, 6, 4, 4, 0, 2, len(tokens)) + tokens)
    doc = parse_biff_workbook(bof + cell(5) + shared + cell(6) + record(10))
    assert [text for text in texts(doc) if text] == ['42 (=C6+D6)', '42 (=C7+D7)']


def test_biff5_codepage_record_reaches_string_formula():
    bof = record(0x809, struct.pack('<HH', 0x500, 0x10))
    data = '한글'.encode('cp949')
    doc = parse_biff_workbook(bof + record(0x42, struct.pack('<H', 949))
                              + formula(b'\x17' + bytes([len(data)]) + data) + record(10))
    assert texts(doc) == ['42 (=\"한글\")']


def test_biff5_memarea_consumes_six_byte_ranges():
    tokens = bytes.fromhex('2600000000090024000000240100011019100000')
    extra = bytes.fromhex('0100000001000001')
    errors = []
    assert _decode_formula_token_stream(tokens, extra_data=extra,
                                        formula_context=legacy_context(), errors=errors) == 'SUM($A$1,$B$2)'
    assert not errors


@pytest.mark.parametrize('codepage,raw,expected', [
    (32768, b'\x80', 'Ä'),
    (32769, b'\x80', '€'),
    (32769, b'\x81', '\ufffd'),
])
def test_biff5_legacy_codepages_and_invalid_bytes_keep_formula(codepage, raw, expected):
    bof = record(0x809, struct.pack('<HH', 0x500, 0x10))
    doc = parse_biff_workbook(bof + record(0x42, struct.pack('<H', codepage))
                              + formula(b'\x17\x01' + raw) + record(10))
    assert texts(doc) == ['42 (=\"' + expected + '\")']
    assert not doc.errors


def test_ptgexp_inside_memory_frame_warns_and_keeps_cache():
    errors = []
    assert _decode_formula_token_stream(b'\x29\x05\x00\x01\0\0\0\0', errors=errors) == ''
    assert any('PtgExp' in error for error in errors)


def test_biff5_boundsheet_and_name_use_legacy_byte_strings():
    bof = record(0x809, struct.pack('<HH', 0x500, 0x05))
    sheet_bof = record(0x809, struct.pack('<HH', 0x500, 0x10))
    name_bytes = b'Revenue'
    name_header = struct.pack('<HBBHHH4B', 0, 0, len(name_bytes), 3, 0, 0, 0, 0, 0, 0)
    defined_name = record(0x18, name_header + name_bytes + int_token(7))
    sheet = sheet_bof + formula(int_token(2)) + record(10)
    sheet_name = b'Feuil1'
    bound_size = 4 + 7 + len(sheet_name)
    bound = record(0x85, struct.pack('<IBBB', len(bof) + len(defined_name) + bound_size,
                                    0, 0, len(sheet_name)) + sheet_name)
    doc = parse_biff_workbook(bof + defined_name + bound + sheet)
    assert [section.provenance.sheet for section in doc.sections] == ['Feuil1']
    assert doc.sections[0].elements[0].text == 'Defined name: Revenue = 7'
    assert texts(doc) == ['42 (=2)']
    assert not doc.errors


def test_biff8_compressed_name_ignores_workbook_codepage_1200():
    bof = record(0x809, struct.pack('<HH', 0x600, 0x05))
    label = b'Revenue'
    header = struct.pack('<HBBHHH4B', 0, 0, len(label), 3, 0, 0, 0, 0, 0, 0)
    defined_name = record(0x18, header + b'\0' + label + int_token(7))
    doc = parse_biff_workbook(bof + record(0x42, struct.pack('<H', 1200))
                              + defined_name + record(10))
    assert doc.sections[0].elements[0].text == 'Defined name: Revenue = 7'


def test_biff5_unknown_codepage_does_not_abort_sheet_and_name():
    bof = record(0x809, struct.pack('<HH', 0x500, 0x05))
    header = struct.pack('<HBBHHH4B', 0, 0, 3, 3, 0, 0, 0, 0, 0, 0)
    defined_name = record(0x18, header + b'Foo' + int_token(7))
    sheet = record(0x809, struct.pack('<HH', 0x500, 0x10)) + formula(int_token(2)) + record(10)
    name = b'Data'
    bound_size = 4 + 7 + len(name)
    globals_ = bof + record(0x42, struct.pack('<H', 65000)) + defined_name
    bound = record(0x85, struct.pack('<IBBB', len(globals_) + bound_size, 0, 0,
                                    len(name)) + name)
    doc = parse_biff_workbook(globals_ + bound + sheet)
    assert doc.sections[0].provenance.sheet == 'Data'
    assert doc.sections[0].elements[0].text == 'Defined name: Foo = 7'
