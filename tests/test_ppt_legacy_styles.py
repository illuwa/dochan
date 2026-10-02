"""마스터와 확장 서식의 합성 바이트 회귀 테스트."""
import struct

from dochan.office_binary.officeart import parse_records
from dochan.office_binary.ppt_text import apply_auto_numbers, render_text
from test_ppt_text import block, cf, pf, rec


def master(kind, levels):
    payload = struct.pack('<H', len(levels))
    for level, mask, data in levels:
        if kind >= 5:
            payload += struct.pack('<H', level)
        payload += struct.pack('<II', 0, mask) + data
    return rec(4003, payload, instance=kind)


def test_master_level_inheritance_and_explicit_off():
    from dochan.office_binary.ppt_styles import read_master_styles
    styles = read_master_styles(parse_records(master(1, [
        (0, 0xA0003, struct.pack('<HHh', 3, 32, 30)),
        (1, 1, struct.pack('<H', 0)),
    ])), [])
    b = block('A\rBC', pf(2) + pf(3, level=1) + cf(3) + cf(2, 2, struct.pack('<H', 0)))
    result = render_text(b, None, default_styles=styles)
    a, b, c = result[0].runs[0], result[1].runs[0], result[1].runs[1]
    assert (a.bold, a.italic, a.font_size_pt, a.superscript) == (True, True, 32, True)
    assert (b.bold, b.italic, b.font_size_pt, b.superscript) == (False, True, 32, True)
    assert (c.bold, c.italic) == (False, False)


def test_special_text_type_inherits_body_then_own_style():
    from dochan.office_binary.ppt_styles import read_master_styles
    data = master(1, [(0, 3, struct.pack('<H', 3))])
    data += master(5, [(0, 0x20001, struct.pack('<HH', 0, 24))])
    styles = read_master_styles(parse_records(data), [])
    run = render_text(block('text', text_type=5), None, default_styles=styles)[0].runs[0]
    assert (run.bold, run.italic, run.font_size_pt) == (False, True, 24)


def test_environment_cf_atom_is_below_master_and_slide_overrides():
    from dochan.office_binary.ppt_styles import read_master_styles
    data = rec(4004, struct.pack('<IH', 3, 3))
    data += master(1, [(0, 2, struct.pack('<H', 0))])
    styles = read_master_styles(parse_records(data), [])
    run = render_text(block('A'), None, default_styles=styles)[0].runs[0]
    assert run.bold and not run.italic
    run = render_text(block('A', pf(2) + cf(2, 1, struct.pack('<H', 0))),
                      None, default_styles=styles)[0].runs[0]
    assert not run.bold and not run.italic


def test_master_other_text_style_does_not_leak_into_body_text():
    from dochan.office_binary.ppt_styles import read_master_styles
    data = master(4, [(0, 3, struct.pack('<H', 3))])
    data += master(1, [(0, 0x20000, struct.pack('<H', 24))])
    styles = read_master_styles(parse_records(data), [])
    run = render_text(block('Body'), None, default_styles=styles)[0].runs[0]
    assert not run.bold and not run.italic and run.font_size_pt == 24


def test_character_mask_does_not_enable_absent_flags_and_reads_baseline():
    b = block('A', pf(2) + cf(2, 0x80002, struct.pack('<Hh', 3, -25)))
    run = render_text(b, None)[0].runs[0]
    assert not run.bold and run.italic and run.subscript and not run.superscript


def test_cf9_extension_does_not_discard_later_numbering():
    b = block('A\rB', pf(2, mask=1, props=struct.pack('<H', 1))
              + pf(2, mask=1, props=struct.pack('<H', 1)) + cf(4))
    entry = struct.pack('<IH Hh II I', 0x03000000, 1, 3, 1, 0x100000, 0, 0)
    errors = []
    apply_auto_numbers([b], entry + entry, errors)
    assert b.paragraph_numbers == [(3, 1), (3, 1)]
    assert [p.text for p in render_text(b, None)] == ['1. A', '2. B']
    assert not errors


def test_cf9_truncation_keeps_completed_numbering_and_warns():
    b = block('A\rB', pf(2) + pf(2) + cf(4))
    complete = struct.pack('<IH Hh II I', 0x03000000, 1, 3, 1, 0x100000, 0, 0)
    errors = []
    apply_auto_numbers([b], complete + struct.pack('<IIH', 0, 0x100000, 0), errors)
    assert b.paragraph_numbers[0] == (3, 1)
    assert any('truncated style property' in error for error in errors)


def test_si_bidi_extension_preserves_following_paragraph_numbers():
    b = block('A\rB', pf(2) + pf(2) + cf(4))
    # tdf77747.ppt has the two-byte bidi field after the CF9 mask.
    entry = struct.pack('<IH Hh IIH', 0x03000000, 1, 25, 1, 0, 0x40, 1)
    errors = []
    apply_auto_numbers([b], entry + entry, errors)
    assert b.paragraph_numbers == [(25, 1), (25, 1)]
    assert not errors


def test_truncated_master_retains_completed_level_and_warns():
    from dochan.office_binary.ppt_styles import read_master_styles
    data = master(1, [(0, 1, struct.pack('<H', 1))])
    data = bytearray(data)
    struct.pack_into('<H', data, 8, 2)
    errors = []
    styles = read_master_styles(parse_records(bytes(data)), errors)
    assert render_text(block('A'), None, default_styles=styles)[0].runs[0].bold
    assert errors


def test_slide_inherits_master_even_when_master_objects_are_hidden():
    from dochan.office_binary.ppt import parse_ppt_document_stream
    from test_ppt_structure import presentation, record, sheet, slide_list
    outline = rec(3999, struct.pack('<I', 1)) + rec(4008, b'Inherited')
    data, current = presentation(
        [(2, sheet(master=900, flags=0)),
         (3, record(1016, master(1, [(0, 0x20003, struct.pack('<HH', 3, 24))]), container=True))],
        [slide_list([(2, 256, outline)]), slide_list([(3, 900, b'')], 1)])
    doc = parse_ppt_document_stream(data, current_user=current)
    run = doc.find_all('paragraph')[0].runs[0]
    assert (run.text, run.bold, run.italic, run.font_size_pt) == ('Inherited', True, True, 24)
    assert not doc.errors
