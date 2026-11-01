"""The optional document parser suppresses ImportError only."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('kind', ['disable', 'missing', 'error'])
def test_loader(kind):
    env = dict(os.environ)
    env.pop('DOCHAN_DISABLE_ACCEL', None)
    if kind == 'disable':
        env['DOCHAN_DISABLE_ACCEL'] = '1'
    code = '''
import sys
import importlib.abc
kind = sys.argv[1]
if kind == 'missing':
    sys.modules['dochan.pdf._cobjects'] = None
if kind == 'error':
    class Broken(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == 'dochan.pdf._cobjects':
                raise RuntimeError('sentinel')
    sys.meta_path.insert(0, Broken())
try:
    from dochan.pdf.objects import PDFLexer, OBJECT_PARSER_BACKEND
except RuntimeError as error:
    assert kind == 'error' and str(error) == 'sentinel'
else:
    assert kind != 'error'
    assert OBJECT_PARSER_BACKEND == 'python'
    assert PDFLexer(b'<< /a 1 >>').parse_object() == {'a': 1}
'''
    subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        [sys.executable, '-c', code, kind], env=env,
        cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True)
