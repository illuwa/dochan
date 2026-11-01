"""Font preparation accelerator must mirror the Python parser transactionally."""
import importlib
import os

import pytest

from dochan.pdf import cmap


def test_ccmap_backend_contract():
    expected = 'python' if os.environ.get('DOCHAN_DISABLE_ACCEL') == '1' else 'c'
    try:
        importlib.import_module('dochan.pdf._ccmap')
    except ImportError:
        expected = 'python'
    assert cmap.CMAP_BACKEND == expected


@pytest.mark.parametrize('data', [
    b'', b'beginbfchar <01><0041><01><0042> endbfchar',
    b'begincodespacerange <0><ffff> endcodespacerange',
    b'beginbfrange <01><03><0041> endbfrange',
    b'beginbfrange <01><03>[<0041>[<0042>] endbfrange',
    b'beginbfrange <01><03><d7ff> endbfrange',
    b'beginbfrange <01><03><ffff> endbfrange',
    b'beginbfchar <01><f> endbfchar beginbfrange <01><00><01> endbfrange',
    b'% beginbfchar <01><0041> endbfchar',
    b'beginbfchar <00000000000000000001><0041> endbfchar',
    b'beginbfrange <00><ffff><0000> endbfrange ' * 2,
])
def test_tounicode_mirror(data):
    before, after = [], []
    left = cmap._parse_tounicode_python(data, before)
    right = cmap.parse_tounicode(data, after)
    assert vars(left) == vars(right)
    assert list(left.mapping.items()) == list(right.mapping.items())
    assert before == after


def test_encoding_mirror():
    data = (b'/A usecmap /Registry (Adobe) /Ordering (Korea1) '
            b'begincodespacerange <00><ff> endcodespacerange '
            b'begincidrange <01><03> 4 <ff><00> 2 endcidrange '
            b'beginnotdefchar <04> 3 endnotdefchar')
    parents = {'A': b'/A usecmap /WMode 1 def'}
    warnings1, warnings2 = [], []
    left = cmap._parse_encoding_cmap_python(data, warnings1, parents)
    right = cmap.parse_encoding_cmap(data, warnings2, parents)
    for key in vars(left):
        if key != 'parent':
            assert getattr(left, key) == getattr(right, key)
    assert vars(left.parent) == vars(right.parent)
    assert warnings1 == warnings2


@pytest.mark.parametrize('values', [[], [0, [500, float('nan'), -0.0]],
                                    [0, 65535, 12, 0, [500]],
                                    [False, [True, None, 'x']],
                                    [-2, [1, 2, 3], 4, 6, 120]])
def test_width_mirror(values):
    from dochan.pdf.widths import WidthMap
    native = pytest.importorskip('dochan.pdf._ccmap')
    expected = WidthMap.cid(values, float('nan'))
    table, default, warnings = native.cid_widths(values, float('nan'))
    assert list(table.items()) == list(expected._widths.items())
    assert default == expected._default
    assert warnings == expected.warnings
    assert native.simple_widths(-1, [12, 34, float('inf'), -0.0]) == {0: 34.0, 2: -0.0}


def test_differences_mirror():
    native = pytest.importorskip('dochan.pdf._ccmap')
    assert native.differences({0: 'a'}, [True, 'b', 1, 'c', False, 'd']) == {0: 'a', 1: 'c', 2: 'd'}


@pytest.mark.parametrize('rows', [[], [(0, 2, 1), (3, 5, 10)],
                                  [(3, 5, 10), (0, 2, 1)],
                                  [(0, 5, 1), (3, 7, 10)],
                                  [(2, 1, 5)], [(0, 2, 1.5)],
                                  [(0, 2, True)], [(0, 2**80, 1)]])
@pytest.mark.parametrize('constant', [False, True])
def test_flatten_ordered_mirror(rows, constant):
    expected = cmap._flatten_ranges_python(rows, constant)
    actual = cmap._flatten_ranges(rows, constant)
    from scripts.probe_pdf_objects import freeze
    assert freeze(actual) == freeze(expected)
    assert actual is not rows


def test_flatten_custom_flag_keeps_python_evaluation():
    class Flag:
        def __bool__(self):
            raise ValueError('custom flag')

    with pytest.raises(ValueError, match='custom flag'):
        cmap._flatten_ranges([(0, 1, 2)], Flag())


@pytest.mark.skipif(__import__('sys').platform not in ('darwin', 'linux'),
                    reason='ru_maxrss requires macOS or Linux')
def test_bfrange_pdf_peak_rss(tmp_path):
    """Measure complete PDF reads in fresh processes, including decompression."""
    import json
    import subprocess
    import sys
    import zlib
    from pathlib import Path

    from test_pdf_structure import _build_pdf, _minimal_objects

    pytest.importorskip('dochan.pdf._ccmap')
    data = (b'begincmap 1 begincodespacerange <00><ff> endcodespacerange '
            b'1 beginbfrange ' + b'[' * (16 * 1024 * 1024 - 200)
            + b' endbfrange endcmap')
    compressed = zlib.compress(data, 9)
    objects = _minimal_objects(b'BT /F1 12 Tf 72 720 Td (AB) Tj ET')
    objects[4] = (b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica '
                  b'/ToUnicode 6 0 R >>')
    objects[6] = (b'<< /Length %d /Filter /FlateDecode >>stream\n' % len(compressed)
                   + compressed + b'\nendstream')
    path = tmp_path / 'bracket-tounicode.pdf'
    path.write_bytes(_build_pdf(objects))
    code = '''
import json, resource, sys
from dochan.pdf import cmap
from dochan.pdf.reader import PDFReader
PDFReader().read(sys.argv[1])
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({'rss': rss * (1024 if sys.platform == 'linux' else 1),
                  'backend': cmap.CMAP_BACKEND}))
'''
    measurements = {}
    for mode in ('python', 'c'):
        env = dict(os.environ)
        env['DOCHAN_DISABLE_ACCEL'] = '1' if mode == 'python' else '0'
        # nosemgrep: dangerous-subprocess-use-audit
        result = subprocess.run([sys.executable, '-c', code, str(path)],
                                cwd=Path(__file__).resolve().parents[1], env=env,
                                capture_output=True, text=True, check=True, timeout=60)
        measurements[mode] = json.loads(result.stdout)
        assert measurements[mode]['backend'] == mode
    assert measurements['c']['rss'] <= measurements['python']['rss'] * 1.2, measurements


@pytest.mark.parametrize('body', [
    b'[[<01><02><0041>]<03><03>[<0043>]',
    b'<02><01>[<01><01><0041>',
    b'<01><01>[<0041>[<0042>] <02><02><0042>',
    b'<01><02>[<0041>[<0042>] <03><03><0043>',
    b'<01><01>[<0041><0042><0043>',
    b'<01><01><0041><02><02>',
    b'<01><01>[',
])
def test_streaming_bfrange_recovery(body):
    native = pytest.importorskip('dochan.pdf._ccmap')
    data = b'beginbfrange ' + body + b' endbfrange'
    expected = cmap._parse_tounicode_python(data)
    mapping, lengths, truncated = native.tounicode(data)
    assert list(mapping.items()) == list(expected.mapping.items())
    assert lengths == expected.code_lengths
    assert truncated == expected.truncated


def test_streaming_ignored_tail_preserves_bailout():
    native = pytest.importorskip('dochan.pdf._ccmap')
    # Nested '[' aborts mapping, but the old whole-block scan still bailed on
    # a long token after it. Keep that transactional fallback contract.
    with pytest.raises(native.Bailout):
        native.tounicode(b'beginbfrange <01><02>[[<0000000000000000> endbfrange')
