"""Reproduce CFB residual evidence using public corpus files and optional APIs.

Only hashes, lengths, numeric metadata and diagnostics are emitted; document
body contents are omitted. The reference package implementation is never read.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import signal

from scripts.audit_cfb_defects import public_relative
from scripts.compare_cfb_olefile import _backend, _snapshot, discover_ole, select_samples

CORPUS_ROOTS = ('hwp-public/hwp', 'poi-src/test-data/document',
                'poi-src/test-data/slideshow', 'poi-src/test-data/spreadsheet',
                'lo-src', 'tika-test-docs')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def conversion_evidence(path, module):
    from dochan import Dochan
    with _backend(module):
        doc = Dochan(path)
        markdown, raw = doc.to_markdown(), doc.to_json()
        obj = json.loads(raw)
        metadata = obj.get('metadata', {})
        metadata.pop('errors', None)
        result = {'markdown_length': len(markdown), 'markdown_hash': digest(markdown),
                  'json_hash': digest(raw), 'errors': list(doc.errors),
                  'json_without_errors_hash': digest(json.dumps(obj, ensure_ascii=False, sort_keys=True)),
                  'metadata_counts': {key: value for key, value in metadata.items()
                                      if isinstance(value, int) and not isinstance(value, bool)},
                  'source_format': metadata.get('source_format')}
        return result


def container_evidence(path, module):
    shot = _snapshot(module, path)
    if not shot['accepted']:
        return shot
    return {'accepted': True, 'streams': [
        {'path_hash': digest('/'.join(item['path'])),
         'size': item.get('size'), 'read_size': item.get('read_size'),
         'sha256': item.get('sha256'), 'error': item.get('error')}
        for item in shot['snapshot']['streams']]}


def _timeout(signum, frame):
    raise TimeoutError('residual probe time limit')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--compare', type=Path, required=True)
    parser.add_argument('--convert', type=Path, required=True)
    parser.add_argument('--previous', type=Path, help='optional exact previous-recheck report')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--per-format', type=int, default=300)
    parser.add_argument('--timeout', type=float, default=20)
    args = parser.parse_args(argv)
    if args.per_format < 1 or args.timeout <= 0:
        parser.error('positive sample count and timeout are required')
    report = {'conversions': [], 'containers': []}
    try:
        reference = importlib.import_module('olefile')
    except ModuleNotFoundError as exc:
        if exc.name != 'olefile':
            raise
        report['skipped'] = 'optional_reference_olefile_not_installed'
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        return 0
    native = importlib.import_module('dochan.cfb')
    compare = json.loads(args.compare.read_text(encoding='utf-8'))
    convert = json.loads(args.convert.read_text(encoding='utf-8'))
    paths = discover_ole([args.corpus / part for part in CORPUS_ROOTS])
    samples = select_samples(paths, args.per_format, convert['seed'])
    if len(paths) != compare['discovered'] or len(samples) != convert['scheduled']:
        raise ValueError('corpus/sample count differs from report; IDs cannot be reused')
    batches = [
        ('conversions', convert['records'], samples, conversion_evidence),
        ('containers', compare['records'], paths, container_evidence),
    ]
    if args.previous:
        prior = json.loads(args.previous.read_text(encoding='utf-8'))['conversions']
        selected = {}
        for row in prior:
            relative = Path(row['file'])
            if not relative.parts or relative.parts[0] != 'corpus':
                raise ValueError('previous report paths must be corpus-relative')
            path = args.corpus.joinpath(*relative.parts[1:])
            public_relative(path, args.corpus)
            selected[row['id']] = str(path)
        report['previous_conversions'] = []
        batches.append(('previous_conversions', prior, selected, conversion_evidence))
    previous = signal.signal(signal.SIGALRM, _timeout)
    try:
        for collection, records, selected, probe in batches:
            for row in records:
                if row['status'] == 'equal' or (collection != 'containers' and row['status'] != 'different'):
                    continue
                path = selected[row['id']]
                record = {'id': row['id'], 'path': public_relative(path, args.corpus),
                          'status': row['status'], 'differences': row.get('differences', [])}
                for label, module in (('reference', reference), ('native', native)):
                    signal.setitimer(signal.ITIMER_REAL, args.timeout)
                    try:
                        record[label] = probe(path, module)
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
                if collection != 'containers':
                    record['content_json_equal'] = (record['reference']['json_without_errors_hash']
                                                    == record['native']['json_without_errors_hash'])
                report[collection].append(record)
    finally:
        signal.signal(signal.SIGALRM, previous)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: len(value) for key, value in report.items()}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
