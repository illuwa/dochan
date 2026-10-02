"""공개 DOC의 factoid CP 범위가 같은 출처 문단에 보존되는지 검사한다.

코퍼스 경로를 인자로 받으며 원본을 복사하지 않는다. Factoid는 텍스트에
부가된 메타데이터이므로 기존 DOC 렌더러가 보존하는 표시 텍스트를 검증한다.
"""
import argparse
import bisect
import json
from pathlib import Path
import re
import struct

from dochan.office_binary.doc import DOCReader
from scripts.check_doc_word_preservation import read_binary


def factoid_ranges(binary):
    """Read observed MS-DOC SttbfBkmkFactoid/FBKFD/FBKLD layouts.

    FibRgFcLcb2002 slots 114, 115 and 117 hold the string table, start
    PLC and end PLC. Each FBKFD is six bytes; each FBKLD is four bytes.
    """
    names, starts, ends = (binary.blob(i) for i in (114, 115, 117))
    if not any((names, starts, ends)):
        return []
    if len(names) < 6 or len(starts) < 4 or len(ends) < 4:
        raise ValueError('truncated factoid tables')
    marker, count, extra = struct.unpack_from('<HHH', names)
    if marker != 0xffff or extra or count > 100000:
        raise ValueError('invalid factoid string table header')
    if (len(starts) - 4) % 10 or (len(ends) - 4) % 8:
        raise ValueError('invalid factoid PLC length')
    if (len(starts) - 4) // 10 != count or (len(ends) - 4) // 8 != count:
        raise ValueError('factoid table counts differ')
    pos = 6
    for _ in range(count):
        if pos + 14 > len(names) or struct.unpack_from('<H', names, pos)[0] != 6:
            raise ValueError('invalid FactoidInfo record')
        pos += 14
    if pos != len(names):
        raise ValueError('trailing FactoidInfo bytes')
    result = []
    for index in range(count):
        start = struct.unpack_from('<I', starts, index * 4)[0]
        end_index = struct.unpack_from('<I', starts, (count + 1) * 4 + index * 6)[0]
        if end_index >= count:
            raise ValueError('factoid end index outside PLC')
        end = struct.unpack_from('<I', ends, end_index * 4)[0]
        if not 0 <= start <= end <= len(binary.text):
            raise ValueError('factoid CP range outside text')
        result.append((start, end))
    return result


def probe(path):
    try:
        binary, _ = read_binary(path)
    except Exception as exc:
        return {'file': path.name, 'native': False, 'ranges': [],
                'scan_skip': str(exc)}
    if binary is None:
        return {'file': path.name, 'native': False, 'ranges': []}
    ranges = factoid_ranges(binary)
    if not ranges:
        return {'file': path.name, 'native': True, 'ranges': []}
    doc = DOCReader().read(str(path))
    paragraphs = {}
    for paragraph in doc.find_all('paragraph'):
        source = getattr(paragraph.provenance, 'path', '')
        if source.startswith('WordDocument#cp'):
            paragraphs.setdefault(int(source[15:]), []).append(paragraph.text)
    records = sorted((r for a, b in binary.stories.values()
                      for r in binary.paragraphs(a, b)), key=lambda r: r.start)
    positions = [r.start for r in records]
    rows = []
    for start, end in ranges:
        index = bisect.bisect_right(positions, start) - 1
        record = records[index] if index >= 0 else None
        raw = binary.text[start:end]
        source_text = '\n'.join(paragraphs.get(record.start, [])) if record else ''
        # A crossing or empty range is explicitly unverified, never counted as
        # evidence from an identical phrase in an unrelated paragraph.
        verifiable = bool(raw) and record is not None and end <= record.end
        normalized = re.sub(r'\s+', ' ', raw)
        matched = verifiable and normalized in re.sub(r'\s+', ' ', source_text)
        rows.append({'cp': [start, end], 'text': raw, 'verified': bool(matched),
                     'empty': start == end, 'paragraph_cp': record.start if record else None})
    return {'file': path.name, 'native': True, 'ranges': rows, 'errors': doc.errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi', type=Path, required=True)
    parser.add_argument('--lo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [p for p in args.poi.iterdir() if p.suffix.lower() == '.doc']
    paths += list((args.lo / 'sw/qa/extras').glob('*/data/*.doc'))
    rows = []
    for path in sorted(paths):
        try:
            rows.append(probe(path))
        except Exception as exc:
            rows.append({'file': path.name, 'scan_error': str(exc), 'ranges': []})
    summary = {'documents': len(rows),
               'factoid_documents': sum(bool(r['ranges']) for r in rows),
               'ranges': sum(len(r['ranges']) for r in rows),
               'verified': sum(v['verified'] for r in rows for v in r['ranges']),
               'empty_ranges': sum(v['empty'] for r in rows for v in r['ranges']),
               'scan_skips': sum('scan_skip' in r for r in rows),
               'scan_errors': sum('scan_error' in r for r in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'summary': summary, 'documents': rows},
                                     ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    return int(summary['ranges'] - summary['empty_ranges'] != summary['verified']
               or summary['scan_errors'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
