"""PDF 렌더로 판독한 별도 공개 개발 표본의 HWP/HWPX 제목 일치도.

표본 경로는 실행 인자로 받는다. 아래 인덱스는 최상위 문단 기준이며,
PDF 쪽과 텍스트 접두어를 함께 대조해 문단 순서가 달라지면 실패한다.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


# (공개 newsId, PDF 1-based 쪽, 최상위 문단 인덱스, 제목 여부, 텍스트 접두어)
# 본 작업 평가용 34문서와 기존 5문서는 포함하지 않았다.
DEVELOPMENT = (
    ('156783513', 4, 14, True, '□ 추진배경'),
    ('156783513', 4, 17, True, '□ 진행계획'),
    ('156783784', 3, 15, True, '□ 분석 조건'),
    ('156783784', 3, 19, True, '□ 분석 결과'),
    ('156784016', 3, 7, True, '□ 개요'),
    ('156784016', 3, 17, True, '□ 세부일정'),
    ('156784016', 3, 18, True, '□ 향후 추진계획'),
    ('156784118', 2, 13, True, '□ 목적'),
    ('156784118', 2, 17, False, '□ 일시'),
    ('156784118', 2, 18, False, '□ 장소'),
    ('156784118', 2, 19, False, '□ 참석'),
    ('156784118', 2, 20, True, '□ 주요 내용'),
    ('156784118', 2, 34, True, '□ 세부 일정'),
    ('156784118', 2, 35, True, '□ 연구 배경'),
    ('156784118', 2, 39, True, '□ 주요 연구 내용'),
    ('156783551', 3, 12, False, '□ 표 1.'),
    ('156783551', 3, 14, False, '□ 표 2.'),
    ('156783551', 3, 16, False, '□ 표 3.'),
    ('156783551', 3, 18, False, '□ 표 4.'),
    ('156783551', 3, 20, False, '1. 국립축산과학원'),
    ('156783551', 3, 21, False, '2. 강선문'),
    ('156783557', 6, 43, True, '□ 연구 배경'),
    ('156783557', 6, 47, True, '□ 고소애 가수분해물'),
    ('156783765', 1, 4, True, '< 국민 일상에서'),
)


def score(corpus):
    from dochan import Dochan

    counts = {ext: Counter() for ext in ('.hwp', '.hwpx')}
    rows = []
    cache = {}
    for stem, page, index, expected, prefix in DEVELOPMENT:
        for ext in ('.hwp', '.hwpx'):
            path = corpus / (stem + ext)
            if path not in cache:
                doc = Dochan(str(path)).doc
                cache[path] = [item for section in doc.sections
                               for item in section.elements
                               if hasattr(item, 'heading_level')]
            paragraphs = cache[path]
            if index >= len(paragraphs) or not paragraphs[index].text.strip().startswith(prefix):
                raise ValueError('개발 표본 문단 불일치: %s %d' % (path.name, index))
            actual = bool(paragraphs[index].heading_level)
            counter = counts[ext]
            counter['N'] += 1
            counter['H'] += expected
            counter['TP'] += expected and actual
            counter['FP'] += not expected and actual
            counter['FN'] += expected and not actual
            rows.append({'file': path.name, 'pdf_page': page, 'index': index,
                         'expected': expected, 'level': paragraphs[index].heading_level})
    return {'formats': {key: dict(value) for key, value in counts.items()},
            'rows': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--source-root', type=Path,
                        default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    print(json.dumps(score(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
