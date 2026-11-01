"""Body event partitioning preserves order, anchor mutation and replay."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from dochan.pdf import reader
from dochan.pdf.content import Fragment
from dochan.pdf.tables import TableCandidate


def fragment(order, y=50, size=10):
    return Fragment(text=str(order), x=10, y=y, size=size, width=5, space_width=3, order=order)


def test_python_mirror_exists():
    assert callable(reader.PDFReader._body_groups_python)


def test_body_matches_python_with_ties_and_empty_groups(monkeypatch):
    def assemble(fs):
        return list(fs)
    monkeypatch.setattr(reader, "assemble_lines", assemble)
    monkeypatch.setattr(reader, "_BODY_ASSEMBLE_LINES", assemble)
    fragments = [fragment(4), fragment(1), fragment(1), fragment(8)]
    tables = [TableCandidate(None, (0, 0, 100, 70), {4}, -1),
              TableCandidate(None, (0, 0, 100, 70), set(), 1)]
    first, second = deepcopy(tables), deepcopy(tables)
    actual = reader.PDFReader._body_groups(None, fragments, first, (1, 3))
    expected = reader.PDFReader._body_groups_python(None, fragments, second, (1, 3))
    assert actual == expected
    assert first == second


def test_body_zero_sizes_calls_assembly_twice(monkeypatch):
    fragments = [fragment(2, size=0), fragment(1, size=0)]
    calls = []
    def assemble(fs):
        calls.append(list(fs))
        return []
    monkeypatch.setattr(reader, 'assemble_lines', assemble)
    monkeypatch.setattr(reader, '_BODY_ASSEMBLE_LINES', assemble)
    reader.PDFReader._body_groups(None, fragments, [], ())
    assert calls == [[fragments[1], fragments[0]], [fragments[0]], [fragments[1]]]


def test_body_partial_anchor_mutation_on_error():
    tables = [TableCandidate(None, (0, 0, 100, 70), set(), -1),
              SimpleNamespace(fragment_orders=set(), anchor_order=-1, bbox=())]
    with pytest.raises(IndexError):
        reader.PDFReader._body_groups(None, [fragment(5)], tables)
    assert tables[0].anchor_order == 5
    assert tables[1].anchor_order == -1


def test_body_direct_rejects_unknown_models():
    cbody = pytest.importorskip('dochan.pdf._cbody')
    with pytest.raises(cbody.Bailout):
        cbody.partition([object()], [], (), Fragment, TableCandidate)


def test_direct_stable_groups_and_no_public_writes():
    cbody = pytest.importorskip('dochan.pdf._cbody')
    fs = [fragment(4), fragment(1), fragment(1), fragment(8)]
    table = TableCandidate(None, (0, 0, 100, 70), {4}, -1)
    groups, anchors, singles = cbody.partition(fs, [table, table], (1, 3), Fragment, TableCandidate)
    assert groups == [[], fs[1:3], [], [], [fs[3]]]
    assert anchors == [(table, 4), (table, 4)]
    assert table.anchor_order == -1
    assert singles is None


def test_unexpected_c_error_replays_without_context(monkeypatch):
    def broken(*args):
        raise RuntimeError("C failure")
    monkeypatch.setattr(reader, '_cbody', SimpleNamespace(partition=broken))
    tables = [TableCandidate(None, (0, 0, 100, 70), set(), -1),
              SimpleNamespace(fragment_orders=set(), anchor_order=-1, bbox=())]
    with pytest.raises(IndexError) as raised:
        reader.PDFReader._body_groups(None, [fragment(5)], tables)
    assert raised.value.__context__ is None
    assert tables[0].anchor_order == 5


def test_assembly_error_keeps_committed_anchor(monkeypatch):
    def broken(_fs):
        raise ValueError("assembly failure")
    monkeypatch.setattr(reader, 'assemble_lines', broken)
    monkeypatch.setattr(reader, '_BODY_ASSEMBLE_LINES', broken)
    table = TableCandidate(None, (0, 0, 100, 70), set(), -1)
    with pytest.raises(ValueError, match="assembly failure"):
        reader.PDFReader._body_groups(None, [fragment(5)], [table])
    assert table.anchor_order == 5


def test_unmatched_anchor_scan_keeps_linear_temporary_memory():
    import tracemalloc

    cbody = pytest.importorskip('dochan.pdf._cbody')
    fragments = [fragment(i, y=100) for i in range(2000)]
    tables = [TableCandidate(None, (0, 0, 50, 0), set(), -1) for _ in range(500)]
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    try:
        for _ in range(2):
            baseline = tracemalloc.get_traced_memory()[0]
            tracemalloc.reset_peak()
            groups, anchors, singles = cbody.partition(
                fragments, tables, (), Fragment, TableCandidate)
            peak = tracemalloc.get_traced_memory()[1] - baseline
            assert groups[0] == fragments
            assert groups[1:] == [[] for _ in tables]
            assert anchors == [(table, len(fragments)) for table in tables]
            assert singles is None
            assert all(table.anchor_order == -1 for table in tables)
            # A retained y reference per comparison costs >8 MiB here. Event,
            # group and anchor storage scales with input count and stays <1 MiB.
            assert peak < 1024 * 1024
            del groups, anchors
    finally:
        if not was_tracing:
            tracemalloc.stop()
