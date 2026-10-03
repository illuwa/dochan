"""Summarize public XLS formula restoration without saving document output."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct

from dochan import cfb
from dochan.office_binary.xls import _iter_records
from dochan.utils.bounded_io import MAX_OLE_STREAM_SIZE, read_ole_stream
from scripts.probe_xls_formula_pairs import split_formula
from scripts.probe_xls_tokens import inspect_file, public_paths


_DDE_FORMULA = re.compile(
    r"[A-Za-z0-9_.]+\|(?:'(?:[^']|'')*'|[A-Za-z0-9_.]+)!"
    r"(?:'(?:[^']|'')*'|[A-Za-z0-9_.]+)")


def raw_table_cells(path):
    with cfb.OleFileIO(str(path)) as ole:
        stream = 'Workbook' if ole.exists('Workbook') else 'Book'
        data = read_ole_stream(ole, stream, max_bytes=MAX_OLE_STREAM_SIZE)
    count = 0
    for _, kind, payload in _iter_records(data):
        if (kind == 6 and len(payload) >= 27
                and struct.unpack_from('<H', payload, 20)[0] == 5
                and payload[22] == 2):
            count += 1
    return count


def probe(root):
    totals = Counter()
    causes = Counter()
    targeted = {}
    dde = set()
    failures = []
    for path in public_paths(root):
        relative = str(path.relative_to(root))
        try:
            result = inspect_file(path)
        except Exception as exc:
            failures.append({'file': relative, 'error': type(exc).__name__})
            continue
        totals['files'] += 1
        totals['raw_formula_cells'] += result['raw_formula_cells']
        totals['retained_formulas'] += result['retained_formulas']
        totals['omitted'] += len(result['omitted'])
        causes.update(item['root_cause'] for item in result['omitted'])
        table_count = 0
        dde_count = 0
        for _, _, display in result['cells']:
            _, expression = split_formula(display)
            if expression.startswith('TABLE('):
                table_count += 1
            if _DDE_FORMULA.fullmatch(expression):
                dde_count += 1
                dde.add(expression)
        try:
            raw_tables = raw_table_cells(path)
        except (cfb.CFBError, ValueError, OSError):
            raw_tables = 0
            totals['raw_table_unreadable_files'] += 1
        if table_count or dde_count or raw_tables:
            targeted[relative] = {
                'table_cells': table_count, 'dde_cells': dde_count,
                'raw_table_cells': raw_tables,
                'omitted': len(result['omitted']),
                'markdown_sha256': result['markdown_sha256'],
                'json_sha256': result['json_sha256'],
            }
    return {'totals': dict(totals), 'omitted_causes': dict(causes),
            'targeted_files': targeted, 'dde_unique_formulas': sorted(dde),
            'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.corpus)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'dde_unique_formulas'}, ensure_ascii=False))
        print('dde_unique_count=%d' % len(result['dde_unique_formulas']))
    else:
        print(rendered)
    return bool(result['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
