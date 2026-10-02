"""공개 HWP/HWPX 문단 정렬과 누름틀 안내문을 읽기 전용으로 검증한다.

실행: /usr/bin/python3 -m scripts.probe_hwp_review /path/to/hwp-public
공개 코퍼스 경로를 인자로 받아 공개 파일명과 집계 수치만 출력한다.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
from unittest.mock import patch
import zipfile

import olefile

from dochan import Dochan
from dochan.hwp.forms import clickhere_prompt
from dochan.hwp.header import FileHeader
from dochan.utils.bounded_io import MAX_OLE_DOCUMENT_SIZE, read_ole_stream, validate_file_size
from scripts.probe_hwp_features import _records, _xml_part, HH

ALIGN = {'JUSTIFY': 0, 'LEFT': 1, 'RIGHT': 2, 'CENTER': 3,
         'DISTRIBUTE': 4, 'DISTRIBUTE_SPACE': 5}
PRESS_PREFIXES = ('nts-241226', 'nts-20260108',
                  'korea-20260726_보도자료_기상청', 'pubinst-kma_20260726')


def probe(corpus):
    root = Path(corpus)
    counts = Counter()
    align_rows = []
    prompt_rows = []
    failures = []
    for path in sorted((root / 'hwp').glob('*.hwp')):
        counts['files'] += 1
        pair = root / 'hwpx' / (path.stem + '.hwpx')
        try:
            validate_file_size(str(path), MAX_OLE_DOCUMENT_SIZE)
            if not olefile.isOleFile(str(path)):
                continue
            with olefile.OleFileIO(str(path)) as ole:
                if not ole.exists('FileHeader'):
                    continue
                header = FileHeader.parse(read_ole_stream(ole, 'FileHeader', max_bytes=256))
                if header.is_encrypted or header.is_distribution:
                    continue
                if pair.is_file() and not zipfile.is_zipfile(str(pair)):
                    counts['align_invalid_zip_pairs'] += 1
                if pair.is_file() and zipfile.is_zipfile(str(pair)):
                    raw = [struct.unpack_from('<I', record.data)[0]
                           for record in _records(ole, 'DocInfo', header.is_compressed)
                           if record.tag_id == 25 and len(record.data) >= 4]
                    with zipfile.ZipFile(str(pair)) as archive:
                        xml = _xml_part(archive, 'Contents/header.xml')
                        shapes = {int(shape.get('id')): shape.find(HH + 'align').get('horizontal')
                                  for shape in xml.iter(HH + 'paraPr')}
                    if set(shapes) == set(range(len(raw))):
                        expected = [ALIGN.get(shapes[index], -1) for index in range(len(raw))]
                        before = sum((value & 7) == gold for value, gold in zip(raw, expected))
                        after = sum(((value >> 2) & 7) == gold for value, gold in zip(raw, expected))
                        counts['align_pairs'] += 1
                        counts['align_shapes'] += len(raw)
                        counts['align_low3_matches'] += before
                        counts['align_bit2_4_matches'] += after
                        counts['align_bit2_4_exact_pairs'] += after == len(raw)
                        counts['align_low3_exact_pairs'] += before == len(raw)
                        if after == len(raw) and before != after and len(align_rows) < 8:
                            examples = [dict(shape=index, props=hex(value),
                                             expected=shapes[index], low3=value & 7,
                                             bit2_4=(value >> 2) & 7)
                                        for index, (value, gold) in enumerate(zip(raw, expected))
                                        if (value & 7) != gold]
                            align_rows.append(dict(file=path.name, shapes=len(raw),
                                                   before=before, after=after, examples=examples[:3]))
                    else:
                        counts['align_different_shape_sets'] += 1
                click_records = []
                for body_path in ole.listdir():
                    if len(body_path) != 2 or body_path[0] != 'BodyText':
                        continue
                    click_records.extend(record for record in _records(ole, body_path, header.is_compressed)
                                         if record.tag_id == 71 and record.data[:4] == b'klc%')
            if not click_records:
                continue
            counts['click_documents'] += 1
            counts['click_controls'] += len(click_records)
            inserted = []

            def observed_prompt(data):
                value = clickhere_prompt(data)
                if value:
                    inserted.append(value)
                return value

            with patch('dochan.hwp.section.clickhere_prompt', observed_prompt):
                document = Dochan(path)
            counts['positive_prompt_documents'] += bool(inserted)
            counts['positive_prompt_controls'] += len(inserted)
            xml_positive = None
            if inserted and pair.is_file():
                xml_text = Dochan(pair).to_plain_text()
                xml_positive = sum(value in xml_text for value in inserted)
                counts['positive_prompt_paired_documents'] += 1
                counts['positive_prompt_gold_controls'] += xml_positive
            if inserted or path.name.startswith(PRESS_PREFIXES):
                stored_prompts = set()
                for record in click_records:
                    try:
                        value = clickhere_prompt(record.data)
                        if value:
                            stored_prompts.add(value)
                    except ValueError:
                        pass
                actual_text = document.to_plain_text()
                actual_occurrences = sum(actual_text.count(value) for value in stored_prompts)
                gold_occurrences = None
                if pair.is_file():
                    xml_text = Dochan(pair).to_plain_text()
                    gold_occurrences = sum(xml_text.count(value) for value in stored_prompts)
                prompt_rows.append(dict(file=path.name, controls=len(click_records),
                                        dirty_controls=sum(bool(struct.unpack_from('<I', r.data, 4)[0] & 0x8000)
                                                           for r in click_records if len(r.data) >= 8),
                                        accepted_prompts=len(inserted),
                                        output_prompt_occurrences=actual_occurrences,
                                        gold_prompt_occurrences=gold_occurrences,
                                        paired=pair.is_file(), gold_present=xml_positive,
                                        diagnostics=len(document.errors)))
        except Exception as error:
            failures.append(dict(file=path.name, error=type(error).__name__))
    return dict(counts=dict(counts), align_exact_pair_examples=align_rows,
                prompts=prompt_rows, failures=failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
