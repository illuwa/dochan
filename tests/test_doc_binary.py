"""Synthetic MS-DOC FIB, PLC, FKP and style records."""
import struct

from dochan.office_binary.doc_binary import DocBinary, decode_grpprl


def make_binary(text='Hello\r', pap=b'', chp=b'', styles=b'', stories=None):
    word = bytearray(3072)
    struct.pack_into('<HH', word, 0, 0xa5ec, 0xc1)
    struct.pack_into('<H', word, 32, 14)
    struct.pack_into('<H', word, 62, 22)
    counts = stories or [len(text), 0, 0, 0, 0, 0, 0]
    for idx, count in zip([3, 4, 5, 7, 8, 9, 10], counts):
        struct.pack_into('<I', word, 64 + idx * 4, count)
    struct.pack_into('<H', word, 152, 93)
    word[1024:1024 + len(text)] = text.encode('cp1252')
    table = bytearray()
    def add(index, value):
        struct.pack_into('<II', word, 154 + index * 8, len(table), len(value))
        table.extend(value)
    pcdt = struct.pack('<IIHIH', 0, len(text), 0, 0x40000000 | (1024 * 2), 0)
    add(33, b'\x02' + struct.pack('<I', len(pcdt)) + pcdt)
    if pap:
        page = bytearray(512)
        struct.pack_into('<II', page, 0, 1024, 1024 + len(text))
        page[8] = 100
        payload = struct.pack('<H', 0) + pap
        if not len(payload) % 2:
            payload += b'\0'
        page[200] = (len(payload) + 1) // 2
        page[201:201 + len(payload)] = payload
        page[511] = 1
        word[1536:2048] = page
        add(13, struct.pack('<III', 1024, 1024 + len(text), 3))
    if chp:
        page = bytearray(512)
        struct.pack_into('<II', page, 0, 1024, 1024 + len(text))
        page[8] = 100
        page[200] = len(chp)
        page[201:201 + len(chp)] = chp
        page[511] = 1
        word[2048:2560] = page
        add(12, struct.pack('<III', 1024, 1024 + len(text), 4))
    if styles:
        add(1, styles)
    return DocBinary(bytes(word), bytes(table))


def test_cp_story_ranges_and_piece_mapping():
    d = make_binary('main\rnote\rhead\r', stories=[5, 5, 5, 0, 0, 0, 0])
    assert d.text == 'main\rnote\rhead\r'
    assert d.stories['footnote'] == (5, 10)
    assert d.stories['header'] == (10, 15)
    assert d.cp_to_fc(6) == 1030
    assert d.fc_to_cp(1030) == 6
    assert [p.text for p in d.paragraphs(0, 5)] == ['main\r']


def test_fkp_properties_and_toggle_sprms():
    pap = struct.pack('<HBHBHI', 0x2416, 1, 0x2417, 1, 0x6649, 1)
    chp = struct.pack('<HBHBHB', 0x0835, 1, 0x0836, 1, 0x2a3e, 1)
    d = make_binary(pap=pap, chp=chp)
    p = list(d.paragraphs(0, 6))[0]
    assert p.props['in_table'] is True
    assert p.props['row_end'] is True
    assert p.props['itap'] == 1
    assert d.char_props(2)['bold'] is True
    assert d.char_props(2)['italic'] is True
    assert d.char_props(2)['underline'] is True


def style_record(name, base, pap=b'', chp=b''):
    hdr = struct.pack('<HHHHH', 0, (base << 4) | 1, 2, 0, 0)
    body = hdr + struct.pack('<H', len(name)) + name.encode('utf-16-le') + b'\0\0'
    for p in [b'\0\0' + pap, chp]:
        body += struct.pack('<H', len(p)) + p
        if len(p) % 2:
            body += b'\0'
    return struct.pack('<H', len(body)) + body


def test_style_inheritance_and_direct_toggle():
    stshi = struct.pack('<HH', 2, 10) + b'\0' * 14
    styles = struct.pack('<H', len(stshi)) + stshi
    styles += style_record('Normal', 0xfff, chp=struct.pack('<HB', 0x0835, 1))
    styles += style_record('Heading 1', 0, chp=struct.pack('<HB', 0x0836, 1))
    d = make_binary(styles=styles, chp=struct.pack('<HB', 0x0835, 0x81))
    assert d.styles[1]['props']['bold'] is True
    assert d.styles[1]['props']['italic'] is True
    assert d.styles[1]['heading_level'] == 1
    assert d.char_props(0)['bold'] is False


def test_grpprl_table_definition_and_truncation():
    operand = b'\x01' + struct.pack('<hh', 0, 100) + b'\0' * 20
    raw = struct.pack('<HH', 0xd608, len(operand) + 1) + operand
    assert decode_grpprl(raw)['table_def'] == operand
    assert decode_grpprl(b'\x35\x08') == {}
    assert DocBinary(b'', b'').text == ''


def test_revision_author_picture_and_inner_table_sprms():
    raw = (struct.pack('<HBHBHHHIHB', 0x0801, 1, 0x0800, 1,
                       0x4804, 3, 0x6a03, 123, 0x0855, 1)
           + struct.pack('<HBHB', 0x244b, 1, 0x244c, 1))
    props = decode_grpprl(raw)
    assert props == {'inserted': True, 'deleted': True, 'author': 3,
                     'pic_location': 123, 'special': True,
                     'inner_cell': True, 'inner_row': True}


def test_style_cycle_is_bounded():
    stshi = struct.pack('<HH', 2, 10) + b'\0' * 14
    styles = struct.pack('<H', len(stshi)) + stshi
    styles += style_record('A', 1, chp=struct.pack('<HB', 0x0835, 1))
    styles += style_record('B', 0, chp=struct.pack('<HB', 0x0836, 1))
    d = make_binary(styles=styles)
    assert set(d.styles) == {0, 1}
    assert d.styles[0]['props']['bold'] is True


def test_huge_papx_dereferences_data_stream():
    d = make_binary(pap=struct.pack('<HI', 0x6646, 4))
    props = struct.pack('<HBHB', 0x2416, 1, 0x2417, 1)
    d = DocBinary(d.word, d.table, b'\0' * 4 + struct.pack('<H', len(props)) + props)
    record = list(d.paragraphs(0, 6))[0]
    assert record.props['in_table'] is True
    assert record.props['row_end'] is True


def test_unicode_piece_preserves_surrogate_cp_coordinates():
    d = make_binary('abcd\r')
    word = bytearray(d.word)
    table = bytearray(d.table)
    # Five UTF-16 code units: A, surrogate pair, B, paragraph mark.
    word[1024:1034] = 'A\U0001f600B\r'.encode('utf-16-le')
    struct.pack_into('<I', table, 5 + 8 + 2, 1024)
    d = DocBinary(bytes(word), bytes(table))
    assert len(d.text) == 5
    assert d.text[3:] == 'B\r'
    assert d.cp_to_fc(3) == 1030
    assert d.fc_to_cp(1030) == 3


def test_out_of_stream_fkp_is_warning_without_losing_text():
    d = make_binary(chp=struct.pack('<HB', 0x0835, 1))
    table = bytearray(d.table)
    offset, length = struct.unpack_from('<II', d.word, 154 + 12 * 8)
    struct.pack_into('<I', table, offset + 8, 0x2000)
    result = DocBinary(d.word, bytes(table))
    assert result.text == 'Hello\r'
    assert result.valid
    assert result.warnings == ['DOC FKP page outside stream']


def test_huge_papx_invalid_pointer_is_reported():
    original = make_binary(pap=struct.pack('<HI', 0x6646, 1234))
    assert original.text == 'Hello\r'
    assert any('huge PAPX' in warning for warning in original.warnings)


def test_invalid_fkp_offset_does_not_escape():
    d = make_binary(pap=struct.pack('<HB', 0x2416, 1))
    word = bytearray(d.word)
    word[1536 + 8] = 255
    word[1536 + 510] = 255
    result = DocBinary(bytes(word), d.table)
    assert result.text == 'Hello\r'
    assert result.warnings


def test_story_ranges_beyond_piece_text_request_fallback():
    d = make_binary('Hello\r', stories=[7, 0, 0, 0, 0, 0, 0])
    assert not d.valid
    assert any('story CP' in warning for warning in d.warnings)


def test_empty_main_with_valid_piece_table_is_structured_document():
    d = make_binary('\r', stories=[0, 0, 0, 0, 0, 0, 0])
    assert d.valid
    assert list(d.paragraphs(*d.stories['main'])) == []


def test_fast_saved_paragraph_uses_mark_style_for_all_characters():
    stshi = struct.pack('<HH', 2, 10) + b'\0' * 14
    styles = struct.pack('<H', len(stshi)) + stshi
    styles += style_record('Normal', 0xfff)
    styles += style_record('Heading 1', 0, chp=struct.pack('<HB', 0x0835, 1))
    original = make_binary(styles=styles, pap=struct.pack('<HB', 0x2416, 0))
    word = bytearray(original.word)
    page = bytearray(512)
    struct.pack_into('<III', page, 0, 1024, 1029, 1030)
    page[12], page[25] = 100, 110
    page[200:204] = b'\x02\x00\x00\x00'
    page[220:224] = b'\x02\x01\x00\x00'
    page[511] = 2
    word[1536:2048] = page
    binary = DocBinary(bytes(word), original.table)
    assert list(binary.paragraphs(0, 6))[0].props['istd'] == 1
    assert binary.char_props(0)['bold'] is True
    assert binary.char_props(4)['bold'] is True


def test_extended_tab_operand_keeps_following_sprm():
    # PChgTabsOperand cb=255 uses cTabsDel * 4 + cTabsAdd * 3 + 2.
    tabs = b'\x3f' + b'\0' * (63 * 4) + b'\x01' + b'\0' * 3
    raw = struct.pack('<HB', 0xc615, 255) + tabs + struct.pack('<HB', 0x2416, 1)
    assert decode_grpprl(raw) == {'in_table': True}
    assert decode_grpprl(struct.pack('<HB', 0xc615, 255) + b'\xff') == {}


def test_nested_huge_papx_and_table_props_are_resolved():
    raw = struct.pack('<HBHB', 0x2416, 1, 0x2417, 1)
    nested = struct.pack('<HI', 0x646b, 16)
    data = struct.pack('<H', len(nested)) + nested + b'\0' * 8
    data += struct.pack('<H', len(raw)) + raw
    original = make_binary(pap=struct.pack('<HI', 0x6646, 0))
    result = DocBinary(original.word, original.table, data)
    assert result.paragraph_props(0)['in_table'] is True
    assert result.paragraph_props(0)['row_end'] is True
    assert not result.warnings


def test_nested_papx_cycle_is_reported_and_keeps_other_properties():
    raw = struct.pack('<HBHI', 0x2416, 1, 0x646b, 0)
    original = make_binary(pap=struct.pack('<HI', 0x6646, 0))
    result = DocBinary(original.word, original.table, struct.pack('<H', len(raw)) + raw)
    assert result.paragraph_props(0)['in_table'] is True
    assert any('cycle' in warning for warning in result.warnings)
    assert 'huge_papx' not in result.paragraph_props(0)
    assert 'table_props' not in result.paragraph_props(0)


def test_section_mark_is_paragraph_boundary():
    binary = make_binary('a\x0cb\r')
    assert [p.text for p in binary.paragraphs(0, 4)] == ['a\x0c', 'b\r']


def test_ciss_super_subscript_and_reset():
    assert decode_grpprl(struct.pack('<HB', 0x2a48, 1)) == {
        'superscript': True, 'subscript': False}
    assert decode_grpprl(struct.pack('<HB', 0x2a48, 2)) == {
        'superscript': False, 'subscript': True}
    assert decode_grpprl(struct.pack('<HB', 0x2a48, 0)) == {
        'superscript': False, 'subscript': False}


def test_fkp_piece_index_does_not_charge_disjoint_pieces(monkeypatch):
    from dochan.office_binary import doc_binary
    from dochan.office_binary.doc_binary import Piece
    original = make_binary(pap=struct.pack('<HB', 0x2416, 1))
    # One run intersects only the last of one hundred physical pieces.
    original.pieces = [Piece(i, i + 1, 1024 + i, True) for i in range(100)]
    word = bytearray(original.word)
    struct.pack_into('<II', word, 1536, 1123, 1124)
    original.word = bytes(word)
    monkeypatch.setattr(doc_binary, 'MAX_FKP_INTERSECTIONS', 2)
    records = original._fkps(13, True)
    assert len(records) == 1
    assert records[0][:2] == (99, 100)
    assert not original.warnings


def test_deleted_paragraph_mark_merges_with_next_paragraph():
    binary = make_binary('a\rb\r')
    binary._chp = [(1, 2, {'deleted': True})]
    binary._chp_starts = [1]
    assert [p.text for p in binary.paragraphs(0, 4)] == ['a\rb\r']


def test_deleted_table_row_mark_is_exposed_without_merging():
    binary = make_binary('a\x07b\r', pap=struct.pack('<HB', 0x2417, 1))
    binary._chp = [(1, 2, {'deleted': True})]
    binary._chp_starts = [1]
    records = list(binary.paragraphs(0, 4))
    assert len(records) == 2
    assert records[0].props['deleted_mark'] is True


def test_data_loader_is_lazy_and_cached():
    original = make_binary()
    calls = []
    def load():
        calls.append(1)
        return b'data'
    binary = DocBinary(original.word, original.table, load)
    assert binary.valid
    assert calls == []
    assert binary.data == binary.data == b'data'
    assert calls == [1]


def test_character_runs_match_per_character_properties_in_gaps():
    binary = make_binary('ab\rcdef\r')
    binary._chp = [(1, 2, {'bold': True}), (4, 6, {'italic': True})]
    binary._chp_starts = [1, 4]
    expected = [binary.char_props(cp) for cp in range(8)]
    runs = list(binary.iter_char_runs(0, 8))
    actual = [props for start, end, props in runs for cp in range(start, end)]
    assert actual == expected
    assert [(start, end) for start, end, _ in runs] == [
        (0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 8)]


def test_nested_papx_depth_and_byte_limits(monkeypatch):
    from dochan.office_binary import doc_binary
    original = make_binary(pap=struct.pack('<HI', 0x6646, 0))
    data = struct.pack('<HHI', 6, 0x646b, 8)
    data += struct.pack('<HHB', 3, 0x2416, 1)
    monkeypatch.setattr(doc_binary, 'MAX_PAPX_DEPTH', 1)
    binary = DocBinary(original.word, original.table, data)
    assert any('depth limit' in warning for warning in binary.warnings)
    monkeypatch.setattr(doc_binary, 'MAX_PAPX_DEPTH', 32)
    monkeypatch.setattr(doc_binary, 'MAX_PAPX_BYTES', 7)
    binary = DocBinary(original.word, original.table, data)
    assert any('byte limit' in warning for warning in binary.warnings)


def test_nested_papx_keeps_horizontal_merge_definition():
    from dochan.model.document import Paragraph, TextRun
    from dochan.office_binary.doc_tables import assemble_blocks
    from dochan.office_binary.doc_binary import ParagraphRecord
    table_def = (b'\x02' + struct.pack('<hhh', 0, 100, 200)
                 + struct.pack('<H', 1) + b'\0' * 18
                 + struct.pack('<H', 2) + b'\0' * 18)
    raw = struct.pack('<HH', 0xd608, len(table_def) + 1) + table_def
    nested = struct.pack('<HI', 0x646b, 8)
    data = struct.pack('<H', len(nested)) + nested + struct.pack('<H', len(raw)) + raw
    source = make_binary(pap=struct.pack('<HI', 0x6646, 0))
    binary = DocBinary(source.word, source.table, data)
    props = dict(binary.paragraph_props(0), in_table=True, itap=1)
    records = [ParagraphRecord(0, 2, 'A\x07', props),
               ParagraphRecord(2, 3, '\x07', props),
               ParagraphRecord(3, 4, '\x07', dict(props, row_end=True))]
    def render(record):
        return [Paragraph(runs=[TextRun(record.text.rstrip('\x07'))])]
    table = assemble_blocks(records, render, [])[0]
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away


def test_fkp_index_preserves_fast_save_overlapping_pieces():
    from dochan.office_binary.doc_binary import Piece
    binary = make_binary(pap=struct.pack('<HB', 0x2416, 1))
    binary.pieces = [Piece(0, 2, 1028, True), Piece(2, 6, 1024, True),
                     Piece(6, 8, 1025, True)]
    records = binary._fkps(13, True)
    assert [record[:2] for record in records] == [(0, 2), (2, 6), (6, 8)]


def test_deleted_body_mark_before_deleted_table_preserves_live_text():
    from dochan.office_binary.doc_structure import parse_structured_doc
    source = make_binary('live\rdead\x07\x07', pap=struct.pack('<HB', 0x2416, 0),
                         chp=struct.pack('<HB', 0x0800, 1))
    word = bytearray(source.word)
    pap = bytearray(512)
    struct.pack_into('<IIII', pap, 0, 1024, 1029, 1034, 1035)
    for index, (at, props) in enumerate([
            (200, struct.pack('<HB', 0x2416, 0)),
            (220, struct.pack('<HB', 0x2416, 1)),
            (240, struct.pack('<HBHB', 0x2416, 1, 0x2417, 1))]):
        payload = b'\0\0' + props
        if not len(payload) % 2:
            payload += b'\0'
        pap[16 + index * 13] = at // 2
        pap[at] = (len(payload) + 1) // 2
        pap[at + 1:at + 1 + len(payload)] = payload
    pap[511] = 3
    word[1536:2048] = pap
    chp = bytearray(512)
    struct.pack_into('<III', chp, 0, 1024, 1028, 1035)
    chp[13] = 100
    chp[200:204] = b'\x03\x00\x08\x01'
    chp[511] = 2
    word[2048:2560] = chp
    binary = DocBinary(bytes(word), source.table)
    records = list(binary.paragraphs(0, 11))
    assert records[0].text == 'live\r'
    assert not records[0].props.get('in_table')
    document = parse_structured_doc(bytes(word), source.table)
    assert [element.text for element in document.sections[0].elements] == ['live']
