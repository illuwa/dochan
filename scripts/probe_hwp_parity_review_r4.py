"""공개 짝의 코드 31과 HWPX 공백 표현을 원시 레코드/XML로 조사한다.

python -m scripts.probe_hwp_parity_review_r4 corpus/hwp-public --output spaces.json
파일명과 원시 속성, 개수만 기록하며 문서 본문은 저장하지 않는다.
"""

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from dochan import cfb
from dochan.control_char import get_advance_bytes
from dochan.hwp.header import FileHeader
from dochan.hwp.section import SectionParser
from dochan.utils.bounded_io import MAX_OLE_DOCUMENT_SIZE, read_ole_stream, validate_file_size
from scripts.probe_hwp_features import _records, _xml_part, HH, HP
from scripts.probe_hwp_parity_sweep import discover_pairs


def fixed_space_positions(data):
    """확장 컨트롤 payload를 문자로 세지 않고 WCHAR 위치를 읽는다."""
    positions = []
    offset = 0
    while offset + 1 < len(data):
        code = struct.unpack_from('<H', data, offset)[0]
        if code == 13:
            break
        if code == 31:
            positions.append(offset // 2)
        offset += 2 if code >= 32 else get_advance_bytes(code)
    return positions


def _hwp_contexts(path):
    validate_file_size(path, MAX_OLE_DOCUMENT_SIZE)
    contexts = Counter()
    with cfb.OleFileIO(path) as ole:
        header = FileHeader.parse(read_ole_stream(ole, 'FileHeader', max_bytes=256))
        if header.is_encrypted or header.is_distribution:
            raise ValueError('protected')
        info = _records(ole, 'DocInfo', header.is_compressed)
        para_shapes = [record.data for record in info if record.tag_id == 25]
        char_shapes = [record.data for record in info if record.tag_id == 21]
        for stream in ole.listdir():
            if len(stream) != 2 or stream[0] != 'BodyText':
                continue
            tree = SectionParser()._build_tree(_records(ole, stream, header.is_compressed))
            pending = [(node, False) for node in reversed(tree)]
            while pending:
                node, in_table = pending.pop()
                record = node['record']
                in_table = in_table or (record.tag_id == 71 and record.data[:4] == b' lbt')
                pending.extend((child, in_table) for child in reversed(node['children']))
                if record.tag_id != 66:
                    continue
                text = next((c['record'].data for c in node['children']
                             if c['record'].tag_id == 67), b'')
                positions = fixed_space_positions(text)
                if not positions:
                    continue
                sid = struct.unpack_from('<H', record.data, 8)[0] if len(record.data) >= 10 else -1
                props = para_shapes[sid] if 0 <= sid < len(para_shapes) else b''
                align = (struct.unpack_from('<I', props)[0] >> 2) & 7 if len(props) >= 4 else -1
                raw_shapes = next((c['record'].data for c in node['children']
                                   if c['record'].tag_id == 68), b'')
                pairs = sorted(struct.iter_unpack('<II', raw_shapes[:len(raw_shapes) // 8 * 8]))
                starts = [p for p, _sid in pairs]
                for position in positions:
                    index = bisect_right(starts, position) - 1
                    cid = pairs[index][1] if index >= 0 else -1
                    shape = char_shapes[cid] if 0 <= cid < len(char_shapes) else b''
                    height = struct.unpack_from('<i', shape, 42)[0] if len(shape) >= 46 else -1
                    flags = struct.unpack_from('<I', shape, 46)[0] if len(shape) >= 50 else 0
                    context = (in_table, align, height, bool(flags & 2))
                    contexts[context] += 1
    return [{'table': key[0], 'align': key[1], 'height': key[2], 'bold': key[3], 'count': count}
            for key, count in sorted(contexts.items())]


def _xml_contexts(archive):
    header = _xml_part(archive, 'Contents/header.xml')
    paragraphs = {p.get('id'): p for p in header.iter(HH + 'paraPr')}
    characters = {p.get('id'): p for p in header.iter(HH + 'charPr')}
    contexts = Counter()
    for name in archive.namelist():
        if not name.startswith('Contents/section') or not name.endswith('.xml'):
            continue
        root = _xml_part(archive, name)
        pending = [(root, False, '', '')]
        while pending:
            element, in_table, pid, cid = pending.pop()
            if not isinstance(element.tag, str):
                continue
            in_table = in_table or element.tag == HP + 'tbl'
            if element.tag == HP + 'p':
                pid = element.get('paraPrIDRef', '')
            if element.tag == HP + 'run':
                cid = element.get('charPrIDRef', '')
            para = paragraphs.get(pid)
            align = para.find(HH + 'align') if para is not None else None
            char = characters.get(cid)
            context = (in_table, align.get('horizontal', '') if align is not None else '',
                       char.get('height', '') if char is not None else '',
                       char.find(HH + 'bold') is not None if char is not None else False)
            if element.tag == HP + 'fwSpace':
                contexts[('element',) + context] += 1
            # Tail belongs to the parent text context, which is unchanged for hp:t children.
            for value in (element.text, element.tail):
                if value:
                    contexts[('literal',) + context] += value.count('\u2007')
            pending.extend((child, in_table, pid, cid) for child in reversed(list(element)))
    return [{'representation': key[0], 'table': key[1], 'align': key[2],
             'height': key[3], 'bold': key[4], 'count': count}
            for key, count in sorted(contexts.items()) if count]


def measure(corpus):
    rows = {}
    counts = Counter()
    for stem, hwpx, hwp in discover_pairs(corpus):
        if not zipfile.is_zipfile(hwpx):
            counts['not_zip'] += 1
            continue
        try:
            with zipfile.ZipFile(hwpx) as archive:
                if len(archive.filelist) > 10000:
                    raise ValueError('ZIP entry limit')
                xml = _xml_contexts(archive)
            raw = _hwp_contexts(hwp)
        except Exception as exc:
            counts['unreadable'] += 1
            rows[stem] = {'error_type': type(exc).__name__}
            continue
        hwp_count = sum(row['count'] for row in raw)
        literal = sum(row['count'] for row in xml if row['representation'] == 'literal')
        element = sum(row['count'] for row in xml if row['representation'] == 'element')
        if not (hwp_count or literal or element):
            continue
        kind = 'literal' if literal else 'element' if element else 'hwp_only'
        counts[kind + '_pairs'] += 1
        counts[kind + '_hwp_codes'] += hwp_count
        counts[kind + '_literal'] += literal
        counts[kind + '_elements'] += element
        rows[stem] = {'hwp_code31': hwp_count, 'hwpx_literal': literal,
                      'hwpx_element': element, 'hwp_contexts': raw, 'hwpx_contexts': xml}
    return {'summary': dict(counts), 'pairs': rows}


def conservation_fingerprints(corpus, changes):
    """변경된 공개 파일의 비공백 글자·개체 수 보존 지문만 기록한다."""
    from dochan import Dochan

    result = {}
    root = Path(corpus).resolve()
    for row in json.loads(Path(changes).read_text(encoding='utf-8'))['changes']:
        filename = row['file']
        path = (root / filename).resolve()
        if root not in path.parents:
            raise ValueError('changed file is outside the corpus')
        reader = Dochan(path)
        counts = Counter(char for char in reader.to_plain_text() if not char.isspace())
        encoded = json.dumps(sorted(counts.items()), ensure_ascii=False).encode('utf-8')
        result[filename] = {
            'nonspace_characters_sha256': hashlib.sha256(encoded).hexdigest(),
            'nonspace_characters': sum(counts.values()),
            'element_counts': {kind: len(reader.doc.find_all(kind)) for kind in
                               ('table', 'image', 'equation', 'footnote', 'endnote',
                                'header', 'footer', 'comment')},
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--conservation-changes', type=Path,
                        help='전체 해시 비교의 변경 목록을 읽어 글자·개체 보존 지문을 만든다.')
    args = parser.parse_args()
    result = (conservation_fingerprints(args.corpus, args.conservation_changes)
              if args.conservation_changes else measure(args.corpus))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(result.get('summary', {'fingerprinted': len(result)}), ensure_ascii=False))


if __name__ == '__main__':
    main()
