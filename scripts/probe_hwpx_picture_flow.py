"""Compare public HWP/HWPX Markdown and JSON without storing document output.

Run once against the old source and again with --reference and --baseline-code.
Only changed documents are parsed a second time for structural invariants.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from dochan import Dochan
from dochan.model.document import Paragraph
from dochan.model.equation import Equation
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Table


def _paths(roots, suffixes):
    for index, root in enumerate(roots):
        root = Path(root)
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix.lower() in suffixes:
                yield '%d/%s' % (index, path.relative_to(root)), path


def _trace_elements(elements, out, depth=0):
    if depth > 40:
        out.append(['X', 'depth-limit'])
        return
    for item in elements:
        if isinstance(item, Paragraph):
            out.append(['P', item.heading_level, item.text])
        elif isinstance(item, Image):
            out.append(['I', item.filename, item.bin_id, item.alt_text,
                        item.caption_text, item.caption_side])
            if item.caption:
                out.append(['CAP<'])
                _trace_elements(item.caption, out, depth + 1)
                out.append(['CAP>'])
        elif isinstance(item, Table):
            out.append(['T<', item.row_count, item.col_count])
            for row_number, row in enumerate(item.rows):
                for col_number, cell in enumerate(row):
                    out.append(['C', row_number, col_number])
                    _trace_elements(cell.paragraphs, out, depth + 1)
            if item.caption:
                out.append(['CAP<'])
                _trace_elements(item.caption, out, depth + 1)
                out.append(['CAP>'])
            out.append(['T>'])
        elif isinstance(item, Equation):
            out.append(['E', item.script])
        elif isinstance(item, (HeaderFooter, Footnote)):
            out.append(['H<', item.type])
            _trace_elements(item.paragraphs, out, depth + 1)
            out.append(['H>'])
        else:
            out.append(['X', type(item).__name__])


def _read(path, detail=False):
    try:
        reader = (Dochan(str(path), include_assets=False)
                  if path.suffix.lower() == '.hwpx' else Dochan(str(path)))
        markdown = reader.to_markdown()
        encoded_json = reader.to_json().encode('utf-8')
        row = {
            'markdown_sha256': hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
            'markdown_characters': len(markdown),
            'json_sha256': hashlib.sha256(encoded_json).hexdigest(),
            'json_bytes': len(encoded_json),
            'errors': list(reader.errors),
        }
        if detail:
            trace = []
            for section in reader.doc.sections:
                section_trace = []
                _trace_elements(section.elements, section_trace)
                trace.append(section_trace)
            row['trace'] = trace
        return row
    except Exception as exc:
        return {'exception': type(exc).__name__, 'message': str(exc)[:200]}


def _groups(section):
    skeleton = []
    groups = []
    current = []
    folded = []
    index = 0
    while index < len(section):
        event = section[index]
        if (event[0] == 'I' and index + 1 < len(section)
                and section[index + 1][0] == 'CAP<'):
            depth = 0
            end = index + 1
            while end < len(section):
                if section[end][0] == 'CAP<':
                    depth += 1
                elif section[end][0] == 'CAP>':
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            folded.append(event + [section[index + 1:end + 1]])
            index = end + 1
        else:
            folded.append(event)
            index += 1
    for event in folded:
        if event[0] in {'T<', 'T>', 'C', 'E', 'H<', 'H>', 'CAP<', 'CAP>', 'X'}:
            groups.append(current)
            current = []
            skeleton.append(event)
        else:
            current.append(event)
    groups.append(current)
    return skeleton, groups


def _compare_traces(before, after):
    """Require the same containers/images/letters and at most one paragraph of image movement."""
    reasons = []
    heading_changes = 0
    image_moves = 0
    if len(before) != len(after):
        return {'valid': False, 'reasons': ['section_count'],
                'heading_changes': 0, 'image_moves': 0}
    for old_section, new_section in zip(before, after):
        old_skeleton, old_groups = _groups(old_section)
        new_skeleton, new_groups = _groups(new_section)
        if old_skeleton != new_skeleton:
            reasons.append('structure')
            continue
        for old, new in zip(old_groups, new_groups):
            old_images = [event for event in old if event[0] == 'I']
            new_images = [event for event in new if event[0] == 'I']
            if old_images != new_images:
                reasons.append('image_order_or_identity')
                continue
            old_paragraphs = [event for event in old if event[0] == 'P']
            new_paragraphs = [event for event in new if event[0] == 'P']
            def normalize(paragraphs):
                return re.sub(r'\s+', '', ''.join(event[2] for event in paragraphs))
            if normalize(old_paragraphs) != normalize(new_paragraphs):
                reasons.append('nonspace_text')
                continue
            if len(old_paragraphs) == len(new_paragraphs):
                heading_changes += sum(a[1] != b[1] for a, b in zip(old_paragraphs, new_paragraphs))
            # 문단 병합 후의 새 문단 경계에 원래 그림 위치를 투영한다.
            # 단순 문단 개수 차이는 병합 자체를 그림 이동으로 오인한다.
            new_ends = []
            text_end = 0
            for event in new:
                if event[0] == 'P':
                    text_end += len(re.sub(r'\s+', '', event[2]))
                    new_ends.append(text_end)
            old_positions = []
            text_before = 0
            for event in old:
                if event[0] == 'P':
                    text_before += len(re.sub(r'\s+', '', event[2]))
                elif event[0] == 'I':
                    old_positions.append(sum(end <= text_before for end in new_ends))
            new_positions = [sum(event[0] == 'P' for event in new[:i])
                             for i, event in enumerate(new) if event[0] == 'I']
            for old_pos, new_pos in zip(old_positions, new_positions):
                shift = old_pos - new_pos
                if abs(shift) > 1:
                    reasons.append('image_moved_over_one_paragraph')
                elif shift:
                    image_moves += 1
    return {'valid': not reasons, 'reasons': sorted(set(reasons)),
            'heading_changes': heading_changes, 'image_moves': image_moves}


def _only_heading_levels_changed(before, after):
    def without_levels(trace):
        return [[['P', None, event[2]] if event[0] == 'P' else event
                 for event in section] for section in trace]

    return before != after and without_levels(before) == without_levels(after)


def _baseline_detail(code_root, path):
    command = [sys.executable, '-m', 'scripts.probe_hwpx_picture_flow',
               '--detail', str(path.resolve())]
    # nosemgrep: dangerous-subprocess-use-audit
    result = subprocess.run(command, cwd=str(code_root), check=True,
                            capture_output=True, text=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--reference')
    parser.add_argument('--baseline-code', type=Path)
    parser.add_argument('--detail', type=Path)
    parser.add_argument('--suffix', choices=('hwp', 'hwpx', 'both'), default='both')
    parser.add_argument('roots', nargs='*')
    args = parser.parse_args()
    if args.detail:
        print(json.dumps(_read(args.detail, detail=True), ensure_ascii=False))
        return
    if not args.output or not args.roots:
        parser.error('--output and at least one root are required')
    if args.reference and not args.baseline_code:
        parser.error('--reference requires --baseline-code for invariant checks')
    suffixes = {'.hwp', '.hwpx'} if args.suffix == 'both' else {'.' + args.suffix}
    reference = None
    if args.reference:
        with open(args.reference, encoding='utf-8') as handle:
            reference = json.load(handle)['files']
    rows = {}
    changed = []
    failed = []
    heading_only = []
    headings = {}
    moves = 0
    markdown_changed = []
    json_changed = []
    for key, path in _paths(args.roots, suffixes):
        row = _read(path)
        rows[key] = row
        if reference is None or row == reference.get(key):
            continue
        changed.append(key)
        old = reference.get(key)
        if old and row.get('markdown_sha256') != old.get('markdown_sha256'):
            markdown_changed.append(key)
        if old and row.get('json_sha256') != old.get('json_sha256'):
            json_changed.append(key)
        if old is None or ('exception' in old) != ('exception' in row):
            failed.append([key, ['exception_or_missing']])
            continue
        if 'exception' in row:
            failed.append([key, ['exception_changed']])
            continue
        before = _baseline_detail(args.baseline_code, path)
        after = _read(path, detail=True)
        verdict = _compare_traces(before['trace'], after['trace'])
        if not verdict['valid']:
            failed.append([key, verdict['reasons']])
        moves += verdict['image_moves']
        if verdict['heading_changes']:
            headings[key] = verdict['heading_changes']
        if (verdict['heading_changes']
                and _only_heading_levels_changed(before['trace'], after['trace'])):
            heading_only.append(key)
    result = {'files': rows, 'summary': {
        'scanned': len(rows), 'exceptions': sum('exception' in row for row in rows.values()),
        'changed': changed, 'markdown_changed': markdown_changed,
        'json_changed': json_changed, 'invariants_failed': failed,
        'heading_only': heading_only, 'heading_changes': headings,
        'image_moves': moves}}
    with open(args.output, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=1)
    print(json.dumps({key: (len(value) if isinstance(value, (list, dict)) else value)
                      for key, value in result['summary'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
