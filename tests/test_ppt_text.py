"""Synthetic PPT text records; real Office samples stay outside the repository."""
import struct

from dochan.conversion import Provenance
from dochan.office_binary.officeart import parse_records
from dochan.office_binary.ppt_text import (
    read_hyperlinks, render_text, shape_hyperlink, text_blocks,
)


def rec(kind, data=b'', instance=0, container=False):
    return struct.pack('<HHI', instance * 16 + (15 if container else 0), kind, len(data)) + data


def block(text, style=b'', tail=b'', text_type=1):
    data = rec(3999, struct.pack('<I', text_type)) + rec(4000, text.encode('utf-16le'))
    if style:
        data += rec(4001, style)
    return text_blocks(parse_records(data + tail))[0]


def pf(count, level=0, mask=0, props=b''):
    return struct.pack('<IHI', count, level, mask) + props


def cf(count, mask=0, props=b''):
    return struct.pack('<II', count, mask) + props


def interaction(link_id):
    return rec(4082, rec(4083, struct.pack('<IIBBBBB3x', 0, link_id, 4, 0, 0, 0, 8)), container=True)


def test_ppt_text_preserves_unicode_and_separates_headers():
    records = parse_records(rec(3999, struct.pack('<I', 0)) + rec(4000, '제목'.encode('utf-16le'))
                            + rec(3999, struct.pack('<I', 1)) + rec(4008, b'body'))
    blocks = text_blocks(records)
    assert [b.text for b in blocks] == ['제목', 'body']
    assert [p.heading_level for b in blocks for p in render_text(b, None)] == [1, 0]


def test_ppt_text_character_styles_and_paragraph_levels():
    style = pf(2) + pf(3, 2) + cf(1, 1, b'\x01\x00') + cf(1) + cf(1, 2, b'\x02\x00') + cf(2, 4, b'\x04\x00')
    b = block('A\rBC', style)
    provenance = Provenance(source_format='ppt', slide=1, path='PowerPoint Document')
    paragraphs = render_text(b, provenance)
    assert [p.text for p in paragraphs] == ['A', 'BC']
    assert paragraphs[0].runs[0].bold
    assert paragraphs[1].runs[0].italic
    assert paragraphs[1].runs[1].underline
    assert b.paragraph_levels == [(0, 2, 0), (2, 5, 2)]
    assert paragraphs[1].runs[1].provenance == provenance


def test_ppt_text_character_style_offsets_are_utf16_units():
    style = pf(5) + cf(2, 1, b'\x01\x00') + cf(3, 2, b'\x02\x00')
    paragraphs = render_text(block('😀BC', style), None)
    assert [(r.text, r.bold, r.italic) for r in paragraphs[0].runs] == [('😀', True, False), ('BC', False, True)]


def test_ppt_text_style_skips_optional_properties_in_wire_order():
    style = pf(4, mask=0x1800, props=struct.pack('<HH', 2, 80))
    style += cf(1, 0x070001, struct.pack('<HHHI', 1, 2, 24, 0x123456)) + cf(3, 2, b'\x02\x00')
    runs = render_text(block('ABC', style), None)[0].runs
    assert runs[0].bold and runs[0].font_size_pt == 24
    assert runs[1].text == 'BC' and runs[1].italic


def test_ppt_text_links_apply_only_to_character_range():
    tail = interaction(7) + rec(4063, struct.pack('<II', 2, 6))
    paragraphs = render_text(block('a link z', tail=tail), None, {7: 'https://example.com'})
    assert paragraphs[0].text == 'a link <https://example.com> z'


def test_ppt_text_link_including_paragraph_terminator_has_no_lost_text():
    tail = interaction(7) + rec(4063, struct.pack('<II', 0, 5))
    paragraphs = render_text(block('link\rnext', tail=tail), None, {7: 'https://example.com'})
    assert [p.text for p in paragraphs] == ['link <https://example.com>', 'next']


def test_ppt_text_shape_link_follows_pptx_suffix_contract():
    records = parse_records(interaction(7))
    assert shape_hyperlink(records, {7: 'https://example.com'}) == 'https://example.com'
    assert render_text(block('Button'), None, default_hyperlink='https://example.com')[0].text == 'Button <https://example.com>'


def test_ppt_hyperlink_dictionary_and_internal_slide_target():
    def link(idx, target):
        return rec(4055, rec(4051, struct.pack('<I', idx)) + rec(4026, 'label'.encode('utf-16le'))
                   + rec(4026, target.encode('utf-16le'), instance=1), container=True)
    records = parse_records(link(1, 'https://example.com') + link(2, '256,1,Title'))
    assert read_hyperlinks(records, {256: 1}) == {1: 'https://example.com', 2: '#PowerPoint Document#slide1'}


def test_ppt_text_truncated_style_falls_back_with_warning():
    errors = []
    records = parse_records(rec(3999, struct.pack('<I', 1)) + rec(4008, b'safe') + rec(4001, b'\x00'))
    b = text_blocks(records, errors=errors)[0]
    assert render_text(b, None)[0].text == 'safe'
    assert any('style' in e.lower() for e in errors)


def test_ppt_text_zero_run_count_is_bounded_and_plain_text_survives():
    errors = []
    records = parse_records(rec(3999, struct.pack('<I', 1)) + rec(4008, b'safe') + rec(4001, pf(0)))
    b = text_blocks(records, errors=errors)[0]
    assert render_text(b, None)[0].text == 'safe'
    assert errors


def test_ppt_text_explicit_bullet_uses_existing_pptx_prefix_contract():
    style = pf(4, level=2, mask=0x81, props=struct.pack('<HH', 1, 0x2022)) + cf(4)
    p = render_text(block('One', style), None)[0]
    assert p.text == '• One'
    assert p.heading_level == 0


def test_ppt_text_large_disjoint_link_ranges_keep_their_own_targets():
    text = 'x' * 1000
    tail = b''.join(interaction(i + 1) + rec(4063, struct.pack('<II', i, i + 1)) for i in range(1000))
    p = render_text(block(text, tail=tail), None, {i + 1: 'https://e/%d' % i for i in range(1000)})[0]
    assert p.text.startswith('x <https://e/0>x <https://e/1>')
    assert p.text.endswith('x <https://e/999>')


def test_ppt_text_empty_headers_preserve_outline_reference_indices():
    records = parse_records(rec(3999, struct.pack('<I', 0))
                            + rec(3999, struct.pack('<I', 1)) + rec(4008, b'Body'))
    blocks = text_blocks(records)
    assert len(blocks) == 2
    assert [b.text for b in blocks] == ['', 'Body']
    assert render_text(blocks[0], None) == []


def test_ppt_hyperlink_oversized_numeric_target_is_not_integer_parsed():
    target = '9' * 5000 + ',1,Title'
    records = parse_records(rec(4055, rec(4051, struct.pack('<I', 1))
                                + rec(4026, target.encode('utf-16le'), instance=1), container=True))
    assert read_hyperlinks(records)[1] == target


def test_ppt_text_output_budget_bounds_repeated_hyperlink_expansion():
    errors = []
    target = 'https://example.com/' + 'x' * 100000
    tail = b''.join(interaction(i + 1) + rec(4063, struct.pack('<II', i, i + 1)) for i in range(10))
    paragraphs = render_text(block('abcdefghij', tail=tail), None,
                             {i + 1: target for i in range(10)}, max_output_chars=15, errors=errors)
    assert ''.join(p.text for p in paragraphs) == 'abcdefghij'
    assert any('output' in e.lower() for e in errors)


def test_ppt_text_output_budget_bounds_shape_links_and_plain_text():
    errors = []
    paragraphs = render_text(block('abc\rdefgh'), None, default_hyperlink='x' * 100000,
                             max_output_chars=5, errors=errors)
    assert [p.text for p in paragraphs] == ['abc', 'de']
    assert errors


def test_ppt_text_output_budget_counts_bullet_prefix():
    errors = []
    style = pf(4, mask=0x81, props=struct.pack('<HH', 1, 0x2022)) + cf(4)
    paragraphs = render_text(block('One', style), None, max_output_chars=3, errors=errors)
    assert paragraphs[0].text == '• O'
    assert errors


def test_ppt_text_bullet_surrogate_is_replaced_by_safe_unicode():
    style = pf(4, mask=0x81, props=struct.pack('<HH', 1, 0xD800)) + cf(4)
    p = render_text(block('One', style), None)[0]
    assert p.text == '\ufffd One'
    assert p.text.encode('utf-8')


def test_ppt_text_long_output_run_is_chunked_without_text_loss():
    text = 'x' * 70000
    p = render_text(block(text), None)[0]
    assert p.text == text
    assert all(len(run.text) <= 65536 for run in p.runs)


def test_ppt_text_output_run_count_has_a_hard_limit(monkeypatch):
    from dochan.office_binary import ppt_text
    monkeypatch.setattr(ppt_text, 'MAX_TEXT_RUNS', 2)
    errors = []
    p = render_text(block('x' * 200000), None, errors=errors)[0]
    assert len(p.runs) == 2
    assert len(p.text) == 2 * 65536
    assert any('run count' in e for e in errors)


def test_ppt_hyperlink_preserves_external_and_location_only_destinations():
    def link(idx, address, location):
        return rec(4055, rec(4051, struct.pack('<I', idx))
                   + rec(4026, address.encode('utf-16le'), instance=1)
                   + rec(4026, location.encode('utf-16le'), instance=3), container=True)
    records = parse_records(link(1, 'https://example.com/page', 'section2')
                            + link(2, '', '300,2,Title') + link(3, '', 'bookmark'))
    assert read_hyperlinks(records, {300: 7}) == {
        1: 'https://example.com/page#section2', 2: '#PowerPoint Document#slide7',
        3: '#bookmark',
    }


def test_ppt_text_blank_fragments_obey_processing_limit(monkeypatch):
    from dochan.office_binary import ppt_text
    monkeypatch.setattr(ppt_text, 'MAX_TEXT_FRAGMENTS', 10, raising=False)
    errors = []
    assert render_text(block('\r' * 50 + 'late'), None, errors=errors) == []
    assert any('fragment' in error for error in errors)


def test_ppt_text_newline_scanning_does_not_allocate_per_character_arrays():
    import tracemalloc
    b = block('\r' * 300000)
    tracemalloc.start()
    try:
        render_text(b, None)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024


def test_ppt_title_discards_leading_soft_line_breaks():
    from dochan.output.markdown import _paragraph_to_md
    paragraph = render_text(block('\x0b\x0b\x0bTable sample', text_type=0), None)[0]
    assert _paragraph_to_md(paragraph) == '# Table sample'


def test_ppt_paragraph_leading_indent_does_not_become_markdown_code():
    paragraphs = render_text(block('    first\r\t second'), None)
    assert [p.text for p in paragraphs] == ['first', 'second']


def test_ppt_adjacent_markdown_styles_merge_without_losing_model_font_sizes():
    from dochan.output.markdown import _paragraph_to_md
    style = pf(8) + cf(3, 0x20001, struct.pack('<HH', 1, 24))
    style += cf(1, 0x20001, struct.pack('<HH', 1, 12)) + cf(4, 1, struct.pack('<H', 1))
    provenance = Provenance(source_format='ppt', slide=1, path='PowerPoint Document')
    p = render_text(block('logb(x)', style), provenance)[0]
    assert [run.font_size_pt for run in p.runs] == [24, 12, 10]
    assert _paragraph_to_md(p) == '**logb(x)**'


def test_ppt_symbol_font_maps_private_use_math_without_touching_regular_text():
    # Symbol byte B3 is greater-than-or-equal (POI TestBugs.bug49541).
    style = pf(10) + cf(1, 0x10000, struct.pack('<H', 3)) + cf(9)
    p = render_text(block('\uf0b375 years', style), None, font_names={0: 'Arial', 3: 'Symbol'})[0]
    assert p.text == '≥75 years'
    p = render_text(block('\uf0b3', pf(2) + cf(2, 0x10000, struct.pack('<H', 0))),
                    None, font_names={0: 'Arial'})[0]
    assert p.text == '\uf0b3'


def test_ppt_wingdings_bullet_uses_declared_bullet_font():
    # with_textbox.ppt stores bullet char D8 and font index 2 (Wingdings).
    style = pf(4, mask=0x91, props=struct.pack('<HHH', 1, 0xD8, 2)) + cf(4)
    assert render_text(block('One', style), None, font_names={2: 'Wingdings'})[0].text == '➢ One'


def test_ppt_unknown_extension_mask_preserves_preceding_verified_formatting():
    # Without local wire-length evidence, never guess where the following run
    # begins. Keep completed runs and the independently decoded PF properties.
    for extension_mask in (0x100000, 0x1000000, 0x2000000, 0x4000000):
        style = pf(4, mask=0x81, props=struct.pack('<HH', 1, 0x2022))
        style += cf(1, 1, struct.pack('<H', 1)) + cf(1, extension_mask, b'\x01\x02') + cf(2)
        errors = []
        data = rec(3999, struct.pack('<I', 1)) + rec(4008, b'ABC') + rec(4001, style)
        b = text_blocks(parse_records(data), errors=errors)[0]
        p = render_text(b, None)[0]
        assert p.text == '• ABC'
        assert any(r.text == 'A' and r.bold for r in p.runs)
        assert p.runs[-1].text == 'BC' and not p.runs[-1].bold
        assert any('unsupported character style mask' in e for e in errors)


def test_ppt_symbol_fallback_font_maps_only_private_use_characters():
    # symbolFontRef applies to the symbol character domain; it must not turn
    # ordinary Latin letters in the same CF run into Greek letters.
    style = pf(3) + cf(3, 0x810000, struct.pack('<HH', 0, 3))
    p = render_text(block('A\uf0b3', style), None, font_names={0: 'Arial', 3: 'Symbol'})[0]
    assert p.text == 'A≥'
