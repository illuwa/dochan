"""PPT·PPTX 공개 메모를 독립 레코드/XML 정답과 슬라이드 순서로 대조한다.

사용법: python -m scripts.probe_presentation_comments CORPUS [CORPUS ...]
        --output .codex-work/presentation-comments.json
정답: [MS-PPT] CurrentUserAtom/UserEditAtom/PersistDirectoryAtom/
SlideListWithText/Comment10/Comment10Atom/CString, ECMA-376 p:cmLst.
화면 x/y·이니셜·시각은 원시 증거로 기록하되 제품 출력 계약은 슬라이드와 문구이다.
"""
from pathlib import Path
import struct

from scripts.comment_probe_common import (
    MAX_RECORDS, annotation, compare, ole_streams, product,
    relationship_targets, run_cli, xml, zip_package, zip_read,
)

P = 'http://schemas.openxmlformats.org/presentationml/2006/main}'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def pptx_oracle(path):
    with zip_package(path) as package:
        parts = [n for n in package.namelist() if n.startswith('ppt/comments/') and n.endswith('.xml')]
        modern = [n for n in package.namelist() if 'modernComment' in n]
        if not parts:
            return {'comments': [], 'raw_count': 0, 'comment_parts': [], 'modern_parts': modern}
        authors = {}
        if 'ppt/commentAuthors.xml' in package.namelist():
            authors = {a.attrs['id']: a.attrs.get('name', '')
                       for a in xml(zip_read(package, 'ppt/commentAuthors.xml')).items('cmAuthor')}
        rels = relationship_targets(package, 'ppt/presentation.xml')
        presentation = xml(zip_read(package, 'ppt/presentation.xml'))
        listing = presentation.items('sldIdLst')
        comments, linked = [], set()
        for index, slide in enumerate(listing[0].items('sldId') if listing else [], 1):
            slide_part = rels[slide.attrs[R + 'id']][1]
            for relation, target in relationship_targets(package, slide_part).values():
                if not relation.endswith('/comments'):
                    continue
                linked.add(target)
                root = xml(zip_read(package, target))
                if root.tag != P + 'cmLst':
                    modern.append(target)
                    continue
                for order, cm in enumerate(root.items('cm'), 1):
                    texts, pos = cm.items('text'), cm.items('pos')
                    body = texts[0].text.strip() if texts else ''
                    author = authors.get(cm.attrs.get('authorId'), '')
                    comments.append({'slide': index, 'order': order, 'part': target,
                                     'author_id': cm.attrs.get('authorId'), 'author': author,
                                     'body': body, 'index': cm.attrs.get('idx'),
                                     'position': pos[0].attrs if pos else {},
                                     'annotation': annotation(author, body) if body else ''})
        return {'comments': comments, 'raw_count': sum(len(xml(zip_read(package, n)).items('cm')) for n in parts),
                'comment_parts': parts, 'unlinked_parts': sorted(set(parts) - linked),
                'modern_parts': sorted(set(modern))}


def ppt_records(data, start=0, end=None, depth=0, budget=None):
    """[MS-PPT] 8바이트 헤더; ProgBinaryTagData는 5003 payload도 레코드열이다."""
    end = len(data) if end is None else end
    budget = [MAX_RECORDS] if budget is None else budget
    if depth > 64:
        raise ValueError('oracle PPT nesting limit')
    nodes = []
    while start + 8 <= end:
        options, kind, length = struct.unpack_from('<HHI', data, start)
        stop = start + 8 + length
        if stop > end:
            raise ValueError('truncated oracle PPT record')
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError('oracle PPT record limit')
        payload = memoryview(data)[start + 8:stop]
        # [MS-PPT] RoundTripCustomTableStyles12 (1064) has recVer=0xF
        # but its payload is an opaque ZIP package, not nested PPT records.
        children = ppt_records(data, start + 8, stop, depth + 1, budget) if options & 15 == 15 and kind != 1064 else []
        nodes.append({'kind': kind, 'instance': options >> 4, 'data': payload,
                      'children': children, 'offset': start})
        start = stop
    return nodes


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node['children'])


def comment10(nodes, slide):
    result = []
    for tag in walk(nodes):
        if tag['kind'] != 5002:
            continue
        name = [bytes(n['data']).decode('utf-16le').rstrip('\0')
                for n in tag['children'] if n['kind'] == 4026]
        if '___PPT10' not in name:
            continue
        for binary in tag['children']:
            if binary['kind'] != 5003:
                continue
            for cm in walk(ppt_records(binary['data'])):
                if cm['kind'] != 12000:
                    continue
                strings = {n['instance']: bytes(n['data']).decode('utf-16le').rstrip('\0')
                           for n in cm['children'] if n['kind'] == 4026}
                atom = next((n for n in cm['children'] if n['kind'] == 12001), None)
                author, body = strings.get(0, '').strip(), strings.get(1, '').strip()
                body = body.replace('\r\n', '\n').replace('\r', '\n')
                row = {'slide': slide, 'order': len(result) + 1, 'author': author,
                       'body': body, 'initials': strings.get(2, ''),
                       'annotation': annotation(author, body) if body else ''}
                if atom is not None and len(atom['data']) >= 28:
                    index, *values = struct.unpack_from('<I8Hii', atom['data'])
                    row.update(index=index, system_time=values[:8], position=values[8:])
                result.append(row)
    return result


def ppt_oracle_stream(data, current):
    physical = ppt_records(data)
    historical = comment10(physical, None)
    if not historical:
        return {'comments': [], 'raw_count': 0, 'historical_count': 0}
    if len(current) < 20:
        raise ValueError('oracle PPT CurrentUserAtom missing')
    edit = struct.unpack_from('<I', current, 16)[0]
    offsets, visited, doc_id = {}, set(), None
    by_offset = {n['offset']: n for n in physical}
    for _ in range(1024):
        if edit in visited:
            raise ValueError('oracle PPT edit cycle')
        visited.add(edit)
        user = by_offset[edit]
        previous, directory, pid = struct.unpack_from('<III', user['data'], 8)
        if doc_id is None:
            doc_id = pid
        payload = by_offset[directory]['data']
        cursor = 0
        while cursor + 4 <= len(payload):
            entry = struct.unpack_from('<I', payload, cursor)[0]
            first, count = entry & 0xFFFFF, entry >> 20
            cursor += 4
            if not count or cursor + count * 4 > len(payload):
                raise ValueError('oracle PPT persist directory invalid')
            for i in range(count):
                offsets.setdefault(first + i, struct.unpack_from('<I', payload, cursor + i * 4)[0])
            cursor += count * 4
        if not previous:
            break
        edit = previous
    else:
        raise ValueError('oracle PPT edit limit')
    document = by_offset[offsets[doc_id]]
    slides = []
    for listing in document['children']:
        if listing['kind'] != 4080 or listing['instance'] != 0:
            continue
        for atom in listing['children']:
            if atom['kind'] == 1011:
                pid = struct.unpack_from('<I', atom['data'])[0]
                slides.append(by_offset[offsets[pid]])
    comments = [c for index, slide in enumerate(slides, 1)
                for c in comment10([slide], index)]
    return {'comments': comments, 'raw_count': len(comments),
            'historical_count': len(historical), 'slide_count': len(slides)}


def ppt_oracle(path):
    streams = ole_streams(path, ['PowerPoint Document', 'Current User'])
    data = streams['PowerPoint Document']
    # Inventory complete Comment10 records even when an unrelated container
    # is corrupt. These candidates include historical edits, not live output.
    candidates, offset = [], 0
    for _ in range(MAX_RECORDS):
        hit = data.find(b'\xe0\x2e', offset)
        if hit < 0:
            break
        offset = hit + 2
        start = hit - 2
        if start < 0 or start + 8 > len(data):
            continue
        options, _kind, size = struct.unpack_from('<HHI', data, start)
        stop = start + 8 + size
        if options & 15 != 15 or stop > len(data):
            continue
        try:
            nodes = ppt_records(data[start:stop])
        except ValueError:
            continue
        children = nodes[0]['children']
        if any(n['kind'] == 4026 and n['instance'] == 1 for n in children):
            candidates.append(start)
    else:
        raise ValueError('oracle PPT candidate scan limit')
    try:
        result = ppt_oracle_stream(data, streams.get('Current User', b''))
    except Exception as exc:
        result = {'oracle_error': type(exc).__name__ + ': ' + str(exc)}
    return {**result, 'physical_comment_candidates': candidates}


def inspect(path):
    """공개 메모의 원시 순서·슬라이드·작성자·본문을 제품과 비교한다."""
    try:
        raw = pptx_oracle(path) if Path(path).suffix.lower() == '.pptx' else ppt_oracle(path)
    except Exception as exc:
        raw = {'oracle_error': type(exc).__name__ + ': ' + str(exc)}
    actual = product(path)
    paragraphs = actual.pop('paragraphs')
    if 'comments' in raw:
        raw['comparison'] = compare(raw['comments'], paragraphs, ('slide', 'annotation'))
    else:
        raw['unverified_actual_count'] = len(paragraphs)
    actual.pop('cells')
    return {**raw, **actual}


if __name__ == '__main__':
    run_cli(inspect, {'.ppt', '.pptx'})
