"""공개 HWP/HWPX의 제목 판정을 기준 리비전과 메모리에서 대조한다.

기준 소스는 git archive로 만든 한 사본을 --baseline에 전달한다. 파일별
출력 본문은 저장하지 않고 두 파서를 차례로 실행해 해시와 요약만 기록한다.
"""

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path


def _marker_type(text):
    text = text.lstrip()
    if text.startswith(('□', '■')):
        return 'square'
    if re.match(r'(?:\d+(?:-\d+)?|[가나다라마바사아자차카타파하]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]+)[.)](?=\s|[<〈\[【])', text):
        return 'number'
    if text.startswith(('<', '〈', '[', '【')):
        return 'bracket'
    if text and unicodedata.category(text[0]) == 'Co':
        return 'pua'
    return 'other'


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _paragraphs(doc):
    stack = [(section, 's%d' % index)
             for index, section in reversed(list(enumerate(doc.sections)))]
    seen = set()
    while stack:
        element, path = stack.pop()
        if id(element) in seen:
            continue
        seen.add(id(element))
        if hasattr(element, 'heading_level'):
            yield path, element
        children = []
        for index, row in enumerate(getattr(element, 'rows', [])):
            for column, cell in enumerate(row):
                children.append((cell, '%s.r%d.c%d' % (path, index, column)))
        for field in ('elements', 'paragraphs', 'caption'):
            for index, child in enumerate(getattr(element, field, [])):
                children.append((child, '%s.%s%d' % (path, field, index)))
        stack.extend(reversed(children))


def inspect(path, root):
    from dochan import Dochan

    options = {'include_assets': False} if path.suffix.lower() == '.hwpx' else {}
    try:
        doc = Dochan(str(path), **options).doc
    except TypeError as exc:
        # 오래된 기준 리비전에는 include_assets 인자가 없다.
        if 'include_assets' not in str(exc):
            raise
        doc = Dochan(str(path)).doc
    from dochan.output.markdown import to_markdown

    paragraphs = list(_paragraphs(doc))
    markdown = to_markdown(doc)
    levels = [para.heading_level for _, para in paragraphs]
    try:
        for _, para in paragraphs:
            para.heading_level = 0
        neutral = to_markdown(doc)
    finally:
        for (_, para), level in zip(paragraphs, levels):
            para.heading_level = level
    body = [(' '.join(para.text.split()), para.heading_level)
            for key, para in paragraphs if re.fullmatch(r's\d+\.elements\d+', key)]
    return {
        'file': str(path.relative_to(root)),
        'levels': [(key, para.heading_level) for key, para in paragraphs],
        'body': body,
        'markdown_sha256': _digest(markdown),
        'neutral_sha256': _digest(neutral),
        'characters': len(markdown),
        'errors': list(doc.errors),
    }


def _paths(root):
    return sorted(path for path in root.rglob('*')
                  if path.is_file() and path.suffix.lower() in ('.hwp', '.hwpx'))


def stream(args):
    sys.path.insert(0, str(args.source_root.resolve()))
    for index, path in enumerate(_paths(args.root), 1):
        try:
            item = inspect(path, args.root)
        except Exception as exc:
            item = {'file': str(path.relative_to(args.root)),
                    'exception': type(exc).__name__ + ': ' + str(exc)}
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if index % 500 == 0:
            print('baseline %d' % index, file=sys.stderr, flush=True)


def compare(args):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    root = args.root.resolve()
    command = [sys.executable, str(Path(__file__).resolve()), 'stream',
               str(root), '--source-root', str(args.baseline.resolve())]
    child = subprocess.Popen(  # nosemgrep: dangerous-subprocess-use-audit
        command, stdout=subprocess.PIPE, text=True)
    stats = Counter()
    by_ext = {}
    pair_levels = {}
    changed_examples = []
    nonheading_examples = []
    promoted_sample = []
    marker_counts = Counter()
    rng = random.Random(20261004)
    try:
        for index, line in enumerate(child.stdout, 1):
            before = json.loads(line)
            path = root / before['file']
            extension = path.suffix.lower()
            group = by_ext.setdefault(extension, Counter())
            stats['files'] += 1
            group['files'] += 1
            try:
                after = inspect(path, root)
            except Exception as exc:
                after = {'exception': type(exc).__name__ + ': ' + str(exc)}
            if 'exception' in before or 'exception' in after:
                group['exceptions'] += 1
                stats['exceptions'] += 1
                group['baseline_exceptions'] += 'exception' in before
                group['current_exceptions'] += 'exception' in after
                group['new_exceptions'] += 'exception' not in before and 'exception' in after
                continue
            if before['neutral_sha256'] != after['neutral_sha256']:
                group['nonheading_markdown_changes'] += 1
                if len(nonheading_examples) < 30 and not args.private:
                    nonheading_examples.append(before['file'])
            if before['markdown_sha256'] != after['markdown_sha256']:
                group['markdown_changes'] += 1
                if len(changed_examples) < 8 and not args.private:
                    changed_examples.append(before['file'])
            old = dict(before['levels'])
            new = dict(after['levels'])
            if old.keys() != new.keys():
                group['paragraph_path_changes'] += 1
            for key in old.keys() & new.keys():
                previous, current = old[key], new[key]
                if previous and not current:
                    group['heading_to_body'] += 1
                elif not previous and current:
                    group['body_to_heading'] += 1
                elif previous and current and previous != current:
                    group['level_change'] += 1
            group['paragraphs_before'] += len(before['levels'])
            group['paragraphs_after'] += len(after['levels'])
            group['headings_before'] += sum(bool(level) for _, level in before['levels'])
            group['headings_after'] += sum(bool(level) for _, level in after['levels'])
            group['body_paragraphs_before'] += len(before['body'])
            group['body_paragraphs_after'] += len(after['body'])
            group['body_headings_before'] += sum(bool(level) for _, level in before['body'])
            group['body_headings_after'] += sum(bool(level) for _, level in after['body'])
            if before['errors'] != after['errors']:
                group['error_changes'] += 1
            if args.pairs:
                stem = unicodedata.normalize('NFC', path.stem)
                row = pair_levels.setdefault(stem, {})
                row[extension] = (before['body'], after['body'])
            if not args.private:
                for (old_text, old_level), (new_text, new_level) in zip(
                        before['body'], after['body']):
                    if old_text != new_text or old_level or not new_level:
                        continue
                    marker_counts[_marker_type(new_text)] += 1
                    seen = sum(marker_counts.values())
                    sample = {'file': before['file'], 'text': new_text[:40],
                              'level': new_level}
                    if len(promoted_sample) < 60:
                        promoted_sample.append(sample)
                    else:
                        slot = rng.randrange(seen)
                        if slot < 60:
                            promoted_sample[slot] = sample
            if index % 500 == 0:
                print('compare %d' % index, file=sys.stderr, flush=True)
    finally:
        child.stdout.close()
        child.wait()
    pair_stats = Counter()
    for versions in pair_levels.values():
        if '.hwp' not in versions or '.hwpx' not in versions:
            continue
        pair_stats['pairs'] += 1
        for time_index, label in ((0, 'before'), (1, 'after')):
            hwp = versions['.hwp'][time_index]
            hwpx = versions['.hwpx'][time_index]
            answer = Counter((text, level) for text, level in hwpx if text)
            candidate = Counter((text, level) for text, level in hwp if text)
            answer_status = Counter((text, bool(level)) for text, level in hwpx if text)
            candidate_status = Counter((text, bool(level)) for text, level in hwp if text)
            texts_a = Counter(text for text, _ in hwpx if text)
            texts_b = Counter(text for text, _ in hwp if text)
            pair_stats[label + '_matched'] += sum((answer & candidate).values())
            pair_stats[label + '_status_matched'] += sum(
                (answer_status & candidate_status).values())
            pair_stats[label + '_common_text'] += sum((texts_a & texts_b).values())
    result = {'root': 'private' if args.private else str(root),
              'files': stats['files'], 'exceptions': stats['exceptions'],
              'formats': {key: dict(value) for key, value in by_ext.items()},
              'pairs': dict(pair_stats), 'changed_examples': changed_examples,
              'nonheading_examples': nonheading_examples,
              'promoted_markers': dict(marker_counts)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.sample_output and not args.private:
        args.sample_output.write_text(
            json.dumps(promoted_sample, ensure_ascii=False, indent=2), encoding='utf-8')
    if child.returncode:
        raise SystemExit(child.returncode)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='mode', required=True)
    scanner = sub.add_parser('stream')
    scanner.add_argument('root', type=Path)
    scanner.add_argument('--source-root', type=Path, required=True)
    scanner.set_defaults(func=stream)
    comparison = sub.add_parser('compare')
    comparison.add_argument('root', type=Path)
    comparison.add_argument('--baseline', type=Path, required=True)
    comparison.add_argument('--pairs', action='store_true')
    comparison.add_argument('--private', action='store_true')
    comparison.add_argument('--sample-output', type=Path)
    comparison.set_defaults(func=compare)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
