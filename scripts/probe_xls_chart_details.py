"""공개 XLS 코퍼스의 차트 표와 서식 레코드를 JSON으로 기록한다."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
import struct

from dochan import cfb as olefile  # olefile 호환 API 의 자체 [MS-CFB] 리더

from dochan.model.table import Table
from dochan.office_binary.xls import parse_biff_workbook
from dochan.office_binary.xls_chart import _records, _unicode_text


def snapshot(roots):
    result = {}
    for root in roots:
        root = Path(root)
        for path in sorted(root.rglob('*.xls')):
            records = []
            try:
                with olefile.OleFileIO(str(path)) as ole:
                    name = 'Workbook' if ole.exists('Workbook') else 'Book'
                    data = ole.openstream(name).read()
                records = list(_records(data, []))
                if not any(sid == 0x0809 and len(payload) >= 4
                           and struct.unpack_from('<H', payload, 2)[0] == 0x20
                           for sid, payload in records):
                    continue
                doc = parse_biff_workbook(data)
                tables = []
                for section in doc.sections:
                    for element in section.elements:
                        if not isinstance(element, Table) or not element.rows:
                            continue
                        provenance = element.rows[0][0].provenance
                        if provenance and '#chart' in (provenance.path or ''):
                            tables.append({'path': provenance.path,
                                           'caption': element.caption_text,
                                           'rows': [[cell.text for cell in row] for row in element.rows]})
                result[str(path.relative_to(root)) + '@' + str(root)] = {
                    'tables': tables,
                    'formats': [list(struct.unpack_from('<BBHHH', payload))
                                for sid, payload in records if sid == 0x1051 and len(payload) >= 8],
                    # Preserve ordered raw group/series records for independent
                    # SerToCrt -> ChartFormat proof, without external source code.
                    'structure_records': [
                        {'record_index': index, 'sid': hex(sid), 'payload_hex': payload.hex()}
                        for index, (sid, payload) in enumerate(records)
                        if sid in (0x0809, 0x000a, 0x1003, 0x1014, 0x1045,
                                   0x1017, 0x101b, 0x100d, 0x1027)],
                    'format_codes': {str(struct.unpack_from('<H', payload)[0]): _unicode_text(payload, 2)
                                     for sid, payload in records if sid == 0x041e and len(payload) >= 5},
                    'errors': list(doc.errors),
                }
            except Exception as exc:
                # Unreadable/encrypted non-chart files are excluded, not interpreted.
                if any(sid == 0x0809 and len(payload) >= 4
                       and struct.unpack_from('<H', payload, 2)[0] == 0x20
                       for sid, payload in records):
                    result[str(path)] = {'error': str(exc)}
    return result


def _value_series(table):
    rows = table['rows']
    result = defaultdict(list)
    if rows[0][:1] == ['Series'] and 'Y' in rows[0]:
        column = rows[0].index('Y')
        for row in rows[1:]:
            if row[column]:
                result[row[0]].append(row[column])
    else:
        for column, name in enumerate(rows[0][1:], 1):
            for row in rows[1:]:
                if row[column]:
                    result[name].append(row[column])
    return result


def _number(value):
    try:
        return float(value.replace(',', '').rstrip('%')) / (100 if value.endswith('%') else 1)
    except ValueError:
        return value


def compare(before, after):
    """표의 장단 형식과 백분율 표시를 정규화하고 계열별 비어 있지 않은 Y를 비교한다."""
    mismatches = []
    value_cells = 0
    before = {key: value for key, value in before.items() if 'tables' in value}
    after = {key: value for key, value in after.items() if 'tables' in value}
    if before.keys() != after.keys():
        mismatches.append({'file_sets_differ': True})
    for path, old in before.items():
        new = after.get(path, {'tables': []})
        if len(old['tables']) != len(new['tables']):
            mismatches.append({'path': path, 'chart_counts_differ': True})
        for left, right in zip(old['tables'], new['tables']):
            previous, current = _value_series(left), _value_series(right)
            if previous.keys() != current.keys():
                mismatches.append({'path': path, 'chart': left['path'], 'series_differ': True})
            for name, values in previous.items():
                value_cells += len(values)
                other = current.get(name, [])
                if len(values) != len(other):
                    mismatches.append({'path': path, 'series': name, 'lengths_differ': True})
                    continue
                for index, (first, second) in enumerate(zip(values, other)):
                    first, second = _number(first), _number(second)
                    equal = first == second
                    if isinstance(first, float) and isinstance(second, float):
                        equal = math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-12)
                    if not equal:
                        mismatches.append({'path': path, 'chart': left['path'], 'series': name,
                                           'index': index, 'before': first, 'after': second})
    return {'chart_files': len(after), 'charts': sum(len(v['tables']) for v in after.values()),
            'value_cells': value_cells, 'mismatches': mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+')
    parser.add_argument('--output', required=True)
    parser.add_argument('--baseline', help='앞서 저장한 JSON과 Y 값 보존 여부를 비교한다.')
    args = parser.parse_args()
    result = snapshot(args.roots)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    summary = {'files': len(result), 'charts': sum(len(v.get('tables', [])) for v in result.values())}
    if args.baseline:
        summary = compare(json.loads(Path(args.baseline).read_text()), result)
        Path(args.output + '.comparison.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
