"""공개 코퍼스의 FIB 암호 비트와 DOC 캡션 실물을 읽기 전용으로 조사한다.

사용법: python -m scripts.probe_doc_legacy_evidence ROOT [ROOT ...] --output FILE
확장자와 무관하게 OLE/원시 Word FIB를 찾으며 외부 구현 소스는 해석하지 않는다.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import signal
import struct

import olefile

from dochan.office_binary.doc import DOCReader
from dochan.office_binary.doc_binary import DocBinary
from dochan.office_binary.doc_captions import DocCaptions
from dochan.office_binary.doc_stories import Stories
from dochan.model.document import Document
from dochan.ooxml.docx import DOCXReader
from dochan.utils.bounded_io import MAX_OLE_STREAM_SIZE
from scripts.compare_office_pairs import _walk


def _timeout(signum, frame):
    raise TimeoutError('document probe timed out')


def _fib(data):
    if len(data) < 12:
        return None
    ident, version = struct.unpack_from('<HH', data)
    if ident not in (0xa5db, 0xa5dc, 0xa5ec):
        return None
    flags = struct.unpack_from('<H', data, 10)[0]
    return {'ident': hex(ident), 'nFib': version, 'flags': hex(flags),
            'encrypted': bool(flags & 0x100),
            'obfuscated_bit': bool(flags & 0x8000),
            'modern_fib': version >= 0xc1}


def _raw_captions(path):
    with olefile.OleFileIO(str(path)) as ole:
        word = _stream(ole, 'WordDocument')
        table_name = '1Table' if struct.unpack_from('<H', word, 10)[0] & 0x200 else '0Table'
        if not ole.exists(table_name):
            return []
        binary = DocBinary(word, _stream(ole, table_name),
                           _stream(ole, 'Data') if ole.exists('Data') else b'')
    if not binary.valid:
        return []
    doc = Document(source_format='doc')
    captions = DocCaptions(binary, Stories(binary, doc), doc.errors)
    records = list(binary.paragraphs(*binary.stories['main']))
    found = []
    for index, record in enumerate(records):
        kind = captions.kind(record)
        if not kind:
            continue
        neighbors = []
        for offset in (-1, 0, 1):
            if 0 <= index + offset < len(records):
                other = records[index + offset]
                neighbors.append({'offset': offset, 'cp': other.start,
                                  'text': other.text[:500], 'props': {
                                      key: value for key, value in other.props.items()
                                      if key in ('istd', 'in_table', 'itap')}})
        found.append({'kind': kind, 'neighbors': neighbors})
    return found


def _stream(ole, name):
    if ole.get_size(name) > MAX_OLE_STREAM_SIZE:
        raise ValueError('OLE stream exceeds probe byte limit')
    return ole.openstream(name).read()


def _caption_snapshot(doc):
    return [{'type': type(node).__name__, 'side': node.caption_side,
             'text': node.caption_text,
             'source': [getattr(p.provenance, 'path', '') for p in node.caption]}
            for node in _walk(doc) if getattr(node, 'caption', None)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--captions', action='store_true')
    args = parser.parse_args()
    result = {'counts': {}, 'fibs': [], 'captions': [], 'raw_captions': [],
              'same_stem_docx': [], 'errors': []}
    count = Counter()
    documents = defaultdict(list)
    docxs = defaultdict(list)
    signal.signal(signal.SIGALRM, _timeout)
    for root in args.roots:
        for path in sorted(root.rglob('*')):
            if not path.is_file() or '.git' in path.parts:
                continue
            count[str(root.name) + '_files'] += 1
            count['files'] += 1
            if path.suffix.lower() == '.doc':
                documents[path.stem].append(str(path))
            elif path.suffix.lower() == '.docx':
                docxs[path.stem].append(str(path))
            phase = 'fib'
            try:
                with path.open('rb') as stream:
                    head = stream.read(32)
                entries = []
                signal.alarm(10)
                if head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
                    count['ole_files'] += 1
                    with olefile.OleFileIO(str(path)) as ole:
                        for name in ole.listdir():
                            if name[-1] == 'WordDocument':
                                info = _fib(_stream(ole, name)[:32])
                                if info:
                                    entries.append((name, info))
                else:
                    info = _fib(head)
                    if info:
                        entries.append(([], info))
                for name, info in entries:
                    count['fib_streams'] += 1
                    count['modern_fib' if info['modern_fib'] else 'old_fib'] += 1
                    count['encrypted'] += int(info['encrypted'])
                    count['obfuscated_bit'] += int(info['obfuscated_bit'])
                    count['modern_xor_candidates'] += int(
                        info['modern_fib'] and info['encrypted'] and info['obfuscated_bit'])
                    count['old_encrypted_candidates'] += int(
                        not info['modern_fib'] and info['encrypted'])
                    item = dict(info, path=str(path), stream='/'.join(name))
                    result['fibs'].append(item)
                if args.captions and any(name == ['WordDocument'] and not info['encrypted']
                                         for name, info in entries):
                    count['caption_documents'] += 1
                    phase = 'captions'
                    doc = DOCReader().read(str(path))
                    captions = _caption_snapshot(doc)
                    if captions:
                        result['captions'].append({'path': str(path), 'captions': captions})
                    raw = _raw_captions(path)
                    if raw:
                        result['raw_captions'].append({'path': str(path), 'captions': raw})
            except Exception as exc:
                result['errors'].append({'path': str(path), 'phase': phase, 'error': str(exc)})
            finally:
                signal.alarm(0)
    if args.captions:
        stems = documents.keys() & docxs.keys()
        count['same_stems'] = len(stems)
        for stem in sorted(stems):
            for path in docxs[stem]:
                signal.alarm(10)
                try:
                    doc = DOCXReader().read(path)
                    result['same_stem_docx'].append({
                        'docx': path, 'docs': documents[stem],
                        'captions': _caption_snapshot(doc), 'errors': doc.errors})
                except Exception as exc:
                    result['errors'].append({'path': path, 'phase': 'docx', 'error': str(exc)})
                finally:
                    signal.alarm(0)
    result['counts'] = dict(count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'counts': result['counts'], 'errors': len(result['errors']),
                      'caption_documents_found': len(result['captions'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
