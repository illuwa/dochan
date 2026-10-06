"""Line-assembly loader checks also run without a compiled extension."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _run(code, disabled=None):
    env = dict(os.environ)
    env.pop("DOCHAN_DISABLE_ACCEL", None)
    if disabled is not None:
        env["DOCHAN_DISABLE_ACCEL"] = disabled
    return subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, check=True)


def test_disable_line_accelerator():
    result = _run('''
import sys
import importlib.abc
class MustNotImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "dochan.pdf._clines":
            raise AssertionError("disabled extension was imported")
sys.meta_path.insert(0, MustNotImport())
from dochan.pdf import content
assert content._c_assemble_lines is None
print(content.LINE_ASSEMBLY_BACKEND)
''', disabled="1")
    assert result.stdout.strip() == "python"


def test_missing_line_accelerator():
    result = _run('''
import sys
sys.modules["dochan.pdf._clines"] = None
from dochan.pdf import content
assert content._c_assemble_lines is None
print(content.LINE_ASSEMBLY_BACKEND)
''')
    assert result.stdout.strip() == "python"


@pytest.mark.parametrize("exception, expected", [
    ("ImportError", "python"), ("ModuleNotFoundError", "python"),
    ("RuntimeError", "propagated"), ("ValueError", "propagated"),
])
def test_line_accelerator_import_exception_policy(exception, expected):
    result = _run('''
import sys
import importlib.abc
class Broken(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "dochan.pdf._clines":
            raise EXCEPTION("sentinel")
sys.meta_path.insert(0, Broken())
try:
    from dochan.pdf import content
except EXCEPTION as exc:
    assert str(exc) == "sentinel"
    print("propagated")
else:
    assert content._c_assemble_lines is None
    print(content.LINE_ASSEMBLY_BACKEND)
'''.replace("EXCEPTION", exception))
    assert result.stdout.strip() == expected


def test_all_public_line_entrypoints_use_extension():
    result = _run('''
import sys
import types
calls = []
module = types.ModuleType("dochan.pdf._clines")
def fake(*args):
    calls.append(args)
    return None
module.assemble_lines = fake
sys.modules["dochan.pdf._clines"] = module
from dochan.pdf import content
assert content.LINE_ASSEMBLY_BACKEND == "c"
assert content._c_assemble_lines is fake
fragment = content.Fragment(0.0, 0.0, 1.0, 10.0, "x", 2.0)
assert content.assemble_lines([fragment])[0].text == "x"
extractor = content.ContentTextExtractor()
extractor.extract_fragments = lambda data: [fragment]
assert extractor.extract_lines(b"")[0].text == "x"
assert extractor.extract_sized(b"") == [("x", 10.0)]
assert len(calls) == 3
for args in calls:
    assert args == ([fragment], content._Line, content._Segment,
                    content.Fragment, content._LINE_Y_TOLERANCE)
print("routed")
''')
    assert result.stdout.strip() == "routed"


def test_line_accelerator_runtime_errors_propagate():
    result = _run('''
import sys
import types
module = types.ModuleType("dochan.pdf._clines")
def broken(*args):
    raise RuntimeError("line sentinel")
module.assemble_lines = broken
sys.modules["dochan.pdf._clines"] = module
from dochan.pdf import content
try:
    content.assemble_lines([content.Fragment(0.0, 0.0, 1.0, 10.0, "x", 2.0)])
except RuntimeError as exc:
    assert str(exc) == "line sentinel"
else:
    raise AssertionError("runtime error was suppressed")
print("propagated")
''')
    assert result.stdout.strip() == "propagated"
