"""Cached C strings survive row construction, errors and module reloads."""
import gc
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

import pytest

from dochan.pdf import content

clines = pytest.importorskip("dochan.pdf._clines")


def _assemble(line_type=content._Line, segment_type=content._Segment):
    fragments = [content.Fragment(0.0, 0.0, 10.0, 10.0, "a", 4.0,
                                  dir_x=0.0, dir_y=-1.0),
                 content.Fragment(50.0, 0.0, 10.0, 10.0, "b ", 4.0,
                                  dir_x=0.0, dir_y=-1.0)]
    return clines.assemble_lines(fragments, line_type, segment_type,
                                content.Fragment, content._LINE_Y_TOLERANCE)


def test_directions_share_the_module_owned_interned_string():
    expected = sys.intern("down")
    for _ in range(10):
        lines = _assemble()
        assert len(lines) == 2
        assert all(line.direction is expected for line in lines)


def test_cached_names_preserve_dynamic_new_and_constructor_errors():
    calls = []

    class Line(content._Line):
        def __new__(cls):
            calls.append(cls)
            return object.__new__(cls)

    class BrokenSegment(content._Segment):
        def __new__(cls):
            raise RuntimeError("segment allocation failed")

    lines = _assemble(Line)
    assert calls == [Line, Line]
    assert all(type(line) is Line for line in lines)
    with pytest.raises(RuntimeError, match="segment allocation failed"):
        _assemble(Line, BrokenSegment)
    assert [line.text for line in _assemble()] == ["a", "b"]


def test_cached_strings_do_not_accumulate_references_after_errors_and_reload():
    direction = sys.intern("down")
    key = sys.intern("fragment_orders")

    class BrokenLine(content._Line):
        @property
        def __dict__(self):
            raise RuntimeError("dictionary unavailable")

    def exercise():
        for _ in range(100):
            _assemble()
            with pytest.raises(RuntimeError, match="dictionary unavailable"):
                _assemble(BrokenLine)
        importlib.reload(clines)
        gc.collect()

    exercise()
    before = sys.getrefcount(direction), sys.getrefcount(key)
    exercise()
    assert (sys.getrefcount(direction), sys.getrefcount(key)) == before
    assert _assemble()[0].direction is direction


@pytest.mark.parametrize("module,checks", [(1, 42), (2, 16), (3, 9)])
def test_partial_module_initialization_cleans_owned_globals(tmp_path, module, checks):
    compiler = shutil.which("clang") or shutil.which("cc")
    if compiler is None or sys.platform == "win32":
        pytest.skip("fault-injection harness needs a Unix C compiler")
    source = Path(__file__).with_name("pdf_accel_cache_init.c")
    library = tmp_path / ("_cache_init_probe" + sysconfig.get_config_var("EXT_SUFFIX"))
    command = [compiler, "-std=c99", "-ffp-contract=off", "-fPIC",
               "-I" + sysconfig.get_config_var("INCLUDEPY"), "-DCACHE_MODULE=" + str(module),
               str(source), "-o", str(library)]
    command += (["-bundle", "-undefined", "dynamic_lookup"] if sys.platform == "darwin"
                else ["-shared"])
    subprocess.run(command, check=True, capture_output=True, text=True)  # nosemgrep: dangerous-subprocess-use-audit
    code = """
import importlib.util
import sys
from dochan.pdf import content, objects, paths
spec = importlib.util.spec_from_file_location('_cache_init_probe', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.run() == int(sys.argv[2])
"""
    # Keep ordinary loaders out of this test module's independent cache.
    env = dict(os.environ, DOCHAN_DISABLE_ACCEL="1")
    subprocess.run([sys.executable, "-c", code, str(library), str(checks)],  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
                   check=True, capture_output=True, text=True, env=env)
