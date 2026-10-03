"""독립 PDF 제목 라벨과 부모·앞선 커밋·현재 리더 판정을 대조한다.

라벨 JSON의 b/a는 각각 부모/앞선 커밋에서 저장한 제목 수준이다.
현재 수준은 입력 코퍼스를 다시 읽는다. 라벨과 코퍼스 경로는 인자로 받는다.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from scripts.probe_heading_relative import _paragraphs


def score(corpus, labels_path, overrides_path):
    from dochan import Dochan

    labels = json.loads(labels_path.read_text(encoding='utf-8'))
    overrides = (json.loads(overrides_path.read_text(encoding='utf-8'))
                 if overrides_path else {})
    by_file = defaultdict(list)
    for row in labels:
        by_file[row['doc']].append(row)
    scores = defaultdict(Counter)
    for filename, rows in by_file.items():
        path = corpus / filename
        options = {'include_assets': False} if path.suffix.lower() == '.hwpx' else {}
        doc = Dochan(str(path), **options).doc
        paragraphs = list(_paragraphs(doc))
        for row in rows:
            index = row['i']
            if index >= len(paragraphs):
                raise ValueError('문단 인덱스 불일치: ' + filename)
            text = ' '.join(paragraphs[index][1].text.split())[:100]
            if text != row['t']:
                raise ValueError('라벨 문단 텍스트 불일치: ' + filename)
            expected = overrides.get('%s#%d' % (filename, row['idx']), row['auto']) == 'H'
            for version, predicted in (
                ('parent', bool(row['b'])),
                ('commit', bool(row['a'])),
                ('current', bool(paragraphs[index][1].heading_level)),
            ):
                for group in ('all', path.suffix.lower()):
                    result = scores[(version, group)]
                    result['N'] += 1
                    result['H'] += expected
                    result['TP'] += expected and predicted
                    result['FP'] += not expected and predicted
                    result['FN'] += expected and not predicted
                if expected:
                    kind = ('larger' if row['pdf_sz'] >= 1.1 * row['local_body']
                            else 'same_or_smaller')
                    result = scores[(version, kind)]
                    result['H'] += 1
                    result['TP'] += predicted
    return {'%s:%s' % key: dict(value) for key, value in scores.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('labels', type=Path)
    parser.add_argument('--overrides', type=Path)
    args = parser.parse_args()
    print(json.dumps(score(args.corpus, args.labels, args.overrides),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
