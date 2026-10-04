"""같은 파일로 dochan 과 다른 변환 도구의 속도를 잰다(비교 전용 — 다른 도구는 dochan 의 의존성이 아니다).

다른 도구(PyMuPDF·pdfminer.six·pdfplumber·pypdf·markitdown·pyhwp)는 저장소 밖 별도 가상환경에 설치하고,
그 환경의 파이썬으로 이 스크립트를 실행한다. dochan 은 같은 파이썬에서 저장소 소스를 직접 읽는다.

    python -m scripts.bench_converters sample corpus out/        # 형식별 무작위 표본 목록(files-<형식>.json)
    python -m scripts.bench_converters run dochan out/files-pdf.json out/pdf-dochan.json
    python -m scripts.bench_converters run pymupdf out/files-pdf.json out/pdf-pymupdf.json
    python -m scripts.bench_converters report out/               # 둘 다 성공한 파일만 합산한 비교표

도구마다 한 프로세스에서 한 번 불러온 뒤 파일별 변환 시간(벽시계)만 잰다. 파일당 60초 상한이며
결과에는 시간·상태·출력 글자 수만 저장한다(본문 저장 없음).
"""
import argparse
import glob
import io
import json
import os
import random
import signal
import statistics
import time
from contextlib import closing

SAMPLES = {
    'pdf': (['press-pairs/*.pdf', 'press-pairs-holdout/*.pdf', 'pdfjs-src/test/pdfs/*.pdf'], 300),
    'hwp': (['hwp-public/hwp/*.hwp'], 300),
    'hwpx': (['hwp-public/hwpx/*.hwpx'], 300),
    'docx': (['poi-src/test-data/**/*.docx', 'lo-src/**/*.docx'], 300),
    'pptx': (['poi-src/test-data/**/*.pptx', 'lo-src/**/*.pptx'], 200),
    'xlsx': (['poi-src/test-data/**/*.xlsx'], 200),
    'xls': (['poi-src/test-data/**/*.xls', 'lo-src/**/*.xls'], 200),
}
COMPARISONS = {
    'pdf': ['pymupdf', 'pypdf', 'pdfminer', 'pdfplumber', 'markitdown'],
    'hwp': ['pyhwp'],
    'docx': ['markitdown'],
    'pptx': ['markitdown'],
    'xlsx': ['markitdown'],
    'xls': ['markitdown'],
}
FILE_SECONDS = 60


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def _converter(tool):
    """도구 이름에 맞는 `path -> text` 함수를 돌려준다(도구는 여기서 처음 불러온다)."""
    if tool == 'dochan':
        from dochan import Dochan
        return lambda path: Dochan(path).to_markdown()
    if tool == 'pymupdf':
        import pymupdf

        def convert(path):
            with pymupdf.open(path) as doc:
                return '\n'.join(page.get_text() for page in doc)
        return convert
    if tool == 'pdfminer':
        from pdfminer.high_level import extract_text
        return extract_text
    if tool == 'pdfplumber':
        import pdfplumber

        def convert(path):
            with pdfplumber.open(path) as pdf:
                return '\n'.join((page.extract_text() or '') for page in pdf.pages)
        return convert
    if tool == 'pypdf':
        from pypdf import PdfReader
        return lambda path: '\n'.join((page.extract_text() or '') for page in PdfReader(path).pages)
    if tool == 'markitdown':
        from markitdown import MarkItDown
        converter = MarkItDown()
        return lambda path: converter.convert(path).text_content
    if tool == 'pyhwp':
        from hwp5.hwp5txt import TextTransform
        from hwp5.xmlmodel import Hwp5File
        transform = TextTransform()

        def convert(path):
            buffer = io.BytesIO()
            with closing(Hwp5File(path)) as hwp:
                transform.transform_hwp5_to_text(hwp, buffer)
            return buffer.getvalue().decode('utf-8', 'replace')
        return convert
    raise SystemExit('unknown tool: %s' % tool)


def sample(corpus, out_dir, seed):
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(seed)
    for fmt, (patterns, count) in SAMPLES.items():
        files = sorted(set(path for pattern in patterns
                           for path in glob.glob(os.path.join(corpus, pattern), recursive=True)))
        rng.shuffle(files)
        chosen = sorted(files[:count])
        with open(os.path.join(out_dir, 'files-%s.json' % fmt), 'w', encoding='utf-8') as handle:
            json.dump(chosen, handle, ensure_ascii=False)
        print(fmt, len(chosen))


def run(tool, listing, output):
    with open(listing, encoding='utf-8') as handle:
        files = json.load(handle)
    convert = _converter(tool)
    signal.signal(signal.SIGALRM, _alarm)
    rows = {}
    for path in files:
        start = time.perf_counter()
        signal.alarm(FILE_SECONDS)
        try:
            text = convert(path)
            status, chars = 'ok', len(text or '')
        except _Timeout:
            status, chars = 'timeout', 0
        except BaseException as exc:  # 변환 실패도 측정 결과다
            status, chars = 'error:' + type(exc).__name__, 0
        finally:
            signal.alarm(0)
        rows[path] = {'s': round(time.perf_counter() - start, 5), 'status': status, 'chars': chars}
    with open(output, 'w', encoding='utf-8') as handle:
        json.dump(rows, handle, ensure_ascii=False)
    print(tool, 'files', len(rows), 'ok', sum(row['status'] == 'ok' for row in rows.values()),
          'total %.1fs' % sum(row['s'] for row in rows.values()))


def _load(out_dir, fmt, tool):
    path = os.path.join(out_dir, '%s-%s.json' % (fmt, tool))
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def report(out_dir):
    for fmt in SAMPLES:
        own = _load(out_dir, fmt, 'dochan')
        if own is None:
            continue
        seconds = sorted(row['s'] for row in own.values())
        print('%s dochan: ok %d/%d, total %.1fs, median %.1fms, p95 %.0fms, max %.2fs' % (
            fmt, sum(row['status'] == 'ok' for row in own.values()), len(own), sum(seconds),
            statistics.median(seconds) * 1000, seconds[int(len(seconds) * 0.95)] * 1000, seconds[-1]))
        for tool in COMPARISONS.get(fmt, []):
            other = _load(out_dir, fmt, tool)
            if other is None:
                continue
            both = [path for path in own if path in other
                    and own[path]['status'] == 'ok' and other[path]['status'] == 'ok']
            mine = sum(own[path]['s'] for path in both)
            theirs = sum(other[path]['s'] for path in both)
            ratio = theirs / mine if mine else 0.0
            print('  vs %-10s both-ok %3d | dochan %.1fs, %s %.1fs | dochan speed ratio %.2fx | %s failed %d' % (
                tool, len(both), mine, tool, theirs, ratio, tool,
                sum(row['status'] != 'ok' for row in other.values())))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    sampler = commands.add_parser('sample')
    sampler.add_argument('corpus')
    sampler.add_argument('out_dir')
    sampler.add_argument('--seed', type=int, default=20261004)
    runner = commands.add_parser('run')
    runner.add_argument('tool')
    runner.add_argument('listing')
    runner.add_argument('output')
    reporter = commands.add_parser('report')
    reporter.add_argument('out_dir')
    args = parser.parse_args()
    if args.command == 'sample':
        sample(args.corpus, args.out_dir, args.seed)
    elif args.command == 'run':
        run(args.tool, args.listing, args.output)
    else:
        report(args.out_dir)


if __name__ == '__main__':
    main()
