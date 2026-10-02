"""Characterize the existing shared-story textbox path with synthetic bytes.

These tests do not establish unobserved FTXBXS destination-link semantics.
"""
import struct
from types import SimpleNamespace

import pytest

from dochan.model.document import Document
from dochan.office_binary.doc_images import DocImages
from dochan.office_binary.doc_stories import Stories


@pytest.mark.parametrize('header', [False, True])
def test_shared_textbox_story_emits_once_for_linked_shape_ids(header):
    text = 'first\rsecond\rthird\r'
    # One text story shared by three shape IDs; low 16 bits vary by box.
    record = struct.pack('<IIHIII', 3, 0, 0, 0xffffffff, 1025, 0)
    plc = struct.pack('<II', 0, len(text)) + record
    story = 'header_textbox' if header else 'textbox'
    index = 58 if header else 56
    binary = SimpleNamespace(text=text, stories={story: (0, len(text))},
                             blob=lambda i: plc if i == index else b'')
    doc = Document()
    stories = Stories(binary, doc)
    pictures = DocImages(binary, doc)
    pictures._anchors = {0: 1025, 1: 1026, 2: 1027}
    pictures._shapes = {
        1025 + i: SimpleNamespace(textbox_id=(1 << 16) | i) for i in range(3)
    }
    output = []
    calls = []

    def render(start, end):
        calls.append((start, end))
        return text[start:end].splitlines()

    for cp in (2, 0, 1):
        output.extend(stories.textbox(pictures.textbox_at(cp), render, header=header))
    _, trailing = stories.extras(render)
    assert output == ['first', 'second', 'third']
    assert calls == [(0, len(text))]
    assert trailing == []
    assert doc.errors == []
