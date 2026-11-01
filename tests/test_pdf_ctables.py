"""Whole-page C/Python table contracts, including replay and budget publication."""
import importlib
import os
import subprocess
import sys
from dataclasses import fields, is_dataclass
import struct

import pytest

from dochan.pdf import tables
from dochan.pdf.content import Fragment
from dochan.pdf.paths import Segment


def exact(value):
    """Keep numeric tags/bits, sequence order, and every dataclass field."""
    tag = type(value).__module__, type(value).__qualname__
    if isinstance(value, float):
        return tag, struct.pack('!d', value)
    if is_dataclass(value):
        return tag, tuple((field.name, exact(getattr(value, field.name)))
                          for field in fields(value))
    if isinstance(value, dict):
        return tag, tuple((exact(k), exact(v)) for k, v in value.items())
    if isinstance(value, (set, frozenset)):
        return tag, tuple(exact(item) for item in value)
    if isinstance(value, (list, tuple)):
        return tag, tuple(exact(item) for item in value)
    return tag, value


def fixture():
    segments = [Segment(0., y, 90., y) for y in (0., 20., 40., 60.)]
    segments += [Segment(x, 0., x, 60.) for x in (0., 30., 60., 90.)]
    fragments = [Fragment(4. + col * 30., 5. + row * 20., 10., 8.,
                          str(10 + row + col), 2., order=row * 3 + col)
                 for row in range(3) for col in range(3)]
    return segments, fragments


def native():
    try:
        return importlib.import_module('dochan.pdf._ctables')
    except ImportError:
        pytest.skip('optional C table accelerator is not built')


def test_table_backend_and_python_mirror_are_exposed():
    assert tables.TABLE_BACKEND in ('python', 'c')
    assert callable(tables._build_tables_python)
    if os.environ.get('DOCHAN_DISABLE_ACCEL') == '1':
        assert tables.TABLE_BACKEND == 'python'


@pytest.mark.parametrize('remaining', [0, 1, 8, 9, 10, 200000])
@pytest.mark.parametrize('tolerance', [0., 0.5, 1.5, 2.])
def test_ctables_every_field_and_document_budget(remaining, tolerance):
    c = native()
    segments, fragments = fixture()
    warning_c, warning_py = ['prior'], ['prior']
    budget_c, budget_py = tables.TableBudget(remaining), tables.TableBudget(remaining)
    expected = tables._build_tables_python(segments, fragments, tolerance, 3, warning_py, budget_py)
    actual = c.build_tables(segments, fragments, tolerance, 3, warning_c, budget_c)
    assert exact(actual) == exact(expected)
    assert exact(warning_c) == exact(warning_py)
    assert exact(budget_c) == exact(budget_py)


def test_ctables_empty_input_native():
    c = native()
    assert c.build_tables([], []) == []


def test_bailout_replays_with_original_warnings_and_budget(monkeypatch):
    c = native()
    segments, fragments = fixture()
    warnings = ['prior']
    budget = tables.TableBudget(20)
    expected_warnings = list(warnings)
    expected_budget = tables.TableBudget(budget.remaining)
    expected = tables._build_tables_python(segments, fragments, 1.5, 2,
                                          expected_warnings, expected_budget)

    def failed(*args, **kwargs):
        # Simulates an unsupported input discovered after work was attempted.
        local_warnings = kwargs.get('warnings', args[4] if len(args) > 4 else None)
        local_budget = kwargs.get('budget', args[5] if len(args) > 5 else None)
        if local_warnings is not None:
            local_warnings.append('discarded C attempt')
        if local_budget is not None:
            local_budget.remaining -= 1
        raise c.Bailout('unsupported')

    monkeypatch.setattr(tables, '_c_build_tables', failed)
    monkeypatch.setattr(tables, '_CTablesBailout', c.Bailout)
    actual = tables.build_tables(segments, fragments, 1.5, 2, warnings, budget)
    assert exact(actual) == exact(expected)
    assert warnings == expected_warnings
    assert budget == expected_budget


@pytest.mark.parametrize('limit_warning', [False, True])
def test_non_bailout_errors_propagate(monkeypatch, limit_warning):
    """Replay Python so a caught page error preserves its partial document budget."""
    c = native()
    monkeypatch.setattr(tables, '_c_build_tables', c.build_tables)
    monkeypatch.setattr(tables, '_CTablesBailout', c.Bailout)
    segments = grid([0, 20, 40], [0, 20, 40]) + grid([100, 200, 300], [100, 200, 300])
    if limit_warning:
        monkeypatch.setattr(tables, 'MAX_COMPONENT_LINES', 8)
        segments += grid([400, 410, 420, 430, 440], [400, 410, 420, 430, 440])
    fragments = [Fragment(5, 5, 5, 8, 'a', 2, order=0),
                 Fragment(150, 150, 5, 8, None, 2, order=1)]
    states = []
    for fn in (tables._build_tables_python, tables.build_tables):
        warnings, budget = ['existing'], tables.TableBudget(100)
        with pytest.raises(TypeError) as error:
            fn(segments, fragments, 1.5, 1, warnings, budget)
        assert error.value.__context__ is None
        states.append((str(error.value), list(warnings), budget.remaining))
        # reader catches the error and reuses this budget on the next page.
        states.append(exact(fn(*fixture(), budget=budget, warnings=warnings)))
    assert states[0][2] == 96
    assert len(states[0][1]) == 1 + limit_warning
    assert states[:2] == states[2:]


def grid(xs, ys):
    return ([Segment(xs[0], y, xs[-1], y) for y in ys]
            + [Segment(x, ys[0], x, ys[-1]) for x in xs])


def test_native_error_python_success_warns_and_discards_pending_state(monkeypatch):
    c = native()

    def failed(*args):
        args[4].append('discarded')
        args[5].remaining = 0
        raise RuntimeError('C-only failure')

    monkeypatch.setattr(tables, '_c_build_tables', failed)
    monkeypatch.setattr(tables, '_CTablesBailout', c.Bailout)
    warnings, budget = [], tables.TableBudget(100)
    expected = tables._build_tables_python(*fixture())
    actual = tables.build_tables(*fixture(), warnings=warnings, budget=budget)
    assert exact(actual) == exact(expected)
    assert budget.remaining == 91
    assert warnings == ['WARN: PDF 표 복원 C 가속 불일치 — Python 결과 사용']


@pytest.mark.parametrize('module_name,name', [('layout', 'merge_lines'), ('content', 'assemble_lines')])
def test_definition_module_callback_replacement_uses_python(monkeypatch, module_name, name):
    c = native()
    module = importlib.import_module('dochan.pdf.' + module_name)
    expected = tables._build_tables_python(*fixture())

    def forbidden(*args, **kwargs):
        pytest.fail('definition-module replacement must bypass native dispatch')

    monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(tables, '_c_build_tables', forbidden)
    monkeypatch.setattr(tables, '_CTablesBailout', c.Bailout)
    assert exact(tables.build_tables(*fixture())) == exact(expected)


@pytest.mark.parametrize('disabled', [False, True])
def test_backend_loader_environment(disabled):
    native()
    env = os.environ.copy()
    env.pop('DOCHAN_DISABLE_ACCEL', None)
    if disabled:
        env['DOCHAN_DISABLE_ACCEL'] = '1'
    code = 'from dochan.pdf.tables import TABLE_BACKEND; print(TABLE_BACKEND)'
    result = subprocess.run([sys.executable, '-c', code], env=env,  # nosemgrep: dangerous-subprocess-use-audit
                            check=True, text=True, capture_output=True)
    assert result.stdout.strip() == ('python' if disabled else 'c')


@pytest.mark.parametrize('error', ['ImportError', 'RuntimeError'])
def test_backend_loader_only_suppresses_import_error(error):
    env = os.environ.copy()
    env.pop('DOCHAN_DISABLE_ACCEL', None)
    code = '''
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'dochan.pdf._ctables':
            raise ERROR('intentional native loader error')
sys.meta_path.insert(0, Block())
from dochan.pdf.tables import TABLE_BACKEND
assert TABLE_BACKEND == 'python'
'''.replace('ERROR', error)
    result = subprocess.run([sys.executable, '-c', code], env=env,  # nosemgrep: dangerous-subprocess-use-audit
                            text=True, capture_output=True)
    if error == 'ImportError':
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert 'RuntimeError: intentional native loader error' in result.stderr


def test_document_budget_is_shared_across_successive_pages():
    c = native()
    segments, fragments = fixture()
    native_budget, python_budget = tables.TableBudget(18), tables.TableBudget(18)
    native_warnings, python_warnings = [], []
    for page in range(4):
        expected = tables._build_tables_python(segments, fragments, 1.5, page,
                                              python_warnings, python_budget)
        actual = c.build_tables(segments, fragments, 1.5, page, native_warnings, native_budget)
        assert exact(actual) == exact(expected)
        assert exact(native_budget) == exact(python_budget)
        assert exact(native_warnings) == exact(python_warnings)


@pytest.mark.parametrize('tolerance', [10 ** 1000, -(10 ** 1000)], ids=['large', 'negative-large'])
def test_large_integer_tolerance_replays_empty_input(tolerance):
    native()
    assert tables.build_tables([], [], tolerance) == tables._build_tables_python([], [], tolerance)


def test_negative_intersection_limit_keeps_empty_page_semantics(monkeypatch):
    c = native()
    monkeypatch.setattr(tables, 'MAX_INTERSECTION_CHECKS', -1)
    assert c.build_tables([], []) == tables._build_tables_python([], [])



def test_unrepresentable_coordinate_replays_before_any_mutation():
    c = native()
    segments = [Segment(10 ** 1000, 0, 10 ** 1000, 0)]
    with pytest.raises(c.Bailout):
        c.build_tables(segments, [])
    with pytest.raises(OverflowError) as expected:
        tables._build_tables_python(segments, [])
    with pytest.raises(OverflowError) as actual:
        tables.build_tables(segments, [])
    assert str(actual.value) == str(expected.value)
    assert actual.value.__context__ is None


def test_nested_fragment_set_iteration_matches_python():
    """Set equality misses resizing differences between add and union."""
    c = native()
    segments = [
        Segment(253.0, 53.0, 307.0, 53.0),
        Segment(253.0, 87.0, 307.0, 87.0),
        Segment(253.0, 53.0, 253.0, 87.0),
        Segment(307.0, 53.0, 307.0, 87.0),
        Segment(256.0, 56.0, 304.0, 56.0),
        Segment(256.0, 63.333333333333336, 304.0, 63.333333333333336),
        Segment(256.0, 67.0, 304.0, 67.0),
        Segment(256.0, 56.0, 256.0, 67.0),
        Segment(304.0, 56.0, 304.0, 67.0),
        Segment(305.499999999, 94.500000001, 305.499999999, 166.999999999),
        Segment(253.5, 93.5, 306.5, 93.5),
        Segment(253.5, 118.33333333333333, 306.5, 118.33333333333333),
        Segment(253.5, 143.16666666666666, 306.5, 143.16666666666666),
        Segment(253.5, 168.0, 306.5, 168.0),
        Segment(280.0, 93.5, 280.0, 168.0),
        Segment(306.5, 93.5, 306.5, 168.0),
    ]
    fragments = [
        Fragment(277.5, 66.5, 10.0, 8.0, '12%', 2.0, order=7, dir_x=1.0, dir_y=0.0, up_x=0.0, up_y=1.0),
        Fragment(277.5, 58.0, 3, 10.0, '12', 2.0, order=12, dir_x=1.0, dir_y=0.0, up_x=0.0, up_y=1.0),
        Fragment(277.5, 75.0, 20.0, 8.0, '.5', 2.0, order=14, dir_x=0.0, dir_y=-1.0, up_x=1.0, up_y=0.0),
        Fragment(277.5, 54.33333333333333, 0.0, 10.0, '-5', 2.0, order=15, dir_x=1.0, dir_y=0.0, up_x=0.0, up_y=1.0),
        Fragment(277.499999999, 58.0, 20.0, 8.0, 'abc', 2.0, order=16, dir_x=1.0, dir_y=-0.0, up_x=-0.0, up_y=1.0),
    ]
    expected = tables._build_tables_python(segments, fragments, budget=tables.TableBudget(8))
    actual = c.build_tables(segments, fragments, budget=tables.TableBudget(8))
    assert expected
    assert [list(t.fragment_orders) for t in actual] == [list(t.fragment_orders) for t in expected]
    assert exact(actual) == exact(expected)
