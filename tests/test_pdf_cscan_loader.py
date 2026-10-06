"""Loader controls also run on installations without a compiled extension."""
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


def test_disable_accelerator_in_subprocess():
    result = _run("from dochan.pdf.content import CONTENT_SCANNER_BACKEND, "
                  "ContentScanner, _PythonContentScanner; "
                  "assert CONTENT_SCANNER_BACKEND == 'python'; "
                  "assert ContentScanner is _PythonContentScanner; "
                  "print(CONTENT_SCANNER_BACKEND)", disabled="1")
    assert result.stdout.strip() == "python"


def test_import_failure_falls_back():
    result = _run("import sys; sys.modules['dochan.pdf._cscan'] = None; "
                  "from dochan.pdf.content import CONTENT_SCANNER_BACKEND, "
                  "ContentScanner, _PythonContentScanner; "
                  "assert ContentScanner is _PythonContentScanner; "
                  "print(CONTENT_SCANNER_BACKEND)")
    assert result.stdout.strip() == "python"


def test_only_import_error_is_suppressed():
    result = _run('''
import sys
import importlib.abc

class Broken(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "dochan.pdf._cscan":
            raise RuntimeError("sentinel")

sys.meta_path.insert(0, Broken())
try:
    import dochan.pdf.content
except RuntimeError as exc:
    assert str(exc) == "sentinel"
else:
    raise AssertionError("error suppressed")
print("propagated")
''')
    assert result.stdout.strip() == "propagated"
