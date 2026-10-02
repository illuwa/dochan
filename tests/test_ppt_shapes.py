"""Synthetic PPT OfficeArt geometry and table fixtures."""
import struct

from dochan.conversion import Provenance
from dochan.model.document import Paragraph, TextRun
from dochan.office_binary.officeart import parse_records, read_shapes
from dochan.office_binary.ppt_shapes import positioned_shapes, shape_bounds, table_from_shape


def atom(kind, data=b"", version=0, instance=0):
    return struct.pack("<HHI", (instance << 4) | version, kind, len(data)) + data


def shape(spid, bounds, child=False, group=False, table=False, local=None,
          shape_type=1, text=b"", flags=0):
    bits = flags | (2 if child else 0) | (1 if group else 0)
    data = atom(0xF00A, struct.pack("<II", spid, bits), instance=shape_type)
    if bounds is not None:
        l, t, r, b = bounds
        data += (atom(0xF00F, struct.pack("<4i", l, t, r, b)) if child
                 else atom(0xF010, struct.pack("<4h", t, l, r, b)))
    if local is not None:
        data += atom(0xF009, struct.pack("<4i", *local))
    if table:
        data += atom(0xF122, struct.pack("<HI", 0x39F, 1), version=3, instance=1)
    if text:
        data += atom(0xF00D, text)
    return atom(0xF004, data, version=15)


def group(header, *children):
    return atom(0xF003, header + b"".join(children), version=15)


def parse(data):
    return read_shapes(parse_records(data))


def test_ppt_client_and_child_anchors_use_distinct_field_orders():
    for child in (False, True):
        s = parse(shape(1, (-20, 30, 120, 180), child=child))[0]
        assert shape_bounds(s) == (-20, 30, 120, 180)


def test_ppt_group_coordinates_transform_before_reading_order():
    data = shape(10, (0, 200, 100, 300)) + group(
        shape(20, (50, 100, 250, 200), group=True, local=(0, 500, 100, 600)),
        shape(21, (25, 500, 50, 550), child=True),
        shape(22, (0, 520, 30, 540), child=True),
    )
    items = positioned_shapes(parse(data))
    assert [(y, x, s.spid) for y, x, _, s in items] == [(100, 100, 21), (120, 50, 22), (200, 0, 10)]


def test_ppt_nested_groups_compose_and_equal_position_preserves_child_order():
    data = group(shape(1, None, group=True, flags=4), group(
        shape(2, (100, 100, 300, 300), group=True, local=(0, 0, 100, 100)),
        group(shape(3, (10, 20, 60, 70), child=True, group=True, local=(100, 200, 200, 300)),
              shape(4, (120, 220, 140, 240), child=True),
              shape(5, (120, 220, 140, 240), child=True)),
    ))
    items = positioned_shapes(parse(data))
    assert [(y, x, s.spid) for y, x, _, s in items] == [(160, 140, 4), (160, 140, 5)]


def test_ppt_flipped_group_transforms_child_rectangles():
    s = parse(group(shape(1, (100, 200, 300, 400), group=True,
                          local=(0, 0, 100, 100), flags=0xC0),
                    shape(2, (0, 0, 25, 25), child=True),
                    shape(3, (75, 75, 100, 100), child=True)))
    assert [(y, x, leaf.spid) for y, x, _, leaf in positioned_shapes(s)] == [(200, 100, 3), (350, 250, 2)]


def test_ppt_table_grid_and_merges_preserve_nested_paragraphs_and_provenance():
    data = group(shape(1, (0, 0, 200, 300), group=True, table=True),
                 shape(2, (0, 0, 200, 100), child=True),
                 shape(3, (0, 100, 100, 300), child=True),
                 shape(4, (100, 100, 200, 200), child=True),
                 shape(5, (100, 200, 200, 300), child=True),
                 shape(6, (0, 0, 200, 0), child=True, shape_type=20))
    s = parse(data)[0]
    assert [item[3].spid for item in positioned_shapes([s])] == [1]
    prov = Provenance(source_format="ppt", slide=2, path="slide2")
    table = table_from_shape(s, lambda cell: [Paragraph([TextRun(str(cell.spid))]), Paragraph([TextRun("nested")])], prov)
    assert (table.row_count, table.col_count) == (3, 2)
    assert table.rows[0][0].col_span == 2
    assert table.rows[0][1].is_merged_away
    assert table.rows[1][0].row_span == 2
    assert table.rows[2][0].is_merged_away
    assert table.rows[2][1].text == "5\nnested"
    assert table.rows[2][1].provenance.cell == "R3C2"
    assert table.rows[2][1].provenance.slide == 2


def test_ppt_ordinary_groups_are_not_tables_and_overlapping_cells_warn():
    ordinary = parse(group(shape(1, None, group=True), shape(2, (0, 0, 10, 10), child=True)))[0]
    assert table_from_shape(ordinary, lambda cell: [], None) is None
    invalid = parse(group(shape(1, None, group=True, table=True),
                          shape(2, (0, 0, 20, 20), child=True),
                          shape(3, (10, 0, 30, 20), child=True)))[0]
    errors = []
    assert table_from_shape(invalid, lambda cell: [], None, errors) is None
    assert any("overlap" in error for error in errors)


def test_ppt_group_cycle_is_bounded():
    s = parse(group(shape(1, None, group=True), shape(2, (0, 0, 10, 10), child=True)))[0]
    s.children.append(s)
    errors = []
    assert len(positioned_shapes([s], errors)) == 1
    assert errors


def test_ppt_table_grid_size_is_bounded_before_allocation():
    s = parse(group(shape(1, None, group=True, table=True), *[
        shape(i + 2, (i * 2, i * 2, i * 2 + 1, i * 2 + 1), child=True)
        for i in range(200)
    ]))[0]
    errors = []
    assert table_from_shape(s, lambda cell: [], None, errors) is None
    assert any("limit" in error for error in errors)


def test_ppt_table_respects_remaining_document_cell_budget_before_rendering():
    s = parse(group(shape(1, None, group=True, table=True),
                    shape(2, (0, 0, 20, 10), child=True),
                    shape(3, (0, 10, 10, 20), child=True),
                    shape(4, (10, 10, 20, 20), child=True)))[0]
    called = []
    errors = []
    assert table_from_shape(s, lambda cell: called.append(cell) or [], None,
                            errors, max_cells=3) is None
    assert called == []
    assert any("limit" in error for error in errors)
    table = table_from_shape(s, lambda cell: [], None, max_cells=4)
    assert (table.row_count, table.col_count) == (2, 2)


def test_ppt_table_reserves_shared_budget_before_nested_callback():
    s = parse(group(shape(1, None, group=True, table=True),
                    shape(2, (0, 0, 20, 10), child=True),
                    shape(3, (0, 10, 10, 20), child=True),
                    shape(4, (10, 10, 20, 20), child=True)))[0]
    budget = [6]
    nested = []

    def render(cell):
        nested.append(table_from_shape(s, lambda inner: [], None, cell_budget=budget))
        return []

    outer = table_from_shape(s, render, None, cell_budget=budget)
    assert (outer.row_count, outer.col_count) == (2, 2)
    assert nested == [None, None, None]
    assert budget == [2]


def test_empty_groups_consume_shared_document_traversal_budget():
    groups = parse(b"".join(group(shape(i, None, group=True)) for i in range(3)))
    errors = []
    budget = [4]
    assert positioned_shapes(groups, errors, shape_budget=budget) == []
    assert budget == [1]
    assert positioned_shapes(groups, errors, shape_budget=budget) == []
    assert budget == [0]
    assert any("shape traversal budget" in error for error in errors)


def test_group_budget_stops_before_visiting_later_leaves():
    groups = parse(group(shape(1, None, group=True),
                         group(shape(2, None, group=True)),
                         shape(3, (0, 0, 10, 10))))
    errors = []
    budget = [2]
    assert positioned_shapes(groups, errors, shape_budget=budget) == []
    assert budget == [0]
    assert any("shape traversal budget" in error for error in errors)
