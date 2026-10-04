"""출력 전체를 저장하지 않고 Markdown·제목·첫 제목의 전후 변화를 집계한다.

사용법: python -m scripts.probe_pdf_heading_regression --public pdfjs=CORPUS
        --private internal=PRIVATE_CORPUS --output BEFORE.jsonl --repo SNAPSHOT
        --format pdf
다시 실행할 때 --baseline BEFORE.jsonl 을 주면 집계도 출력한다.
내부 문서 이름·본문·경고 원문은 저장하지 않는다. 같은 파일 집합·정렬 순서로 비교한다.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

MAX_HEADING_RECORDS = 200_000


def digest(text):
    return hashlib.sha256(text.encode('utf-8', 'replace')).hexdigest()


def document_record(doc, markdown):
    from dochan.model.document import Paragraph

    headings = []
    paragraphs = 0
    heading_count = 0
    first = None
    for section in doc.sections:
        for para in section.elements:
            if not isinstance(para, Paragraph):
                continue
            if para.heading_level:
                text_hash = digest(para.text)
                if first is None:
                    first = text_hash
                heading_count += 1
                if len(headings) < MAX_HEADING_RECORDS:
                    headings.append([paragraphs, text_hash, para.heading_level])
            paragraphs += 1
    return {'hash': digest(markdown), 'chars': len(markdown), 'headings': headings,
            'heading_count': heading_count, 'first': first,
            'text': digest(''.join(para.text for section in doc.sections for para in section.elements
                                 if isinstance(para, Paragraph))),
            'errors': digest(json.dumps(doc.errors, ensure_ascii=False)), 'error_count': len(doc.errors),
            'truncated': heading_count > MAX_HEADING_RECORDS}


def child(path, repo):
    if repo:
        sys.path.insert(0, str(repo.resolve()))
    from dochan import Dochan

    try:
        parsed = Dochan(str(path))
        return document_record(parsed.doc, parsed.to_markdown())
    except Exception as exc:
        return {'exception': type(exc).__name__}


def collect(job, repo, timeout):
    group, index, public_name, path = job
    command = [sys.executable, '-m', 'scripts.probe_pdf_heading_regression', '--child', str(path)]
    if repo:
        command.extend(('--repo', str(repo)))
    try:
        # nosemgrep: dangerous-subprocess-use-audit
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        result = json.loads(process.stdout) if process.returncode == 0 else {'exception': 'worker_failed'}
    except subprocess.TimeoutExpired:
        result = {'exception': 'timeout'}
    except (OSError, ValueError):
        result = {'exception': 'worker_failed'}
    result.update(group=group, id=index, file=public_name)
    return result


def compare_records(before, after):
    baseline = {(record['group'], record['id']): record for record in before}
    output = defaultdict(lambda: defaultdict(int))
    seen = set()
    for current in after:
        key = current['group'], current['id']
        if key in seen:
            raise ValueError('duplicate record')
        seen.add(key)
        previous = baseline.get(key)
        if previous is None or previous['file'] != current['file']:
            raise ValueError('different corpus inventory')
        counts = output[key[0]]
        counts['files'] += 1
        if previous.get('exception') or current.get('exception'):
            counts['exceptions'] += 1
            continue
        counts['markdown_changed'] += previous['hash'] != current['hash']
        counts['headings_before'] += previous['heading_count']
        counts['headings_after'] += current['heading_count']
        counts['first_changed'] += previous['first'] != current['first']
        counts['new_first'] += previous['first'] is None and current['first'] is not None
        counts['errors_changed'] += previous['errors'] != current['errors']
        if previous.get('text') and current.get('text'):
            counts['text_changed'] += previous['text'] != current['text']
        old_size = {tuple(row) for row in previous['headings'] if row[2] in (1, 2)}
        new_size = {tuple(row) for row in current['headings'] if row[2] in (1, 2)}
        counts['size_headings_changed'] += len(old_size ^ new_size)
        counts['truncated'] += bool(previous.get('truncated') or current.get('truncated'))
    if seen != baseline.keys():
        raise ValueError('different corpus inventory')
    return {group: dict(counts) for group, counts in output.items()}


def _root(value):
    group, separator, root = value.partition('=')
    if not separator or not group or not root:
        raise argparse.ArgumentTypeError('use GROUP=ROOT')
    return group, Path(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', action='append', type=_root, default=[])
    parser.add_argument('--private', action='append', type=_root, default=[])
    parser.add_argument('--format', action='append', choices=('pdf', 'hwp', 'hwpx'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--child', type=Path)
    args = parser.parse_args(argv)
    if args.child:
        print(json.dumps(child(args.child, args.repo), ensure_ascii=False))
        return 0
    if not args.output or not (args.public or args.private) or args.workers < 1 or args.timeout < 1:
        parser.error('roots, output and positive workers/timeout are required')
    groups = [group for group, _root in args.public + args.private]
    if len(groups) != len(set(groups)):
        parser.error('group names must be unique')
    jobs = []
    formats = set(args.format or ['pdf'])
    for public, roots in ((True, args.public), (False, args.private)):
        for group, root in roots:
            paths = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower().lstrip('.') in formats)
            jobs.extend((group, index, str(path.relative_to(root)) if public else '', path)
                        for index, path in enumerate(paths))
    with args.output.open('w', encoding='utf-8') as stream, ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, result in enumerate(pool.map(lambda job: collect(job, args.repo, args.timeout), jobs), 1):
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
            if index % 100 == 0:
                stream.flush()
                print('%d/%d' % (index, len(jobs)), file=sys.stderr, flush=True)
    if args.baseline:
        before = [json.loads(line) for line in args.baseline.read_text(encoding='utf-8').splitlines()]
        after = [json.loads(line) for line in args.output.read_text(encoding='utf-8').splitlines()]
        print(json.dumps(compare_records(before, after), ensure_ascii=False, indent=2))
    return int(not jobs)


if __name__ == '__main__':
    raise SystemExit(main())
