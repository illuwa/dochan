"""
output/markdown.py — Markdown 변환
AI/LLM에 최적화된 Markdown 출력
"""

from ..model.document import Document, Paragraph, TextRun
from ..model.table import Table, Cell, flatten_block_texts
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote

# 중첩 표를 Markdown 셀 한 칸 안에 평탄화할 때의 구분자.
# Markdown 표는 중첩을 지원하지 않으므로 한 줄로 접는다.
_NESTED_COL_SEP = ' / '
_NESTED_ROW_SEP = ' ; '


class _MdContext:
    """to_markdown 한 번의 호출 동안만 사는 렌더 상태.

    각주 번호를 매기고 정의부를 모은다. 모듈 전역 상태를 쓰면
    batch.py 의 병렬 변환에서 번호가 섞이므로 반드시 호출 스코프에 둔다.
    """

    __slots__ = ('_labels', '_defs', '_note_seq', '_comment_seq')

    def __init__(self):
        self._labels = {}      # id(Footnote) -> 라벨
        self._defs = []        # [(라벨, 본문 블록 목록)]
        self._note_seq = 0     # 각주+미주 공용 카운터 (DOCX 본문 마커와 정합)
        self._comment_seq = 0  # 주석 전용 카운터

    def label_for(self, fn) -> str:
        key = id(fn)
        if key in self._labels:
            return self._labels[key]
        if getattr(fn, 'type', '') == 'comment':
            self._comment_seq += 1
            label = f"comment-{self._comment_seq}"
        else:
            number = getattr(fn, 'number', 0)
            if number:
                label = str(number)
                self._note_seq = max(self._note_seq, number)
            else:
                self._note_seq += 1
                label = str(self._note_seq)
        self._labels[key] = label
        return label

    def add_definition(self, label: str, blocks: list) -> None:
        self._defs.append((label, blocks))

    def definitions(self) -> list:
        return [_definition_to_md(label, blocks) for label, blocks in self._defs]


def to_markdown(doc: Document) -> str:
    """Document → Markdown 문자열 변환"""
    parts = []
    ctx = _MdContext()
    include_sheet_headings = _should_include_sheet_headings(doc)
    include_slide_headings = _should_include_slide_headings(doc)

    for section in doc.sections:
        elements = list(section.elements)
        if include_sheet_headings:
            while elements and _is_sheet_preamble(elements[0]):
                md = _element_to_md(elements.pop(0), ctx)
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
            md = _element_to_md(elem, ctx)
            if md:
                parts.append(md)

    # 각주/미주 정의는 문서 말미에 모은다 — Markdown 에는 페이지 개념이 없다.
    parts.extend(ctx.definitions())

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


def _element_to_md(elem, ctx=None) -> str:
    if isinstance(elem, Paragraph):
        return _paragraph_to_md(elem, ctx)
    elif isinstance(elem, Table):
        return _table_to_md(elem, ctx)
    elif isinstance(elem, Equation):
        return _equation_to_md(elem)
    elif isinstance(elem, Image):
        return _image_to_md(elem, ctx)
    elif isinstance(elem, HeaderFooter):
        return _header_footer_to_md(elem)
    elif isinstance(elem, Footnote):
        return _footnote_to_md(elem, ctx)
    return ""


def _paragraph_to_md(para: Paragraph, ctx=None) -> str:
    text = _runs_to_md(para.runs, ctx)
    if not text.strip():
        return ""

    if para.heading_level > 0:
        prefix = '#' * min(para.heading_level, 6)
        return f"{prefix} {text}"

    return text


def _runs_to_md(runs: list, ctx=None) -> str:
    """런 목록을 Markdown 으로. 연속하는 동일 링크 런은 하나로 묶어 감싼다."""
    parts = []
    index = 0
    total = len(runs)
    while index < total:
        link = getattr(runs[index], 'link', '')
        if link:
            end = index
            group = []
            while end < total and getattr(runs[end], 'link', '') == link:
                group.append(runs[end])
                end += 1
            inner = ''.join(_run_to_md(run) for run in group)
            if inner:
                parts.append(_link_to_md(inner, link))
            index = end
            continue

        text = _run_to_md(runs[index])
        if text:
            parts.append(text)
        index += 1

    return ''.join(parts)


def _run_to_md(run: TextRun) -> str:
    # 각주 참조 마커는 서식 대신 Markdown 각주 참조로 렌더한다.
    note_ref = getattr(run, 'note_ref', 0)
    if note_ref:
        return f"[^{note_ref}]"

    text = run.text
    if not text:
        return ""

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

    return text


def _link_to_md(text: str, url: str) -> str:
    """[텍스트](URL) — 링크가 서식보다 바깥에 온다."""
    safe_text = text.replace('[', '\\[').replace(']', '\\]')
    safe_url = url.strip()
    if not safe_url:
        return text
    # 공백이나 괄호가 있는 URL 은 꺾쇠로 감싸야 링크가 끊기지 않는다.
    if any(ch in safe_url for ch in ' ()<>'):
        safe_url = '<' + safe_url.replace('<', '%3C').replace('>', '%3E') + '>'
    return f"[{safe_text}]({safe_url})"


def _table_to_md(table: Table, ctx=None) -> str:
    if not table.rows:
        return ""

    lines = []
    col_count = table.col_count
    if col_count == 0:
        # 행은 있는데 셀이 하나도 없다 — 대시 없는 가짜 구분선을 만들지 않는다
        return _with_caption("", table)

    for row_idx, row in enumerate(table.rows):
        cells_text = []
        for cell in row:
            if cell.is_merged_away:
                cells_text.append("")
            else:
                cells_text.append(_cell_text(cell, ctx))

        # 열 수 맞추기
        while len(cells_text) < col_count:
            cells_text.append("")

        line = "| " + " | ".join(cells_text) + " |"
        lines.append(line)

        # 첫 행 후 구분선
        if row_idx == 0:
            sep = "| " + " | ".join(["---"] * col_count) + " |"
            lines.append(sep)

    return _with_caption('\n'.join(lines), table)


def _with_caption(rendered: str, elem) -> str:
    """캡션이 있으면 side 에 따라 위/아래에 이탤릭 한 줄로 붙인다."""
    caption = getattr(elem, 'caption_text', '')
    if not caption or not caption.strip():
        return rendered
    text = ' '.join(caption.split())
    line = f"*{text}*"
    # LEFT 는 TOP 과, RIGHT 는 BOTTOM 과 같이 취급한다 (Markdown 에 좌우 개념이 없다).
    side = (getattr(elem, 'caption_side', '') or 'BOTTOM').upper()
    if side in ('TOP', 'LEFT'):
        return f"{line}\n\n{rendered}"
    return f"{rendered}\n\n{line}"


def _cell_text(cell: Cell, ctx=None) -> str:
    """셀 내용을 Markdown 표 한 칸에 들어갈 한 줄로 만든다.

    셀 안에서도 하이퍼링크와 각주 참조는 살려야 하므로 문단은 런 단위로 훑는다.
    다만 굵게/기울임 같은 문자 서식은 셀 안에서 평문으로 둔다(기존 동작 유지).
    """
    parts = []
    for block in cell.paragraphs:
        if isinstance(block, Footnote):
            # 참조 마커는 파서가 런에 심어 두었다. 여기서는 정의만 등록하거나
            # (마커가 없으면) 정의를 셀 안에 남긴다.
            rendered = _footnote_to_md(block, ctx)
            if rendered:
                parts.append(_escape_cell(rendered))
            continue
        if isinstance(block, Paragraph):
            text = _runs_to_cell_text(block.runs)
            if text:
                parts.append(_escape_cell(text))
            continue
        for text in flatten_block_texts(
            [block], cell_sep=_NESTED_COL_SEP, row_sep=_NESTED_ROW_SEP
        ):
            escaped = _escape_cell(text)
            if escaped:
                parts.append(escaped)
    return ' '.join(p for p in parts if p)


def _escape_cell(text: str) -> str:
    """Markdown 표 한 칸에 안전하게 들어가도록 정리한다."""
    text = text.replace('\n', ' ').replace('\r', '')
    return text.replace('\t', ' ').replace('|', '\\|')


def _runs_to_cell_text(runs: list) -> str:
    """셀용 런 렌더 — 링크와 각주 참조만 적용하고 문자 서식은 평문으로."""
    parts = []
    index = 0
    total = len(runs)
    while index < total:
        run = runs[index]
        link = getattr(run, 'link', '')
        if link:
            end = index
            inner = []
            while end < total and getattr(runs[end], 'link', '') == link:
                inner.append(runs[end].text)
                end += 1
            joined = ''.join(inner)
            if joined:
                parts.append(_link_to_md(joined, link))
            index = end
            continue

        note_ref = getattr(run, 'note_ref', 0)
        parts.append(f"[^{note_ref}]" if note_ref else run.text)
        index += 1
    return ''.join(parts)


def _equation_to_md(eq: Equation) -> str:
    latex = eq.latex
    if latex:
        return f"$$ {latex} $$"
    elif eq.script:
        return f"$$ {eq.script} $$"
    return ""


def _image_to_md(img: Image, ctx=None) -> str:
    parts = []
    alt = ' '.join((getattr(img, 'alt_text', '') or '').split())
    alt = alt.replace('[', '\\[').replace(']', '\\]') or "이미지"
    target = img.filename or "image"
    # 공백이나 괄호가 든 파일명은 꺾쇠로 감싸야 이미지 문법이 깨지지 않는다
    if any(ch in target for ch in ' ()<>'):
        target = '<' + target.replace('<', '%3C').replace('>', '%3E') + '>'
    parts.append(f"![{alt}]({target})")

    # OCR 텍스트가 있으면 이미지 아래에 추가
    if img.ocr_text:
        parts.append(f"\n{img.ocr_text}")

    return _with_caption('\n'.join(parts), img)


def _header_footer_to_md(hf: HeaderFooter) -> str:
    text = hf.text.strip()
    if text:
        return f"<!-- {hf.type}: {text} -->"
    return ""


def _footnote_body(fn: Footnote, ctx=None) -> list:
    body = []
    for item in fn.paragraphs:
        if isinstance(item, Table):
            rendered = _table_to_md(item, ctx)
        elif isinstance(item, Paragraph):
            rendered = _paragraph_to_md(item, ctx)
        else:
            rendered = getattr(item, "text", "")
        if rendered.strip():
            body.append(rendered)
    return body


def _footnote_to_md(fn: Footnote, ctx=None) -> str:
    """각주 본문을 Markdown 각주 정의로 렌더한다.

    파서가 본문에 참조 마커를 심어준 경우(fn.number > 0)에만 정의를 문서 말미로 모은다.
    마커가 없는데 정의만 말미로 보내면 Markdown 렌더러가 미참조 정의를 통째로 버려
    각주 내용이 소실된다 — 그때는 원래 자리에 남긴다.
    """
    body = _footnote_body(fn, ctx)
    if not body:
        return ""

    if ctx is None:
        return _definition_to_md(_fallback_label(fn), body)

    label = ctx.label_for(fn)
    if getattr(fn, 'number', 0):
        ctx.add_definition(label, body)
        return ""
    return _definition_to_md(label, body)


def _fallback_label(fn: Footnote) -> str:
    kind = getattr(fn, 'type', 'footnote')
    number = getattr(fn, 'number', 0)
    if kind == 'comment':
        return f"comment-{number or 1}"
    return str(number or 1)


def _definition_to_md(label: str, blocks: list) -> str:
    """Markdown 각주 정의. 두 번째 줄부터는 4칸 들여써야 정의 안에 남는다."""
    lines = blocks[0].splitlines() or ['']
    out = [f"[^{label}]: {lines[0]}"]
    out.extend("    " + line if line else "" for line in lines[1:])
    for block in blocks[1:]:
        out.append("")
        out.extend("    " + line if line else "" for line in block.splitlines())
    return '\n'.join(out)
