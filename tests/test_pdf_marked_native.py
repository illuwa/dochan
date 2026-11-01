"""Native marked-content state consumes structural operators without yielding."""
import random
import struct

import pytest

from dochan.pdf import content
from dochan.pdf._show_table import font_table

native = pytest.importorskip('dochan.pdf._cinterp')


def engine_for(data, owner=None):
    owner = owner or content.ContentTextExtractor.from_fonts({})
    owner._extract_page_python(b'')
    warnings = []
    engine = native.Interpreter(data, {}, (1, 0, 0, 1, 0, 0),
                                (None, 0., 0., 0., 1., 0., 0, 1.),
                                [], [], warnings, owner, [], content.Fragment, font_table, True)
    return engine, owner, warnings


def test_native_marked_no_python_round_trip():
    engine, owner, warnings = engine_for(
        b'/Artifact << /MCID 7 >> BDC /Span << /MCID 7 >> BDC EMC EMC /GS gs')
    owner.resources = {'ExtGState': {'GS': {'LW': 2.75}}}
    assert engine.next() is None
    assert engine.marked_ids == {7}
    assert engine.duplicate_marked_ids == {7}
    assert owner._marked_stack == []
    assert owner._marked_overflow == 0
    assert engine.stroke_width == 2.75
    assert warnings == []


@pytest.mark.parametrize('width', [True, False, 0, -0.0, 4, 2.75, -1, float('inf'), float('nan'), None])
def test_native_graphics_width(width):
    engine, owner, _ = engine_for(b'/GS gs')
    owner.resources = {'ExtGState': {'GS': {'LW': width}}}
    expected = owner._graphics_width(['GS'], 1.)
    assert engine.next() is None
    assert struct.pack('!d', engine.stroke_width) == struct.pack('!d', expected)


def test_native_marked_differential_random_streams():
    rng = random.Random(919)
    choices = [b'/Artifact BMC', b'/Span BMC', b'EMC', b'/Span /P BDC',
               b'/Span << /MCID -1 >> BDC', b'/Span << /MCID true >> BDC',
               b'/Span << /MCID 7 >> BDC', b'/Artifact << /MCID 7 >> BDC']
    for _ in range(200):
        data = b' '.join(rng.choices(choices, k=100))
        expected = content.ContentTextExtractor.from_fonts({})
        expected.properties = {'P': {'MCID': 23}}
        page = expected._extract_page_python(data)
        engine, owner, warnings = engine_for(data)
        owner.properties = expected.properties
        assert engine.next() is None
        assert engine.marked_ids == page.marked_ids
        assert engine.duplicate_marked_ids == page.duplicate_marked_ids
        assert warnings == page.warnings
        assert owner._marked_stack == expected._marked_stack
        assert owner._marked_overflow == expected._marked_overflow


def test_native_marked_overflow_unwind():
    data = b'/Artifact << /MCID 1 >> BDC ' * 66 + b'EMC ' * 66
    engine, owner, warnings = engine_for(data)
    assert engine.next() is None
    assert engine.marked_ids == {1}
    assert engine.duplicate_marked_ids == {1}
    assert len(warnings) == 1
    assert owner._marked_stack == []
    assert owner._marked_overflow == 0


def test_native_graphics_resolver_exception_and_call_order():
    engine, owner, _ = engine_for(b'/GS gs')
    states = {'GS': {'LW': 3}}
    owner.resources = {'ExtGState': states}
    calls = []

    def resolve(value):
        calls.append(value)
        if len(calls) == 3:
            raise ValueError('bad resource')
        return value

    owner.resolve_resource = resolve
    assert engine.next() is None
    assert calls == [states, states['GS'], 3]
    assert engine.stroke_width == 1.


def test_native_graphics_resolver_base_exception_propagates():
    engine, owner, _ = engine_for(b'/GS gs')
    owner.resources = {'ExtGState': {}}

    def resolve(value):
        raise KeyboardInterrupt

    owner.resolve_resource = resolve
    with pytest.raises(KeyboardInterrupt):
        engine.next()


def test_native_graphics_width_float_subclass():
    class Width(float):
        def __float__(self):
            return 4.25

    engine, owner, _ = engine_for(b'/GS gs')
    owner.resources = {'ExtGState': {'GS': {'LW': Width(2.5)}}}
    assert engine.next() is None
    assert engine.stroke_width == owner._graphics_width(['GS'], 1.)


def test_native_marked_large_identifier_and_invalid_types():
    engine, owner, _ = engine_for(b'/Span /P BDC EMC /Artifact /Q BDC')
    owner.properties = {'P': {'MCID': 1 << 100}, 'Q': {'MCID': False}}
    assert engine.next() is None
    assert engine.marked_ids == {1 << 100}
    assert owner._marked_stack == [(None, True)]


@pytest.mark.parametrize('method', ['_begin_marked', '_end_marked', '_graphics_width'])
def test_overridden_marked_callbacks_are_not_bypassed(monkeypatch, method):
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    monkeypatch.setattr(content, '_CInterpreterBailout', native.Bailout)
    owner = content.ContentTextExtractor.from_fonts({})
    original = getattr(owner, method)
    calls = []

    def replacement(*args):
        calls.append(args)
        return original(*args)

    setattr(owner, method, replacement)
    owner.extract_page(b'/Span << /MCID 7 >> BDC EMC /GS gs')
    assert len(calls) == 1
