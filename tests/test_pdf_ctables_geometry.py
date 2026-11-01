"""Differential contracts for the table geometry accelerator."""
import random

import pytest

from dochan.pdf import tables
from dochan.pdf.paths import Segment


def native():
    return pytest.importorskip('dochan.pdf._ctables')


@pytest.mark.parametrize('name,args', [
    ('_snap_runs', ([(0, 0, 4), (0.2, 4, 8), (2, 0, 3)], 0.5)),
    ('_components', ([(0, 0, 4), (4, 0, 4)], [(0, 0, 4), (4, 0, 4)], 0.5)),
    ('_covered', ([(0, 4), (3, 6)], 0, 10, 0.5)),
    ('_rectangles', ([0, 1, 3], 3)),
    ('_shared_extent', ([0, 2, 2.1, 5], 0.2, False)),
    ('_inside', ((0, 0, 1, 1), (0, 0, 2, 2))),
])
def test_geometry_mirror(name, args):
    assert getattr(native(), name)(*args) == getattr(tables, name)(*args)


def test_grid_mirror():
    args = ([(0, 0, 40), (20, 0, 40), (40, 0, 40)],
            [(0, 0, 40), (20, 20, 40), (40, 0, 40)],
            [0, 20, 40], [40, 20, 0], 1.5, 3)
    assert native()._make_grid(*args) == tables._make_grid(*args)


def test_geometry_random_components_and_snap():
    rng = random.Random(621)
    for _ in range(300):
        hs = [(rng.randrange(15), rng.randrange(10), rng.randrange(10, 20))
              for _ in range(rng.randrange(25))]
        vs = [(rng.randrange(15), rng.randrange(10), rng.randrange(10, 20))
              for _ in range(rng.randrange(25))]
        hs = tables._snap_runs(hs, 1.5)
        vs = tables._snap_runs(vs, 1.5)
        assert native()._snap_runs(hs, 1.5) == tables._snap_runs(hs, 1.5)
        assert native()._components(hs, vs, 1.5) == tables._components(hs, vs, 1.5)


def test_dash_rules_and_extents():
    segments = [Segment(i, 4, i + .2, 4) for i in (0, .5, 1, 1.5)]
    assert native()._short_dash_runs(segments, 1.5) == tables._short_dash_runs(segments, 1.5)
    hs = [(0, -20, 40), (20, -20, 40)]
    a, b = [0, 20], [0, 20]
    assert native()._extend_to_rule_extents(a, hs, 1.5) is None
    tables._extend_to_rule_extents(b, hs, 1.5)
    assert a == b


def test_reverse_extent_stable_ties_and_dash_types():
    import math
    from collections import defaultdict
    values = [0, -0.0, 0.0, 0]
    result = native()._shared_extent(values, 1, True)
    assert type(result) is int
    result = native()._shared_extent([-0.0, 0.0], 1, True)
    assert math.copysign(1, result) == -1
    dashes = native()._short_dash_runs([], 1.5)
    assert type(dashes['h']) is defaultdict
    assert dashes['h'].default_factory is list
    assert type(dashes['v']) is defaultdict


def test_owner_regions_match():
    from types import SimpleNamespace
    xs, ys = [0, 10, 20], [20, 10, 0]
    hs = [(0, 0, 20), (10, 0, 20), (20, 0, 20)]
    vs = [(0, 0, 20), (10, 0, 20), (20, 0, 20)]
    _, owners, boxes = tables._make_grid(hs, vs, xs, ys, 1.5, None)
    parent = SimpleNamespace(xs=xs, ys=ys, owners=owners, boxes=boxes)
    for bbox in [(1, 1, 9, 9), (0, 0, 10, 10), (0, 0, 20, 20), (-1, 1, 9, 9)]:
        assert native()._owner_region(bbox, parent) == tables._owner_region(bbox, parent)


def test_grid_cell_paragraph_lists_are_independent():
    xs, ys = [0, 10, 20], [20, 10, 0]
    hs = [(y, 0, 20) for y in ys]
    vs = [(x, 0, 20) for x in xs]
    grid, _, _ = native()._make_grid(hs, vs, xs, ys, 1.5, 3)
    cells = [cell for row in grid for cell in row]
    assert len({id(cell.paragraphs) for cell in cells}) == len(cells)
    assert all(cell.paragraphs == [] for cell in cells)
    assert all(cell.provenance is cells[0].provenance for cell in cells)
    cells[0].paragraphs.append(object())
    assert all(cell.paragraphs == [] for cell in cells[1:])
