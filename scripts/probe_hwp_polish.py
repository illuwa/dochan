"""재감수 표본을 읽기 전용으로 검증하고 공개 파일명과 집계만 출력한다.

실행: /usr/bin/python3 -m scripts.probe_hwp_polish /path/to/hwp-public
"""
import argparse
import json
from pathlib import Path

from dochan import cfb

from dochan import Dochan
from dochan.hwp.forms import clickhere_prompt
from dochan.hwp.header import FileHeader
from dochan.hwp.records.para_text import parse_para_text
from dochan.utils.bounded_io import read_ole_stream
from scripts.probe_hwp_features import _records


def _fields(path):
    with cfb.OleFileIO(str(path)) as ole:
        header = FileHeader.parse(read_ole_stream(ole, 'FileHeader', max_bytes=256))
        records = [record for entry in ole.listdir()
                   if len(entry) == 2 and entry[0] == 'BodyText'
                   for record in _records(ole, entry, header.is_compressed)]
    controls = [r for r in records if r.tag_id == 71 and r.data[:4] == b'klc%']
    directions = {clickhere_prompt(r.data) for r in controls} - {''}
    raw_text = '\n'.join(parse_para_text(r.data)['text'] for r in records if r.tag_id == 67)
    actual = Dochan(path)
    return dict(file=path.name, controls=len(controls),
                unique_directions=len(directions),
                raw_body_direction_occurrences=sum(raw_text.count(t) for t in directions),
                output_direction_occurrences=sum(actual.to_plain_text().count(t) for t in directions),
                markdown_characters=len(actual.to_markdown()), errors=actual.errors)


def probe(corpus):
    root = Path(corpus)
    fields = [_fields(root / 'hwp' / (stem + '.hwp'))
              for stem in ('field-01', 'field-01-memo', 'rhwp-field-01')]
    stems = ['form-01', 'form-02', 'form-002', 'sample-outline-list',
             'sample-mixed-lists-with-outline']
    for prefix in ('nts-241226', 'nts-20260108', 'korea-20260726_보도자료_기상청',
                   'pubinst-kma_20260726'):
        stems.extend(p.stem for p in sorted((root / 'hwp').glob(prefix + '*.hwp')))
    pairs = []
    for stem in stems:
        hwp = Dochan(root / 'hwp' / (stem + '.hwp'))
        hwpx = Dochan(root / 'hwpx' / (stem + '.hwpx'))
        left, right = hwp.find_all('paragraph'), hwpx.find_all('paragraph')
        pairs.append(dict(file=stem, paragraphs_hwp=len(left), paragraphs_hwpx=len(right),
                          plain_exact=hwp.to_plain_text() == hwpx.to_plain_text(),
                          markdown_exact=hwp.to_markdown() == hwpx.to_markdown(),
                          paragraphs_exact=[p.text for p in left] == [p.text for p in right],
                          headings_exact=[p.heading_level for p in left] == [p.heading_level for p in right],
                          direction_occurrences_hwp=hwp.to_plain_text().count('이곳을 마우스로 누르고'),
                          direction_occurrences_hwpx=hwpx.to_plain_text().count('이곳을 마우스로 누르고'),
                          errors_hwp=hwp.errors, errors_hwpx=hwpx.errors))
    multi = Dochan(root / 'hwp' / 'hwp-multi-002.hwp')
    paragraphs = multi.find_all('paragraph')
    return dict(fields=fields, pairs=pairs,
                multi=dict(file='hwp-multi-002.hwp', paragraphs=len(paragraphs),
                           headings=sum(p.is_heading for p in paragraphs),
                           pair_exists=(root / 'hwpx' / 'hwp-multi-002.hwpx').is_file(),
                           errors=multi.errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
