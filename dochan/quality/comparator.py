"""
quality/comparator.py — 필터 서버 GT 대조
자체 파싱 결과 vs 필터 서버 결과 비교
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ComparisonResult:
    """비교 결과"""
    text_similarity: float = 0.0       # 0~1 텍스트 유사도
    table_count_match: bool = False
    equation_count_match: bool = False
    image_count_match: bool = False
    details: str = ""


def compare_with_gt(our_text: str, gt_text: str) -> ComparisonResult:
    """자체 파싱 텍스트 vs GT 텍스트 비교"""
    result = ComparisonResult()

    # 텍스트 정규화
    our_clean = _normalize(our_text)
    gt_clean = _normalize(gt_text)

    if not gt_clean:
        result.details = "GT 텍스트 없음"
        return result

    # 문자 단위 유사도 (간단한 방식)
    result.text_similarity = _char_similarity(our_clean, gt_clean)

    return result


def _normalize(text: str) -> str:
    """비교를 위한 텍스트 정규화"""
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def _char_similarity(a: str, b: str) -> float:
    """두 문자열의 문자 집합 기반 유사도 (Jaccard)"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    # bigram 기반 유사도
    a_bigrams = set()
    b_bigrams = set()
    for i in range(len(a) - 1):
        a_bigrams.add(a[i:i+2])
    for i in range(len(b) - 1):
        b_bigrams.add(b[i:i+2])

    if not a_bigrams or not b_bigrams:
        return 0.0

    intersection = len(a_bigrams & b_bigrams)
    union = len(a_bigrams | b_bigrams)
    return intersection / union if union > 0 else 0.0
