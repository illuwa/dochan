"""공개 차트 및 스프레드시트의 HEAD/수정본 Markdown·JSON 출력을 비교한다.

원본 코퍼스는 읽기만 한다. inventory → snapshot(HEAD/수정본) → compare 순서로
실행하며, snapshot은 --tree의 코드만 import한다. 실패·경고도 비교 대상이다.
"""
import argparse
from collections import Counter
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import zipfile

OFFICE = {'.docx', '.xlsx', '.xlsm', '.pptx', '.pptm', '.docm', '.potx', '.dotx', '.xltx'}
SHEETS = {'.xls', '.xlsx', '.xlsm', '.xltx'}


def inventory(corpus):
    groups = {'ooxml': [], 'xls': [], 'hwpx': [], 'spreadsheets': []}
    for root in (corpus / 'poi-src/test-data', corpus / 'lo-src'):
        for path in sorted(root.rglob('*')):
            suffix = path.suffix.lower()
            relative = str(path.relative_to(corpus))
            if suffix in SHEETS:
                groups['spreadsheets'].append(relative)
            if suffix == '.xls':
                groups['xls'].append(relative)
            elif suffix in OFFICE:
                try:
                    with zipfile.ZipFile(path) as archive:
                        if any('/charts/chart' in n.lower() or 'chartex' in n.lower()
                               for n in archive.namelist()):
                            groups['ooxml'].append(relative)
                except (OSError, zipfile.BadZipFile):
                    pass
    for path in sorted((corpus / 'hwp-public/hwpx').rglob('*.hwpx')):
        try:
            with zipfile.ZipFile(path) as archive:
                if any('chart' in n.lower() for n in archive.namelist()):
                    groups['hwpx'].append(str(path.relative_to(corpus)))
        except (OSError, zipfile.BadZipFile):
            pass
    return groups


def identity(path):
    return hashlib.sha256(path.encode()).hexdigest()[:20]


def snapshot(args, groups):
    sys.path.insert(0, str(args.tree.resolve()))
    import dochan
    assert Path(dochan.__file__).is_relative_to(args.tree.resolve())
    from dochan import Dochan
    paths = sorted(set(sum(groups.values(), [])))
    args.output.mkdir(parents=True, exist_ok=True)
    def timeout(_signum, _frame):
        raise TimeoutError('document timeout')
    signal.signal(signal.SIGALRM, timeout)
    counts = Counter()
    for index, relative in enumerate(paths):
        target = args.output / (identity(relative) + '.json.gz')
        if target.exists():
            counts['cached'] += 1
            continue
        record = {'file': relative}
        start = time.monotonic()
        signal.alarm(args.timeout)
        try:
            doc = Dochan(str(args.corpus / relative))
            record['md'] = doc.to_markdown()
            record['json'] = doc.to_dict()
            record['errors'] = doc.errors
            cells = {}
            charts = []
            for table in doc.doc.find_all('table'):
                table_cells = []
                is_sheet = False
                for row in table.rows:
                    table_cells.append([cell.text for cell in row])
                    for cell in row:
                        provenance = cell.provenance
                        if provenance is not None and provenance.cell is not None:
                            is_sheet = True
                            cells[str(provenance.sheet) + '!' + provenance.cell] = cell.text
                if not is_sheet:
                    charts.append({'rows': table_cells,
                                   'path': getattr(getattr(table, 'provenance', None), 'path', None)})
            record['cells'] = cells
            record['tables'] = charts
            counts['parsed'] += 1
        except Exception as error:
            record['exception'] = type(error).__name__ + ': ' + str(error)[:300]
            counts['exception'] += 1
        finally:
            signal.alarm(0)
        record['seconds'] = time.monotonic() - start
        try:
            signal.alarm(args.timeout)
            with gzip.open(target, 'wt', encoding='utf-8', compresslevel=1) as output:
                json.dump(record, output, ensure_ascii=False, default=str)
        except TimeoutError:
            record = {'file': relative, 'exception': 'TimeoutError: output serialization limit'}
            counts['serialization_timeout'] += 1
            with gzip.open(target, 'wt', encoding='utf-8') as output:
                json.dump(record, output)
        finally:
            signal.alarm(0)
        if index % 50 == 0:
            print(index, len(paths), dict(counts), flush=True)
    print(json.dumps(dict(counts)), flush=True)


def load(directory, relative):
    with gzip.open(directory / (identity(relative) + '.json.gz'), 'rt', encoding='utf-8') as source:
        return json.load(source)


def compare(args, groups):
    args.output.mkdir(parents=True, exist_ok=True)
    paths = sorted(set(sum(groups.values(), [])))
    chart_paths = set(groups['ooxml'] + groups['xls'] + groups['hwpx'])
    counts = Counter()
    changed = []
    cells = []
    if args.refresh:
        refresh = set(sum(json.loads(args.refresh.read_text()).values(), []))
        previous = json.loads((args.output / 'comparison.json').read_text())
        counts.update(previous['summary'])
        changed = [row for row in previous['changed'] if row['file'] not in refresh]
        cells = [row for row in previous['cells'] if row['file'] not in refresh]
        for relative in refresh:
            scope = 'chart854' if relative in chart_paths else 'additional_sheet'
            counts[scope + '_files'] -= 1
            before = load(args.before, relative)
            if before.get('exception'):
                counts[scope + '_unverified'] -= 1
            if before.get('errors'):
                counts[scope + '_head_docs_with_warnings'] -= 1
                counts[scope + '_after_docs_with_warnings'] -= 1
            old = next((row for row in previous['changed'] if row['file'] == relative), {})
            assert not old.get('errors_changed'), 'refresh requires separate warning reconciliation'
            for kind in ('md', 'json', 'errors', 'exception'):
                if old.get(kind + '_changed'):
                    counts[scope + '_' + kind + '_changed'] -= 1
        paths = sorted(refresh)
    for relative in paths:
        before, after = load(args.before, relative), load(args.after, relative)
        scope = 'chart854' if relative in chart_paths else 'additional_sheet'
        counts[scope + '_files'] += 1
        if before.get('exception') or after.get('exception'):
            counts[scope + '_unverified'] += 1
        if before.get('errors'):
            counts[scope + '_head_docs_with_warnings'] += 1
        if after.get('errors'):
            counts[scope + '_after_docs_with_warnings'] += 1
        entry = {'file': relative, 'scope': scope}
        for kind in ('md', 'json', 'errors', 'exception'):
            entry[kind + '_changed'] = before.get(kind) != after.get(kind)
            if entry[kind + '_changed']:
                counts[scope + '_' + kind + '_changed'] += 1
        if any(entry[key] for key in ('md_changed', 'json_changed', 'errors_changed', 'exception_changed')):
            changed.append(entry)
            diff = '\n'.join(difflib.unified_diff(before.get('md', '').splitlines(),
                                                 after.get('md', '').splitlines(),
                                                 fromfile='HEAD', tofile='current', n=1))
            (args.output / (identity(relative) + '.diff')).write_text(diff + '\n')
        old_cells, new_cells = before.get('cells', {}), after.get('cells', {})
        for coordinate in sorted(set(old_cells) | set(new_cells)):
            if old_cells.get(coordinate) != new_cells.get(coordinate):
                cells.append({'file': relative, 'cell': coordinate,
                              'before': old_cells.get(coordinate), 'after': new_cells.get(coordinate)})
    counts['sheet_cell_changes'] = len(cells)
    counts['sheet_files_changed'] = len({cell['file'] for cell in cells})
    result = {'summary': dict(counts), 'changed': changed, 'cells': cells}
    (args.output / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'snapshot', 'compare'))
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--tree', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--after', type=Path)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--refresh', type=Path, help='Existing comparison: rescan only this manifest after an additional implementation fix')
    args = parser.parse_args()
    if args.command == 'inventory':
        result = inventory(args.corpus)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print({name: len(paths) for name, paths in result.items()})
    else:
        groups = json.loads(args.manifest.read_text())
        if args.command == 'snapshot':
            snapshot(args, groups)
        else:
            compare(args, groups)


if __name__ == '__main__':
    main()
