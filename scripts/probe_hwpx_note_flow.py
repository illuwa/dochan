"""Measure HWPX note-flow changes without writing converted documents to disk.

Usage: python -m scripts.probe_hwpx_note_flow --output RESULT ROOT [ROOT ...]
       python -m scripts.probe_hwpx_note_flow --output RESULT --reference BEFORE ROOT [ROOT ...]
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from dochan import Dochan
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Paragraph
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Table
from dochan.output.json_out import to_json
from dochan.output.markdown import to_markdown


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _main_paragraph_text(document):
    """Exclude note definitions, whose position changes when a paragraph joins."""
    parts = []
    seen = set()

    def visit(elements, depth=0):
        if depth > 32:
            return
        for item in elements:
            if id(item) in seen:
                continue
            seen.add(id(item))
            if isinstance(item, Paragraph):
                parts.append(item.text)
            elif isinstance(item, Footnote):
                continue
            elif isinstance(item, HeaderFooter):
                visit(item.paragraphs, depth + 1)
            elif isinstance(item, Table):
                for row in item.rows:
                    for cell in row:
                        visit(cell.paragraphs, depth + 1)
                visit(item.caption, depth + 1)
            elif isinstance(item, Image):
                visit(item.caption, depth + 1)

    for section in document.sections:
        visit(section.elements)
    return ''.join(parts)


def _measure(path):
    try:
        if path.suffix == '.hwpx':
            reader = Dochan(str(path), include_assets=False)
            document = reader.doc
            markdown = reader.to_markdown()
            encoded_json = reader.to_json().encode('utf-8')
            errors = reader.errors
        else:
            # Dochan's format dispatch is case-sensitive; probe the same parser
            # and output functions directly for an upper-case HWPX extension.
            document = HWPXParser().parse(path, include_assets=False)
            markdown = to_markdown(document)
            encoded_json = to_json(document).encode('utf-8')
            errors = document.errors
        notes = [(note.type, note.number, note.text)
                 for note in document.find_all('note')
                 if note.type in ('footnote', 'endnote')]
        paragraphs = document.find_all('paragraph')
        main_text = _main_paragraph_text(document)
        references = [run.note_ref for paragraph in paragraphs
                      for run in paragraph.runs if run.note_ref]
        objects = {kind: len(document.find_all(kind))
                   for kind in ('table', 'image', 'header_footer', 'equation', 'comment')}
        return {
            'markdown_sha256': _digest(markdown.encode('utf-8')),
            'markdown_characters': len(markdown),
            'json_sha256': _digest(encoded_json),
            'json_bytes': len(encoded_json),
            'note_count': len(notes),
            'notes_sha256': _digest(json.dumps(notes, ensure_ascii=False).encode('utf-8')),
            'references_sha256': _digest(json.dumps(references).encode('ascii')),
            'reference_count': len(references),
            'text_sha256': _digest(main_text.encode('utf-8')),
            'nonspace_text_sha256': _digest(''.join(main_text.split()).encode('utf-8')),
            'paragraph_count': len(paragraphs),
            'objects': objects,
            'error_count': len(errors),
            'error_sha256': _digest(json.dumps(errors, ensure_ascii=False).encode('utf-8')),
        }
    except Exception as exc:
        return {'exception': type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('roots', nargs='+', type=Path)
    args = parser.parse_args()
    reference = None
    if args.reference:
        reference = json.loads(args.reference.read_text(encoding='utf-8'))['files']
    rows = {}
    for index, root in enumerate(args.roots):
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix.lower() == '.hwpx':
                key = '%d/%s' % (index, path.relative_to(root))
                rows[key] = _measure(path)
    summary = {
        'scanned': len(rows),
        'measured': sum('exception' not in row for row in rows.values()),
        'note_documents': sum(row.get('note_count', 0) > 0 for row in rows.values()),
        'notes': sum(row.get('note_count', 0) for row in rows.values()),
    }
    if reference is not None:
        changed = []
        markdown_changed = []
        json_changed = []
        failures = []
        whitespace_only_text_changes = []
        paragraph_reductions = 0
        for key, row in rows.items():
            old = reference.get(key)
            if old == row:
                continue
            if old is None or 'exception' in old or 'exception' in row:
                if old != row:
                    failures.append([key, 'exception_or_missing'])
                continue
            if old['markdown_sha256'] != row['markdown_sha256']:
                markdown_changed.append(key)
            if old['json_sha256'] != row['json_sha256']:
                json_changed.append(key)
            if old['markdown_sha256'] != row['markdown_sha256'] or old['json_sha256'] != row['json_sha256']:
                changed.append(key)
                if old['note_count'] == 0:
                    failures.append([key, 'changed_without_note'])
            for field in ('note_count', 'notes_sha256', 'references_sha256',
                          'reference_count', 'nonspace_text_sha256', 'objects',
                          'error_count', 'error_sha256'):
                if old[field] != row[field]:
                    failures.append([key, field])
            if (old['text_sha256'] != row['text_sha256']
                    and old['nonspace_text_sha256'] == row['nonspace_text_sha256']):
                whitespace_only_text_changes.append(key)
            paragraph_reductions += old['paragraph_count'] - row['paragraph_count']
        summary.update(changed=changed, markdown_changed=markdown_changed,
                       json_changed=json_changed, failures=failures,
                       whitespace_only_text_changes=whitespace_only_text_changes,
                       paragraph_reductions=paragraph_reductions,
                       missing=set(reference) - set(rows))
        summary['missing'] = sorted(summary['missing'])
        summary['failure_counts'] = dict(Counter(reason for _, reason in failures))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'summary': summary, 'files': rows},
                                      ensure_ascii=False), encoding='utf-8')
    print(json.dumps({key: (len(value) if isinstance(value, list) else value)
                      for key, value in summary.items()
                      if key != 'missing'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
