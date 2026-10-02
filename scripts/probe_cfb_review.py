"""Compare complete public-corpus conversion outputs between two source trees.

``snapshot CORPUS --tree TREE --output snapshot.json`` runs every CFB input in
isolated, time-bounded workers. ``compare OLD NEW --corpus CORPUS --output FILE``
adds independent numeric byte evidence only for changed files. No document text
is written. The explicit public roots prevent accidental internal-file reports.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import resource
import random
import struct
import subprocess
import sys
import threading
import time

MAGIC = bytes.fromhex('d0cf11e0a1b11ae1')
PUBLIC_ROOTS = ('poi-src/test-data/document', 'poi-src/test-data/slideshow',
                'poi-src/test-data/spreadsheet', 'lo-src', 'tika-test-docs',
                'hwp-public/hwp')
MAX_INPUT = 512 * 1024 * 1024


def discover_public(corpus):
    corpus = Path(corpus).resolve()
    found = set()
    for sub in PUBLIC_ROOTS:
        root = corpus / sub
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(root)
                with resolved.open('rb') as source:
                    if source.read(8) == MAGIC:
                        found.add(resolved.relative_to(corpus).as_posix())
            except (OSError, ValueError):
                continue
    return sorted(found)


def discover_opus_sample(corpus, hwp_count=400):
    """Reproduce the review's all-Office + DIFAT + seeded HWP selection."""
    corpus = Path(corpus).resolve()
    allowed = set(discover_public(corpus))
    office, hwp, difat = [], [], []
    for sub in PUBLIC_ROOTS:
        for directory, dirs, names in os.walk(corpus / sub):
            dirs.sort()
            for name in sorted(names):
                path = Path(directory) / name
                relative = path.relative_to(corpus).as_posix()
                if relative not in allowed:
                    continue
                if sub != 'hwp-public/hwp':
                    office.append(relative)
                    continue
                with path.open('rb') as source:
                    header = source.read(76)
                if len(header) >= 76 and struct.unpack_from('<I', header, 72)[0]:
                    difat.append(relative)
                else:
                    hwp.append(relative)
    return office + difat + random.Random(4242).sample(hwp, min(hwp_count, len(hwp)))


def select_paths(corpus, selection='all', manifest=None):
    if manifest is None:
        return (discover_opus_sample(corpus) if selection == 'opus'
                else discover_public(corpus))
    paths = json.loads(Path(manifest).read_text())
    if (not isinstance(paths, list) or any(not isinstance(p, str) for p in paths)
            or len(paths) != len(set(paths))):
        raise ValueError('manifest must be a unique list of public relative paths')
    allowed = set(discover_public(corpus))
    if any(path not in allowed for path in paths):
        raise ValueError('manifest contains a missing or nonpublic path')
    return paths


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def worker(tree, path):
    sys.path.insert(0, str(Path(tree).resolve()))
    from dochan import Dochan
    if Path(path).stat().st_size > MAX_INPUT:
        return {'status': 'input_limit'}
    try:
        doc = Dochan(path)
        parts = {'markdown': doc.to_markdown(), 'json': doc.to_json(),
                 'errors': json.dumps(list(doc.errors), ensure_ascii=False)}
        return {'status': 'converted', 'hashes': {k: digest(v) for k, v in parts.items()},
                'error_count': len(doc.errors)}
    except MemoryError:
        return {'status': 'memory_limit'}
    except Exception as exc:
        # Preserve equality without leaking error text or document content.
        return {'status': 'exception', 'exception_type': type(exc).__name__,
                'exception_hash': digest(str(exc))}


def run_one(tree, path, timeout, worker_script=None, memory_mb=1536):
    script = Path(worker_script) if worker_script else Path(__file__).resolve()
    try:
        result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
            [sys.executable, str(script), '_worker', str(tree), str(path), str(memory_mb)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
            check=False)
    except subprocess.TimeoutExpired:
        return {'status': 'timeout'}
    if result.returncode == 75:
        return {'status': 'memory_limit'}
    if result.returncode:
        return {'status': 'worker_exit', 'returncode': result.returncode}
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError):
        return {'status': 'invalid_worker_output'}


def bound_worker_memory(memory_mb):
    """Enforce RSS on Darwin too, where RLIMIT_AS is not reliably supported."""
    limit = memory_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_DATA, (limit, limit))
        if sys.platform != 'darwin':
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (OSError, ValueError):
        pass

    def check():
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if (peak if sys.platform == 'darwin' else peak * 1024) > limit:
            os._exit(75)

    check()

    def watch():
        while True:
            check()
            time.sleep(0.05)

    threading.Thread(target=watch, daemon=True).start()


def damage_evidence(findings):
    """Separate address damage from metadata deviations seen in normal files."""
    benign = {'allocation_marker', 'difat_unused_slots', 'difat_terminator',
              'directory_color', 'stream_child_pointer', 'allocation_unused_tail_crosslink',
              'orphan_live_entries', 'unused_minifat_count', 'unused_fat_outside',
              'byte_order', 'partial_last_sector'}
    evidence = []
    for item in findings:
        code = item['code']
        if code in benign:
            continue
        if code == 'chain_length' and item['actual'] >= item['expected']:
            continue
        if code.startswith('directory_name_') and item.get('entry') == 0:
            continue
        evidence.append(item)
    return evidence


def compare_runs(baseline, current):
    summary = Counter(total=len(set(baseline) | set(current)))
    changes = []
    for path in sorted(set(baseline) | set(current)):
        old, new = baseline.get(path, {}), current.get(path, {})
        if (not old or not new or old.get('status') not in (None, 'converted', 'exception')
                or new.get('status') not in (None, 'converted', 'exception')):
            summary['unverified'] += 1
            changes.append({'path': path, 'baseline': old, 'current': new,
                            'differences': ['unverified'], 'damage': new.get('damage', [])})
            continue
        differences = [key for key in ('markdown', 'json', 'errors')
                       if old.get('hashes', {}).get(key) != new.get('hashes', {}).get(key)]
        if ((old.get('exception_type'), old.get('exception_hash')) !=
                (new.get('exception_type'), new.get('exception_hash'))):
            differences.append('exception')
        if not differences:
            summary['equal'] += 1
            continue
        summary['changed'] += 1
        if 'errors' in differences:
            summary['errors_changed'] += 1
            suffix = 'with_damage_evidence' if new.get('damage') else 'without_damage_evidence'
            summary['errors_changed_' + suffix] += 1
        changes.append({'path': path, 'differences': differences,
                        'baseline': old, 'current': new, 'damage': new.get('damage', [])})
    for key in ('equal', 'changed', 'unverified', 'errors_changed',
                'errors_changed_with_damage_evidence', 'errors_changed_without_damage_evidence'):
        summary.setdefault(key, 0)
    return {'summary': dict(summary), 'changes': changes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='mode', required=True)
    snap = subs.add_parser('snapshot')
    snap.add_argument('corpus', type=Path)
    snap.add_argument('--tree', type=Path, required=True)
    snap.add_argument('--output', type=Path, required=True)
    snap.add_argument('--jobs', type=int, default=8)
    snap.add_argument('--selection', choices=('all', 'opus'), default='all')
    snap.add_argument('--paths', type=Path, help='JSON list of public corpus-relative paths')
    snap.add_argument('--label', default='', help='Source commit or baseline label')
    snap.add_argument('--timeout', type=float, default=120)
    snap.add_argument('--memory-mb', type=int, default=1536)
    compare = subs.add_parser('compare')
    compare.add_argument('baseline', type=Path)
    compare.add_argument('current', type=Path)
    compare.add_argument('--corpus', type=Path, required=True)
    compare.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.mode == 'snapshot':
        if args.jobs < 1 or args.timeout <= 0 or args.memory_mb < 1:
            parser.error('jobs, timeout and memory-mb must be positive')
        files = select_paths(args.corpus, args.selection, args.paths)
        print('CFB inputs: %d' % len(files), flush=True)
        results = {}
        with ThreadPoolExecutor(args.jobs) as pool:
            outcomes = pool.map(lambda p: run_one(args.tree.resolve(), args.corpus.resolve() / p,
                                                 args.timeout, memory_mb=args.memory_mb), files)
            for path, result in zip(files, outcomes):
                results[path] = result
                if len(results) % 500 == 0:
                    print('completed: %d/%d' % (len(results), len(files)), flush=True)
        report = {'roots': PUBLIC_ROOTS, 'source_label': args.label,
                  'selection': 'manifest' if args.paths else args.selection, 'results': results,
                  'summary': dict(Counter(r['status'] for r in results.values()))}
    else:
        old_snapshot = json.loads(args.baseline.read_text())
        new_snapshot = json.loads(args.current.read_text())
        old, new = old_snapshot['results'], new_snapshot['results']
        from scripts.audit_cfb_defects import audit_bytes
        changed = compare_runs(old, new)['changes']
        allowed = set(discover_public(args.corpus))
        for row in changed:
            path = row['path']
            if path not in allowed or path not in new:
                continue
            with (args.corpus / path).open('rb') as source:
                data = source.read(MAX_INPUT + 1)
            if len(data) <= MAX_INPUT:
                findings = audit_bytes(data)['findings']
                new[path]['raw_findings'] = findings
                new[path]['damage'] = damage_evidence(findings)
        report = compare_runs(old, new)
        report['baseline_label'] = old_snapshot.get('source_label', '')
        report['current_label'] = new_snapshot.get('source_label', '')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '_worker':
        bound_worker_memory(int(sys.argv[4]) if len(sys.argv) > 4 else 1536)
        print(json.dumps(worker(sys.argv[2], sys.argv[3]), ensure_ascii=False))
    else:
        main()
