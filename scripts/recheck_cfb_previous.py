"""Replay earlier CFB discrepancies against a public corpus without copying it.

Run ``python -m scripts.recheck_cfb_previous CORPUS PREVIOUS_ARTIFACTS --output FILE``.
The previous directory supplies cfb-discrepancy-classification.json and
cfb-conversion-classification.json. Only previously different conversions run.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib
import json
from pathlib import Path

from scripts.audit_cfb_defects import public_relative
from scripts.compare_cfb_olefile import bounded_results, discover_ole


def map_previous(paths, previous_rows, corpus):
    """Require exactly one public candidate per previous filename and byte size."""
    corpus = Path(corpus).resolve()
    index = defaultdict(list)
    for new_id, name in enumerate(paths):
        path = Path(name).resolve()
        relative = public_relative(path, corpus)
        index[path.name, path.stat().st_size].append((new_id, path, relative))
    result = {}
    for prior in previous_rows:
        candidates = index[prior['filename'], prior['file_size']]
        if len(candidates) != 1:
            raise ValueError('previous corpus identity must have one unique candidate')
        if prior['id'] in result:
            raise ValueError('previous corpus IDs must be unique')
        new_id, path, relative = candidates[0]
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        result[prior['id']] = {
            'old_id': prior['id'], 'new_id': new_id,
            'file': relative,
            'file_size': prior['file_size'], 'sha256': digest.hexdigest(),
            'prior_status': prior['status'],
            'prior_native_reason': prior.get('native_reason'),
        }
    return result


def replay(corpus, previous, jobs=2, timeout=30, memory_mb=1536):
    """Return public identities and bounded container/conversion comparisons."""
    corpus, previous = Path(corpus).resolve(), Path(previous)
    discrepancy_name = 'cfb-discrepancy-classification.json'
    conversion_name = 'cfb-conversion-classification.json'
    discrepancies = json.loads((previous / discrepancy_name).read_text(encoding='utf-8'))
    conversions = json.loads((previous / conversion_name).read_text(encoding='utf-8'))
    roots = []
    for item in conversions['roots']:
        root = (corpus / item['root']).resolve()
        public_relative(root, corpus)
        roots.append(root)
    paths = discover_ole(roots)
    rows = map_previous(paths, discrepancies['rows'], corpus)
    report = {'discovered': len(paths), 'seed': 20261003, 'jobs': jobs,
              'timeout_seconds': timeout, 'memory_mb': memory_mb,
              'mapping': 'unique filename and byte size within the prior public corpus roots',
              'prior_artifacts': [discrepancy_name, conversion_name]}
    try:
        importlib.import_module('olefile')
    except ImportError:
        report['skipped'] = 'optional_reference_olefile_not_installed'
        return report
    tasks = [('compare', old_id, paths[row['new_id']], timeout, report['seed'])
             for old_id, row in rows.items()]
    for result in bounded_results(tasks, jobs, timeout, memory_mb):
        rows[result['id']]['current_container'] = result
    selected = {row['conversion_id']: row for row in conversions['rows']
                if row['conversion_status'] == 'different'}
    tasks = [('convert', old_id, paths[rows[row['cfb_id']]['new_id']], timeout, report['seed'])
             for old_id, row in selected.items()]
    results = []
    for result in bounded_results(tasks, jobs, timeout, memory_mb):
        prior = selected[result['id']]
        target = rows[prior['cfb_id']]
        result.update(old_conversion_id=prior['conversion_id'], old_cfb_id=prior['cfb_id'],
                      new_cfb_id=target['new_id'], file=target['file'],
                      prior_native_reason=target['prior_native_reason'],
                      prior_container_status=prior['container_status'],
                      current_container_status=target['current_container']['status'])
        results.append(result)
    report.update(
        prior_container_counts=dict(Counter(row['prior_status'] for row in rows.values())),
        current_container_counts=dict(Counter(row['current_container']['status'] for row in rows.values())),
        conversion_counts=dict(Counter(row['status'] for row in results)),
        containers=sorted(rows.values(), key=lambda row: row['old_id']),
        conversions=sorted(results, key=lambda row: row['old_conversion_id']),
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path, help='Public corpus root only')
    parser.add_argument('previous_artifacts', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--memory-mb', type=int, default=1536)
    args = parser.parse_args()
    if args.jobs < 1 or args.timeout <= 0 or args.memory_mb < 128:
        parser.error('positive limits are required (memory >= 128 MiB)')
    report = replay(args.corpus, args.previous_artifacts, args.jobs, args.timeout, args.memory_mb)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items()
                      if key in ('current_container_counts', 'conversion_counts', 'skipped')}))


if __name__ == '__main__':
    main()
