"""Document-object acceleration must preserve values, types and parser state."""
import struct

import pytest

from dochan.pdf import objects


def frozen(value):
    if isinstance(value, float):
        return (type(value).__name__, struct.pack('!d', value))
    if isinstance(value, dict):
        return (type(value).__name__, tuple((frozen(k), frozen(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(map(frozen, value)))
    return (type(value).__name__, value)


def outcome(cls, data, pos=0, skip=False, method='parse_object'):
    lexer = cls(data, pos)
    lexer.skip_array_operators = skip
    try:
        result = ('ok', frozen(getattr(lexer, method)()))
    except Exception as error:
        result = ('error', type(error).__name__, str(error))
    return result, lexer.pos, lexer._depth, lexer.stray_closers


@pytest.mark.parametrize('data', [
    b'<< /A [1 0 R -0 -0.0 true false null /N#61me (a(b)c)] >>',
    b'<< /URI (a)) /Next 2 >>', b'<< /URI (a))) >>',
    b'/#-1#+1#ff#xx', b'<0\x0b1>', b'<0\x001>', b'(a\\777\\\r\nb)',
    b'[1.0 0 R]', b'[(a) 0 Tc (b)]', b'[(a) Tc',
    b'[' * 70 + b']' * 70, b'<< /x (abc)', b'1_000 02 R',
    b'1.2e+3', b'1e3', b'99999999999999999999999999 0 R',
    b'\x00% comment\r\n[ /A /A true ]', b'', b'>', b'<ff', b'(abc\\',
])
@pytest.mark.parametrize('skip', [False, True])
def test_differential(data, skip):
    assert outcome(objects.PDFLexer, data, skip=skip) == outcome(
        objects._PythonPDFLexer, data, skip=skip)


@pytest.mark.parametrize('pos', [-100, -3, -1, 0, 3, 100, 2**100])
@pytest.mark.parametrize('method', ['parse_object', 'skip_whitespace', 'read_token'])
def test_offsets(pos, method):
    assert outcome(objects.PDFLexer, b'123', pos, method=method) == outcome(
        objects._PythonPDFLexer, b'123', pos, method=method)


def test_batch_duplicate_numbers_and_offsets():
    # First duplicate number wins at lookup; duplicate offsets share the spelling.
    data = b'5 0 5 2 6 0 7 4 1 2 (x))'
    pairs, parsed = objects.parse_object_stream(data, 4, 16)
    assert pairs == [(5, 0), (5, 2), (6, 0), (7, 4)]
    if objects._cobjects is None:
        assert parsed == {}
        return
    assert parsed[0] == (1, 0)
    assert parsed[2] == (2, 0)
    assert parsed[4] == (b'x', 0)


def test_backend_contract():
    assert objects.OBJECT_PARSER_BACKEND in ('c', 'python')


@pytest.mark.parametrize('body', [
    b'<< /Length 3 >> stream\r\nabc\nendstream',
    b'<< /Length 99 >> stream\na\n\nendstream',
    b'<< /Length true >> stream\nx endstream',
    b'<< /Length 2 0 R /URI (a)) >> stream\rxy\rendstream',
    b'<< >> stream\nmissing', b'123 endobj', b'(bad', b'<< /x (a)) >> endobj',
])
def test_indirect(body):
    def run(function):
        recovered, calls = [], []
        def resolve(ref):
            calls.append(ref)
            return 2
        try:
            value = ('ok', frozen(function(b'1 0 obj ' + body, 0, resolve, recovered)))
        except Exception as error:
            value = ('error', type(error).__name__, str(error))
        return value, recovered, calls
    assert run(objects.parse_indirect_object) == run(objects._parse_indirect_python)


def test_batch_loader_preserves_lazy_warnings_and_duplicate_lookup(monkeypatch):
    from dochan.pdf.structure import PDFFile
    from dochan.pdf import structure

    def run(accel):
        monkeypatch.setattr(objects, '_cobjects', accel)
        monkeypatch.setattr(structure, 'PDFLexer',
                            objects.PDFLexer if accel else objects._PythonPDFLexer)
        header = b'5 0 5 2 7 4 8 13 '
        data = header + b'1 2 << /a (x)) >> (broken'
        stream = objects.PDFStream({'Type': 'ObjStm', 'N': 4, 'First': len(header)}, data)
        pdf = PDFFile.__new__(PDFFile)
        pdf._cache = {}
        pdf._objstm_cache = {}
        pdf._objstm_parsed = {}
        pdf._compressed = {5: (10, 1), 6: (10, 1), 7: (10, 2), 9: (10, 3)}
        pdf.warnings = []
        pdf.get_object = lambda ref: stream
        pdf.decode_stream_bytes = lambda stm: data
        values = [pdf._load_compressed(i) for i in (5, 6, 7)]
        # Eagerly parsing the unused broken object must not emit its warning.
        assert values[:2] == [1, 2]
        assert len(pdf.warnings) == 1
        values.append(pdf._load_compressed(9))
        return frozen(values), pdf.warnings
    accel = objects._cobjects
    assert run(accel) == run(None)


def test_bailout_does_not_chain_exception():
    with pytest.raises(objects.PDFSyntaxError) as failure:
        objects.PDFLexer(b'<< /x [oops]').parse_object()
    assert not isinstance(failure.value.__context__,
                          type(objects._cobjects.Bailout()) if objects._cobjects else RuntimeError)


def test_limits_and_recovery_state(monkeypatch):
    monkeypatch.setattr(objects, 'MAX_COLLECTION_ITEMS', 2)
    monkeypatch.setattr(objects, 'MAX_NESTING_DEPTH', 2)
    for data in (b'[1 2 3]', b'<< /a 1 /b 2 /a 3 >>', b'[[[1]]]',
                 b'<< /a (x)) /b [broken] >>'):
        assert outcome(objects.PDFLexer, data) == outcome(objects._PythonPDFLexer, data)


def test_huge_object_stream_first_retains_header():
    assert objects.parse_object_stream(b'1 0 2 2 3 4', 2, 2**100) == ([(1, 0), (2, 2)], {})


def test_large_configured_limits(monkeypatch):
    monkeypatch.setattr(objects, 'MAX_COLLECTION_ITEMS', 2**100)
    monkeypatch.setattr(objects, 'MAX_NESTING_DEPTH', 2**100)
    assert outcome(objects.PDFLexer, b'[[1]]') == outcome(objects._PythonPDFLexer, b'[[1]]')


def test_duplicate_offsets_do_not_alias_mutable_objects():
    from dochan.pdf.structure import PDFFile
    header = b'5 0 6 0 '
    data = header + b'<< /a [1] >>'
    stream = objects.PDFStream({'Type': 'ObjStm', 'N': 2, 'First': len(header)}, data)
    pdf = PDFFile.__new__(PDFFile)
    pdf._cache, pdf._objstm_cache, pdf._objstm_parsed = {}, {}, {}
    pdf._compressed = {5: (10, 0), 6: (10, 1)}
    pdf.warnings = []
    pdf.get_object = lambda ref: stream
    pdf.decode_stream_bytes = lambda stm: data
    first = pdf._load_compressed(5)
    first['a'].append(2)
    assert pdf._load_compressed(6) == {'a': [1]}


def test_rescan_discards_eager_cache():
    from dochan.pdf.structure import PDFFile
    pdf = PDFFile(b'%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj')
    pdf._objstm_parsed[99] = {0: ({'old': True}, 0)}
    pdf._scan_objects()
    assert pdf._objstm_parsed == {}


_OVERLONG_PAIR = b'1' * 5000 + b' ' + b'9' * 20 + b' '
_FRESH_PROCESS = '''
import struct, sys
from dochan.pdf import objects
def frozen(value):
    if isinstance(value, float):
        return (type(value).__name__, struct.pack("!d", value))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(map(frozen, value)))
    if isinstance(value, dict):
        return (type(value).__name__, tuple((frozen(k), frozen(v)) for k, v in value.items()))
    return (type(value).__name__, value)
def run(function, *args):
    try:
        return ("ok", frozen(function(*args)))
    except Exception as error:
        return ("error", type(error).__name__)
pair = b"1" * 5000 + b" " + b"9" * 20 + b" "
assert objects.OBJECT_PARSER_BACKEND == "c", objects.OBJECT_PARSER_BACKEND
first = run(objects.parse_indirect_object, pair + b"obj 1 endobj", 0)
accel = objects._cobjects
objects._cobjects = None
expected = run(objects._parse_indirect_python, pair + b"obj 1 endobj", 0)
objects._cobjects = accel
assert first == expected, (first, expected)
stream = pair + b"1"
first = run(objects.parse_object_stream, stream, 1, len(stream) - 1)
objects._cobjects = None
expected = run(objects.parse_object_stream, stream, 1, len(stream) - 1)
assert first == expected, (first, expected)
print("same")
'''


@pytest.mark.skipif(objects.OBJECT_PARSER_BACKEND != 'c', reason='C object parser not built')
def test_overlong_number_pair_in_fresh_process():
    """A first number too long to convert must not leave a half-set error for the second.

    The leak only shows in a fresh interpreter: once int(bytes) has run anywhere, the stale
    error state is masked, so the check runs in a subprocess.
    """
    import subprocess
    import sys
    # nosemgrep: dangerous-subprocess-use-audit
    completed = subprocess.run([sys.executable, '-c', _FRESH_PROCESS], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip() == 'same'
