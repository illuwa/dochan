"""Differential contract for optional native heading run sizing."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from dochan.model.document import Paragraph, TextRun
from dochan.pdf import headings


def line(parts, orders=None, size=10):
    return SimpleNamespace(runs=[(''.join(parts), False, False)],
                           fragment_orders=list(range(len(parts))) if orders is None else orders,
                           segments=[SimpleNamespace(runs=[(p, False, False)]) for p in parts],
                           size=size)


def test_python_mirror_exists():
    assert callable(headings._sized_runs_python)


@pytest.mark.parametrize('parts,text,sizes', [
    (['abc', 'def'], 'abcdef', {0: 12, 1: 8.0}),
    (['  abc', 'def  '], 'abcdef', {0: -0.0, 1: 0}),
    (['한글', '\u2003', 'text'], '한글\u2003text', {0: 12.0, 1: 10, 2: 8}),
    (['same', 'same'], 'samesame', {0: 11, 1: 11.0}),
    ([''], '', {}),
])
def test_native_matches_python(parts, text, sizes):
    native = pytest.importorskip('dochan.pdf._cheadings')
    para = Paragraph(runs=[TextRun(text=text, bold=True, link='link', note_ref=1)])
    lines = [line(parts)]
    before = asdict(para)
    actual = native.sized_runs(para, lines, sizes)
    expected = headings._sized_runs_python(para, lines, sizes)
    assert [asdict(r) for r in actual] == [asdict(r) for r in expected]
    assert [(type(r.font_size_pt), r.font_size_pt.hex() if isinstance(r.font_size_pt, float)
             else r.font_size_pt) for r in actual] == [
        (type(r.font_size_pt), r.font_size_pt.hex() if isinstance(r.font_size_pt, float)
         else r.font_size_pt) for r in expected]
    assert asdict(para) == before


def test_native_bad_metadata_returns_original():
    native = pytest.importorskip('dochan.pdf._cheadings')
    para = Paragraph(runs=[TextRun('abc')])
    lines = [line(['xyz'])]
    lines[0].segments[0].runs = [('unmatched', False, False)]
    assert native.sized_runs(para, lines, {}) is para.runs


def test_wrapper_replays_errors_without_context(monkeypatch):
    native = pytest.importorskip('dochan.pdf._cheadings')
    monkeypatch.setattr(headings, '_CHeadingsBailout', native.Bailout)
    def broken(*args):
        raise ValueError('native error')
    monkeypatch.setattr(headings, '_c_sized_runs', broken)
    para = Paragraph(runs=[TextRun('abc')])
    assert headings.sized_runs(para, [line(['abc'])], {}) == headings._sized_runs_python(
        para, [line(['abc'])], {})
    with pytest.raises(AttributeError) as caught:
        headings.sized_runs(None, [], {})
    assert caught.value.__context__ is None


def test_native_nan_and_repeated_line():
    native = pytest.importorskip('dochan.pdf._cheadings')
    nan = float('nan')
    para = Paragraph(runs=[TextRun('ab')])
    one = line(['a', 'b'])
    actual = native.sized_runs(para, [one], {0: nan, 1: nan})
    expected = headings._sized_runs_python(para, [one], {0: nan, 1: nan})
    assert [r.text for r in actual] == [r.text for r in expected]
    shared = line(['a'])
    assert native.sized_runs(para, [shared, shared], {}) == headings._sized_runs_python(
        para, [shared, shared], {})


def test_native_custom_input_bails_without_access():
    native = pytest.importorskip('dochan.pdf._cheadings')
    class Custom:
        @property
        def text(self):
            raise AssertionError('must not access')
    with pytest.raises(native.Bailout):
        native.sized_runs(Custom(), [], {})


def test_native_ignores_unused_custom_size():
    native = pytest.importorskip('dochan.pdf._cheadings')
    para = Paragraph(runs=[TextRun('abc')])
    lines = [line(['abc'])]
    sizes = {0: 12, 100: object()}
    assert native.sized_runs(para, lines, sizes) == headings._sized_runs_python(para, lines, sizes)


def test_native_used_custom_size_bails():
    native = pytest.importorskip('dochan.pdf._cheadings')
    with pytest.raises(native.Bailout):
        native.sized_runs(Paragraph(runs=[TextRun('abc')]), [line(['abc'])], {0: object()})


def test_native_does_not_call_dataclasses_replace():
    import dataclasses
    import sys
    native = pytest.importorskip('dochan.pdf._cheadings')
    para = Paragraph(runs=[TextRun('abc'), TextRun('def', bold=True)])
    calls = []

    def profile(frame, event, arg):
        if event == 'call' and frame.f_code is dataclasses.replace.__code__:
            calls.append(1)

    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        actual = native.sized_runs(para, [line(['abc', 'def'])], {0: 12, 1: 10})
    finally:
        sys.setprofile(previous)
    assert actual == headings._sized_runs_python(para, [line(['abc', 'def'])], {0: 12, 1: 10})
    assert calls == []


def test_native_preserves_every_declared_run_field():
    from dataclasses import fields
    native = pytest.importorskip('dochan.pdf._cheadings')
    values = dict(char_shape_id=7, bold=True, italic=True, underline=True,
                  strikeout=True, superscript=True, subscript=True,
                  font_size_pt=-0.0, link='https://example.test', note_ref=9,
                  provenance={'origin': 'public'}, note_reference_type='endnote',
                  note_reference_number=3, equation=None)
    assert set(values) == {field.name for field in fields(TextRun)} - {'text'}
    para = Paragraph(runs=[TextRun('ab', **values), TextRun('cd', **values)])
    args = (para, [line(['a', 'b', 'c', 'd'])], {0: 8, 1: 8.0, 2: -0.0, 3: 12})
    assert native.sized_runs(*args) == headings._sized_runs_python(*args)


def test_native_changed_dataclass_fields_bail(monkeypatch):
    native = pytest.importorskip('dochan.pdf._cheadings')
    fields = dict(TextRun.__dataclass_fields__)
    fields.pop('bold')
    monkeypatch.setattr(TextRun, '__dataclass_fields__', fields)
    with pytest.raises(native.Bailout):
        native.sized_runs(Paragraph(runs=[TextRun('a')]), [line(['a'])], {})


def test_native_constructor_keyword_order_matches_replace(monkeypatch):
    native = pytest.importorskip('dochan.pdf._cheadings')
    para = Paragraph(runs=[TextRun('ab'), TextRun('cd')])
    args = (para, [line(['ab', 'cd'])], {0: 12, 1: 10})
    original = TextRun.__init__
    calls = []

    def init(self, **kwargs):
        calls.append(tuple(kwargs))
        original(self, **kwargs)

    monkeypatch.setattr(TextRun, '__init__', init)
    native.sized_runs(*args)
    actual = list(calls)
    calls.clear()
    headings._sized_runs_python(*args)
    assert actual == calls


def test_native_rejects_custom_schema_without_comparison(monkeypatch):
    native = pytest.importorskip('dochan.pdf._cheadings')
    para = Paragraph(runs=[TextRun('a')])

    class UnknownSchema:
        def __eq__(self, other):
            raise AssertionError('unsupported metadata must not run user code')

    monkeypatch.setattr(TextRun, '__dataclass_fields__', UnknownSchema())
    with pytest.raises(native.Bailout):
        native.sized_runs(para, [line(['a'])], {})
