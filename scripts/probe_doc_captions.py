"""Scan public DOC corpora for caption evidence without copying source files.

Run with --poi POI_DOCUMENT --lo LO_ROOT --output RESULT.json.
Every LO sw/qa/extras/*/data/*.doc is included, not a filename allowlist.
"""
import argparse
from collections import Counter
import bisect
import json
from pathlib import Path
import re

from dochan.model.document import Document
from dochan.model.table import Table
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.doc_captions import DocCaptions
from dochan.office_binary.doc_stories import Stories
from dochan.office_binary.doc_tables import assemble_blocks
from dochan.ooxml.docx import DOCXReader
from scripts.check_doc_word_preservation import document_text, read_binary, words


def caption_rows(doc):
    return [{'type': 'table' if isinstance(e, Table) else 'image',
             'caption': e.caption_text, 'side': e.caption_side,
             'cp': [getattr(p.provenance, 'path', '') for p in e.caption]}
            for kind in ('table', 'image') for e in doc.find_all(kind) if e.caption]


def probe(path, pairs):
    current = DOCReader().read(str(path))
    original = DocCaptions.render
    try:
        # The unmodified structure path is the immediate pre-change baseline.
        DocCaptions.render = lambda self, records, render, warnings, textbox_at=None: assemble_blocks(records, render, warnings)
        baseline = DOCReader().read(str(path))
    finally:
        DocCaptions.render = original
    before, after = words(document_text(baseline)), words(document_text(current))
    row = {'file': path.name, 'captions': caption_rows(current),
           'word_loss': dict(before - after), 'word_gain': dict(after - before),
           'errors_before': baseline.errors, 'errors_after': current.errors,
           'candidates': [], 'pairs': []}
    try:
        binary, stream = read_binary(path)
    except Exception as exc:
        row['scan_skip'] = type(exc).__name__ + ': ' + str(exc)
        return row
    if binary is None:
        row['scan_skip'] = 'No valid native DOC FIB/CLX'
        return row
    scratch = Document()
    stories = Stories(binary, scratch)
    detector = DocCaptions(binary, stories, scratch.errors)
    row['native'] = True
    baseline_paragraphs = {getattr(p.provenance, 'path', ''): p.text
                           for p in baseline.find_all('paragraph')}
    def source_record(record):
        return {'cp': [record.start, record.end], 'raw': record.text,
                'in_table': bool(record.props.get('in_table')),
                'row_end': bool(record.props.get('row_end'))}
    for story, (start, end) in binary.stories.items():
        records = list(binary.paragraphs(start, end))
        for index, record in enumerate(records):
            style = record.props.get('istd', 0)
            a = bisect.bisect_left(detector.starts, record.start)
            b = bisect.bisect_left(detector.starts, record.end)
            fields = [f.instruction for f in stories.fields[a:b]
                      if f.instruction.lstrip().upper().startswith('SEQ ')]
            # The inventory includes cells/textboxes; attachment remains main-only.
            name = binary.styles.get(style, {}).get('name', '')
            kind = detector.kind(record)
            if fields or kind or style in detector.builtin or name.casefold() == 'caption':
                row['candidates'].append({'story': story, 'cp': [record.start, record.end],
                    'raw': record.text, 'style': style, 'style_name': name,
                    'builtin_caption': style in detector.builtin, 'seq': fields,
                    'in_table': bool(record.props.get('in_table')), 'kind': kind,
                    'visible_before': baseline_paragraphs.get('WordDocument#cp%d' % record.start, ''),
                    'previous': source_record(records[index - 1]) if index else None,
                    'following': source_record(records[index + 1]) if index + 1 < len(records) else None})
    row['attached_text_matches_source'] = all(
        len(c['cp']) == 1 and c['caption'] == baseline_paragraphs.get(c['cp'][0])
        for c in row['captions'])
    from dochan.output.markdown import to_markdown
    # The shared caption renderer intentionally folds whitespace and emits
    # italic caption text, while the model retains the original runs.
    before_md = re.sub(r'\s+', ' ', to_markdown(baseline))
    after_md = re.sub(r'\s+', ' ', to_markdown(current))
    row['caption_markdown_counts_match'] = all(
        before_md.count(re.sub(r'\s+', ' ', c['caption'])) ==
        after_md.count(re.sub(r'\s+', ' ', c['caption'])) for c in row['captions'])
    if row['candidates']:
        for pair in pairs:
            docx = DOCXReader().read(str(pair))
            row['pairs'].append({'file': str(pair.name), 'captions': caption_rows(docx), 'errors': docx.errors})
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi', type=Path, required=True)
    parser.add_argument('--lo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [('poi', p) for p in sorted(args.poi.iterdir()) if p.is_file() and p.suffix.lower() == '.doc']
    paths += [('lo/' + p.parent.parent.name, p) for p in sorted((args.lo / 'sw/qa/extras').glob('*/data/*.doc'))]
    pairs = {}
    for p in list(args.poi.glob('*.docx')) + list((args.lo / 'sw/qa/extras').glob('*/data/*.docx')):
        pairs.setdefault(p.stem.casefold(), []).append(p)
    rows = []
    for corpus, path in paths:
        try:
            row = probe(path, pairs.get(path.stem.casefold(), []))
        except Exception as exc:
            row = {'file': path.name, 'probe_error': type(exc).__name__ + ': ' + str(exc)}
        row['corpus'] = corpus
        rows.append(row)
    summary = {'documents': len(rows), 'native': sum(r.get('native', False) for r in rows),
        'corpora': dict(Counter(r['corpus'] for r in rows)),
        'candidate_documents': sum(bool(r.get('candidates')) for r in rows),
        'candidate_paragraphs': sum(len(r.get('candidates', [])) for r in rows),
        'attached_documents': sum(bool(r.get('captions')) for r in rows),
        'attached_by_type': dict(Counter(c['type'] for r in rows for c in r.get('captions', []))),
        'word_loss_documents': sum(bool(r.get('word_loss')) for r in rows),
        'word_gain_documents': sum(bool(r.get('word_gain')) for r in rows),
        'probe_errors': sum('probe_error' in r for r in rows),
        'attached_text_mismatches': sum(r.get('attached_text_matches_source') is False for r in rows),
        'caption_markdown_count_mismatches': sum(r.get('caption_markdown_counts_match') is False for r in rows),
        'changed_error_documents': sum(r.get('errors_before') != r.get('errors_after') for r in rows),
        'scan_skips': sum('scan_skip' in r for r in rows),
        'paired_candidate_documents': sum(bool(r.get('pairs')) for r in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'summary': summary, 'documents': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return int(any(summary[key] for key in ('probe_errors', 'word_loss_documents', 'word_gain_documents',
        'attached_text_mismatches', 'caption_markdown_count_mismatches', 'changed_error_documents')))


if __name__ == '__main__':
    raise SystemExit(main())
