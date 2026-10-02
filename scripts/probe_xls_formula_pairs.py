"""Compare every public same-name XLS/XLSX pair against raw OOXML <f> text.

The optional xlrd interpreter is an external oracle, never a runtime dependency.
Shared followers are expanded only from their raw OOXML anchor formula text.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import posixpath
import re
import struct
import subprocess
from lxml import etree as ET

from pathlib import Path
from zipfile import ZipFile

import olefile

from dochan.office_binary.xls import (
    XLSReader, _cell_ref, _decode_formula_token_stream, _iter_records, _read_boundsheet_name,
)
from dochan.utils.bounded_io import MAX_OLE_STREAM_SIZE, read_ole_stream

_SAFE_XML = ET.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def _coordinate(ref):
    letters = ''.join(c for c in ref if c.isalpha())
    column = 0
    for character in letters.upper():
        column = column * 26 + ord(character) - 64
    return int(ref[len(letters):]), column


def translate_shared_formula(formula, anchor, follower):
    """Translate relative A1 tokens, preserving strings and quoted sheet names."""
    row, col = _coordinate(follower)
    anchor_row, anchor_col = _coordinate(anchor)
    def move(match):
        absolute_col, letters, absolute_row, digits = match.groups()
        source_row, source_col = _coordinate(letters + digits)
        target_row = source_row if absolute_row else source_row + row - anchor_row
        target_col = source_col if absolute_col else source_col + col - anchor_col
        if target_row < 1 or target_col < 1:
            return '#REF!'
        result = ''
        while target_col:
            target_col, rem = divmod(target_col - 1, 26)
            result = chr(65 + rem) + result
        return absolute_col + result + absolute_row + str(target_row)
    pieces = re.split(r'("(?:[^" ]| |"")*"|\'(?:[^\']|\'\')*\')', formula)
    # Quoted strings/sheet identifiers are captured at odd positions.
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(r'(?<![A-Za-z0-9_.$])(\$?)([A-Za-z]{1,3})(\$?)([1-9][0-9]*)(?![A-Za-z0-9_!])', move, pieces[index])
    return ''.join(pieces)


def raw_formulas(path):
    result, followers = {}, 0
    with ZipFile(path) as archive:
        book = ET.fromstring(archive.read('xl/workbook.xml'), _SAFE_XML)
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'), _SAFE_XML)
        targets = {r.attrib['Id']: r.attrib['Target'] for r in rels}
        for sheet in book.findall('s:sheets/s:sheet', NS):
            target = targets[sheet.attrib[RID]]
            member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            tree = ET.fromstring(archive.read(member), _SAFE_XML)
            shared, pending = {}, []
            for cell in tree.findall('.//s:c', NS):
                formula = cell.find('s:f', NS)
                if formula is None:
                    continue
                if formula.text is None:
                    followers += 1
                    if formula.attrib.get('t') == 'shared':
                        pending.append((cell.attrib['r'], formula.attrib.get('si')))
                    continue
                result[(sheet.attrib['name'], cell.attrib['r'])] = formula.text
                if formula.attrib.get('t') == 'shared':
                    shared[formula.attrib.get('si')] = (cell.attrib['r'], formula.text)
            for follower, shared_id in pending:
                if shared_id in shared:
                    anchor, formula = shared[shared_id]
                    result[(sheet.attrib['name'], follower)] = translate_shared_formula(formula, anchor, follower)
    return result, followers


def decoded_cells(document):
    return {(cell.provenance.sheet, cell.provenance.cell): cell.text
            for section in document.sections for element in section.elements
            for row in getattr(element, 'rows', []) for cell in row
            if cell.provenance is not None}


def split_formula(text):
    if ' (=' in text and text.endswith(')'):
        cache, formula = text.rsplit(' (=', 1)
        return cache, formula[:-1]
    if text.startswith('='):
        return '', text[1:]
    return text, ''


def normalize_formula_presentation(formula):
    """Ignore only spacing around operators, never reference intersection spaces."""
    pieces = _formula_pieces(formula)
    for index in range(0, len(pieces), 2):
        piece = re.sub(r'\s*([,+*/^&=<>-])\s*', r'\1', pieces[index])
        # Whitespace outside parentheses can be the reference intersection operator.
        pieces[index] = re.sub(r'\s+\)', ')', re.sub(r'\(\s+', '(', piece))
    return ''.join(pieces)


def _formula_pieces(formula):
    # Protect string literals, quoted sheet identifiers and bracketed names.
    return re.split(r'("(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'|\[[^\]]*\])', formula)


def normalize_formula_spelling(formula, absolute_refs=False):
    """Normalize conservative spellings; never turn F255(name,args) into name(args).

    Dollar removal is an optional, separate *same-cell* diagnostic: relative and
    absolute references are not equivalent under copying or shared translation.
    """
    pieces = _formula_pieces(normalize_formula_presentation(formula))
    for index, piece in enumerate(pieces):
        if index % 2:
            if (re.fullmatch(r"'[A-Za-z_][A-Za-z0-9_.]*(?::[A-Za-z_][A-Za-z0-9_.]*)?'", piece)
                    and index + 1 < len(pieces) and pieces[index + 1].startswith('!')):
                pieces[index] = piece[1:-1]
            continue
        piece = re.sub(r'(?<![\w.])_xlfn\.(?=[A-Za-z_][A-Za-z0-9_.]*\()', '', piece)
        if absolute_refs:
            piece = re.sub(r'(?<![\w.$])\$?[A-Za-z]{1,3}\$?[1-9][0-9]*(?![\w.!\(])',
                           lambda match: match.group(0).replace('$', ''), piece)
        pieces[index] = piece
    return ''.join(pieces)


def formula_comparison(expected, actual):
    if actual == expected:
        return 'exact'
    if normalize_formula_presentation(actual) == normalize_formula_presentation(expected):
        return 'whitespace'
    if normalize_formula_spelling(actual) == normalize_formula_spelling(expected):
        return 'sheet quotes or function prefix'
    if normalize_formula_spelling(actual, True) == normalize_formula_spelling(expected, True):
        return 'absolute reference markers only'
    return 'mismatch'


def workbook_formula_evidence(data, coordinates):
    """Observe raw BOUNDSHEET/FORMULA records, without using decoded cell output.

    Only requested coordinates are retained. Token bytes are public-corpus
    evidence; isolated warnings identify unsupported NameX/array tokens per cell.
    """
    sheets = []
    for _, kind, payload in _iter_records(data):
        if kind == 0x85 and len(payload) >= 8:
            sheets.append((struct.unpack_from('<I', payload)[0], _read_boundsheet_name(payload)))
    sheets.sort()
    wanted, found = set(coordinates), {}
    for index, (start, name) in enumerate(sheets):
        end = sheets[index + 1][0] if index + 1 < len(sheets) else len(data)
        if not 0 <= start < end <= len(data):
            continue
        arrays, sheet_formulas = {}, []
        for _, kind, payload in _iter_records(memoryview(data)[start:end]):
            if kind == 0x221 and len(payload) >= 14:
                first_row, _, first_col = struct.unpack_from('<HHB', payload)
                length = struct.unpack_from('<H', payload, 12)[0]
                arrays[(first_row, first_col)] = payload[14:14 + length]
            if kind != 6 or len(payload) < 22:
                continue
            row, col = struct.unpack_from('<HH', payload)
            key = name, _cell_ref(row, col)
            if key not in wanted:
                continue
            length = struct.unpack_from('<H', payload, 20)[0]
            tokens = payload[22:22 + length]
            warnings = []
            _decode_formula_token_stream(tokens, errors=warnings)
            found[key] = {'tokens': tokens.hex(), 'token_warnings': warnings}
            sheet_formulas.append((key, tokens))
        for key, tokens in sheet_formulas:
            if len(tokens) == 5 and tokens[0] == 1:
                template = arrays.get(struct.unpack_from('<HH', tokens, 1))
                if template is not None:
                    found[key]['array_template'] = template.hex()
                    _decode_formula_token_stream(template, errors=found[key]['token_warnings'])
    return found, [name for _, name in sheets]


def raw_formula_evidence(path, coordinates):
    with olefile.OleFileIO(str(path)) as ole:
        stream = 'Workbook' if ole.exists('Workbook') else 'Book'
        data = read_ole_stream(ole, stream, max_bytes=MAX_OLE_STREAM_SIZE)
    return workbook_formula_evidence(data, coordinates)


def mismatch_cause(check, evidence, source_sheets):
    if check['comparison'] != 'mismatch':
        return check['comparison']
    if check['sheet'] not in source_sheets:
        return 'source sheet absent'
    if evidence is None:
        return 'source formula absent'
    if re.search(r'\bF255\(', check['actual']):
        return 'UDF name indirection'
    if '[External' in check['actual']:
        return 'external workbook reference'
    warnings = ' '.join(evidence['token_warnings'])
    if not check['actual'] and 'token 0x39' in warnings:
        return 'NameX or add-in'
    if not check['actual'] and 'token 0x20' in warnings:
        return 'array constant'
    if check['actual'] and re.search(r'\b[A-Za-z_][A-Za-z0-9_]*\[', check['expected']):
        return 'structured reference versus BIFF range'
    return 'unclassified mismatch'


def classify_cache(display, oracle):
    if 'error' in oracle:
        return 'oracle error'
    kind, value = oracle['type'], oracle['value']
    if kind == 4:
        expected = 'TRUE' if value else 'FALSE'
    elif kind == 5:
        expected = {0: '#NULL!', 7: '#DIV/0!', 15: '#VALUE!', 23: '#REF!',
                    29: '#NAME?', 36: '#NUM!', 42: '#N/A'}.get(value, '')
    elif kind in (2, 3):
        expected = str(int(value)) if value == int(value) else str(value)
    else:
        expected = str(value)
    if display == expected:
        return 'exact'
    if kind == 2:
        cleaned = display.strip().replace(',', '')
        cleaned = cleaned.lstrip('$€£¥₩').strip()
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]
        percent = cleaned.endswith('%')
        try:
            parsed = Decimal(cleaned[:-1] if percent else cleaned)
            if percent:
                parsed /= 100
            if parsed == Decimal(str(value)):
                return 'number-format equivalent'
            # A rounding comparison is allowed only when xlrd independently
            # supplies a numeric display mask specifying that precision.
            mask = oracle.get('format', '').split(';')[0]
            mask = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', mask)
            numeric = re.search(r'([#0?,]+)(?:\.([#0?]+))?', mask)
            if numeric and not re.search(r'[YyDdHhSs]', mask):
                decimals = len(numeric.group(2) or '')
                commas = len(numeric.group(1)) - len(numeric.group(1).rstrip(','))
                scale = Decimal(100) if '%' in mask else Decimal(1)
                scale /= Decimal(1000) ** commas
                expected_display = (Decimal(str(value)) * scale).quantize(
                    Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
                actual_display = parsed * (100 if percent else 1)
                if actual_display == expected_display:
                    return 'number-format equivalent'
        except InvalidOperation:
            pass
    # Rounding and date formatting are intentionally not guessed equivalent.
    return 'mismatch'


def oracle_values(interpreter, path, coordinates):
    code = '''import json,sys,xlrd
book=xlrd.open_workbook(sys.argv[1], formatting_info=True)
result=[]
for sheet, ref in json.loads(sys.stdin.read()):
    letters=''.join(c for c in ref if c.isalpha()); col=0
    for c in letters: col=col*26+ord(c.upper())-64
    row=int(ref[len(letters):])-1
    try:
        s=book.sheet_by_name(sheet); cell=s.cell(row,col-1)
        result.append({'sheet':sheet,'cell':ref,'type':cell.ctype,'value':cell.value,'format':book.format_map[book.xf_list[cell.xf_index].format_key].format_str})
    except (IndexError,KeyError,xlrd.biffh.XLRDError) as exc:
        result.append({'sheet':sheet,'cell':ref,'error':str(exc)})
print(json.dumps(result,ensure_ascii=False))
'''
    proc = subprocess.run([str(interpreter), '-c', code, str(path)],  # nosemgrep: dangerous-subprocess-use-audit
                          input=json.dumps(list(coordinates)), text=True,
                          capture_output=True, timeout=60)
    if proc.returncode:
        return {'error': proc.stderr[-1000:]}
    # xlrd can print recovery warnings before its final JSON line.
    return json.loads(proc.stdout.strip().splitlines()[-1])


def probe(root, oracle_python=None):
    pairs = []
    for legacy in sorted(root.rglob('*.xls')):
        modern = legacy.with_suffix('.xlsx')
        if not modern.is_file():
            continue
        entry = {'file': str(legacy.relative_to(root)), 'xlsx': str(modern.relative_to(root))}
        try:
            expected, followers = raw_formulas(modern)
            doc = XLSReader().read(str(legacy))
            actual = decoded_cells(doc)
            raw_evidence, source_sheets = raw_formula_evidence(legacy, expected) if expected else ({}, [])
            checks = []
            for coordinate, formula in expected.items():
                cache, decoded = split_formula(actual.get(coordinate, ''))
                comparison = formula_comparison(formula, decoded)
                checks.append({'sheet': coordinate[0], 'cell': coordinate[1],
                               'expected': formula, 'actual': decoded,
                               'cached_display': cache, 'passed': decoded == formula,
                               'comparison': comparison,
                               'presentation_equivalent': comparison in ('exact', 'whitespace', 'sheet quotes or function prefix'),
                               'reference_equivalent': comparison != 'mismatch'})
                check = checks[-1]
                evidence = raw_evidence.get(coordinate)
                check['cause'] = mismatch_cause(check, evidence, source_sheets)
                if comparison == 'mismatch':
                    check['source_formula'] = evidence
            entry.update(formulas=len(checks), passed=sum(c['passed'] for c in checks),
                         presentation_equivalent=sum(c['presentation_equivalent'] for c in checks),
                         reference_equivalent=sum(c['reference_equivalent'] for c in checks),
                         comparison_counts=dict(Counter(c['comparison'] for c in checks)),
                         cause_counts=dict(Counter(c['cause'] for c in checks)),
                         source_sheets=source_sheets,
                         empty_shared_followers=followers, checks=checks, errors=doc.errors)
            if oracle_python and checks:
                oracle = oracle_values(oracle_python, legacy, expected)
                entry['xlrd_cached_values'] = oracle
                if isinstance(oracle, list):
                    by_coordinate = {(c['sheet'], c['cell']): c for c in oracle}
                    for check in checks:
                        value = by_coordinate.get((check['sheet'], check['cell']), {'error': 'missing'})
                        check['cache_comparison'] = classify_cache(check['cached_display'], value)
                    entry['cache_comparisons'] = dict(Counter(c['cache_comparison'] for c in checks))
        except Exception as exc:
            entry['probe_error'] = '%s: %s' % (type(exc).__name__, exc)
        pairs.append(entry)
    cache_counts, comparison_counts, cause_counts = Counter(), Counter(), Counter()
    for pair in pairs:
        cache_counts.update(pair.get('cache_comparisons', {}))
        comparison_counts.update(pair.get('comparison_counts', {}))
        cause_counts.update(pair.get('cause_counts', {}))
    return {'pairs': pairs, 'pair_count': len(pairs), 'cache_comparisons': dict(cache_counts),
            'comparison_counts': dict(comparison_counts),
            'cause_counts': dict(cause_counts),
            'formula_pairs': sum(bool(p.get('formulas')) for p in pairs),
            'formulas': sum(p.get('formulas', 0) for p in pairs),
            'passed': sum(p.get('passed', 0) for p in pairs),
            'presentation_equivalent': sum(p.get('presentation_equivalent', 0) for p in pairs),
            'reference_equivalent': sum(p.get('reference_equivalent', 0) for p in pairs),
            'empty_shared_followers': sum(p.get('empty_shared_followers', 0) for p in pairs),
            'probe_errors': sum('probe_error' in p for p in pairs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--oracle-python', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.corpus, args.oracle_python)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'pairs'}))
    else:
        print(rendered)
    return 0 if not result['probe_errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
