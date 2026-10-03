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
# 표 행 괘선이 쌓인 간격으로 보는 거리(한 행 높이 여유). 각주 구분선 위로는 본문이 온다.
STACKED_RULE_DISTANCE = 48.0
_MARKER = re.compile(r"^\s*(\d{1,3})\)\s*$")
_DEFINITION = re.compile(r"^\s*(\d{1,3})\)\s*\S")
_DIGITS = re.compile(r"^\s*\d{1,3}\s*$")


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
    horizontal = sorted(((segment.y0 + segment.y1) / 2, *sorted((segment.x0, segment.x1)))
                        for segment in segments
                        if all(math.isfinite(value) for value in
                               (segment.x0, segment.y0, segment.x1, segment.y1))
                        and abs(segment.y1 - segment.y0) <= GEOMETRY_TOLERANCE)
    horizontal_ys = [item[0] for item in horizontal]
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
        # 표 테두리는 각주 구분선이 아니다. 바로 위에 같은 폭의 가로선이 쌓여 있으면
        # (좌우 테두리가 없는 표의 행 괘선) 거부한다.
        low = bisect_right(horizontal_ys, y + GEOMETRY_TOLERANCE)
        high = bisect_right(horizontal_ys, y + STACKED_RULE_DISTANCE)
        if not _spend(budget, high - low, warnings):
            return False
        if any(abs(other_left - left) <= GEOMETRY_TOLERANCE and abs(other_right - right) <= GEOMETRY_TOLERANCE
               for _y, other_left, other_right in horizontal[low:high]):
            continue
        # 끝점에 세로선이 붙어도 표 테두리다.
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


class _Marker:
    """각주 표지 후보. 숫자와 닫는 괄호가 따로 그려졌으면 여러 조각이고, 첫 조각 자리에 참조를 단다."""

    def __init__(self, parts):
        first, last = parts[0], parts[-1]
        self.x, self.y, self.size, self.order = first.x, first.y, first.size, first.order
        self.width = last.x + last.width - first.x
        self.text = "".join(part.text for part in parts)
        self.extra_orders = {part.order for part in parts[1:]}


def _touching(left, right, size):
    gap = right.x - left.x - left.width
    return (right.order == left.order + 1
            and abs(right.size - size) <= 0.05 * size
            and abs(right.y - left.y) <= 0.1 * size
            and -0.1 * size <= gap <= 0.3 * size)


def _marker_candidates(small):
    """작은 조각 중 각주 표지 `n)` 후보. 한 조각이거나, 내용 순서로 이어지고
    같은 기준선·크기에서 맞닿은 숫자 조각과 괄호 조각(최대 4조각)을 합친다.
    앞에 맞닿은 `(`·숫자가 있으면(`(1)`, `12)` 의 뒷부분) 시작점으로 쓰지 않는다."""
    ordered = sorted(small, key=lambda frag: frag.order)
    markers, used = [], set()
    for index, frag in enumerate(ordered):
        match = _MARKER.match(frag.text)
        if match:
            markers.append((_Marker([frag]), match))
            continue
        if frag.order in used or not _DIGITS.match(frag.text):
            continue
        previous = ordered[index - 1] if index else None
        if (previous is not None and _touching(previous, frag, frag.size)
                and (previous.text.strip() == "(" or _DIGITS.match(previous.text))):
            continue
        parts = [frag]
        for following in ordered[index + 1:index + 4]:
            if not _touching(parts[-1], following, frag.size):
                break
            parts.append(following)
            match = _MARKER.match("".join(part.text for part in parts))
            if match:
                markers.append((_Marker(parts), match))
                used.update(part.order for part in parts)
                break
    return markers


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
                                note_ref=run[4] if len(run) > 4 and (len(run) < 6 or run[5] != "comment") else 0,
                                note_reference_type=(run[5] if len(run) > 5 else "footnote") if len(run) > 4 and run[4] else "",
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
    markers = _marker_candidates([frag for frag in horizontal if 0 < frag.size <= body * 0.8])
    if len(markers) > MAX_NOTE_MARKERS:
        if warnings is not None:
            warnings.append("WARN: PDF 각주 표지 수 한도(1000) 초과 — 각주 복원 생략")
        return empty
    # 각주 정의는 그것을 다는 본문보다 작게 짠다. 쪽의 최빈 크기(제목이 많으면
    # 본문보다 클 수 있다)뿐 아니라 정의 글자보다 뚜렷이 큰 글자도 표지의 바탕이다.
    host_size = min(body * 0.95, min(line.size for _index, line, _match in definitions) * 1.1)
    hosts = sorted((frag for frag in horizontal if frag.size >= host_size), key=lambda frag: frag.y)
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
        # 글자마다 조각인 줄은 앞 조각들을 이어 붙여 표지를 찾는다.
        prefix = ""
        for position, segment in enumerate(line.segments[:4]):
            prefix += segment.text
            if _MARKER.match(prefix):
                if position + 1 < len(line.segments):
                    left_margins.append(line.segments[position + 1].x0)
                break
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
        marker = references[match.group(1)][0]
        reference_numbers[marker.order] = number
        consumed.update(marker.extra_orders)
        number += 1
    return notes, consumed, reference_numbers, number


_ENDNOTE_HEADING = re.compile(r"^(?:미\s*주|end\s*notes|notes)$", re.IGNORECASE)
_ENDNOTE_DEFINITION = re.compile(r"^\s*(\d{1,3})[.)]\s+\S")
_ENDNOTE_MARKER = re.compile(r"^\s*(\d{1,3})[.)]?\s*$")
MAX_ENDNOTE_LINES = 200000
MAX_ENDNOTE_CHARACTERS = 4 * 1024 * 1024


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
        nearby = hosts[bisect_left(ys, marker.y - max_size):bisect_right(ys, marker.y)]
        if not _spend(budget, len(nearby), warnings):
            return []
        valid = [h for h in nearby if marker.size <= h.size * .8
                 and .15 * h.size <= marker.y - h.y <= max(.30 * h.size, h.size - marker.size) + 1e-6
                 and -.1 * h.size <= marker.x - h.x - h.width <= .5 * h.size]
        # 커닝으로 나뉜 마지막 글자와 문장부호는 같은 기준선의 한 호스트다.
        if (valid and max(h.y for h in valid) - min(h.y for h in valid) <= .1
                and max(h.size for h in valid) - min(h.size for h in valid) <= .1):
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
    if sum(len(line.text) for _d, line in entries) > MAX_ENDNOTE_CHARACTERS:
        if warnings is not None:
            warnings.append("WARN: PDF 미주 문자 수 한도 초과 — 미주 구역 복원 생략")
        return first_number
    headings = [i for i, (_d, line) in enumerate(entries)
                if _ENDNOTE_HEADING.fullmatch(line.text.strip())]
    if len(headings) != 1:
        return first_number
    chapter_number = _detect_chapter_endnotes(drafts, entries, headings[0], dropped, first_number, warnings)
    if chapter_number != first_number:
        return chapter_number
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


def _heading_key(text):
    """목차·본문·미주 제목의 대소문자와 조판 공백만 정규화한다."""
    return "".join(c for c in text.casefold() if not c.isspace())


def _detect_chapter_endnotes(drafts, entries, begin, dropped, first_number, warnings):
    """목차와 본문 제목으로 독립 확인된 장마다 번호를 재시작한다.

    단순 끝 구역과 별개로, 목차의 Notes 다음 제목이 실제 구역 끝을
    증명하고 모든 장의 연속 정의와 위첨자가 일대일인 경우만 이동한다.
    다른 크기 문단도 본문 열에 있으면 포함하며 지면 여백은 보존한다.
    """
    heading_draft, heading = entries[begin]
    # Contents와 Notes 사이의 목차에서 페이지 번호가 붙은 제목만 채택한다.
    contents = [i for i, (_d, line) in enumerate(entries[:begin])
                if _heading_key(line.text) in ("contents", "tableofcontents", "목차")]
    if len(contents) != 1:
        return first_number
    toc = []
    for _d, line in entries[contents[0] + 1:begin]:
        parts = line.text.rsplit(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9]+|[ivxlcdm]+", parts[1], re.I):
            toc.append((_heading_key(parts[0]), line))
    notes_key = _heading_key(heading.text)
    positions = [i for i, (key, _line) in enumerate(toc) if key == notes_key]
    if len(positions) != 1 or positions[0] + 1 >= len(toc):
        return first_number
    toc = toc[:positions[0] + 2]
    stop_key = toc[-1][0]
    stops = [i for i in range(begin + 1, len(entries))
             if _heading_key(entries[i][1].text) == stop_key
             and abs(entries[i][1].size - heading.size) <= .1]
    if len(stops) != 1:
        return first_number
    end = stops[0]
    section = entries[begin + 1:end]
    section_pages = {d.page_number for d, _line in section}
    if any(d.ordered or d.rotation for d in drafts if d.page_number in section_pages):
        return first_number
    toc_keys = {key for key, _line in toc[:-2]}
    # 실물에서 미주 소제목과 본문 장 제목은 같은 문자열이며 크기가 다르다.
    chapter_lines = [(i, d, line, _heading_key(line.text))
                     for i, (d, line) in enumerate(section)
                     if _heading_key(line.text) in toc_keys]
    if len(chapter_lines) < 2:
        return first_number
    keys = [item[3] for item in chapter_lines]
    if len(set(keys)) != len(keys):
        return first_number
    if len(keys) > MAX_NOTE_MARKERS:
        return first_number
    candidates = {}
    for i, (d, line) in enumerate(entries[:begin]):
        candidates.setdefault(_heading_key(line.text), []).append((i, d, line))
    body_headings = {}
    for key, (_start, _d, chapter, _key) in zip(keys, chapter_lines):
        found = [item for item in candidates.get(key, []) if item[2].size > chapter.size]
        if len(found) != 1:
            return first_number
        body_headings[key] = found[0]
    if [body_headings[k][0] for k in keys] != sorted(body_headings[k][0] for k in keys):
        return first_number
    marker_count = sum(len(getattr(d, "note_markers", [])) for d in drafts)
    if marker_count > MAX_NOTE_MARKERS:
        return first_number
    if not _spend([MAX_NOTE_GEOMETRY_CHECKS],
                  sum(len(line.fragment_orders) for _d, line in entries[:begin]), warnings):
        return first_number
    source_lines = {(d.page_number, order): (i, line)
                    for i, (d, line) in enumerate(entries[:begin])
                    for order in line.fragment_orders}
    refs = []
    for d in drafts:
        for order, label in getattr(d, "note_markers", []):
            source = source_lines.get((d.page_number, order))
            if source:
                refs.append((source[0], source[1], order, label))
    planned, updates = [], {}
    for chapter_index, (start, _d, chapter, key) in enumerate(chapter_lines):
        stop = chapter_lines[chapter_index + 1][0] if chapter_index + 1 < len(chapter_lines) else len(section)
        body_start = body_headings[key][0]
        body_stop = (body_headings[keys[chapter_index + 1]][0]
                     if chapter_index + 1 < len(keys) else begin)
        references = {}
        for i, line, order, label in refs:
            if body_start < i < body_stop:
                references.setdefault(label, []).append((line, order))
        definitions = []
        body_bottoms = {}
        body_right = max((line.right for _d, line in section
                          if abs(line.size - chapter.size) <= .1), default=chapter.right)
        for d, line in section[start + 1:stop]:
            if abs(line.size - chapter.size) <= .1:
                body_bottoms[d.page_number] = min(body_bottoms.get(d.page_number, line.y), line.y)
        for index in range(start + 1, stop):
            d, line = section[index]
            if (not all(math.isfinite(v) for v in (line.size, line.y, line.left, line.right))
                    or line.direction != "ltr"):
                return first_number
            if (abs(line.size - chapter.size) > .1
                    and (line.right < chapter.left
                         or line.left < chapter.left - GEOMETRY_TOLERANCE
                         or line.left > body_right + GEOMETRY_TOLERANCE
                         or (_heading_key(re.sub(r"\d+", "", line.text)) in ("", notes_key)
                             and line.y < body_bottoms.get(d.page_number, d.bounds[0])))):
                continue
            at_bottom = line.y <= d.bounds[0] + HEADER_FOOTER_ZONE
            if (abs(line.size - chapter.size) > .1
                    and (at_bottom or line.y >= d.bounds[1] - HEADER_FOOTER_ZONE)):
                # 반복 머리말·꼬리말은 detect_running의 dropped로 이미 제외됐다.
                # 남은 여백 줄도 같은 페이지의 인접 줄과 문단이 이어지면 포함한다.
                # 불확실한 줄만 건너뛰면 미주가 잘리므로 구역 전체를 보류한다.
                neighbors = section[max(start + 1, index - 1):index]
                neighbors += section[index + 1:min(stop, index + 2)]
                if not any(other_draft is d
                           and abs(other.size - line.size) <= .1
                           and abs(other.left - line.left) <= GEOMETRY_TOLERANCE
                           and 0 < abs(other.y - line.y) <= line.size * 2
                           for other_draft, other in neighbors):
                    if at_bottom and definitions:
                        previous_draft, previous = definitions[-1][1][-1]
                        # 같은 쪽에서 미주 문단과 분리된 바닥글은 본문에 남긴다.
                        # 앞선 미주가 다른 쪽에 있으면 분리 여부를 확인할 수 없다.
                        if previous_draft is d and previous.y - line.y > line.size * 2:
                            continue
                    return first_number
            match = _ENDNOTE_DEFINITION.match(line.text)
            if match:
                label = match.group(1)
                if int(label) != len(definitions) + 1 or len(references.get(label, [])) != 1:
                    return first_number
                definitions.append((label, [(d, line)]))
            else:
                if not definitions:
                    return first_number
                previous_draft, previous = definitions[-1][1][-1]
                # 이어지는 문단의 들여쓰기는 허용하되 원래 정의의 수평 범위를 벗어나지 않는다.
                first = definitions[-1][1][0][1]
                if (line.left < chapter.left - GEOMETRY_TOLERANCE
                        or line.left > first.right
                        or (d is previous_draft and not 0 < previous.y - line.y <= line.size * 2)):
                    return first_number
                definitions[-1][1].append((d, line))
        if not definitions or set(references) != {label for label, _lines in definitions}:
            return first_number
        for label, lines in definitions:
            number = first_number + len(planned)
            source, order = references[label][0]
            runs = _endnote_reference_runs(source, order, number, updates.get(id(source)))
            if runs is None:
                return first_number
            updates[id(source)] = runs
            paragraphs = []
            for offset, (d, line) in enumerate(lines):
                paragraph = _paragraph(line, d.page_number)
                if offset == 0:
                    prefix = re.match(r"^\s*\d{1,3}[.)]\s*", paragraph.text).end()
                    for run in paragraph.runs:
                        removed = min(prefix, len(run.text))
                        run.text = run.text[removed:]
                        prefix -= removed
                    paragraph.runs = [run for run in paragraph.runs if run.text]
                paragraphs.append(paragraph)
            planned.append((source, lines, Footnote(type="endnote", paragraphs=paragraphs, number=number)))
            if len(planned) > MAX_NOTE_MARKERS:
                return first_number
    for source, lines, note in planned:
        source.runs = updates[id(source)]
        lines[0][0].notes.append(note)
        for d, line in lines:
            dropped.setdefault(d.page_number, set()).add(id(line))
    # 도입문이 있는 Notes 제목은 도입문과 함께 본문에 남긴다.
    return first_number + len(planned)
