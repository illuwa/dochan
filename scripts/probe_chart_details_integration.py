"""차트 파트 프로브 결과를 실제 문서 리더의 출력과 대조한다.

--probe에는 probe_chart_details의 공개 코퍼스 JSON을 준다. 원본 문서는
읽기만 하며, 고아 차트나 지원하지 않는 배치로 출력되지 않은 파트를 구분한다.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from dochan.ooxml.docx import DOCXReader
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.xlsx import XLSXReader


def probe(source):
    by_file = defaultdict(list)
    for row in source['results']:
        if 'part' in row:
            by_file[row['file']].append(row)
    stats = Counter()
    results = []
    for filename, parts in sorted(by_file.items()):
        suffix = Path(filename).suffix.lower()
        reader = DOCXReader if suffix in ('.docx', '.docm', '.dotx') else PPTXReader if suffix in ('.pptx', '.pptm', '.potx') else XLSXReader
        try:
            document = reader().read(filename)
        except Exception as error:
            # 한 실물의 실패가 전체 코퍼스 검증 결과를 지우지 않도록 기록한다.
            stats['read_failures'] += 1
            results.append({'file': filename, 'read_error': type(error).__name__ + ': ' + str(error)[:256]})
            continue
        stats['read_files'] += 1
        tables = document.find_all('table')
        for part in parts:
            matches = [table for table in tables if
                       getattr(getattr(table, 'provenance', None), 'path', '') == part['part']
                       or any(getattr(getattr(p, 'provenance', None), 'path', '') == part['part']
                              for p in (getattr(table, 'caption', None) or []))]
            result = {'file': filename, 'part': part['part'], 'emitted': bool(matches)}
            if not matches:
                stats['not_emitted'] += 1
            else:
                stats['emitted'] += 1
                actual = [[cell.text for cell in row] for row in matches[0].rows]
                result['rows_match'] = actual == part['rows']
                result['actual_rows'] = actual
                result['expected_rows'] = part['rows']
                stats['rows_match' if result['rows_match'] else 'rows_mismatch'] += 1
            results.append(result)
    return {'summary': dict(stats), 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    result = probe(json.loads(args.probe.read_text()))
    if args.baseline:
        before = json.loads(args.baseline.read_text())
        def missing(data):
            return sorted((r['file'], r['part']) for r in data['results']
                          if 'part' in r and not r['emitted'])
        result['summary']['missing_parts_unchanged'] = missing(before) == missing(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
