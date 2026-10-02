"""Synthetic Word FFN/CHPX and bookmark regressions for the P3 review."""
import struct
from types import SimpleNamespace

from lxml import etree

from dochan.model.document import Document, TextRun
from dochan.office_binary.doc_binary import DocBinary, decode_grpprl
from dochan.office_binary.doc_stories import Stories
from dochan.office_binary.doc_structure import StructureRenderer
from dochan.ooxml.docx import DOCXReader


def _binary(text, chp=b'', fonts=('Wingdings', 'Symbol')):
    word = bytearray(3072)
    struct.pack_into('<HH', word, 0, 0xa5ec, 0xc1)
    struct.pack_into('<H', word, 32, 14)
    struct.pack_into('<H', word, 62, 22)
    struct.pack_into('<I', word, 76, len(text))
    struct.pack_into('<H', word, 152, 93)
    raw = text.encode('utf-16le', errors='surrogatepass')
    word[1024:1024 + len(raw)] = raw
    table = bytearray()

    def add(index, value):
        struct.pack_into('<II', word, 154 + index * 8, len(table), len(value))
        table.extend(value)

    pcd = struct.pack('<IIHIH', 0, len(text), 0, 1024, 0)
    add(33, b'\x02' + struct.pack('<I', len(pcd)) + pcd)
    ffn = bytearray(struct.pack('<HH', len(fonts), 0))
    for name in fonts:
        record = bytearray(40) + name.encode('utf-16le') + b'\0\0'
        record[0] = len(record) - 1
        record[4] = 2
        ffn.extend(record)
    add(15, bytes(ffn))
    if chp:
        page = bytearray(512)
        struct.pack_into('<II', page, 0, 1024, 1024 + len(raw))
        page[8] = 100
        page[200] = len(chp)
        page[201:201 + len(chp)] = chp
        page[511] = 1
        word[2048:2560] = page
        add(12, struct.pack('<III', 1024, 1024 + len(raw), 4))
    return DocBinary(bytes(word), bytes(table))


def _render(binary, stories=None):
    doc = Document()
    renderer = StructureRenderer(binary, doc, stories or Stories(binary, doc), SimpleNamespace())
    return renderer.render(0, len(binary.text))


def test_doc_font_ffn_and_character_font_sprm():
    binary = _binary('oþ\r', struct.pack('<HH', 0x4a4f, 0))
    assert binary.font_names == {0: 'Wingdings', 1: 'Symbol'}
    assert _render(binary)[0].text == '☐☑'


def test_doc_font_symbol_and_private_use_run_mapping():
    binary = _binary('Aα\uf057\r', struct.pack('<HH', 0x4a4f, 1))
    assert _render(binary)[0].text == 'ΑαΩ'


def test_doc_font_symbol_operand_replaces_special_placeholder_only():
    chp = struct.pack('<HBHHH', 0x0855, 1, 0x6a09, 0, 0xf0fe)
    binary = _binary('(x\r', chp)
    assert _render(binary)[0].text == '☑x'
    assert decode_grpprl(chp)['symbol'] == (0, 0xf0fe)
    assert _render(_binary('(x\r', struct.pack('<HHH', 0x6a09, 0, 0xf0fe)))[0].text == '(x'


def test_doc_font_macrobutton_uses_display_run_font():
    binary = _binary('\x13 MACROBUTTON Check o\x15unchecked\r')
    cp = binary.text.index('o\x15')
    binary._chp = [(cp, cp + 1, {'font': 0})]
    binary._chp_starts = [cp]
    assert _render(binary)[0].text == '☐unchecked'


def test_doc_font_truncated_ffn_warns_without_losing_body():
    binary = _binary('Body\r')
    word = bytearray(binary.word)
    start, size = binary._pairs[15]
    struct.pack_into('<II', word, 154 + 15 * 8, start, size - 3)
    binary = DocBinary(bytes(word), binary.table)
    assert _render(binary)[0].text == 'Body'
    assert any('font' in warning.lower() for warning in binary.warnings)


def test_doc_font_record_limit_warns_and_unknown_fonts_keep_text():
    binary = _binary('o\r', struct.pack('<HH', 0x4a4f, 0), fonts=('Unknown Symbol',))
    assert _render(binary)[0].text == 'o'
    table = bytearray(binary.table)
    struct.pack_into('<H', table, binary._pairs[15][0], 65535)
    damaged = DocBinary(binary.word, bytes(table))
    assert damaged.valid
    assert _render(damaged)[0].text == 'o'
    assert any('font table: record limit' in warning for warning in damaged.warnings)


def test_doc_macrobutton_font_coordinates_preserve_surrogate_pairs():
    binary = _binary('\ud83d\ude00\x13 MACROBUTTON Check o\x15unchecked\r')
    cp = binary.text.index('o\x15')
    binary._chp = [(cp, cp + 1, {'font': 0})]
    binary._chp_starts = [cp]
    assert _render(binary)[0].text == '😀☐unchecked'


def test_doc_bookmark_does_not_split_identically_formatted_runs():
    binary = _binary('Paragraph\r', struct.pack('<HB', 0x0835, 1))
    stories = Stories(binary, Document())
    stories._markers = {1: [TextRun('[bookmark: SG12] ')]}
    stories._markers[1][0]._bookmark_annotation = True
    stories._event_cps = [1]
    result = _render(binary, stories)[0]
    assert [run.text for run in result.runs] == ['[bookmark: SG12] ', 'Paragraph']
    assert result.runs[1].bold


def test_doc_bookmarks_move_to_paragraph_start_preserving_word_and_style():
    binary = _binary('Paragraph\r')
    binary._chp = [(0, 1, {'bold': True})]
    binary._chp_starts = [0]
    stories = Stories(binary, Document())
    stories._markers = {1: [TextRun('[bookmark: SG12] ')]}
    stories._markers[1][0]._bookmark_annotation = True
    stories._event_cps = [1]
    result = _render(binary, stories)[0]
    assert result.text == '[bookmark: SG12] Paragraph'
    assert result.runs[1].text == 'P'
    assert result.runs[1].bold


def test_docx_bookmarks_move_to_paragraph_start_including_nested_runs():
    xml = '''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:r><w:rPr><w:b/></w:rPr><w:t>P</w:t></w:r>
      <w:ins><w:bookmarkStart w:id="1" w:name="SG12"/><w:r><w:t>aragraph</w:t></w:r></w:ins>
      <w:bookmarkStart w:id="2" w:name="Tail"/>
    </w:p>'''
    runs = DOCXReader()._parse_runs(etree.fromstring(xml))
    assert ''.join(run.text for run in runs) == '[bookmark: SG12] [bookmark: Tail] Paragraph'
    assert runs[2].bold


def test_docx_bookmark_relocation_preserves_textbox_end_spacing():
    xml = '''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Box</w:t></w:r></w:p></w:txbxContent></w:pict></w:r>
      <w:bookmarkStart w:id="1" w:name="BoxAnchor"/>
      <w:r><w:t>After</w:t></w:r>
    </w:p>'''
    runs = DOCXReader()._parse_runs(etree.fromstring(xml))
    assert ''.join(run.text for run in runs) == '[bookmark: BoxAnchor] Box After'


def test_docx_bookmark_relocation_preserves_textbox_start_spacing():
    xml = '''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:r><w:t>Before</w:t></w:r>
      <w:bookmarkStart w:id="1" w:name="BoxAnchor"/>
      <w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Box</w:t></w:r></w:p></w:txbxContent></w:pict></w:r>
    </w:p>'''
    runs = DOCXReader()._parse_runs(etree.fromstring(xml))
    assert ''.join(run.text for run in runs) == '[bookmark: BoxAnchor] Before Box'


def test_doc_macrobutton_bookmark_literal_stays_at_its_text_position():
    binary = _binary('Before \x13 MACROBUTTON Check [bookmark: literal] \x15 After\r')
    assert _render(binary)[0].text == 'Before [bookmark: literal] After'
