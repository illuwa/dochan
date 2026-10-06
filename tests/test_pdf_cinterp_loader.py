"""Interpreter loader controls run even without a compiled extension."""
import os
from pathlib import Path
import subprocess
import sys


def _run(code, disabled=None):
    env = dict(os.environ)
    env.pop("DOCHAN_DISABLE_ACCEL", None)
    if disabled is not None:
        env["DOCHAN_DISABLE_ACCEL"] = disabled
    return subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, check=True)


def test_disable_interpreter_in_subprocess():
    result = _run("from dochan.pdf.content import CONTENT_INTERPRETER_BACKEND, _CInterpreter; "
                  "assert CONTENT_INTERPRETER_BACKEND == 'python'; "
                  "assert _CInterpreter is None; print(CONTENT_INTERPRETER_BACKEND)", disabled="1")
    assert result.stdout.strip() == "python"


def test_interpreter_import_failure_falls_back():
    result = _run("import sys; sys.modules['dochan.pdf._cinterp'] = None; "
                  "from dochan.pdf.content import CONTENT_INTERPRETER_BACKEND, _CInterpreter; "
                  "assert _CInterpreter is None; print(CONTENT_INTERPRETER_BACKEND)")
    assert result.stdout.strip() == "python"


def test_interpreter_only_import_error_is_suppressed():
    result = _run('''
import sys
import importlib.abc

class Broken(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "dochan.pdf._cinterp":
            raise RuntimeError("interpreter sentinel")

sys.meta_path.insert(0, Broken())
try:
    import dochan.pdf.content
except RuntimeError as exc:
    assert str(exc) == "interpreter sentinel"
else:
    raise AssertionError("error suppressed")
print("propagated")
''')
    assert result.stdout.strip() == "propagated"


def test_uncompiled_interpreter_extracts_with_python():
    result = _run('''
import sys
sys.modules["dochan.pdf._cinterp"] = None
from dochan.pdf.content import ContentTextExtractor, CONTENT_INTERPRETER_BACKEND
assert CONTENT_INTERPRETER_BACKEND == "python"
page = ContentTextExtractor().extract_page(b"BT /F 12 Tf (fallback) Tj 0 0 m 100 0 l S")
assert page.fragments[0].text == "fallback"
assert len(page.segments) == 1
print("fallback")
''')
    assert result.stdout.strip() == "fallback"


def test_partial_interpreter_import_does_not_enable_acceleration():
    result = _run('''
import sys
import types
partial = types.ModuleType("dochan.pdf._cinterp")
partial.Interpreter = object
sys.modules["dochan.pdf._cinterp"] = partial
from dochan.pdf.content import CONTENT_INTERPRETER_BACKEND, _CInterpreter
assert CONTENT_INTERPRETER_BACKEND == "python"
assert _CInterpreter is None
print("fallback")
''')
    assert result.stdout.strip() == "fallback"


def test_import_error_fallback_handles_form_loader_and_child_errors():
    result = _run('''
import sys
sys.modules["dochan.pdf._cinterp"] = None
from dochan.pdf.content import ContentTextExtractor, _CInterpreterBailout
assert _CInterpreterBailout is None
extractor = ContentTextExtractor()
def load(name, resources):
    if name == "LoaderError":
        raise ValueError("loader sentinel")
    fonts = (lambda: 1 / 0) if name == "ChildError" else {}
    return name, b"BT /F 10 Tf (LEAF) Tj ET", (1,0,0,1,0,0), {}, fonts, {}, 4, None, False
extractor.form_loader = load
page = extractor.extract_page(b"/LoaderError Do /ChildError Do /OK Do")
assert [f.text for f in page.fragments] == ["LEAF"]
assert len(page.warnings) == 1
assert "해석 실패" in page.warnings[0]
assert not extractor._form_context["active"]
print("fallback forms")
''')
    assert result.stdout.strip() == "fallback forms"
