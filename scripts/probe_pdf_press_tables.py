"""공개 HWPX/PDF 짝의 표 불일치와 줄 결합 오류를 요약한다.

사용법: python -m scripts.probe_pdf_press_tables PAIRS_DIR OUTPUT.json
파일명은 공개 코퍼스에만 사용한다. 원문 전체와 셀 내용은 저장하지 않는다.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import unicodedata

from dochan import Dochan
from dochan.pdf import layout
from scripts.compare_pdf_pairs import find_pairs, normalize_text, token_ratio
from scripts.probe_pdf_table_mismatch import classify_documents

MAX_JOIN_SAMPLES = 8


def _join_label(answer, previous, following, spaced):
    if not (previous and following and
            '가' <= previous[-1] <= '힣' and '가' <= following[0] <= '힣'):
        return None
    tail = unicodedata.normalize('NFC', previous[-3:])
    head = unicodedata.normalize('NFC', following[:3])
    without = tail + head in answer
    with_space = tail + ' ' + head in answer
    if without == with_space:
        return 'ambiguous'
    if spaced == with_space:
        return 'correct'
    return 'missing_space' if with_space else 'extra_space'


def join_outcomes(answer, joins):
    """유일하게 판정되는 한글 줄 경계만 오류 방향을 센다."""
    counts = Counter({'missing_space': 0, 'extra_space': 0,
                      'correct': 0, 'ambiguous': 0})
    source = normalize_text(answer)
    for previous, following, spaced in joins:
        label = _join_label(source, previous, following, spaced)
        if label is not None:
            counts[label] += 1
    return dict(counts)


def suspect_different_content(token_overlap, answer_length, pdf_length):
    """요약 PDF 등의 후보만 표시한다. 참/거짓 판정은 쪽 렌더로 한다."""
    return (answer_length > 0 and pdf_length < answer_length * 0.5
            and token_overlap < 0.5)


def inspect_pair(hwpx_path, pdf_path):
    answer = Dochan(hwpx_path)
    joins = []
    previous_observer = layout.JOIN_OBSERVER
    layout.JOIN_OBSERVER = lambda old, new, space: joins.append((old, new, space))
    try:
        pdf = Dochan(pdf_path)
    finally:
        layout.JOIN_OBSERVER = previous_observer
    answer_text = answer.to_plain_text()
    pdf_text = pdf.to_plain_text()
    ratio = token_ratio(answer_text, pdf_text)
    classified = classify_documents(answer.doc, pdf.doc)
    outcomes = join_outcomes(answer_text, joins)
    samples = []
    normalized_answer = normalize_text(answer_text)
    for previous, following, spaced in joins:
        label = _join_label(normalized_answer, previous, following, spaced)
        if label in ('missing_space', 'extra_space') and len(samples) < MAX_JOIN_SAMPLES:
            samples.append({'kind': label, 'tail': previous[-12:],
                            'head': following[:12]})
    return {
        'token_ratio': round(ratio, 4),
        'answer_length': len(answer_text), 'pdf_length': len(pdf_text),
        'suspect_different_content': suspect_different_content(
            ratio, len(answer_text), len(pdf_text)),
        'pdf_sections': len(pdf.doc.sections),
        'joins': outcomes, 'join_samples': samples,
        'hwpx_tables': classified['hwpx_tables'],
        'pdf_tables': classified['pdf_tables'],
        'signature_exact': classified['baseline_exact'],
        'pdf_only_candidates': classified['pdf_only'],
        'categories': classified['categories'], 'cases': classified['cases'],
        'pdf_errors': len(pdf.errors), 'hwpx_errors': len(answer.errors),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pairs_dir', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    if not (args.pairs_dir / 'manifest.json').is_file():
        parser.error('공개 보도자료 코퍼스의 manifest.json이 필요합니다')
    rows = {}
    failures = Counter()
    for _name, hwpx_path, pdf_path in find_pairs(str(args.pairs_dir)):
        try:
            rows[Path(pdf_path).name] = inspect_pair(hwpx_path, pdf_path)
        except Exception as exc:
            failures[type(exc).__name__] += 1
    categories = Counter()
    joins = Counter()
    for row in rows.values():
        categories.update(row['categories'])
        joins.update(row['joins'])
    report = {'pairs': len(rows), 'failures': dict(failures),
              'categories': dict(categories), 'joins': dict(joins), 'rows': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('pairs', 'failures', 'categories', 'joins')},
                     ensure_ascii=False))
    return int(bool(failures) or not rows)


if __name__ == '__main__':
    raise SystemExit(main())
