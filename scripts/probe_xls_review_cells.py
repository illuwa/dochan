"""공개 XLS의 rich text, 내부 링크와 STRING 캐시를 xlrd와 대조한다.

xlrd는 --oracle-python으로 지정한 별도 환경에서만 실행하며 런타임 의존성으로
추가하지 않는다. 코퍼스는 읽기만 하고 검증 결과만 JSON으로 저장한다.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path


def _records(data, start=0):
    while start + 4 <= len(data):
        kind, length = struct.unpack_from('<HH', data, start)
        start += 4
        if start + length > len(data):
            return
        yield kind, data[start:start + length]
        start += length


def _string_formula_cells(path, sheet_names):
    """FORMULA의 문자열 캐시 표시와 좌표만 독립적으로 읽는다."""
    import olefile
    with olefile.OleFileIO(str(path)) as ole:
        name = 'Workbook' if ole.exists('Workbook') else 'Book'
        data = ole.openstream(name).read()
    offsets = []
    for kind, payload in _records(data):
        if kind == 0x85 and len(payload) >= 8 and payload[5] == 0:
            offsets.append(struct.unpack_from('<I', payload)[0])
        if kind == 0x0a:
            break
    result = {}
    for sheet, offset in zip(sheet_names, offsets):
        coordinates = []
        for kind, payload in _records(data, offset):
            if kind == 0x06 and len(payload) >= 14:
                cached = payload[6:14]
                if cached[-2:] == b'\xff\xff' and cached[0] == 0:
                    coordinates.append(list(struct.unpack_from('<HH', payload)))
            if kind == 0x0a:
                break
        result[sheet] = coordinates
    return result


def oracle(corpus):
    import xlrd
    result = {'files': [], 'unreadable': []}
    with open(os.devnull, 'w') as quiet:
        for path in sorted(corpus.glob('*.xls')):
            try:
                book = xlrd.open_workbook(str(path), formatting_info=True, logfile=quiet)
            except Exception as error:
                result['unreadable'].append({'file': path.name, 'exception': type(error).__name__})
                continue
            sheets = []
            for sheet in book.sheets():
                rich, links, strings = [], [], []
                for (row, col), runlist in sheet.rich_text_runlist_map.items():
                    if row >= sheet.nrows or col >= sheet.ncols:
                        continue
                    cell = sheet.cell(row, col)
                    font = book.font_list[book.xf_list[cell.xf_index].font_index]
                    runs = [[off, book.font_list[index].weight >= 600,
                             bool(book.font_list[index].italic)]
                            for off, index in runlist if index < len(book.font_list)]
                    rich.append({'row': row, 'col': col, 'text': cell.value,
                                 'default': [font.weight >= 600, bool(font.italic)], 'runs': runs})
                for link in sheet.hyperlink_list:
                    if link.type == 'workbook':
                        links.append({'row': link.frowx, 'col': link.fcolx,
                                      'target': '#' + link.textmark})
                if path.name == 'StringContinueRecords.xls':
                    for row in range(sheet.nrows):
                        for col in range(sheet.ncols):
                            cell = sheet.cell(row, col)
                            if cell.ctype == xlrd.XL_CELL_TEXT:
                                strings.append({'row': row, 'col': col, 'text': cell.value})
                if rich or links or strings:
                    sheets.append({'name': sheet.name, 'rich': rich, 'links': links, 'strings': strings})
            if sheets:
                item = {'file': path.name, 'sheets': sheets}
                if path.name == 'StringContinueRecords.xls':
                    item['sheet_names'] = book.sheet_names()
                result['files'].append(item)
    return result


def _segments(pairs):
    result = []
    for text, flags in pairs:
        if result and result[-1][1] == flags:
            result[-1][0] += text
        else:
            result.append([text, flags])
    return result


def _signature(text):
    return {'length': len(text), 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def _cached_string_matches(actual, expected, is_formula):
    if actual == expected:
        return True
    if actual is None or not is_formula:
        return False
    # The expected length is known from xlrd, so embedded '(=' in the cached
    # string cannot be mistaken for the formula annotation delimiter.
    return (actual[:len(expected)] == expected and
            actual[len(expected):].startswith(' (=') and actual.endswith(')'))


def compare(corpus, expected):
    from dochan.office_binary.xls import XLSReader
    from dochan.model.table import Table
    groups = {'rich_text': [], 'internal_links': [], 'string_cache': []}
    for item in expected['files']:
        document = XLSReader().read(str(corpus / item['file']))
        string_formula_cells = (_string_formula_cells(corpus / item['file'], item['sheet_names'])
                                if item.get('sheet_names') else {})
        cells = {(section.provenance.sheet, cell.row, cell.col): cell
                 for section in document.sections for element in section.elements
                 if isinstance(element, Table)
                 for row in element.rows for cell in row
                 if cell.provenance is not None and cell.provenance.cell is not None}
        for sheet in item['sheets']:
            def record(entry):
                return {'file': item['file'], 'sheet': sheet['name'],
                        'row': entry['row'], 'col': entry['col']}
            for entry in sheet['rich']:
                cell = cells.get((sheet['name'], entry['row'], entry['col']))
                flags = [entry['default']] * len(entry['text'])
                runs = sorted(entry['runs'])
                for index, (offset, bold, italic) in enumerate(runs):
                    end = runs[index + 1][0] if index + 1 < len(runs) else len(flags)
                    for position in range(offset, min(end, len(flags))):
                        flags[position] = [bold, italic]
                wanted = _segments(zip(entry['text'], flags))
                got = [(char, [bool(run.bold), bool(run.italic)])
                       for paragraph in cell.paragraphs for run in getattr(paragraph, 'runs', [])
                       for char in run.text] if cell else []
                # Hyperlink suffixes are output annotations, not part of SST.
                match = _segments(got[:len(flags)]) == wanted and len(got) >= len(flags)
                check = record(entry)
                check.update(passed=match, expected=_signature(entry['text']),
                             actual=_signature(''.join(char for char, _ in got[:len(flags)])))
                groups['rich_text'].append(check)
            for entry in sheet['links']:
                cell = cells.get((sheet['name'], entry['row'], entry['col']))
                actual = cell.text if cell else None
                check = record(entry)
                check.update(expected=entry['target'], actual=actual,
                             passed=actual is not None and (actual == entry['target'] or
                                    actual.endswith(' <' + entry['target'] + '>')))
                groups['internal_links'].append(check)
            formula_cells = string_formula_cells.get(sheet['name'], [])
            for entry in sheet['strings']:
                if [entry['row'], entry['col']] not in formula_cells:
                    continue
                cell = cells.get((sheet['name'], entry['row'], entry['col']))
                actual = cell.text if cell else None
                matched = _cached_string_matches(actual, entry['text'], True)
                check = record(entry)
                check.update(expected=_signature(entry['text']),
                             actual=_signature(actual[:len(entry['text'])] if matched else actual or ''),
                             display_length=len(actual or ''), is_formula=True, passed=matched)
                groups['string_cache'].append(check)
    return {'summary': {name: {'files': len({check['file'] for check in checks}),
                               'total': len(checks), 'passed': sum(check['passed'] for check in checks)}
                        for name, checks in groups.items()},
            'checks': groups, 'oracle_unreadable': expected['unreadable']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--oracle-python', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--oracle-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.oracle_only:
        print(json.dumps(oracle(args.corpus), ensure_ascii=False))
        return 0
    if not args.oracle_python or not args.output:
        parser.error('--oracle-python and --output are required')
    process = subprocess.run([str(args.oracle_python), str(Path(__file__).resolve()),  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
                              str(args.corpus), '--oracle-only'],
                             capture_output=True, text=True, timeout=300)
    if process.returncode:
        raise RuntimeError('xlrd oracle failed: ' + process.stderr[-3000:])
    result = compare(args.corpus, json.loads(process.stdout))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0 if all(group['total'] == group['passed'] for group in result['summary'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
