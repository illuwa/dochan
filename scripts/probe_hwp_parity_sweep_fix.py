"""4차 감수 수정의 지문·제목·개체 순서를 읽기 전용으로 측정한다.

scan CORPUS --source-root SOURCE --output hashes.json [--private-pairs PAIRS]
diff BEFORE AFTER --output delta.json
본문은 저장하지 않는다. 내부 짝은 숫자 인덱스와 해시·집계만 저장한다.
"""

import argparse
from collections import Counter
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import struct
import sys


def sha(text):
    return hashlib.sha256(text.encode('utf-8', errors='surrogatepass')).hexdigest()


def compact(text):
    return ''.join(re.sub(r'\[bookmark: [^\]\r\n]+\] ', '', text).split())


def _initialize(source):
    sys.path.insert(0, source)
    import dochan.hwp.section as module
    from dochan.hwp.records.para_text import parse_para_text
    from dochan.hwp.records.ctrl_header import parse_ctrl_id
    from dochan.model.document import Paragraph
    from dochan.model.table import Table
    from dochan.model.header_footer import HeaderFooter, Footnote
    from dochan.model.image import Image

    global _stats, _flows
    _stats, _flows = Counter(), []
    stack = []
    original_control = module.SectionParser._parse_control

    def control(self, node):
        result = original_control(self, node)
        if stack:
            objects = result if isinstance(result, list) else [result] if result else []
            stack[-1].append((node['record'].data, objects))
        return result

    module.SectionParser._parse_control = control
    original_group = module.SectionParser._parse_paragraph_group_impl

    def group(self, node):
        stack.append([])
        try:
            result = original_group(self, node)
        finally:
            controls = stack.pop()
        raw = next((parse_para_text(child['record'].data) for child in node['children']
                    if child['record'].tag_id == 67), None)
        if raw:
            anchors = {}
            for start, _end, cid in raw.get('inline_controls', []):
                anchors.setdefault(cid, []).append(start)
            seen = Counter()
            positions = {id(obj): index for index, obj in enumerate(result)}
            control_ids = {id(obj) for _data, elems in controls for obj in elems}
            host_paragraphs = [index for index, obj in enumerate(result)
                               if isinstance(obj, Paragraph) and id(obj) not in control_ids]
            objects = []
            for data, elems in controls:
                cid = parse_ctrl_id(data)
                index = seen[cid]
                seen[cid] += 1
                locations = anchors.get(cid, [])
                if index >= len(locations):
                    continue
                start = locations[index]
                for obj in elems:
                    if id(obj) in positions:
                        kind = ('table' if isinstance(obj, Table) else
                                'image' if isinstance(obj, Image) else
                                'header' if isinstance(obj, HeaderFooter) else
                                'note' if isinstance(obj, Footnote) else 'shape')
                        objects.append((start, positions[id(obj)], kind))
                        if isinstance(obj, (Table, HeaderFooter)):
                            projected = raw['raw_to_text'][start]
                            if 0 < projected < len(raw['text']):
                                place = positions[id(obj)]
                                split_here = (any(p < place for p in host_paragraphs) and
                                              any(p > place for p in host_paragraphs))
                                as_char = len(data) >= 8 and struct.unpack_from('<I', data, 4)[0] & 1
                                label = ('table_char' if as_char else 'table_float') if kind == 'table' else 'header'
                                _stats[label + '_middle_splits'] += int(split_here)
            inversions = Counter()
            for index, (raw_a, out_a, kind_a) in enumerate(objects):
                for raw_b, out_b, kind_b in objects[index + 1:]:
                    if (kind_a == 'table') == (kind_b == 'table'):
                        continue
                    if (raw_a < raw_b) != (out_a < out_b):
                        inversions[kind_b if kind_a == 'table' else kind_a] += 1
            _stats.update({'inversion_' + kind: count for kind, count in inversions.items()})
        return result

    module.SectionParser._parse_paragraph_group_impl = group
    original_split = getattr(module, '_split_paragraph_blocks', None)
    if original_split:
        def split(para, blocks, sizes, **kwargs):
            result = original_split(para, blocks, sizes, **kwargs)
            ids = {id(obj) for _raw, _pos, obj in blocks}
            fragments = [obj for obj in result if isinstance(obj, Paragraph) and id(obj) not in ids]
            _flows.append((sha(compact(para.text)), fragments))
            _stats['flows'] += 1
            _stats['whitespace_discarded'] += len(para.text) - sum(len(p.text) for p in fragments)
            # The review counted rendered fragments, which also include an
            # inline note/equation before a source anchor at text position 0.
            specs = {id(obj): data for data, objects in stack[-1] for obj in objects}
            locations = [index for index, obj in enumerate(result)
                         if isinstance(obj, Paragraph) and id(obj) not in ids]
            if locations:
                for index, obj in enumerate(result):
                    if not locations[0] < index < locations[-1]:
                        continue
                    if isinstance(obj, Table):
                        data = specs.get(id(obj), b'')
                        as_char = len(data) >= 8 and struct.unpack_from('<I', data, 4)[0] & 1
                        label = 'table_char' if as_char else 'table_float'
                    elif isinstance(obj, HeaderFooter):
                        label = 'header'
                    else:
                        continue
                    _stats[label + '_rendered_middle_splits'] += 1
            return result
        module._split_paragraph_blocks = split


def _first_block(markdown):
    text = markdown.lstrip()
    return ('empty' if not text else 'comment' if text.startswith('<!--') else
            'heading' if text.startswith('#') else 'table' if text.startswith('|') else
            'image' if text.startswith('![') else 'note' if text.startswith('[^') else
            'equation' if text.startswith('$$') else 'paragraph')


def _block_tokens(data):
    def value(elements):
        output = []
        for elem in elements:
            if elem['type'] == 'paragraph':
                output.append(compact(elem['text']))
            elif elem['type'] == 'table':
                for row in elem['rows']:
                    for cell in row:
                        output.extend(value(cell['paragraphs']))
            elif 'elements' in elem:
                output.extend(value(elem['elements']))
        return output

    tokens = []
    for section in data['sections']:
        for elem in section['elements']:
            kind = elem['type']
            if kind == 'table':
                tokens.append('T' + sha('|'.join(value([elem]))))
            elif kind == 'image':
                tokens.append('I')
            elif kind in ('header', 'footer'):
                tokens.append(kind[0].upper() + sha('|'.join(value(elem['elements']))))
            elif kind in ('footnote', 'endnote'):
                tokens.append('N' + str(elem.get('number', 0)))
    return tokens


def _fingerprint(path):
    from dochan import Dochan
    _stats.clear()
    _flows.clear()
    reader = Dochan(str(path))
    data = reader.to_dict()
    markdown, plain = reader.to_markdown(), reader.to_plain_text()
    headings = [(sha(compact(p.text)), p.heading_level)
                for p in reader.doc.find_all('paragraph') if p.heading_level]
    first = next((p for section in reader.doc.sections for p in section.elements
                  if hasattr(p, 'heading_level') and p.heading_level), None)
    flow_heads = [(parent, [sha(compact(p.text)) for p in fragments if p.heading_level])
                  for parent, fragments in _flows]
    return reader, {
        'format': reader.doc.source_format,
        'json': sha(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))),
        'markdown': sha(markdown), 'plain': sha(plain),
        'markdown_length': len(markdown), 'plain_length': len(plain),
        'plain_multiset': sha(json.dumps(sorted(Counter(''.join(plain.split())).items()))),
        'errors': list(reader.errors), 'headings': headings,
        'first_heading': sha(compact(first.text)) if first is not None else '',
        'first_heading_raw': sha(first.text) if first is not None else '',
        'first_block': _first_block(markdown), 'tokens': _block_tokens(data),
        'counts': {kind: len(reader.doc.find_all(kind)) for kind in
                   ('table', 'image', 'equation', 'footnote', 'endnote', 'header_footer', 'comment')},
        'flow_heading_sources': flow_heads, 'flow_stats': dict(_stats),
    }


def _file(task):
    root, name = task
    try:
        return name, _fingerprint(Path(root) / name)[1]
    except Exception as exc:
        return name, {'exception': type(exc).__name__}


def _pair(task):
    index, answer_path, candidate_path = task
    from scripts.probe_hwp_parity_sweep import summarize_pair
    try:
        answer, a = _fingerprint(answer_path)
        candidate, b = _fingerprint(candidate_path)
        row = summarize_pair(answer, candidate)
        for key, kinds in (('table_image', 'TI'), ('table_note', 'TN'), ('table_header', 'THF')):
            row[key + '_equal'] = ([t for t in a['tokens'] if t[0] in kinds] ==
                                  [t for t in b['tokens'] if t[0] in kinds])
        # Internal diagnostics can contain names. Keep only counts here.
        row['errors'] = {'hwpx': len(a['errors']), 'hwp': len(b['errors'])}
        return index, row
    except Exception as exc:
        return index, {'exception': type(exc).__name__}


def _pair_summary(rows):
    eligible = [r for r in rows.values() if r.get('same_document')]
    return {'pairs': len(rows), 'eligible': len(eligible),
            'markdown_exact': sum(r['markdown_equal'] for r in eligible),
            'asset_neutral_exact': sum(r['asset_neutral_markdown_equal'] for r in eligible),
            'plain_exact': sum(r['plain_equal'] for r in eligible),
            'classes': dict(Counter(r['difference_class'] for r in eligible))}


def scan(args):
    from scripts.probe_hwp_parity_sweep import discover_pairs
    source = str(args.source_root.resolve())
    root = args.corpus.resolve()
    files = sorted(str(p.relative_to(root)) for directory in ('hwp', 'hwpx')
                   for p in (root / directory).iterdir()
                   if p.is_file() and p.suffix.lower() in ('.hwp', '.hwpx'))
    with multiprocessing.get_context('spawn').Pool(
            args.workers, initializer=_initialize, initargs=(source,), maxtasksperchild=25) as pool:
        rows = {}
        for index, (name, row) in enumerate(pool.imap_unordered(
                _file, [(str(root), name) for name in files]), 1):
            rows[name] = row
            if index % 500 == 0:
                print('files {}/{}'.format(index, len(files)), flush=True)
        pairs = dict(pool.imap_unordered(_pair, discover_pairs(root)))
        press = dict(pool.imap_unordered(_pair, discover_pairs(args.press_pairs))) if args.press_pairs else {}
        private = {}
        if args.private_pairs:
            from scripts.compare_hwp_pairs import find_pairs
            tasks = [(str(i), a, b) for i, (_name, a, b) in enumerate(find_pairs([str(args.private_pairs)]))]
            private = dict(pool.imap_unordered(_pair, tasks))
    result = {'files': rows, 'pairs': pairs, 'press': press, 'private': private,
              'summary': {name: _pair_summary(group) for name, group in
                          (('pairs', pairs), ('press', press), ('private', private))}}
    args.output.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False), flush=True)


def refresh_changes(args):
    """변경된 공개 파일만 추가 지표를 재측정한다."""
    names = json.loads(args.changes.read_text(encoding='utf-8'))['files']['changed_public_files']
    with multiprocessing.get_context('spawn').Pool(
            args.workers, initializer=_initialize,
            initargs=(str(args.source_root.resolve()),), maxtasksperchild=25) as pool:
        rows = dict(pool.imap_unordered(_file, [(str(args.corpus.resolve()), name) for name in names]))
    result = json.loads(args.snapshot.read_text(encoding='utf-8'))
    for name, row in rows.items():
        # The refresh may add metrics, but must not change measured outputs.
        assert all(json.loads(json.dumps(row.get(key))) == result['files'][name].get(key)
                   for key in ('json', 'markdown', 'plain', 'errors', 'headings'))
        result['files'][name] = row
    args.snapshot.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print('refreshed {}'.format(len(rows)))


def diff(args):
    before, after = (json.loads(path.read_text(encoding='utf-8')) for path in (args.before, args.after))
    result = {}
    reference = (json.loads(args.pair_reference.read_text(encoding='utf-8'))['pairs']
                 if args.pair_reference else None)
    for name in ('pairs', 'press', 'private'):
        a, b = before[name], after[name]
        keys = [key for key in a.keys() & b.keys() if a[key].get('same_document')]
        if name == 'pairs' and reference is not None:
            keys = [key for key in keys if reference.get(key, {}).get('same_document')]
        changes = {}
        for metric in ('markdown_equal', 'asset_neutral_markdown_equal', 'plain_equal',
                       'table_image_equal', 'table_note_equal', 'table_header_equal'):
            changes[metric] = {
                'before': sum(a[k].get(metric, False) for k in keys),
                'after': sum(b[k].get(metric, False) for k in keys),
                'plus': sum(not a[k].get(metric) and b[k].get(metric, False) for k in keys),
                'minus': sum(a[k].get(metric, False) and not b[k].get(metric) for k in keys)}
        result[name] = {'compared': len(keys), 'metrics': changes,
                        'after_classes': dict(Counter(b[k].get('difference_class') for k in keys))}
    a, b = before['files'], after['files']
    counts = Counter()
    heading_counts = Counter()
    flow_stats = Counter()
    inversion_changes = Counter()
    heading_formats = {}
    changed = []
    for key in sorted(a.keys() & b.keys()):
        old, new = a[key], b[key]
        if old.get('json') != new.get('json'):
            changed.append(key)
        for metric in ('json', 'markdown', 'plain', 'errors', 'exception', 'plain_multiset',
                       'counts', 'first_block', 'first_heading', 'first_heading_raw'):
            counts[metric] += old.get(metric) != new.get(metric)
        heading_counts['before'] += len(old.get('headings', []))
        heading_counts['after'] += len(new.get('headings', []))
        group = heading_formats.setdefault(old.get('format', 'unreadable'), Counter())
        group['before'] += len(old.get('headings', []))
        group['after'] += len(new.get('headings', []))
        source_heads = {item[0] for item in old.get('headings', [])}
        for parent, fragments in new.get('flow_heading_sources', []):
            heading_counts['split_headings'] += max(0, len(fragments) - 1)
            heading_counts['fake_fragment_headings'] += bool(fragments and parent not in source_heads)
        flow_stats.update(new.get('flow_stats', {}))
        for metric in ('image', 'shape', 'header', 'note'):
            delta = (new.get('flow_stats', {}).get('inversion_' + metric, 0) -
                     old.get('flow_stats', {}).get('inversion_' + metric, 0))
            inversion_changes[metric + '_added'] += max(0, delta)
            inversion_changes[metric + '_removed'] += max(0, -delta)
    result['files'] = {'total': len(a.keys() & b.keys()), 'changes': dict(counts),
                       'heading_counts': dict(heading_counts), 'flow_stats': dict(flow_stats),
                       'headings_by_format': {key: dict(row) for key, row in heading_formats.items()},
                       'inversion_changes': dict(inversion_changes),
                       'changed_public_files': changed}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result['files'].items() if k != 'changed_public_files'}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan_parser = commands.add_parser('scan')
    scan_parser.add_argument('corpus', type=Path)
    scan_parser.add_argument('--source-root', type=Path, default=Path.cwd())
    scan_parser.add_argument('--press-pairs', type=Path)
    scan_parser.add_argument('--private-pairs', type=Path)
    scan_parser.add_argument('--workers', type=int, default=4)
    scan_parser.add_argument('--output', type=Path, required=True)
    scan_parser.set_defaults(func=scan)
    diff_parser = commands.add_parser('diff')
    diff_parser.add_argument('before', type=Path)
    diff_parser.add_argument('after', type=Path)
    diff_parser.add_argument('--output', type=Path, required=True)
    diff_parser.add_argument('--pair-reference', type=Path,
                             help='same_document 판정을 저장한 JSON으로 비교 분모를 고정한다.')
    diff_parser.set_defaults(func=diff)
    refresh_parser = commands.add_parser('refresh-changes')
    refresh_parser.add_argument('corpus', type=Path)
    refresh_parser.add_argument('changes', type=Path)
    refresh_parser.add_argument('snapshot', type=Path)
    refresh_parser.add_argument('--source-root', type=Path, default=Path.cwd())
    refresh_parser.add_argument('--workers', type=int, default=4)
    refresh_parser.set_defaults(func=refresh_changes)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
