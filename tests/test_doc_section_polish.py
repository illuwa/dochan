"""Section PLC boundaries, inline page breaks and resource limits."""
import struct

import pytest

from dochan.office_binary.doc_binary import DocBinary
from dochan.office_binary.doc_structure import parse_structured_doc
from test_doc_review import native


def streams_with_sections(text, cps=None):
    streams = native(text)
    if cps is not None:
        plc = struct.pack('<%dI' % len(cps), *cps) + b'\0' * (12 * (len(cps) - 1))
        word = bytearray(streams['WordDocument'])
        table = streams['0Table']
        struct.pack_into('<II', word, 154 + 6 * 8, len(table), len(plc))
        streams['WordDocument'] = bytes(word)
        streams['0Table'] = table + plc
    return streams


def parse(streams):
    return parse_structured_doc(streams['WordDocument'], streams['0Table'])


def test_page_break_in_field_result_stays_in_one_paragraph():
    doc = parse(native('x\x13 HYPERLINK "http://a.b" \x14li\x0cnk\x15y\r'))
    assert len(doc.sections) == 1
    assert [p.text for p in doc.find_all('paragraph')] == ['xli\nnk <http://a.b>y']


def test_page_break_inside_cell_does_not_split_paragraph_record():
    streams = native('cell\x0ccontinued\x07')
    binary = DocBinary(streams['WordDocument'], streams['0Table'])
    records = list(binary.paragraphs(0, len(binary.text)))
    assert len(records) == 1
    assert records[0].text == 'cell\x0ccontinued\x07'
    assert [p.text for p in parse(streams).find_all('paragraph')] == ['cell\ncontinued']


def test_only_plc_boundaries_create_sections_and_own_paragraph_properties():
    text = 'first\x0csecond\x0cthird\r'
    streams = streams_with_sections(text, [0, 6, len(text)])
    doc = parse(streams)
    assert [[p.text for p in s.elements] for s in doc.sections] == [['first'], ['second\nthird']]
    binary = DocBinary(streams['WordDocument'], streams['0Table'])
    assert [p.text for p in binary.paragraphs(0, len(text))] == ['first\x0c', 'second\x0cthird\r']


@pytest.mark.parametrize('cps', [[0, 8, 3, 12], [0, 99, 100], [2, 5, 12]])
def test_invalid_section_plc_warns_and_retains_text(cps):
    doc = parse(streams_with_sections('first\x0ctail\r', cps))
    assert len(doc.sections) == 1
    assert [p.text for p in doc.find_all('paragraph')] == ['first\ntail']
    assert any('WARN:' in e and 'section' in e.lower() for e in doc.errors)


def test_section_limit_coalesces_tail_without_losing_text(monkeypatch):
    monkeypatch.setattr('dochan.office_binary.doc_binary.MAX_SECTIONS', 3, raising=False)
    text = 'a\x0cb\x0cc\x0cd\x0ce\r'
    doc = parse(streams_with_sections(text, [0, 2, 4, 6, 8, 10]))
    assert len(doc.sections) == 3
    assert [[p.text for p in s.elements] for s in doc.sections] == [['a'], ['b'], ['c\nd\ne']]
    assert any('WARN:' in e and 'section limit' in e for e in doc.errors)


def test_empty_section_ranges_and_main_end_cp_are_valid():
    # Real producers retain empty section descriptors and a main-end boundary
    # before the terminal CP that also includes secondary stories.
    doc = parse(streams_with_sections('a\x0cb\x0c', [0, 0, 2, 4, 19]))
    assert [[p.text for p in s.elements] for s in doc.sections] == [['a'], ['b']]
    assert not doc.errors


def test_page_break_flood_is_one_section():
    doc = parse(native('a\x0c' * 500000))
    assert len(doc.sections) == 1
    assert doc.find_all('paragraph')[0].text == 'a\n' * 500000
