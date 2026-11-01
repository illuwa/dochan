"""Form clipping reuses only numerically unchanged complete runs."""
from dataclasses import fields, replace
import struct

import pytest

from dochan.pdf.content import Fragment, _clip_form_fragments


def _fragment(**changes):
    return replace(Fragment(10.0, 20.0, 12.0, 8.0, 'abc', 4.0,
                            char_offsets=(0.0, 4.0, 8.0, 12.0)), **changes)


def _clip(fragment):
    return _clip_form_fragments([fragment], (-100, -100, 100, 100),
                                (1, 0, 0, 1, 0, 0))[0]


def _typed(value):
    if isinstance(value, float):
        return type(value), struct.pack('>d', value)
    if isinstance(value, tuple):
        return type(value), tuple(map(_typed, value))
    return type(value), value


def test_unchanged_complete_form_run_reuses_fragment():
    fragment = _fragment()
    assert _clip(fragment) is fragment


@pytest.mark.parametrize('changes', [
    {'x': -0.0}, {'y': -0.0}, {'x': 10}, {'y': 20}, {'width': 12},
    {'char_offsets': (0, 4, 8, 12)},
    {'char_offsets': (-0.0, 4.0, 8.0, 12.0)},
    {'char_offsets': (0.0, -0.0, 8.0, 12.0)},
    {'char_offsets': (1.0, 4.0, 8.0, 12.0)},
    {'width': 13.0}, {'dir_x': -1.0},
])
def test_complete_run_preserves_original_arithmetic_types_and_bits(changes):
    fragment = _fragment(**changes)
    offsets = fragment.char_offsets
    shift = offsets[0]
    expected = replace(fragment, x=fragment.x + fragment.dir_x * shift,
                       y=fragment.y + fragment.dir_y * shift,
                       width=offsets[-1] - shift,
                       char_offsets=tuple(value - shift for value in offsets))
    actual = _clip(fragment)
    assert [_typed(getattr(actual, f.name)) for f in fields(actual)] == [
        _typed(getattr(expected, f.name)) for f in fields(expected)]
