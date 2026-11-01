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
        return tag, frozenset(exact(item) for item in value)
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


def test_non_bailout_errors_propagate(monkeypatch):
    c = native()

    def failed(*args, **kwargs):
        raise RuntimeError('table accelerator failure')

    monkeypatch.setattr(tables, '_c_build_tables', failed)
    monkeypatch.setattr(tables, '_CTablesBailout', c.Bailout)
    with pytest.raises(RuntimeError, match='table accelerator failure'):
        tables.build_tables([], [])


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
