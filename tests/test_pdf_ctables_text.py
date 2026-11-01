"""Differential tests for the optional C table text kernels."""
import struct

import pytest

from dochan.pdf import tables
from dochan.pdf.content import Fragment


def native():
    return pytest.importorskip('dochan.pdf._ctables')


def fragment(x=10, y=20, order=0, text='12', **kwargs):
    return Fragment(text=text, x=x, y=y, width=6, size=10, space_width=5, order=order, **kwargs)


def bits(value):
    if isinstance(value, float):
        return type(value), struct.pack('!d', value)
    if isinstance(value, (list, tuple)):
        return type(value), tuple(bits(v) for v in value)
    return value


@pytest.mark.parametrize('direction', [(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (.3, .7)])
def test_reference_and_reading(direction):
    c = native()
    f = fragment(dir_x=direction[0], dir_y=direction[1])
    for name in ('_reference_axes', '_reference_point', '_reading_key'):
        assert bits(getattr(c, name)(f)) == bits(getattr(tables, name)(f))


def test_index_ties_and_cached_lines():
    c = native()
    fs = [fragment(x=x, order=i) for i, x in enumerate([40, 10, 10, 30])]
    actual = c._fragment_index(fs)
    expected = tables._fragment_index(fs)
    assert actual == expected
    assert [id(f) for _, f in actual[0]] == [id(f) for _, f in expected[0]]
    for box in [(0, 0, 80, 80), (10, 0, 25, 80), (0, 0, 0, 0)]:
        assert c._fragments_inside(actual, box) == tables._fragments_inside(expected, box)
        assert c._has_fragment_inside(actual, box) == tables._has_fragment_inside(expected, box)
    cache = {}
    lines = c._cell_lines(fs, cache)
    assert c._cell_lines(fs, cache) is lines
    assert [vars(line) for line in lines] == [vars(line) for line in tables._cell_lines(fs, None)]


def test_numeric_rows_and_assignment():
    c = native()
    xs, ys = [0, 30, 60, 90], [80, 0]
    hs = [(y, 0, 90) for y in ys]
    vs = [(x, 0, 80) for x in xs]
    fs = [fragment(x=x + 5, y=y, order=i * 3 + j)
          for i, y in enumerate([60, 30]) for j, x in enumerate(xs[:-1])]
    args = (hs, vs, xs, ys, fs, 1.5)
    assert c._numeric_row_rules(*args) == tables._numeric_row_rules(*args)
    grid, owners, boxes = tables._make_grid(hs, vs, xs, ys, 1.5, 1)
    args = (grid, owners, boxes, xs, ys, fs, 1)
    assert c._assign_text(*args) == tables._assign_text(*args)
