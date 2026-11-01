"""The read-only note preflight retains the original Python contract."""
import copy

import pytest

from dochan.pdf import notes
from dochan.pdf.content import Fragment
from dochan.pdf.paths import Segment


def sample():
    return [Fragment(40, 500, 24, 12, 'Body', 4, order=0),
            Fragment(64, 502.5, 9, 9, '1)', 3, order=1),
            Fragment(40, 100, 47.25, 10.5, '1) Detail', 3.5, order=2)]


def test_prepare_note_mirror_exists():
    assert callable(notes._prepare_notes_python)


@pytest.mark.parametrize('horizontal', [False, True])
def test_prepare_note_c_matches(horizontal):
    c = pytest.importorskip('dochan.pdf._cnotes')
    fragments = sample()
    supplied = fragments if horizontal else None
    assert c.prepare(fragments, (0, 800), supplied, Fragment) == notes._prepare_notes_python(
        fragments, (0, 800), supplied)


def test_prepare_note_exception_replayed_outside_handler(monkeypatch):
    class Backend:
        @staticmethod
        def prepare(*args):
            raise RuntimeError('injected')
    monkeypatch.setattr(notes, '_cnotes', Backend)
    fragments = sample()
    fragments[0].size = object()
    with pytest.raises(TypeError) as caught:
        notes.detect_notes(fragments, [], (0, 800), 1)
    assert caught.value.__context__ is None


def test_notes_backend_preserves_output_and_input(monkeypatch):
    c = pytest.importorskip('dochan.pdf._cnotes')
    original = sample()
    accelerated = copy.deepcopy(original)
    segments = [Segment(40, 115, 180, 115)]
    monkeypatch.setattr(notes, '_cnotes', None)
    expected = notes.detect_notes(original, segments, (0, 800), 3)
    monkeypatch.setattr(notes, '_cnotes', c)
    actual = notes.detect_notes(accelerated, segments, (0, 800), 3)
    assert actual == expected
    assert accelerated == original


def test_prepare_custom_number_bails_out():
    c = pytest.importorskip('dochan.pdf._cnotes')
    class Number(float):
        pass
    fragments = sample()
    fragments[0].size = Number(12)
    with pytest.raises(c.Bailout):
        c.prepare(fragments, (0, 800), None, Fragment)


def test_endnote_geometry_c_matches_python(monkeypatch):
    c = pytest.importorskip('dochan.pdf._cnotes')
    fragments = sample()
    warnings = []
    expected = notes._endnote_references_python(
        fragments, warnings, _horizontal=fragments)
    assert c.endnotes(fragments, Fragment, notes._ENDNOTE_MARKER, 200000, 1000) == (expected, 0)
    monkeypatch.setattr(notes, '_cnotes', c)
    assert notes.endnote_references(fragments, _horizontal=fragments) == expected


@pytest.mark.parametrize('budget,maximum', [(0, 1000), (200000, 0)])
def test_endnote_geometry_preserves_warning(monkeypatch, budget, maximum):
    c = pytest.importorskip('dochan.pdf._cnotes')
    monkeypatch.setattr(notes, 'MAX_NOTE_GEOMETRY_CHECKS', budget)
    monkeypatch.setattr(notes, 'MAX_NOTE_MARKERS', maximum)
    fragments = sample()
    expected_warnings, actual_warnings = [], []
    expected = notes._endnote_references_python(
        fragments, expected_warnings, _horizontal=fragments)
    monkeypatch.setattr(notes, '_cnotes', c)
    actual = notes.endnote_references(fragments, actual_warnings, _horizontal=fragments)
    assert actual == expected
    assert actual_warnings == expected_warnings


def test_nonfinite_bounds_do_not_hide_original_fragment_error():
    pytest.importorskip('dochan.pdf._cnotes')
    fragments = sample()
    fragments[0].x = object()
    with pytest.raises(TypeError):
        notes.detect_notes(fragments, [], (float('nan'), 800), 1)


def test_direct_endnotes_rejects_callback_pattern():
    c = pytest.importorskip('dochan.pdf._cnotes')
    class Pattern:
        def fullmatch(self, text):
            raise AssertionError('must not invoke user code')
    with pytest.raises(c.Bailout):
        c.endnotes(sample(), Fragment, Pattern(), 200000, 1000)


def test_prepare_observes_replaced_horizontal_classifier(monkeypatch):
    pytest.importorskip('dochan.pdf._cnotes')
    monkeypatch.setattr(notes, 'horizontal_note_fragments', lambda _: [])
    assert notes.detect_notes(sample(), [], (0, 800), 1) == ([], set(), {}, 1)


def test_prepare_observes_replaced_finite_predicate(monkeypatch):
    pytest.importorskip('dochan.pdf._cnotes')
    seen = []
    def finite(fragment):
        seen.append(fragment)
        return False
    monkeypatch.setattr(notes, '_finite_fragment', finite)
    fragments = sample()
    assert notes.detect_notes(fragments, [], (0, 800), 1) == ([], set(), {}, 1)
    assert seen == fragments[:1]


def test_endnotes_observes_replaced_budget_callback(monkeypatch):
    pytest.importorskip('dochan.pdf._cnotes')
    seen = []
    def spend(*args):
        seen.append(args)
        return False
    monkeypatch.setattr(notes, '_spend', spend)
    fragments = sample()
    assert notes.endnote_references(fragments, _horizontal=fragments) == []
    assert seen
