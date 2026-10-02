"""Final review regressions, using synthetic PPT records only."""
import struct

import pytest

from dochan.office_binary.officeart import parse_records
from dochan.office_binary.ppt import parse_ppt_document_stream
from dochan.office_binary.ppt_text import read_hyperlinks, render_text, shape_hyperlink
from dochan.output.markdown import to_markdown
from test_ppt_structure import record, presentation, sheet, shape, slide_list
from test_ppt_text import block
from test_ppt_text import pf, cf


def test_fix2_empty_slide_list_recovers_text_with_provenance():
    data, cu = presentation([(2, sheet(shapes=shape(b'Recovered')))], [])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['Recovered']
    assert doc.find_all('paragraph')[0].provenance.path.endswith('#legacy-recovery')
    assert any('legacy text' in e for e in doc.errors)


def test_fix2_empty_damaged_drawing_recovers_legacy_text():
    # A bad OfficeArt header hides a valid text atom from the tree parser.
    drawing = record(1036, b'\x00\x00\xff\xff\xff\xff\xff\xff' + record(4008, b'Recovered'), container=True)
    data, cu = presentation([(2, record(1006, drawing, container=True))], [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['Recovered']
    assert any('legacy text' in e for e in doc.errors)


def test_fix2_picture_is_one_model_element_at_shape_position():
    data, cu = presentation([(2, sheet(shapes=shape(b'Before', y=0) +
                            shape(pib=1, description='Diagram', y=100) + shape(b'After', y=200)))],
                            [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    elements = doc.sections[0].elements
    assert [type(e).__name__ for e in elements] == ['Paragraph', 'Image', 'Paragraph']
    assert [p.text for p in doc.find_all('paragraph')] == ['Before', 'After']
    md = to_markdown(doc)
    assert md.count('![') == 1
    assert md.index('Before') < md.index('![Diagram]') < md.index('After')


def test_fix2_picture_description_and_name_contract():
    props = [(0x4104, 1), (0x8105, 'File description'), (0x8380, 'Picture 1')]
    headers, strings = [], b''
    for key, value in props:
        if isinstance(value, str):
            encoded = (value + '\0').encode('utf-16le')
            strings += encoded
            value = len(encoded)
        headers.append(struct.pack('<HI', key, value))
    sp = record(0xF004, record(0xF00A, struct.pack('<II', 1, 0xA00)) +
                record(0xF00B, b''.join(headers) + strings, instance=3), container=True)
    data, cu = presentation([(2, sheet(shapes=sp))], [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert doc.find_all('image')[0].alt_text == 'File description Picture 1'


def test_fix2_display_name_only_internal_link():
    links = record(4055, record(4051, struct.pack('<I', 7)) +
                   record(4026, 'Slide 1'.encode('utf-16le')), container=True)
    assert read_hyperlinks(parse_records(links), [256, 257])[7] == '#PowerPoint Document#slide1'


def test_fix2_empty_action_shape_preserves_saved_hyperlink_label():
    links = record(4055, record(4051, struct.pack('<I', 7)) +
                   record(4026, 'Slide 1'.encode('utf-16le')), container=True)
    from test_ppt_text import interaction
    sp = record(0xF004, record(0xF00A, struct.pack('<II', 1, 0xA00)) +
                record(0xF011, interaction(7)), container=True)
    data, cu = presentation([(2, sheet(shapes=sp))], [links, slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['Slide 1 <#PowerPoint Document#slide1>']


def test_fix2_jump_action_resolves_relative_slide():
    atom = struct.pack('<IIBBBBB3x', 0, 7, 3, 0, 1, 0, 0)
    records = parse_records(record(4082, record(4083, atom), container=True))
    assert shape_hyperlink(records, {}, slide_index=2, slide_count=4) == '#PowerPoint Document#slide3'
    assert shape_hyperlink(records, {}, slide_index=4, slide_count=4) == ''
    p = render_text(block('Next', tail=record(4082, record(4083, atom), container=True) +
                          record(4063, struct.pack('<II', 0, 4))), None,
                    slide_index=2, slide_count=4)[0]
    assert p.text == 'Next <#PowerPoint Document#slide3>'


def test_fix2_style9_auto_numbering_matches_pptx():
    text = 'One\rTwo\rThree'
    style = pf(len(text) + 1, mask=1, props=struct.pack('<H', 1)) + cf(len(text) + 1)
    textbox = record(3999, struct.pack('<I', 1)) + record(4008, text.encode()) + record(4001, style)
    # TextPFException9: blipRef, hasAutoNumber, scheme=arabicPeriod, start=6;
    # TextCFException9 and TextSIException carry no properties.
    ext = struct.pack('<IhHHhII', 0x03800000, -1, 1, 3, 6, 0, 0)
    tag = record(5000, record(5002, record(4026, '___PPT9'.encode('utf-16le')) +
                 record(5003, record(4012, ext)), container=True), container=True)
    sp = record(0xF004, record(0xF00A, struct.pack('<II', 1, 0xA00)) +
                record(0xF011, tag) + record(0xF00D, textbox), container=True)
    data, cu = presentation([(2, sheet(shapes=sp))], [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['6. One', '7. Two', '8. Three']


@pytest.mark.parametrize('extension', [b'\0', struct.pack('<I', 0x40000000)])
def test_fix2_truncated_or_unknown_number_extension_keeps_text(extension):
    from dochan.office_binary.ppt_text import apply_auto_numbers
    b = block('safe', pf(5, mask=1, props=struct.pack('<H', 1)) + cf(5))
    errors = []
    apply_auto_numbers([b], extension, errors)
    assert render_text(b, None)[0].text == '• safe'
    assert errors and all(e.startswith('WARN:') for e in errors)


@pytest.mark.parametrize('label', ['Slide 0', 'Slide 9999999999', 'Slide 2 notes', 'https://example.com'])
def test_fix2_display_only_link_does_not_invent_a_target(label):
    links = record(4055, record(4051, struct.pack('<I', 7)) +
                   record(4026, label.encode('utf-16le')), container=True)
    assert read_hyperlinks(parse_records(links), [256, 257]) == {}


def test_fix2_healthy_empty_latest_slide_does_not_revive_older_text():
    data, cu = presentation([(2, sheet(shapes=shape(b'Old text')))],
                            [slide_list([(2, 256, b'')])], previous=(2, sheet()))
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert doc.find_all('paragraph') == []
    assert doc.errors == []


def test_fix2_missing_picture_does_not_revive_older_slide_text():
    data, cu = presentation([(2, sheet(shapes=shape(b'Old text')))],
                            [slide_list([(2, 256, b'')])], previous=(2, sheet(shapes=shape(pib=1))))
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert doc.find_all('paragraph') == []
    assert any('BLIP unavailable' in e for e in doc.errors)


def test_fix2_auto_number_legacy_recovery_does_not_duplicate_body():
    from dochan.model.document import Document, Section
    from dochan.office_binary.ppt import _supplement_legacy_text
    b = block('One', pf(4, mask=1, props=struct.pack('<H', 1)) + cf(4))
    b.paragraph_numbers = [(3, 1)]
    doc = Document(sections=[Section(elements=render_text(b, None))])
    _supplement_legacy_text(doc, record(4008, b'One'), 'PowerPoint Document', 1000, 100)
    assert [p.text for p in doc.find_all('paragraph')] == ['1. One']
