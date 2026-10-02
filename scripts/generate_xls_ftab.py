"""Generate XLS function facts from the extracted Microsoft Ftab JSON table.

Usage: python -m scripts.generate_xls_ftab INPUT_JSON OUTPUT_PY [--check]
No network, third-party implementation, or corpus is needed by the generated module.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


SOURCE_URL = ('https://learn.microsoft.com/en-us/openspecs/office_file_formats/'
              'ms-xls/00b5dd7d-51ca-4938-b7b7-483fe0e5933b')


def argument_bounds(grammar):
    """Interpret the Ftab parameter grammar as a (minimum, maximum) count.

    ref and val each occupy one stack operand, not one referenced cell.
    Commas concatenate operands; '/' chooses an alternative (ref / val = 1).
    Parentheses group; [x] makes x optional; *N(x) repeats x zero to N times.
    Thus *13(val, val) contributes 0..26 operands, not 13. The explicit
    no-parameters sentence means zero. Only min == max can define PtgFunc
    arity; variable functions use PtgFuncVar's byte, never stack depth.
    Fail closed on unfamiliar syntax instead of silently generating wrong facts.
    """
    if len(grammar) > 4096:
        raise ValueError('parameter grammar too long')
    grammar = ' '.join(grammar.split())
    if grammar == 'This function takes no parameters':
        return 0, 0
    match = re.fullmatch(r'[a-z0-9-]+-params\s*=\s*(.+)', grammar)
    if not match:
        raise ValueError('invalid parameter production')
    body = re.sub(r'\s+', '', match.group(1))
    tokens = re.findall(r'ref|val|[0-9]+|[(),/\[\]*]', body)
    if ''.join(tokens) != body:
        raise ValueError('unknown parameter grammar syntax')
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else ''

    def atom(depth):
        nonlocal position
        if depth > 32:
            raise ValueError('parameter grammar nesting limit')
        token = peek()
        position += 1
        if token in ('ref', 'val'):
            return 1, 1
        if token in ('(', '['):
            low, high = alternative(depth + 1)
            if peek() != (')' if token == '(' else ']'):
                raise ValueError('unbalanced parameter grammar')
            position += 1
            return (0 if token == '[' else low), high
        if token == '*' and peek().isdigit():
            repetitions = int(peek())
            position += 1
            if repetitions > 255:
                raise ValueError('parameter repetition limit')
            _, high = atom(depth + 1)
            if repetitions * high > 255:
                raise ValueError('parameter count limit')
            return 0, repetitions * high
        raise ValueError('expected parameter atom')

    def sequence(depth):
        nonlocal position
        low, high = atom(depth)
        while peek() == ',':
            position += 1
            more_low, more_high = atom(depth)
            low, high = low + more_low, high + more_high
        if high > 255:
            raise ValueError('parameter count limit')
        return low, high

    def alternative(depth):
        nonlocal position
        low, high = sequence(depth)
        while peek() == '/':
            position += 1
            other_low, other_high = sequence(depth)
            low, high = min(low, other_low), max(high, other_high)
        return low, high

    result = alternative(0)
    if position != len(tokens):
        raise ValueError('trailing parameter grammar')
    return result


def parse_rows(rows):
    """Return id -> (official name, normalized production, fixed arity or None)."""
    entries = {}
    pending = None
    for row in rows:
        if len(row) == 2 and re.fullmatch(r'0x[0-9A-Fa-f]+', row[0]):
            if pending is not None:
                raise ValueError('missing parameter row')
            index, name = int(row[0], 16), row[1]
            if index > 0x7fff or index in entries:
                raise ValueError('invalid or duplicate Ftab id')
            if not re.fullmatch(r'[A-Z][A-Z0-9.]*|User Defined Function', name):
                raise ValueError('invalid Ftab name')
            pending = index, name
        elif pending is not None and len(row) == 2 and not row[0]:
            index, name = pending
            grammar = ' '.join(row[1].split())
            production = name.lower().replace('.', '-').replace(' ', '-') + '-params'
            if grammar != 'This function takes no parameters' and not grammar.startswith(production + ' ='):
                raise ValueError('parameter row does not match function name')
            low, high = argument_bounds(grammar)
            entries[index] = name, grammar, low if low == high else None
            pending = None
        elif pending is not None or entries:
            raise ValueError('unexpected Ftab row')
        # The extracted JSON starts with the bit-field diagram and table header.
    if pending is not None or not entries:
        raise ValueError('incomplete or empty Ftab table')
    return entries


def render_module(entries, digest):
    lines = [
        '"""Generated facts from [MS-XLS] 2.5.198.17 Ftab; do not edit by hand.',
        '', 'Source: ' + SOURCE_URL,
        'Regenerate: python -m scripts.generate_xls_ftab INPUT_JSON OUTPUT_PY',
        'Input JSON SHA-256: ' + digest,
        '"""', '',
        '# Includes the UDF sentinel as an official label, not a callable name.',
        'FUNCTION_NAMES = {',
    ]
    for index, (name, _, _) in sorted(entries.items()):
        lines.append('    0x%04X: %r,' % (index, name))
    lines.extend(['}', '',
                  '# ref/val = one operand; commas add; / chooses; [] is optional;',
                  '# *N(group) repeats 0..N times. Include only min == max.',
                  '# Variable functions take the arity from PtgFuncVar.',
                  '# No compatibility overrides belong in this specification data.',
                  'FIXED_ARGUMENT_COUNTS = {'])
    for index, (name, grammar, count) in sorted(entries.items()):
        if count is not None:
            lines.append('    0x%04X: %d,  # %s: %s' % (index, count, name, grammar))
    lines.extend(['}', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.source.stat().st_size > 2 * 1024 * 1024:
        parser.error('Ftab JSON exceeds 2 MiB')
    raw = args.source.read_bytes()
    entries = parse_rows(json.loads(raw))
    rendered = render_module(entries, hashlib.sha256(raw).hexdigest())
    if args.check:
        if args.output.read_text(encoding='utf-8') != rendered:
            parser.error('generated module is out of date')
    else:
        args.output.write_text(rendered, encoding='utf-8')
    print('%d functions; %d fixed arities' % (
        len(entries), sum(entry[2] is not None for entry in entries.values())))


if __name__ == '__main__':
    main()
