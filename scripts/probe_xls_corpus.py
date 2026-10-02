"""공개 XLS 코퍼스를 파일별 격리 프로세스로 읽고 회귀 증거를 기록한다.

예: /usr/bin/python3 -m scripts.probe_xls_corpus /path/to/spreadsheet --output result.json
--reader-source 는 비교용 이전 xls.py 파일이며 코퍼스는 읽기만 한다.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def inspect(path, reader_source=None):
    import dochan.office_binary.xls as xls
    if reader_source:
        source = Path(reader_source).read_text()
        exec(compile(source, reader_source, 'exec'), xls.__dict__)
    from dochan import Dochan
    doc = Dochan(path).doc
    from dochan.model.table import Table
    tables = [element for section in doc.sections for element in section.elements
              if isinstance(element, Table)]
    cells = [cell.text for table in tables for row in table.rows for cell in row]
    images = doc.find_all('image')
    return {'file': Path(path).name, 'errors': doc.errors, 'sections': len(doc.sections),
            'tables': len(tables), 'cells': len(cells), 'nonempty_cells': sum(bool(c) for c in cells),
            'cell_sha256': hashlib.sha256(json.dumps(cells, ensure_ascii=False).encode()).hexdigest(),
            'images': len(images), 'image_bytes': sum(len(i.image_data or b'') for i in images)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus')
    parser.add_argument('--output')
    parser.add_argument('--reader-source')
    parser.add_argument('--one', action='store_true')
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    if args.one:
        try:
            result = inspect(args.corpus, args.reader_source)
        except Exception as error:
            result = {'file': Path(args.corpus).name, 'exception': type(error).__name__ + ': ' + str(error)}
        print(json.dumps(result, ensure_ascii=False))
        return
    results = []
    for path in sorted(Path(args.corpus).glob('*.xls')):
        command = [sys.executable, '-m', 'scripts.probe_xls_corpus', str(path), '--one']
        if args.reader_source:
            command += ['--reader-source', args.reader_source]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
            result = json.loads(process.stdout) if process.returncode == 0 else {
                'file': path.name, 'process_exit': process.returncode, 'stderr': process.stderr[-2000:]}
        except (subprocess.TimeoutExpired, ValueError) as error:
            result = {'file': path.name, 'exception': type(error).__name__}
        results.append(result)
        if len(results) % 50 == 0:
            print('%d files' % len(results), flush=True)
    payload = {'files': len(results), 'results': results}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(results),
        'exceptions': sum('exception' in r or 'process_exit' in r for r in results),
        'with_errors': sum(bool(r.get('errors')) for r in results)}))


if __name__ == '__main__':
    main()
