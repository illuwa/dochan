"""
output/plain_text.py — 플레인 텍스트 출력
"""

from ..model.document import Document, Paragraph
from ..model.table import Table
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote


def to_plain_text(doc: Document) -> str:
    """Document → 플레인 텍스트"""
    parts = []

    for section in doc.sections:
        for elem in section.elements:
            text = _element_to_text(elem)
            if text:
                parts.append(text)

    return '\n\n'.join(parts)


def _element_to_text(elem) -> str:
    if isinstance(elem, Paragraph):
        return _paragraph_to_text(elem)
    elif isinstance(elem, Table):
        return _with_caption(_table_to_text(elem), elem)
    elif isinstance(elem, Equation):
        return f"[수식: {elem.latex or elem.script}]" if (elem.latex or elem.script) else ""
    elif isinstance(elem, Image):
        if elem.ocr_text:
            return _with_caption(elem.ocr_text, elem)
        body = f"[이미지: {elem.filename}]" if elem.filename else "[이미지]"
        return _with_caption(body, elem)
    elif isinstance(elem, (HeaderFooter, Footnote)):
        return elem.text.strip()
    return ""


def _paragraph_to_text(para: Paragraph) -> str:
    """문단 텍스트. 하이퍼링크는 OOXML 리더의 관행대로 '텍스트 <URL>' 로 덧붙인다."""
    runs = para.runs
    parts = []
    index = 0
    total = len(runs)
    while index < total:
        link = getattr(runs[index], 'link', '')
        if link:
            end = index
            inner = []
            while end < total and getattr(runs[end], 'link', '') == link:
                inner.append(runs[end].text)
                end += 1
            joined = ''.join(inner)
            parts.append(f"{joined} <{link}>" if joined else f"<{link}>")
            index = end
            continue
        parts.append(runs[index].text)
        index += 1
    return ''.join(parts).strip()


def _with_caption(rendered: str, elem) -> str:
    caption = getattr(elem, 'caption_text', '')
    if not caption or not caption.strip():
        return rendered
    text = caption.strip()
    side = (getattr(elem, 'caption_side', '') or 'BOTTOM').upper()
    if side in ('TOP', 'LEFT'):
        return f"{text}\n{rendered}" if rendered else text
    return f"{rendered}\n{text}" if rendered else text


def _table_to_text(table: Table) -> str:
    lines = []
    for row in table.rows:
        # 행 전체가 병합에 가려졌으면 탭만 남은 빈 줄이 되므로 통째로 건너뛴다.
        if row and all(cell.is_merged_away for cell in row):
            continue
        # 가려진 셀도 빈 칸으로 남겨야 열이 밀리지 않는다.
        cells = ['' if cell.is_merged_away else cell.text.replace('\n', ' ') for cell in row]
        if cells:
            lines.append('\t'.join(cells))
    return '\n'.join(lines)
