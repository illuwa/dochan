"""PDF 렌더를 눈으로 판독한 공개 보도자료 43문단의 제목 정확도.

각 (newsId, PDF 쪽, HWPX 최상위 문단 인덱스, 제목 여부)는 PDFium 렌더를
보며 기록했다. 짝수 newsId는 기준 선택, 홀수는 보류 검증 표본이다.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path


LABELS = {
    156783590: (4, {12, 17, 23}, range(12, 24)),
    156783701: (4, {19, 24}, range(19, 25)),
    156783756: (3, {9, 19}, range(9, 20)),
    156783951: (7, {39, 42}, range(39, 45)),
    156784194: (1, {1, 2, 3}, range(1, 9)),
}


def _score(root):
    from dochan import Dochan

    groups = {'tuning': Counter(), 'holdout': Counter(), 'hwp_pairs': Counter()}
    rows = []
    for news_id, (page, positives, indices) in LABELS.items():
        pdf = root / ('%d.pdf' % news_id)
        hwpx = root / ('%d.hwpx' % news_id)
        if not pdf.is_file() or not hwpx.is_file():
            raise FileNotFoundError('missing public pair: %d' % news_id)
        doc = Dochan(str(hwpx), include_assets=False).doc
        paragraphs = [item for section in doc.sections for item in section.elements
                      if hasattr(item, 'heading_level')]
        hwp = root / ('%d.hwp' % news_id)
        hwp_paragraphs = []
        if hwp.is_file():
            hwp_doc = Dochan(str(hwp)).doc
            hwp_paragraphs = [item for section in hwp_doc.sections for item in section.elements
                              if hasattr(item, 'heading_level')]
        group = groups['tuning' if news_id % 2 == 0 else 'holdout']
        for index in indices:
            predicted = bool(paragraphs[index].heading_level)
            expected = index in positives
            group['paragraphs'] += 1
            group['positive'] += expected
            group['predicted'] += predicted
            group['tp'] += expected and predicted
            group['fp'] += not expected and predicted
            group['fn'] += expected and not predicted
            rows.append((news_id, page, index, expected, paragraphs[index].heading_level))
            if hwp_paragraphs and index < len(hwp_paragraphs):
                candidate = hwp_paragraphs[index]
                if candidate.text.strip() == paragraphs[index].text.strip():
                    hwp_group = groups['hwp_pairs']
                    hwp_predicted = bool(candidate.heading_level)
                    hwp_group['paragraphs'] += 1
                    hwp_group['positive'] += expected
                    hwp_group['predicted'] += hwp_predicted
                    hwp_group['tp'] += expected and hwp_predicted
                    hwp_group['fp'] += not expected and hwp_predicted
                    hwp_group['fn'] += expected and not hwp_predicted
    return groups, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--source-root', type=Path,
                        default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    groups, rows = _score(args.corpus)
    for name, group in groups.items():
        precision = group['tp'] / group['predicted'] if group['predicted'] else 0
        recall = group['tp'] / group['positive'] if group['positive'] else 0
        print('%s: %s precision=%.4f recall=%.4f' % (
            name, dict(group), precision, recall))
    for row in rows:
        print('%d PDF p%d HWPX body[%d] expected=%d actual=%d' % row)


if __name__ == '__main__':
    main()
