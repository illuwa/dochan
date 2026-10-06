"""The optional handwritten scanner must preserve Python events and positions."""
import gc
import random
import struct
import sys

import pytest

from dochan.pdf.content import ContentTextExtractor, _PythonContentScanner

cscan = pytest.importorskip("dochan.pdf._cscan")


def _signature(value):
    identity = (type(value).__module__, type(value).__qualname__)
    if isinstance(value, float):
        return identity, repr(value), struct.pack("!d", value).hex()
    if isinstance(value, (list, tuple)):
        return identity, repr(value), tuple(_signature(item) for item in value)
    if isinstance(value, dict):
        return identity, repr(value), tuple(
            (_signature(key), _signature(item)) for key, item in value.items())
    return identity, repr(value)


def _step(scanner):
    try:
        value = scanner.next()
    except Exception as exc:
        return "exception", type(exc), scanner.pos
    return "return", _signature(value), scanner.pos


def _compare(data, positions=None, inline=False):
    python = _PythonContentScanner(data)
    native = cscan.Scanner(data)
    for call in range(len(data) * 2 + 5):
        if positions is not None and call < len(positions):
            python.pos = native.pos = positions[call]
        expected = _step(python)
        actual = _step(native)
        assert actual == expected, (data, call, expected, actual)
        if expected[0] == "exception":
            return
        if expected[1] == _signature(None):
            # Exhausting the regex iterator prevents rewinding, even via pos.
            python.pos = native.pos = -1
            assert _step(native) == _step(python)
            return
        if inline and expected[1] == _signature(("operator", b"BI")):
            python.pos = native.pos = ContentTextExtractor._skip_inline_image(data, python.pos)
    pytest.fail("scanner did not terminate")


BOUNDARIES = [
    b"", b"\x00\t\n\x0c\r ", b"%", b"% no newline", b"% one\r% two\n",
    b"(unterminated", b"<abc", b"[ 1 (broken", b"<< /A 1", b"<< /A >> Tj",
    b"[" * 70 + b"1" + b"]" * 70,
    b"<< /A " * 70 + b"1" + b" >>" * 70,
    b"(a\\(b\\)c) <ab c> /A#20B [/N true false null 0 Tc (x)] TJ",
    b"1 0 R", b"+1 0 R -1 0 R 1.0 0 R", b"1% c\r\n0% d\nR",
    b"1\x00\t0\rR/Name", b"1 0 Rfoo 1 0/R 1 0 R%end",
    b"+5 -.5 5. . - 1_0 1e5 0x10 --1", b"-0 +0 -0.0 +.0 .0",
    b"1.0e5 1.0e-999 1.0e999 1_0.5 1.0_5 +.inf -.nan",
    b"9" * 20, b"9" * 40, b"9" * 100,
    b"+999999999999999999 -999999999999999999",
    b"0." + b"0" * 400 + b"1", b"9" * 400 + b".0",
    b"0.1000000000000000055511151231257827021181583404541015625",
    b"1\x00\xff 2\x0b3\x0c4\x85 5\xff6", bytes(range(256)),
    b")>]}{ true false null q Q", b"1" + b" " * 4096 + b"m",
    b"BI /W 1 /H 1 ID \x00\xff EI Q", b"BI /W 1 ID (broken % data EI Q",
]


@pytest.mark.parametrize("data", BOUNDARIES)
def test_boundaries(data):
    _compare(data)


def test_inline_images():
    for data in BOUNDARIES[-2:]:
        _compare(data, inline=True)


def test_seeded_random_bytes_and_tokens():
    rng = random.Random(20261006)
    alphabet = b"abcXYZ0123456789 /[]()<>%\r\n\t\x00#\\-+.\"'\xff"
    for index in range(10000):
        size = rng.randrange(129)
        data = (rng.randbytes(size) if index % 2 else
                bytes(rng.choice(alphabet) for _ in range(size)))
        _compare(data)
    tokens = [b"1", b"0", b"R", b"+5", b"-.5", b"5.", b".", b"-", b"1_0",
              b"1e5", b"0x10", b"--1", b"9" * 100, b"1.0e999", b"1_0.5",
              b"/Name#20", b"(a\\)b)", b"<abc>", b"[1 /X]", b"<< /N 2 >>",
              b"[", b"]", b"(", b"<", b"<<", b">>", b"true", b"null", b"q",
              b"BI", b"ID", b"EI", b"\xff", b"12.345678901234567890"]
    gaps = [b" ", b"\n", b"\x00", b"%comment\r\n", b"", b"\t"]
    for _ in range(10000):
        _compare(b"".join(rng.choice(tokens) + rng.choice(gaps)
                          for _ in range(rng.randrange(24))))


@pytest.mark.parametrize("data", [b"", b"abc 12 /Name (text) Q", b"%comment\n1 0 R"])
def test_mutable_positions(data):
    for pos in [-10**100, -len(data) - 1, -1, 0, 1, len(data), len(data) + 1, 10**100]:
        _compare(data, [pos])
        _compare(data, [0, pos])
    # Advance into the middle of tokens, whitespace, comments and objects;
    # move backwards after a structured object consumed regex matches.
    for pos in range(len(data) + 2):
        _compare(data, [0, pos, -1, 2, 0])


def test_seeded_position_changes():
    rng = random.Random(725)
    for _ in range(1000):
        data = rng.randbytes(rng.randrange(128))
        _compare(data, [rng.randrange(-10, len(data) + 10) for _ in range(12)])


def test_float_rounding_and_signed_integers():
    rng = random.Random(815)
    for _ in range(4000):
        digits = bytes(rng.choice(b"0123456789") for _ in range(rng.randrange(1, 100)))
        split = rng.randrange(len(digits) + 1)
        sign = rng.choice([b"", b"+", b"-"])
        _compare(sign + digits[:split] + b"." + digits[split:])
        _compare(sign + digits)


@pytest.mark.parametrize("data", [bytearray(b"1"), "1", None])
def test_requires_bytes(data):
    with pytest.raises(TypeError):
        cscan.Scanner(data)


def test_attributes_and_data_lifetime():
    data = b"(retained) Tj"
    scanner = cscan.Scanner(data=data)
    assert scanner.data is data
    del data
    with pytest.raises(AttributeError):
        scanner.data = b"different"
    for invalid in [None, 1.5, "1"]:
        with pytest.raises(TypeError):
            scanner.pos = invalid
    with pytest.raises(TypeError):
        del scanner.pos
    assert scanner.next() == ("operand", b"retained")


def test_reinitialization_and_reference_counts():
    from dochan.pdf.objects import PDFSyntaxError

    data = bytes(bytearray(b"(owned) Tj"))
    gc.collect()
    references = tuple(sys.getrefcount(obj) for obj in (data, cscan.Scanner, PDFSyntaxError))
    for _ in range(5000):
        scanner = cscan.Scanner(data)
        assert scanner.next() == ("operand", b"owned")
        scanner.__init__(b"-0.0")
        assert scanner.pos == 0
        assert scanner.next() == ("operand", -0.0)
        del scanner
    gc.collect()
    assert tuple(sys.getrefcount(obj) for obj in (data, cscan.Scanner, PDFSyntaxError)) == references


def test_constructor_and_parser_failures_release_references(monkeypatch):
    from dochan.pdf import objects

    data = bytes(bytearray(b"(error) Q"))
    references = sys.getrefcount(data)

    class BrokenFactory(objects.PDFLexer):
        def __init__(self, data):
            raise RuntimeError("constructor")

    monkeypatch.setattr(objects, "PDFLexer", BrokenFactory)
    for _ in range(100):
        with pytest.raises(RuntimeError, match="constructor"):
            cscan.Scanner(data)
    gc.collect()
    assert sys.getrefcount(data) == references

    class BrokenParser(objects.PDFLexer):
        def __init__(self, data):
            self.data = data

        def parse_object(self):
            raise RuntimeError("parser")

    monkeypatch.setattr(objects, "PDFLexer", BrokenParser)
    for _ in range(100):
        scanner = cscan.Scanner(data)
        with pytest.raises(RuntimeError, match="parser"):
            scanner.next()
        del scanner
    gc.collect()
    assert sys.getrefcount(data) == references


def test_gc_collects_lexer_cycle(monkeypatch):
    from dochan.pdf import objects

    instances = []

    class CyclicLexer(objects.PDFLexer):
        def parse_object(self):
            self.scanner = instances[-1]
            return super().parse_object()

    monkeypatch.setattr(objects, "PDFLexer", CyclicLexer)
    gc.collect()
    before = sum(type(obj) is CyclicLexer for obj in gc.get_objects())
    for _ in range(100):
        instances.append(cscan.Scanner(b"(x)"))
        assert instances[-1].next() == ("operand", b"x")
    instances.clear()
    gc.collect()
    assert sum(type(obj) is CyclicLexer for obj in gc.get_objects()) == before
