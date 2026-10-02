"""공개 PPT/PPTX 짝의 같은 슬라이드·같은 문단에서 굵게/기울임을 비교한다."""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path

import olefile

from dochan import Dochan
from dochan.office_binary.officeart import walk_records
from dochan.office_binary.ppt_structure import resolve_presentation
from dochan.office_binary.ppt_text import _Cursor, _character_properties, _paragraph_properties
from dochan.utils.bounded_io import read_ole_stream


def inspect_master_records(path):
    """공개 파일의 4003/4004 원시 마스크와 값·바이트 위치를 남긴다."""
    with olefile.OleFileIO(str(path)) as ole:
        presentation = resolve_presentation(read_ole_stream(ole, 'PowerPoint Document'),
                                            read_ole_stream(ole, 'Current User'), [])
    rows = []
    if presentation is None:
        return rows
    sources = [('environment', list(walk_records(presentation.document.children)))]
    sources += [(str(key), sheet.record.children) for key, sheet in presentation.masters.items()]
    for source, records in sources:
        for atom in records:
            if atom.header.rec_type not in (4003, 4004):
                continue
            cursor = _Cursor(atom.data)
            row = {'source': source, 'record_type': atom.header.rec_type,
                   'text_type': atom.header.rec_instance, 'offset': atom.offset, 'levels': []}
            try:
                count = cursor.read('<H') if atom.header.rec_type == 4003 else 1
                if count > 5:
                    raise ValueError('too many levels')
                for index in range(count):
                    level = index
                    if atom.header.rec_type == 4003:
                        if atom.header.rec_instance >= 5:
                            level = cursor.read('<H')
                        _paragraph_properties(cursor, cursor.read('<I'))
                    offset = cursor.pos
                    mask = cursor.read('<I')
                    values = _character_properties(cursor, mask)
                    row['levels'].append({'level': level, 'cf_offset': offset, 'mask': hex(mask),
                                          'bold_italic_underline_size_baseline': values})
            except ValueError as exc:
                row['error'] = str(exc)
            rows.append(row)
    return rows


def paragraphs(doc):
    result = defaultdict(deque)
    for p in doc.find_all('paragraph'):
        slide = getattr(p.provenance, 'slide', None)
        path = getattr(p.provenance, 'path', '') or ''
        if slide and not any(x in path for x in ('notes', 'comments')):
            result[(slide, p.text.strip())].append(p)
    return result


def compare(ppt, pptx):
    candidate, answer = Dochan(str(ppt)), Dochan(str(pptx))
    pool = paragraphs(candidate.doc)
    result = {'ppt': str(ppt), 'pptx': str(pptx), 'matched_paragraphs': 0,
              'unmatched_paragraphs': 0, 'runs': 0, 'equal_runs': 0,
              'characters': 0, 'equal_characters': 0, 'mismatches': [],
              'errors': candidate.errors, 'answer_errors': answer.errors}
    for key, entries in paragraphs(answer.doc).items():
        for p in entries:
            if not pool[key]:
                result['unmatched_paragraphs'] += 1
                continue
            other = pool[key].popleft()
            result['matched_paragraphs'] += 1
            a = [(c, r.bold, r.italic) for r in p.runs for c in r.text]
            b = [(c, r.bold, r.italic) for r in other.runs for c in r.text]
            while a and a[0][0].isspace():
                a.pop(0)
            while b and b[0][0].isspace():
                b.pop(0)
            while a and a[-1][0].isspace():
                a.pop()
            while b and b[-1][0].isspace():
                b.pop()
            result['characters'] += len(a)
            result['equal_characters'] += sum(x == y for x, y in zip(a, b))
            offset = 0
            leading = len(p.text) - len(p.text.lstrip())
            for r in p.runs:
                lo, hi = max(0, offset - leading), min(len(a), offset + len(r.text) - leading)
                offset += len(r.text)
                if hi <= lo:
                    continue
                result['runs'] += 1
                if a[lo:hi] == b[lo:hi]:
                    result['equal_runs'] += 1
                else:
                    result['mismatches'].append({'slide': key[0], 'text': r.text,
                                                 'answer': [r.bold, r.italic],
                                                 'candidate': sorted(set((x[1], x[2]) for x in b[lo:hi]))})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--record-sample', type=Path, action='append', default=[])
    args = parser.parse_args()
    rows = [compare(p, p.with_suffix('.pptx')) for name in ('poi-src', 'lo-src', 'tika-test-docs')
            for p in sorted((args.corpus / name).rglob('*.ppt')) if p.with_suffix('.pptx').exists()]
    summary = {key: sum(r[key] for r in rows) for key in
               ('matched_paragraphs', 'unmatched_paragraphs', 'runs', 'equal_runs', 'characters', 'equal_characters')}
    raw = {str(path): inspect_master_records(path) for path in args.record_sample}
    args.output.write_text(json.dumps({'summary': summary, 'pairs': rows, 'raw_master_records': raw},
                                     ensure_ascii=False, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
