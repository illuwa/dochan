"""Nested LIST_HEADER repair must visit children moved during compaction."""
from dochan.hwp.section import RawRecord, SectionParser


def _node(tag, offset, children=None):
    return {"record": RawRecord(tag, 0, 0, b"", offset), "children": children or []}


def test_moved_list_header_children_receive_nested_repair():
    inner_list = _node(72, 3)
    inner_para = _node(66, 4, [_node(67, 5)])
    outer_para = _node(66, 2, [inner_list, inner_para])
    outer_list = _node(72, 1)
    next_list = _node(72, 6)
    nodes = [outer_list, outer_para, next_list]
    parser = SectionParser()
    parser._fix_empty_list_headers(nodes)
    assert nodes == [outer_list, next_list]
    assert outer_list["children"] == [outer_para]
    assert outer_para["children"] == [inner_list]
    assert inner_list["children"] == [inner_para]
    assert inner_para["children"][0]["record"].offset == 5
    assert not parser.errors


def test_moved_children_obey_structure_depth_limit():
    inner_list = _node(72, 3)
    inner_para = _node(66, 4)
    outer_para = _node(66, 2, [inner_list, inner_para])
    nodes = [_node(72, 1), outer_para]
    parser = SectionParser()
    parser.MAX_STRUCTURE_DEPTH = 1
    parser._fix_empty_list_headers(nodes)
    assert outer_para["children"] == [inner_list, inner_para]
    assert parser.errors == ["ERR: HWP structure depth exceeds limit: 2 > 1"]
