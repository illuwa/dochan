"""구분선·본문 위첨자·하단 정의가 일치하는 PDF 각주 휴리스틱.

PDF에는 일반적인 각주/미주 번호 관계가 남지 않으므로, 세 증거가 모두 있는
작은 하단 블록만 복원한다. 하단 블록은 footnote로 정규화하고, 명시적인 문서 끝 미주 구역은
별도의 문서 단위 검출기로 endnote로 복원한다. 반환된 정의 조각만 본문에서 빼며 참조 번호는 문서 전체에서 증가한다.
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


_ENDNOTE_HEADING = re.compile(r"^(?:미\s*주|end\s*notes|notes)$", re.IGNORECASE)
_ENDNOTE_DEFINITION = re.compile(r"^\s*(\d{1,3})[.)]\s+\S")
_ENDNOTE_MARKER = re.compile(r"^\s*(\d{1,3})[.)]?\s*$")
MAX_ENDNOTE_LINES = 200000


def endnote_references(fragments, warnings=None):
    """앞 페이지의 확실한 위첨자 후보만 보존한다. 본문 전체를 중복 보관하지 않는다."""
    if len(fragments) > MAX_NOTE_FRAGMENTS:
        if warnings is not None:
            warnings.append("WARN: PDF 미주 조각 수 한도 초과 — 참조 복원 생략")
        return []
    horizontal = [f for f in fragments if _finite_fragment(f) and f.size > 0
                  and writing_direction(f) == "ltr"]
    markers = [(f, _ENDNOTE_MARKER.fullmatch(f.text)) for f in horizontal
               if not f.note_ref]
    markers = [(f, m) for f, m in markers if m]
    if len(markers) > MAX_NOTE_MARKERS:
        if warnings is not None:
            warnings.append("WARN: PDF 미주 표지 수 한도 초과 — 참조 복원 생략")
        return []
    hosts = sorted(horizontal, key=lambda f: f.y)
    ys = [f.y for f in hosts]
    max_size = max((f.size for f in hosts), default=0)
    budget = [MAX_NOTE_GEOMETRY_CHECKS]
    result = []
    for marker, match in markers:
        nearby = hosts[bisect_left(ys, marker.y - max_size * .3):bisect_right(ys, marker.y)]
        if not _spend(budget, len(nearby), warnings):
            return []
        valid = [h for h in nearby if marker.size <= h.size * .8
                 and .15 * h.size <= marker.y - h.y <= .3 * h.size
                 and -.1 * h.size <= marker.x - h.x - h.width <= .5 * h.size]
        if len(valid) == 1:
            result.append((marker.order, match.group(1)))
    return result


def _endnote_reference_runs(line, order, number, original_runs=None):
    """기존 서식·링크를 보존하면서 한 원본 조각의 run만 미주 참조로 바꾼다."""
    try:
        index = line.fragment_orders.index(order)
    except ValueError:
        return None
    original_runs = line.runs if original_runs is None else original_runs
    text = "".join(run[0] for run in original_runs)
    cursor = 0
    for segment in line.segments[:index + 1]:
        start = text.find(segment.text, cursor)
        if start < 0:
            return None
        cursor = start + len(segment.text)
    end = cursor
    result, cursor = [], 0
    for run in original_runs:
        stop = cursor + len(run[0])
        first, last = max(start, cursor), min(end, stop)
        if first < last:
            if first > cursor:
                result.append((run[0][:first - cursor],) + run[1:])
            result.append((run[0][first - cursor:last - cursor], run[1], run[2],
                           run[3] if len(run) > 3 else "", number, "endnote"))
            if last < stop:
                result.append((run[0][last - cursor:],) + run[1:])
        else:
            result.append(run)
        cursor = stop
    return result


def detect_endnotes(drafts, dropped, first_number=1, warnings=None):
    """명시적인 문서 끝 미주 구역을 여러 페이지에 걸쳐 원자적으로 연결한다.

    제목·번호 정의·앞선 위첨자가 모두 일치하고 뒤에 본문/표가 없는 경우만
    이동한다. 증거 없는 마지막 페이지 전체를 미주로 간주하지 않는다.
    """
    if sum(len(g) for d in drafts for g in d.groups) > MAX_ENDNOTE_LINES:
        if warnings is not None:
            warnings.append("WARN: PDF 미주 줄 수 한도 초과 — 미주 구역 복원 생략")
        return first_number
    entries = [(d, line) for d in drafts for g in d.groups for line in g
               if id(line) not in dropped.get(d.page_number, set())]
    headings = [i for i, (_d, line) in enumerate(entries)
                if _ENDNOTE_HEADING.fullmatch(line.text.strip())]
    if len(headings) != 1:
        return first_number
    begin = headings[0]
    section = entries[begin + 1:]
    if not section:
        return first_number
    heading_draft, heading = entries[begin]
    end_drafts = [d for d in drafts if d.page_number >= heading_draft.page_number]
    if any(d.ordered or d.rotation for d in end_drafts):
        return first_number
    references = {}
    source_lines = {}
    budget = [MAX_NOTE_GEOMETRY_CHECKS]
    for d, line in entries[:begin]:
        if not _spend(budget, len(line.fragment_orders), warnings):
            return first_number
        for order in line.fragment_orders:
            source_lines[(d.page_number, order)] = line
    marker_count = sum(len(getattr(d, "note_markers", [])) for d in drafts)
    if marker_count > MAX_NOTE_MARKERS:
        return first_number
    for d in drafts:
        for order, label in getattr(d, "note_markers", []):
            line = source_lines.get((d.page_number, order))
            if line is not None:
                references.setdefault(label, []).append((line, order))
    if len(references) > MAX_NOTE_MARKERS:
        return first_number
    definitions = []
    for d, line in section:
        if not (all(math.isfinite(value) for value in (line.size, line.y, line.left, line.right))
                and line.size > 0 and line.direction == "ltr"):
            return first_number
        match = _ENDNOTE_DEFINITION.match(line.text)
        if match:
            if len(definitions) >= MAX_NOTE_MARKERS:
                return first_number
            if any(item[0] == match.group(1) for item in definitions):
                return first_number
            if len(references.get(match.group(1), [])) != 1:
                return first_number
            definitions.append((match.group(1), [(d, line)]))
        else:
            if not definitions:
                return first_number
            first = definitions[-1][1][0][1]
            previous_draft, previous = definitions[-1][1][-1]
            margins = [first.left]
            if len(first.segments) > 1 and _ENDNOTE_MARKER.fullmatch(first.segments[0].text):
                margins.append(first.segments[1].x0)
            if (abs(line.size - first.size) > .1
                    or not any(abs(line.left - left) <= GEOMETRY_TOLERANCE for left in margins)
                    or (d is previous_draft and not 0 < previous.y - line.y <= line.size * 2)):
                return first_number
            definitions[-1][1].append((d, line))
    planned = []
    reference_updates = {}
    for offset, (label, lines) in enumerate(definitions):
        number = first_number + offset
        source, order = references[label][0]
        runs = _endnote_reference_runs(source, order, number, reference_updates.get(id(source)))
        if runs is None:
            return first_number
        reference_updates[id(source)] = runs
        paragraphs = []
        for index, (d, line) in enumerate(lines):
            paragraph = _paragraph(line, d.page_number)
            if index == 0:
                prefix = re.match(r"^\s*\d{1,3}[.)]\s*", paragraph.text).end()
                for run in paragraph.runs:
                    removed = min(prefix, len(run.text))
                    run.text = run.text[removed:]
                    prefix -= removed
                paragraph.runs = [r for r in paragraph.runs if r.text]
            paragraphs.append(paragraph)
        planned.append((source, runs, lines, Footnote(type="endnote", paragraphs=paragraphs, number=number)))
    # 판단이 모두 끝난 뒤에만 본문과 참조를 수정한다.
    dropped.setdefault(heading_draft.page_number, set()).add(id(heading))
    for source, runs, lines, note in planned:
        source.runs = reference_updates[id(source)]
        lines[0][0].notes.append(note)
        for d, line in lines:
            dropped.setdefault(d.page_number, set()).add(id(line))
    return first_number + len(planned)
