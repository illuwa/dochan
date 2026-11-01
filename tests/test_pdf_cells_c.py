"""Native cell assembly must preserve every model field and Python fallback."""
import dataclasses
import random
from types import SimpleNamespace

import pytest

from dochan.pdf import layout
from dochan.pdf.tables import _NUMBER


def native():
    return pytest.importorskip("dochan.pdf._clayout")


def line(text='abc', **kw):
    values = dict(text=text, direction='ltr', left=0., right=100., y=50.,
                  size=10., first_size=10., last_size=10., order=0,
                  trailing_space=False, runs=[(text, False, False)])
    values.update(kw)
    return SimpleNamespace(**values)


def test_native_layout_exists():
    assert callable(native().merge_lines)


@pytest.mark.parametrize('runs', [[], [('  ', False, True)],
    [(' x ', True, False, 'url', 3, 'comment'), (' y ', False, True)],
    [('\u2003', False, False), ('\tx\u3000', True, True), (' ', True, False)]])
def test_trim_and_paragraph(runs):
    c = native()
    assert c.trim_runs(runs) == layout._python_trim_runs(runs)
    block = layout.TextBlock('x', 10, 1, runs)
    assert dataclasses.asdict(c.paragraph(block, 3)) == dataclasses.asdict(
        layout._python_paragraph(block, 3))


def test_merge_differential():
    rng = random.Random(716)
    for _ in range(1000):
        lines = [line(rng.choice(['한글', '中文', '12', 'abc', '• item', '', '  text ']),
                      y=50.-i*rng.choice([8., 15., 25.]),
                      right=rng.choice([50., 100.]), order=i,
                      direction=rng.choice(['ltr', 'rtl', 'up', 'down']),
                      trailing_space=rng.choice([True, False])) for i in range(rng.randrange(7))]
        bounds = rng.choice([None, (0., 100.)])
        assert native().merge_lines(lines, bounds) == layout._python_merge_lines(lines, bounds)


def test_number_unicode_and_boundaries():
    for value in ['', '-', '+1', '−１２,٣.٤%', '1,', '1,,', '.1', '1.', '²', '1\n', '1 2', '١']:
        assert native().number(value) == bool(_NUMBER.fullmatch(value))


def test_bailout_replays_python(monkeypatch):
    def bail(*args):
        raise native().Bailout()
    monkeypatch.setattr(layout, '_c_merge_lines', bail)
    assert layout.merge_lines([line()]) == layout._python_merge_lines([line()])


def test_custom_spacing_model_replays(monkeypatch):
    class Model:
        def joins_with_space(self, last, first):
            return True
    monkeypatch.setattr(layout, 'load_model', lambda: Model())
    lines = [line('한국'), line('국가', y=40.)]
    assert layout.merge_lines(lines) == layout._python_merge_lines(lines)


def test_sum_matches_runtime_bits():
    from dochan.pdf import tables
    from scripts.probe_pdf_ctables_fuzz import exact
    c = pytest.importorskip('dochan.pdf._ctables')
    runs = [(1. + i * 1e-10, 0., 1.) for i in range(101)]
    assert exact(c._snap_runs(runs, 1.5)) == exact(tables._snap_runs(runs, 1.5))


def test_observer_runs_only_on_python_replay(monkeypatch):
    events = []
    monkeypatch.setattr(layout, 'JOIN_OBSERVER', lambda *args: events.append(args))
    assert layout.merge_lines([line(), line('def', y=40.)])[0].text == 'abc def'
    assert events == [('abc', 'def', True)]


def test_unsupported_run_container_replays():
    class Run(tuple):
        pass
    runs = [Run((' x ', True, False))]
    assert layout._trim_runs(runs) == layout._python_trim_runs(runs)


def test_spacing_model_subclass_replays_python(monkeypatch):
    """joins_with_space 를 재정의한 하위 클래스는 C 가 표를 직접 읽으면 안 된다(감수 권고)."""
    from dochan.pdf import spacing

    class Always(spacing.SpacingModel):
        def joins_with_space(self, last, first):
            return True
    monkeypatch.setattr(spacing, '_DEFAULT_MODEL', Always())
    lines = [line('가나'), line('다라', y=40.)]
    merged = layout.merge_lines(lines)
    assert merged == layout._python_merge_lines(lines)
    assert merged[0].text == '가나 다라'


def test_conversion_error_replays_python():
    """C 가 OverflowError 등 변환 오류를 내도 래퍼는 Python 원본 결과를 돌려준다(감수 권고)."""
    native()
    lines = [line('abc'), line('def', y=40., first_size=10 ** 400, last_size=10 ** 400)]
    assert layout.merge_lines(lines) == layout._python_merge_lines(lines)
