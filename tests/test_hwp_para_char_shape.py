"""HWP 글자모양 구간의 레코드 배치와 원시 WCHAR 위치를 검증한다."""

import struct

import pytest

from dochan.constants import HWPTAG_PARA_CHAR_SHAPE, HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT
from dochan.control_char import get_advance_bytes
from dochan.hwp.doc_info import DocInfo
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.records.para_char_shape import parse_para_char_shape
from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.section import RawRecord, SectionParser


def _record_node(tag, data):
    return {"record": RawRecord(tag, 1, len(data), data), "children": []}


def _paragraph(text_data, pairs_data, doc_info=None):
    node = {
        "record": RawRecord(HWPTAG_PARA_HEADER, 0, 22, bytes(22)),
        "children": [
            _record_node(HWPTAG_PARA_TEXT, text_data),
            _record_node(HWPTAG_PARA_CHAR_SHAPE, pairs_data),
        ],
    }
    return SectionParser(doc_info)._parse_paragraph_group(node)[0]


def _shapes():
    return DocInfo(char_shapes=[CharShape(), CharShape(bold=True)])


def _pairs(*items):
    return b"".join(struct.pack("<II", position, shape_id) for position, shape_id in items)


def _text(value):
    return value.encode("utf-16-le") + struct.pack("<H", 13)


def test_char_shape_uses_eight_byte_position_and_id_pairs():
    data = bytes.fromhex("00000000 0a000000 0d000000 09000000")
    assert parse_para_char_shape(data) == [(0, 10), (13, 9)]
    assert parse_para_char_shape(data + b"\x01\x02\x03") == [(0, 10), (13, 9)]
    assert parse_para_char_shape(b"") == []
    assert parse_para_char_shape(_pairs((0, 65536))) == [(0, 65536)]


def test_raw_to_text_tracks_extended_control_without_output_character():
    control = struct.pack("<H", 11) + bytes(get_advance_bytes(11) - 2)
    result = parse_para_text(_text("ab")[:-2] + control + _text("cd"))

    assert result["text"] == "abcd"
    assert result["raw_to_text"][2] == 2
    assert result["raw_to_text"][10] == 2
    assert result["raw_to_text"][12] == 4
    assert len(result["raw_to_text"]) == 13
    assert result["ctrl_positions"] == [(2, 11)]


def test_raw_to_text_tracks_tab_surrogate_and_unused_wchar():
    tab = struct.pack("<H", 9) + bytes(get_advance_bytes(9) - 2)
    data = _text("a")[:-2] + tab + _text("😀")[:-2] + struct.pack("<H", 0) + _text("b")
    result = parse_para_text(data)

    assert result["text"] == "a\t😀b"
    assert result["raw_to_text"][1:10] == [1] * 8 + [2]
    assert result["raw_to_text"][9:13] == [2, 2, 3, 3]
    assert result["raw_to_text"][-1] == 4


def test_runs_split_at_raw_wchar_boundaries_and_keep_formatting():
    para = _paragraph(_text("abcdefgh"), _pairs((0, 0), (3, 1)), _shapes())

    assert [run.text for run in para.runs] == ["abc", "defgh"]
    assert [run.bold for run in para.runs] == [False, True]
    assert para.text == "abcdefgh"


def test_runs_map_extended_control_before_splitting():
    control = struct.pack("<H", 11) + bytes(get_advance_bytes(11) - 2)
    data = _text("abc")[:-2] + control + _text("defgh")
    para = _paragraph(data, _pairs((0, 0), (11, 1)), _shapes())

    assert [run.text for run in para.runs] == ["abc", "defgh"]
    assert [run.bold for run in para.runs] == [False, True]
    assert para.text == "abcdefgh"


def test_missing_head_boundary_uses_first_shape_for_head():
    para = _paragraph(_text("abcdefgh"), _pairs((3, 1)), _shapes())

    assert [run.text for run in para.runs] == ["abc", "defgh"]
    assert [run.bold for run in para.runs] == [True, True]


@pytest.mark.parametrize("pairs_data, expected", [
    (_pairs((0, 0), (5, 1), (2, 1), (999, 1)), ["abcde", "fgh"]),
    (_pairs((3, 1)), ["abc", "defgh"]),
    (_pairs((999, 1)), ["abcdefgh"]),
    (_pairs((0, 0), (3, 9999)), ["abc", "defgh"]),
    (b"", ["abcdefgh"]),
    (b"\x01\x02\x03", ["abcdefgh"]),
    (struct.pack("<IH", 0, 0) + struct.pack("<IH", 3, 1), None),
])
def test_malformed_boundaries_never_duplicate_or_drop_text(pairs_data, expected):
    para = _paragraph(_text("abcdefgh"), pairs_data, _shapes())

    if expected is not None:
        assert [run.text for run in para.runs] == expected
    assert "".join(run.text for run in para.runs) == "abcdefgh"
    assert all(run.text for run in para.runs)


def test_runs_keep_text_when_doc_info_is_missing():
    para = _paragraph(_text("abcdefgh"), _pairs((0, 0), (3, 1)))
    assert "".join(run.text for run in para.runs) == "abcdefgh"


def test_trailing_high_surrogate_becomes_replacement_char():
    """레코드 끝에 짝 없는 high surrogate 가 남으면 대체 문자로 바꾼다 (Opus 감수 P3)."""
    result = parse_para_text(b"A\x00\x00\xd8")
    assert result["text"] == "A\ufffd"
    assert result["raw_to_text"] == [0, 1, 2]
    result["text"].encode("utf-8")  # 인코딩 가능해야 한다
