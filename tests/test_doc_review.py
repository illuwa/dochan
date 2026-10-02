"""Review regressions built only from synthetic MS-DOC stream bytes."""
import struct

from dochan.model.document import Document
from dochan.office_binary.doc_stories import Stories
from dochan.office_binary.doc_structure import parse_structured_doc
from test_doc_structure import _native_streams, _fake_reader, render
from test_doc_stories import Binary, plc, sttbf


def native(text):
    streams = _native_streams()
    raw = text.encode('cp1252')
    word = bytearray(streams['WordDocument'])
    struct.pack_into('<I', word, 76, len(raw))
    word[1024:1024 + len(raw)] = raw
    pcd = struct.pack('<IIHIH', 0, len(raw), 0, 0x40000800, 0)
    table = b'\x02' + struct.pack('<I', len(pcd)) + pcd
    struct.pack_into('<II', word, 154 + 33 * 8, 0, len(table))
    return {'WordDocument': bytes(word), '0Table': table}


def test_doc_review_page_break_preserves_words_in_paragraph():
    streams = native('Alpha\x0cBeta\r')
    doc = parse_structured_doc(streams['WordDocument'], streams['0Table'])
    assert [[p.text for p in s.elements] for s in doc.sections] == [['Alpha\nBeta']]


def test_doc_review_column_break_and_nonbreaking_hyphen():
    assert render('non\x1especific\x0enext\r')[0].text == 'non-specific\nnext'


def test_doc_review_nested_instruction_hides_link_suffix_and_macro():
    text = ('\x13 IF \x13 HYPERLINK "https://example.com" \x14label\x15'
            ' \x13 MACROBUTTON NoMacro secret\x15 = "x" "yes" "no" \x14no\x15\r')
    streams = native(text)
    doc = parse_structured_doc(streams['WordDocument'], streams['0Table'])
    assert [p.text for p in doc.find_all('paragraph')] == ['no']


def test_doc_review_instruction_bookmarks_hidden_but_result_bookmarks_visible():
    text = '\x13 IF secret \x14visible\x15\r'
    a, b = text.index('secret'), text.index('visible')
    binary = Binary(text, {21: sttbf(['Hidden', 'Visible']),
        22: plc([a, b, len(text)], struct.pack('<hHhH', 0, 0, 1, 0)),
        23: plc([a + 6, b + 7, len(text)])})
    stories = Stories(binary, Document())
    assert stories.markers(a) == []
    assert stories.markers(b)[0].text == '[bookmark: Visible] '


def test_doc_review_header_bookmark_uses_global_cp_range():
    text = 'Body\rHeader\r'
    binary = Binary(text, {21: sttbf(['HeaderMark']),
        22: plc([5, 12], struct.pack('<hH', 0, 0)), 23: plc([11, 12])},
        {'main': (0, 5), 'header': (5, 12)})
    doc = Document()
    stories = Stories(binary, doc)
    assert not doc.errors
    assert stories.markers(5)[0].text == '[bookmark: HeaderMark] '


def test_doc_review_does_not_structure_parse_stale_table(monkeypatch, tmp_path):
    streams = native('Current text\r')
    streams['1Table'] = streams['0Table']
    calls = []

    def failed_preferred(word, table, data):
        calls.append(table)
        return None

    monkeypatch.setattr('dochan.office_binary.doc_structure.parse_structured_doc', failed_preferred)
    doc = _fake_reader(monkeypatch, tmp_path, streams)
    assert len(calls) == 1
    assert doc.sections[0].elements[0].text == 'Current text'


def test_doc_review_unused_data_stream_is_not_read(monkeypatch, tmp_path):
    import dochan.office_binary.doc as module
    streams = native('Plain text\r')
    streams['Data'] = b'unused'
    original = module.read_ole_stream
    reads = []

    def tracked(ole, name, **kwargs):
        reads.append(name)
        return original(ole, name, **kwargs)

    monkeypatch.setattr(module, 'read_ole_stream', tracked)
    doc = _fake_reader(monkeypatch, tmp_path, streams)
    assert reads == ['WordDocument', '0Table']
    assert not doc.errors


def test_doc_review_plain_run_does_not_resolve_properties_per_character(monkeypatch):
    from dochan.office_binary.doc_binary import DocBinary
    streams = native('A' * 500 + '\r')
    original = DocBinary.char_props
    calls = []

    def counted(self, cp):
        calls.append(cp)
        return original(self, cp)

    monkeypatch.setattr(DocBinary, 'char_props', counted)
    doc = parse_structured_doc(streams['WordDocument'], streams['0Table'])
    assert doc.find_all('paragraph')[0].text == 'A' * 500
    assert len(calls) <= 4


def test_doc_review_bad_header_plc_retains_story_text_without_guessing_kind():
    from test_doc_stories import render as story_render
    text = 'Body\rHeader content\r'
    binary = Binary(text, {11: plc([0, 4, 2])},
                    {'main': (0, 5), 'header': (5, len(text))})
    doc = Document()
    stories = Stories(binary, doc)
    headers, trailers = stories.extras(lambda a, b: story_render(binary, stories, a, b))
    assert not headers
    assert [p.text for p in trailers] == ['Header content']
    assert any('headers' in error for error in doc.errors)
