"""Synthetic MS-DOC PLCs; no external corpus is required."""
import struct

from dochan.model.document import Document, Paragraph, TextRun
from dochan.office_binary.doc_stories import Stories


def plc(cps, records=b''):
    return struct.pack('<' + 'I' * len(cps), *cps) + records


def sttbf(names):
    return struct.pack('<HHH', 0xffff, len(names), 0) + b''.join(
        struct.pack('<H', len(n)) + n.encode('utf-16-le') for n in names)


class Binary:
    def __init__(self, text, blobs=None, stories=None):
        self.text = text
        self._blobs = blobs or {}
        self.stories = stories or {'main': (0, len(text))}

    def blob(self, index):
        return self._blobs.get(index, b'')


def render(binary, stories, start, end):
    runs = []
    for cp in range(start, end):
        runs.extend(stories.markers(cp))
        if not stories.hidden(cp) and binary.text[cp] not in '\x02\x05\r':
            runs.append(TextRun(binary.text[cp], link=stories.link(cp)))
    return [Paragraph(runs)] if runs else []


def test_doc_story_hyperlink_and_field_result_cp_positions():
    text = 'Go \x13 HYPERLINK "https://example.com" \x14label\x15.\r'
    start, sep, end = [text.index(x) for x in '\x13\x14\x15']
    binary = Binary(text, {16: plc([start, sep, end, len(text)], bytes([19, 88, 20, 255, 21, 128]))})
    stories = Stories(binary, Document())
    paragraph = render(binary, stories, 0, len(text))[0]
    assert paragraph.text == 'Go label.'
    assert ''.join(r.text for r in paragraph.runs if r.link) == 'label'
    assert {r.link for r in paragraph.runs if r.link} == {'https://example.com'}


def test_doc_story_nested_fields_and_internal_hyperlink():
    text = '\x13 HYPERLINK \\l "Summary" \x14See \x13 SEQ Table \x141\x15\x15'
    binary = Binary(text)
    stories = Stories(binary, Document())
    result = render(binary, stories, 0, len(text))[0]
    assert result.text == 'See 1'
    assert all(r.link == '#Summary' for r in result.runs)


def test_doc_story_bookmarks_validate_matching_end_and_hide_private_names():
    text = 'Title\r'
    binary = Binary(text, {21: sttbf(['Summary', '_GoBack']),
        22: plc([0, 2, 6], struct.pack('<hHhH', 0, 0, 1, 0)),
        23: plc([4, 5, 6])})
    stories = Stories(binary, Document())
    assert render(binary, stories, 0, 6)[0].text == '[bookmark: Summary] Title'


def test_doc_story_notes_have_body_order_numbering_and_comment_author():
    body, foot, annotation, endnote = 'A\x02B\x02C\x05\r', '\x02Foot\r\r', '\x05Comment\r\r', '\x02End\r\r'
    text = body + foot + annotation + endnote
    a, b, c = len(body), len(body + foot), len(body + foot + annotation)
    owner = 'Reviewer'
    atrd = struct.pack('<H', 1) + 'R'.encode('utf-16-le') + b'\0' * 16 + struct.pack('<H', 0) + b'\0' * 8
    binary = Binary(text, {2: plc([3, 7], b'\x01\0'), 3: plc([0, 6, 7]),
        46: plc([1, 7], b'\x01\0'), 47: plc([0, 5, 6]),
        4: plc([5, 7], atrd), 5: plc([0, 9, 10]),
        36: struct.pack('<H', len(owner)) + owner.encode('utf-16-le')},
        {'main': (0, a), 'footnote': (a, b), 'annotation': (b, c), 'endnote': (c, len(text))})
    stories = Stories(binary, Document())
    assert render(binary, stories, 0, a)[0].text == 'A[1]B[2]C[comment 1]'
    headers, notes = stories.extras(lambda start, end: render(binary, stories, start, end))
    assert not headers
    assert [(n.type, n.number, n.text) for n in notes] == [
        ('endnote', 1, 'End'), ('footnote', 2, 'Foot'), ('comment', 1, 'Comment')]
    assert notes[2].author == owner
    assert stories.markers(1)[0].note_ref == 1
    assert stories.markers(3)[0].note_reference_type == 'footnote'


def test_doc_story_headers_and_footers_use_plcfhdd_slots():
    body = 'Body\r'
    headers = 'Header\rFooter\r'
    # Six special separator slots, then even/odd header and even/odd footer.
    binary = Binary(body + headers, {11: plc([0, 0, 0, 0, 0, 0, 0, 0, 7, 7, 14, 14, 14])},
                    {'main': (0, 5), 'header': (5, 19)})
    stories = Stories(binary, Document())
    before, after = stories.extras(lambda start, end: render(binary, stories, start, end))
    assert [(x.type, x.text) for x in before + after] == [('header', 'Header'), ('footer', 'Footer')]


def test_doc_story_malformed_field_keeps_visible_text_and_warns():
    document = Document()
    binary = Binary('Before \x13 unfinished')
    stories = Stories(binary, document)
    assert 'Before ' in render(binary, stories, 0, len(binary.text))[0].text
    assert document.errors


def test_doc_story_bad_note_plc_warns_without_losing_main_text():
    document = Document()
    binary = Binary('Body\rNote', {2: b'\xff' * 5, 3: plc([0, 99999])},
                    {'main': (0, 5), 'footnote': (5, 9)})
    stories = Stories(binary, document)
    assert render(binary, stories, 0, 5)[0].text == 'Body'
    assert document.errors


def test_doc_story_preserves_explicit_empty_headers_but_skips_overrun_sentinel():
    binary = Binary('Body\r\r\rHeader\r\r',
                    {11: plc([0, 0, 0, 0, 0, 0, 0, 2, 9, 12])},
                    {'main': (0, 5), 'header': (5, 15)})
    stories = Stories(binary, Document())
    before, after = stories.extras(lambda start, end: render(binary, stories, start, end))
    assert [(x.type, x.text) for x in before + after] == [('header', ''), ('header', 'Header')]


def test_doc_story_textbox_range_inserted_once_at_anchor_not_trailer():
    body, boxes = 'Before\x08After\r', 'Box one\rBox two\r\r'
    binary = Binary(body + boxes, {56: plc([0, 8, 16, 999], b'\0' * 66)},
                    {'main': (0, len(body)), 'textbox': (len(body), len(body + boxes))})
    stories = Stories(binary, Document())
    callback = lambda start, end: render(binary, stories, start, end)
    assert [p.text for p in stories.textbox(0, callback)] == ['Box one']
    assert stories.textbox(0, callback) == []
    _, trailing = stories.extras(callback)
    assert [p.text for p in trailing] == ['Box two']


def test_doc_story_suffix_uses_existing_docx_visible_url_contract():
    text = '\x13 HYPERLINK "https://example.com" \x14label\x15'
    stories = Stories(Binary(text), Document())
    assert stories.suffix(len(text) - 1) == ' <https://example.com>'
    assert stories.suffix(0) == ''


def test_doc_story_macrobutton_without_cached_separator_keeps_display_text():
    text = '\x13MACROBUTTON NoMacro [Document Title]\x15'
    stories = Stories(Binary(text), Document())
    assert render(stories.binary, stories, 0, len(text))[0].text == '[Document Title]'


def xstz(text):
    return struct.pack('<H', len(text)) + text.encode('utf-16-le') + b'\0\0'


def form_binary(instruction, form_type, result, default, choices=None):
    text = '\x13 ' + instruction + ' \x01\x15'
    payload = struct.pack('<IHHH', 0xffffffff, form_type | (result << 2), 0, 20)
    payload += xstz('Field')
    payload += xstz(default) if form_type == 0 else struct.pack('<H', default)
    payload += xstz('') * 5
    if choices is not None:
        payload += sttbf(choices)
    binary = Binary(text)
    binary.data = struct.pack('<IHH', 68 + len(payload), 68, 0) + b'\0' * 60 + payload
    binary.char_props = lambda cp: {'special': True, 'pic_location': 0}
    return binary


def test_doc_story_form_checkbox_uses_ffdata_current_and_default_values():
    for current, default, expected in [(1, 0, '[x]'), (0, 1, '[ ]'), (25, 1, '[x]')]:
        binary = form_binary('FORMCHECKBOX', 1, current, default)
        stories = Stories(binary, Document())
        assert render(binary, stories, 0, len(binary.text))[0].text == expected


def test_doc_story_form_dropdown_uses_default_selection_and_text_default():
    binary = form_binary('FORMDROPDOWN', 2, 25, 1, ['First', 'Second'])
    stories = Stories(binary, Document())
    assert render(binary, stories, 0, len(binary.text))[0].text == 'Second'
    binary = form_binary('FORMTEXT', 0, 25, 'Default text')
    stories = Stories(binary, Document())
    assert render(binary, stories, 0, len(binary.text))[0].text == 'Default text'


def test_doc_story_truncated_form_data_warns_without_exception():
    binary = form_binary('FORMCHECKBOX', 1, 25, 1)
    binary.data = binary.data[:80]
    document = Document()
    stories = Stories(binary, document)
    assert stories.markers(0) == []
    assert document.errors


def test_doc_story_empty_dropdown_list_is_valid_empty_control():
    binary = form_binary('FORMDROPDOWN', 2, 25, 0, [])
    document = Document()
    Stories(binary, document)
    assert document.errors == []


def test_doc_story_fallback_stops_scanning_at_control_limit(monkeypatch):
    import dochan.office_binary.doc_stories as module
    monkeypatch.setattr(module, '_MAX_RECORDS', 4)

    class CountedText(str):
        reads = 0

        def __getitem__(self, key):
            self.reads += 1
            assert self.reads <= 5, 'scan must stop before allocating all control positions'
            return super().__getitem__(key)

    text = CountedText('\x13' * 100)
    document = Document()
    Stories(Binary(text), document)
    assert text.reads == 5
    assert any('record limit' in warning for warning in document.errors)


def test_doc_story_field_limit_is_global_across_secondary_stories(monkeypatch):
    import dochan.office_binary.doc_stories as module
    monkeypatch.setattr(module, '_MAX_RECORDS', 4)
    names = ['main', 'header', 'footnote', 'annotation', 'endnote']
    text = '\x13SEQ\x15' * len(names)
    ranges = {name: (i * 5, (i + 1) * 5) for i, name in enumerate(names)}
    document = Document()
    stories = Stories(Binary(text, stories=ranges), document)
    assert len(stories.fields) == 4
    assert any('field count limit' in warning for warning in document.errors)


def test_doc_story_header_table_is_not_discarded_for_lacking_text_attribute():
    from dochan.model.table import Cell, Table
    binary = Binary('Body\rHeader\r', {11: plc([0, 0, 0, 0, 0, 0, 0, 7])},
                    {'main': (0, 5), 'header': (5, 12)})
    stories = Stories(binary, Document())
    table = Table(rows=[[Cell(paragraphs=[Paragraph([TextRun('Header')])])]])
    headers, _ = stories.extras(lambda start, end: [table])
    assert headers[0].paragraphs == [table]
    assert headers[0].text == 'Header'
