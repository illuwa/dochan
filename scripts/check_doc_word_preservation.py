"""Compare every public DOC against a pinned pre-structure reader.

Only word occurrences justified by bounded CP or baseline-decoder evidence may
be discounted. No sample-name allowlist is used. The corpus is read-only.
Run with --poi POI_DOCUMENT --lo LO_ROOT --output RESULT.json.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import types

from dochan import cfb

from dochan.model.document import Document
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.doc_binary import DocBinary
from dochan.office_binary.doc_stories import Stories
from dochan.utils.bounded_io import (ByteBudget, MAX_OLE_DOCUMENT_SIZE,
    MAX_OLE_STREAM_SIZE, read_ole_stream, validate_file_size)


def words(text):
    return Counter(re.findall(r'\w+', text))


def document_text(doc):
    # Runs are joined within each paragraph: bold/italic boundaries are not
    # linguistic boundaries. Table and story paragraphs are visited once.
    return '\n'.join(''.join(r.text for r in p.runs
        if not (r.provenance is None and re.fullmatch(r'\[bookmark: [^\]]+\] ', r.text)))
        for p in doc.find_all('paragraph'))


def classify_losses(before, after, evidence):
    remaining = before - after
    result = {}
    for category, budget in evidence:
        accepted = remaining & budget
        if accepted:
            result[category] = dict(sorted(accepted.items()))
            remaining -= accepted
    result['unclassified'] = dict(sorted(remaining.items()))
    return result


def load_baseline(ref):
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', ref], text=True).strip()
    source = subprocess.check_output(['git', '-C', str(root), 'show',
        revision + ':dochan/office_binary/doc.py'], text=True)
    if 'parse_structured_doc' in source:
        raise ValueError('baseline already uses structured DOC parsing; choose an earlier revision')
    module = types.ModuleType('dochan.office_binary._word_audit_baseline')
    module.__package__ = 'dochan.office_binary'
    exec(compile(source, '<git DOC baseline>', 'exec'), module.__dict__)
    return module, revision


def read_binary(path):
    validate_file_size(str(path), MAX_OLE_DOCUMENT_SIZE)
    budget = ByteBudget(MAX_OLE_DOCUMENT_SIZE)
    with cfb.OleFileIO(str(path)) as ole:
        def read(name):
            return read_ole_stream(ole, name, max_bytes=MAX_OLE_STREAM_SIZE, budget=budget)
        word = read('WordDocument')
        names = DOCReader()._table_stream_names(ole, word)
        tables = [(name, read(name)) for name in names]
        data = read('Data') if ole.exists('Data') else b''
    for name, table in tables:
        binary = DocBinary(word, table, data)
        if binary.valid:
            return binary, name
    return None, ''


def canonical_words(text, baseline):
    return words('\n'.join(baseline._clean_text_lines(text)))


def transition_budget(before_text, after_text, baseline):
    return canonical_words(before_text, baseline) - canonical_words(after_text, baseline)


def cp_evidence(binary, baseline, after):
    stories = Stories(binary, Document())
    raw = binary.text
    deleted_cps = [cp for cp in range(len(raw)) if binary.char_props(cp).get('deleted')]
    deletion_set = set(deleted_cps)
    without_deletion = ''.join(c for cp, c in enumerate(raw) if cp not in deletion_set)
    def excluded(cp):
        return cp in deletion_set

    valid_story_text = ''.join(c for cp, c in enumerate(raw) if not excluded(cp))
    story_boundaries = {start for start, end in binary.stories.values() if start and start < end}
    partitioned_text = ''.join(('\n' if cp in story_boundaries else '') + c
                               for cp,c in enumerate(raw) if not excluded(cp))
    # Transform original CPs, never CP positions shifted by an earlier removal.
    visible = []
    for cp, char in enumerate(raw):
        if excluded(cp):
            continue
        if cp in story_boundaries:
            visible.append('\n')
        if not stories.hidden(cp):
            visible.append(char)
        # End delimiters themselves are hidden, but visible field results have
        # exported targets and separator-less controls have display markers.
        visible.append(stories.suffix(cp))
        for marker in stories.markers(cp):
            if not marker.text.startswith('[bookmark:') and not marker.note_reference_type:
                visible.append(marker.text)
    field_visible = ''.join(visible)
    without_optional_hyphen = field_visible.replace('\x1f', '')
    normalized_controls = ''.join(
        '\n' if c in '\r\x07\x0b\x0c\x0e' else '-' if c == '\x1e'
        else c if ord(c) >= 32 or c in '\t\n' else ''
        for c in without_optional_hyphen)
    evidence = [
        ('tracked_deletion', transition_budget(raw, without_deletion, baseline)),
        ('story_partition', transition_budget(valid_story_text, partitioned_text, baseline)),
        ('hidden_field', transition_budget(partitioned_text, field_visible, baseline)),
        ('optional_hyphen', transition_budget(field_visible, without_optional_hyphen, baseline)),
        ('control_character_normalization', transition_budget(without_optional_hyphen, normalized_controls, baseline)),
    ]
    details = {
        'story_partition': {'basis': 'FibRgLw story CP boundaries separate main/body and subdocuments', 'cps': sorted(story_boundaries)},
        'tracked_deletion': {'basis': 'CHPX sprmCFRMarkDel CPs; compare before/after complete words including partial deletions',
                             'cp_ranges': consecutive_ranges(deleted_cps)},
        'hidden_field': {'basis': 'field instruction intervals and recovered display markers',
                         'fields': [{'cp': [f.start, f.separator, f.end], 'instruction': f.instruction}
                                    for f in stories.fields]},
        'control_character_normalization': {'basis': 'control characters are semantic markers, not literal word separators',
            'cp_ranges': consecutive_ranges([i for i,c in enumerate(raw) if ord(c) < 32 and c not in '\t\n\r\x07\x0b\x0c\x0e'])},
        'optional_hyphen': {'basis': 'MS-DOC U+001F discretionary hyphens are omitted',
                            'cps': [i for i,c in enumerate(raw) if c == '\x1f']},
    }
    # A removed fragment is explained by concatenation only when its newly
    # formed complete word actually survived the current reader.
    first = canonical_words(raw, baseline)
    last = canonical_words(normalized_controls, baseline)
    added = last - first
    unmet = Counter({w: max(0, last[w] - after[w]) for w in added})
    unmet += Counter()
    details['replacement_word_requirements'] = {'required': dict(added), 'unmet': dict(unmet)}
    if unmet:
        evidence = []
    else:
        # A token may disappear then reappear between transformations. Never
        # explain that occurrence twice: final surviving source words win.
        cap = first - last
        bounded = []
        for name, budget in evidence:
            accepted = budget & cap
            bounded.append((name, accepted))
            cap -= accepted
        evidence = bounded
    return evidence, details


def consecutive_ranges(cps):
    result = []
    for cp in cps:
        if result and result[-1][1] == cp:
            result[-1][1] += 1
        else:
            result.append([cp, cp + 1])
    return result


def has_new_fatal(old_errors, new_errors):
    return (any(e.startswith('ERR:') for e in new_errors)
            and not any(e.startswith('ERR:') for e in old_errors))


def audit_document(path, baseline, compare_renderer=False):
    old = baseline.DOCReader().read(str(path))
    new = DOCReader().read(str(path))
    before, after = words(document_text(old)), words(document_text(new))
    evidence, details = [], {}
    row = {'file': path.name, 'old_words': sum(before.values()),
           'new_words': sum(after.values()), 'old_errors': old.errors, 'new_errors': new.errors,
           'new_fatal_error': has_new_fatal(old.errors, new.errors)}
    if compare_renderer:
        from dochan.office_binary.doc_structure import StructureRenderer
        from dochan.output.json_out import to_dict

        def per_character(renderer, record):
            for cp in range(record.start, record.end):
                yield cp, renderer.binary.text[cp], renderer.binary.char_props(cp)

        original = StructureRenderer._chunks
        try:
            StructureRenderer._chunks = per_character
            reference = DOCReader().read(str(path))
        finally:
            StructureRenderer._chunks = original
        row['renderer_equivalent'] = to_dict(new) == to_dict(reference)
    if before - after:
        binary, stream_name = read_binary(path)
        if binary is not None:
            evidence, details = cp_evidence(binary, baseline, after)
            canonical = baseline.build_structured_section(
                baseline._clean_text_lines(binary.text), 'doc')
            canonical_doc = Document(sections=[canonical])
            canonical_words = words(document_text(canonical_doc))
            # The exact old decoder applied to a validated CLX establishes what
            # old output words could come from current document characters.
            # Excesses are stale/non-piece bytes or baseline decoder artifacts;
            # all current-CLX occurrences remain protected by their counts.
            non_piece = before - canonical_words
            evidence.insert(0, ('legacy_non_piece_text', non_piece))
            details['legacy_non_piece_text'] = {
                'basis': 'old output minus identical legacy cleanup/model of validated PlcPcd text',
                'table_stream': stream_name,
                'clx_sha256': hashlib.sha256(binary.blob(33)).hexdigest(),
                'piece_count': len(binary.pieces), 'cp_count': len(binary.text),
                'candidate_words': dict(sorted(non_piece.items()))}
    row['losses'] = classify_losses(before, after, evidence)
    row['lost_words'] = sum((before - after).values())
    row['evidence'] = details
    row['unclassified_words'] = sum(row['losses']['unclassified'].values())
    return row


def corpus_paths(poi, lo):
    if poi:
        for path in sorted(poi.iterdir()):
            if path.is_file() and path.suffix.lower() == '.doc':
                yield 'poi', path
    if lo:
        for group in ('ww8export', 'ww8import', 'ooxmlexport'):
            directory = lo / 'sw' / 'qa' / 'extras' / group / 'data'
            for path in sorted(directory.glob('*.doc')):
                yield 'lo/' + group, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi', type=Path)
    parser.add_argument('--lo', type=Path)
    parser.add_argument('--baseline-ref', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-renderer-equivalence', action='store_true',
                        help='compare full JSON with the per-character renderer')
    args = parser.parse_args()
    if not args.poi and not args.lo:
        parser.error('at least one corpus is required')
    baseline, revision = load_baseline(args.baseline_ref)
    rows = []
    for corpus, path in corpus_paths(args.poi, args.lo):
        try:
            row = audit_document(path, baseline, args.check_renderer_equivalence)
        except Exception as exc:
            row = {'file': path.name, 'audit_error': type(exc).__name__ + ': ' + str(exc),
                   'unclassified_words': 0}
        row['corpus'] = corpus
        rows.append(row)
    categories = Counter()
    for row in rows:
        for name, counts in row.get('losses', {}).items():
            categories[name] += sum(counts.values())
    summary = {'documents': len(rows), 'corpora': dict(Counter(r['corpus'] for r in rows)),
               'documents_with_loss': sum(bool(r.get('lost_words')) for r in rows),
               'unclassified_documents': sum(bool(r['unclassified_words']) for r in rows),
               'loss_categories': dict(categories),
               'audit_errors': sum('audit_error' in r for r in rows),
               'renderer_checks': sum('renderer_equivalent' in r for r in rows),
               'renderer_differences': sum(r.get('renderer_equivalent') is False for r in rows),
               'new_fatal_documents': sum(r.get('new_fatal_error', False) for r in rows)}
    result = {'baseline_revision': revision, 'metric': 'case-sensitive Unicode word occurrence multiset from paragraph text',
              'summary': summary, 'documents': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if (summary['unclassified_documents'] or summary['audit_errors']
                 or summary['new_fatal_documents'] or summary['renderer_differences']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
