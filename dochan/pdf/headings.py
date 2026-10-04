"""기존 PDF 크기 제목을 보존하며 공용 강조 절 제목 규칙을 적용한다."""
from dataclasses import replace
from bisect import bisect_left, bisect_right
import math
import re
from types import SimpleNamespace

from ..model.document import Paragraph
from ..utils.heading_font import (MAX_FONT_HEADING_PARAGRAPHS, _context_exclusions,
                                 body_font_size, emphasized_heading_level)
from .pagination import _inherited

GEOMETRY_TOLERANCE = 1.5  # PDF 표 경계와 같은 좌표 오차 허용치(pt).
_DOT_LEADER = re.compile(r'\.{4,}\s*\d+\s*$')


def horizontal_bounds(pdf, page):
    box = _inherited(pdf, page, 'MediaBox')
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        left, right = sorted(float(pdf.resolve(box[i])) for i in (0, 2))
        if all(math.isfinite(v) for v in (left, right)) and right > left:
            return left, right
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def sized_runs(paragraph, lines, sizes):
    """조립된 런의 문자·링크·주석을 유지하고 조각 경계의 실제 크기를 복원한다."""
    spans = []
    offset = 0
    for line in lines:
        text = ''.join(run[0] for run in line.runs)
        cursor = 0
        leading = len(text) - len(text.lstrip())
        length = len(text.strip())
        for order, segment in zip(line.fragment_orders, line.segments):
            part = ''.join(run[0] for run in segment.runs)
            end = text.find(part, cursor)
            if end < 0:
                return paragraph.runs  # 손상 메타데이터로 문자·서식을 바꾸지 않는다.
            end += len(part)
            start_at = max(cursor - leading, 0)
            end_at = min(end - leading, length)
            if end_at > start_at:
                _append_size_span(spans, offset + start_at, offset + end_at, sizes.get(order, line.size))
            cursor = end
        offset += length
        if line is not lines[-1]:
            # 병합 줄은 공백 없이 이어질 수도 있다. 최종 문자열에서만 구분자를 확인한다.
            if paragraph.text[offset:offset + 1].isspace():
                _append_size_span(spans, offset, offset + 1, line.size)
                offset += 1
    if offset != len(paragraph.text):
        return paragraph.runs
    result = []
    position = 0
    at = 0
    for run in paragraph.runs:
        start = position
        end = position + len(run.text)
        while at < len(spans) and spans[at][1] <= position:
            at += 1
        while position < end:
            if at >= len(spans) or spans[at][0] > position:
                return paragraph.runs
            stop = min(end, spans[at][1])
            piece = replace(run, text=run.text[position - start:stop - start],
                            font_size_pt=spans[at][2])
            if result and replace(piece, text=result[-1].text) == result[-1]:
                result[-1].text += piece.text
            else:
                result.append(piece)
            position = stop
            if position >= spans[at][1]:
                at += 1
    return result


def _append_size_span(spans, start, end, size):
    # 글자별 Tj 수천 개도 같은 크기 구간은 하나로 묶는다. 누적 문자열 복사를 피한다.
    if spans and spans[-1][1] == start and spans[-1][2] == size:
        spans[-1] = (spans[-1][0], end, size)
    else:
        spans.append((start, end, size))


def candidate_geometry(block, bounds, rotation, median, table_tops=(), baselines=()):
    single = len(block.lines) == 1 and block.lines[0].direction == 'ltr' and rotation == 0
    line = block.lines[0]
    centered = bool(single and bounds and abs(line.left + line.right - sum(bounds)) <= 2 * GEOMETRY_TOLERANCE)
    # PDF에는 문단 모양 ID가 없다. 같은 들여쓰기·크기·정렬의 값 목록만 묶는다.
    shape = (round(line.left / GEOMETRY_TOLERANCE), round(line.size, 1), centered)
    caption = False
    if centered:
        index = bisect_left(table_tops, (line.y,)) - 1
        if index >= 0:
            top, left, right = table_tops[index]
            # 표의 그리기 순서는 본문보다 뒤일 수 있다. 가까운 아래 표와 사이에
            # 본문 줄이 없는 경우만 인접으로 본다(기존 줄 병합 거리 1.8배).
            caption = (0 < line.y - top <= 1.8 * line.size
                       and left <= (line.left + line.right) / 2 <= right
                       and bisect_left(baselines, line.y) == bisect_right(baselines, top))
    return single, centered, shape, median, caption


def finalize_emphasized_headings(doc):
    paragraphs = []
    for section in doc.sections:
        for para in section.elements:
            if isinstance(para, Paragraph) and hasattr(para, '_pdf_heading'):
                paragraphs.append(para)
                if len(paragraphs) > MAX_FONT_HEADING_PARAGRAPHS:
                    break
        if len(paragraphs) > MAX_FONT_HEADING_PARAGRAPHS:
            break
    try:
        if len(paragraphs) > MAX_FONT_HEADING_PARAGRAPHS:
            doc.errors.append('WARN: PDF 강조 제목 문단 한도 초과 — 기존 크기 제목만 유지')
            return 0
        body = body_font_size(paragraphs, doc=doc)
        if not body:
            return 0
        shapes = {}
        proxy_sections = []
        proxies = {}
        for section in doc.sections:
            elements = []
            for element in section.elements:
                if isinstance(element, Paragraph) and hasattr(element, '_pdf_heading'):
                    _single, centered, shape, _median, _caption = element._pdf_heading
                    if shape not in shapes:
                        shapes[shape] = len(shapes)
                    proxy = SimpleNamespace(runs=element.runs, heading_level=element.heading_level,
                                            para_shape_id=shapes[shape])
                    proxies[id(element)] = proxy
                    elements.append(proxy)
                else:
                    elements.append(element)
            proxy_sections.append(SimpleNamespace(elements=elements))
        context = SimpleNamespace(sections=proxy_sections, para_shapes=[
            SimpleNamespace(align=3 if shape[2] else 0) for shape in shapes])
        captions, keys = _context_exclusions(context)
        for para in paragraphs:
            # 기존 H1/H2는 중앙값·문단 길이·기존 출력 계약 그대로 보존한다.
            if para.heading_level or not para._pdf_heading[0]:
                continue
            proxy = proxies[id(para)]
            # 스타일이 없는 PDF의 점선 차례 항목은 실측한 문자 모양으로 제외한다.
            text = para.text.strip()
            bracket = {'<': '>', '〈': '〉', '[': ']', '【': '】'}
            geometric_caption = (para._pdf_heading[4] and text[:1] in bracket
                                 and text.endswith(bracket[text[0]]))
            if (id(proxy) not in captions and id(proxy) not in keys
                    and not geometric_caption and not _DOT_LEADER.search(text)):
                para.heading_level = emphasized_heading_level(para.runs, body)
        return body
    finally:
        for section in doc.sections:
            for para in section.elements:
                if isinstance(para, Paragraph) and hasattr(para, '_pdf_heading'):
                    del para._pdf_heading
