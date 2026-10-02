"""Compare shared Markdown output on public corpora against the pre-fix writer.

The independent expectation reuses the old single-line writer for each line,
then its old outer wrappers. Only emphasis boundaries and table image rendering
are allowed to differ. The document model is parsed once for all three outputs.
"""

import argparse
import ast
from dataclasses import replace
import difflib
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import types

from dochan import Dochan
from dochan.model.image import Image
from dochan.model.table import Cell
from dochan.output import markdown


def _load_writer(source, name):
    module = types.ModuleType('dochan.output.' + name)
    module.__package__ = 'dochan.output'
    exec(compile(source, name, 'exec'), module.__dict__)
    return module


def _expected_writer(source, images=False):
    writer = _load_writer(source, 'review_expected')
    old_run = writer._run_to_md
    old_cell = writer._cell_text

    def linewise_run(run):
        if run.note_ref or '\n' not in run.text or not (run.bold or run.italic):
            return old_run(run)
        # Feed only physical lines to the unchanged baseline formatter. Preserve
        # underline, strikeout and script wrappers around the original whole run.
        inner = '\n'.join(old_run(replace(
            run, text=line, underline=False, strikeout=False,
            superscript=False, subscript=False,
        )) for line in run.text.split('\n'))
        return old_run(replace(run, text=inner, bold=False, italic=False))

    def image_cell(cell, ctx=None):
        parts = []
        for block in cell.paragraphs:
            if isinstance(block, Image):
                part = writer._escape_cell(writer._image_to_md(block, ctx))
            else:
                part = old_cell(Cell(paragraphs=[block]), ctx)
            if part:
                parts.append(part)
        return ' '.join(parts)

    writer._run_to_md = linewise_run
    if images:
        writer._cell_text = image_cell
    return writer


def _changed_lines(before, after):
    counts = [0, 0]
    for tag, a, b, c, d in difflib.SequenceMatcher(
            None, before.splitlines(), after.splitlines(), autojunk=False).get_opcodes():
        if tag != 'equal':
            counts[0] += b - a
            counts[1] += d - c
    return counts


def _timeout(signum, frame):
    raise TimeoutError('public sample exceeded per-document time limit')


def _candidates(root, fmt):
    if fmt in ('hwp', 'hwpx'):
        roots = [root / 'hwp-public']
    else:
        kind = 'document' if fmt in ('doc', 'docx') else 'slideshow'
        roots = [root / 'poi-src' / 'test-data' / kind, root / 'lo-src']
    for directory in roots:
        for path in sorted(directory.rglob('*.' + fmt)):
            # Keep the run practical and reproducible without copying documents.
            if path.is_file() and path.stat().st_size <= 5 * 1024 * 1024:
                yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--baseline-ref', default='HEAD')
    parser.add_argument('--baseline-file', type=Path)
    parser.add_argument('--count', type=int, default=200)
    parser.add_argument('--list', dest='file_list', type=Path,
                        help='Compare every listed document, including empty output; ignore count.')
    parser.add_argument('--formats', nargs='+', default=['docx', 'pptx', 'hwp', 'hwpx'],
                        choices=['doc', 'ppt', 'docx', 'pptx', 'hwp', 'hwpx'])
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.count < 1 or args.timeout < 1:
        parser.error('count and timeout must be positive')
    if args.baseline_file:
        source = args.baseline_file.read_text()
    else:
        source = subprocess.check_output(  # nosemgrep: dangerous-subprocess-use-audit
            ['git', 'show', args.baseline_ref + ':dochan/output/markdown.py'], text=True,
        )
    baseline = _load_writer(source, 'review_before')
    emphasis = _expected_writer(source)
    expected = _expected_writer(source, images=True)
    current_source = Path(markdown.__file__).read_text()
    emphasis_actual = _load_writer(current_source, 'review_emphasis_actual')
    # Isolate the emphasis fix in the actual current writer by restoring only
    # the old cell renderer. Compile it in the current module's namespace so
    # nested footnotes still call the current paragraph/run renderer.
    old_cell = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == '_cell_text')
    exec(compile(ast.Module(body=[old_cell], type_ignores=[]), 'old_cell', 'exec'),
         emphasis_actual.__dict__)
    report = {
        'baseline_ref': args.baseline_ref,
        'baseline_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'current_sha256': hashlib.sha256(Path(markdown.__file__).read_bytes()).hexdigest(),
        'count_requested': None if args.file_list else args.count, 'formats': {},
    }
    listed = None
    if args.file_list:
        listed = []
        for line in args.file_list.read_text().splitlines():
            if not line.strip():
                continue
            path = Path(line.strip())
            if not path.is_absolute():
                path = args.corpus / path
            # List input must still belong to the specified public corpus root.
            path.resolve().relative_to(args.corpus.resolve())
            listed.append(path)
        report['listed_count'] = len(listed)
    signal.signal(signal.SIGALRM, _timeout)
    for fmt in args.formats:
        records, skipped = [], []
        candidates = (_candidates(args.corpus, fmt) if listed is None else
                      (path for path in listed if path.suffix.lower() == '.' + fmt))
        for path in candidates:
            relative = str(path.relative_to(args.corpus))
            signal.alarm(args.timeout)
            try:
                doc = Dochan(str(path)).doc
                if ((listed is None and doc.source_format != fmt)
                        or any(e.startswith('ERR:') for e in doc.errors)):
                    skipped.append({'file': relative, 'reason': 'format mismatch or parser error'})
                    continue
                before = baseline.to_markdown(doc)
                if not before.strip() and listed is None:
                    skipped.append({'file': relative, 'reason': 'empty baseline Markdown'})
                    continue
                emphasis_only = emphasis.to_markdown(doc)
                isolated = emphasis_actual.to_markdown(doc)
                after = markdown.to_markdown(doc)
                allowed = expected.to_markdown(doc)
                records.append({
                    'file': relative, 'warnings': len(doc.errors),
                    'source_format': doc.source_format,
                    'empty_baseline': not before.strip(),
                    'changed': before != after,
                    'emphasis_changed': before != emphasis_only,
                    'emphasis_lines': _changed_lines(before, emphasis_only),
                    'table_images_changed': emphasis_only != allowed,
                    'table_image_lines': _changed_lines(emphasis_only, allowed),
                    'matches_expected': after == allowed,
                    'emphasis_matches_expected': isolated == emphasis_only,
                    'baseline_sha256': hashlib.sha256(before.encode()).hexdigest(),
                    'current_sha256': hashlib.sha256(after.encode()).hexdigest(),
                })
            except (Exception, TimeoutError) as exc:
                skipped.append({'file': relative, 'reason': type(exc).__name__})
            finally:
                signal.alarm(0)
            if listed is None and len(records) >= args.count:
                break
        summary = {
            'compared': len(records),
            'empty_baseline': sum(row['empty_baseline'] for row in records),
            'format_mismatch': sum(row['source_format'] != fmt for row in records),
            'unchanged': sum(not row['changed'] for row in records),
            'emphasis_changed': sum(row['emphasis_changed'] for row in records),
            'emphasis_lines_before': sum(row['emphasis_lines'][0] for row in records),
            'emphasis_lines_after': sum(row['emphasis_lines'][1] for row in records),
            'table_images_changed': sum(row['table_images_changed'] for row in records),
            'unexpected_changes': sum(not row['matches_expected'] for row in records),
            'unexpected_emphasis_changes': sum(not row['emphasis_matches_expected'] for row in records),
            'skipped_count': len(skipped), 'records': records, 'skipped': skipped,
        }
        report['formats'][fmt] = summary
        print(fmt, {key: val for key, val in summary.items() if key not in ('records', 'skipped')}, flush=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return int(any((listed is None and item['compared'] < args.count) or item['unexpected_changes']
                   or item['unexpected_emphasis_changes']
                   for item in report['formats'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
