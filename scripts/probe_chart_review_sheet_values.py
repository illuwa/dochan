"""시트 변경 셀을 원시 수치 또는 독립적인 날짜·백분율 산술로 판정한다."""
import argparse
from collections import Counter
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re

from scripts.probe_chart_review_diff_values import number, temporal_keys


def check(entry):
    evidence = entry['evidence']
    raw = evidence['raw']
    fmt = evidence['format']
    value = (entry['after'] or '').split(' (=')[0]
    if number(value) is not None and not value.endswith('%') and number(value) == number(raw):
        return '원시 수치 보존', raw
    if value.endswith('%'):
        # Read the precision from the original format, never from the output
        # under test. Other percentage patterns remain unverified here.
        percent = re.fullmatch(r'0(?:\.(0+))?%', fmt)
        if percent:
            decimals = len(percent.group(1) or '')
            expected = (Decimal(str(float(raw))) * 100).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
            display = format(expected, '.%df' % decimals) + '%'
            if value == display:
                return '백분율 지정 자릿수 HALF_UP', display
    if value in temporal_keys(raw, evidence.get('date1904', False)):
        return '날짜·시간 의미 일치', value
    # Elapsed formats retain all hours/minutes, unlike wall-clock time.
    if re.search(r'\[(?:h+|m+|s+)\]', fmt, re.I):
        total = round(float(raw) * 86400)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        possibilities = ['%02d:%02d:%02d' % (hours, minutes, seconds),
                         '%02d:%02d' % (hours, minutes),
                         '%02d:%02d' % (total // 60, seconds), str(total)]
        if value in possibilities:
            return '경과 시간 의미 일치', value
    return '미확인', ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--csv', type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads(args.evidence.read_text())
    counts = Counter()
    for entry in entries:
        entry['verdict'], entry['expected'] = check(entry)
        counts[entry['verdict']] += 1
    args.output.write_text(json.dumps({'summary': dict(counts), 'cells': entries}, ensure_ascii=False, indent=2) + '\n')
    with args.csv.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['공개 파일', '셀', '원시 XML/레코드 위치', '원시 값', '서식', 'HEAD', '수정본', '독립 기대', '판정'])
        for entry in entries:
            evidence = entry['evidence']
            writer.writerow([entry['file'], entry['cell'], evidence['source'], evidence['raw'], evidence['format'],
                             entry['before'], entry['after'], entry['expected'], entry['verdict']])
    print(dict(counts))


if __name__ == '__main__':
    main()
