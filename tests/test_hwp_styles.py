"""HWP 스타일의 이름·문단 모양과 직접 글자모양의 우선순위를 검증한다."""

import struct

from dochan.constants import HWPTAG_PARA_CHAR_SHAPE, HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT
from dochan.hwp.doc_info import DocInfo, DocInfoParser
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import RawRecord, SectionParser
from dochan.model.style import StyleEntry


def _paragraph(info, style_id=0, para_id=0xffff, pairs=b""):
    header = bytearray(22)
    struct.pack_into("<H", header, 8, para_id)
    header[10] = style_id
    def node(tag, data):
        return {"record": RawRecord(tag, 1, len(data), data), "children": []}
    paragraph = node(HWPTAG_PARA_HEADER, bytes(header))
    paragraph["children"] = [node(HWPTAG_PARA_TEXT, "text".encode("utf-16-le")),
                             node(HWPTAG_PARA_CHAR_SHAPE, pairs)]
    return SectionParser(info)._parse_paragraph_group(paragraph)[0]


def test_style_outline_para_shape_inherits_heading_level():
    info = DocInfo(styles=[StyleEntry(name="Custom", para_shape_id=0)])
    DocInfoParser()._parse_para_shape(struct.pack("<I", (1 << 23) | (2 << 25)), info)
    assert _paragraph(info).heading_level == 3


def test_direct_outline_para_shape_works_without_named_style():
    info = DocInfo()
    DocInfoParser()._parse_para_shape(struct.pack("<I", (1 << 23) | (4 << 25)), info)
    assert _paragraph(info, para_id=0).heading_level == 0


def test_missing_direct_char_shape_stays_plain_and_explicit_shape_applies():
    info = DocInfo(char_shapes=[CharShape(), CharShape(bold=True)],
                   styles=[StyleEntry(name="Custom", char_shape_id=1)])
    assert not _paragraph(info).runs[0].bold
    assert _paragraph(info, pairs=struct.pack("<II", 0, 1)).runs[0].bold
    assert not _paragraph(info, pairs=struct.pack("<II", 0, 0)).runs[0].bold


def test_subtitle_is_not_matched_as_title():
    assert _paragraph(DocInfo(styles=[StyleEntry(name="부제목")])).heading_level == 2
