"""The optional content interpreter preserves Python types and IEEE bits."""
from dataclasses import fields, is_dataclass
import gc
import math
import os
from pathlib import Path
import random
import struct
import subprocess
import sys

import pytest

from dochan.pdf import content
from dochan.pdf.content import ContentTextExtractor, FontInfo
from dochan.pdf.objects import PDFName
from dochan.pdf.widths import WidthMap

cinterp = pytest.importorskip("dochan.pdf._cinterp")


def _signature(value):
    """Include every dataclass field, container type and signed floating zero."""
    identity = (type(value).__module__, type(value).__qualname__)
    if isinstance(value, float):
        return identity, struct.pack("!d", value).hex()
    if is_dataclass(value):
        return identity, tuple((f.name, _signature(getattr(value, f.name)))
                               for f in fields(value))
    if isinstance(value, (list, tuple)):
        return identity, tuple(_signature(item) for item in value)
    if isinstance(value, dict):
        return identity, tuple(sorted(((_signature(k), _signature(v))
                                       for k, v in value.items()), key=repr))
    if isinstance(value, (set, frozenset)):
        return identity, tuple(sorted((_signature(item) for item in value), key=repr))
    return identity, value


def _fonts():
    widths = WidthMap({code: 480 + code for code in range(256)}, 500.0)
    return {"F": FontInfo(lambda raw: raw.decode("latin1"), widths),
            "F V": FontInfo(lambda raw: raw.decode("latin1"), widths, bold=True,
                            italic=True, wmode=1)}


def _extract(data, native, configure=None, initial_ctm=(1, 0, 0, 1, 0, 0), initial_state=None):
    saved = content._CInterpreter, content._CInterpreterBailout
    content._CInterpreter = cinterp.Interpreter if native else None
    content._CInterpreterBailout = cinterp.Bailout
    try:
        extractor = ContentTextExtractor.from_fonts(_fonts(), track_char_positions=True)
        extractor.resources = {"ExtGState": {"GS": {"LW": 2.75}}}
        extractor.properties = {"Props": {"MCID": 7}}
        if configure:
            configure(extractor)
        try:
            page = extractor.extract_page(data, _initial_ctm=initial_ctm,
                                          _initial_text_state=initial_state)
        except Exception as exc:
            return ("exception", type(exc), str(exc)), None
        state = (extractor._form_context, extractor._marked_stack,
                 extractor._marked_overflow, extractor._link_position_reliable)
        return ("return", _signature(page)), _signature(state)
    finally:
        content._CInterpreter, content._CInterpreterBailout = saved


def _compare(data, configure=None, **kwargs):
    expected = _extract(data, False, configure, **kwargs)
    actual = _extract(data, True, configure, **kwargs)
    assert actual == expected, (data, expected, actual)


STATE_OPERATORS = {
    b"q": b"", b"Q": b"", b"cm": b"1 -0.0 0 1 3 4", b"BT": b"",
    b"Tf": b"/F 12", b"Tc": b"0.25", b"Tw": b"2", b"Tz": b"75",
    b"TL": b"14", b"Tr": b"2", b"w": b"0.5", b"Td": b"3 4",
    b"TD": b"3 -4", b"Tm": b"1 0 0 1 5 6", b"T*": b"",
    b"m": b"0 0", b"l": b"100 0", b"re": b"0 0 100 1",
    b"c": b"10 0 90 0 100 0", b"v": b"90 0 100 0", b"y": b"10 0 100 0",
    b"h": b"", b"S": b"", b"s": b"", b"f": b"", b"F": b"",
    b"f*": b"", b"B": b"", b"B*": b"", b"b": b"", b"b*": b"", b"n": b"",
    b"Tj": b"(text)", b"'": b"(quote)", b'"': b"2 1 (double)",
    b"TJ": b"[(a) 20 (b) -35 (c)]", b"Do": b"/Missing", b"gs": b"/GS",
    b"BDC": b"/Span << /MCID 3 >>", b"BMC": b"/Artifact", b"EMC": b"",
    b"unknown": b"0 1",
}


@pytest.mark.parametrize("op,operands", STATE_OPERATORS.items())
@pytest.mark.parametrize("mode", ["valid", "missing", "string", "name", "boolean", "array"])
def test_each_operator_valid_and_malformed_operands(op, operands, mode):
    if mode == "missing":
        operands = b""
    elif mode != "valid":
        invalid = {"string": b"(bad)", "name": b"/Bad", "boolean": b"true",
                   "array": b"[1 2]"}[mode]
        operands = b" ".join([invalid] * 6)
    _compare(b"BT /F 12 Tf 0 0 m " + operands + b" " + op
             + b" (after) Tj 100 0 l S ET")


SELECTED = [
    b"(integer identity) Tj", b"BT /F 12 Tf (A) Tj (B) Tj ET",
    b"BT /F 12 Tf -0.0 Tc -0.0 Tw -0.0 TL -0.0 w (A) Tj T* (B) Tj",
    b"-0.0 0.0 0 -1.0 0 -0.0 cm BT /F 12 Tf 1 0 0 1 -0.0 -0.0 Tm (x) Tj",
    b"BT /F 12 Tf (old) Tj /Missing (invalid) Tf (after) Tj 18 Tf (size) Tj",
    b"BT /F 12 Tf 14 TL (a) Tj (b) ' 2 1 (c) \" [(d) 20 (e) -35 /N [3] (f)] TJ",
    b"BT /F 12 Tf 3 Tr (hidden) Tj 2 Tr 2 w (stroke) Tj /GS gs (wide) Tj",
    b"BT /F#20V 12 Tf 14 TL (a) Tj [(b) 20 (c)] TJ (d) ' 3 1 (e) \"",
    b"0 0 m 10 0 90 0 100 0 c S 0 0 m 10 40 90 40 100 0 c S",
    b"0 0 m 100 0 100 0 v S 0 0 m 0 0 100 0 y S",
    b"0 0 100 1 re f 0 0 100 40 re f 0 0 -100 -1 re f*",
    b"0 0 m 100 0 l 100 100 l h s 0 0 100 1 re B*",
    b"0 0 m 100 0 l", b"0 0 m 0.5 0 l S 0 0 m 1 0.6 l S",
    b"/Span << /MCID 4 >> BDC BT /F 12 Tf (a) Tj EMC /Span << /MCID 4 >> BDC (b) Tj EMC",
    b"/Span /Props BDC /Artifact BMC BT /F 12 Tf (artifact) Tj EMC EMC",
    b"BI /W 1 /H 1 /BPC 8 ID \xff\x00 (fake) Tj EI BT /F 12 Tf (real) Tj",
    b"BI /W 1 ID (broken % inline data EI BT /F 12 Tf (real) Tj",
    b"BT /F 12 Tf (unterminated", b"BT /F 12 Tf [(a) 30 (broken TJ",
    b"BT /F 12 Tf /A# /A#2 /A#20 /A#20B /A#gg Tf (after) Tj",
    b"BT /F 12 Tf (a\\050b\\051\\101\\7\\777\\q\r\nb\\\r\nc\\\nd) Tj",
    b"BT /F 12 Tf (nested (child) \\(escaped\\) end) Tj <61 62 6> Tj",
    b"BT /F 12 Tf [1 0 R (a) true null [2 (nested)] << /X 1 >> 5.0] TJ",
    b"BT /F 12 Tf [" * 70 + b"(deep)" + b"]" * 70 + b" TJ",
    b"1e400 Tc 1.0e400 Tc 1.0e-400 Tz (overflow) Tj",
    b"% no final newline", bytes(range(256)),
]


@pytest.mark.parametrize("data", SELECTED)
def test_selected_streams(data):
    _compare(data)


@pytest.mark.parametrize("digits", [20, 40, 400])
def test_large_integers_and_float_overflow(digits):
    huge = b"9" * digits
    for op in (b"Tc", b"Tr", b"cm", b"Tm", b"m", b"re", b"Tf", b"TJ"):
        _compare(b"BT /F 12 Tf (before) Tj " + b" ".join([huge] * 6)
                 + b" " + op + b" (after) Tj")
    _compare(b"BT /F 12 Tf 1 0 0 1 " + huge + b" 0 cm (x) Tj")


def test_graphics_stack_overflow_and_operand_truncation():
    _compare(b"BT /F 12 Tf " + b"q 1 0 0 1 1 2 cm " * 300
             + b"(deep) Tj " + b"Q " * 300 + b"(restored) Tj")
    for count in (64, 65, 66, 128, 130, 257):
        _compare(b"BT /F 12 Tf " + b" ".join(str(i).encode() for i in range(count))
                 + b" 1 0 0 1 10 20 Tm (window) Tj")


def test_marked_content_stack_overflow():
    _compare(b"/Span << /MCID 3 >> BDC " * 65
             + b"BT /F 12 Tf (deep) Tj " + b"EMC " * 65 + b"(plain) Tj")


@pytest.mark.parametrize("pattern", [b"0 0 m 100 0 l S ", b"0 0 m 0.5 0 l S ",
                                     b"0 0 m 100 0 l ", b"0 0 m "])
def test_path_limits_20001(pattern):
    _compare(pattern * 20001 + b"S BT /F 12 Tf (survives) Tj")


def _form_setup(extractor):
    forms = {
        "A": (b"/Span << /MCID 99 >> BDC BT /F 10 Tf (child) Tj /B Do EMC", (1, 0, 0, 1, 2, 3)),
        "B": (b"BT /F 9 Tf (nested) Tj /A Do", (1.0, 0, 0, 1, 5, 6)),
        "Bad": (b"BT /F 10 Tf (bad) Tj", (0, 0, 0, 0, 0, 0)),
        "Huge": (b"BT /F 10 Tf (huge) Tj", (10**40, 0, 0, 1, 0, 0)),
        "Limit": (b"BT /F 10 Tf (limit) Tj", (1, 0, 0, 1, 0, 0)),
    }

    def load(name, resources):
        if name == "Raises":
            raise ValueError("test loader")
        if name not in forms:
            return None
        data, matrix = forms[name]
        count = 40000 if name == "Limit" else ContentTextExtractor._count_operators(data)[0]
        return name, data, matrix, {}, extractor._fonts, {}, count, None, False

    extractor.form_loader = load


@pytest.mark.parametrize("data", [
    b"BT /F 12 Tf /Span << /MCID 2 >> BDC /A Do /A Do EMC (parent) Tj",
    b"/Raises Do /Missing Do /Bad Do /Huge Do /Limit Do /A Do",
    b"/A Do /Span << /MCID 1 >> BDC BT /F 12 Tf (parent) Tj (bad) Tc /A Do EMC",
])
def test_forms_recursion_cycles_limits_and_bailout_context(data):
    _compare(data, _form_setup)


def test_form_depth_limit():
    def configure(extractor):
        def load(name, resources):
            level = int(name[1:])
            data = b"BT /F 12 Tf (child) Tj /F" + str(level + 1).encode() + b" Do"
            return level, data, (1, 0, 0, 1, 0, 0), {}, extractor._fonts, {}, 4, None, False
        extractor.form_loader = load
    _compare(b"/F0 Do", configure)


def test_bailout_after_form_replays_and_restores_all_context(monkeypatch):
    data = b"/Span << /MCID 8 >> BDC BT /F 12 Tf (parent) Tj /A Do EMC (after) Tj"
    expected = _extract(data, False, _form_setup)
    native = cinterp.Interpreter
    calls = []

    class DelayedBailout:
        def __init__(self, *args):
            object.__setattr__(self, "wrapped", native(*args))
            object.__setattr__(self, "after_form", False)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def __setattr__(self, name, value):
            setattr(self.wrapped, name, value)

        def next(self):
            if self.after_form:
                calls.append("bailout")
                raise cinterp.Bailout("forced after Form side effects")
            event = self.wrapped.next()
            if event is not None and event[0] == b"Do":
                object.__setattr__(self, "after_form", True)
            return event

    monkeypatch.setattr(cinterp, "Interpreter", DelayedBailout)
    actual = _extract(data, True, _form_setup)
    assert calls
    assert actual == expected


def test_seeded_random_operator_combinations_and_byte_mutations():
    rng = random.Random(20261006)
    fragments = [args + b" " + op for op, args in STATE_OPERATORS.items()]
    fragments += SELECTED[:24] + [b"-0.0", b"(broken", b"[", b"<< /MCID 4 >>",
                                  b"/A#20B", b"true", b"9" * 40, b"1.0e400"]
    gaps = [b" ", b"\n", b"\x00", b"%comment\r\n", b"\t"]
    for index in range(20000):
        data = b"BT /F 12 Tf " + b"".join(rng.choice(fragments) + rng.choice(gaps)
                                          for _ in range(rng.randrange(1, 9)))
        if index % 3 == 0:
            mutated = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                action = rng.randrange(3)
                pos = rng.randrange(len(mutated) + 1)
                if action == 0:
                    mutated.insert(pos, rng.randrange(256))
                elif pos < len(mutated):
                    if action == 1:
                        del mutated[pos]
                    else:
                        mutated[pos] = rng.randrange(256)
            data = bytes(mutated)
        _compare(data)


def test_hypot_axis_fast_path_ieee_identity():
    rng = random.Random(92817)
    values = [0.0, -0.0, float("inf"), -float("inf"),
              sys.float_info.min, sys.float_info.max, math.ulp(0.0)]
    for _ in range(20000):
        value = struct.unpack("!d", rng.getrandbits(64).to_bytes(8, "big"))[0]
        if not math.isnan(value):
            values.append(value)
    for value in values:
        assert _signature(math.hypot(0, value)) == _signature(abs(value))
        assert _signature(math.hypot(value, 0)) == _signature(abs(value))


def _interpreter(data, fonts=None, ctm=(1, 0, 0, 1, 0, 0)):
    return cinterp.Interpreter(data, {} if fonts is None else fonts, ctm,
                               (None, 0.0, 0.0, 0.0, 1.0, 0.0, 0, 1.0), [], [], [])


def test_interpreter_contract_and_state_types():
    native = _interpreter(b"BT /F 12 Tf 3 4 Td (one) Tj 100 0 l S (two) Tj", _fonts())
    assert _signature(native.ctm) == _signature((1, 0, 0, 1, 0, 0))
    assert native.next() == (b"Tj", [b"one"])
    assert native.fs == 12.0 and type(native.fs) is float
    assert _signature(native.tm) == _signature((1, 0, 0, 1, 3.0, 4.0))
    assert native.text_line_reset
    native.text_line_reset = False
    native.tm = (1, 0, 0, 1, -0.0, 9.0)
    assert native.next() == (b"Tj", [b"two"])
    assert not native.text_line_reset
    assert _signature(native.tm) == _signature((1, 0, 0, 1, -0.0, 9.0))
    assert native.next() is None
    assert native.next() is None


@pytest.mark.parametrize("data", [bytearray(b"1"), "1", None])
def test_interpreter_requires_bytes(data):
    with pytest.raises((TypeError, cinterp.Bailout)):
        _interpreter(data)


@pytest.mark.parametrize("number", [True, 10**40])
def test_constructor_uncertain_numeric_ctm_bails_out(number):
    with pytest.raises(cinterp.Bailout):
        _interpreter(b"", ctm=(number, 0, 0, 1, 0, 0))


def test_reference_counts_and_input_lifetime():
    data = bytes(bytearray(b"BT /F 12 Tf (retained) Tj"))
    fonts = _fonts()
    gc.collect()
    refs = sys.getrefcount(data), sys.getrefcount(fonts)
    for _ in range(500):
        native = _interpreter(data, fonts)
        assert gc.is_tracked(native)
        assert native.next() == (b"Tj", [b"retained"])
        del native
    gc.collect()
    assert (sys.getrefcount(data), sys.getrefcount(fonts)) == refs
    native = _interpreter(data, fonts)
    del data, fonts
    assert native.next() == (b"Tj", [b"retained"])


def test_gc_collects_cycles_via_font_dictionary():
    gc.collect()
    before = sum(type(obj) is cinterp.Interpreter for obj in gc.get_objects())
    for _ in range(100):
        fonts = {}
        native = _interpreter(b"", fonts)
        fonts["cycle"] = native
    del native, fonts
    gc.collect()
    assert sum(type(obj) is cinterp.Interpreter for obj in gc.get_objects()) == before


@pytest.mark.parametrize("data", [
    b"/A# /A#2 /A#20 /A#20B /A#gg (x) Tj",
    b"(a\\050b\\051\\101\\7\\777\\q\r\nb\\\r\nc\\\nd) (x) Tj",
    b"(nested (child) \\(escaped\\) end) <61 62 6> /A (x) Tj",
    b"[1 (a) /N true false null 0 Tc [2 (b)] << /X 3 >>] TJ",
    b"<< /A 1 /B (x) >> /N 1 0 R (show) Tj",
    b"(unterminated", b"<abc", b"[1 (broken", b"<< /A 1",
])
def test_next_operand_lists_match_python_object_types(data):
    scanner = content._PythonContentScanner(data)
    expected = []
    operands = []
    yielded = {b"Tj", b"'", b'"', b"TJ", b"Do", b"BDC", b"BMC", b"EMC", b"gs", b"BI"}
    while True:
        event = scanner.next()
        if event is None:
            break
        kind, value = event
        if kind == "operand":
            operands.append(value)
            if len(operands) > 64:
                del operands[:-8]
        else:
            if value in yielded:
                expected.append((value, operands))
            operands = []
    native = _interpreter(data)
    actual = []
    while True:
        event = native.next()
        if event is None:
            break
        actual.append(event)
    assert _signature(actual) == _signature(expected)
    for _op, values in actual:
        for value in values:
            if isinstance(value, PDFName):
                assert type(value) is PDFName


def test_returned_operand_window_65_and_130():
    for count in (64, 65, 130):
        data = b" ".join(str(i).encode() for i in range(count)) + b" (x) Tj"
        native = _interpreter(data)
        operands = []
        for value in list(range(count)) + [b"x"]:
            operands.append(value)
            if len(operands) > 64:
                del operands[:-8]
        assert _signature(native.next()) == _signature((b"Tj", operands))


@pytest.mark.parametrize("ctm", [
    (1, 0, 0, 1, 0, 0), (1.0, 0, 0, 1, -0.0, 0),
    (-0.0, 0.0, -0.0, -1.0, -0.0, 0.0), (1, 0, 0, 1, 2**53, -2**53),
    (2**54, 0, 0, 1, 0, 0), (True, 0, 0, 1, 0, 0),
    (1, 0, 0, 1, float("nan"), 0), (float("inf"), 0, 0, 1, 0, 0),
])
def test_initial_matrix_numeric_types_nonfinite_and_range(ctm):
    _compare(b"BT /F 12 Tf (initial) Tj 3 4 Td (moved) Tj 0 0 m 100 0 l S", initial_ctm=ctm)


@pytest.mark.parametrize("initial_state", [
    (None, 12, 0, 0, 1, 14), (None, 12, -0.0, 0, 1.0, -0.0, 2, 1),
    (None, 12.0, 0.0, 2, 1, 14, 3, 0.25),
])
def test_initial_text_state_preserves_integer_and_float_categories(initial_state):
    _compare(b"BT (initial) Tj T* (line) Tj (quoted) ' q 2 Tc (changed) Tj Q (restored) Tj",
             initial_state=initial_state)


class _IntSubclass(int):
    pass


class _FloatSubclass(float):
    pass


@pytest.mark.parametrize("number", [True, _IntSubclass(1), _FloatSubclass(1.0)])
def test_constructor_rejects_nonexact_numeric_types(number):
    with pytest.raises(cinterp.Bailout):
        _interpreter(b"", ctm=(number, 0, 0, 1, 0, 0))
    with pytest.raises(cinterp.Bailout):
        cinterp.Interpreter(b"", {}, (1, 0, 0, 1, 0, 0),
                            (None, number, 0.0, 0.0, 1.0, 0.0, 0, 1.0), [], [], [])


@pytest.mark.parametrize("number", [True, _IntSubclass(1), _FloatSubclass(1.0)])
def test_initial_ctm_nonexact_numeric_types_replay_python(number):
    _compare(b"BT /F 12 Tf (subclass) Tj 0 0 m 100 0 l S",
             initial_ctm=(number, 0, 0, 1, 0, 0))


def test_integer_intermediate_overflow_bails_out_and_replays():
    # Repeated T* from inherited integer leading adds exact integer translation.
    # The second -2**53 translation exceeds the C exact range before Tj yields.
    _compare(b"BT T* T* (large integer translated) Tj",
             initial_state=(None, 12, 0, 0, 1, 2**53, 0, 1))
    native = _interpreter(b"T*")
    native.tlm = (1, 0, 2**30, 1, 0, 0)
    native.tl = 2**30
    with pytest.raises(cinterp.Bailout, match="multiplication"):
        native.next()
    native = _interpreter(b"T*")
    native.tlm = (1, 0, 0, 1, 0, 2**53)
    native.tl = -1
    with pytest.raises(cinterp.Bailout, match="addition"):
        native.next()


@pytest.mark.parametrize("reset", [
    b"BT", b"1 0 0 1 0 0 Tm", b"3 4 Td", b"3 4 TD", b"T*",
    b"Tm", b"Td", b"TD", b"(next) '", b"2 1 (next) \"",
])
def test_text_line_reset_restores_link_reliability_even_when_malformed(reset):
    prefix = b"BT /Missing 12 Tf (unknown widths) Tj /F 12 Tf "
    suffix = b" /Span BMC (reliable) Tj EMC"
    data = prefix + reset + suffix
    _compare(data)
    extractor = ContentTextExtractor.from_fonts(_fonts(), track_char_positions=True)
    page = extractor.extract_page(data)
    assert not page.fragments[0].link_geometry_reliable
    assert page.fragments[-1].link_geometry_reliable
    # A reset consumed before EOF must also restore the extractor flag, even
    # without a final text/operator yield from the native interpreter.
    _compare(prefix + reset)


def _nested_chain(depth, bailout):
    def configure(extractor):
        extractor.resources = {"level": 0}

        def load(name, resources):
            level = resources["level"] + 1
            data = (b"/N Do" if level < depth else
                    b"BT /F1 10 Tf 40 500 Td (LEAF) Tj ET")
            if bailout:
                data += b" (x) Tc"
            return (level, data, (1, 0, 0, 1, 0, 0), {"level": level},
                    {"F1": extractor._fonts["F"]}, {}, 8, None, False)

        extractor.form_loader = load
    return configure


@pytest.mark.parametrize("bailout", [True, False])
def test_nested_form_page_replay_is_linear(monkeypatch, bailout):
    depth = 16
    data = b"/N Do" + (b" (x) Tc" if bailout else b"")
    configure = _nested_chain(depth, bailout)
    expected = _extract(data, False, configure)
    calls = {"python": 0, "accelerated": 0}
    contexts = []
    for backend in calls:
        name = "_extract_page_" + backend
        original = getattr(ContentTextExtractor, name)

        def counted(self, *args, _backend=backend, _original=original, **kwargs):
            calls[_backend] += 1
            if _backend == "accelerated":
                contexts.append(args[2])
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(ContentTextExtractor, name, counted)
    actual = _extract(data, True, configure)
    assert actual == expected
    assert calls["accelerated"] == depth + 1
    assert calls["python"] == (depth + 1 if bailout else 0)
    assert sum(calls.values()) <= 2 * (depth + 1) + 2
    assert all(set(ctx) == {"active", "cache", "cache_bytes", "expanded",
                            "operators", "warned", "char_positions"} for ctx in contexts)


def test_many_distinct_forms_do_not_copy_shared_context(monkeypatch):
    count = 2000
    copies = []
    invocations = []

    class Cache(dict):
        def copy(self):
            copies.append(len(self))
            return super().copy()

    original = ContentTextExtractor._invoke_form

    def invoke(self, *args):
        context = args[-1]
        if not isinstance(context["cache"], Cache):
            context["cache"] = Cache(context["cache"])
        invocations.append(1)
        return original(self, *args)

    monkeypatch.setattr(ContentTextExtractor, "_invoke_form", invoke)

    def configure(extractor):
        def load(name, resources):
            return name, b"q Q", (1, 0, 0, 1, 0, 0), {}, {}, {}, 2, None, False
        extractor.form_loader = load

    data = b" ".join(b"/N%d Do" % i for i in range(count))
    actual = _extract(data, True, configure)
    assert actual[0][0] == "return"
    assert len(invocations) == count
    assert not copies
    assert actual == _extract(data, False, configure)


@pytest.mark.parametrize("source", ["child", "loader"])
def test_form_bailout_propagates_without_interpretation_warning(monkeypatch, source):
    def configure(extractor):
        attempts = []

        def load(name, resources):
            if source == "loader" and not attempts:
                attempts.append(1)
                raise cinterp.Bailout("loader callback")
            return (name, b"BT /F 10 Tf (LEAF) Tj ET (x) Tc", (1, 0, 0, 1, 0, 0),
                    {}, extractor._fonts, {}, 6, None, False)
        extractor.form_loader = load

    monkeypatch.setattr(content, "_CInterpreter", cinterp.Interpreter)
    monkeypatch.setattr(content, "_CInterpreterBailout", cinterp.Bailout)
    extractor = ContentTextExtractor.from_fonts(_fonts())
    configure(extractor)
    page = extractor.extract_page(b"/N Do")
    assert [f.text for f in page.fragments] == ["LEAF"]
    assert page.warnings == []
    assert extractor._form_context["warned"] == set()
    assert extractor._form_context["active"] == set()


def test_python_replay_exception_has_no_bailout_context(monkeypatch):
    monkeypatch.setattr(content, "_CInterpreter", cinterp.Interpreter)
    monkeypatch.setattr(content, "_CInterpreterBailout", cinterp.Bailout)

    def fail(self, *args):
        raise ValueError("pure replay sentinel")

    monkeypatch.setattr(ContentTextExtractor, "_extract_page_python", fail)
    with pytest.raises(ValueError) as error:
        ContentTextExtractor.from_fonts(_fonts()).extract_page(b"(x) Tc")
    assert error.value.__context__ is None


def _native_subprocess(code):
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)


def test_path_operand_overflow_bails_out_instead_of_overwriting_stack():
    _native_subprocess('''
import gc
from dochan.pdf._cinterp import Interpreter, Bailout
outputs = [[], [], []]
native = Interpreter(b"n", {}, (1,0,0,1,0,0), (None,0.,0.,0.,1.,0.,0,1.), *outputs)
operands = next(x for x in gc.get_referents(native)
                if type(x) is list and all(x is not out for out in outputs))
operands.extend([1.5] * 200)
try:
    native.next()
except Bailout:
    pass
else:
    raise AssertionError("path operand overflow was accepted")
''')


def test_font_callback_shrinking_operands_propagates_index_error():
    _native_subprocess('''
import gc
from dochan.pdf._cinterp import Interpreter
from dochan.pdf.objects import PDFName
outputs = [[], [], []]
native = Interpreter(b"Tf", {}, (1,0,0,1,0,0), (None,0.,0.,0.,1.,0.,0,1.), *outputs)
operands = next(x for x in gc.get_referents(native)
                if type(x) is list and all(x is not out for out in outputs))
class Shrink(PDFName):
    def __str__(self):
        operands.clear()
        return "F"
name = Shrink("F")
operands.extend([name, 12])
try:
    native.next()
except IndexError:
    pass
else:
    raise AssertionError("missing operand lookup error was suppressed")
''')


@pytest.mark.parametrize("field", ["ctm", "tm", "tlm"])
@pytest.mark.parametrize("bad", [True, "bad", 2**80, float("inf")])
def test_matrix_setter_failure_preserves_previous_state(field, bad):
    native = _interpreter(b"")
    original = (1, -0.0, 0, 1, 7, 8.0)
    setattr(native, field, original)
    with pytest.raises(cinterp.Bailout):
        setattr(native, field, (2, 3.0, 4, 5.0, 9, bad))
    assert _signature(getattr(native, field)) == _signature(original)


def test_heap_type_is_a_gc_referent():
    native = _interpreter(b"")
    assert any(obj is type(native) for obj in gc.get_referents(native))


def test_failed_module_initialization_releases_imported_references():
    _native_subprocess('''
import sys
sys.modules["dochan.pdf._cinterp"] = None
from dochan.pdf import paths, objects, content
del sys.modules["dochan.pdf._cinterp"]
del paths.PATH_WARNING
tracked = [paths, objects.PDFLexer, objects.PDFSyntaxError, objects.PDFName, paths.Segment]
before = [sys.getrefcount(obj) for obj in tracked]
for _ in range(10):
    try:
        import dochan.pdf._cinterp
    except AttributeError as exc:
        assert "PATH_WARNING" in str(exc)
    else:
        raise AssertionError("module initialization should fail")
assert [sys.getrefcount(obj) for obj in tracked] == before
print("references released")
''')


def test_unrepresentable_path_limit_bails_out_and_replays(monkeypatch):
    from dochan.pdf import paths
    monkeypatch.setattr(paths, "MAX_SEGMENTS", 2**100)
    with pytest.raises(cinterp.Bailout, match="path segment limit"):
        _interpreter(b"")
    _compare(b"0 0 m 100 0 l S BT /F 10 Tf (text) Tj")


@pytest.mark.skipif(os.name != "posix", reason="POSIX interval timer required")
def test_signal_handler_interrupts_inside_native_operator_loop():
    _native_subprocess('''
import signal
from dochan.pdf._cinterp import Interpreter
data = b"n " * 10000000
native = Interpreter(data, {}, (1,0,0,1,0,0), (None,0.,0.,0.,1.,0.,0,1.), [], [], [])
class Interrupted(Exception):
    pass
def handler(signum, frame):
    raise Interrupted("timer sentinel")
signal.signal(signal.SIGALRM, handler)
signal.setitimer(signal.ITIMER_REAL, 0.01)
try:
    native.next()
except Interrupted as exc:
    assert str(exc) == "timer sentinel"
    assert exc.__context__ is None
    assert 0 < native.pos < len(data), (native.pos, len(data))
else:
    raise AssertionError("timer did not interrupt next")
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
''')


def test_font_switch_and_graphics_stack_do_not_reset_link_reliability():
    data = b"BT /Missing 12 Tf (unknown) Tj /F 12 Tf q 2 Tc Q /Span BMC (continued) Tj EMC"
    _compare(data)
    extractor = ContentTextExtractor.from_fonts(_fonts(), track_char_positions=True)
    page = extractor.extract_page(data)
    assert [fragment.link_geometry_reliable for fragment in page.fragments] == [False, False]


_NONFINITE_BITS = [0x7ff0000000000000, 0xfff0000000000000,
                   0x7ff8000000000000, 0xfff8000000000000,
                   0x7ff8000000000123, 0xfff8000000000456,
                   0x7ff0000000000001, 0xfff0000000000001]


@pytest.mark.parametrize("bits", _NONFINITE_BITS)
def test_nonfinite_ieee_payloads_replay_original_python(bits):
    number = struct.unpack("!d", bits.to_bytes(8, "big"))[0]
    _compare(b"BT /F 12 Tf (nonfinite) Tj 0 0 m 100 0 l S",
             initial_ctm=(number, 0, 0, 1, 0, 0))
    _compare(b"BT T* (nonfinite leading) Tj 0 0 100 1 re f",
             initial_state=(None, 12.0, 0.0, 0.0, 1.0, number, 0, 1.0))


@pytest.mark.parametrize("data", [
    b"1.0e300 0 0 1.0e300 0 0 cm 1.0e300 0 0 1.0e300 0 0 cm BT /F 12 Tf (overflow) Tj",
    b"1.0e300 0 0 1.0e300 0 0 cm 0 0 m 1.0e300 0 l S BT /F 12 Tf (after) Tj",
    b"BT /F 12 Tf 1.0e300 0 0 1.0e300 0 0 Tm 1.0e300 1.0e300 Td (overflow) Tj",
    b"BT /F 12 Tf 1.0e300 TL T* T* (finite huge) Tj",
])
def test_finite_operands_overflow_matrix_and_path_arithmetic_replay(data):
    _compare(data)


@pytest.mark.parametrize("bits", _NONFINITE_BITS)
def test_uncertain_nonfinite_constructor_and_setters_bail_out(bits):
    number = struct.unpack("!d", bits.to_bytes(8, "big"))[0]
    with pytest.raises(cinterp.Bailout):
        _interpreter(b"", ctm=(number, 0, 0, 1, 0, 0))
    native = _interpreter(b"")
    for name in ("ctm", "tm", "tlm"):
        with pytest.raises(cinterp.Bailout):
            setattr(native, name, (1, 0, 0, 1, number, 0))
    for name in ("fs", "tc", "tw", "th", "tl", "tr", "stroke_width"):
        with pytest.raises(cinterp.Bailout):
            setattr(native, name, number)


def test_numeric_objects_rounding_and_unusual_tokens():
    rng = random.Random(81729)
    tokens = [b"-0", b"+0", b"-0.0", b"+.0", b"1e400", b"1.0e400", b"1_0.5",
              b"1.0_5", b"+.inf", b"-.nan", b"+5", b"-.5", b"5.",
              b"0.1000000000000000055511151231257827021181583404541015625",
              b"9" * 400, b"0." + b"0" * 400 + b"1"]
    for _ in range(1000):
        digits = bytes(rng.choice(b"0123456789") for _ in range(rng.randrange(1, 100)))
        split = rng.randrange(len(digits) + 1)
        sign = rng.choice([b"", b"+", b"-"])
        tokens.append(sign + digits[:split] + b"." + digits[split:])
        tokens.append(sign + digits)
    for token in tokens:
        test_next_operand_lists_match_python_object_types(token + b" (numeric window) Tj")
