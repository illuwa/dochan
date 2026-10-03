"""공개 Excel TEXT() 캐시를 독립 표시 정답으로 전후 서식기를 비교한다.

snapshot은 지정한 코드 트리만 불러온다. 캐시는 계산하지 않고 원본 XML에서
읽으며, 표시 불일치와 원시 값 폴백을 구분한다. 원시 값 폴백은 Excel 표시
정확 일치로 세지 않는다.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys
import zipfile

from lxml import etree

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
FILES = ('NumberFormatTests.xlsx', 'DateFormatTests.xlsx', 'ElapsedFormatTests.xlsx',
         'FormatChoiceTests.xlsx', 'FormatConditionTests.xlsx', 'GeneralFormatTests.xlsx',
         'TextFormatTests.xlsx', 'NumberFormatApproxTests.xlsx', 'DateFormatNumberTests.xlsx')
FORMULA = re.compile(r'\s*TEXT\(\s*\$?([A-Z]+)\$?(\d+)\s*,\s*\$?([A-Z]+)\$?(\d+)\s*\)\s*')
CONCAT_FORMULA = re.compile(
    r'\s*TEXT\(\s*\$?([A-Z]+)\$?(\d+)\s*,\s*CONCATENATE\(";;;",\s*\$?([A-Z]+)\$?(\d+)\)\s*\)\s*')
CELL_ROW = re.compile(r'(?<![A-Z0-9_])(\$?[A-Z]+)(\$?)(\d+)')


def _shift_formula(formula, shift):
    return CELL_ROW.sub(lambda match: match.group() if match[2] else
                        match[1] + str(int(match[3]) + shift), formula)


def xml(data):
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))


def snapshot(args):
    sys.path.insert(0, str(args.tree.resolve()))
    import dochan
    assert Path(dochan.__file__).is_relative_to(args.tree.resolve())
    from dochan.ooxml.xlsx import XLSXReader
    rows = []
    for filename in FILES:
        with zipfile.ZipFile(args.corpus / filename) as archive:
            workbook = xml(archive.read('xl/workbook.xml'))
            prop = workbook.find('s:workbookPr', NS)
            date1904 = prop is not None and prop.get('date1904', '0').lower() in ('1', 'true')
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(n.text or '' for n in item.iter('{%s}t' % NS['s']))
                           for item in xml(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
            for part in sorted(n for n in archive.namelist()
                               if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')):
                cells = {}
                shared_formulas = {}
                for cell in xml(archive.read(part)).findall('.//s:sheetData/s:row/s:c', NS):
                    kind = cell.get('t', 'n')
                    value = cell.findtext('s:v', None, NS)
                    if kind == 's' and value is not None:
                        value = strings[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(n.text or '' for n in cell.iter('{%s}t' % NS['s']))
                    formula_element = cell.find('s:f', NS)
                    formula = formula_element.text if formula_element is not None else None
                    shared = formula_element.get('si') if formula_element is not None else None
                    ref = cell.get('r')
                    if shared is not None and formula:
                        shared_formulas[shared] = (ref, formula)
                    cells[ref] = (kind, value, formula, shared)
                for ref, (_, expected, formula, shared) in cells.items():
                    if not formula and shared in shared_formulas:
                        master_ref, master_formula = shared_formulas[shared]
                        formula = _shift_formula(master_formula, int(re.search(r'\d+$', ref)[0]) -
                                                 int(re.search(r'\d+$', master_ref)[0]))
                    match = FORMULA.fullmatch(formula or '')
                    concat = CONCAT_FORMULA.fullmatch(formula or '')
                    match = match or concat
                    if not match or expected is None:
                        continue
                    value_ref, format_ref = match[1] + match[2], match[3] + match[4]
                    value_cell, format_cell = cells.get(value_ref), cells.get(format_ref)
                    if not format_cell or format_cell[1] is None:
                        continue
                    raw_value = value_cell[1] if value_cell and value_cell[1] is not None else ''
                    format_string = (';;;' if concat else '') + format_cell[1]
                    reader = XLSXReader()
                    reader._errors = []
                    reader._date_1904 = date1904
                    try:
                        actual = reader._format_cell_value(raw_value, format_string)
                    except Exception as error:
                        actual = 'EXCEPTION:' + type(error).__name__
                    rows.append({'file': filename, 'part': part, 'cell': ref, 'formula': formula,
                                 'value_cell': value_ref, 'format_cell': format_ref,
                                 'raw': raw_value, 'format': format_string, 'date1904': date1904,
                                 'excel': expected, 'actual': actual})
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print('TEXT cache rows:', len(rows), 'exact:', sum(row['excel'] == row['actual'] for row in rows))


def compare(args):
    before, after = json.loads(args.before.read_text()), json.loads(args.after.read_text())
    assert len(before) == len(after)
    counts = Counter(total=len(before))
    rows = []
    for old, new in zip(before, after):
        assert all(old[key] == new[key] for key in ('file', 'part', 'cell', 'excel', 'raw', 'format'))
        was_exact, is_exact = old['actual'] == old['excel'], new['actual'] == new['excel']
        is_raw = new['actual'] == new['raw']
        counts['before_exact'] += was_exact
        counts['after_exact'] += is_exact
        counts['after_raw'] += not is_exact and is_raw
        counts['after_other'] += not is_exact and not is_raw
        counts['exact_gained'] += not was_exact and is_exact
        counts['exact_lost'] += was_exact and not is_exact
        counts['exact_lost_to_raw'] += was_exact and not is_exact and is_raw
        rows.append(dict(new, before=old['actual']))
    args.output.write_text(json.dumps({'summary': dict(counts), 'rows': rows}, ensure_ascii=False, indent=2) + '\n')
    if args.csv:
        with args.csv.open('w', newline='', encoding='utf-8') as output:
            writer = csv.writer(output, lineterminator='\n')
            writer.writerow(['공개 파일', '파트', 'TEXT 셀', '수식', '원시 값', '서식', '1904 날짜', 'Excel 캐시', 'HEAD', '수정본', '판정'])
            for row in rows:
                verdict = ('Excel 표시 정확 일치' if row['actual'] == row['excel']
                           else '원시 값 폴백' if row['actual'] == row['raw'] else '표시 미지원')
                writer.writerow([row[key] for key in ('file', 'part', 'cell', 'formula', 'raw', 'format', 'date1904', 'excel', 'before', 'actual')] + [verdict])
    print(dict(counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('snapshot', 'compare'))
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--tree', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--after', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--csv', type=Path)
    args = parser.parse_args()
    (snapshot if args.command == 'snapshot' else compare)(args)


if __name__ == '__main__':
    main()
