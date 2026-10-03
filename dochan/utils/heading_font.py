"""HWP/HWPX의 개요 정보 없는 문단에 쓰는 공통 글꼴 제목 규칙."""

from collections import Counter


MAX_FONT_HEADING_PARAGRAPHS = 200_000


def first_visible_font_size(runs):
    """공백뿐인 선행 런을 건너뛴 첫 글자 런의 포인트 크기."""
    for run in runs:
        if run.text.strip():
            return run.font_size_pt
    return 0


def body_font_size(paragraphs):
    """문단 길이 가중 최빈 글꼴 크기. 빈약한 표본에는 0을 반환한다."""
    weights = Counter()
    count = 0
    for para in paragraphs:
        size = first_visible_font_size(para.runs)
        if size <= 0:
            continue
        count += 1
        weights[round(size, 1)] += min(len(para.text.strip()), 200)
    if count < 3 or sum(weights.values()) < 40:
        return 0
    return min(weights, key=lambda size: (-weights[size], size))


def relative_heading_level(runs, body_size):
    """본문 크기보다 뚜렷이 큰 첫 글자 런만 H1~H3로 판정한다."""
    size = first_visible_font_size(runs)
    if body_size <= 0 or size <= 0:
        return 0
    ratio = size / body_size
    if ratio >= 1.4:
        return 1
    if ratio >= 1.25:
        return 2
    if ratio >= 1.1:
        return 3
    return 0


def finalize_font_headings(paragraphs):
    """본문 크기를 추정할 수 있는 문서만 글꼴 폴백을 다시 계산한다."""
    paragraphs = tuple(paragraphs)
    body_size = body_font_size(paragraphs)
    if body_size:
        for para in paragraphs:
            para.heading_level = relative_heading_level(para.runs, body_size)
    return body_size
