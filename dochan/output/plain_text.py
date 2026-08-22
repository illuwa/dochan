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
        return elem.text.strip()
    elif isinstance(elem, Table):
        return _table_to_text(elem)
    elif isinstance(elem, Equation):
        return f"[수식: {elem.latex or elem.script}]" if (elem.latex or elem.script) else ""
    elif isinstance(elem, Image):
        if elem.ocr_text:
            return elem.ocr_text
        return f"[이미지: {elem.filename}]" if elem.filename else "[이미지]"
    elif isinstance(elem, HeaderFooter):
        return elem.text.strip()
    elif isinstance(elem, Footnote):
        parts = [_element_to_text(item) for item in elem.paragraphs]
        return '\n'.join(part for part in parts if part).strip()
    return ""


def _table_to_text(table: Table) -> str:
    lines = []
    for row in table.rows:
        cells = []
        for cell in row:
            if cell.is_merged_away:
                continue
            parts = [_element_to_text(item) for item in cell.paragraphs]
            cells.append(' '.join(part for part in parts if part).replace('\n', ' '))
        if cells:
            lines.append('\t'.join(cells))
    return '\n'.join(lines)
