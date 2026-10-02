"""공개 문서를 같은 모델로 읽고 세 작성기의 CommonMark 해석을 비교한다.

이미 설치된 markdown-it-py를 검증 도구로만 사용한다. 런타임 의존성이 아니다.
원본 파일이나 본문은 저장하지 않고 공개 경로, 해시, 구문 집계만 남긴다.
"""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import signal
import subprocess

from dochan import Dochan
from dochan.output import markdown
from scripts.probe_markdown_review import _load_writer, _timeout


class _Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.alts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.alts.append(dict(attrs).get('alt', ''))


def _unclosed(state):
    # Image alt labels have their own recursive inline parse and are measured
    # separately through rendered HTML alt attributes, not as body emphasis.
    if state.src != state.env['audit_source']:
        return
    positions = []
    line = 0
    for token in state.tokens:
        positions.append(line)
        line += token.content.count('\n')
        if token.type in ('softbreak', 'hardbreak'):
            line += 1
    groups = [state.delimiters]
    groups.extend(meta['delimiters'] for meta in state.tokens_meta
                  if meta and 'delimiters' in meta)
    for group in groups:
        for delimiter in group:
            token = state.tokens[delimiter.token]
            if (delimiter.marker in (42, 95) and delimiter.open and delimiter.end < 0
                    and token.type == 'text' and token.content in ('*', '_')):
                state.env['unclosed'].add(positions[delimiter.token])


def make_parser():
    from markdown_it import MarkdownIt
    parser = MarkdownIt('commonmark')
    parser.inline.ruler2.before('fragments_join', 'audit_unclosed', _unclosed)
    return parser


def measure(text, parser=None):
    """Count unmatched CommonMark opening delimiters by physical source line.

    Balanced multi-line paragraphs are valid and count zero; heading/block
    boundaries, escapes, code spans and flanking rules come from the parser.
    Literal punctuation can also be unmatched, so this is a diagnostic count,
    not a claim that every counted line is a writer bug.
    """
    parser = parser or make_parser()
    tokens = []
    env = {}
    normalized = text.replace('\r\n', '\n').replace('\r', '\n').replace('\0', '\ufffd')
    parser.block.parse(normalized, parser, env, tokens)
    unclosed = set()
    for token in tokens:
        if token.type == 'inline':
            env.update(audit_source=token.content, unclosed=set())
            token.children = []
            parser.inline.parse(token.content, parser, env, token.children)
            unclosed.update(token.map[0] + line for line in env['unclosed'])
    html = parser.renderer.render(tokens, parser.options, {})
    images = _Images()
    images.feed(html)
    return {
        'unclosed_emphasis_lines': len(unclosed),
        'image_alts_with_stars': sum('**' in alt for alt in images.alts),
        'images': len(images.alts),
        'markdown_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'html_sha256': hashlib.sha256(html.encode()).hexdigest(),
    }


def candidates(root, fmt):
    if fmt in ('hwp', 'hwpx'):
        roots = ['hwp-public']
    elif fmt == 'pdf':
        roots = ['pdfjs-src', 'poi-src/test-data', 'lo-src', 'tika-test-docs']
    else:
        kind = 'document' if fmt in ('doc', 'docx') else 'slideshow'
        roots = ['poi-src/test-data/' + kind, 'lo-src', 'tika-test-docs']
    for directory in roots:
        for path in sorted((root / directory).rglob('*.' + fmt)):
            if path.is_file() and path.stat().st_size <= 5 * 1024 * 1024:
                yield path


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('corpus', type=Path)
    cli.add_argument('--count', type=int, default=200)
    cli.add_argument('--timeout', type=int, default=20)
    cli.add_argument('--formats', nargs='+', default=['docx', 'pptx', 'hwp', 'hwpx', 'pdf', 'doc', 'ppt'])
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    if args.count < 200 or args.timeout < 1:
        cli.error('count must be >= 200 and timeout must be positive')
    writers = {'current': markdown}
    sources = {'current': Path(markdown.__file__).read_text()}
    for ref in ('5c149c2', '107e18d'):
        sources[ref] = subprocess.check_output(  # nosemgrep: dangerous-subprocess-use-audit
            ['git', 'show', ref + ':dochan/output/markdown.py'], text=True)
        writers[ref] = _load_writer(sources[ref], 'commonmark_' + ref)
    import markdown_it
    result = {'parser': 'markdown-it-py ' + markdown_it.__version__ + ' commonmark',
              'comparison': 'same current document model, three writer revisions',
              'writer_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sources.items()},
              'requested_successes': args.count, 'formats': {}}
    parser = make_parser()
    signal.signal(signal.SIGALRM, _timeout)
    for fmt in args.formats:
        records, skipped = [], []
        for path in candidates(args.corpus, fmt):
            relative = str(path.relative_to(args.corpus))
            signal.alarm(args.timeout)
            try:
                doc = Dochan(str(path)).doc
                if doc.source_format != fmt or any(e.startswith('ERR:') for e in doc.errors):
                    skipped.append({'file': relative, 'reason': 'format mismatch or parser error'})
                    continue
                outputs = {key: writer.to_markdown(doc) for key, writer in writers.items()}
                if not outputs['current'].strip():
                    skipped.append({'file': relative, 'reason': 'empty Markdown'})
                    continue
                records.append({'file': relative, 'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'metrics': {key: measure(value, parser) for key, value in outputs.items()}})
            except Exception as exc:
                skipped.append({'file': relative, 'reason': type(exc).__name__})
            finally:
                signal.alarm(0)
            if len(records) >= args.count:
                break
        totals = {key: {metric: sum(row['metrics'][key][metric] for row in records)
                        for metric in ('unclosed_emphasis_lines', 'image_alts_with_stars', 'images')}
                  for key in writers}
        item = {'compared': len(records), 'skipped_count': len(skipped), 'totals': totals,
                'records': records, 'skipped': skipped}
        result['formats'][fmt] = item
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(fmt, len(records), 'skipped', len(skipped), totals, flush=True)
    return int(any(item['compared'] < args.count for item in result['formats'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
