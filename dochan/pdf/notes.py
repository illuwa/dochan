"""구분선·본문 위첨자·하단 정의가 일치하는 PDF 각주 휴리스틱.

PDF에는 일반적인 각주/미주 번호 관계가 남지 않으므로, 세 증거가 모두 있는
작은 하단 블록만 복원한다. 각주와 미주는 모양으로 구분할 수 없어 footnote로
정규화한다. 반환된 정의 조각만 본문에서 빼며 참조 번호는 문서 전체에서 증가한다.
"""
from bisect import bisect_left, bisect_right
from collections import Counter
import math
import re

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from ..model.header_footer import Footnote
from .content import assemble_lines, writing_direction
from .pagination import HEADER_FOOTER_ZONE

MAX_NOTE_FRAGMENTS = 50000
MAX_NOTE_MARKERS = 1000
MAX_NOTES_PER_PAGE = 100
MAX_NOTE_GEOMETRY_CHECKS = 200000
GEOMETRY_TOLERANCE = 1.5
# 두 내부 양성 문서의 구분선은 첫 정의보다 정확히 15pt 위였다.
MAX_SEPARATOR_GAP = 15.0 + GEOMETRY_TOLERANCE
_MARKER = re.compile(r"^\s*(\d{1,3})\)\s*$")
_DEFINITION = re.compile(r"^\s*(\d{1,3})\)\s*\S")


def _finite_fragment(frag):
    return all(math.isfinite(value) for value in
               (frag.x, frag.y, frag.width, frag.size))


def _spend(budget, count, warnings):
    budget[0] -= count
    if budget[0] >= 0:
        return True
    if warnings is not None:
        warnings.append("WARN: PDF 각주 기하 검사 수 한도(200000) 초과 — 각주 복원 생략")
    return False


def _has_separator(segments, line, budget, warnings):
    if not _spend(budget, len(segments), warnings):
        return False
    verticals = sorted((segment.x0, min(segment.y0, segment.y1),
                        max(segment.y0, segment.y1)) for segment in segments
                       if all(math.isfinite(value) for value in
                              (segment.x0, segment.y0, segment.x1, segment.y1))
                       and abs(segment.x0 - segment.x1) <= GEOMETRY_TOLERANCE
                       and abs(segment.y0 - segment.y1) > GEOMETRY_TOLERANCE)
    vertical_xs = [item[0] for item in verticals]
    for segment in segments:
        if not _spend(budget, 1, warnings):
            return False
        if not all(math.isfinite(value) for value in
                   (segment.x0, segment.y0, segment.x1, segment.y1)):
            continue
        if abs(segment.y1 - segment.y0) > GEOMETRY_TOLERANCE:
            continue
        y = (segment.y0 + segment.y1) / 2
        left, right = sorted((segment.x0, segment.x1))
        if not (0 < y - line.y <= MAX_SEPARATOR_GAP
                and abs(left - line.left) <= GEOMETRY_TOLERANCE
                and right - left > line.size):
            continue
        # 표 테두리는 각주 구분선이 아니다. 끝점에 세로선이 붙으면 거부한다.
        nearby = []
        for edge in (left, right):
            low = bisect_left(vertical_xs, edge - GEOMETRY_TOLERANCE)
            high = bisect_right(vertical_xs, edge + GEOMETRY_TOLERANCE)
            if not _spend(budget, high - low, warnings):
                return False
            nearby.extend(verticals[low:high])
        attached = any(low - GEOMETRY_TOLERANCE <= y <= high + GEOMETRY_TOLERANCE
                       for _x, low, high in nearby)
        if not attached:
            return True
    return False


def _paragraph(line, page_number, strip_marker=False):
    provenance = Provenance(source_format="pdf", page=page_number)
    runs = []
    skip = 0
    if strip_marker:
        prefix = re.match(r"^\s*\d{1,3}\)\s*", "".join(run[0] for run in line.runs))
        skip = prefix.end() if prefix else 0
    for run in line.runs:
        text, bold, italic = run[:3]
        removed = min(skip, len(text))
        skip -= removed
        text = text[removed:]
        if text:
            runs.append(TextRun(text=text, bold=bold, italic=italic,
                                link=run[3] if len(run) > 3 else "",
                                note_ref=run[4] if len(run) > 4 else 0,
                                note_reference_type="footnote" if len(run) > 4 and run[4] else "",
                                note_reference_number=run[4] if len(run) > 4 and run[4] else None,
                                provenance=provenance))
    return Paragraph(runs=runs, provenance=provenance)


def detect_notes(fragments, segments, bounds, page_number, first_number=1, warnings=None):
    """(Footnote 목록, 소비 정의 order 집합, 참조 order→번호, 다음 번호)를 반환한다."""
    empty = ([], set(), {}, first_number)
    if not fragments:
        return empty
    if len(fragments) > MAX_NOTE_FRAGMENTS:
        if warnings is not None:
            warnings.append("WARN: PDF 각주 조각 수 한도(50000) 초과 — 각주 복원 생략")
        return empty
    if not all(_finite_fragment(frag) for frag in fragments):
        return empty
    if not all(math.isfinite(value) for value in bounds):
        return empty
    horizontal = [frag for frag in fragments if frag.size > 0 and writing_direction(frag) == "ltr"]
    if not horizontal:
        return empty
    bottom, top = bounds
    body_fragments = [frag for frag in horizontal
                      if frag.y > bottom + (top - bottom) * 0.25]
    if not body_fragments:
        return empty
    sizes = Counter(round(frag.size, 3) for frag in body_fragments)
    body = sizes.most_common(1)[0][0]
    lines = assemble_lines(horizontal)
    definitions = [(index, line, _DEFINITION.match(line.text))
                   for index, line in enumerate(lines)
                   if bottom <= line.y <= bottom + (top - bottom) * 0.25
                   and 0 < line.size < body * 0.9]
    definitions = [(index, line, match) for index, line, match in definitions if match]
    if not definitions:
        return empty
    if len(definitions) > MAX_NOTES_PER_PAGE:
        if warnings is not None:
            warnings.append("WARN: PDF 페이지 각주 수 한도(100) 초과 — 각주 복원 생략")
        return empty
    first = max(definitions, key=lambda item: item[1].y)[1]
    budget = [MAX_NOTE_GEOMETRY_CHECKS]
    if not _has_separator(segments, first, budget, warnings):
        return empty
    markers = [(frag, _MARKER.match(frag.text)) for frag in horizontal
               if 0 < frag.size <= body * 0.8]
    markers = [(frag, match) for frag, match in markers if match]
    if len(markers) > MAX_NOTE_MARKERS:
        if warnings is not None:
            warnings.append("WARN: PDF 각주 표지 수 한도(1000) 초과 — 각주 복원 생략")
        return empty
    hosts = sorted((frag for frag in horizontal if frag.size >= body * 0.95), key=lambda frag: frag.y)
    host_ys = [frag.y for frag in hosts]
    max_size = max((host.size for host in hosts), default=0)
    references = {}
    # 세로 색인으로 가까운 기준선만 본다. 모든 표지와 모든 조각의 직적을 피한다.
    for frag, match in markers:
        nearby = hosts[bisect_left(host_ys, frag.y - 0.3 * max_size):bisect_right(host_ys, frag.y)]
        if not _spend(budget, len(nearby), warnings):
            return empty
        nearby = [host for host in nearby
                  if 0.15 * host.size <= frag.y - host.y <= 0.3 * host.size
                  and -0.1 * host.size <= frag.x - host.x - host.width <= 0.5 * host.size]
        if len(nearby) == 1:
            references.setdefault(match.group(1), []).append(frag)
    counts = Counter(match.group(1) for _index, _line, match in definitions)
    # 블록의 일부 정의만 이동하면 미해결 표지가 남고 본문/각주 경계도 불명확해진다.
    for _index, line, match in definitions:
        refs = references.get(match.group(1), [])
        if len(refs) != 1 or counts[match.group(1)] != 1 or refs[0].y <= line.y + body:
            return empty
    notes, consumed, reference_numbers = [], set(), {}
    number = first_number
    for index, line, match in definitions:
        following = next((i for i, _ln, _m in definitions if i > index), len(lines))
        note_lines = [line]
        previous_y = line.y
        observed_gap = None
        left_margins = [line.left]
        # 표지가 독립 조각이면 실제 정의 텍스트의 시작 x도 연속 줄의
        # 내어쓰기 기준으로 쓴다. 글자 수로 들여쓰기 폭을 추정하지 않는다.
        if len(line.segments) > 1 and _MARKER.match(line.segments[0].text):
            left_margins.append(line.segments[1].x0)
        for continuation in lines[index + 1:following]:
            gap = previous_y - continuation.y
            # 하단 영역은 독립 바닥글일 수 있으므로, 위에서 실제로 관찰한
            # 줄간격이 있어야 진입한다. 이어지는 줄도 아래의 간격·내어쓰기
            # 검사를 통과해야 한다. 위치만으로 긴 각주의 끝을 잘라내지 않는다.
            if (continuation.y > line.y or abs(continuation.size - line.size) > 0.1
                    or continuation.y < bottom
                    or (continuation.y <= bottom + HEADER_FOOTER_ZONE
                        and observed_gap is None)
                    or not any(abs(continuation.left - left) <= GEOMETRY_TOLERANCE
                               for left in left_margins)
                    or gap <= 0 or gap > line.size * 2
                    or (observed_gap is not None
                        and abs(gap - observed_gap) > GEOMETRY_TOLERANCE)):
                break
            note_lines.append(continuation)
            if observed_gap is None:
                observed_gap = gap
            previous_y = continuation.y
        paragraphs = [_paragraph(note_line, page_number, offset == 0)
                      for offset, note_line in enumerate(note_lines)]
        if not paragraphs or not any(paragraph.text.strip() for paragraph in paragraphs):
            return empty
        notes.append(Footnote(type="footnote", paragraphs=paragraphs, number=number))
        for note_line in note_lines:
            # 줄 조립 때 보존한 실제 원본만 소비한다. 좌표와 최대 글자 크기로
            # 다시 찾으면 혼합 크기 조각을 남기거나 다른 줄의 조각을 지운다.
            if not _spend(budget, len(note_line.fragment_orders), warnings):
                return empty
            consumed.update(note_line.fragment_orders)
        reference_numbers[references[match.group(1)][0].order] = number
        number += 1
    return notes, consumed, reference_numbers, number
