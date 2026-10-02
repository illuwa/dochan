"""공개 HWP 변경 추적의 final 투영과 저장된 BodyText를 재검증한다.

실행: /usr/bin/python3 -m scripts.probe_hwp_polish_revisions /path/to/hwp-public
코퍼스는 읽기만 하며 공개 파일명, 길이, 진단과 해시만 출력한다.
상한 확장 관찰은 원인 분석용이며 기본 상한 검증의 통과 수에 넣지 않는다.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import olefile

from dochan import Dochan
from dochan.hwp.doc_info import DocInfoParser
from dochan.hwp.header import FileHeader
from dochan.hwp.section import SectionParser
from dochan.model.document import Document
from dochan.output.plain_text import to_plain_text
from dochan.utils.bounded_io import MAX_OLE_DOCUMENT_SIZE, read_ole_stream, validate_file_size
from dochan.utils.safe_decompress import safe_zlib_decompress
from scripts.probe_hwp_features import _records

# 진단 자체도 무제한 순회를 하지 않는다. 운영 파서의 상한은 변경하지 않는다.
MAX_DIAGNOSTIC_RECORDS = 1_000_000


def _raw_inventory(ole, paths, compressed):
    rows = []
    for path in paths:
        raw = read_ole_stream(ole, path)
        if compressed:
            raw = safe_zlib_decompress(raw)
        parser = SectionParser()
        offset = 0
        count = 0
        tags = Counter()
        while offset < len(raw) - 3 and count < MAX_DIAGNOSTIC_RECORDS:
            record, offset = parser._read_one_record(raw, offset)
            count += 1
            tags[record.tag_id] += 1
        rows.append(dict(stream='/'.join(path), bytes=len(raw), records=count,
                         fully_scanned=offset == len(raw), tags=dict(tags)))
    return rows


def _compare(ole, header, info):
    texts = {}
    result = {}
    for storage, mode in (('ViewText', 'final'), ('BodyText', 'preserve')):
        parser = SectionParser(doc_info=info, revision_mode=mode,
                               project_revisions=storage == 'ViewText')
        document = Document(source_format='hwp')
        paths = sorted(path for path in ole.listdir()
                       if len(path) == 2 and path[0] == storage)
        for path in paths:
            document.sections.append(parser.parse_stream(read_ole_stream(ole, path),
                                                         header.is_compressed))
        text = to_plain_text(document)
        texts[storage] = text
        errors = list(info.errors) + parser.errors
        result[storage] = dict(sections=len(paths), characters=len(text),
                               paragraphs=len(document.find_all('paragraph')),
                               sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                               errors=errors, incomplete=any(e.startswith('ERR:') for e in errors))
    result['exact'] = texts['ViewText'] == texts['BodyText']
    result['passed'] = result['exact'] and all(result[s]['sections'] and not result[s]['incomplete']
                                              for s in ('ViewText', 'BodyText'))
    if not result['exact']:
        a, b = texts['ViewText'], texts['BodyText']
        result['common_prefix_characters'] = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y),
                                                  min(len(a), len(b)))
    return result, texts['BodyText']


def probe(corpus):
    root = Path(corpus)
    hwp_root = root / 'hwp' if (root / 'hwp').is_dir() else root
    counts = Counter()
    rows = []
    failures = []
    for path in sorted(hwp_root.glob('*.hwp')):
        counts['files'] += 1
        header = None
        try:
            validate_file_size(str(path), MAX_OLE_DOCUMENT_SIZE)
            if not olefile.isOleFile(str(path)):
                counts['not_ole'] += 1
                continue
            with olefile.OleFileIO(str(path)) as ole:
                if not ole.exists('FileHeader'):
                    counts['no_file_header'] += 1
                    continue
                header = FileHeader.parse(read_ole_stream(ole, 'FileHeader', max_bytes=256))
                counts['hwp'] += 1
                counts['header_tracking_documents'] += header.is_track_change
                counts['invalid_header'] += any(e.startswith('ERR:') for e in header.validate())
                if header.is_encrypted or header.is_distribution:
                    counts['encrypted_or_distribution'] += 1
                    counts['protected_header_tracking_documents'] += header.is_track_change
                    continue
                issues = []
                records = _records(ole, 'DocInfo', header.is_compressed, issues) if ole.exists('DocInfo') else []
                changes = sum(r.tag_id == 96 for r in records)
                counts['docinfo_partial'] += bool(issues)
                if not (header.is_track_change or changes):
                    continue
                counts['revision_documents'] += 1
                counts['metadata_only_tracking_documents'] += not header.is_track_change
                info = DocInfoParser().parse_stream(read_ole_stream(ole, 'DocInfo'), header.is_compressed)
                result, _ = _compare(ole, header, info)
                row = dict(file=path.name, tracking_bit=header.is_track_change,
                           changes=changes, baseline=result)
                counts['projection_body_exact'] += result['exact']
                counts['projection_body_passed'] += result['passed']
                if not result['passed']:
                    paths = sorted(p for p in ole.listdir()
                                   if len(p) == 2 and p[0] in ('ViewText', 'BodyText'))
                    inventory = _raw_inventory(ole, paths, header.is_compressed)
                    row['raw_stream_inventory'] = inventory
                    if all(r['fully_scanned'] for r in inventory):
                        observed_max = max(r['records'] for r in inventory)
                        with patch('dochan.hwp.section.MAX_HWP_RECORDS', observed_max + 1):
                            row['diagnostic_only_expanded_record_limit'], _ = _compare(ole, header, info)
                        row['diagnostic_only_record_limit'] = observed_max + 1
            final = Dochan(path, revision_mode='final')
            preserve = Dochan(path)
            row['api_final'] = dict(characters=len(final.to_plain_text()),
                                    markdown_characters=len(final.to_markdown()), errors=final.errors)
            row['api_preserve'] = dict(characters=len(preserve.to_plain_text()),
                                       markdown_characters=len(preserve.to_markdown()), errors=preserve.errors)
            rows.append(row)
        except Exception as error:
            counts['failures'] += 1
            counts['failed_header_tracking_documents'] += bool(header and header.is_track_change)
            failures.append(dict(file=path.name, error=type(error).__name__,
                                 tracking_bit=header.is_track_change if header else None))
    return dict(counts=dict(counts), revisions=rows, failures=failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
