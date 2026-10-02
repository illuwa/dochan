"""공개 HWP/HWPX의 구간 분포와 공개 API 출력 해시를 읽기 전용으로 측정한다.

예: python -m scripts.probe_hwp_runs corpus/hwp-public --output results.json
--source-root로 별도 HEAD 소스를 지정하고 --compare로 이전 결과와 비교한다.
본문과 바이너리는 저장하지 않으며, 공개 파일명과 수치 및 SHA-256만 기록한다.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import fields, is_dataclass
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import sys
import time


_OBSERVATIONS = None


def _install_observers():
    from dochan.hwp.section import SectionParser
    from dochan.hwp.records.para_text import parse_para_text
    from dochan.hwpx.parser import HWPXParser

    original_hwp = SectionParser._parse_paragraph_group_impl

    def hwp(self, node):
        pairs = characters = 0
        for child in node['children']:
            record = child['record']
            if record.tag_id == 68:
                pairs = len(record.data) // 8
            elif record.tag_id == 67:
                characters = len(parse_para_text(record.data)['text'])
        _OBSERVATIONS['pairs'].append(pairs)
        _OBSERVATIONS['characters'].append(characters)
        return original_hwp(self, node)

    original_hwpx = HWPXParser._parse_paragraph_elem

    def hwpx(self, element):
        runs = [child for child in element if child.tag.endswith('}run')]
        _OBSERVATIONS['pairs'].append(len(runs))
        _OBSERVATIONS['characters'].append(sum(
            len(''.join(text.itertext())) for run in runs for text in run
            if text.tag.endswith('}t')))
        return original_hwpx(self, element)

    SectionParser._parse_paragraph_group_impl = hwp
    HWPXParser._parse_paragraph_elem = hwpx
    if hasattr(HWPXParser, '_limit_body_nodes'):
        original_limit = HWPXParser._limit_body_nodes

        def body_nodes(self, root):
            before = self._body_nodes_remaining
            original_limit(self, root)
            _OBSERVATIONS['body_nodes_reserved'] += before - self._body_nodes_remaining

        HWPXParser._limit_body_nodes = body_nodes


def _model_runs(document):
    from dochan.model.document import TextRun
    seen = set()
    todo = [document]
    count = 0
    while todo:
        value = todo.pop()
        if id(value) in seen:
            continue
        if isinstance(value, TextRun):
            seen.add(id(value))
            count += 1
        elif is_dataclass(value):
            seen.add(id(value))
            todo.extend(getattr(value, field.name) for field in fields(value))
        elif isinstance(value, (tuple, list)):
            seen.add(id(value))
            todo.extend(value)
        elif isinstance(value, dict):
            seen.add(id(value))
            todo.extend(value.values())
    return count


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _probe(path):
    from dochan import Dochan
    global _OBSERVATIONS
    _OBSERVATIONS = {'pairs': [], 'characters': [], 'body_nodes_reserved': 0}
    started = time.monotonic()
    result = {'file': path.parent.name + '/' + path.name,
              'format': path.suffix[1:].lower()}
    try:
        reader = Dochan(path)
        result.update(runs=_model_runs(reader.doc),
                      paragraphs=len(reader.doc.find_all('paragraph')),
                      notes=len(reader.doc.find_all('note')),
                      markdown_sha256=_digest(reader.to_markdown()),
                      json_sha256=_digest(reader.to_json()),
                      errors_sha256=_digest(json.dumps(reader.errors, ensure_ascii=False)),
                      error_count=len(reader.errors))
        for metric, values in _OBSERVATIONS.items():
            if metric == 'body_nodes_reserved':
                result[metric] = values
                continue
            result[metric + '_histogram'] = dict(Counter(values))
            result[metric + '_top20'] = sorted(
                enumerate(values), key=lambda item: (-item[1], item[0]))[:20]
    except Exception as error:
        result['probe_failure'] = type(error).__name__ + ': ' + str(error)
    result['seconds'] = round(time.monotonic() - started, 4)
    return result


def _distribution(histogram, top):
    total = sum(histogram.values())
    result = {'observations': total, 'maximum': max(histogram, default=0),
              'top20': sorted(top, key=lambda item: (-item['value'], item['file'], item.get('paragraph', 0)))[:20]}
    for percentile in (50, 90, 95, 99, 99.9):
        target = math.ceil(total * percentile / 100)
        cumulative = 0
        result['p' + str(percentile)] = 0
        for value, count in sorted(histogram.items()):
            cumulative += count
            if cumulative >= target:
                result['p' + str(percentile)] = value
                break
    return result


def _summarize(rows):
    summary = {}
    for kind in ('hwp', 'hwpx'):
        selected = [row for row in rows if row['format'] == kind]
        valid = [row for row in selected if 'probe_failure' not in row]
        stats = {'files': len(selected), 'completed': len(valid),
                 'probe_failures': len(selected) - len(valid),
                 'documents_with_errors': sum(row['error_count'] > 0 for row in valid)}
        for metric in ('pairs', 'characters'):
            histogram = Counter()
            top = []
            for row in valid:
                histogram.update({int(k): v for k, v in row[metric + '_histogram'].items()})
                top.extend({'file': row['file'], 'paragraph': index, 'value': value}
                           for index, value in row[metric + '_top20'])
            stats[metric] = _distribution(histogram, top)
        stats['runs'] = _distribution(Counter(row['runs'] for row in valid),
                                     [{'file': row['file'], 'value': row['runs']} for row in valid])
        stats['paragraphs_and_notes'] = _distribution(
            Counter(row['paragraphs'] + row['notes'] for row in valid),
            [{'file': row['file'], 'value': row['paragraphs'] + row['notes']} for row in valid])
        stats['body_nodes_reserved_max'] = max((row.get('body_nodes_reserved', 0) for row in valid), default=0)
        summary[kind] = stats
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--source-root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    _install_observers()
    paths = sorted(path for kind in ('hwp', 'hwpx')
                   for path in (args.corpus / kind).rglob('*')
                   if path.is_file() and path.suffix.lower() in ('.hwp', '.hwpx'))
    if args.limit:
        paths = paths[:args.limit]
    rows = []
    started = time.monotonic()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix('.jsonl').open('w', encoding='utf-8') as journal:
        with ProcessPoolExecutor(max_workers=args.workers,
                                 mp_context=multiprocessing.get_context('fork')) as pool:
            futures = [pool.submit(_probe, path) for path in paths]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                journal.write(json.dumps(row, ensure_ascii=False) + '\n')
                journal.flush()
                if len(rows) % 100 == 0:
                    print('{}/{} {:.1f}s'.format(len(rows), len(paths), time.monotonic() - started), flush=True)
    rows.sort(key=lambda row: (row['format'], row['file']))
    result = {'summary': _summarize(rows), 'seconds': round(time.monotonic() - started, 3), 'documents': rows}
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding='utf-8'))
        old = {(row['format'], row['file']): row for row in baseline['documents']}
        changed = []
        for row in rows:
            before = old.get((row['format'], row['file']), {})
            differences = [key for key in ('markdown_sha256', 'json_sha256', 'errors_sha256', 'probe_failure')
                           if before.get(key) != row.get(key)]
            if differences:
                changed.append({'file': row['file'], 'format': row['format'], 'differences': differences})
        current_keys = {(row['format'], row['file']) for row in rows}
        missing = [{'format': kind, 'file': name}
                   for kind, name in sorted(set(old) - current_keys)]
        result['comparison'] = {
            'baseline_files': len(old), 'current_files': len(rows),
            'changed': changed, 'changed_count': len(changed), 'missing': missing,
            'identical': not changed and not missing and len(old) == len(rows),
            'formats': {
                kind: {'files': sum(row['format'] == kind for row in rows),
                       'changed': sum(row['format'] == kind for row in changed),
                       'missing': sum(row['format'] == kind for row in missing)}
                for kind in ('hwp', 'hwpx')},
        }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'summary': result['summary'], 'comparison': result.get('comparison')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
