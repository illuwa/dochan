"""서식기 추가 수정의 공개 코퍼스 영향을 원시 값·서식으로 전수 선별한다.

구·신 셀 서식기의 출력과 kind를 함께 비교하고 변경 파일은 전체 Markdown·JSON
스냅샷을 다시 수집한다. 두 날짜 체계를 모두 검사하여 선별 누락을 피한다.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

from dochan.ooxml.xlsx import BUILTIN_NUM_FORMATS, XLSXReader
from scripts.probe_chart_review_evidence import chart_numbers, ooxml_cells, xls_cells


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--before-code', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    name = 'dochan.ooxml._audit_before_formatter'
    spec = importlib.util.spec_from_file_location(name, args.before_code)
    before_module = importlib.util.module_from_spec(spec)
    sys.modules[name] = before_module
    spec.loader.exec_module(before_module)
    before, after = before_module.XLSXReader(), XLSXReader()
    manifest = json.loads(args.manifest.read_text())
    files = sorted(set(sum(manifest.values(), [])))
    counts, result, failures = Counter(), [], []
    memo = {}
    for index, filename in enumerate(files):
        path = args.corpus / filename
        candidates = []
        try:
            if path.suffix.lower() in ('.xls', '.xlsx', '.xlsm', '.xltx'):
                candidates.extend((xls_cells(path) if path.suffix.lower() == '.xls' else ooxml_cells(path)).values())
            if filename in manifest['ooxml'] or filename in manifest['hwpx'] or path.suffix.lower() == '.xls':
                candidates.extend(chart_numbers(path))
        except Exception as error:
            failures.append({'file': filename, 'exception': type(error).__name__})
            continue
        changed = []
        for item in candidates:
            value, fmt = item.get('raw'), item.get('format') or ''
            if item.get('type', 'n') not in ('n', '') or value is None:
                continue
            if fmt.startswith('builtin:'):
                fmt = BUILTIN_NUM_FORMATS.get(int(fmt.split(':')[1]), '')
            if not fmt:
                continue
            key = (value, fmt)
            counts['numeric_source_points'] += 1
            if key not in memo:
                differences = []
                for date_1904 in (False, True):
                    before._date_1904 = after._date_1904 = date_1904
                    try:
                        old = (before._format_metadata(fmt).kind, before._format_cell_value(value, fmt))
                        new = (after._format_metadata(fmt).kind, after._format_cell_value(value, fmt))
                        if old != new:
                            differences.append({'date1904': date_1904, 'before': old, 'after': new})
                    except Exception as error:
                        differences.append({'exception': type(error).__name__})
                memo[key] = differences
            if memo[key]:
                changed.append(dict(item, comparisons=memo[key]))
        if changed:
            result.append({'file': filename, 'points': changed})
        if index % 100 == 0:
            print(index, len(files), 'changed files', len(result), flush=True)
    counts['unique_value_formats'] = len(memo)
    counts['changed_files'] = len(result)
    counts['source_read_failures'] = len(failures)
    args.output.write_text(json.dumps({'summary': dict(counts), 'changes': result, 'failures': failures}, ensure_ascii=False, indent=2) + '\n')
    print(dict(counts))


if __name__ == '__main__':
    main()
