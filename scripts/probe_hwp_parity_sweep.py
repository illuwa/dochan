"""공개 HWP/HWPX 같은 이름 쌍의 출력과 구조를 요약해 비교한다.

사용법: python -m scripts.probe_hwp_parity_sweep corpus/hwp-public --output result.json
출력에는 본문 대신 SHA-256, 길이, 일치 지표, 파서 진단만 기록한다.
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from scripts.compare_pdf_pairs import (cell_hit_rate, normalize_text,
                                       structure_matches, table_stats)


def discover_pairs(directory):
    """서로 다른 하위 디렉터리에 저장된 같은 NFC 이름의 파일도 짝짓는다."""
    root = Path(directory)
    formats = {'hwp': {}, 'hwpx': {}}
    for path in sorted(root.rglob('*')):
        suffix = path.suffix.lower().lstrip('.')
        if suffix not in formats or not path.is_file():
            continue
        found = formats[suffix]
        stem = unicodedata.normalize('NFC', path.stem)
        # 형식별 디렉터리의 원본을 우선하고 중복 이름은 한 번만 비교한다.
        priority = 0 if path.parent.name == suffix else 1
        if stem not in found or priority < found[stem][0]:
            found[stem] = (priority, str(path))
    return [(stem, formats['hwpx'][stem][1], formats['hwp'][stem][1])
            for stem in sorted(formats['hwp'].keys() & formats['hwpx'].keys())]


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


_IMAGE_LINK = re.compile(r'(!\[[^\]]*\]\()[^\n)]*(\))')
_PLAIN_IMAGE = re.compile(r'\[이미지: [^\n\]]+\]')


def _asset_neutral(text):
    """비교할 때만 자산의 패키지별 경로를 지운다. 원본 해시는 별도로 보존한다."""
    text = _IMAGE_LINK.sub(r'\1ASSET\2', text)
    return _PLAIN_IMAGE.sub('[이미지: ASSET]', text)


def _image_neutral(text):
    return _IMAGE_LINK.sub('![IMAGE](ASSET)', _asset_neutral(text))


def _title(doc):
    for section in doc.sections:
        for item in section.elements:
            if hasattr(item, 'runs'):
                value = normalize_text(item.text)
                if value:
                    return value[:200]
    return ''


def _headings(doc):
    return [(normalize_text(item.text), item.heading_level)
            for section in doc.sections for item in section.elements
            if hasattr(item, 'runs') and item.heading_level]


def _counts(doc):
    return {kind: len(doc.find_all(kind)) for kind in
            ('table', 'equation', 'footnote', 'endnote', 'image')}


def _token_similarity(left, right):
    """순서에 영향받지 않는 전체 토큰 다중집합 Dice 유사도."""
    a = Counter(normalize_text(left).split())
    b = Counter(normalize_text(right).split())
    total = sum(a.values()) + sum(b.values())
    return round(2 * sum((a & b).values()) / total, 4) if total else 1.0


def summarize_pair(hwpx, hwp):
    answer_md, candidate_md = hwpx.to_markdown(), hwp.to_markdown()
    answer_text, candidate_text = hwpx.to_plain_text(), hwp.to_plain_text()
    neutral_md = _asset_neutral(answer_md), _asset_neutral(candidate_md)
    neutral_text = _asset_neutral(answer_text), _asset_neutral(candidate_text)
    answer_sigs, answer_cells = table_stats(hwpx.doc)
    candidate_sigs, candidate_cells = table_stats(hwp.doc)
    answer_title, candidate_title = _title(hwpx.doc), _title(hwp.doc)
    answer_len, candidate_len = len(answer_text), len(candidate_text)
    length_ratio = (min(answer_len, candidate_len) / max(answer_len, candidate_len)
                    if max(answer_len, candidate_len) else 1.0)
    title_similarity = SequenceMatcher(None, answer_title, candidate_title,
                                       autojunk=False).ratio()
    counts = {'hwpx': _counts(hwpx.doc), 'hwp': _counts(hwp.doc)}
    heading_levels_equal = _headings(hwpx.doc) == _headings(hwp.doc)
    format_valid = (hwpx.doc.source_format == 'hwpx' and
                    hwp.doc.source_format == 'hwp')
    same_document = bool(format_valid and answer_len and candidate_len and
                         (length_ratio >= 0.5 or title_similarity >= 0.7))
    reasons = []
    if answer_md != candidate_md:
        if answer_text == candidate_text:
            reasons.append('markdown_or_format')
        else:
            reasons.append('text_or_flow')
        if answer_sigs != candidate_sigs or answer_cells != candidate_cells:
            reasons.append('table_or_cell')
        for kind in ('equation', 'footnote', 'endnote', 'image'):
            if counts['hwpx'][kind] != counts['hwp'][kind]:
                reasons.append(kind + '_count')
        if not heading_levels_equal:
            reasons.append('heading')
    if answer_md == candidate_md:
        difference_class = 'exact'
    elif neutral_md[0] == neutral_md[1]:
        difference_class = 'asset_path_only'
    elif _image_neutral(answer_md) == _image_neutral(candidate_md):
        difference_class = 'image_markup_only'
    elif neutral_text[0] == neutral_text[1]:
        difference_class = 'format_only'
    elif Counter(neutral_text[0].splitlines()) == Counter(neutral_text[1].splitlines()):
        difference_class = 'line_order'
    elif Counter(neutral_text[0].split()) == Counter(neutral_text[1].split()):
        difference_class = 'text_segmentation'
    else:
        difference_class = 'content'
    return {
        'same_document': same_document,
        'format_valid': format_valid,
        'title_similarity': round(title_similarity, 4),
        'length_ratio': round(length_ratio, 4),
        'plain_lengths': {'hwpx': answer_len, 'hwp': candidate_len},
        'markdown_sha256': {'hwpx': _sha(answer_md), 'hwp': _sha(candidate_md)},
        'plain_sha256': {'hwpx': _sha(answer_text), 'hwp': _sha(candidate_text)},
        'markdown_equal': answer_md == candidate_md,
        'asset_neutral_markdown_equal': neutral_md[0] == neutral_md[1],
        'plain_equal': answer_text == candidate_text,
        'difference_class': difference_class,
        'token_similarity': _token_similarity(answer_text, candidate_text),
        'table_signature': {'hwpx': len(answer_sigs), 'hwp': len(candidate_sigs),
                            'matched': structure_matches(answer_sigs, candidate_sigs)[0]},
        'cell_hit': cell_hit_rate(answer_cells, candidate_cells),
        'cell_text_equal': Counter(answer_cells) == Counter(candidate_cells),
        'heading_levels_equal': heading_levels_equal,
        'heading_counts': {'hwpx': len(_headings(hwpx.doc)),
                           'hwp': len(_headings(hwp.doc))},
        'counts': counts,
        'reasons': reasons,
        'errors': {'hwpx': hwpx.errors[:5], 'hwp': hwp.errors[:5]},
    }


def measure(directory):
    from dochan import Dochan

    rows = {}
    for stem, hwpx_path, hwp_path in discover_pairs(directory):
        try:
            rows[stem] = summarize_pair(Dochan(hwpx_path), Dochan(hwp_path))
        except Exception as exc:
            rows[stem] = {'error': type(exc).__name__ + ': ' + str(exc)[:200]}
    eligible = [row for row in rows.values() if row.get('same_document')]
    reasons = Counter(reason for row in eligible for reason in row['reasons'])
    classes = Counter(row['difference_class'] for row in eligible)
    return {
        'summary': {
            'pairs': len(rows),
            'same_document': len(eligible),
            'excluded_or_unreadable': len(rows) - len(eligible),
            'markdown_exact': sum(row['markdown_equal'] for row in eligible),
            'plain_exact': sum(row['plain_equal'] for row in eligible),
            'mean_token_similarity': round(sum(row['token_similarity'] for row in eligible)
                                           / len(eligible), 4) if eligible else None,
            'reason_counts': dict(reasons),
            'difference_classes': dict(classes),
        },
        'pairs': rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', help='공개 HWP/HWPX 코퍼스 루트')
    parser.add_argument('--output', help='해시와 지표만 담을 JSON 경로')
    args = parser.parse_args(argv)
    result = measure(args.directory)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=1)
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0 if result['summary']['pairs'] else 1


if __name__ == '__main__':
    sys.exit(main())
