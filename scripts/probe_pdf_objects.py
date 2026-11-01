"""Deterministic document-object differential fuzzing (public PDF inputs only)."""
import argparse
import json
from pathlib import Path
import random
import re
import struct

from dochan.pdf import objects


def freeze(value):
    if isinstance(value, float):
        return ('float', struct.pack('!d', value).hex())
    if isinstance(value, dict):
        return ('dict', tuple((freeze(k), freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(map(freeze, value)))
    if isinstance(value, objects.PDFStream):
        return ('PDFStream', freeze(value.dictionary), value.raw)
    return (type(value).__name__, value)


def outcome(cls, data, pos, skip, method):
    lexer = cls(data, pos)
    lexer.skip_array_operators = skip
    try:
        value = ('ok', freeze(getattr(lexer, method)()))
    except Exception as error:
        value = ('error', type(error).__name__, str(error))
    return value, lexer.pos, lexer._depth, lexer.stray_closers


def indirect_outcome(function, data, pos):
    recovered = []
    try:
        value = ('ok', freeze(function(data, pos, recovered=recovered)))
    except Exception as error:
        value = ('error', type(error).__name__, str(error))
    return value, recovered


def seeds(paths):
    result = [b'<< /A [1 0 R (a\\777) /a#ff] /B true >>', b'/#+1#-1#zz',
              b'[1.0 0 R]', b'(a(b)c\\\r\nd)', b'<00\x0bff>', b'1_000 0 R',
              b'1' * 4500, b'[' * 70 + b'0' + b']' * 70]
    for path in paths:
        data = Path(path).read_bytes()
        for match in list(re.finditer(rb'\d+\s+\d+\s+obj\b', data))[:100]:
            result.append(data[match.end():match.end() + 768])
    return result


def fuzz(paths, count, seed):
    rng = random.Random(seed)
    pool = seeds(paths)
    stats = {'cases': count, 'seeds': len(pool), 'direct_c_success': 0,
             'direct_c_bailout': 0, 'indirect': 0, 'batch': 0, 'differences': 0}
    special = [b'\x00\t%hi\r\n', b'#ff', b'#-1', b'\\777', b'\r\n', b'>>',
               b'<< /URI (x)) /A ', b'[' * 66, b'\xff', b'1.2e+5', b'1_2', b'\v']
    for index in range(count):
        data = rng.choice(pool)
        variant = index % 8
        if variant == 1:
            data = data[:rng.randrange(len(data) + 1)]
        elif variant == 2:
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(100)))
        elif variant == 3:
            at = rng.randrange(len(data) + 1)
            data = data[:at] + rng.choice(special) + data[at:]
        elif variant == 4:
            data = b'[' + data + b']'
        elif variant == 5:
            data = b'<< /X ' + data + b' /Y (x)) >>'
        elif variant == 6:
            data = data.replace(b'\n', b'\r\n').replace(b' ', b'\x00%foo\n')
        elif variant == 7:
            shuffled = bytearray(data[:256])
            rng.shuffle(shuffled)
            data = bytes(shuffled)
        pos = rng.choice([0, 0, 0, -1, len(data), len(data) + 1])
        skip = bool(index % 2)
        method = 'parse_object'
        before = outcome(objects._PythonPDFLexer, data, pos, skip, method)
        after = outcome(objects.PDFLexer, data, pos, skip, method)
        if before != after:
            raise AssertionError((index, data, pos, skip, method, before, after))
        if objects._cobjects is not None and pos == 0 and method == 'parse_object':
            try:
                objects._cobjects.parse(data, pos, 0, skip, 64, 100000)
                stats['direct_c_success'] += 1
            except objects._cobjects.Bailout:
                stats['direct_c_bailout'] += 1
        if index % 10 == 0:
            indirect = b'1 0 obj ' + data + b' endobj'
            before = indirect_outcome(objects._parse_indirect_python, indirect, 0)
            after = indirect_outcome(objects.parse_indirect_object, indirect, 0)
            if before != after:
                raise AssertionError(('indirect', index, data, before, after))
            stats['indirect'] += 1
        if index % 10 == 1:
            batch_data = b'1 0 1 2 2 0 3 4 ' + data
            pairs, parsed = objects.parse_object_stream(batch_data, 4, 16)
            assert pairs == [(1, 0), (1, 2), (2, 0), (3, 4)]
            for offset, entry in parsed.items():
                if entry is None:
                    continue
                lexer = objects._PythonPDFLexer(batch_data, 16 + offset)
                expected = lexer.parse_object()
                assert freeze(entry) == freeze((expected, lexer.stray_closers)), (index, offset)
            stats['batch'] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths', type=Path, help='JSON list of public PDF paths')
    parser.add_argument('--count', type=int, default=200000)
    parser.add_argument('--seed', type=int, default=20261101)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    paths = json.loads(args.paths.read_text()) if args.paths else []
    stats = fuzz(paths, args.count, args.seed)
    text = json.dumps(stats, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
