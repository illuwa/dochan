"""
output/markdown.py — Markdown 변환
AI/LLM에 최적화된 Markdown 출력
"""

from ..model.document import Document, Paragraph, TextRun
from ..model.table import Table, Cell
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote


def to_markdown(doc: Document) -> str:
    """Document → Markdown 문자열 변환"""
    parts = []

    for section in doc.sections:
        for elem in section.elements:
            md = _element_to_md(elem)
            if md:
                parts.append(md)

    return '\n\n'.join(parts)


def _element_to_md(elem) -> str:
    if isinstance(elem, Paragraph):
        return _paragraph_to_md(elem)
    elif isinstance(elem, Table):
        return _table_to_md(elem)
    elif isinstance(elem, Equation):
        return _equation_to_md(elem)
    elif isinstance(elem, Image):
        return _image_to_md(elem)
    elif isinstance(elem, HeaderFooter):
        return _header_footer_to_md(elem)
    elif isinstance(elem, Footnote):
        return _footnote_to_md(elem)
    return ""


def _paragraph_to_md(para: Paragraph) -> str:
    text = _runs_to_md(para.runs)
    if not text.strip():
        return ""

    if para.heading_level > 0:
        prefix = '#' * min(para.heading_level, 6)
        return f"{prefix} {text}"

    return text


def _runs_to_md(runs: list) -> str:
    parts = []
    for run in runs:
        text = run.text
        if not text:
            continue

        # 서식 적용
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"

        if run.strikeout:
            text = f"~~{text}~~"
        if run.superscript:
            text = f"<sup>{text}</sup>"
        if run.subscript:
            text = f"<sub>{text}</sub>"

        parts.append(text)

    return ''.join(parts)


def _table_to_md(table: Table) -> str:
    if not table.rows:
        return ""

    lines = []
    col_count = table.col_count

    for row_idx, row in enumerate(table.rows):
        cells_text = []
        for cell in row:
            if cell.is_merged_away:
                cells_text.append("")
            else:
                cells_text.append(_cell_text(cell))

        # 열 수 맞추기
        while len(cells_text) < col_count:
            cells_text.append("")

        line = "| " + " | ".join(cells_text) + " |"
        lines.append(line)

        # 첫 행 후 구분선
        if row_idx == 0:
            sep = "| " + " | ".join(["---"] * col_count) + " |"
            lines.append(sep)

    return '\n'.join(lines)


def _cell_text(cell: Cell) -> str:
    texts = []
    for p in cell.paragraphs:
        if hasattr(p, 'text'):
            text = p.text.replace('\n', ' ').replace('\r', '')
            text = text.replace('|', '\\|')
            texts.append(text)
        elif isinstance(p, Image) and p.ocr_text:
            text = p.ocr_text.replace('\n', ' ').replace('\r', '').replace('|', '\\|')
            texts.append(text)
    return ' '.join(texts)


def _equation_to_md(eq: Equation) -> str:
    latex = eq.latex
    if latex:
        return f"$$ {latex} $$"
    elif eq.script:
        return f"$$ {eq.script} $$"
    return ""


def _image_to_md(img: Image) -> str:
    parts = []
    if img.filename:
        parts.append(f"![이미지]({img.filename})")
    else:
        parts.append("![이미지](image)")

    # OCR 텍스트가 있으면 이미지 아래에 추가
    if img.ocr_text:
        parts.append(f"\n{img.ocr_text}")

    return '\n'.join(parts)


def _header_footer_to_md(hf: HeaderFooter) -> str:
    text = hf.text.strip()
    if text:
        return f"<!-- {hf.type}: {text} -->"
    return ""


def _footnote_to_md(fn: Footnote) -> str:
    text = fn.text.strip()
    if text:
        label = "각주" if fn.type == "footnote" else "미주"
        return f"[^{label}]: {text}"
    return ""
