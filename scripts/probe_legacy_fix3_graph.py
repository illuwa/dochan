"""Independently compare public Graph datasheets with rendered chart tables.

Run: /usr/bin/python3 -m scripts.probe_legacy_fix3_graph CORPUS --output FILE
Expected body cells come directly from Graph Number/Label records and the
included rectangular datasheet selection, never the normalized BIFF cache.
All stored Graph objects (including historical PPT storage records) are counted.
"""
import argparse
import io
import json
from pathlib import Path
import struct
import zlib

import olefile

from dochan.office_binary.ole_objects import parse_embedded_chart


FILES = ('37625.ppt', '42520.ppt', 'bug61881.ppt', '53446.ppt')
# Observed nonrectangular selection records; keep them in the denominator.
EXPECTED_FALLBACKS = {('37625.ppt', 116371), ('37625.ppt', 428118), ('53446.ppt', 454115)}


def ppt_atoms(data, start=0, end=None, depth=0):
    if depth > 64:
        raise ValueError('PPT nesting limit')
    end = len(data) if end is None else end
    while start + 8 <= end:
        flags, kind, size = struct.unpack_from('<HHI', data, start)
        stop = start + 8 + size
        if stop > end:
            raise ValueError('PPT atom outside container')
        if flags & 15 == 15:
            yield from ppt_atoms(data, start + 8, stop, depth + 1)
        else:
            yield start, kind, flags >> 4, data[start + 8:stop]
        start = stop


def graph_objects(path):
    with olefile.OleFileIO(str(path)) as outer:
        data = outer.openstream('PowerPoint Document').read()
    for offset, kind, instance, payload in ppt_atoms(data):
        if kind != 0x1011:
            continue
        if instance == 1:
            size = struct.unpack_from('<I', payload)[0]
            if size > 16 * 1024 * 1024:
                raise ValueError('PPT object byte limit')
            inflater = zlib.decompressobj()
            raw = inflater.decompress(payload[4:], size + 1)
            if len(raw) != size or inflater.unconsumed_tail:
                raise ValueError('PPT object size mismatch')
        elif instance == 0:
            raw = payload
        else:
            continue
        with olefile.OleFileIO(io.BytesIO(raw)) as inner:
            if not inner.exists('\x01CompObj'):
                continue
            comp = inner.openstream('\x01CompObj').read()
            if b'MSGraph.Chart.8\0' not in comp:
                continue
            name = next((n for n in ('Workbook', 'Book') if inner.exists(n)), None)
            if name:
                yield offset, inner.openstream(name).read()


def datasheet(data):
    cells = {}
    selection = {}
    orientation = None
    offset = 0
    codepage = 1252
    in_chart = False
    while offset + 4 <= len(data):
        kind, size = struct.unpack_from('<HH', data, offset)
        if kind == size == 0:
            break
        payload = data[offset + 4:offset + 4 + size]
        if len(payload) != size:
            raise ValueError('Truncated Graph record')
        offset += 4 + size
        if kind == 0x809:
            in_chart = struct.unpack_from('<H', payload, 2)[0] == 0x8000
        if kind == 0x42:
            codepage = struct.unpack_from('<H', payload)[0]
        elif kind in (0x1053, 0x1054) and in_chart:
            if len(payload) != 4:
                raise ValueError('Nonrectangular Graph selection')
            first, stop = struct.unpack('<HH', payload)
            if first != 0:
                raise ValueError('Nonprefix Graph selection')
            selection[kind] = stop
        elif kind == 0x1055:
            orientation = payload[0]
        elif kind in (3, 4):
            row, column = struct.unpack_from('<HH', payload)
            if kind == 3:
                value = struct.unpack_from('<d', payload, 7)[0]
                value = str(int(value)) if value.is_integer() else str(value)
            else:
                count = struct.unpack_from('<H', payload, 7)[0]
                raw = payload[9:9 + count]
                codec = 'ascii' if all(b < 128 for b in raw) else 'cp%d' % codepage
                value = raw.decode(codec)
            cells[row, column] = value
    if orientation not in (0, 1) or len(selection) != 2:
        raise ValueError('Incomplete Graph selection')
    series = range(1, selection[0x1053 if orientation else 0x1054])
    points = range(1, selection[0x1054 if orientation else 0x1053])

    def cell(axis, point, default=''):
        return cells.get((axis, point) if orientation else (point, axis), default)

    names = [cell(axis, 0) for axis in series]
    body = [[cell(0, point, str(point))] + [cell(axis, point) for axis in series] for point in points]
    return names, body


def probe(root):
    checks = []
    for name in FILES:
        path = root / 'poi-src/test-data/slideshow' / name
        for offset, data in graph_objects(path):
            errors = []
            elements = parse_embedded_chart(data, errors, graph=True)
            tables = [e for e in elements if hasattr(e, 'rows')]
            actual = [[c.text for c in row] for row in tables[0].rows] if len(tables) == 1 else []
            try:
                names, expected = datasheet(data)
                basis_error = None
            except ValueError as exc:
                names, expected = [], []
                basis_error = str(exc)
            columns_match = bool(actual) and len(actual[0]) == len(names) + 1
            body_match = bool(actual) and actual[1:] == expected
            # Saved SeriesText can override a datasheet heading; only populated
            # headings are checked here, and any difference remains reviewable.
            headings_match = bool(actual) and all(not wanted or wanted == got
                                                  for wanted, got in zip(names, actual[0][1:]))
            checks.append(dict(file=name, offset=offset, expected_series=len(names),
                               expected_points=len(expected), expected_names=names,
                               expected_body=expected, actual=actual, errors=errors,
                               columns_match=columns_match, body_match=body_match,
                               headings_match=headings_match,
                               passed=basis_error is None and columns_match and body_match and headings_match,
                               basis_error=basis_error,
                               fallback=not actual))
    unsupported = {(c['file'], c['offset']) for c in checks if c['fallback']
                   and c['basis_error'] == 'Nonrectangular Graph selection'}
    coverage_match = (len(checks) == 34 and sum(c['passed'] for c in checks) == 31
                      and sum(c['fallback'] for c in checks) == 3
                      and unsupported == EXPECTED_FALLBACKS)
    return dict(coverage_match=coverage_match, total=len(checks), matched=sum(c['passed'] for c in checks),
                fallback=sum(c['fallback'] for c in checks),
                body_cells=sum(sum(len(row) for row in c['expected_body']) for c in checks),
                checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.corpus)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'checks'}))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['coverage_match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
