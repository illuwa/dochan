"""공개 표본을 경로 SHA-1 순으로 골라 두 리비전의 Markdown을 비교한다.

snapshot은 지정한 소스의 리더와 작성기를 함께 실행한다. compare는 이미 설치된
markdown-it-py를 검증에만 쓰며 본문 손실, 별표 증가 묶음, 빈 그림 참조를 센다.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import difflib
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import signal
import sys


FORMATS = ('docx', 'pptx', 'xlsx', 'hwp', 'hwpx', 'pdf', 'doc', 'ppt')
PUBLIC_ROOTS = ('hwp-public', 'lo-src', 'poi-src', 'pdfjs-src', 'tika-test-docs', 'generated')
MAX_SAVED_MARKDOWN = 16 * 1024 * 1024


def text_digest(text):
    digest = hashlib.sha256()
    for start in range(0, len(text), 1024 * 1024):
        digest.update(text[start:start + 1024 * 1024].encode())
    return digest.hexdigest()


def select(corpus):
    files = {fmt: [] for fmt in FORMATS}
    for name in PUBLIC_ROOTS:
        for path in (corpus / name).rglob('*'):
            fmt = path.suffix.lower().lstrip('.')
            if fmt in files and path.is_file() and path.stat().st_size <= 5 * 1024 * 1024:
                files[fmt].append(path.relative_to(corpus).as_posix())
    for fmt, paths in files.items():
        paths.sort(key=lambda p: hashlib.sha1(p.encode()).hexdigest())
        files[fmt] = paths if fmt in ('doc', 'ppt') else paths[:160]
    return files


def _timeout(*_args):
    raise TimeoutError('document timeout')


def snapshot_one(args):
    source, corpus, relative, output = args
    sys.path.insert(0, source)
    from dochan import Dochan
    import dochan
    if not Path(dochan.__file__).resolve().is_relative_to(Path(source).resolve()):
        raise RuntimeError('wrong parser source')
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(60)
    result = {'path': relative, 'status': 'ok'}
    text = ''
    try:
        path = Path(corpus) / relative
        result['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        document = Dochan(str(path))
        text = document.to_markdown()
        result['format'] = document.doc.source_format
        result['errors'] = len(document.doc.errors)
        result['parser_errors'] = sum(str(e).startswith('ERR') for e in document.doc.errors)
        images = document.doc.find_all('image')
        result['unnamed_image_data'] = sum(bool(i.image_data) and not i.filename for i in images)
        result['empty_images'] = sum(not i.image_data and not i.filename for i in images)
    except Exception as exc:
        result['status'] = type(exc).__name__
    finally:
        signal.alarm(0)
    key = hashlib.sha1(relative.encode()).hexdigest()
    result['key'] = key
    result['markdown_sha256'] = text_digest(text)
    result['empty_markdown'] = not bool(text.strip())
    result['has_image_opener'] = bool(re.search(r'!\[|<img\b', text))
    result['oversize_markdown_omitted'] = len(text) > MAX_SAVED_MARKDOWN
    if not result['oversize_markdown_omitted']:
        (Path(output) / (key + '.md')).write_text(text)
    return result


class _RenderedBody(HTMLParser):
    BLOCKS = frozenset(('p', 'div', 'br', 'hr', 'li', 'ul', 'ol', 'table', 'tr', 'td', 'th',
                        'blockquote', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section'))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.alts, self.targets = [], [], []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif not self.hidden:
            if tag == 'img':
                attr = dict(attrs)
                self.alts.append(attr.get('alt') or '')
                self.targets.append(attr.get('src') or '')
            elif tag in self.BLOCKS:
                self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif tag in self.BLOCKS and not self.hidden:
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def rendered(text, parser):
    """Measure actual rendered HTML, including raw HTML blocks and images.

    Use the reviewer's CommonMark + table + strikethrough dialect. Image alt is
    separate from visible body text; markup tags and script/style are excluded.
    """
    result = _RenderedBody()
    result.feed(parser.render(text))
    result.close()
    return ''.join(result.parts), result.alts, result.targets


def body_words(text):
    # Same normalization as Opus: whitespace tokens, excluding emphasis/escape
    # residue. Keep the unnormalized body hash separately for auditability.
    return Counter(word for token in text.split()
                   for word in [re.sub(r'[*\\]', '', token)] if word)


def compare_text(before, after, parser):
    if before == after and not re.search(r'!\[|<img\b', before):
        # Some XLSX outputs are hundreds of megabytes. Exact equality proves
        # zero regressions without asking an external renderer to parse them.
        # No image opener means no image reference to audit either.
        return {'lost_body_words': 0, 'stray_increase_hunks': 0,
                'rendered_stars': [None, None], 'body_sha256': [None, None],
                'images': [0, 0], 'empty_target_refs': [0, 0],
                'image_alts_with_stars': [0, 0], 'proof': 'identical Markdown, no image opener'}
    old, old_alts, old_targets = rendered(before, parser)
    new, new_alts, new_targets = ((old, old_alts, old_targets) if before == after
                                 else rendered(after, parser))
    lost = body_words(old) - body_words(new)
    increases = 0
    matcher = difflib.SequenceMatcher(None, before.split('\n\n'), after.split('\n\n'), autojunk=False)
    for op, i, j, k, m in ([] if before == after else matcher.get_opcodes()):
        if op == 'equal':
            continue
        left = rendered('\n\n'.join(matcher.a[i:j]), parser)[0]
        right = rendered('\n\n'.join(matcher.b[k:m]), parser)[0]
        increases += right.count('*') > left.count('*')
    return {
        'lost_body_words': sum(lost.values()),
        'stray_increase_hunks': increases,
        'rendered_stars': [old.count('*'), new.count('*')],
        'body_sha256': [hashlib.sha256(t.encode()).hexdigest() for t in (old, new)],
        'images': [len(old_targets), len(new_targets)],
        'empty_target_refs': [sum(t in ('', 'image') for t in targets)
                              for targets in (old_targets, new_targets)],
        'image_alts_with_stars': [sum('**' in a for a in alts) for alts in (old_alts, new_alts)],
    }


def compare(base, current, output):
    from markdown_it import MarkdownIt
    import markdown_it
    parser = MarkdownIt('commonmark', {'html': True}).enable('table').enable('strikethrough')
    old = {row['path']: row for row in json.loads((base / 'records.json').read_text())}
    new = {row['path']: row for row in json.loads((current / 'records.json').read_text())}
    if old.keys() != new.keys():
        raise ValueError('snapshot samples differ')
    report = {'parser': 'markdown-it-py ' + markdown_it.__version__, 'formats': {}, 'records': []}
    signal.signal(signal.SIGALRM, _timeout)
    for path, b in old.items():
        a = new[path]
        fmt = Path(path).suffix.lower().lstrip('.')
        totals = report['formats'].setdefault(fmt, Counter())
        totals['selected'] += 1
        row = {'path': path, 'before_status': b['status'], 'after_status': a['status']}
        if a['status'] != 'ok' or b['status'] != 'ok':
            totals['exceptions'] += 1
            totals['status_regressions'] += a['status'] != b['status']
            report['records'].append(row)
            continue
        if a['input_sha256'] != b['input_sha256']:
            raise ValueError('input changed: ' + path)
        totals['compared'] += 1
        totals['parser_error_files'] += bool(a['parser_errors'])
        totals['parser_error_increases'] += a['parser_errors'] > b['parser_errors']
        totals['format_mismatches'] += a['format'] != fmt
        oversized = a.get('oversize_markdown_omitted') or b.get('oversize_markdown_omitted')
        if oversized:
            if (a['markdown_sha256'] != b['markdown_sha256']
                    or a['has_image_opener'] or b['has_image_opener']):
                raise ValueError('oversized output requires separate audit: ' + path)
            before = after = ''
            totals['identical_oversize'] += 1
            row['oversize_proof'] = 'identical full SHA-256; image opener scan negative'
            totals['empty_outputs'] += a['empty_markdown']
        else:
            before = (base / (b['key'] + '.md')).read_text()
            after = (current / (a['key'] + '.md')).read_text()
            totals['empty_outputs'] += not bool(after.strip())
        totals['changed'] += before != after
        totals['valid_nonempty'] += (not a['parser_errors'] and a['format'] == fmt
                                     and (not a['empty_markdown'] if oversized else bool(after.strip())))
        signal.alarm(60)
        try:
            row.update(compare_text(before, after, parser))
        finally:
            signal.alarm(0)
        row['changed'] = before != after
        for metric in ('lost_body_words', 'stray_increase_hunks'):
            totals[metric] += row[metric]
        totals['body_loss_files'] += bool(row['lost_body_words'])
        for index, name, source in ((0, 'before', b), (1, 'after', a)):
            # The placeholder has no resolvable asset only if unnamed image
            # bytes are absent too. External named targets are not fetched.
            broken = max(0, row['empty_target_refs'][index] - source['unnamed_image_data'])
            row['broken_refs_' + name] = broken
            totals['broken_refs_' + name] += broken
            if row['rendered_stars'][index] is not None:
                totals['rendered_stars_' + name] += row['rendered_stars'][index]
        report['records'].append(row)
        if len(report['records']) % 100 == 0:
            print('compared', len(report['records']), flush=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['formats'], ensure_ascii=False, indent=2))
    return int(any(v['lost_body_words'] or v['stray_increase_hunks'] or v['broken_refs_after']
                   or v['status_regressions'] or v['parser_error_increases']
                   for v in report['formats'].values()))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='mode', required=True)
    pick = sub.add_parser('select')
    pick.add_argument('corpus', type=Path)
    pick.add_argument('output', type=Path)
    snap = sub.add_parser('snapshot')
    snap.add_argument('corpus', type=Path)
    snap.add_argument('source', type=Path)
    snap.add_argument('samples', type=Path)
    snap.add_argument('output', type=Path)
    snap.add_argument('--workers', type=int, default=4)
    diff = sub.add_parser('compare')
    diff.add_argument('base', type=Path)
    diff.add_argument('current', type=Path)
    diff.add_argument('output', type=Path)
    args = cli.parse_args()
    if args.mode == 'select':
        samples = select(args.corpus)
        args.output.write_text(json.dumps(samples, indent=2) + '\n')
        print({k: len(v) for k, v in samples.items()})
    elif args.mode == 'snapshot':
        args.output.mkdir(parents=True, exist_ok=True)
        samples = json.loads(args.samples.read_text())
        tasks = [(str(args.source.resolve()), str(args.corpus.resolve()), p, str(args.output.resolve()))
                 for paths in samples.values() for p in paths]
        results = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for result in pool.map(snapshot_one, tasks):
                results.append(result)
                if len(results) % 100 == 0:
                    print('processed', len(results), flush=True)
                (args.output / 'records.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        return compare(args.base, args.current, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
