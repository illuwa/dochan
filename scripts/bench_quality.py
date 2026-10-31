"""Public HWP/HWPX/PDF triples: text and table quality, without saved bodies.

Run with --pairs-dir, --output, --split and optionally --venv-python.
External extractors run in isolated subprocesses; only numeric scores and hashes
are persisted. Their text travels through anonymous pipes, never result files.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import contextlib
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

TOOLS = ('dochan', 'pymupdf', 'pdfplumber', 'pypdf', 'pdfminer', 'markitdown')
PACKAGES = {'pymupdf': 'PyMuPDF', 'pdfminer': 'pdfminer.six'}


def score(reference, candidate):
    """Reuse pair metrics; shape recall deliberately does not claim span parity."""
    from scripts.compare_pdf_pairs import cell_hit_rate, normalize_text, token_ratio

    def cells(tables):
        return [normalize_text(c) for t in tables for row in t for c in row
                if c and normalize_text(c)]

    def shapes(tables):
        return Counter((len(t), max((len(r) for r in t), default=0)) for t in tables)

    rt, ct = reference['tables'], candidate['tables']
    comparable = rt is not None and ct is not None
    return {
        'failed': 0,
        'token_ratio': token_ratio(reference['text'], candidate['text']),
        'text_sha256': hashlib.sha256(candidate['text'].encode('utf-8')).hexdigest(),
        'reference_tables': len(rt) if rt is not None else None,
        'candidate_tables': len(ct) if ct is not None else None,
        'cell_hit': cell_hit_rate(cells(rt), cells(ct)) if comparable else None,
        'table_shape_matches': sum((shapes(rt) & shapes(ct)).values()) if comparable else None,
        'reference_headings': reference['headings'],
        'candidate_headings': candidate['headings'],
    }


def summarize(rows):
    good = [r for r in rows if not r['failed']]
    ratios = [r['token_ratio'] for r in good]
    hits = [r['cell_hit'] for r in good if r['cell_hit'] is not None]
    tables = [r for r in good if r['table_shape_matches'] is not None]
    denominator = sum(r['reference_tables'] for r in tables)
    return {
        'successes': len(good), 'failures': len(rows) - len(good),
        'token_mean': statistics.mean(ratios) if ratios else None,
        'token_median': statistics.median(ratios) if ratios else None,
        'cell_hit_mean': statistics.mean(hits) if hits else None,
        'cell_scored_documents': len(hits),
        'table_shape_recall': sum(r['table_shape_matches'] for r in tables) / denominator
        if denominator else None,
        'reference_tables_scored': denominator,
        'candidate_tables': sum(r['candidate_tables'] for r in tables) if tables else None,
        'reference_headings': sum(r['reference_headings'] for r in good)
        if good and all(r['reference_headings'] is not None for r in good) else None,
        'candidate_headings': sum(r['candidate_headings'] for r in good)
        if good and all(r['candidate_headings'] is not None for r in good) else None,
    }


def extract(tool, path):
    """Only public APIs; no third-party implementation inspection."""
    tables = headings = None
    if tool == 'dochan':
        from dochan import Dochan, __version__
        reader = Dochan(path)
        if any(e.startswith('ERR') for e in reader.errors):
            raise ValueError('reader error')
        text = reader.to_plain_text()
        tables = [[[c.text if not c.is_merged_away else '' for c in row]
                   for row in t.rows] for t in reader.doc.find_all('table')]
        headings = sum(p.is_heading for p in reader.doc.find_all('paragraph'))
        version = __version__
    else:
        version = importlib.metadata.version(PACKAGES.get(tool, tool))
        if tool == 'pymupdf':
            import pymupdf
            with pymupdf.open(path) as doc:
                text = '\n'.join(page.get_text() for page in doc)
                tables = [t.extract() for page in doc for t in page.find_tables().tables]
        elif tool == 'pdfplumber':
            import pdfplumber
            with pdfplumber.open(path) as doc:
                text = '\n'.join(page.extract_text() or '' for page in doc.pages)
                tables = [t for page in doc.pages for t in page.extract_tables()]
        elif tool == 'pypdf':
            from pypdf import PdfReader
            text = '\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
        elif tool == 'pdfminer':
            from pdfminer.high_level import extract_text
            text = extract_text(path)
        elif tool == 'markitdown':
            from markitdown import MarkItDown
            text = MarkItDown().convert(path).text_content
            headings = len(re.findall(r'^#{1,6}\s+\S', text, re.MULTILINE))
        else:
            raise ValueError('unknown tool')
    return {'text': text, 'tables': tables, 'headings': headings, 'version': version}


def worker(tool, path):
    # Diagnostics can contain body snippets. Discard them rather than persisting.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = extract(tool, path)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception:
        return 1


def invoke(tool, path, python, timeout):
    # nosemgrep: dangerous-subprocess-use-audit
    proc = subprocess.run([python, str(Path(__file__).resolve()), '--worker', tool, str(path)],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=timeout, check=True)
    return json.loads(proc.stdout)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def measure(pdf, tools, external_python, timeout):
    started = time.monotonic()
    row = {'sha256': {ext: sha256(pdf.with_suffix('.' + ext))
                      for ext in ('hwp', 'hwpx', 'pdf')}, 'tools': {}}
    try:
        reference = invoke('dochan', pdf.with_suffix('.hwpx'), sys.executable, timeout)
    except (subprocess.SubprocessError, ValueError, OSError):
        row['reference_failed'] = 1
        row['tools'] = {tool: {'failed': 1, 'reference_failed': 1} for tool in tools}
        return pdf.stem, row
    row['reference_failed'] = 0
    row['reference_text_sha256'] = hashlib.sha256(reference['text'].encode('utf-8')).hexdigest()
    for tool in tools:
        try:
            candidate = invoke(tool, pdf, sys.executable if tool == 'dochan' else external_python,
                               timeout)
            row['tools'][tool] = score(reference, candidate)
            row['tools'][tool]['version'] = candidate['version']
        except subprocess.TimeoutExpired:
            row['tools'][tool] = {'failed': 1, 'timeout': 1}
        except (subprocess.SubprocessError, ValueError, OSError):
            row['tools'][tool] = {'failed': 1, 'timeout': 0}
    row['seconds'] = time.monotonic() - started
    return pdf.stem, row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--split', choices=('development', 'holdout'), required=True)
    parser.add_argument('--venv-python', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--limit', type=int, help='Development smoke check only')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; refusing to overwrite evidence')
    if args.workers < 1 or args.timeout <= 0 or (args.limit is not None and args.limit < 1):
        parser.error('workers, timeout and limit must be positive')
    if args.split == 'holdout' and args.limit:
        parser.error('Holdout must be measured as a complete frozen set')
    pairs = [p for p in sorted(args.pairs_dir.glob('*.pdf'))
             if p.with_suffix('.hwp').is_file() and p.with_suffix('.hwpx').is_file()]
    if not pairs:
        parser.error('No complete HWP/HWPX/PDF triples')
    if args.limit:
        pairs = pairs[:args.limit]
    tools = TOOLS if args.venv_python and args.venv_python.is_file() else ('dochan',)
    data = {'schema': 1, 'split': args.split, 'triples': len(pairs),
            'external_available': int(len(tools) > 1), 'timeout': args.timeout,
            'workers': args.workers, 'rows': {}}
    # Exclusive creation prevents accidental overwrite, including concurrent runs.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(measure, p, tools, str(args.venv_python), args.timeout)
                       for p in pairs]
            for future in as_completed(futures):
                key, row = future.result()
                data['rows'][key] = row
                # Checkpoint contains only hashes and numbers, plus tool/version metadata.
                out.seek(0)
                json.dump(data, out, ensure_ascii=True, sort_keys=True)
                out.truncate()
                out.flush()
                print(f"{args.split}: {len(data['rows'])}/{len(pairs)}", flush=True)
        data['summary'] = {tool: summarize([row['tools'][tool] for row in data['rows'].values()])
                           for tool in tools}
        out.seek(0)
        json.dump(data, out, ensure_ascii=True, sort_keys=True, indent=2)
        out.truncate()
    return 0


if __name__ == '__main__':
    # Direct script execution in the separate venv needs the checkout on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        sys.exit(worker(sys.argv[2], sys.argv[3]))
    sys.exit(main())
