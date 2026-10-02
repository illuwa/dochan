"""1.7.0 대비 변경 셀을 원시 서식별로 묶어 표시 개선·중립·회귀를 판정한다.

Opus classify.py의 (파일, 이전 표시, 새 표시, 원시 값, 서식) 분류를 셀 좌표로
연결한다. 범용 Excel 서식 oracle은 아니며, 관찰한 서식군 외에는 미확인이다.
원시값 폴백이나 ISO 날짜 정규화를 Excel 문자열 정확 일치로 세지 않는다.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import json
from pathlib import Path
import re


def half_up(value):
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def classify(entry):
    evidence = entry['evidence']
    raw, fmt = evidence['raw'], evidence['format']
    old = (entry['before'] or '').split(' (=')[0]
    new = (entry['after'] or '').split(' (=')[0]
    value = Fraction(raw)
    if fmt.startswith('[=0]?;') and not value:
        if new != '0':
            return '미확인', '영값 구역', ' ', '지원하지 않는 영값 표시다.'
        direction = '가까워짐' if old == '1899-12-31' else '중립'
        return direction, '영값 구역', ' ', '날짜 오인은 제거했다. ?의 공백은 아직 0으로 표시한다.'
    if fmt == '[<0]"";0%' and value < 0:
        return ('가까워짐' if new == '' else '멀어짐'), '빈 조건 구역', '', '음수 구역의 빈 리터럴이다.'
    if fmt.startswith('[=0]?;[<4.16666666666667]') and value > 0:
        total = half_up(value * 86400)
        hours, rest = divmod(total, 3600)
        minutes, seconds = divmod(rest, 60)
        expected = '%02d:%02d' % (hours, minutes)
        if value < Fraction('4.16666666666667'):
            expected += ':%02d' % seconds
        return ('가까워짐' if new == expected else '멀어짐'), '경과 시간', expected, '원시 유리수로 총 초를 HALF_UP 계산했다.'
    if re.fullmatch(r'0(?:\.0+)?%', fmt):
        digits = len(fmt.split('.')[1][:-1]) if '.' in fmt else 0
        expected = format((Decimal(format(float(raw), '.15g')) * 100).quantize(
            Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), '.%df' % digits) + '%'
        return ('가까워짐' if new == expected else '멀어짐'), '백분율', expected, '15유효자리에서 HALF_UP으로 계산했다.'
    if re.match(r'\d{4}-\d\d-\d\d ', new) or fmt == 'h"时"mm"分"ss"秒";@':
        precision = 3 if 'ss.000' in fmt else 0
        ticks = half_up(value * 86400 * 10 ** precision)
        days, remainder = divmod(ticks, 86400 * 10 ** precision)
        seconds, fraction = divmod(remainder, 10 ** precision)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        expected = '%02d:%02d' % (hours, minutes)
        if 'ss' in fmt:
            expected += ':%02d' % seconds
        if precision:
            expected += '.%03d' % fraction
        if fmt != 'h"时"mm"分"ss"秒";@':
            base = datetime(1904, 1, 1) if evidence.get('date1904') else datetime(1899, 12, 30 if days >= 60 else 31)
            expected = (base + timedelta(days=days)).strftime('%Y-%m-%d') + ' ' + expected
        return ('가까워짐' if new == expected else '멀어짐'), '날짜·시각', expected, '날짜는 ISO 정규화이며 시간·소수 초는 독립 유리수 계산과 대조했다.'
    # Verify that layout-token removal alone explains the complete difference;
    # this does not assert that every inherited accounting layout is exact.
    if ('_' in fmt or '*' in fmt) and re.sub(r'_.', ' ', re.sub(r'\*.', '', old)) == new:
        return '가까워짐', '회계·공백', new, '수치는 동일하며 _x를 공백으로, *x를 빈 문자열로 바꾼 결과와 일치한다.'
    if new == raw:
        if (fmt.startswith('[>999999]') or fmt == '[DBNum1][$-804]General'
                or re.fullmatch(r'\[\$-[0-9A-Fa-f]+\]0', fmt)):
            return '가까워짐', '잘못된 접미·통화 제거', raw, '임의 M/K 또는 달러를 제거했다. 원시값을 정확 표시로 세지 않는다.'
        if fmt in ('builtin:14', '#,##0,,'):
            return '중립', '미지원 원시값', raw, '음수 날짜 또는 배율 미지원이며 이전 표시도 Excel과 일치하지 않는다.'
    return '미확인', '미분류', '', '관찰한 검증 규칙으로 판정하지 못했다.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--csv', type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.evidence.read_text())
    counts = Counter({'가까워짐': 0, '중립': 0, '멀어짐': 0, '미확인': 0})
    groups = Counter()
    for row in rows:
        row['verdict'], row['group'], row['expected'], row['reason'] = classify(row)
        counts[row['verdict']] += 1
        groups[row['group']] += 1
    args.output.write_text(json.dumps({'summary': dict(counts), 'groups': dict(groups), 'cells': rows},
                                    ensure_ascii=False, indent=2) + '\n')
    with args.csv.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['공개 파일', '셀', '원시 XML 위치', '원시 값', '서식', '1.7.0', '수정본', '독립 기대', '판정', '서식군', '근거'])
        for row in rows:
            e = row['evidence']
            writer.writerow([row['file'], row['cell'], e['source'], e['raw'], e['format'], row['before'],
                             row['after'], row['expected'], row['verdict'], row['group'], row['reason']])
    print(dict(counts), dict(groups))
    if counts['멀어짐'] or counts['미확인']:
        raise SystemExit('변경 셀의 회귀 또는 미확인 판정이 남아 있다.')


if __name__ == '__main__':
    main()
