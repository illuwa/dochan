"""Measure alternating CLI file-output runs with macOS time -l.

Only public input paths should be passed. Synthetic XLSX inputs and output
bodies live in TemporaryDirectory; the report retains hashes and metrics only.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def synthetic_xlsx(path, rows):
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('xl/workbook.xml',
                         f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/'
                         'officeDocument/2006/relationships"><sheets>'
                         '<sheet name="측정" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels',
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                         'relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                         '</Relationships>')
        archive.writestr('xl/sharedStrings.xml', f'<sst xmlns="{ns}"><si><t>한글 측정</t></si></sst>')
        with archive.open('xl/worksheets/sheet1.xml', 'w') as sheet:
            sheet.write(f'<worksheet xmlns="{ns}"><sheetData>'.encode())
            for row in range(1, rows + 1):
                cells = []
                for col in range(20):
                    ref = f'{chr(65 + col)}{row}'
                    cells.append(f'<c r="{ref}" t="s"><v>0</v></c>' if col % 2
                                 else f'<c r="{ref}"><v>{row}</v></c>')
                sheet.write((f'<row r="{row}">' + ''.join(cells) + '</row>').encode())
            sheet.write(b'</sheetData></worksheet>')


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def measure(before, after, inputs, output, python, rss_method="time-l", synthetic_rows=(5000, 9900)):
    records = []
    with tempfile.TemporaryDirectory(prefix='dochan-stream-') as directory:
        root = Path(directory)
        synthetic = [root / f'synthetic-{n}.xlsx' for n in synthetic_rows]
        for path, rows in zip(synthetic, synthetic_rows):
            synthetic_xlsx(path, rows)
        for source in synthetic + [Path(p).resolve() for p in inputs]:
            for fmt in ('json', 'markdown'):
                expected = None
                for label in ('before', 'after', 'after', 'before', 'before', 'after'):
                    destination = root / 'output'
                    arguments = ['convert', str(source), '--format', fmt, '-o', str(destination)]
                    if rss_method == 'time-l':
                        command = ['/usr/bin/time', '-l', python, '-m', 'dochan.cli', *arguments]
                    else:
                        # macOS sandbox can deny time -l's kern.clockrate sysctl.
                        # Measure the CLI process itself, not the parent process pool.
                        wrapper = (
                            'import atexit,resource,runpy,sys; '
                            'atexit.register(lambda: print("RSS_BYTES", '
                            'resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, file=sys.stderr)); '
                            'sys.argv=["dochan"]+sys.argv[1:]; '
                            'runpy.run_module("dochan.cli",run_name="__main__")'
                        )
                        command = ['/usr/bin/time', python, '-c', wrapper, *arguments]
                    # nosemgrep: dangerous-subprocess-use-audit
                    run = subprocess.run(command, cwd=before if label == 'before' else after,
                                         capture_output=True, text=True, check=False)
                    if run.returncode:
                        raise RuntimeError(run.stderr)
                    sha = digest(destination)
                    if expected is None:
                        expected = sha
                    if sha != expected:
                        raise AssertionError('output bytes changed: ' + source.name)
                    rss_pattern = (r'(\d+)\s+maximum resident set size' if rss_method == 'time-l'
                                   else r'RSS_BYTES (\d+)')
                    rss = int(re.search(rss_pattern, run.stderr)[1])
                    elapsed = float(re.search(r'([\d.]+)\s+real\s', run.stderr)[1])
                    records.append(dict(input=source.name, format=fmt, version=label,
                                        rss_bytes=rss, rss_method=rss_method, seconds=elapsed, sha256=sha,
                                        bytes=destination.stat().st_size))
                    destination.unlink()
                    Path(output).write_text(json.dumps(records, indent=2) + '\n')
                    print(source.name, fmt, label, rss, elapsed, flush=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', default='.')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--output', required=True)
    parser.add_argument('--rss-method', choices=['time-l', 'resource'], default='time-l')
    parser.add_argument('--no-synthetic', action='store_true')
    parser.add_argument('inputs', nargs='*')
    args = parser.parse_args()
    measure(str(Path(args.before).resolve()), str(Path(args.after).resolve()),
            args.inputs, args.output, args.python, args.rss_method,
            () if args.no_synthetic else (5000, 9900))


if __name__ == '__main__':
    main()
