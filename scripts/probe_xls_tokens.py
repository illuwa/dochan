"""공개 XLS의 캐시 폴백 토큰, RSTRING 및 출력 회귀를 기록한다.

코퍼스 루트 아래 poi-src/test-data, lo-src, tika-test-docs만 읽는다.
--source-root로 HEAD 소스 스냅샷을 지정하면 격리 프로세스에서 그 코드를 쓴다.
원본 문서는 복사하지 않으며 결과 파일의 표본 경로는 코퍼스 상대 경로다.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys


TOKEN_NAMES = {0x18: 'PtgElf', 0x20: 'PtgArray', 0x26: 'PtgMemArea',
               0x27: 'PtgMemErr', 0x28: 'PtgMemNoMem', 0x29: 'PtgMemFunc',
               0x2E: 'PtgMemAreaN', 0x2F: 'PtgMemNoMemN', 0x39: 'PtgNameX'}


def failure_cause(warnings):
    """실패 진단에 기록된 토큰만 분류하며 피연산자 바이트를 세지 않는다."""
    text = ' '.join(warnings)
    if 'DDE' in text or 'OLE' in text:
        return 'DDE/OLE NameX'
    match = re.search(r'token 0x([0-9A-Fa-f]{2})', text)
    if match:
        token = int(match.group(1), 16)
        return '%s (0x%02X)' % (TOKEN_NAMES.get(token, 'token'), token)
    if 'NameX' in text:
        return 'unresolved NameX'
    if text:
        return re.sub(r'^WARN: XLS formula (?:[A-Z]+[0-9]+: )?', '', warnings[0])
    return 'no decoder diagnostic'


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def formula_is_rendered(text, decoded):
    """실제 해석 결과로 확인해 수식 뒤의 기존 주석 표기를 허용한다."""
    if not decoded:
        return False
    marker = ' (=' + decoded + ')'
    position = text.rfind(marker)
    return (text == '=' + decoded or position >= 0 and
            (position + len(marker) == len(text) or
             text[position + len(marker):].startswith(' [comment: ')))


def inspect_file(path, details_prefix=None):
    """리더의 실제 시트/토큰 호출을 관측해 폴백을 셀 단위로 센다."""
    import dochan.office_binary.xls as xls
    from dochan.output.markdown import to_markdown
    from dochan.output.json_out import to_json
    from scripts.probe_xls_formula_pairs import decoded_cells, split_formula

    sheet_parser = xls._parse_sheet_records
    token_parser = xls._decode_formula_token_stream
    workbook_parser = xls.parse_biff_workbook
    state = {'sheet': '', 'version': 0, 'workbook_version': 0}
    formulas, diagnostics, rich = {}, {}, []
    workbooks = {}

    def observe_workbook(data, *args, **kwargs):
        formulas.clear()
        diagnostics.clear()
        rich.clear()
        state['workbook_version'] = struct.unpack_from('<H', data, 4)[0] if len(data) >= 6 else 0
        doc = workbook_parser(data, *args, **kwargs)
        workbooks[id(doc)] = (dict(formulas), dict(diagnostics), list(rich))
        return doc

    def observe_tokens(tokens, *args, **kwargs):
        result = token_parser(tokens, *args, **kwargs)
        cell = kwargs.get('diagnostic_cell')
        if cell:
            isolated = dict(kwargs)
            isolated['errors'] = []
            token_parser(tokens, *args, **isolated)
            diagnostics[(state['sheet'], cell)] = {
                'tokens': bytes(tokens).hex(), 'warnings': isolated['errors'],
                'decoded': str(result), 'version': state['workbook_version']}
            context = kwargs.get('formula_context')
            if len(tokens) >= 7 and xls._base_formula_token(tokens[0]) == 0x39 and context:
                try:
                    book, _, _ = context.link(struct.unpack_from('<H', tokens, 1)[0])
                    diagnostics[(state['sheet'], cell)]['link_kind'] = book.kind
                except ValueError:
                    pass
        return result

    def observe_sheet(data, sheet, *args, **kwargs):
        state['sheet'] = sheet.name
        records = list(xls._iter_records(data))
        state['version'] = next((struct.unpack_from('<H', payload)[0]
                                 for _, kind, payload in records
                                 if kind in (0x809, 0x409, 0x209, 9) and len(payload) >= 2), 0)
        for _, kind, payload in records:
            if kind == 6 and len(payload) >= 6:
                row, col = struct.unpack_from('<HH', payload)
                if col < 256:
                    key = (sheet.name, xls._cell_ref(row, col))
                    formulas[key] = {'version': state['workbook_version'],
                                     'sheet_version': state['version'], 'raw': payload.hex()}
            elif kind == 0xD6 and len(payload) >= 6:
                row, col = struct.unpack_from('<HH', payload)
                rich.append({'sheet': sheet.name, 'cell': xls._cell_ref(row, col),
                             'version': state['version'], 'raw': payload.hex()})
        return sheet_parser(data, sheet, *args, **kwargs)

    xls._parse_sheet_records = observe_sheet
    xls._decode_formula_token_stream = observe_tokens
    xls.parse_biff_workbook = observe_workbook
    try:
        doc = xls.XLSReader().read(str(path))
    finally:
        xls._parse_sheet_records = sheet_parser
        xls._decode_formula_token_stream = token_parser
        xls.parse_biff_workbook = workbook_parser
    formulas, diagnostics, rich = workbooks.get(id(doc), ({}, {}, []))
    cells = {key: value for key, value in decoded_cells(doc).items()
             if key[0] is not None and key[1] is not None}
    omitted = []
    retained = 0
    for key, evidence in sorted(formulas.items()):
        display = cells.get(key, '')
        cache, formula = split_formula(display)
        diagnostic = diagnostics.get(key, {})
        if formula or formula_is_rendered(display, diagnostic.get('decoded', '')):
            retained += 1
            continue
        warnings = diagnostic.get('warnings', [])
        omitted.append(dict(evidence, sheet=key[0], cell=key[1], cache=cache,
                            tokens=diagnostic.get('tokens', ''), warnings=warnings,
                            decoded=diagnostic.get('decoded', ''),
                            cell_present=key in cells,
                            cause=failure_cause(warnings),
                            root_cause=('decoded formula absent from rendered cells'
                                        if diagnostic.get('decoded') and key not in cells else
                                        'BIFF5 layout' if evidence['version'] == 0x500 else
                                        'DDE/OLE NameX' if diagnostic.get('link_kind') == 'dde'
                                        else failure_cause(warnings))))
    by_key = {(cell.provenance.sheet, cell.provenance.cell): cell
              for section in doc.sections for element in section.elements
              for row in getattr(element, 'rows', []) for cell in row
              if cell.provenance is not None}
    for entry in rich:
        cell = by_key.get((entry['sheet'], entry['cell']))
        entry['actual_text'] = cell.text if cell else None
        entry['actual_runs'] = [[run.text, bool(run.bold), bool(run.italic)]
                                for paragraph in cell.paragraphs for run in paragraph.runs] if cell else []
    markdown, json_text = to_markdown(doc), to_json(doc)
    if details_prefix:
        details_prefix.parent.mkdir(parents=True, exist_ok=True)
        details_prefix.with_suffix('.md').write_text(markdown, encoding='utf-8')
        details_prefix.with_suffix('.json').write_text(json_text, encoding='utf-8')
        images = [{'filename': image.filename, 'bytes': len(image.image_data or b''),
                   'sha256': hashlib.sha256(image.image_data or b'').hexdigest()}
                  for image in doc.find_all('image')]
        details_prefix.with_suffix('.images.json').write_text(json.dumps(images), encoding='utf-8')
    return {'markdown_sha256': _hash(markdown),
            'json_sha256': _hash(json_text), 'errors': doc.errors,
            'cells': [[sheet, cell, text] for (sheet, cell), text in sorted(cells.items())],
            'raw_formula_cells': len(formulas), 'retained_formulas': retained,
            'omitted': omitted, 'rstring': rich,
            'biff_versions': dict(Counter('%04X' % v['version'] for v in formulas.values()))}


def public_paths(root):
    paths = []
    for relative in ('poi-src/test-data', 'lo-src', 'tika-test-docs'):
        directory = root / relative
        if directory.is_dir():
            paths.extend(path for path in directory.rglob('*')
                         if path.is_file() and path.suffix.lower() == '.xls')
    return sorted(set(paths))


def raw_inventory(path):
    """암호/손상 스트림을 제외한 RSTRING 원시 분모를 따로 기록한다."""
    from dochan import cfb
    from dochan.office_binary.xls import _iter_records, has_filepass_record
    from dochan.utils.bounded_io import MAX_OLE_STREAM_SIZE, read_ole_stream
    streams, failures, encrypted = [], [], []
    try:
        with cfb.OleFileIO(str(path)) as ole:
            for name in ('Workbook', 'Book'):
                if not ole.exists(name):
                    continue
                try:
                    data = read_ole_stream(ole, name, max_bytes=MAX_OLE_STREAM_SIZE)
                    if has_filepass_record(data):
                        encrypted.append(name)
                        continue
                    records = list(_iter_records(data))
                    rich = [payload.hex() for _, kind, payload in records if kind == 0xD6]
                    streams.append({'stream': name, 'rstring_records': len(rich),
                                    'rstring_raw': rich})
                except Exception as exc:
                    failures.append('%s: %s' % (name, exc))
    except Exception as exc:
        failures.append('%s: %s' % (type(exc).__name__, exc))
    if not streams and not failures and not encrypted:
        failures.append('Workbook/Book stream absent')
    return {'streams': streams, 'failures': failures, 'encrypted': encrypted}


def summarize(entries):
    count, files = Counter(), defaultdict(set)
    roots, root_files = Counter(), defaultdict(set)
    for entry in entries:
        for omission in entry.get('omitted', []):
            count[omission['cause']] += 1
            files[omission['cause']].add(entry['file'])
            root = omission.get('root_cause', omission['cause'])
            roots[root] += 1
            root_files[root].add(entry['file'])
    completed = [entry for entry in entries if 'probe_error' not in entry]
    failed_docs = [entry for entry in completed
                   if any(error.startswith('ERR:') for error in entry.get('errors', []))]
    return {'file_count': len(entries), 'completed_files': len(completed),
            'successful_files': len(completed) - len(failed_docs),
            'document_error_files': len(failed_docs),
            'probe_error_files': len(entries) - len(completed),
            'raw_inventoried_files': sum(bool(entry.get('raw_inventory', {}).get('streams'))
                                        for entry in entries),
            'raw_encrypted_files': sum(bool(entry.get('raw_inventory', {}).get('encrypted'))
                                       for entry in entries),
            'raw_inventory_failure_files': sum(bool(entry.get('raw_inventory', {}).get('failures'))
                                               for entry in entries),
            'raw_rstring_records': sum(stream['rstring_records'] for entry in entries
                                       for stream in entry.get('raw_inventory', {}).get('streams', [])),
            'raw_formula_cells': sum(entry.get('raw_formula_cells', 0) for entry in entries),
            'retained_formulas': sum(entry.get('retained_formulas', 0) for entry in entries),
            'omitted_formulas': sum(len(entry.get('omitted', [])) for entry in entries),
            'decoded_but_absent': sum(bool(omission.get('decoded')) and not omission.get('cell_present', True)
                                      for entry in entries for omission in entry.get('omitted', [])),
            'rstring_cells': sum(len(entry.get('rstring', [])) for entry in entries),
            'rstring_files': sum(bool(entry.get('rstring')) for entry in entries),
            'top20': [{'cause': cause, 'cells': total, 'files': len(files[cause])}
                      for cause, total in count.most_common(20)],
            'root_causes': [{'cause': cause, 'cells': total, 'files': len(root_files[cause])}
                            for cause, total in roots.most_common()], 'files': entries}


def probe(root, source_root, jobs=4):
    script = str(Path(__file__).resolve())
    env = dict(os.environ, PYTHONPATH=str(source_root.resolve()))
    def one(path):
        entry = {'file': str(path.relative_to(root))}
        try:
            process = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
                [sys.executable, script, str(path), '--one'], cwd=str(source_root),
                env=env, capture_output=True, text=True, timeout=120)
            if process.returncode:
                entry['probe_error'] = process.stderr[-2000:]
            else:
                entry.update(json.loads(process.stdout))
        except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
            entry['probe_error'] = '%s: %s' % (type(exc).__name__, exc)
        entry['raw_inventory'] = raw_inventory(path)
        return entry
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        entries = list(executor.map(one, public_paths(root)))
    return summarize(entries)


def compare_snapshots(before, after):
    from scripts.probe_xls_formula_pairs import split_formula
    old_files = {entry['file']: entry for entry in before['files']}
    result = {'added_formulas': 0, 'lost_formulas': [], 'changed_existing_formulas': [],
              'changed_cache_values': [], 'changed_markdown': [], 'changed_json': [],
              'new_errors': []}
    for entry in after['files']:
        previous = old_files.get(entry['file'])
        if previous is None:
            continue
        if 'probe_error' in entry or 'probe_error' in previous:
            if entry.get('probe_error') != previous.get('probe_error'):
                result['new_errors'].append(entry['file'])
            continue
        for kind in ('markdown', 'json'):
            if previous[kind + '_sha256'] != entry[kind + '_sha256']:
                result['changed_' + kind].append(entry['file'])
        old_cells = {(s, c): t for s, c, t in previous.get('cells', [])}
        new_cells = {(s, c): t for s, c, t in entry.get('cells', [])}
        for key, value in old_cells.items():
            old_cache, old_formula = split_formula(value)
            new_cache, new_formula = split_formula(new_cells.get(key, ''))
            evidence = {'file': entry['file'], 'sheet': key[0], 'cell': key[1],
                        'before': value, 'after': new_cells.get(key)}
            if old_cache != new_cache:
                result['changed_cache_values'].append(evidence)
            if old_formula and not new_formula:
                result['lost_formulas'].append(evidence)
            elif old_formula and old_formula != new_formula:
                result['changed_existing_formulas'].append(evidence)
            elif not old_formula and new_formula:
                result['added_formulas'] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--source-root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--one', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--details-prefix', type=Path,
                        help='--one 파일의 실제 Markdown/JSON 출력 저장 접두사')
    args = parser.parse_args()
    if args.one:
        print(json.dumps(inspect_file(args.corpus, args.details_prefix), ensure_ascii=False))
        return 0
    result = probe(args.corpus.resolve(), args.source_root.resolve(), args.jobs)
    if args.compare:
        result['regression'] = compare_snapshots(json.loads(args.compare.read_text()), result)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
