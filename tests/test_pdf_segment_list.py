"""Lazy native path storage retains Segment identity and numeric categories."""
import struct

import pytest

native = pytest.importorskip('dochan.pdf._cinterp')


def collect(data):
    segments, shorts = native.SegmentList(), native.SegmentList()
    interp = native.Interpreter(data, {}, (1, 0, 0, 1, 0, 0),
                                (None, 0., 0., 0., 1., 0., 0, 1.),
                                segments, shorts, [])
    while interp.next() is not None:
        pass
    return segments, shorts


def test_lazy_sequence_identity_and_slice():
    segments, shorts = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S')
    assert len(segments) == 2
    assert len(shorts) == 0
    assert segments[0] is segments[0]
    assert segments[-1] is segments[1]
    assert segments[:] == list(segments)
    assert segments[::-1] == [segments[1], segments[0]]
    with pytest.raises(IndexError):
        segments[2]
    with pytest.raises(ValueError):
        segments[::0]


def test_numeric_types_and_clear():
    segments, shorts = collect(b'0 -0.0 m 10 -0.0 l S 0 1 m 0.5 1 l S')
    assert type(segments[0].x0) is float
    assert type(segments[0].y0) is float
    assert struct.pack('d', segments[0].y0) == struct.pack('d', 0.)
    assert len(shorts) == 1
    shorts.clear()
    assert list(shorts) == []


def test_tables_read_uncached_arrays_and_observe_cached_mutations(monkeypatch):
    tables = pytest.importorskip('dochan.pdf._ctables')
    from dochan.pdf.paths import Segment
    segments, shorts = collect(b'0 0 10 10 re S 0 5 m .5 5 l S 1 5 m 1.5 5 l S 2 5 m 2.5 5 l S')
    calls = []
    original = Segment.__post_init__

    def counted(self):
        calls.append(self)
        original(self)

    monkeypatch.setattr(Segment, '__post_init__', counted)
    actual = tables.build_tables(segments, [], short_segments=shorts)
    assert calls == []
    expected = tables.build_tables(list(segments), [], short_segments=list(shorts))
    assert actual == expected
    segments[0].x1 = 99.0
    assert tables.build_tables(segments, [], short_segments=shorts) == tables.build_tables(
        list(segments), [], short_segments=list(shorts))


def test_short_overflow_clears_previously_painted_segments():
    from dochan.pdf.paths import MAX_SEGMENTS, PathCollector
    data = b'0 0 m .5 0 l S ' * (MAX_SEGMENTS + 1)
    segments, shorts = collect(data)
    paths = PathCollector()
    for _ in range(MAX_SEGMENTS + 1):
        paths.operate(b'm', [0, 0], (1, 0, 0, 1, 0, 0))
        paths.operate(b'l', [.5, 0], (1, 0, 0, 1, 0, 0))
        paths.operate(b'S', [], (1, 0, 0, 1, 0, 0))
    assert list(segments) == paths.segments == []
    assert list(shorts) == paths.short_segments == []


@pytest.mark.parametrize('key', [-3, 2, 10**100, -(10**100)])
def test_sequence_index_bounds(key):
    segments, _ = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S')
    with pytest.raises(IndexError):
        segments[key]


@pytest.mark.parametrize('key', [1.0, '0', None, (0,)])
def test_sequence_invalid_index_types(key):
    segments, _ = collect(b'0 0 m 10 0 l S')
    with pytest.raises(TypeError):
        segments[key]


def test_sequence_index_protocol_and_slice_identity():
    class Index:
        def __index__(self):
            return 1

    segments, _ = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S')
    assert segments[Index()] is segments[1]
    assert segments[True] is segments[1]
    assert segments[False] is segments[0]
    assert segments[1:][0] is segments[1]
    assert segments[100:200] == []
    assert segments[-100:100:2] == [segments[0]]
    assert segments[1::-1] == [segments[1], segments[0]]


def test_sequence_comparison_and_mutation_visibility():
    segments, _ = collect(b'0 0 m 10 0 l S')
    same, _ = collect(b'0 0 m 10 0 l S')
    assert segments == same
    assert segments == list(segments)
    assert list(segments) == segments
    assert segments != ()
    segments[0].x1 = 2.5
    assert segments != same
    assert segments[0] in segments
    with pytest.raises(TypeError):
        segments[0] = same[0]
    with pytest.raises(TypeError):
        del segments[0]


def test_clear_releases_materialized_objects_and_keeps_external_reference():
    import gc
    import weakref

    segments, _ = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S')
    retained = segments[0]
    released = weakref.ref(segments[1])
    segments.clear()
    gc.collect()
    assert released() is None
    assert retained.x1 == 10.
    assert not segments
    assert list(segments) == []
    assert segments[:] == []
    segments.clear()
    with pytest.raises(IndexError):
        segments[0]


def test_cached_segment_reference_cycle_is_collectible():
    import gc
    import weakref

    segments, _ = collect(b'0 0 m 10 0 l S')
    item = segments[0]
    item.owner = segments
    reference = weakref.ref(item)
    del segments, item
    gc.collect()
    assert reference() is None


def test_materialization_error_can_be_retried(monkeypatch):
    from dochan.pdf.paths import Segment
    segments, _ = collect(b'0 0 m 10 0 l S')
    original = Segment.__post_init__

    def fail(self):
        raise ValueError('materialization failed')

    monkeypatch.setattr(Segment, '__post_init__', fail)
    with pytest.raises(ValueError, match='materialization failed'):
        segments[0]
    monkeypatch.setattr(Segment, '__post_init__', original)
    assert segments[0].x1 == 10.
    assert segments[0] is segments[0]


def test_long_overflow_preserves_first_segments_and_warning():
    from dochan.pdf.paths import MAX_SEGMENTS, PATH_WARNING, PathCollector
    data = b'0 0 m 2 0 l S ' * (MAX_SEGMENTS + 1)
    segments, shorts, warnings = native.SegmentList(), native.SegmentList(), []
    interp = native.Interpreter(data, {}, (1, 0, 0, 1, 0, 0),
                                (None, 0., 0., 0., 1., 0., 0, 1.),
                                segments, shorts, warnings)
    assert interp.next() is None
    paths = PathCollector()
    for _ in range(MAX_SEGMENTS + 1):
        paths.operate(b'm', [0., 0.], (1, 0, 0, 1, 0, 0))
        paths.operate(b'l', [2., 0.], (1, 0, 0, 1, 0, 0))
        paths.operate(b'S', [], (1, 0, 0, 1, 0, 0))
    assert len(segments) == MAX_SEGMENTS
    assert list(segments) == paths.segments
    assert warnings == paths.warnings == [PATH_WARNING]
    assert list(shorts) == paths.short_segments == []


def test_materializer_clear_does_not_leak_returned_segment(monkeypatch):
    import gc
    import weakref

    from dochan.pdf.paths import Segment
    segments, _ = collect(b'0 0 m 10 0 l S')
    original = Segment.__post_init__
    references = []

    def clear_during_init(self):
        original(self)
        references.append(weakref.ref(self))
        segments.clear()

    monkeypatch.setattr(Segment, '__post_init__', clear_during_init)
    item = segments[0]
    assert len(segments) == 0
    del item
    gc.collect()
    assert references[0]() is None


def test_materializer_clear_and_repopulate_uses_new_generation(monkeypatch):
    from dochan.pdf.paths import Segment
    segments, _ = collect(b'0 0 m 10 0 l S')
    original = Segment.__post_init__
    invoked = []

    def replace_during_init(self):
        original(self)
        if invoked:
            return
        invoked.append(True)
        segments.clear()
        engine = native.Interpreter(b'5 0 m 20 0 l S', {}, (1, 0, 0, 1, 0, 0),
                                    (None, 0., 0., 0., 1., 0., 0, 1.),
                                    segments, native.SegmentList(), [])
        assert engine.next() is None

    monkeypatch.setattr(Segment, '__post_init__', replace_during_init)
    previous = segments[0]
    assert previous.x1 == 10.
    assert segments[0].x0 == 5.
    assert segments[0].x1 == 20.
    assert segments[0] is not previous


def test_clear_is_safe_when_cached_destructor_clears_again(monkeypatch):
    from dochan.pdf.paths import Segment
    segments, _ = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S')
    destroyed = []

    def destroy(self):
        destroyed.append(self.x1)
        segments.clear()

    monkeypatch.setattr(Segment, '__del__', destroy, raising=False)
    assert segments[0].x1 == 10.
    assert segments[1].x1 == 2.
    segments.clear()
    assert destroyed == [10., 2.]
    assert len(segments) == 0


def test_table_input_mutation_during_cached_attribute_read_bails(monkeypatch):
    tables = pytest.importorskip('dochan.pdf._ctables')
    from dochan.pdf.paths import Segment
    segments, _ = collect(b'0 0 m 10 0 l S')
    retained = segments[0]
    original = Segment.__getattribute__

    def read(self, name):
        if self is retained and name == 'x0':
            segments.clear()
        return original(self, name)

    monkeypatch.setattr(Segment, '__getattribute__', read)
    with pytest.raises(tables.Bailout):
        tables.build_tables(segments, [])


def _exact_table_value(value):
    from dataclasses import fields, is_dataclass

    tag = type(value)
    if isinstance(value, float):
        return tag, struct.pack('!d', value)
    if is_dataclass(value):
        return tag, tuple((field.name, _exact_table_value(getattr(value, field.name)))
                          for field in fields(value))
    if isinstance(value, dict):
        return tag, tuple((_exact_table_value(k), _exact_table_value(v)) for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return tag, tuple(_exact_table_value(item) for item in value)
    return tag, value


@pytest.mark.parametrize('origin', [-float(2**52 + 16), -float(2**52 - 32), -0.0,
                                    0, 0.25, float(2**52 - 32), float(2**52 + 16)])
@pytest.mark.parametrize('tolerance', [0, 0.0, 0.5, 1.5, 2.0])
@pytest.mark.parametrize('cache_mode', ['uncached', 'partial', 'integers'])
def test_tables_native_coordinate_boundaries(origin, tolerance, cache_mode):
    tables = pytest.importorskip('dochan.pdf._ctables')
    from dochan.pdf.tables import TableBudget

    data = f'{origin:.17f} {origin:.17f} 16 12 re S'.encode()
    segments, shorts = collect(data)
    if cache_mode == 'partial':
        assert segments[0].x0 == origin
    elif cache_mode == 'integers':
        for segment in segments:
            for name in ('x0', 'y0', 'x1', 'y1'):
                value = getattr(segment, name)
                if value.is_integer():
                    setattr(segment, name, int(value))
    warnings, expected_warnings = [], []
    budget, expected_budget = TableBudget(2), TableBudget(2)
    actual = tables.build_tables(segments, [], tolerance=tolerance, warnings=warnings,
                                 budget=budget, short_segments=shorts)
    expected = tables.build_tables(list(segments), [], tolerance=tolerance,
                                   warnings=expected_warnings, budget=expected_budget,
                                   short_segments=list(shorts))
    assert _exact_table_value(actual) == _exact_table_value(expected)
    assert _exact_table_value(warnings) == _exact_table_value(expected_warnings)
    assert _exact_table_value(budget) == _exact_table_value(expected_budget)


def test_c_sequence_api_normalizes_negative_indices_once():
    import ctypes
    get_item = ctypes.pythonapi.PySequence_GetItem
    get_item.argtypes = (ctypes.py_object, ctypes.c_ssize_t)
    get_item.restype = ctypes.py_object
    segments, _ = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S')
    assert get_item(segments, -1) is segments[-1]
    assert get_item(segments, -2) is segments[0]
    with pytest.raises(IndexError):
        get_item(segments, -3)


def test_copy_pickle_and_concat_behave_like_list():
    """저장소 도구가 쓰는 deepcopy·pickle·`+` 가 list 와 같이 동작한다(감수 M)."""
    import copy
    import pickle
    segments, shorts = collect(b'0 0 m 10 0 l S 2 3 m 2 9 l S 5 5 m 5.2 5 l S')
    assert copy.deepcopy(segments) == list(segments)
    assert copy.copy(segments) == list(segments)
    assert pickle.loads(pickle.dumps(segments)) == list(segments)
    assert segments + shorts == list(segments) + list(shorts)
    assert segments + [None] == list(segments) + [None]


def test_tables_without_interpreter_module_keep_plain_inputs_silent():
    """해석기 모듈을 못 가져오는 새 프로세스에서 list 입력은 거짓 '불일치' 경고를 내지 않는다(감수 M)."""
    import os
    import subprocess
    import sys
    pytest.importorskip('dochan.pdf._ctables')
    env = {k: v for k, v in os.environ.items() if k != 'DOCHAN_DISABLE_ACCEL'}  # 새 프로세스는 가속 켬
    code = (
        "import sys\n"
        "sys.modules['dochan.pdf._cinterp'] = None\n"
        "from dochan.pdf import tables\n"
        "from dochan.pdf.paths import Segment\n"
        "from dochan.pdf.content import Fragment\n"
        "segs = [Segment(0., 0., 100., 0.), Segment(0., 20., 100., 20.), Segment(0., 0., 0., 20.), Segment(100., 0., 100., 20.)]\n"
        "frags = [Fragment(x=5., y=8., width=5., size=8., text='a', space_width=2.)]\n"
        "warnings = []\n"
        "tables.build_tables(tuple(segs), frags, warnings=warnings)\n"
        "assert tables.TABLE_BACKEND == 'c', tables.TABLE_BACKEND\n"
        "assert not warnings, warnings\n"
        "print('OK')\n")
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,  # nosemgrep: dangerous-subprocess-use-audit
                            timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'OK'
