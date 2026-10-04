"""공개 XLS NOTE·Obj·TxO의 독립 정답을 셀 좌표·순서까지 대조한다.

python -m scripts.probe_xls_comment_cells CORPUS [CORPUS ...] --output JSON
원시 BIFF 해독에는 제품 코드를 쓰지 않는다. 동명 XLSX의 XML 메모도 비교한다.
"""
import struct

from scripts.comment_probe_common import (
    annotation, biff_records, compare, ole_streams, product,
    relationship_targets, run_cli, xml, zip_package, zip_read,
)

R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def cell_ref(row, col):
    letters = ''
    col += 1
    while col:
        col, digit = divmod(col - 1, 26)
        letters = chr(65 + digit) + letters
    return letters + str(row + 1)


def unicode_string(data, start, length, flags):
    width = 2 if flags & 1 else 1
    end = start + length * width
    if end > len(data):
        raise ValueError('truncated oracle BIFF string')
    return data[start:end].decode('utf-16le' if width == 2 else 'latin1')


def xls_oracle_stream(data):
    records, diagnostics = [], []
    try:
        for rec in biff_records(data):
            records.append(rec)
    except ValueError as exc:
        diagnostics.append(str(exc))
    bounds = []
    global_notes = sum(kind == 0x001C for _, kind, _ in records)
    for offset, kind, payload in records:
        if kind == 0x002F:
            return {'comments': [], 'raw_count': global_notes, 'excluded': 'encrypted FILEPASS'}
        if kind == 0x0085 and len(payload) >= 8:
            start = struct.unpack_from('<I', payload)[0]
            name = unicode_string(payload, 8, payload[6], payload[7])
            bounds.append((start, name, payload[5]))
    comments = []
    for start, name, sheet_kind in bounds:
        if sheet_kind != 0:  # Charts/macros have no worksheet cell NOTE contract.
            continue
        subset = []
        level = 0
        for rec in biff_records(data, start):
            subset.append(rec)
            if rec[1] in (0x0809, 0x0409, 0x0209, 0x0009):
                level += 1
            elif rec[1] == 0x000A:
                level -= 1
                if level == 0:
                    break
        pending, bodies, notes = None, {}, []
        cursor, depth = 0, 0
        while cursor < len(subset):
            _, kind, payload = subset[cursor]
            cursor += 1
            if kind in (0x0809, 0x0409, 0x0209, 0x0009):
                depth += 1
            elif kind == 0x000A:
                depth -= 1
                if depth == 0:
                    break
            if depth != 1:
                continue
            if kind == 0x005D:
                pending = None
                if len(payload) >= 10:
                    marker, length, typ, object_id = struct.unpack_from('<4H', payload)
                    if marker == 0x0015 and length == 18 and typ == 0x0019:
                        pending = object_id
            elif kind == 0x01B6 and pending is not None:
                if len(payload) < 14:
                    raise ValueError('truncated oracle TxO')
                remaining = struct.unpack_from('<H', payload, 10)[0]
                wide_parts = bytearray()
                while remaining:
                    if cursor >= len(subset) or subset[cursor][1] != 0x003C:
                        raise ValueError('truncated oracle TxO characters')
                    chunk = subset[cursor][2]
                    cursor += 1
                    if not chunk or chunk[0] not in (0, 1):
                        raise ValueError('invalid oracle Continue encoding')
                    width = 2 if chunk[0] else 1
                    count = min(remaining, (len(chunk) - 1) // width)
                    if count == 0:
                        raise ValueError('empty oracle Continue')
                    raw = chunk[1:1 + count * width]
                    wide_parts.extend(raw if width == 2 else raw.decode('latin1').encode('utf-16le'))
                    remaining -= count
                text = wide_parts.decode('utf-16le')
                bodies[pending] = text.replace('\r\n', '\n').replace('\r', '\n').strip()
                pending = None
            elif kind == 0x001C:
                if len(payload) < 11:
                    return {'comments': [], 'raw_count': global_notes, 'excluded': 'truncated NOTE'}
                row, col, flags, oid, length = struct.unpack_from('<5H', payload)
                author = unicode_string(payload, 11, length, payload[10]).strip()
                notes.append((row, col, oid, author, flags))
        for order, (row, col, oid, author, flags) in enumerate(notes, 1):
            body = bodies.get(oid, '')
            comments.append({'sheet': name, 'cell': cell_ref(row, col), 'row': row, 'col': col,
                             'record_order': order, 'object_id': oid, 'hidden': not bool(flags & 2),
                             'author': author, 'body': body, 'annotation': annotation(author, body)})
    # A worksheet table is emitted in row/column order, rather than NOTE record order.
    ordered = [c for _, name, _ in bounds for c in sorted(
        (c for c in comments if c['sheet'] == name), key=lambda c: (c['row'], c['col']))]
    return {'comments': ordered, 'raw_count': global_notes, 'oracle_diagnostics': diagnostics}


def xls_oracle(path):
    streams = ole_streams(path, ['Workbook', 'Book'])
    data = streams.get('Workbook', streams.get('Book', b''))
    # Keep the independently observed NOTE count even when a later malformed
    # drawing or BoundSheet prevents interpretation of its cells.
    count = 0
    try:
        for _, kind, _ in biff_records(data):
            count += kind == 0x001C
    except ValueError:
        pass
    try:
        return xls_oracle_stream(data)
    except Exception as exc:
        return {'oracle_error': type(exc).__name__ + ': ' + str(exc), 'raw_count': count}


def xlsx_oracle(path):
    with zip_package(path) as package:
        rels = relationship_targets(package, 'xl/workbook.xml')
        book = xml(zip_read(package, 'xl/workbook.xml'))
        comments = []
        for sheet in book.items('sheets')[0].items('sheet'):
            target = rels[sheet.attrs[R + 'id']][1]
            for typ, part in relationship_targets(package, target).values():
                if not typ.endswith('/comments'):
                    continue
                root = xml(zip_read(package, part))
                authors = [n.text for n in root.items('authors')[0].items('author')]
                for cm in root.items('commentList')[0].items('comment'):
                    author = authors[int(cm.attrs['authorId'])]
                    texts = cm.items('text')
                    body = ''
                    for n in texts[0].children if texts else []:
                        if n.tag.rsplit('}', 1)[-1] == 't':
                            body += n.text
                        else:
                            body += ''.join(t.text for t in n.items('t'))
                    body = body.replace('\r\n', '\n').replace('\r', '\n').strip()
                    comments.append({'sheet': sheet.attrs['name'], 'cell': cm.attrs['ref'],
                                     'annotation': annotation(author, body)})
        return comments


def inspect(path):
    """NOTE 작성자·TxO 본문·셀 위치·행열 출력 순서와 OOXML 공통 메모를 대조한다."""
    try:
        raw = xls_oracle(path)
    except Exception as exc:
        raw = {'oracle_error': type(exc).__name__ + ': ' + str(exc)}
    actual = product(path)
    cells = actual.pop('cells')
    if 'comments' in raw and not raw.get('excluded'):
        raw['comparison'] = compare(raw['comments'], cells, ('sheet', 'cell', 'annotation'))
    else:
        raw['unverified_actual_count'] = len(cells)
    actual.pop('paragraphs')
    pair = path.with_suffix('.xlsx')
    if raw.get('raw_count') and pair.is_file() and not raw.get('excluded'):
        reference = xlsx_oracle(pair)
        raw['pair'] = {'file': pair.name, 'xlsx_count': len(reference), 'common': []}
        for c in reference:
            same_cell = next((n for n in raw['comments'] if n['cell'] == c['cell']
                              and n['sheet'] == c['sheet']), None)
            if same_cell:
                raw['pair']['common'].append({'sheet': c['sheet'], 'cell': c['cell'],
                                              'exact': c['annotation'] == same_cell['annotation']})
        counterpart = product(pair)['cells']
        raw['pair']['xlsx_output_count'] = len(counterpart)
        raw['pair']['output_common'] = []
        for c in counterpart:
            same_cell = next((n for n in raw['comments'] if n['cell'] == c['cell']
                              and n['sheet'] == c['sheet']), None)
            if same_cell:
                raw['pair']['output_common'].append({'sheet': c['sheet'], 'cell': c['cell'],
                                                     'exact': c['annotation'] == same_cell['annotation']})
    return {**raw, **actual}


if __name__ == '__main__':
    run_cli(inspect, {'.xls'})
