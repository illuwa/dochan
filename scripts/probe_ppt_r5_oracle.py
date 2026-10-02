"""저장된 PowerPoint 실측과 소스 스냅숏을 오프라인으로 대조한다.

--corpus-root CORPUS --oracle JSON --summary JSON --base SOURCE
--before SOURCE --after SOURCE --output JSON으로 실행한다.
실측 원문이 없는 파일은 출력 동일성 또는 요약에 남은 명시 정답으로만 판정한다.
불일치 목록은 화면 표시 길이와 무관하게 모두 보존한다.
"""
import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

PROPS = ('size', 'bold', 'italic', 'underline', 'script')


def norm(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text or '')).strip()


def keyed(paragraphs):
    counts = Counter((p['slide'], norm(p['text'])) for p in paragraphs if norm(p['text']))
    return {(p['slide'], norm(p['text'])): p for p in paragraphs
            if norm(p['text']) and counts[(p['slide'], norm(p['text']))] == 1}


def values(paragraph):
    runs = [r for r in paragraph['runs'] if r[0].strip()]
    if not runs:
        return None
    r = runs[0]
    return dict(zip(PROPS, (r[1], bool(r[2]), bool(r[3]), bool(r[4]),
                           'sup' if r[5] else 'sub' if r[6] else '')))


def equal(prop, expected, actual):
    if prop == 'size':
        return actual is not None and abs(float(actual) - float(expected)) < 0.6
    return expected == actual


def compare(powerpoint, paragraphs):
    actual = keyed(paragraphs)
    result = {'matched': 0, 'stats': {p: [0, 0] for p in PROPS}, 'mismatches': []}
    for key, pp in keyed(powerpoint).items():
        if key not in actual:
            continue
        result['matched'] += 1
        got = values(actual[key])
        if got is None:
            continue
        expected = {p: {'true': True, 'false': False}.get(pp[k].strip().lower())
                    for p, k in (('bold', 'b'), ('italic', 'i'), ('underline', 'u'))}
        for prop, key_name in (('size', 'size'), ('script', 'off')):
            try:
                number = float(pp[key_name])
                expected[prop] = (number if prop == 'size' else
                                  'sup' if number > 0 else 'sub' if number < 0 else '')
            except ValueError:
                expected[prop] = None
        for prop in PROPS:
            if expected[prop] is None:
                continue
            ok = equal(prop, expected[prop], got[prop])
            result['stats'][prop][0] += int(ok)
            result['stats'][prop][1] += 1
            if not ok:
                result['mismatches'].append({'slide': key[0], 'text': key[1], 'prop': prop,
                                             'pp': expected[prop], 'dochan': got[prop]})
    return result


def regressions(before, after):
    previous = {(m['slide'], m['text'], m['prop']) for m in before['mismatches']}
    return [m for m in after['mismatches'] if (m['slide'], m['text'], m['prop']) not in previous]


def summary_delta(row, before, after):
    """요약의 잘린 문구가 유일하게 대응될 때만 명시 정답을 사용한다."""
    delta = {p: 0 for p in PROPS}
    unknown = []
    bmap, amap = keyed(before), keyed(after)
    if set(bmap) != set(amap):
        return delta, ['paragraph key sets differ']
    for key in bmap:
        b, a = values(bmap[key]), values(amap[key])
        if b == a:
            continue
        if b is None or a is None:
            unknown.append({'slide': key[0], 'text': key[1], 'reason': 'empty runs'})
            continue
        for prop in PROPS:
            if b[prop] == a[prop]:
                continue
            matches = [m for m in row['legacy_mismatches']
                       if m['slide'] == key[0] and m['prop'] == prop and key[1].startswith(m['text'])
                       and sum(k[0] == key[0] and k[1].startswith(m['text']) for k in bmap) == 1]
            if len(matches) != 1 or matches[0]['dochan'] != b[prop]:
                unknown.append({'slide': key[0], 'text': key[1], 'prop': prop})
                continue
            expected = matches[0]['pp']
            delta[prop] += int(equal(prop, expected, a[prop])) - int(equal(prop, expected, b[prop]))
    return delta, unknown


def extract(source, path):
    # nosemgrep: dangerous-subprocess-use-audit
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'extract',
                             str(Path(source).resolve()), str(path)],
                            capture_output=True, check=True, timeout=60)
    return json.loads(result.stdout)


def extract_main(source, path):
    sys.path.insert(0, source)
    import dochan
    from dochan.model.document import Paragraph
    from dochan.office_binary.ppt import PPTReader

    if not Path(dochan.__file__).resolve().is_relative_to(Path(source).resolve()):
        raise ValueError('source import mismatch')
    doc = PPTReader().read(path)
    paragraphs = []
    for index, section in enumerate(doc.sections, 1):
        for p in section.elements:
            if not isinstance(p, Paragraph):
                continue
            origin = getattr(p.provenance, 'path', '') or ''
            if origin.endswith(('#master', '#notes')):
                continue
            paragraphs.append({'slide': getattr(p.provenance, 'slide', None) or index,
                               'text': p.text,
                               'runs': [[r.text, r.font_size_pt, bool(r.bold), bool(r.italic),
                                         bool(r.underline), bool(r.superscript), bool(r.subscript)]
                                        for r in p.runs]})
    print(json.dumps({'paragraphs': paragraphs, 'errors': doc.errors}, ensure_ascii=False))


def raw_records(path):
    """마스터/Environment 및 슬라이드 CF의 원시 바이트와 스트림 위치를 덤프한다."""
    import olefile
    from dochan.office_binary.officeart import parse_records, walk_records
    from dochan.office_binary.ppt_render import sheet_shapes
    from dochan.office_binary.ppt_structure import resolve_presentation
    from dochan.office_binary.ppt_text import (
        _Cursor, _character_properties, _paragraph_properties, text_blocks,
    )
    from dochan.utils.bounded_io import read_ole_stream

    with olefile.OleFileIO(str(path)) as ole:
        stream = read_ole_stream(ole, 'PowerPoint Document')
        current = read_ole_stream(ole, 'Current User')
    errors = []
    pres = resolve_presentation(stream, current, errors)
    if pres is None:
        return {'errors': errors, 'records': []}
    output = []

    def raw(cursor, start, mask, **extra):
        begin = cursor.pos
        props = _character_properties(cursor, mask)
        return dict(extra, offset=start, mask=hex(mask),
                    fontStyle=hex(int.from_bytes(cursor.data[begin:begin + 2], 'little'))
                    if mask & 0xFFFF else None,
                    hex=bytes(cursor.data[start:cursor.pos]).hex(), values=props)

    sources = [('environment', list(walk_records(pres.document.children)))]
    sources += [('master:%s' % key, value.record.children) for key, value in pres.masters.items()]
    for source, records in sources:
        for atom in records:
            if atom.header.rec_type not in (4003, 4004):
                continue
            cursor = _Cursor(atom.data)
            row = {'source': source, 'record_type': atom.header.rec_type,
                   'text_type': atom.header.rec_instance, 'stream_offset': atom.offset, 'cf': []}
            try:
                count = cursor.read('<H') if atom.header.rec_type == 4003 else 1
                if count > 5:
                    raise ValueError('master level limit')
                for i in range(count):
                    level = i
                    if atom.header.rec_type == 4003:
                        if atom.header.rec_instance >= 5:
                            level = cursor.read('<H')
                        _paragraph_properties(cursor, cursor.read('<I'))
                    start = cursor.pos
                    mask = cursor.read('<I')
                    row['cf'].append(raw(cursor, start, mask, level=level))
            except ValueError as exc:
                row['error'] = str(exc)
            output.append(row)
    for index, slide in enumerate(pres.slides, 1):
        if slide.recovery_record is not None:
            slide = replace(slide, record=slide.recovery_record)
        record_sets = [slide.text_records, slide.record.children]
        pending = list(sheet_shapes(slide, errors))
        for _ in range(100000):
            if not pending:
                break
            shape = pending.pop()
            if shape.client_textbox:
                record_sets.append(parse_records(shape.client_textbox))
            pending.extend(shape.children)
        for records in record_sets:
            for block in text_blocks(records, errors):
                if not block.style:
                    continue
                row = {'source': 'slide:%d' % index, 'text_type': block.text_type,
                       'text': block.text, 'cf': [], 'payload_stream_offsets': []}
                # Embedded textboxes have relative Record.offset values. Search
                # the exact style payload and retain ambiguity instead of claiming
                # a relative position is an absolute stream offset.
                position = stream.find(block.style)
                while position >= 0 and len(row['payload_stream_offsets']) < 3:
                    row['payload_stream_offsets'].append(position)
                    position = stream.find(block.style, position + 1)
                cursor = _Cursor(block.style)
                units = len(block.text.encode('utf-16le')) // 2
                try:
                    end = 0
                    for _ in range(100000):
                        count, _level, mask = cursor.read('<IHI')
                        _paragraph_properties(cursor, mask)
                        if count == 0:
                            raise ValueError('zero paragraph count')
                        end += count
                        if end > units:
                            break
                    end = 0
                    for _ in range(100000):
                        if cursor.pos >= len(block.style) or end > units:
                            break
                        start = cursor.pos
                        count, mask = cursor.read('<II')
                        if count == 0:
                            raise ValueError('zero character count')
                        row['cf'].append(raw(cursor, start, mask, span=[end, end + count]))
                        end += count
                except ValueError as exc:
                    row['error'] = str(exc)
                output.append(row)
    return {'errors': errors, 'records': output}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'extract':
        extract_main(sys.argv[2], sys.argv[3])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('corpus-root', 'oracle', 'summary', 'base', 'before', 'after', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    saved = {f['file']: f['powerpoint'] for f in json.loads(args.oracle.read_text())['files']}
    summary = json.loads(args.summary.read_text())
    totals = {label: {p: [0, 0] for p in PROPS} for label in ('base', 'before', 'after')}
    rows = []
    for row in summary:
        path = args.corpus_root / row['file']
        b, a = extract(args.before, path), extract(args.after, path)
        entry = {'file': row['file'], 'text_equal': [p['text'] for p in b['paragraphs']]
                 == [p['text'] for p in a['paragraphs']], 'errors_equal': b['errors'] == a['errors']}
        if row['file'] in saved:
            pp = saved[row['file']]
            entry['base'] = compare(pp, extract(args.base, path)['paragraphs'])
            entry['before'] = compare(pp, b['paragraphs'])
            entry['after'] = compare(pp, a['paragraphs'])
            if entry['base']['stats'] != row['base'] or entry['before']['stats'] != row['legacy']:
                raise ValueError('saved summary differs from remeasurement: ' + row['file'])
            entry['regressions_before'] = regressions(entry['base'], entry['before'])
            entry['regressions_after'] = regressions(entry['base'], entry['after'])
            entry['raw'] = raw_records(path)
        else:
            delta, unknown = summary_delta(row, b['paragraphs'], a['paragraphs'])
            entry.update(base={'stats': row['base']}, before={'stats': row['legacy']},
                         after={'stats': {p: [row['legacy'][p][0] + delta[p], row['legacy'][p][1]]
                                          for p in PROPS}}, unknown=unknown,
                         evidence='unchanged first-run values or explicit summary mismatch', delta=delta)
        for label in totals:
            for prop in PROPS:
                for index in (0, 1):
                    totals[label][prop][index] += entry[label]['stats'][prop][index]
        rows.append(entry)
        print(row['file'], 'checked', flush=True)
    result = {'totals': totals, 'files': rows,
              'regressions_before': sum(len(r.get('regressions_before', [])) for r in rows),
              'regressions_after': sum(len(r.get('regressions_after', [])) for r in rows),
              'unknown': sum(len(r.get('unknown', [])) for r in rows)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
    return int(result['unknown'] != 0 or result['regressions_after'] != 0
               or not all(r['text_equal'] and r['errors_equal'] for r in rows)
               or any(totals['after'][p][0] < max(totals['base'][p][0], totals['before'][p][0])
                      for p in PROPS))


if __name__ == '__main__':
    raise SystemExit(main())
