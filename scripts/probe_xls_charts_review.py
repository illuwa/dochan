"""공개 XLS 차트 전부를 xlrd 셀 정답과 비교한다. 코퍼스는 읽기만 한다.

실행: /usr/bin/python3 -m scripts.probe_xls_charts_review CORPUS --output JSON
      --oracle-python corpus/.venv-oracle/bin/python
차트 참조는 원시 BRAI 토큰에서 독립적으로 좌표를 읽는다. 숫자는 Excel 표시
서식의 반올림 오차를 별도로 기록하며, 0으로 바뀐 비영 값은 허용하지 않는다.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace

from dochan import cfb

from dochan.model.table import Table
from dochan.office_binary import xls, xls_chart


_ORACLE = r"""
import json, sys, xlrd
book = xlrd.open_workbook(sys.argv[1], on_demand=True)
result = {}
for sheet in book.sheets():
    result[sheet.name] = {'rows': sheet.nrows, 'cols': sheet.ncols,
        'cells': [[r, c, sheet.cell_value(r, c), sheet.cell_type(r, c)]
                  for r in range(sheet.nrows) for c in range(sheet.ncols)
                  if sheet.cell_type(r, c) not in (0, 6)]}
print(json.dumps(result))
"""


class OracleBook:
    def __init__(self, path, python):
        process = subprocess.run([str(python), '-c', _ORACLE, str(path)],  # nosemgrep: dangerous-subprocess-use-audit
                                 capture_output=True, text=True, timeout=60, check=True)
        self.sheets = {}
        for name, sheet in json.loads(process.stdout).items():
            cells = {(r, c): SimpleNamespace(value=value, ctype=ctype)
                     for r, c, value, ctype in sheet['cells']}
            self.sheets[name] = SimpleNamespace(nrows=sheet['rows'], ncols=sheet['cols'],
                cell=lambda r, c, cells=cells: cells.get((r, c), SimpleNamespace(value='', ctype=0)))

    def sheet_names(self):
        return list(self.sheets)

    def sheet_by_name(self, name):
        return self.sheets[name]

    def release_resources(self):
        self.sheets.clear()


def records(data):
    pos = 0
    while pos + 4 <= len(data):
        sid, size = struct.unpack_from('<HH', data, pos)
        pos += 4
        if pos + size > len(data):
            return
        yield sid, data[pos:pos + size]
        pos += size


def chart_metadata(items):
    series = []
    stack = []
    pending = None
    for sid, data in items:
        if sid == 0x1033:
            stack.append(pending)
            pending = None
            continue
        if sid == 0x1034:
            if stack:
                stack.pop()
            pending = None
            continue
        context = next((x for x in reversed(stack) if x is not None), None)
        pending = None
        if sid == 0x1003:
            pending = {'references': {}, 'auxiliary': False}
            series.append(pending)
        elif sid == 0x1025:
            pending = 'text'
        elif sid == 0x104a and isinstance(context, dict):
            context['auxiliary'] = True
        elif sid == 0x1051 and isinstance(context, dict) and len(data) >= 8 and data[1] == 2:
            size = struct.unpack_from('<H', data, 6)[0]
            context['references'][data[0]] = data[8:8 + size]
    return [s for s in series if not s['auxiliary']]


def oracle_reference(tokens, book, logical_names, current_sheet, xtis, internal):
    if not tokens:
        return None
    op = ((tokens[0] & 31) | 32) if tokens[0] >= 32 else tokens[0]
    pos = 1
    sheet = current_sheet
    if op in (0x3a, 0x3b):
        if len(tokens) < 3:
            return None
        xti = struct.unpack_from('<H', tokens, 1)[0]
        pos = 3
        if xti >= len(xtis):
            return None
        entry = xtis[xti]
        if len(entry) == 3:
            supbook, first, last = entry
            if supbook not in (internal or set()):
                return None
        else:
            first, last = entry
        if first != last:
            return None
        sheet = first
    if op in (0x24, 0x3a) and len(tokens) == pos + 4:
        r1, c1 = struct.unpack_from('<HH', tokens, pos)
        r2, c2 = r1, c1
    elif op in (0x25, 0x3b) and len(tokens) == pos + 8:
        r1, r2, c1, c2 = struct.unpack_from('<4H', tokens, pos)
    else:
        return None
    c1 &= 255
    c2 &= 255
    if not 0 <= sheet < len(logical_names) or logical_names[sheet] not in book.sheet_names():
        return None
    tab = book.sheet_by_name(logical_names[sheet])
    values = {}
    for r in range(r1, min(r2 + 1, tab.nrows)):
        for c in range(c1, min(c2 + 1, tab.ncols)):
            cell = tab.cell(r, c)
            if cell.ctype not in (0, 6) and cell.value != '':
                values[(r - r1) * (c2 - c1 + 1) + c - c1] = (cell.value, cell.ctype)
    return values


def compare(actual, expected):
    value, ctype = expected
    if ctype == 5:
        error_names = {0: '#NULL!', 7: '#DIV/0!', 15: '#VALUE!', 23: '#REF!',
                       29: '#NAME?', 36: '#NUM!', 42: '#N/A'}
        return 'exact' if actual == error_names.get(value, '#ERROR!') else 'mismatch'
    if ctype == 4:
        return 'exact' if actual == ('TRUE' if value else 'FALSE') else 'mismatch'
    if ctype not in (2, 3):
        return 'exact' if actual == str(value) else 'mismatch'
    actual = actual.strip().replace(',', '').replace('$', '').replace('€', '').replace('£', '')
    if actual.startswith('(') and actual.endswith(')'):
        actual = '-' + actual[1:-1]
    factor = 100 if '%' in actual else 1
    actual = actual.rstrip('%').strip()
    try:
        numeric = float(actual) / factor
    except ValueError:
        if ctype == 3:
            return 'date_display_unverified'
        return 'mismatch'
    if math.isclose(numeric, value, rel_tol=1e-9, abs_tol=1e-10):
        return 'exact'
    if numeric == 0 and value != 0:
        return 'mismatch'
    digits = len(actual.split('.', 1)[1]) if '.' in actual else 0
    if abs(numeric - value) <= 0.5000001 * 10 ** -digits / factor:
        return 'display_rounding'
    return 'mismatch'


def inspect(path, oracle_python):
    with cfb.OleFileIO(str(path)) as ole:
        stream = 'Workbook' if ole.exists('Workbook') else 'Book'
        data = ole.openstream(stream).read()
    all_records = list(records(data))
    count = sum(sid == 0x0809 and len(payload) >= 4 and struct.unpack_from('<H', payload, 2)[0] == 0x20
                for sid, payload in all_records)
    if not count:
        return None
    names = []
    for sid, payload in all_records:
        if sid == 0x85 and len(payload) >= 8:
            n, flags = payload[6:8]
            names.append(payload[8:8 + n * (2 if flags & 1 else 1)].decode('utf-16le' if flags & 1 else 'latin1'))
    book = OracleBook(path, oracle_python)
    stats = Counter()
    mismatches = []
    nonzero_examples = []
    unavailable_references = []
    original = xls_chart._parse_chart

    def checked(items, sheets, xtis, current_sheet, source_path, sheet_name, errors, budget,
                internal_supbooks=None, formula_values=None):
        result = original(items, sheets, xtis, current_sheet, source_path, sheet_name, errors, budget,
                          internal_supbooks, formula_values)
        metadata = chart_metadata(items)
        tables = [element for element in result if isinstance(element, Table)]
        stats['charts'] += 1
        stats['auxiliary_excluded'] += sum(sid == 0x104a for sid, _ in items)
        if not tables:
            stats['without_table'] += 1
            return result
        table = [[cell.text for cell in row] for row in tables[0].rows]
        long_table = table[0] == ['Series', 'X', 'Y']
        long_offset = 1
        for index, meta in enumerate(metadata):
            ys = oracle_reference(meta['references'].get(1), book, names, current_sheet, xtis, internal_supbooks)
            xs = oracle_reference(meta['references'].get(2), book, names, current_sheet, xtis, internal_supbooks)
            if ys is None:
                stats['series_without_internal_reference'] += 1
                unavailable_references.append({'chart': source_path, 'series': index,
                    'tokens': bytes(meta['references'].get(1, b'')).hex()})
                continue
            stats['series_with_internal_reference'] += 1
            indexes = sorted(set(ys) | set(xs or {}))
            for point in sorted(ys):
                offset = indexes.index(point)
                try:
                    actual = table[long_offset + offset][2] if long_table else table[1 + offset][index + 1]
                except IndexError:
                    actual = '<missing>'
                verdict = compare(actual, ys[point])
                stats[verdict] += 1
                stats['reference_points'] += 1
                if ys[point][1] in (2, 3) and ys[point][0] != 0:
                    stats['nonzero_reference_points'] += 1
                    if len(nonzero_examples) < 6:
                        nonzero_examples.append({'chart': source_path, 'expected': ys[point][0],
                                                 'actual': actual, 'verdict': verdict})
                    if verdict in ('exact', 'display_rounding'):
                        stats['nonzero_matched'] += 1
                if verdict == 'mismatch':
                    mismatches.append({'chart': source_path, 'series': index, 'point': point,
                                       'expected': ys[point][0], 'actual': actual})
            long_offset += len(indexes)
        return result

    xls_chart._parse_chart = checked
    try:
        doc = xls.parse_biff_workbook(data)
    finally:
        xls_chart._parse_chart = original
        book.release_resources()
    return {'file': path.name, 'chart_bofs': count, 'stats': dict(stats), 'mismatches': mismatches,
            'errors': doc.errors, 'nonzero_examples': nonzero_examples,
            'unavailable_references': unavailable_references}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--oracle-python', type=Path, required=True)
    args = parser.parse_args()
    output = []
    failures = []
    for path in sorted(args.corpus.glob('*.xls')):
        try:
            result = inspect(path, args.oracle_python)
            if result:
                output.append(result)
                print(path.name, result['stats'], flush=True)
        except Exception as error:
            failures.append({'file': path.name, 'error': str(error)})
    totals = Counter()
    for result in output:
        totals.update(result['stats'])
    payload = {'files': len(output), 'totals': dict(totals), 'results': output, 'scan_failures': failures}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(output), 'totals': dict(totals), 'scan_failures': len(failures)}))


if __name__ == '__main__':
    main()
