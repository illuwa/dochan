"""Synthetic factoid annotations preserve the underlying text contract."""
import struct

import pytest

from dochan.office_binary.doc_binary import DocBinary
from dochan.office_binary.doc_structure import parse_structured_doc
from dochan.output.markdown import to_markdown
from scripts.probe_doc_factoids import factoid_ranges
from test_doc_binary import make_binary


def factoid_binary():
    text = 'Controlled Smart text\r'
    original = make_binary(text)
    word, table = bytearray(original.word), bytearray(original.table)
    word.extend(bytes(4200 - len(word)))
    word[4096:4096 + len(text)] = text.encode('ascii')
    word[154 + 93 * 8:154 + 119 * 8] = bytes(26 * 8)
    struct.pack_into('<H', word, 152, 119)
    struct.pack_into('<I', table, 15, 0x40002000)
    blobs = {
        114: struct.pack('<HHHHIHHI', 0xffff, 1, 0, 6, 42, 0, 1, 0),
        115: struct.pack('<IIHHH', 11, len(text), 0, 0, 0),
        117: struct.pack('<III', 16, len(text), 0),
    }
    for index, blob in blobs.items():
        struct.pack_into('<II', word, 154 + index * 8, len(table), len(blob))
        table.extend(blob)
    return DocBinary(bytes(word), bytes(table))


def test_doc_factoid_text_remains_inline_without_annotation_markup():
    binary = factoid_binary()
    assert binary.valid
    assert factoid_ranges(binary) == [(11, 16)]
    doc = parse_structured_doc(binary.word, binary.table)
    assert doc.find_all('paragraph')[0].text == 'Controlled Smart text'
    assert to_markdown(doc) == 'Controlled Smart text'


@pytest.mark.parametrize('index,blob', [(115, b'bad'), (117, b''),
    (115, struct.pack('<IIHHH', 11, 22, 5, 0, 0)),
    (115, struct.pack('<IIIH', 11, 22, 65536, 0)),
    (117, struct.pack('<III', 1000, 22, 0))])
def test_factoid_probe_rejects_malformed_ranges(index, blob):
    binary = factoid_binary()
    original = binary.blob
    binary.blob = lambda slot: blob if slot == index else original(slot)
    with pytest.raises(ValueError):
        factoid_ranges(binary)
