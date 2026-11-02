"""Batch decoding and bounded temporary allocation for HWP parsing."""
import struct
from unittest.mock import patch

import pytest

from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.section import RawRecord, SectionParser


def test_plain_text_does_not_unpack_each_wchar():
    text = '가나다abc' * 200
    with patch('dochan.hwp.records.para_text.struct.unpack_from', wraps=struct.unpack_from) as unpack:
        result = parse_para_text((text + '\rignored').encode('utf-16-le'))
    assert result['text'] == text
    assert result['raw_to_text'] == list(range(len(text) + 1))
    assert unpack.call_count <= 8


def test_list_repair_allocates_at_most_one_record_per_changed_input():
    records = [RawRecord(72, 0, 0, b'', 0), RawRecord(66, 0, 0, b'', 1),
               RawRecord(67, 1, 0, b'', 2), RawRecord(68, 1, 0, b'', 3)]
    with patch('dochan.hwp.section.RawRecord', wraps=RawRecord) as factory:
        tree = SectionParser()._build_tree(records)
    assert factory.call_count <= 3
    assert [r.level for r in records] == [0, 0, 1, 1]
    assert tree[0]['record'] is records[0]
    paragraph = tree[0]['children'][0]
    assert paragraph['record'].level == 2
    assert [node['record'].level for node in paragraph['children']] == [3, 3]


@pytest.mark.parametrize('tail', [b'', b'\xff'])
def test_batch_text_keeps_surrogates_and_control_boundaries(tail):
    # A valid surrogate pair consumes two raw positions but one text position;
    # unmatched surrogates each produce a replacement, and odd bytes are ignored.
    data = '가A'.encode('utf-16-le') + bytes.fromhex('00d8 00dc 00d8 4200 00dc 0d00') + tail
    result = parse_para_text(data)
    assert result['text'] == '가A\U00010000\ufffdB\ufffd'
    assert result['raw_to_text'] == [0, 1, 2, 2, 3, 4, 5, 6]
    assert result['ctrl_positions'] == result['field_marks'] == result['inline_controls'] == []


def test_single_shape_does_not_allocate_boundary_iterator():
    from dochan.hwp.doc_info import DocInfo
    from dochan.hwp.records.char_shape import CharShape

    shape = CharShape(bold=True, italic=True, base_size=1200, underline_type=1,
                      strikeout=1, superscript=True, subscript=True)
    parser = SectionParser(DocInfo(char_shapes=[shape]))
    text = parse_para_text('한글\r'.encode('utf-16-le'))
    with patch('dochan.hwp.section.struct.iter_unpack', wraps=struct.iter_unpack) as unpack:
        runs, tail = parser._text_runs(text, struct.pack('<II', 0, 0), 1)
    assert not tail
    assert len(runs) == 1
    assert (runs[0].text, runs[0].bold, runs[0].italic, runs[0].font_size_pt,
            runs[0].underline, runs[0].strikeout, runs[0].superscript,
            runs[0].subscript) == ('한글', True, True, 12.0, True, True, True, True)
    assert unpack.call_count == 0


def test_plain_paragraph_skips_empty_inline_object_pipeline():
    from dochan.constants import HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT

    raw = '일반 문단\r'.encode('utf-16-le')
    node = {'record': RawRecord(HWPTAG_PARA_HEADER, 0, 0, b''), 'children': [
        {'record': RawRecord(HWPTAG_PARA_TEXT, 1, len(raw), raw), 'children': []}]}
    from dochan.hwp.section import _merge_inline_objects

    with patch('dochan.hwp.section._merge_inline_objects', wraps=_merge_inline_objects) as merge:
        elements = SectionParser()._parse_paragraph_group(node)
    assert len(elements) == 1
    assert elements[0].text == '일반 문단'
    assert merge.call_count == 0
