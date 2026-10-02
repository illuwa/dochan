"""Regression coverage for reviewed legacy image boundaries and work limits."""
import struct
from types import SimpleNamespace

from dochan.model.document import Document, Paragraph, TextRun
from dochan.model.image import Image
from dochan.office_binary.doc import parse_doc_word_stream
from dochan.office_binary.doc_images import (
    DocImages, _direct_wmf, replace_legacy_image_markers,
)
from test_doc_legacy_images import picf, wmf, word6


def test_word6_picture_only_document_keeps_image_and_section():
    doc = parse_doc_word_stream(bytes(word6(b'\x01\r')))
    assert len(doc.sections) == 1
    assert len(doc.sections[0].elements) == 1
    assert isinstance(doc.sections[0].elements[0], Image)
    assert doc.sections[0].elements[0].image_data == wmf()
    assert len(doc.assets) == 1


def test_word6_field_instruction_picture_does_not_leave_orphan_asset():
    doc = parse_doc_word_stream(bytes(word6(
        b'Before ordinary text ' * 10 + b'\r\x13INCLUDEPICTURE \x01\x14Visible result\x15\r')))
    assert not doc.assets
    assert [p.text for p in doc.find_all('paragraph')] == [
        ('Before ordinary text ' * 10).strip(), 'Visible result']


def test_word97_mm8_is_not_exported_as_a_legacy_wmf():
    word = struct.pack('<HH', 0xa5ec, 0xc1) + bytes(188)
    binary = SimpleNamespace(data=picf(), word=word, text='\x01', blob=lambda n: b'',
                             char_props=lambda cp: {'special': True, 'pic_location': 0})
    doc = Document()
    assert DocImages(binary, doc).image_at(0) is None
    assert not doc.assets


def test_word6_table_cell_picture_reaches_markdown():
    from dochan.output.markdown import to_markdown

    data = word6(b'First cell with ordinary readable text\t\x13INCLUDEPICTURE x\x14\x01\x15\rNext\tCell\r')
    doc = parse_doc_word_stream(bytes(data))
    assert '![이미지](image1.wmf)' in to_markdown(doc)


def test_image_marker_replacement_copies_only_consumed_text():
    class CountedText(str):
        copied = 0

        def partition(self, separator):
            parts = super().partition(separator)
            type(self).copied += sum(map(len, parts))
            return tuple(type(self)(part) for part in parts)

        def __getitem__(self, key):
            part = super().__getitem__(key)
            if isinstance(key, slice):
                type(self).copied += len(part)
            return type(self)(part)

    marker = '\ue000doc-image-1\ue001'
    image = Image(image_format='wmf', image_data=wmf())
    text = CountedText(marker * 1000 + 'tail' * 25000)
    result = replace_legacy_image_markers(
        [Paragraph(runs=[TextRun(text=text)])], {marker: image})
    assert len(result) == 1001
    assert all(element is image for element in result[:-1])
    assert result[-1].text == 'tail' * 25000
    assert CountedText.copied <= 4 * len(text)


def test_wmf_record_limit_accepts_boundary_and_rejects_one_more():
    def payload(records):
        return (struct.pack('<HHHIHIH', 1, 9, 0x300, 9 + 3 * records, 0, 3, 0)
                + struct.pack('<IH', 3, 0x1e) * (records - 1)
                + struct.pack('<IH', 3, 0))

    assert _direct_wmf(payload(100000)) == payload(100000)
    assert _direct_wmf(payload(100001)) is None
