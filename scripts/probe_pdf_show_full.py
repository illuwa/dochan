"""Public real-font differential probe: all Fragment fields, types and IEEE bits.

Captures glyph operands using the Python reference path, then drives complete
native Tj/TJ/quote operators with mutations. Stores counts only, never PDF text.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct

from dochan import Dochan
from dochan.pdf import content
from dochan.pdf import _cinterp
from dochan.pdf._show_table import font_table


def signature(value):
    if isinstance(value, float):
        return type(value).__name__, struct.pack('!d', value).hex()
    if isinstance(value, dict):
        return type(value).__name__, tuple((k, signature(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return type(value).__name__, tuple(signature(v) for v in value)
    return type(value).__name__, value


def run(sample, native, op, track, budget, mode, width):
    raw, tm, font, fs, tc, tw, th, ctm, stack, reliable = sample
    owner = content.ContentTextExtractor.from_fonts({}, track_char_positions=track)
    owner._marked_stack = list(stack)
    owner._marked_overflow = 1 if budget == 7 else 0
    owner._link_position_reliable = reliable
    owner._form_context = {'char_positions': budget}
    if op in (b"'", b'"'):
        owner._link_position_reliable = True
    frags = []
    operands = [raw] if op != b'TJ' else [[raw, -31.25, raw, 0, b' ']]
    if op == b'"':
        operands = [2.5, -0.0, raw]
    tlm = tm
    state = (font, fs, tc, tw, th, 14.0, mode, width)
    def serial(value):
        if isinstance(value, bytes):
            return b'<' + value.hex().encode() + b'>'
        if isinstance(value, list):
            return b'[' + b' '.join(serial(v) for v in value) + b']'
        return repr(value).encode()
    yielded = 0
    try:
        if native:
            engine = _cinterp.Interpreter(b' '.join(serial(v) for v in operands) + b' ' + op,
                                          {}, ctm, state, [], [], [], owner, frags,
                                          content.Fragment, font_table)
            engine.tm = tm
            engine.tlm = tlm
            event = engine.next()
            if event is not None:
                yielded = 1
                tm, tlm, tc, tw = owner._text_operator(
                    op, operands, tm, tlm, font, fs, tc, tw, th, 14.0, mode, width, frags, ctm)
            else:
                tm, tlm, tc, tw = engine.tm, engine.tlm, engine.tc, engine.tw
        else:
            tm, tlm, tc, tw = owner._text_operator(
                op, operands, tm, tlm, font, fs, tc, tw, th, 14.0, mode, width, frags, ctm)
        result = ('return', signature((tm, tlm, tc, tw)), signature([vars(f) for f in frags]))
    except _cinterp.Bailout:
        return run(sample, False, op, track, budget, mode, width)[0], 2
    except Exception as exc:
        result = ('raise', type(exc).__name__)
    return (result, signature(owner._form_context), owner._link_position_reliable), yielded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+')
    parser.add_argument('--cases', type=int, default=100000)
    parser.add_argument('--documents', type=int, default=300)
    args = parser.parse_args()
    binary_hash = hashlib.sha256(Path(_cinterp.__file__).read_bytes()).hexdigest()
    paths = sorted({p for root in args.roots for p in Path(root).rglob('*.pdf')})
    rng = random.Random(20261101)
    paths = rng.sample(paths, min(args.documents, len(paths)))
    samples = []
    original = content.ContentTextExtractor._show
    engine = content._CInterpreter
    content._CInterpreter = None
    per_document = [0]
    capture_counts = Counter()
    table_cache = {}
    def capture(self, raw, tm, font, fs, tc, tw, th, frags, ctm):
        decoder = font.decode if font else None
        bound = getattr(decoder, '__self__', None)
        kind = type(bound).__name__ if bound is not None else getattr(decoder, '__name__', 'missing')
        key = id(font)
        if key not in table_cache:
            table_cache[key] = (font, bool(font_table(font)) if font else False)
        supported = table_cache[key][1]
        capture_counts[kind + (':table' if supported else ':python')] += 1
        if raw and len(raw) <= 256 and per_document[0] < 100:
            samples.append((raw, tm, font, fs, tc, tw, th, ctm,
                            tuple(self._marked_stack), self._link_position_reliable))
            per_document[0] += 1
        return original(self, raw, tm, font, fs, tc, tw, th, frags, ctm)
    content.ContentTextExtractor._show = capture
    failures = 0
    try:
        for path in paths:
            per_document[0] = 0
            try:
                Dochan(path)
            except Exception:
                failures += 1
    finally:
        content.ContentTextExtractor._show = original
        content._CInterpreter = engine
    assert samples, 'No real operands captured'
    counts = Counter()
    for index in range(args.cases):
        sample = list(samples[index % len(samples)])
        if index >= len(samples):
            raw = sample[0]
            sample[0] = rng.choice([raw, raw[::-1], raw[:rng.randrange(len(raw) + 1)], raw + b' ', b'\x00' + raw])
            for slot in (3, 4, 5, 6):
                if rng.random() < 0.35:
                    sample[slot] = rng.choice([0, 1, -1, -0.0, 0.0, 0.75, -3.5, 1e-6, 999.125])
            if rng.random() < 0.5:
                sample[1] = tuple(rng.choice([0, 1, -0.0, 0.125, -2.5]) for _ in range(6))
            if rng.random() < 0.25:
                sample[7] = tuple(rng.choice([0, 1, -0.0, 0.125, -2.5]) for _ in range(6))
        op = (b'Tj', b'TJ', b"'", b'"')[index % 4]
        options = (op, bool(index % 3), (200000, 0, 7)[index % 3], index % 8, (0.0, 0.5)[index % 2])
        expected, _ = run(sample, False, *options)
        actual, yielded = run(sample, True, *options)
        if actual != expected:
            def difference(a, b, path=()):
                if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
                    for j, (x, y) in enumerate(zip(a, b)):
                        if x != y:
                            return difference(x, y, path + (j,))
                return path, repr(a)[:100], repr(b)[:100]
            raise AssertionError((index, difference(expected, actual), sample[1], sample[3:8], options))
        counts[('native', 'yield', 'bailout')[yielded]] += 1
    assert hashlib.sha256(Path(_cinterp.__file__).read_bytes()).hexdigest() == binary_hash
    print(json.dumps({'native_sha256': binary_hash, 'documents': len(paths), 'document_failures': failures,
                      'real_operands': len(samples), 'cases': args.cases,
                      'execution': counts, 'real_glyph_coverage': capture_counts,
                      'differences': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
