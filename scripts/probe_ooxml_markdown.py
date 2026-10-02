"""공용 Markdown 변경을 공개 HWPX/XLS 코퍼스에서 HEAD와 비교한다."""
import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import subprocess
import types

from dochan.hwpx.parser import HWPXParser
from dochan.output.markdown import to_markdown
from dochan.office_binary.xls import XLSReader


def changed_lines(before, after):
    return sum(max(j - i, b - a) for tag, i, j, a, b in
               SequenceMatcher(None, before.splitlines(), after.splitlines(),
                               autojunk=False).get_opcodes() if tag != 'equal')


def probe(hwpx_corpus, spreadsheet_corpus=None):
    source = subprocess.check_output(['git', 'show', 'HEAD:dochan/output/markdown.py'], text=True)
    baseline = types.ModuleType('dochan.output._baseline_markdown')
    baseline.__package__ = 'dochan.output'
    exec(compile(source, 'HEAD:dochan/output/markdown.py', 'exec'), baseline.__dict__)
    result = {}
    collections = [('hwpx', hwpx_corpus, HWPXParser().parse)]
    if spreadsheet_corpus is not None:
        collections.append(('xls', spreadsheet_corpus, XLSReader().read))
    for suffix, corpus, read in collections:
        rows = []
        for path in sorted(path for path in corpus.rglob('*')
                           if path.is_file() and path.suffix.lower() == '.' + suffix):
            try:
                doc = read(str(path))
                before, after = baseline.to_markdown(doc), to_markdown(doc)
                hidden = [s.provenance.sheet for s in doc.sections
                          if getattr(getattr(s, 'provenance', None), 'hidden', False)]
                rows.append({'file': path.name, 'changed_lines': changed_lines(before, after),
                             'hidden_sheets': hidden, 'errors': doc.errors})
            except Exception as exc:
                rows.append({'file': path.name, 'failure': type(exc).__name__})
        result[suffix] = {'scanned': len(rows),
                          'changed_documents': sum(row.get('changed_lines', 0) > 0 for row in rows),
                          'changed_lines': sum(row.get('changed_lines', 0) for row in rows),
                          'failures': sum('failure' in row for row in rows), 'documents': rows}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hwpx_corpus', type=Path)
    parser.add_argument('--spreadsheet-corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(probe(args.hwpx_corpus, args.spreadsheet_corpus),
                                     ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
