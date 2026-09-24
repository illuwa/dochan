"""PDF 페이지 가장자리의 반복 머리글과 바닥글 검출."""
import math
import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from ..model.header_footer import HeaderFooter

EDGE_FRACTION_RUNNING = 0.12
_WHITESPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")
_DATE = re.compile(r"^\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?$")
_PAGE_CHARS = set("-–—·./()[]页쪽페이지PageofOF")


def normalize_text(text: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def is_page_number_like(text: str) -> bool:
    text = normalize_text(text)
    if not _DIGITS.search(text) or _DATE.fullmatch(text):
        return False
    remaining = [ch for ch in text if not ch.isdigit() and not ch.isspace()
                 and ch not in _PAGE_CHARS]
    return len(remaining) < 3


def line_key(zone: str, line) -> Tuple[str, str, float]:
    text = normalize_text(line.text)
    if is_page_number_like(text):
        text = _DIGITS.sub("#", text)
    return zone, text, round(line.size * 2) / 2


def edge_block(lines, bounds, zone: str) -> list:
    bottom, top = bounds
    span = (top - bottom) * EDGE_FRACTION_RUNNING
    if zone == "header":
        candidates = sorted((line for line in lines if line.direction == "ltr"
                             and top - span <= line.y <= top), key=lambda line: -line.y)
    else:
        candidates = sorted((line for line in lines if line.direction == "ltr"
                             and bottom <= line.y <= bottom + span), key=lambda line: line.y)
    block = []
    for line in candidates:
        if block and abs(line.y - block[-1].y) > 1.5 * block[-1].size:
            break
        block.append(line)
        if len(block) == 3:
            break
    return block


def detect_running(pages) -> Tuple[Dict[int, Set[int]], List[Tuple[int, HeaderFooter]]]:
    """페이지별 제거할 줄 객체와 첫 출현 페이지의 머리글/바닥글을 돌려준다."""
    drops: Dict[int, Set[int]] = {page.page_number: set() for page in pages}
    occurrences = defaultdict(list)
    text_pages = sum(bool(any(group for group in page.groups)) for page in pages)
    if text_pages < 2:
        return drops, []
    for page in pages:
        lines = [line for group in page.groups for line in group
                 if line.text and line.direction == "ltr"]
        for zone in ("header", "footer"):
            for line in edge_block(lines, page.bounds, zone):
                occurrences[line_key(zone, line)].append((page.page_number, line))

    threshold = max(2, math.ceil(0.3 * text_pages))
    emitted = []
    for key, found in occurrences.items():
        if len({number for number, _ in found}) < threshold:
            continue
        if is_page_number_like(found[0][1].text):
            numbers = [int(_DIGITS.search(line.text).group()) for _, line in found]
            if numbers != sorted(numbers):
                continue
        for number, line in found:
            drops[number].add(id(line))
        first_page, first_line = min(found, key=lambda item: item[0])
        provenance = Provenance(source_format="pdf", page=first_page)
        paragraph = Paragraph(runs=[TextRun(text=first_line.text, provenance=provenance)],
                              provenance=provenance)
        emitted.append((first_page, HeaderFooter(type=key[0], paragraphs=[paragraph])))
    emitted.sort(key=lambda item: (item[0], item[1].type != "header"))
    return drops, emitted
