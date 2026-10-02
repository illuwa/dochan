"""Markdown의 변경된 표 행에서 숫자 셀마다 원시 XML·BIFF 근거를 기록한다.

차트 표 재배열도 누락하지 않도록 +/- 양쪽의 숫자를 모두 조사한다. 원시 숫자,
백분율, 통화 및 ISO 날짜·시간만 비교하며 비수치 머리글·제목은 별도 검토한다.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import math
from pathlib import Path
import re

from scripts.probe_chart_review_evidence import chart_numbers, ooxml_cells, xls_cells
from scripts.probe_chart_review_outputs import identity


def number(text):
    if '_' in text:
        return None
    text = text.replace(',', '').lstrip('$')
    percent = text.endswith('%')
    if percent:
        text = text[:-1]
    try:
        result = Decimal(text)
        if not result.is_finite():
            return None
        return result / 100 if percent else result
    except InvalidOperation:
        return None


def temporal_keys(raw, date1904=False):
    try:
        value = float(raw)
        if not math.isfinite(value) or value < 0 or value > 2958465:
            return []
        # 공개 표본의 1900 날짜 체계 산술이며 1904 체계는 별도 검사한다.
        day = int(value)
        seconds = round((value - day) * 86400)
        origin = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 31)
        moment = origin + timedelta(days=day - (1 if not date1904 and day >= 60 else 0), seconds=seconds)
        return [moment.strftime('%Y-%m-%d'), moment.strftime('%Y-%m-%d %H:%M'),
                moment.strftime('%Y-%m-%d %H:%M:%S'), moment.strftime('%H:%M'),
                moment.strftime('%H:%M:%S')]
    except (ValueError, OverflowError):
        return []


def audit(args):
    comparison = json.loads(args.comparison.read_text())
    evidence = []
    counts = Counter()
    for changed in comparison['changed']:
        if not changed['md_changed']:
            continue
        filename = changed['file']
        path = args.corpus / filename
        candidates = chart_numbers(path)
        if path.suffix.lower() in ('.xls', '.xlsx', '.xlsm', '.xltx'):
            sheet = xls_cells(path) if path.suffix.lower() == '.xls' else ooxml_cells(path, resolve_strings=True)
            for coordinate, item in sheet.items():
                item['sheet_cell'] = coordinate
                candidates.append(item)
        numerics = defaultdict(list)
        temporals = defaultdict(list)
        for candidate in candidates:
            if candidate.get('type', 'n') != 'n':
                literal = candidate.get('literal')
                if literal is not None and number(literal) is not None:
                    numerics[number(literal)].append(dict(candidate, raw=literal, string_literal=True))
                continue
            value = number(candidate.get('raw') or '')
            if value is not None:
                numerics[value].append(candidate)
                for key in temporal_keys(candidate['raw'], candidate.get('date1904', False)):
                    temporals[key].append(candidate)
        diff = (args.comparison.parent / (identity(filename) + '.diff')).read_text()
        for line_number, line in enumerate(diff.splitlines(), 1):
            if not line.startswith(('+|', '-|')):
                continue
            for column, text in enumerate(line[2:].strip().strip('|').split('|')):
                text = text.strip()
                numeric = number(text)
                temporal = bool(re.fullmatch(r'\d{4}-\d\d-\d\d(?: \d\d:\d\d(?::\d\d)?)?|\d\d:\d\d(?::\d\d)?', text))
                if numeric is None and not temporal:
                    continue
                matches = numerics.get(numeric, []) if numeric is not None else temporals.get(text, [])
                verdict = '원시 수치 일치' if numeric is not None else '독립 날짜 산술 일치'
                if matches and matches[0].get('string_literal'):
                    verdict = '원본 숫자형 문자열 보존'
                if not matches and numeric is not None and line[0] == '-':
                    # BIFF doubles and HEAD's historical % multiplication can
                    # expose differing last binary digits, not decimal rounding.
                    matches = [item for value, items in numerics.items()
                               if math.isclose(float(value), float(numeric), rel_tol=1e-14, abs_tol=1e-14)
                               for item in items]
                    verdict = 'BIFF/백분율 이진수 오차 이내 일치'
                if not matches:
                    verdict = '미확인'
                if not matches:
                    for candidate in candidates:
                        if not candidate.get('sheet_cell'):
                            continue
                        raw, fmt = candidate.get('raw') or '', candidate.get('format') or ''
                        if fmt == 'builtin:11':
                            fmt = '0.00E+00'
                        raw_number = number(raw)
                        if raw_number is None:
                            continue
                        if text.endswith('%') and ('%' in fmt or fmt in ('builtin:9', 'builtin:10')):
                            decimals = 2 if fmt == 'builtin:10' else 0
                            found = re.search(r'\.([0#]+)[^;]*%', fmt)
                            if found:
                                decimals = len(found.group(1))
                            scaled = Decimal(str(float(raw))) * 100
                            expected = (scaled.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
                                        if line[0] == '+' else Decimal(format(float(raw) * 100, '.' + str(decimals) + 'f')))
                            if number(text) * 100 == expected:
                                matches = [candidate]
                                verdict = '시트 백분율 지정 자릿수 표시' if line[0] == '+' else 'HEAD 시트 기존 백분율 반올림'
                                break
                        if '%' not in fmt and not re.search(r'[A-Za-z]', fmt) and numeric is not None:
                            decimal_pattern = re.search(r'\.([0#]+)', fmt)
                            if decimal_pattern:
                                decimals = len(decimal_pattern.group(1))
                                expected = Decimal(str(float(raw))).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
                                if numeric == expected:
                                    matches = [candidate]
                                    verdict = '시트 기존 고정 소수 서식 표시'
                                    break
                        if re.search(r'E[+-]0+', fmt, re.I) and 'E' in text.upper():
                            found = re.search(r'\.([0#]+)', fmt)
                            decimals = len(found.group(1)) if found else 0
                            if number(text) == Decimal(format(raw_number, '.' + str(decimals) + 'E')):
                                matches = [candidate]
                                verdict = '시트 기존 지수 서식 표시'
                                break
                if not matches and numeric is not None and column == 0 and path.suffix.lower() == '.xls':
                    # An implicit category is a generated point index, not a
                    # source numeric value. Verify the index against the actual
                    # table row instead of treating it as numeric source data.
                    from scripts.probe_chart_review_outputs import load
                    snapshot_dir = args.comparison.parent.parent / ('before-final' if line[0] == '-' else 'after-final')
                    snapshot = load(snapshot_dir, filename)
                    for table in snapshot.get('tables', []):
                        rows = table['rows']
                        if rows and rows[0][0] == 'Category' and any(
                                row and row[0] == text == str(index + start) for start in (0, 1) for index, row in enumerate(rows[1:])):
                            matches = [{'raw': None, 'format': '', 'source': 'category fallback point index=' + text}]
                            verdict = '원시 범주 없는 점 인덱스'
                            break
                counts[verdict] += 1
                evidence.append({'file': filename, 'diff_line': line_number,
                                 'side': line[0], 'column': column, 'display': text,
                                 'verdict': verdict, 'evidence': matches[:1]})
    args.output.write_text(json.dumps({'summary': dict(counts), 'values': evidence},
                                    ensure_ascii=False, indent=2) + '\n')
    if args.csv:
        with args.csv.open('w', newline='', encoding='utf-8') as output:
            writer = csv.writer(output)
            writer.writerow(['공개 파일', 'Markdown diff 줄', '전후', '열', '출력 값', '원시 XML/레코드 위치', '원시 값', '서식', '판정'])
            for row in evidence:
                source = row['evidence'][0] if row['evidence'] else {}
                writer.writerow([row['file'], row['diff_line'], row['side'], row['column'], row['display'],
                                 source.get('source'), source.get('raw'), source.get('format'), row['verdict']])
    print(dict(counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--csv', type=Path)
    args = parser.parse_args()
    audit(args)


if __name__ == '__main__':
    main()
