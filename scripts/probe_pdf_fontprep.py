"""Differential font preparation fuzzing, using only explicitly supplied public PDFs."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import random

from dochan.pdf import cmap
from dochan.pdf.objects import PDFRef, PDFStream
from dochan.pdf.structure import PDFFile
from dochan.pdf.widths import WidthMap
from scripts.probe_pdf_objects import freeze


def extract(path):
    streams, visited = [], set()
    try:
        pdf = PDFFile(Path(path).read_bytes())
        for num in sorted(set(pdf.xref) | set(pdf._compressed)):
            obj = pdf.resolve(PDFRef(num, 0))
            candidates = []
            if isinstance(obj, dict):
                candidates = [pdf.resolve(obj.get(key)) for key in ('ToUnicode', 'Encoding')]
            elif isinstance(obj, PDFStream) and str(obj.dictionary.get('Type')) == 'CMap':
                candidates = [obj]
            while candidates:
                stream = candidates.pop()
                if not isinstance(stream, PDFStream) or id(stream) in visited:
                    continue
                visited.add(id(stream))
                streams.append(pdf.decode_stream_bytes(stream))
                candidates.append(pdf.resolve(stream.dictionary.get('UseCMap')))
        return streams, None
    except Exception as error:
        return streams, type(error).__name__


def state(value):
    if isinstance(value, cmap.EncodingCMap):
        return tuple((key, state(item)) for key, item in vars(value).items())
    if isinstance(value, (set, frozenset)):
        return (type(value).__name__, tuple(sorted(value)))
    return freeze(value)


def outcome(function, data, parents=None):
    warnings = []
    try:
        value = function(data, warnings, parents) if parents is not None else function(data, warnings)
        return ('ok', tuple((key, state(item)) for key, item in vars(value).items()), warnings)
    except Exception as error:
        return ('error', type(error).__name__, warnings)


def check(data, parents):
    for before, after, family in ((cmap._parse_tounicode_python, cmap.parse_tounicode, None),
                                  (cmap._parse_encoding_cmap_python, cmap.parse_encoding_cmap, parents)):
        left, right = outcome(before, data, family), outcome(after, data, family)
        if left != right:
            raise AssertionError((before.__name__, data[:200], left, right))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100000)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = json.loads(args.paths.read_text())
    unique, total, errors = {}, 0, {}
    with (ProcessPoolExecutor(args.workers) if args.workers > 1 else nullcontext()) as pool:
        rows = pool.map(extract, paths, chunksize=4) if pool else map(extract, paths)
        for streams, error in rows:
            for data in streams:
                total += 1
                unique[hashlib.sha256(data).digest()] = data
            if error:
                errors[error] = errors.get(error, 0) + 1
    print(json.dumps({'pdfs': len(paths), 'streams': total, 'unique': len(unique), 'errors': errors}), flush=True)
    parents = {'A': b'/B usecmap', 'B': b'/A usecmap'}
    seeds = [b'', b'beginbfchar <01><0041> endbfchar',
             b'beginbfrange <00><ffff><ffff> endbfrange',
             b'beginbfrange <00><ff>[<0041>[<0042>] endbfrange',
             b'begincidrange <ffff><0000> 0 <0000><ffff> 65535 endcidrange',
             b'begincidrange <00><01> 123456 <02><03> 1 endcidrange',
             b'/A usecmap begincodespacerange <00><ff> endcodespacerange']
    originals = list(unique.values()) + seeds
    for data in originals:
        check(data, parents)
    from dochan.pdf.predefined_cmap_data import TABLES
    predefined_rows = 0
    for name in TABLES:
        value = cmap.predefined_cmap(name)
        for source in (value.cidranges, value.notdefranges):
            for size in (1, 2, 3, 4):
                rows = [(lo, hi, cid) for length, lo, hi, cid in source if length == size]
                constant = source is value.notdefranges
                assert freeze(cmap._flatten_ranges(rows, constant)) == freeze(cmap._flatten_ranges_python(rows, constant))
                predefined_rows += len(rows)
    rng = random.Random(20261101)
    native_success = native_bail = 0
    markers = [b'beginbfchar', b'endbfchar', b'beginbfrange', b'endbfrange',
               b'begincidrange', b'endcidrange', b'<00>', b'<ff>', b'<000000000000000000001>',
               b'[', b']', b'%', b'\r\n', b'/A usecmap', b'100000', b'\x00', b'<ffff><0000>']
    for index in range(args.count):
        data = rng.choice(originals)
        # Original streams are all tested above; mutations bound per-case work.
        if len(data) > 2048:
            start = rng.randrange(len(data) - 2048)
            data = data[start:start + 2048]
        variant = index % 7
        if variant == 0:
            data = data[:rng.randrange(len(data) + 1)]
        elif variant == 1:
            at = rng.randrange(len(data) + 1)
            data = data[:at] + rng.choice(markers) + data[at:]
        elif variant == 2:
            data = b'beginbfrange ' + data + b' endbfrange'
        elif variant == 3:
            data = b'beginbfchar ' + b' '.join(rng.choices(markers, k=12)) + b' endbfchar'
        elif variant == 4:
            data = data.replace(b' ', rng.choice([b'\x00', b'\v', b'\r\n', b'%x\n']))
        elif variant == 5:
            data = b'/A usecmap begincidrange ' + b' '.join(rng.choices(markers, k=12)) + b' endcidrange'
        check(data, parents)
        try:
            cmap._ccmap.tounicode(data)
            native_success += 1
        except cmap._ccmap.Bailout:
            native_bail += 1
        rows = [(rng.randrange(-3, 10), rng.randrange(10, 20), rng.randrange(30))
                for _ in range(rng.randrange(10))]
        if index % 2:
            rows = [(i * 3, i * 3 + 1, cid) for i, (_, _, cid) in enumerate(rows)]
        for constant in (False, True):
            assert freeze(cmap._flatten_ranges(rows, constant)) == freeze(cmap._flatten_ranges_python(rows, constant))
        if index % 5 == 0:
            values = [rng.choice([rng.randrange(-5, 30), [0, 1.5, float('inf'), -0.0], None, True])
                      for _ in range(rng.randrange(20))]
            table, default, warnings = cmap._ccmap.cid_widths(values, 1000.)
            expected = WidthMap.cid(values)
            assert freeze(table) == freeze(expected._widths)
            assert default == expected._default and warnings == expected.warnings
        if index and index % 20000 == 0:
            print('cases', index, flush=True)
    result = dict(pdfs=len(paths), streams=total, unique_streams=len(unique), extraction_errors=errors,
                  original_cases=len(originals), mutated_cases=args.count, differences=0,
                  flattened_cases=2 * args.count, predefined_maps=len(TABLES), predefined_rows=predefined_rows,
                  native_success=native_success, native_bailout=native_bail, width_cases=(args.count + 4) // 5)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
