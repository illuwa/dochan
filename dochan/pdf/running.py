"""PDF 페이지 가장자리의 반복 머리글과 바닥글 검출."""
import heapq
import math
import re
import statistics
import unicodedata
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from ..model.header_footer import HeaderFooter

EDGE_FRACTION_RUNNING = 0.12
_WHITESPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")
_PAGE_NUMBER = re.compile(
    r"(?:[-–—]\s*)?(?:\d{1,4}|[(\[]\d{1,4}[)\]]|"
    r"\d{1,4}\s*/\s*\d{1,4}|"
    r"(?:page|p\.?)\s*\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?|"
    r"\d{1,4}\s*(?:쪽|페이지|页))(?:\s*[-–—])?",
    re.IGNORECASE,
)
_ARTICLE_HEADING = re.compile(r"제\s*\d+\s*조(?:\s*\([^)]*\))?")


def normalize_text(text: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def is_page_number_like(text: str) -> bool:
    text = normalize_text(text)
    return bool(_PAGE_NUMBER.fullmatch(text))


def line_key(zone: str, line) -> Tuple[str, str, bool]:
    text = normalize_text(line.text)
    is_page = is_page_number_like(text)
    if is_page:
        text = _DIGITS.sub("#", text)
    return zone, text, is_page


def _table_like(line) -> bool:
    segments = getattr(line, "segments", ())
    if len(segments) < 3:
        return False
    gaps = 0
    for previous, following in zip(segments, segments[1:]):
        width = max(previous.space_width, following.space_width)
        minimum = 2 * width if width > 0 else line.size
        if following.x0 - previous.x1 >= minimum:
            gaps += 1
    return gaps >= 2


def edge_block(lines, bounds, zone: str) -> list:
    bottom, top = bounds
    span = (top - bottom) * EDGE_FRACTION_RUNNING
    if zone == "header":
        candidates = heapq.nlargest(
            3, (line for line in lines if line.direction == "ltr"
                and top - span <= line.y <= top), key=lambda line: line.y)
    else:
        candidates = heapq.nsmallest(
            3, (line for line in lines if line.direction == "ltr"
                and bottom <= line.y <= bottom + span), key=lambda line: line.y)
    block = []
    for line in candidates:
        if block and abs(line.y - block[-1].y) > 1.5 * block[-1].size:
            break
        block.append(line)
    if block:
        block_ids = {id(line) for line in block}
        if zone == "header":
            edge_y = min(line.y for line in block)
            remainder = [line for line in lines if line.direction == "ltr"
                         and id(line) not in block_ids and line.y < edge_y]
        else:
            edge_y = max(line.y for line in block)
            remainder = [line for line in lines if line.direction == "ltr"
                         and id(line) not in block_ids and line.y > edge_y]
        if remainder:
            if zone == "header":
                gap = edge_y - max(line.y for line in remainder)
            else:
                gap = min(line.y for line in remainder) - edge_y
            if gap < 2.0 * max(line.size for line in block):
                return []
    return block


def detect_running(pages) -> Tuple[Dict[int, Set[int]], List[Tuple[int, HeaderFooter]]]:
    """페이지별 제거할 줄 객체와 첫 출현 페이지의 머리글/바닥글을 돌려준다."""
    drops: Dict[int, Set[int]] = {page.page_number: set() for page in pages}
    occurrences = defaultdict(list)
    text_pages = sum(bool(any(group for group in page.groups)) for page in pages)
    if text_pages < 2:
        return drops, []
    for page in pages:
        if page.rotation != 0:
            continue
        lines = [line for group in page.groups for line in group
                 if line.text and line.direction == "ltr"]
        for zone in ("header", "footer"):
            for line in edge_block(lines, page.bounds, zone):
                if (_ARTICLE_HEADING.fullmatch(normalize_text(line.text))
                        or _table_like(line)):
                    continue
                occurrences[line_key(zone, line)].append((page.page_number, line))

    threshold = max(2, math.ceil(0.3 * text_pages))
    first_lines = defaultdict(list)
    for key, found in occurrences.items():
        median_size = statistics.median(line.size if math.isfinite(line.size) else 0.0
                                        for _, line in found)
        found = [(number, line) for number, line in found
                 if abs((line.size if math.isfinite(line.size) else 0.0)
                        - median_size) <= 1.0]
        if len({number for number, _ in found}) < threshold:
            continue
        if key[2]:
            numbered = [(number, line, _DIGITS.search(line.text)) for number, line in found]
            found = [(number, line) for number, line, match in numbered if match]
            if len({number for number, _ in found}) < threshold:
                continue
            numbers = [int(match.group()) for _, _, match in numbered if match]
            if numbers != sorted(numbers):
                continue
        for number, line in found:
            drops[number].add(id(line))
        first_page, first_line = min(found, key=lambda item: item[0])
        first_lines[(first_page, key[0])].append(first_line)
    emitted = []
    for (first_page, zone), lines in first_lines.items():
        provenance = Provenance(source_format="pdf", page=first_page)
        paragraphs = [Paragraph(runs=[TextRun(text=line.text, provenance=provenance)],
                                provenance=provenance)
                      for line in sorted(lines, key=lambda line: -line.y)]
        emitted.append((first_page, HeaderFooter(type=zone, paragraphs=paragraphs)))
    emitted.sort(key=lambda item: (item[0], item[1].type != "header"))
    return drops, emitted
