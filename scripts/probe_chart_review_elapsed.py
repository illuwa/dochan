"""공개 시트의 경과 시간 셀을 원시 XML 및 독립 유리수 산술로 대조한다."""
import argparse
from collections import Counter
import csv
from fractions import Fraction
import json
from pathlib import Path
import re
import zipfile

from lxml import etree

from scripts.probe_chart_review_evidence import ooxml_cells
from scripts.probe_chart_review_outputs import load


def expected_elapsed(raw, fmt):
    """코퍼스에서 관찰한 조건부/단순 경과 서식의 독립 기대를 계산한다."""
    value = Fraction(raw)
    if value < 0:
        return None
    # Quoted semicolons belong to literals, not section delimiters.
    sections = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', fmt)
    selected = sections[0]
    for section in sections:
        condition = re.match(r'\[(<=|>=|<>|=|<|>)(-?[\d.Ee+\-]+)\]', section)
        if condition is None:
            selected = section
            break
        operator, bound = condition.groups()
        bound = Fraction(bound)
        if {'<': value < bound, '<=': value <= bound, '>': value > bound,
                '>=': value >= bound, '=': value == bound, '<>': value != bound}[operator]:
            selected = section[condition.end():]
            break
    # All observed supported cells use [hh]:mm:ss. Also recognize the other
    # requested simple forms without calling any dochan formatting helper.
    tokens = re.findall(r'"[^"]*"|\[[hms]+\]|[hms]+|.', selected, re.I)
    literals_before, literals_after = [], []
    while tokens and tokens[0].startswith('"'):
        literals_before.append(tokens.pop(0)[1:-1])
    while tokens and tokens[-1].startswith('"'):
        literals_after.insert(0, tokens.pop()[1:-1])
    tokens = [token.lower() for token in tokens]
    if not tokens or not re.fullmatch(r'\[(h+|m+|s+)\]', tokens[0]):
        return None
    unit = tokens[0][1:-1]
    tail = tokens[1:]
    allowed = {'h': ([], [':', 'm'], [':', 'mm']),
               'm': ([], [':', 's'], [':', 'ss']), 's': ([],)}
    valid = tail in allowed[unit[0]]
    if unit[0] == 'h' and len(tail) == 4:
        valid = tail[:2] in allowed['h'][1:] and tail[2:] in ([':', 's'], [':', 'ss'])
    if not valid:
        return None
    seconds = value * 86400
    # Positive rational HALF_UP, independently of the runtime Decimal path.
    total = (2 * seconds.numerator + seconds.denominator) // (2 * seconds.denominator)
    first = total // {'h': 3600, 'm': 60, 's': 1}[unit[0]]
    pieces = [str(first).zfill(len(unit))]
    for token in tail[1::2]:
        component = total // 60 % 60 if token[0] == 'm' else total % 60
        pieces.append(str(component).zfill(len(token)))
    return ''.join(literals_before) + ':'.join(pieces) + ''.join(literals_after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--csv', type=Path, required=True)
    args = parser.parse_args()
    counts, rows, excluded = Counter(), [], []
    for name in json.loads(args.manifest.read_text())['spreadsheets']:
        if Path(name).suffix.lower() == '.xls':
            continue
        counts['xlsx_candidates'] += 1
        try:
            with zipfile.ZipFile(args.corpus / name) as archive:
                if 'xl/styles.xml' not in archive.namelist():
                    continue
                styles = archive.read('xl/styles.xml')
                if not re.search(rb'\[(?:h+|m+|s+)\]|numFmtId="46"', styles, re.I):
                    continue
            cells = ooxml_cells(args.corpus / name)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as error:
            excluded.append({'file': name, 'reason': type(error).__name__})
            continue
        before, after = load(args.before, name), load(args.after, name)
        for ref, evidence in cells.items():
            fmt = evidence['format']
            if fmt == 'builtin:46':
                fmt = '[h]:mm:ss'
            if evidence['type'] != 'n' or evidence['raw'] is None or not re.search(r'\[(h+|m+|s+)\]', fmt, re.I):
                continue
            counts['elapsed_format_candidates'] += 1
            expected = expected_elapsed(evidence['raw'], fmt)
            if expected is None:
                counts['not_simple_elapsed_section'] += 1
                continue
            old = before.get('cells', {}).get(ref)
            new = after.get('cells', {}).get(ref)
            actual = new.split(' (=')[0] if new is not None else None
            counts['supported_cells'] += 1
            counts['exact'] += actual == expected
            counts['same_as_baseline'] += old == new
            rows.append(dict(file=name, cell=ref, before=old, after=new,
                             expected=expected, evidence=evidence))
    args.output.write_text(json.dumps({'summary': dict(counts), 'excluded': excluded, 'cells': rows},
                                    ensure_ascii=False, indent=2) + '\n')
    with args.csv.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['공개 파일', '셀', '원시 XML 위치', '원시 값', '서식', '62b8c3e', '수정본', '독립 기대', '기준 동일', '표시 일치'])
        for row in rows:
            e = row['evidence']
            writer.writerow([row['file'], row['cell'], e['source'], e['raw'], e['format'], row['before'],
                             row['after'], row['expected'], row['before'] == row['after'],
                             row['after'] is not None and row['after'].split(' (=')[0] == row['expected']])
    print(dict(counts), 'excluded:', len(excluded))


if __name__ == '__main__':
    main()
