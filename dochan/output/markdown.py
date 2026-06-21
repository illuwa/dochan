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
    include_sheet_headings = _should_include_sheet_headings(doc)
    include_slide_headings = _should_include_slide_headings(doc)

    for section in doc.sections:
        elements = list(section.elements)
        if include_sheet_headings:
            while elements and _is_sheet_preamble(elements[0]):
                md = _element_to_md(elements.pop(0))
                if md:
                    parts.append(md)
            sheet_heading = _sheet_heading(section)
            if sheet_heading:
                parts.append(sheet_heading)
        elif include_slide_headings:
            slide_heading = _slide_heading(section)
            if slide_heading:
                parts.append(slide_heading)
        for elem in elements:
            md = _element_to_md(elem)
            if md:
                parts.append(md)

    return '\n\n'.join(parts)


def _should_include_sheet_headings(doc: Document) -> bool:
    if doc.source_format not in {"xlsx", "xls"}:
        return False
    return any(_is_meaningful_sheet_name(_sheet_name(section)) for section in doc.sections)


def _sheet_heading(section) -> str:
    name = _sheet_name(section)
    return f"## {name}" if _is_meaningful_sheet_name(name) else ""


def _sheet_name(section) -> str:
    provenance = getattr(section, "provenance", None)
    return str(getattr(provenance, "sheet", "") or "").strip()


def _is_meaningful_sheet_name(name: str) -> bool:
    normalized = name.strip().lower()
    compact = normalized.replace(" ", "")
    return bool(normalized) and not (
        compact == "sheet" or (compact.startswith("sheet") and compact[5:].isdigit())
    )


def _is_sheet_preamble(elem) -> bool:
    provenance = getattr(elem, "provenance", None)
    path = str(getattr(provenance, "path", "") or "")
    return path == "docProps/core.xml" or path == "xl/workbook.xml"


def _should_include_slide_headings(doc: Document) -> bool:
    if doc.source_format not in {"pptx", "ppt"} or len(doc.sections) <= 1:
        return False
    return any(_slide_number(section) for section in doc.sections)


def _slide_heading(section) -> str:
    slide = _slide_number(section)
    return f"## Slide {slide}" if slide else ""


def _slide_number(section) -> int:
    provenance = getattr(section, "provenance", None)
    try:
        return int(getattr(provenance, "slide", 0) or 0)
    except (TypeError, ValueError):
        return 0


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

        if run.underline:
            text = f"<u>{text}</u>"
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
    body = []
    for item in fn.paragraphs:
        if isinstance(item, Table):
            rendered = _table_to_md(item)
        elif isinstance(item, Paragraph):
            rendered = _paragraph_to_md(item)
        else:
            rendered = getattr(item, "text", "")
        if rendered.strip():
            body.append(rendered)
    if body:
        label = "각주" if fn.type == "footnote" else "미주"
        text = "\n\n".join(body)
        return f"[^{label}]: {text}"
    return ""
