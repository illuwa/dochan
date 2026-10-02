"""손상된 중첩 컨트롤만 버리고 같은 문단의 내용과 예약을 보존한다."""


import pytest

from dochan.constants import HWPTAG_PARA_HEADER
from dochan.hwp.doc_info import DocInfo
from dochan.hwp.section import RawRecord, SectionParser
from dochan.model.table import Table
from test_parser_hardening_review import (
    _hwp_cell_with_paragraph, _hwp_table_control_node, _hwp_text_paragraph,
)


@pytest.mark.parametrize("failure", ["cells", "depth"])
def test_failed_control_keeps_same_paragraph_and_successful_sibling(monkeypatch, failure):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_SECTION_CELLS", 4)
    paragraph = _hwp_text_paragraph("keep text")
    first = _hwp_table_control_node(1, 1, [])
    if failure == "cells":
        broken = _hwp_table_control_node(1, 3, [])
    else:
        broken = _hwp_table_control_node(1, 1, [])
        broken["children"].append(_hwp_cell_with_paragraph(
            {"record": RawRecord(HWPTAG_PARA_HEADER, 2, 0, b""),
             "children": [_hwp_table_control_node(1, 1, [])]}
        ))
        monkeypatch.setattr(parser, "MAX_TABLE_DEPTH", 2)
    last = _hwp_table_control_node(1, 1, [])
    paragraph["children"].extend([first, broken, last])
    outer = _hwp_table_control_node(1, 1, [])
    outer["children"].append(_hwp_cell_with_paragraph(paragraph))

    table = parser._parse_table(outer)
    blocks = table.rows[0][0].paragraphs
    assert blocks[0].text == "keep text"
    # 깊이 위반에서는 안전한 바깥 표를 남기고 안쪽 컨트롤만 버린다.
    assert len([block for block in blocks if isinstance(block, Table)]) == (2 if failure == "cells" else 3)
    assert parser._section_cells == parser._document_cells == (3 if failure == "cells" else 4)
    assert len(parser.errors) == 1


@pytest.mark.parametrize("doc_info", [None, DocInfo()])
def test_unknown_char_shapes_produce_one_plain_run(doc_info):
    from test_hwp_para_char_shape import _paragraph, _text, _pairs
    para = _paragraph(_text("abcdef"), _pairs((0, 1), (2, 2), (4, 3)), doc_info)
    assert [run.text for run in para.runs] == ["abcdef"]
