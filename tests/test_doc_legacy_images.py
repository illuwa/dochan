"""Word 6/95 pictures assembled from FIB, CHPX FKP and PICF bytes."""
import struct
from types import SimpleNamespace

from dochan.model.document import Document
from dochan.model.image import Image
from dochan.office_binary.doc import parse_doc_word_stream
from dochan.office_binary.doc_images import DocImages


def wmf():
    return struct.pack('<HHHIHIH', 1, 9, 0x300, 12, 0, 3, 0) + struct.pack('<IH', 3, 0)


def picf(payload=None):
    payload = wmf() if payload is None else payload
    return struct.pack('<IHH', 58 + len(payload), 58, 8) + bytes(50) + payload


def word6(text=b'Before picture\r\x01\rAfter picture\r', properties=None):
    word = bytearray(2048)
    struct.pack_into('<HH', word, 0, 0xa5dc, 104)
    struct.pack_into('<II', word, 24, 768, 768 + len(text))
    struct.pack_into('<I', word, 52, len(text))
    word[768:768 + len(text)] = text
    picture_fc = 1536
    picture = picf()
    word[picture_fc:picture_fc + len(picture)] = picture
    struct.pack_into('<II', word, 184, 512, 10)
    fc = 768 + text.index(b'\x01')
    struct.pack_into('<IIH', word, 512, fc, fc + 1, 2)
    struct.pack_into('<II', word, 1024, fc, fc + 1)
    word[1032] = 100
    properties = (b'\x75\x01\x44\x04' + struct.pack('<I', picture_fc)
                  if properties is None else properties)
    word[1224] = len(properties)
    word[1225:1225 + len(properties)] = properties
    word[1535] = 1
    return word


def test_legacy_picf_direct_wmf_has_valid_header_and_records():
    binary = SimpleNamespace(data=picf(), word=bytes(word6()), text='\x01', blob=lambda n: b'',
                             char_props=lambda cp: {'special': True, 'pic_location': 0})
    doc = Document()
    image = DocImages(binary, doc).image_at(0)
    assert image is not None
    assert image.image_format == 'wmf'
    assert image.image_data == wmf()
    assert doc.assets[0].content_type == 'image/x-wmf'


def test_word6_chpx_picture_reaches_reader_in_text_order():
    doc = parse_doc_word_stream(bytes(word6()))
    elements = doc.sections[0].elements
    assert len(elements) == 3
    assert elements[0].text == 'Before picture'
    assert isinstance(elements[1], Image)
    assert elements[1].image_data == wmf()
    assert elements[2].text == 'After picture'


def test_word6_picture_inside_field_result_and_table_cell():
    data = word6(b'First cell with ordinary readable text\t\x13INCLUDEPICTURE x\x14\x01\x15\rNext\tCell\r')
    doc = parse_doc_word_stream(bytes(data))
    table = doc.sections[0].elements[0]
    assert isinstance(table.rows[0][1].paragraphs[0], Image)
    assert table.rows[0][0].text == 'First cell with ordinary readable text'
    assert table.rows[1][1].text == 'Cell'


def test_word6_unknown_chpx_does_not_guess_picture_location():
    data = word6(properties=b'\xff\x75\x01\x44\x04' + struct.pack('<I', 1536))
    doc = parse_doc_word_stream(bytes(data))
    assert not doc.assets


def test_legacy_picf_rejects_invalid_wmf_record_boundary():
    broken = bytearray(wmf())
    struct.pack_into('<I', broken, 18, 100)
    binary = SimpleNamespace(data=picf(bytes(broken)), word=bytes(word6()), text='\x01', blob=lambda n: b'',
                             char_props=lambda cp: {'special': True, 'pic_location': 0})
    doc = Document()
    assert DocImages(binary, doc).image_at(0) is None
    assert any('WMF' in warning for warning in doc.errors)


def test_word6_complex_layout_is_not_mistaken_for_contiguous_text():
    data = word6()
    struct.pack_into('<H', data, 10, 4)
    assert not parse_doc_word_stream(bytes(data)).assets


def test_legacy_wmf_limits_are_checked_before_export():
    from dochan.office_binary.officeart import Limits
    binary = SimpleNamespace(data=picf(), word=bytes(word6()), text='\x01', blob=lambda n: b'',
                             char_props=lambda cp: {'special': True, 'pic_location': 0})
    doc = Document()
    pictures = DocImages(binary, doc)
    pictures.limits = Limits(max_image_bytes=12)
    assert pictures.image_at(0) is None
    assert not doc.assets
    assert any('byte limit' in warning for warning in doc.errors)


def test_word6_truncated_fkp_does_not_abort_text():
    data = word6()
    struct.pack_into('<H', data, 520, 65535)
    doc = parse_doc_word_stream(bytes(data))
    assert not doc.assets
    assert doc.sections[0].elements[0].text == 'Before picture'


def test_word6_inline_image_does_not_leave_new_paragraph_edge_spaces():
    doc = parse_doc_word_stream(bytes(word6(b'Before picture \x01 After picture\r')))
    elements = doc.sections[0].elements
    assert elements[0].text == 'Before picture'
    assert isinstance(elements[1], Image)
    assert elements[2].text == 'After picture'


def test_legacy_image_replacement_preserves_unrelated_empty_and_styled_paragraphs():
    from dochan.model.document import Paragraph, TextRun
    from dochan.model.table import Cell, Table
    from dochan.office_binary.doc_images import replace_legacy_image_markers

    empty = Paragraph()
    styled = Paragraph(runs=[TextRun(text='  unchanged  ', bold=True)])
    cell_empty = Paragraph()
    table = Table(rows=[[Cell(paragraphs=[cell_empty])]])
    marker = '\ue000doc-image-1\ue001'
    image = Image(image_format='wmf', image_data=wmf())
    marked = Paragraph(runs=[TextRun(text=marker)])
    result = replace_legacy_image_markers([empty, styled, table, marked], {marker: image})
    assert len(result) == 4
    assert result[0] is empty
    assert result[1] is styled
    assert styled.runs[0].text == '  unchanged  '
    assert styled.runs[0].bold
    assert table.rows[0][0].paragraphs == [cell_empty]
    assert table.rows[0][0].paragraphs[0] is cell_empty
    assert result[3] is image
