"""Differential table reconstruction on public pages and deterministic mutations.

Only explicit public corpus paths are read. Capture files, if requested, belong
in an ignored work directory. Reports contain counts and structural mismatches,
not document text. Example: python -m scripts.probe_pdf_ctables_fuzz --corpus
corpus/press-pairs --cases 100000 --output .codex-work/tables-fuzz.json
"""
import argparse
from collections import Counter
import copy
from dataclasses import fields, is_dataclass, replace
import importlib
import json
from pathlib import Path
import pickle
import random
import struct
import time


def exact(value):
    """Encode every field, Python type, float bit and defined container order."""
    tag = type(value).__module__, type(value).__qualname__
    if isinstance(value, float):
        return tag, struct.pack('!d', value)
    if is_dataclass(value):
        return tag, tuple((field.name, exact(getattr(value, field.name)))
                          for field in fields(value))
    if isinstance(value, dict):
        return tag, tuple((exact(k), exact(v)) for k, v in value.items())
    if isinstance(value, (set, frozenset)):
        return tag, tuple(exact(item) for item in value)
    if isinstance(value, (list, tuple)):
        return tag, tuple(exact(item) for item in value)
    return tag, value


def synthetic_pages():
    from dochan.pdf.content import Fragment
    from dochan.pdf.paths import Segment
    pages = []
    for columns, rows in ((1, 1), (2, 3), (3, 3), (4, 5)):
        segments = [Segment(0., r * 20., columns * 30., r * 20.)
                    for r in range(rows + 1)]
        segments += [Segment(c * 30., 0., c * 30., rows * 20.)
                     for c in range(columns + 1)]
        fragments = [Fragment(c * 30. + 4., r * 20. + 5., 10., 8.,
                              str(r * columns + c), 2., order=r * columns + c)
                     for r in range(rows) for c in range(columns)]
        pages.append((segments, fragments, []))
        # Unruled numeric bands exercise row inference.
        pages.append(([s for s in segments if s.x0 == s.x1 or s.y0 in (0., rows * 20.)],
                      fragments, []))
    # Internal short dashed boundaries: coordinates and lengths are binary exact.
    segments, fragments, _ = pages[-2]
    short = [Segment(x * .75, 40., x * .75 + .5, 40.) for x in range(160)]
    pages.append(([s for s in segments if s.y0 != 40. or s.y1 != 40.], fragments, short))
    return pages


def capture_pages(roots, max_pages):
    from dochan import Dochan
    from dochan.pdf import reader, tables
    paths = []
    for root in roots:
        root = Path(root)
        if 'local-samples' in root.parts or 'test_pairs' in root.parts:
            raise ValueError('only public corpora are allowed')
        paths.extend([root] if root.is_file() else sorted(root.rglob('*.pdf')))
    pages = []
    original = reader.build_tables

    def capture(segments, fragments, *args, **kwargs):
        if segments and fragments and len(pages) < max_pages:
            pages.append(copy.deepcopy((segments, fragments, kwargs.get('short_segments') or [])))
        return tables._build_tables_python(segments, fragments, *args, **kwargs)

    reader.build_tables = capture
    try:
        # Spread selection across corpora instead of taking only the first PDF.
        if len(paths) > max_pages * 2:
            random.Random(20261101).shuffle(paths)
        for path in paths:
            Dochan(str(path))
            if len(pages) >= max_pages:
                break
    finally:
        reader.build_tables = original
    return pages


def mutate(page, rng, kind):
    from dochan.pdf.paths import Segment
    segments, fragments, short = page
    segments, fragments, short = list(segments), list(fragments), list(short)
    tolerance = 1.5
    budget = rng.choice([0, 1, 3, 8, 50, 50000, 200000])
    if kind == 'original':
        return segments, fragments, short, tolerance, budget
    if kind == 'empty':
        return [], [], [], tolerance, budget
    if kind == 'shuffle':
        rng.shuffle(segments)
        rng.shuffle(fragments)
        rng.shuffle(short)
    elif kind == 'delete':
        if segments:
            del segments[rng.randrange(len(segments))]
        if fragments:
            del fragments[rng.randrange(len(fragments))]
    elif kind == 'add':
        if segments:
            segments.insert(rng.randrange(len(segments) + 1), rng.choice(segments))
        segments.append(Segment(rng.uniform(-10., 100.), 0., rng.uniform(100., 200.), 0.))
    elif kind == 'jitter':
        delta = rng.choice([-1e-9, 1e-9, -.5, .5, -1.5, 1.5])
        if segments:
            i = rng.randrange(len(segments))
            item = segments[i]
            segments[i] = replace(item, x0=item.x0 + delta, x1=item.x1 + delta)
        if fragments:
            i = rng.randrange(len(fragments))
            item = fragments[i]
            fragments[i] = replace(item, x=item.x + delta, y=item.y - delta)
    elif kind == 'boundary':
        tolerance = rng.choice([0., 1e-12, .5 - 1e-12, .5, .5 + 1e-12,
                                1.5 - 1e-12, 1.5, 1.5 + 1e-12, 8.])
    elif kind == 'direction':
        if fragments:
            i = rng.randrange(len(fragments))
            dx, dy, ux, uy = rng.choice([(1., 0., 0., 1.), (-1., 0., 0., 1.),
                                         (0., -1., 1., 0.), (0., 1., -1., 0.),
                                         (0., 0., 0., 0.), (1., 1., -1., 1.)])
            fragments[i] = replace(fragments[i], dir_x=dx, dir_y=dy, up_x=ux, up_y=uy)
    elif kind == 'duplicate':
        if fragments:
            fragments.extend([rng.choice(fragments)] * 2)
    elif kind == 'dash':
        if short:
            short.extend(short[:3])
            rng.shuffle(short)
        else:
            short = [Segment(float(i), 20., i + .5, 20.) for i in range(30)]
    elif kind == 'huge':
        # Dense input exercises snapping and cell-budget rejection before
        # allocating a grid (snapping may reduce the intersection count).
        segments = [Segment(0., float(i), 1500., float(i)) for i in range(1500)]
        segments += [Segment(float(i), 0., float(i), 1500.) for i in range(1500)]
        fragments = fragments[:1]
    return segments, fragments, short, tolerance, budget


def run_case(function, case, bailout=None):
    from dochan.pdf import tables
    segments, fragments, short, tolerance, remaining = case
    warnings = ['existing warning']
    budget = tables.TableBudget(remaining)
    try:
        result = function(segments, fragments, tolerance, 7, warnings, budget, short)
    except Exception as exc:
        if bailout is not None and isinstance(exc, bailout):
            # The direct native entry point must not publish an incomplete attempt.
            assert warnings == ['existing warning'], 'Bailout changed warnings'
            assert budget.remaining == remaining, 'Bailout spent budget'
            return 'bailout', None
        return 'error', (type(exc).__module__, type(exc).__qualname__, str(exc),
                         exact(warnings), exact(budget))
    return 'ok', (exact(result), exact(warnings), exact(budget))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', nargs='*', default=[])
    parser.add_argument('--capture-cache', type=Path)
    parser.add_argument('--max-pages', type=int, default=96)
    parser.add_argument('--cases', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=20261101)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    from dochan.pdf import tables
    native = importlib.import_module('dochan.pdf._ctables')
    if args.capture_cache and args.capture_cache.exists():
        # A locally generated cache only; never deserialize downloaded files.
        with args.capture_cache.open('rb') as handle:
            pages = pickle.load(handle)
    else:
        pages = capture_pages(args.corpus, args.max_pages)
        if args.capture_cache:
            with args.capture_cache.open('wb') as handle:
                pickle.dump(pages, handle, protocol=4)
    real_count = len(pages)
    synthetic = synthetic_pages()
    if not pages:
        pages = synthetic
    rng = random.Random(args.seed)
    counts = Counter()
    kinds = ['original', 'shuffle', 'delete', 'add', 'jitter', 'boundary',
             'direction', 'duplicate', 'dash', 'empty']
    started = time.monotonic()
    for index in range(args.cases):
        # Real full pages regularly; small real crops and complete synthetic
        # tables keep 100k mutations affordable without reducing guard coverage.
        if index % 1000 == 999:
            kind, page = 'huge', synthetic[index % len(synthetic)]
        elif index % 5 == 0:
            kind, page = rng.choice(kinds), rng.choice(synthetic)
        else:
            kind, page = rng.choice(kinds), rng.choice(pages)
            if index % 20:
                s, f, d = page
                page = (s[:rng.randint(8, 36)], f[:rng.randint(8, 48)], d[:32])
        case = mutate(page, rng, kind)
        before = exact(case)
        expected = run_case(tables._build_tables_python, case)
        actual = run_case(native.build_tables, case, native.Bailout)
        if actual[0] == 'bailout':
            counts['bailout'] += 1
            actual = run_case(tables.build_tables, case)
        else:
            counts['native'] += 1
            if actual[0] == 'ok' and actual[1][0][1]:
                counts['native_nonempty'] += 1
        if actual != expected or exact(case) != before:
            report = {'cases': index + 1, 'seed': args.seed, 'mismatch_index': index,
                      'kind': kind, 'expected_status': expected[0], 'actual_status': actual[0],
                      'input_mutated': exact(case) != before, 'counts': dict(counts)}
            args.output.write_text(json.dumps(report, indent=2))
            raise AssertionError(f'table mismatch at case {index}, mutation {kind}')
        counts[kind] += 1
        if index % 10000 == 9999:
            print(json.dumps({'cases': index + 1, 'seconds': time.monotonic() - started,
                              'counts': dict(counts)}), flush=True)
    if args.cases >= 1000 and not counts['native_nonempty']:
        raise AssertionError('no nonempty table output was exercised natively')
    report = {'cases': args.cases, 'seed': args.seed, 'real_pages': real_count,
              'synthetic_pages': len(synthetic), 'counts': dict(counts),
              'seconds': time.monotonic() - started, 'mismatches': 0}
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
