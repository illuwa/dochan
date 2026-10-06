"""Bit- and type-exact differential checks for handwritten line assembly."""
from dataclasses import replace
import gc
import math
import random
import statistics
import struct
import sys

import pytest

from dochan.pdf import content

clines = pytest.importorskip("dochan.pdf._clines")

LINE_FIELDS = (
    "fragment_orders", "order", "direction", "along_start", "along_end", "across",
    "left", "right", "y", "size", "first_size", "last_size", "segments", "runs",
    "trailing_space", "text",
)
SEGMENT_FIELDS = ("x0", "x1", "text", "space_width", "runs")


def _signature(value):
    identity = type(value)
    if isinstance(value, float):
        return identity, struct.pack("!d", value)
    if isinstance(value, (list, tuple)):
        return identity, tuple(_signature(item) for item in value)
    if isinstance(value, content._Segment):
        return identity, tuple(_signature(getattr(value, key)) for key in SEGMENT_FIELDS), repr(value)
    if isinstance(value, content._Line):
        return identity, tuple(_signature(getattr(value, key)) for key in LINE_FIELDS)
    return identity, value


def _pure(frags):
    backend = content._c_assemble_lines
    try:
        content._c_assemble_lines = None
        return content.assemble_lines(frags)
    finally:
        content._c_assemble_lines = backend


def _native(frags, line_class=content._Line):
    return clines.assemble_lines(frags, line_class, content._Segment,
                                 content.Fragment, content._LINE_Y_TOLERANCE)


def _compare(frags):
    expected = _pure(frags)
    actual = _native(frags)
    if actual is None:
        # The production wrapper must redo the entire unsupported call.
        backend = content._c_assemble_lines
        try:
            content._c_assemble_lines = clines.assemble_lines
            actual = content.assemble_lines(frags)
        finally:
            content._c_assemble_lines = backend
    assert _signature(actual) == _signature(expected), frags
    return actual


def _f(text="x", x=0.0, y=0.0, **fields):
    values = dict(x=x, y=y, width=10.0, size=10.0, text=text, space_width=4.0)
    values.update(fields)
    return content.Fragment(**values)


def _hangul(gaps):
    x = 0.0
    fragments = [_f("가", x=x)]
    for index, gap in enumerate(gaps, start=1):
        x = x + 10.0 + gap
        fragments.append(_f(chr(ord("가") + index), x=x, order=index))
    return fragments


BOUNDARIES = [
    [], [_f()], [_f("", width=0.0)],
    [_f("one", order=9), _f("two", x=10.0, order=-2)],
    [_f("a"), _f("b", y=5.0)],
    [_f("a"), _f("b", y=math.nextafter(5.0, math.inf))],
    [_f("a", size=1.0), _f("b", y=3.0)],
    [_f("a", size=1.0), _f("b", y=math.nextafter(3.0, math.inf))],
    [_f("a", size=2.0), _f("b", x=10.0, size=24.0), _f("c", y=12.0)],
    [_f("a", size=24.0), _f("b", y=13.0, size=2.0), _f("c", y=16.1)],
    _hangul([0.2] * 5), _hangul([0.2] * 6),
    _hangul([0.1] * 7 + [1.8] * 7 + [3.0] + [0.3] * 7),
    [_f("가", x=float(index // 2) * 10.0, order=index) for index in range(10)],
    [_f("a "), _f("b", x=50.0)],
    [_f("a"), _f("b ", x=10.0, invisible=True)],
    [_f("a ", invisible=True)], [_f(" \t\u00a0\u3000")],
    [_f("a\u00a0"), _f("b\u3000", x=50.0)],
    [_f("\t a"), _f("b\t", x=12.0)],
    [_f("a"), _f("b", x=12.0)],
    [_f("a"), _f("b", x=math.nextafter(12.0, math.inf))],
    [_f("a"), _f("b", x=12.0, bold=True), _f("c", x=22.0, italic=True)],
    [_f("link", link_spans=[(0, 4, "https://example.invalid/")])],
    [_f("partial", link_spans=[(1, 3, "a"), (4, 7, "b")])],
    [_f("note", note_ref=3)],
    [_f("linked note", note_ref=2, link_spans=[(0, 11, "a")])],
    [_f("comment", comment_markers=[(0, 1), (3, 2), (7, 3)])],
    [_f("mixed", note_ref=1, comment_markers=[(2, 3)])],
    [_f("before", link_spans=[(0, 6, "a")]),
     _f("after", x=50.0, link_spans=[(0, 5, "a")])],
    [_f("first", x=-0.0, y=-0.0, width=-0.0, size=-0.0, space_width=-0.0),
     _f("second", x=0.0, y=0.0, width=0.0, size=0.0, space_width=0.0)],
    [_f("second", x=0.0, order=3), _f("first", x=-0.0, order=1)],
    [_f("a", bold=1), _f("b", x=10.0, italic=0)],
    [_f("huge", x=1e308, width=1e308), _f("tiny", x=-1e308)],
    [_f("negative", width=-10.0, space_width=-4.0, size=-10.0)],
]


@pytest.mark.parametrize("fragments", BOUNDARIES)
def test_handpicked_boundaries(fragments):
    _compare(fragments)


@pytest.mark.parametrize("direction", [(1.0, 0.0), (-1.0, 0.0), (0.0, -1.0), (0.0, 1.0),
                                      (1.0, 1.0), (-1.0, -1.0), (-0.0, -0.0)])
def test_directions_and_stable_ties(direction):
    dx, dy = direction
    frags = [_f(text, x=x, y=y, dir_x=dx, dir_y=dy, order=index)
             for index, (text, x, y) in enumerate([
                 ("third", 10.0, 10.0), ("first", -0.0, -0.0),
                 ("second", 0.0, 0.0), ("fourth", 20.0, 20.0)])]
    _compare(frags)


def test_direction_changes_split_rows():
    directions = [(1.0, 0.0), (-1.0, 0.0), (0.0, -1.0), (0.0, 1.0)]
    lines = _compare([_f(chr(97 + index), dir_x=dx, dir_y=dy)
                      for index, (dx, dy) in enumerate(directions)])
    assert [line.direction for line in lines] == ["ltr", "rtl", "down", "up"]


@pytest.mark.parametrize("field", ["x", "y", "width", "size", "space_width", "dir_x", "dir_y"])
def test_integer_numeric_fields_delegate_and_keep_types(field):
    _compare([_f("a"), replace(_f("b", x=10.0), **{field: 0})])


@pytest.mark.parametrize("field", ["x", "y", "width", "size", "space_width", "dir_x", "dir_y"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_fields_delegate_entire_call(field, value):
    fragments = [_f("a"), replace(_f("b", x=10.0), **{field: value})]
    assert _native(fragments) is None
    _compare(fragments)


@pytest.mark.parametrize("gaps", [
    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    [0.2, 1.1, 0.2, 0.3, 3.8, 0.2, 0.1, 0.5, 0.4],
])
def test_median_window_exact_bits(gaps):
    frags = _hangul(gaps)
    observed = [content.along(right) - content.along(left) - left.width
                for left, right in zip(frags, frags[1:])]
    expected = []
    parities = set()
    for index in range(len(observed)):
        nearby = [value for at, value in enumerate(observed)
                  if abs(at - index) <= 4 and at != index]
        parities.add(len(nearby) % 2)
        ordered = sorted(nearby)
        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        assert struct.pack("!d", median) == struct.pack("!d", statistics.median(nearby))
        expected.append(median)
    assert parities == {0, 1}
    assert _signature(content._Line._hangul_tracking_gaps(frags)) == _signature(expected)
    _compare(frags)


@pytest.mark.parametrize("steps", [
    [1, 2, 1, 2, 3, 1, 3], [0, 1, 2, 0, 3, 2, 1, 0],
    [2, 1, 0, 2, 1, 3, 1, 2, 0],
])
def test_subnormal_median_rounding_changes_inferred_spaces(steps):
    # With tiny glyphs size * .15 rounds to zero, making median rounding
    # directly visible in inferred separators. Absolute spacing stays disabled.
    unit = math.nextafter(0.0, 1.0)
    x = 0.0
    fragments = [_f("가", width=unit, size=unit, space_width=1.0)]
    for index, step in enumerate(steps, start=1):
        x = x + unit + step * unit
        fragments.append(_f(chr(ord("가") + index), x=x, width=unit,
                            size=unit, space_width=1.0))
    references = content._Line._hangul_tracking_gaps(fragments)
    expected = [fragments[0].text]
    for index in range(1, len(fragments)):
        gap = fragments[index].x - (fragments[index - 1].x + unit)
        if gap > references[index - 1]:
            expected.append(" ")
        expected.append(fragments[index].text)
    lines = _compare(fragments)
    assert lines[0].text == "".join(expected)


def test_hangul_comparability_boundaries():
    for field, values in [("size", [10.2, math.nextafter(10.2, math.inf)]),
                          ("width", [10.2, math.nextafter(10.2, math.inf)])]:
        for value in values:
            frags = _hangul([0.1] * 12)
            frags[6] = replace(frags[6], **{field: value})
            _compare(frags)


def test_subclass_fields_preserve_python_types():
    class Text(str):
        pass

    class Number(float):
        pass

    for fragment in [_f(Text("text")), _f(x=Number(-0.0)),
                     _f(size=Number(10.0)), _f(order=2**100), _f(order=-2**100)]:
        _compare([fragment, _f("ordinary", x=20.0)])


def test_tolerance_is_supplied_by_content(monkeypatch):
    monkeypatch.setattr(content, "_LINE_Y_TOLERANCE", 7.5)
    lines = _compare([_f("a", size=1.0), _f("b", y=7.5, size=1.0),
                      _f("c", y=math.nextafter(7.5, math.inf), size=1.0)])
    assert [line.text for line in lines] == ["ab", "c"]


def test_order_comparison_can_mutate_input_list():
    fragments = []

    class ClearingOrder(int):
        def __lt__(self, other):
            fragments.clear()
            gc.collect()
            return super().__lt__(other)

    fragments.extend([_f("first", order=4), _f("second", x=10.0, order=ClearingOrder(1))])
    retained = list(fragments)
    actual = _native(fragments)
    if actual is None:
        actual = _pure(fragments)
    assert actual is not None
    assert fragments == []
    assert _signature(actual[0]) == _signature(content._Line(retained))


def test_fallback_factory_can_mutate_input_after_grouping():
    fragments = [_f("linked", link_spans=[(0, 6, "a")]), _f("next", y=50.0)]
    retained = list(fragments)

    class ClearingLine(content._Line):
        def __init__(self, row):
            fragments.clear()
            gc.collect()
            super().__init__(row)

    actual = _native(fragments, line_class=ClearingLine)
    assert actual is not None
    assert fragments == []
    assert len(actual) == 2
    for line, fragment in zip(actual, retained):
        expected = content._Line([fragment])
        for field in LINE_FIELDS:
            assert _signature(getattr(line, field)) == _signature(getattr(expected, field))


def test_ordinary_rows_skip_init_but_special_rows_call_it():
    calls = []

    class TrackedLine(content._Line):
        def __init__(self, row):
            calls.append(row)
            super().__init__(row)

    first = [_f("ordinary"), _f("row", x=10.0)]
    special = [_f("linked", y=50.0, link_spans=[(0, 6, "a")]), _f("int", x=10, y=50.0)]
    actual = _native(first + special, line_class=TrackedLine)
    assert actual is not None
    assert len(actual) == 2
    assert calls == [special]
    for line, row in zip(actual, [first, special]):
        expected = content._Line(row)
        for field in LINE_FIELDS:
            assert _signature(getattr(line, field)) == _signature(getattr(expected, field))


def test_seeded_twenty_thousand_fragment_lists():
    rng = random.Random(20261006)
    texts = ["", "a", "b ", "\t", "\u00a0", "a\u3000", "가", "각", "나", "한글", "🙂"]
    directions = [(1.0, 0.0), (-1.0, 0.0), (0.0, -1.0), (0.0, 1.0), (1.0, 1.0)]
    for case in range(20000):
        size = rng.choice([0.0, 1.0, 8.0, 10.0, 12.0, 16.0])
        dx, dy = rng.choice(directions)
        x = rng.choice([-0.0, 0.0, -10.0])
        y = rng.choice([-0.0, 0.0, 100.0])
        fragments = []
        for index in range(rng.randrange(21)):
            if case % 4 == 0:
                text = chr(ord("가") + index % 11)
                width = 10.0
                dx, dy = 1.0, 0.0
            else:
                text = rng.choice(texts)
                width = rng.choice([-0.0, 0.0, 0.1, 10.0, 20.0])
            fragment = _f(text, x=x, y=y, width=width,
                          size=rng.choice([size, size, size, 0.0, 10.2]),
                          space_width=rng.choice([0.0, 2.0, 4.0]),
                          bold=rng.choice([True, False]), italic=rng.choice([True, False]),
                          invisible=rng.choice([True, False]), order=rng.randrange(-3, 8),
                          dir_x=dx, dir_y=dy)
            anomaly = rng.randrange(80) if case % 4 != 0 else -1
            if anomaly == 0:
                fragment.link_spans = [(0, len(text), "target")]
            elif anomaly == 1:
                fragment.note_ref = rng.randrange(1, 5)
            elif anomaly == 2:
                fragment.comment_markers = [(rng.randrange(len(text) + 1), 2)]
            elif anomaly == 3:
                fragment.x = int(fragment.x)
            elif anomaly == 4:
                fragment.size = rng.choice([math.nan, math.inf, -math.inf])
            elif anomaly == 5:
                fragment.bold = 1
            fragments.append(fragment)
            increment = width + rng.choice([-0.1, 0.0, 0.1, 1.8, 2.0, 3.0, 15.0])
            if abs(dx) >= abs(dy):
                x = x + increment if dx >= 0 else x - increment
                if rng.randrange(10) == 0:
                    y += rng.choice([3.0, 5.0, 5.000000000000001, 25.0])
            else:
                y = y + increment if dy >= 0 else y - increment
                if rng.randrange(10) == 0:
                    x += rng.choice([3.0, 5.0, 5.000000000000001, 25.0])
            if case % 4 != 0 and rng.randrange(20) == 0:
                dx, dy = rng.choice(directions)
        try:
            _compare(fragments)
        except AssertionError as exc:
            raise AssertionError("random case %d: %r" % (case, fragments)) from exc


def test_repeated_calls_release_references():
    fragments = _hangul([0.2] * 8)
    fragments += [_f("linked", y=50.0, link_spans=[(0, 6, "a")])]
    objects = [fragments, *fragments, content._Line, content._Segment, content.Fragment]
    gc.collect()
    before = [sys.getrefcount(obj) for obj in objects]
    for _ in range(1000):
        _compare(fragments)
    gc.collect()
    assert [sys.getrefcount(obj) for obj in objects] == before


@pytest.mark.parametrize("failure", ["line_new", "segment_new", "delegated_init"])
def test_failed_factories_release_owned_references(failure):
    class BrokenNewLine(content._Line):
        def __new__(cls):
            raise RuntimeError("line_new")

    class BrokenInitLine(content._Line):
        def __init__(self, fragments):
            raise RuntimeError("delegated_init")

    class BrokenSegment(content._Segment):
        def __new__(cls):
            raise RuntimeError("segment_new")

    fragments = [_f("ordinary"), _f("next", y=50.0)]
    if failure == "delegated_init":
        fragments[-1].note_ref = 1
    line_type = {"line_new": BrokenNewLine, "delegated_init": BrokenInitLine}.get(
        failure, content._Line)
    segment_type = BrokenSegment if failure == "segment_new" else content._Segment
    objects = [fragments, *fragments, line_type, segment_type]
    gc.collect()
    before = [sys.getrefcount(obj) for obj in objects]
    for _ in range(300):
        with pytest.raises(RuntimeError, match=failure):
            clines.assemble_lines(fragments, line_type, segment_type,
                                  content.Fragment, content._LINE_Y_TOLERANCE)
    gc.collect()
    assert [sys.getrefcount(obj) for obj in objects] == before
