"""전후 출력의 비시트 변경을 검사하고 검증된 셀 CSV와 Markdown diff를 만든다."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from scripts.probe_chart_review_outputs import identity, load


def without_text(value):
    if isinstance(value, dict):
        return {key: without_text(item) for key, item in value.items() if key != 'text'}
    if isinstance(value, list):
        return [without_text(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--verdicts', type=Path, required=True)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output-prefix', type=Path, required=True)
    parser.add_argument('--baseline', default='62b8c3e')
    args = parser.parse_args()
    comparison = json.loads((args.comparison / 'comparison.json').read_text())
    verdicts = json.loads(args.verdicts.read_text())
    for entry in comparison['changed']:
        old, new = load(args.before, entry['file']), load(args.after, entry['file'])
        assert old.get('tables') == new.get('tables'), entry['file']
        assert without_text(old.get('json')) == without_text(new.get('json')), entry['file']
        if not entry['json_changed']:
            continue
        for a, b in zip(old['json']['sections'], new['json']['sections']):
            for left, right in zip(a['elements'], b['elements']):
                if left == right:
                    continue
                assert left['type'] == right['type'] == 'table', entry['file']
                for r1, r2 in zip(left['rows'], right['rows']):
                    for c1, c2 in zip(r1, r2):
                        if c1 != c2:
                            assert c1.get('provenance', {}).get('cell'), entry['file']
                            assert c2.get('provenance', {}).get('cell'), entry['file']
    counts = defaultdict(Counter)
    with Path(str(args.output_prefix) + '-output-values.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['공개 파일', '출력 종류', '셀', '원시 XML 위치', '원시 값', '서식', args.baseline,
                         '수정본', '독립 기대', '판정'])
        for row in verdicts['cells']:
            e = row['evidence']
            writer.writerow([row['file'], '시트 셀', row['cell'], e['source'], e['raw'], e['format'],
                             row['before'], row['after'], row['expected'], row['verdict']])
            counts[row['file']][row['verdict']] += 1
    lines = ['# 공개 표본의 기준 커밋 대비 출력 차이', '',
             '기준 커밋은 `%s`이다. 비교 집합과 미검증 표본은 같은 접두의 실물 검증 문서를 따른다.' % args.baseline, '',
             '변경된 %s개 파일의 %s셀을 원본 좌표에 연결했다. 차트 표·제목·캡션과 비시트 요소의 변화는 없다. '
             '표시 문자열을 제외한 JSON 구조도 전후 동일했다.' % (len(counts), len(verdicts['cells'])), '',
             '시트 CSV와 출력값 CSV는 같은 변경 셀 집합이다. 별도의 elapsed-values CSV는 바뀌지 않은 경과 시간 '
             '셀도 포함하며 독립 산술 대조와 기준 표시 복구 여부를 구분한다.', '',
             '## 파일별 변경 셀', '', '| 공개 파일 | 판정별 셀 수 | 합계 |', '|---|---|---:|']
    for name, values in sorted(counts.items()):
        lines.append('| `%s` | %s | %d |' % (name, '; '.join('%s: %d' % item for item in sorted(values.items())),
                                            sum(values.values())))
    lines += ['', 'CSV는 수식 설명 접미사 앞의 표시값을 검증한다. 다음은 실제 Markdown 출력의 차이다. '
              '빈 문맥 행의 공백 표시자는 생략했으며 셀의 실제 공백은 CSV에 보존한다.']
    for entry in comparison['changed']:
        if entry['md_changed']:
            diff = (args.comparison / (identity(entry['file']) + '.diff')).read_text()
            diff = '\n'.join('' if line == ' ' else line for line in diff.splitlines())
            lines += ['', '## ' + entry['file'], '', '```diff', diff.rstrip(), '```']
    Path(str(args.output_prefix) + '-output-diffs.md').write_text('\n'.join(lines) + '\n')
    print('non-sheet changes: 0; output CSV cells:', len(verdicts['cells']))


if __name__ == '__main__':
    main()
