"""Measure native XLS formula omission over all public XLS corpus files.

The cell denominator is the set of raw FORMULA coordinates in readable,
unencrypted Workbook/Book streams. Structurally complete, nonempty NAME records
with formulas are counted separately. Files without an inspectable stream are reported
separately, never silently counted as successful. No external engine is used.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import struct
import sys

import olefile

from dochan.utils.bounded_io import MAX_OLE_STREAM_SIZE, read_ole_stream


def load_parser_snapshot(directory):
    """Load a local source snapshot without copying any corpus documents."""
    for stem in ('xls_formula', 'xls'):
        name = 'dochan.office_binary.' + stem
        path = directory / (stem + '.py')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)


def formula_coordinates(data):
    """Return unique worksheet formula coordinates from raw BIFF records."""
    from dochan.office_binary.xls import (
        _cell_ref, _iter_records, _read_boundsheet_name, has_filepass_record,
    )
    if has_filepass_record(data):
        raise ValueError('encrypted FILEPASS stream cannot be inventoried')
    sheets = []
    for _, kind, payload in _iter_records(data):
        if kind == 0x85 and len(payload) >= 8:
            sheets.append((struct.unpack_from('<I', payload)[0],
                           _read_boundsheet_name(payload)))
    sheets.sort()
    coordinates = set()
    for index, (start, name) in enumerate(sheets):
        end = sheets[index + 1][0] if index + 1 < len(sheets) else len(data)
        if not 0 <= start < end <= len(data):
            raise ValueError('invalid worksheet stream bounds')
        for _, kind, payload in _iter_records(memoryview(data)[start:end]):
            if kind == 6 and len(payload) >= 6:
                row, col = struct.unpack_from('<HH', payload)
                if col < 256:
                    coordinates.add((name, _cell_ref(row, col)))
    return coordinates


def named_formula_count(data):
    """Count complete NAME formula records independently of token decoding."""
    from dochan.office_binary.xls import _iter_records
    count = 0
    for _, kind, payload in _iter_records(data):
        if kind != 0x18 or len(payload) < 15:
            continue
        name_length = payload[3]
        formula_length = struct.unpack_from('<H', payload, 4)[0]
        name_bytes = name_length * (2 if payload[14] & 1 else 1)
        if name_length and formula_length and 15 + name_bytes + formula_length <= len(payload):
            count += 1
    return count


def inventory(path):
    coordinates, streams, failures = set(), [], []
    named_count = 0
    with olefile.OleFileIO(str(path)) as ole:
        for stream in ('Workbook', 'Book'):
            if not ole.exists(stream):
                continue
            try:
                data = read_ole_stream(ole, stream, max_bytes=MAX_OLE_STREAM_SIZE)
                coordinates.update(formula_coordinates(data))
                named_count += named_formula_count(data)
                streams.append(stream)
            except Exception as exc:
                failures.append('%s: %s' % (stream, exc))
    if not streams:
        raise ValueError('; '.join(failures) or 'Workbook/Book stream absent')
    return coordinates, named_count, streams, failures


def probe(root):
    from dochan.office_binary.xls import XLSReader
    from scripts.probe_xls_formula_pairs import decoded_cells, split_formula
    entries = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() != '.xls':
            continue
        entry = {'file': str(path.relative_to(root))}
        try:
            coordinates, named_count, streams, stream_errors = inventory(path)
            entry.update(raw_formula_cells=len(coordinates), streams=streams,
                         stream_errors=stream_errors, raw_named_formula_records=named_count)
            retained_names = 0
            try:
                document = XLSReader().read(str(path))
                cells = decoded_cells(document)
                entry['errors'] = document.errors
                retained_names = sum(
                    getattr(element, 'text', '').startswith('Defined name: ')
                    for section in document.sections for element in section.elements)
            except Exception as exc:
                cells = {}
                entry['reader_error'] = '%s: %s' % (type(exc).__name__, exc)
            omitted = [key for key in sorted(coordinates)
                       if not split_formula(cells.get(key, ''))[1]]
            entry.update(omitted=len(omitted), retained=len(coordinates) - len(omitted),
                         omitted_coordinates=omitted, retained_names=retained_names,
                         omitted_names=named_count - retained_names)
        except Exception as exc:
            entry['inventory_error'] = '%s: %s' % (type(exc).__name__, exc)
        entries.append(entry)
    total = sum(entry.get('raw_formula_cells', 0) for entry in entries)
    omitted = sum(entry.get('omitted', 0) for entry in entries)
    named_total = sum(entry.get('raw_named_formula_records', 0) for entry in entries)
    named_omitted = sum(entry.get('omitted_names', 0) for entry in entries)
    errors = Counter(error for entry in entries for error in entry.get('errors', []))
    return {
        'files': entries, 'file_count': len(entries),
        'inventoried_files': sum('raw_formula_cells' in entry for entry in entries),
        'formula_files': sum(bool(entry.get('raw_formula_cells')) for entry in entries),
        'named_formula_files': sum(bool(entry.get('raw_named_formula_records')) for entry in entries),
        'inventory_errors': sum('inventory_error' in entry for entry in entries),
        'reader_errors': sum('reader_error' in entry for entry in entries),
        'raw_formula_cells': total, 'retained': total - omitted, 'omitted': omitted,
        'omission_rate': omitted / total if total else None,
        'raw_named_formula_records': named_total,
        'retained_names': named_total - named_omitted, 'omitted_names': named_omitted,
        'name_omission_rate': named_omitted / named_total if named_total else None,
        'all_formula_records': total + named_total,
        'all_omitted': omitted + named_omitted,
        'all_omission_rate': ((omitted + named_omitted) / (total + named_total)
                              if total + named_total else None),
        'warning_counts': dict(errors),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--parser-snapshot', type=Path,
                        help='directory containing pre-review xls.py and xls_formula.py')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.parser_snapshot:
        load_parser_snapshot(args.parser_snapshot)
    result = probe(args.corpus)
    result['parser_snapshot'] = str(args.parser_snapshot) if args.parser_snapshot else None
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('files', 'warning_counts')}, ensure_ascii=False))
    return 1 if result['reader_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
