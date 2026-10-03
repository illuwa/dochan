"""네이티브 PDF 리더 — 스트림·암호·텍스트·표·주석의 공통 모델 변환.

CTM과 글리프 폭으로 본문과 링크를 배치하며, 검증한 기하 조건으로 각주를
분리한다. 지원하지 않는 요소와 손상 입력은 doc.errors 경고로 보고한다.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from ..conversion import AssetRef, Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.image import Image
from .content import (MAX_FORM_CACHE_BYTES, ContentTextExtractor, FontInfo,
                      VerticalMetrics, assemble_lines, default_byte_decoder)
from .cmap import encoding_wmode, parse_tounicode
from .cid_unicode import (CIDDecoder, MAX_FONT_BYTES, adobe_cid, adobe_space_cid,
                          reverse_truetype_cmap)
from .images import extract_image_bytes
from .formulas import FormulaExtractor
from .objects import PDFName, PDFRef, PDFStream
from .structure import PDFFile
from .widths import WidthMap
from .core14 import Core14Decoder, canonical_font, glyph_names
from .core14_metrics import GLYPH_WIDTHS
from .tables import TableBudget, build_tables
from .text_tables import detect_text_tables
from .layout import merge_lines
from .pagination import (EDGE_FRACTION, HEADER_FOOTER_ZONE, HeadInfo, TailInfo, body_between,
                         continues, merge_continued, page_bounds, page_rotation,
                         repeated_header_rows)
from .notes import detect_notes, detect_endnotes, endnote_references
from .running import detect_running
from .annotations import CommentExtractor, DestinationResolver, attach_comments, attach_links, link_regions, text_string

# 글자 표시(Tj·TJ·'·")와 중첩 Form(Do) 연산자 바이트. 없으면 Form 연산자 세기를 건너뛴다.
_FORM_TEXT_OR_NESTED = re.compile(rb"Tj|TJ|Do|['\"]")

MAX_IMAGES_PER_PAGE = 64

MAX_FILE_SIZE = 500 * 1024 * 1024
MAX_CONTENT_PARTS = 256  # 페이지당 콘텐츠 스트림 수 — 반복 참조 CPU 증폭 방지
MAX_PAGE_CONTENT_BYTES = 64 * 1024 * 1024  # 페이지 콘텐츠 결합 합계 — 같은 스트림 반복 참조 메모리 증폭 방지
MAX_OUTLINE_ITEMS = 1000
MAX_OUTLINE_DEPTH = 32
MAX_RUNNING_TEXT_PAGES = 5000
MAX_RUNNING_LINES = 200_000


@dataclass
class _PageDraft:
    section: Section
    page_number: int
    groups: list = field(default_factory=list)
    ordered: list = field(default_factory=list)
    median_size: float = 0.0
    bounds: tuple = (0.0, 842.0)
    rotation: int = 0
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    note_markers: list = field(default_factory=list)


def _drop_decoder(raw: bytes) -> str:
    return ""


def _median_font_size(sized_lines) -> float:
    sizes = sorted(size for _text, size in sized_lines if size > 0)
    if not sizes:
        return 0.0
    return sizes[len(sizes) // 2]


def _heading_level_for_size(text: str, size: float, median: float) -> int:
    """페이지 본문 중앙값 대비 폰트 크기로 제목 레벨 판정."""
    if median <= 0 or size <= 0 or len(text) > 120:
        return 0
    if size >= median * 1.5:
        return 1
    if size >= median * 1.25:
        return 2
    return 0


def _pdf_text_string(value) -> str:
    """PDF 텍스트 문자열 디코드 — UTF-16BE BOM 또는 PDFDocEncoding(≈cp1252)."""
    return text_string(value)


_IMAGE_CONTENT_TYPES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "jp2": "image/jp2", "tif": "image/tiff", "tiff": "image/tiff",
}


def _image_asset(img: Image, page_number: int, index: int) -> AssetRef:
    """Image 요소를 다른 포맷과 같은 AssetRef 로 등록한다 (JSON 직렬화 계약)."""
    ext = img.image_format or "bin"
    name = getattr(img.provenance, "path", "") or f"image{index}"
    return AssetRef(
        id=f"pdf-image-{index}",
        source_path=f"page{page_number}/{name}",
        filename=f"page{page_number}-{name}.{ext}",
        content_type=_IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream"),
        metadata={"kind": "image", "page": page_number, "source_format": "pdf"},
    )


class PDFReader:
    format_name = "pdf"
    extensions = (".pdf",)

    def __init__(self, text_tables: bool = False, password=""):
        self.password = password
        self.text_tables = text_tables

    def read(self, file_path: str) -> Document:
        doc = Document(source_format="pdf")
        try:
            if os.path.getsize(file_path) > MAX_FILE_SIZE:
                doc.errors.append("ERR: PDF 파일이 크기 한도를 초과함")
                return doc
            with open(file_path, "rb") as f:
                data = f.read()
        except OSError as e:
            doc.errors.append(f"ERR: PDF 파일 열기 실패: {e}")
            return doc

        if b"%PDF-" not in data[:1024]:
            doc.errors.append("ERR: PDF 헤더(%PDF-)를 찾지 못함")
            return doc

        # 파서 내부의 어떤 예외도 크래시 대신 doc.errors 로 강등한다 —
        # 손상/악성 PDF 는 정상 흐름이지 예외 상황이 아니다 (감수 M2)
        try:
            pdf = PDFFile(data, password=self.password)
            if pdf.encrypted and not pdf.decrypt_ok:
                doc.errors.extend(pdf.warnings)
                return doc
            pages = pdf.pages()
        except Exception as e:
            doc.errors.append(f"ERR: PDF 구조 파싱 실패: {e!r}")
            return doc

        try:
            destinations = DestinationResolver(pdf, pages)
        except Exception as e:
            pdf.warnings.append(f"WARN: PDF 목적지 해석 실패: {e!r}")
            destinations = DestinationResolver(pdf, pages, load_names=False)
        pdf._destination_resolver = destinations
        outline_section = self._outline_section(pdf, pages)
        if outline_section is not None:
            doc.sections.append(outline_section)

        try:
            formula_extractor = FormulaExtractor(pdf)
        except Exception as e:
            pdf.warnings.append(f"WARN: PDF Formula 구조 해석 실패: {e!r}")
            formula_extractor = None
        next_note_number = 1
        comment_extractor = CommentExtractor()
        font_cache = {}
        table_budget = TableBudget()
        tail = None
        drafts = []
        running_disabled = False
        text_pages = 0
        running_lines = 0
        for page_number, (page, resources) in enumerate(pages, start=1):
            section = Section(
                provenance=Provenance(source_format="pdf", page=page_number)
            )
            draft = _PageDraft(section=section, page_number=page_number)
            try:
                draft.bounds = page_bounds(pdf, page)
                draft.rotation = page_rotation(pdf, page)
                try:
                    regions = link_regions(pdf, page, destinations)
                except Exception as e:
                    pdf.warnings.append(f"WARN: PDF 링크 주석 해석 실패: {e!r}")
                    regions = []
                try:
                    draft.comments = comment_extractor.extract(pdf, page, page_number)
                except Exception as e:
                    pdf.warnings.append(f"WARN: {page_number}페이지 주석 추출 실패: {e!r}")
                    comment_extractor.regions = []
                comment_regions = comment_extractor.regions
                content_parts = self._page_content_parts(pdf, page)
                lines = []
                groups = []
                tables = []
                page_content = None
                equations = []
                formula_size_fragments = []
                if content_parts:
                    extractor = ContentTextExtractor.from_fonts(
                        self._font_infos(pdf, resources, font_cache),
                        track_char_positions=bool(regions or comment_regions)
                    )
                    properties = pdf.resolve(resources.get("Properties")) if isinstance(resources, dict) else None
                    if isinstance(properties, dict):
                        extractor.properties = {key: pdf.resolve(value) for key, value in properties.items()}
                    self._configure_form_extractor(extractor, pdf, resources, font_cache)
                    page_content = extractor.extract_page(b"\n".join(content_parts))
                    pdf.warnings.extend(page_content.warnings)
                    attach_links(page_content.fragments, regions, pdf.warnings,
                                 allow_clipped_edges=True)
                    note_mcids = set()
                    try:
                        notes, consumed_notes, references, next_note_number = detect_notes(
                            page_content.fragments, page_content.segments, draft.bounds,
                            page_number, next_note_number, pdf.warnings)
                        draft.notes = notes
                        for fragment in page_content.fragments:
                            fragment.note_ref = references.get(fragment.order, 0)
                        draft.note_markers = endnote_references(page_content.fragments, pdf.warnings)
                        note_mcids = {mcid for fragment in page_content.fragments
                                      if fragment.order in consumed_notes for mcid in fragment.mcids}
                        page_content.fragments = [fragment for fragment in page_content.fragments
                                                  if fragment.order not in consumed_notes]
                    except Exception as e:
                        pdf.warnings.append(f"WARN: {page_number}페이지 각주 복원 실패: {e!r}")
                    attach_comments(page_content.fragments, comment_regions, pdf.warnings)
                    try:
                        tables = build_tables(page_content.segments, page_content.fragments,
                                              page_number=page_number, warnings=pdf.warnings,
                                              budget=table_budget,
                                              short_segments=page_content.short_segments)
                    except Exception as e:
                        pdf.warnings.append(f"WARN: {page_number}페이지 표 복원 실패: {e!r}")
                    protected_orders = set().union(*(t.fragment_orders for t in tables))
                    if formula_extractor is not None:
                        formula_page_ready = True
                        try:
                            needs_formula_prepass = self.text_tables and formula_extractor.has_formulas(page)
                        except Exception as e:
                            pdf.warnings.append(f"WARN: PDF Formula 구조 해석 실패: {e!r}")
                            needs_formula_prepass = False
                            formula_page_ready = False
                        if needs_formula_prepass:
                            try:
                                # Decide ownership before Formula removal can
                                # destroy the repeated rows needed for detection.
                                for group in self._body_groups(extractor, page_content.fragments, tables):
                                    for _table, indices in detect_text_tables(group, page_number):
                                        protected_orders.update(order for index in indices
                                                                for order in group[index].fragment_orders)
                            except Exception as e:
                                pdf.warnings.append(f"WARN: {page_number}페이지 텍스트 표 소유권 판정 실패: {e!r}")
                                protected_orders.update(f.order for f in page_content.fragments)
                        try:
                            equations, consumed_formula = (formula_extractor.apply(
                                page, page_content, protected_orders, note_mcids)
                                if formula_page_ready else ([], set()))
                            formula_size_fragments = [f for f in page_content.fragments
                                                      if f.order in consumed_formula]
                            page_content.fragments = [f for f in page_content.fragments
                                                      if f.order not in consumed_formula]
                        except Exception as e:
                            pdf.warnings.append(f"WARN: PDF Formula 변환 실패: {e!r}")
                    groups = self._body_groups(extractor, page_content.fragments, tables,
                                               [event[0] for event in equations])
                    lines = [line for group in groups for line in group]
                image_elems = self._page_images(pdf, resources, page_number)
                has_text = bool(page_content and page_content.fragments)
                if not has_text and image_elems:
                    pdf.warnings.append(
                        f"WARN: {page_number}페이지: 텍스트 없음 — 이미지 기반(OCR 옵션으로 추출 가능)"
                    )
                elif not has_text and self._page_has_images(pdf, resources):
                    pdf.warnings.append(
                        f"WARN: {page_number}페이지: 텍스트 없음 — 스캔 이미지로 추정 (이미지 추출 불가)"
                    )
                size_lines = lines
                if formula_size_fragments:
                    # Equation replacement must not change neighbouring heading
                    # classification by removing the smaller math font samples.
                    size_fragments = sorted(page_content.fragments + formula_size_fragments,
                                            key=lambda fragment: fragment.order)
                    size_lines = [line for group in PDFReader._body_groups(
                        extractor, size_fragments, tables) for line in group]
                median_size = _median_font_size([(ln.text, ln.size) for ln in size_lines])
                merged_head = None
                if tables and page_rotation(pdf, page) != 0:
                    tail = None  # 회전된 페이지는 위·아래 판정이 무의미하다 (180° 는 위아래가 뒤집힌다)
                elif tables:
                    bottom, top = page_bounds(pdf, page)
                    body_bottom, body_top = bottom + HEADER_FOOTER_ZONE, top - HEADER_FOOTER_ZONE
                    consumed = set().union(*(t.fragment_orders for t in tables))
                    # 꼬리·머리 후보는 그리기 순서가 아니라 위치로 고른다
                    first = max(tables, key=lambda t: t.bbox[3])
                    last = min(tables, key=lambda t: t.bbox[1])
                    fragments = page_content.fragments if page_content else []
                    # 후보는 본문 띠(머리말·꼬리말 영역 사이)에 걸쳐 있어야 하고, 가장자리 거리는 0 이상으로 본다
                    in_body = lambda t: t.bbox[1] < body_top and t.bbox[3] > body_bottom  # noqa: E731
                    starts_top = (in_body(first)
                                  and max(0.0, body_top - first.bbox[3]) <= EDGE_FRACTION * (top - bottom)
                                  and not body_between(fragments, consumed, first.bbox[3], body_top))
                    reaches_bottom = (in_body(last)
                                      and not body_between(fragments, consumed, body_bottom, last.bbox[1]))
                    if tail is not None and continues(tail, HeadInfo(first, starts_top)):
                        merged_head = first
                        merge_continued(tail.candidate.table, first.table,
                                        repeated_header_rows(tail.candidate.table, first.table))
                        first.table = tail.candidate.table
                    tail = (TailInfo(last, True, gap_below=max(0.0, last.bbox[1] - body_bottom),
                                     page_height=top - bottom) if reaches_bottom else None)
                else:
                    tail = None
                ordered = [(t.anchor_order, 0, t.table) for t in tables if t is not merged_head] + equations
                draft.groups = groups
                draft.ordered = ordered
                draft.median_size = median_size
                draft.links = self._link_paragraphs(pdf, page, page_number)
                draft.images = image_elems
                for img in image_elems:
                    if img.image_data:
                        doc.assets.append(_image_asset(img, page_number, len(doc.assets) + 1))
            except Exception as e:
                tail = None
                draft.groups = []
                draft.ordered = []
                draft.links = []
                draft.images = []
                pdf.warnings.append(f"WARN: {page_number}페이지 파싱 실패: {e!r}")
            if any(draft.groups):
                text_pages += 1
            if not running_disabled:
                running_lines += sum(len(group) for group in draft.groups)
            if (text_pages > MAX_RUNNING_TEXT_PAGES or running_lines > MAX_RUNNING_LINES) and not running_disabled:
                running_disabled = True
                for held in drafts:
                    self._safe_finalize_draft(held, set(), pdf.warnings)
                    doc.sections.append(held.section)
                drafts.clear()
            if running_disabled:
                self._safe_finalize_draft(draft, set(), pdf.warnings)
                doc.sections.append(section)
            else:
                drafts.append(draft)

        if not running_disabled:
            inserted = []
            try:
                drops, emitted = detect_running(drafts)
                elements_by_page = {}
                for number, element in emitted:
                    elements_by_page.setdefault(number, []).append(element)
                for draft in drafts:
                    elements = draft.section.elements
                    inserted.append((elements, len(elements)))
                    elements.extend(elements_by_page.get(draft.page_number, []))
            except Exception as e:
                pdf.warnings.append(f"WARN: 반복 머리글/바닥글 검출 실패: {e!r}")
                for elements, original_length in inserted:
                    del elements[original_length:]
                drops = {}
            try:
                next_note_number = detect_endnotes(drafts, drops, next_note_number, pdf.warnings)
            except Exception as e:
                pdf.warnings.append(f"WARN: PDF 미주 구역 복원 실패: {e!r}")
            for draft in drafts:
                removed = drops.get(draft.page_number, set())
                self._safe_finalize_draft(draft, removed, pdf.warnings)
                doc.sections.append(draft.section)

        for section in doc.sections:
            number = getattr(section.provenance, "page", None)
            if number in destinations.targets:
                provenance = Provenance(source_format="pdf", page=number, path="destination")
                marker = TextRun(text="[bookmark: page-%d] " % number, provenance=provenance)
                first = section.elements[0] if section.elements else None
                if isinstance(first, Paragraph):
                    first.runs.insert(0, marker)
                else:
                    section.elements.insert(0, Paragraph(runs=[marker], provenance=provenance))

        # 같은 경고가 페이지 수만큼 중복 누적되지 않게 순서 보존 dedup
        seen = set()
        for warning in pdf.warnings:
            if warning not in seen:
                seen.add(warning)
                doc.errors.append(warning)
        return doc

    def _safe_finalize_draft(self, draft: _PageDraft, dropped: set, warnings: list) -> None:
        try:
            self._finalize_draft(draft, dropped, warnings)
        except Exception as e:
            warnings.append(f"WARN: {draft.page_number}페이지 파싱 실패: {e!r}")
            elements = draft.section.elements
            present = {id(element) for element in elements}
            for element in draft.links + draft.images + draft.comments + draft.notes:
                if id(element) not in present:
                    elements.append(element)
                    present.add(id(element))

    def _finalize_draft(self, draft: _PageDraft, dropped: set, warnings: list) -> None:
        """검출 결과를 적용한 뒤 기존 페이지별 문단/텍스트 표 흐름을 완성한다."""
        ordered = draft.ordered
        for group in draft.groups:
            group = [line for line in group if id(line) not in dropped]
            if self.text_tables:
                try:
                    detected = detect_text_tables(group, draft.page_number)
                except Exception as e:
                    warnings.append(f"WARN: {draft.page_number}페이지 텍스트 표 복원 실패: {e!r}")
                    detected = []
                consumed = set()
                for table, indices in detected:
                    consumed.update(indices)
                    ordered.append((group[min(indices)].order, 0, table))
                chunks = [[]]
                for index, line in enumerate(group):
                    if index in consumed:
                        if chunks[-1]:
                            chunks.append([])
                    else:
                        chunks[-1].append(line)
                body_groups = chunks
            else:
                body_groups = [group]
            for body_group in body_groups:
                for block in merge_lines(body_group):
                    paragraph = block.paragraph(draft.page_number)
                    paragraph.heading_level = _heading_level_for_size(
                        block.text, block.size, draft.median_size)
                    ordered.append((block.order, 1, paragraph))
        draft.section.elements.extend(item for _, _, item in sorted(
            ordered, key=lambda event: (event[0], event[1])))
        # 세 출력 모두 link를 보존하는 최종 최상위 문단만 중복 억제 근거다.
        # 표·각주·반복 머리글은 plain text에서 URL을 버리므로 fallback을 남긴다.
        surviving = {run.link for element in draft.section.elements
                     if isinstance(element, Paragraph) for run in element.runs
                     if run.link and run.text.strip() and not run.note_ref}
        draft.section.elements.extend(paragraph for paragraph in draft.links
                                      if paragraph.runs[0].link not in surviving)
        draft.section.elements.extend(draft.images)
        anchored = {run.note_reference_number
                    for paragraph in Document(sections=[Section(
                        elements=draft.section.elements + draft.notes)]).find_all("paragraph")
                    for run in paragraph.runs if run.note_reference_type == "comment"}
        draft.section.elements.extend(element for element in draft.comments
                                      if not (isinstance(element, Paragraph)
                                              and element.runs
                                              and element.runs[0].note_reference_number in anchored))
        draft.section.elements.extend(draft.notes)

    @staticmethod
    def _body_groups(extractor, fragments, tables, boundaries=()):
        """표를 경계로 본문 흐름을 나누고 빈 표의 앵커를 정한다."""
        groups = []
        consumed = set().union(*(t.fragment_orders for t in tables))
        for table in tables:
            if table.anchor_order < 0:
                table.anchor_order = next(
                    (f.order for f in fragments if f.y < table.bbox[3]),
                    len(fragments),
                )
        events = [(f.order, 1, f) for f in fragments
                  if f.order not in consumed]
        events.extend((t.anchor_order, 0, t) for t in tables)
        events.extend((order, 0, None) for order in boundaries)
        pending = []
        for _, kind, event in sorted(events, key=lambda e: (e[0], e[1])):
            if kind:
                pending.append(event)
            else:
                groups.append(assemble_lines(pending))
                pending = []
        groups.append(assemble_lines(pending))
        # 크기 없는 비정상 텍스트는 좌표로 같은 줄임을 보장할 수 없다.
        if fragments and all(f.size == 0 for f in fragments):
            groups = [assemble_lines([f]) for f in fragments
                      if f.order not in consumed]
        return groups

    def _outline_section(self, pdf: PDFFile, pages) -> Optional[Section]:
        """카탈로그 /Outlines 북마크 트리를 목차 섹션으로 변환."""
        root = pdf.resolve(pdf.trailer.get("Root"))
        if not isinstance(root, dict):
            return None
        outlines = pdf.resolve(root.get("Outlines"))
        if not isinstance(outlines, dict):
            return None
        page_numbers = {
            id(page): number for number, (page, _res) in enumerate(pages, start=1)
        }
        paragraphs = []
        self._walk_outline(pdf, outlines.get("First"), 0, page_numbers, paragraphs, set())
        if not paragraphs:
            return None
        return Section(
            elements=paragraphs,
            provenance=Provenance(source_format="pdf", path="outline"),
        )

    def _walk_outline(self, pdf, item_ref, depth, page_numbers, out, visited) -> None:
        while item_ref is not None:
            if depth > MAX_OUTLINE_DEPTH or len(out) >= MAX_OUTLINE_ITEMS:
                return
            key = item_ref.num if isinstance(item_ref, PDFRef) else id(item_ref)
            if key in visited:
                return
            visited.add(key)
            item = pdf.resolve(item_ref)
            if not isinstance(item, dict):
                return
            title = _pdf_text_string(item.get("Title")).strip()
            if title:
                page_no = self._outline_page_number(pdf, item, page_numbers)
                suffix = f" (p.{page_no})" if page_no else ""
                indent = "  " * depth
                out.append(
                    Paragraph(
                        runs=[TextRun(text=f"{indent}- {title}{suffix}")],
                        provenance=Provenance(source_format="pdf", path="outline", page=page_no),
                    )
                )
            self._walk_outline(pdf, item.get("First"), depth + 1, page_numbers, out, visited)
            item_ref = item.get("Next")

    def _outline_page_number(self, pdf, item, page_numbers):
        dest = pdf.resolve(item.get("Dest"))
        if dest is None:
            action = pdf.resolve(item.get("A"))
            if isinstance(action, dict):
                dest = pdf.resolve(action.get("D"))
        if isinstance(dest, list) and dest:
            page = pdf.resolve(dest[0])
            if isinstance(page, dict):
                return page_numbers.get(id(page))
        return None

    def _link_paragraphs(self, pdf: PDFFile, page: dict, page_number: int) -> list:
        """페이지 /Annots 의 링크 주석에서 URI 를 추출해 문단으로 반환."""
        annots = pdf.resolve(page.get("Annots"))
        if not isinstance(annots, list):
            return []
        paragraphs = []
        seen = set()
        destinations = getattr(pdf, "_destination_resolver", None) or DestinationResolver(pdf, pdf.pages())
        for annot_ref in annots[:MAX_CONTENT_PARTS]:
            annot = pdf.resolve(annot_ref)
            if not isinstance(annot, dict) or str(annot.get("Subtype", "")) != "Link":
                continue
            url = destinations.annotation_target(annot)
            if not url or url in seen:
                continue
            seen.add(url)
            provenance = Provenance(source_format="pdf", page=page_number, path="annots")
            paragraphs.append(
                Paragraph(
                    runs=[TextRun(text=("Page " + url[6:] if url.startswith("#page-") else f"<{url}>"),
                                  link=url, provenance=provenance)],
                    provenance=provenance,
                )
            )
        return paragraphs

    def _configure_form_extractor(self, extractor, pdf, resources, font_cache):
        """Attach Form lookup with document-wide decode and font caches."""
        extractor.resources = resources
        loaded_forms = {}
        # Form 바이트 상한은 페이지 단위다. 분석 결과·거부 목록·글꼴 캐시만 문서 단위로 둔다
        # (문서 전체 누적으로 걸면 서로 다른 Form 을 많이 쓰는 문서의 뒤 페이지 글자가 빠진다).
        page_forms = {"bytes": 0, "seen": set()}
        state = getattr(pdf, "_form_cache_state", None)
        if state is None:
            state = {"stream_info": {}, "rejected_streams": {}, "font_infos": {}}
            pdf._form_cache_state = state
        stream_info = state["stream_info"]
        rejected_streams = state["rejected_streams"]

        def load_form(name, caller_resources):
            if not isinstance(caller_resources, dict):
                return None
            xobjects = pdf.resolve(caller_resources.get("XObject"))
            if not isinstance(xobjects, dict):
                return None
            ref = xobjects.get(name)
            stream = pdf.resolve(ref)
            if not isinstance(stream, PDFStream) or str(stream.dictionary.get("Subtype")) != "Form":
                return None
            if rejected_streams.get(id(stream)) is stream:
                return None
            cache_key = (id(stream), id(caller_resources))
            if cache_key in loaded_forms:
                return loaded_forms[cache_key]
            form_resources = pdf.resolve(stream.dictionary.get("Resources"))
            if not isinstance(form_resources, dict):
                form_resources = caller_resources
            matrix = pdf.resolve(stream.dictionary.get("Matrix"))
            if not isinstance(matrix, list) or len(matrix) != 6:
                matrix = [1, 0, 0, 1, 0, 0]
            try:
                matrix = tuple(float(v) if isinstance(v, (int, float)) else float("nan")
                               for v in matrix)
            except (OverflowError, ValueError):
                matrix = (float("nan"),) * 6
            info = stream_info.get(id(stream))
            if info is None or info[0] is not stream:
                data = pdf.decode_form_bytes(stream)
                if data is None:
                    warning = "WARN: PDF Form 해제 예산 한도 — 이후 Form 건너뜀(페이지 본문은 유지)"
                    if warning not in pdf.warnings:
                        pdf.warnings.append(warning)
                    rejected_streams[id(stream)] = stream
                    loaded_forms[cache_key] = None
                    return None
                if len(data) > MAX_FORM_CACHE_BYTES:
                    # 단독으로 상한을 넘는 Form 만 문서 단위로 거부한다. 디코드 결과는 문서 캐시에 남아
                    # 다른 페이지가 해제 예산을 다시 쓰지 않는다.
                    warning = "WARN: PDF Form 디코드 캐시 한도 — 해당 Form 건너뜀"
                    if warning not in pdf.warnings:
                        pdf.warnings.append(warning)
                    rejected_streams[id(stream)] = stream
                    loaded_forms[cache_key] = None
                    return None
                if _FORM_TEXT_OR_NESTED.search(data) is None:
                    # 글자 표시·중첩 Form 연산자 바이트가 없으면 연산자를 세지 않고 바이트도 보관하지 않는다.
                    op_count, has_text_or_form = 0, False
                else:
                    op_count, has_text_or_form = ContentTextExtractor._count_operators(data)
                info = (stream, data if has_text_or_form else b"", op_count, has_text_or_form)
                stream_info[id(stream)] = info
            else:
                _, data, op_count, has_text_or_form = info
            if not has_text_or_form:
                loaded_forms[cache_key] = None
                return None
            if id(stream) not in page_forms["seen"]:
                if page_forms["bytes"] + len(data) > MAX_FORM_CACHE_BYTES:
                    # 이 페이지에서만 건너뛴다(다른 페이지에서는 다시 쓸 수 있다).
                    warning = "WARN: PDF Form 디코드 캐시 한도 — 해당 Form 건너뜀"
                    if warning not in pdf.warnings:
                        pdf.warnings.append(warning)
                    loaded_forms[cache_key] = None
                    return None
                page_forms["seen"].add(id(stream))
                page_forms["bytes"] += len(data)
            if not has_text_or_form:
                loaded_forms[cache_key] = None
                return None
            bbox = pdf.resolve(stream.dictionary.get("BBox"))
            if (not isinstance(bbox, list) or len(bbox) != 4 or
                    not all(isinstance(v, (int, float)) for v in bbox)):
                bbox = None
            else:
                try:
                    bbox = tuple(float(v) for v in bbox)
                except (OverflowError, ValueError):
                    bbox = None
            props = pdf.resolve(form_resources.get("Properties"))
            if isinstance(props, dict):
                props = {key: pdf.resolve(value) for key, value in props.items()}
            else:
                props = {}
            def get_fonts():
                if "Font" not in form_resources:
                    return {}
                cached = state["font_infos"].get(id(form_resources))
                if cached is not None and cached[0] is form_resources:
                    return cached[1]
                infos = self._font_infos(pdf, form_resources, font_cache)
                state["font_infos"][id(form_resources)] = (form_resources, infos)
                return infos

            loaded = (id(stream), data, matrix, form_resources,
                      get_fonts, props, op_count, bbox,
                      isinstance(pdf.resolve(stream.dictionary.get("StructParents")), int))
            loaded_forms[cache_key] = loaded
            return loaded

        extractor.form_loader = load_form

    def _page_content_parts(self, pdf: PDFFile, page: dict) -> list:
        contents = pdf.resolve(page.get("Contents"))
        streams = contents if isinstance(contents, list) else [contents]
        if len(streams) > MAX_CONTENT_PARTS:
            pdf.warnings.append(
                f"WARN: 페이지 콘텐츠 스트림 수가 한도({MAX_CONTENT_PARTS})를 초과 — 일부만 파싱"
            )
            streams = streams[:MAX_CONTENT_PARTS]
        parts = []
        total = 0
        for item in streams:
            stream = pdf.resolve(item)
            if isinstance(stream, PDFStream):
                decoded = pdf.decode_stream_bytes(stream)
                if not decoded:
                    continue
                # 캐시된 같은 스트림을 수백 번 참조하면 결합 시 사본이 그만큼 생긴다
                if total + len(decoded) > MAX_PAGE_CONTENT_BYTES:
                    pdf.warnings.append(
                        "WARN: 페이지 콘텐츠 합계 한도(64MB)를 초과 — 일부만 파싱"
                    )
                    break
                total += len(decoded)
                parts.append(decoded)
        return parts

    def _font_infos(self, pdf: PDFFile, resources, font_cache: dict) -> Dict[str, FontInfo]:
        infos: Dict[str, FontInfo] = {}
        if not isinstance(resources, dict):
            return infos
        fonts = pdf.resolve(resources.get("Font"))
        if not isinstance(fonts, dict):
            return infos
        for name, font_ref in fonts.items():
            # 같은 폰트를 페이지마다 다시 해석하지 않는다 — 수백 페이지 문서에서
            # ToUnicode/폭 파싱이 페이지 수만큼 반복되는 것을 막는다
            cache_key = font_ref if isinstance(font_ref, PDFRef) else None
            if cache_key is not None and cache_key in font_cache:
                infos[str(name)] = font_cache[cache_key]
                continue
            font = pdf.resolve(font_ref)
            if not isinstance(font, dict):
                continue
            info = self._build_font_info(pdf, str(name), font)
            infos[str(name)] = info
            if cache_key is not None:
                font_cache[cache_key] = info
        return infos

    def _build_font_info(self, pdf: PDFFile, name: str, font: dict) -> FontInfo:
        decoder = self._build_font_decoder(pdf, name, font)
        subtype = str(font.get("Subtype", ""))
        if subtype == "Type0":
            code_bytes = 2  # Identity-H/V — 2바이트 CID (가장 흔한 한국어 폰트)
            widths = self._cid_widths(pdf, font)
            descriptor_font = self._cid_descendant(pdf, font)
        else:
            code_bytes = 1
            widths = self._simple_widths(pdf, font)
            descriptor_font = font
        bold, italic = self._font_style_flags(pdf, font, descriptor_font)
        wmode, vertical_metrics = 0, None
        if subtype == "Type0":
            encoding = pdf.resolve(font.get("Encoding"))
            if isinstance(encoding, PDFStream):
                wmode = encoding_wmode(data=pdf.decode_stream_bytes(encoding),
                                       dictionary_mode=pdf.resolve(encoding.dictionary.get("WMode")))
            else:
                wmode = encoding_wmode(str(encoding or ""))
            if wmode == 1:
                vertical_metrics = VerticalMetrics(pdf.resolve(descriptor_font.get("W2")),
                                                   pdf.resolve(descriptor_font.get("DW2")), widths)
                pdf.warnings.extend(vertical_metrics.warnings)
        reliable = (subtype in ("Type1", "TrueType", "MMType1") or
                    subtype == "Type0" and str(pdf.resolve(font.get("Encoding"))) == "Identity-H")
        encoding = pdf.resolve(font.get("Encoding"))
        has_unicode_map = getattr(getattr(decoder, "__self__", None), "mapping", None)
        reliable = reliable and getattr(getattr(decoder, "__self__", None), "reliable", True)
        if not has_unicode_map:
            base_font = str(pdf.resolve(font.get("BaseFont")) or "")
            standard_font = base_font in {
                "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
                "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
                "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"}
            reliable = reliable and (str(encoding) in ("WinAnsiEncoding", "MacRomanEncoding")
                                     or encoding is None and standard_font and subtype != "TrueType")
        space_code = 32
        if subtype == "Type0" and str(encoding) == "Identity-H" and isinstance(has_unicode_map, dict):
            # CID 32 is not necessarily a space. Use a uniquely identified,
            # explicitly measured U+0020, not the width of an unrelated glyph.
            spaces = [key[1] for key, value in has_unicode_map.items()
                      if value == " " and isinstance(key, tuple) and len(key) == 2
                      and key[0] == code_bytes and widths.explicit(key[1])]
            if len(spaces) == 1:
                space_code = spaces[0]
        elif subtype == "Type0" and str(encoding) == "Identity-H":
            recovered_space = getattr(getattr(decoder, "__self__", None), "space_code", None)
            if recovered_space is not None:
                space_code = recovered_space
        return FontInfo(decode=decoder, widths=widths, code_bytes=code_bytes,
                        bold=bold, italic=italic, wmode=wmode, vertical_metrics=vertical_metrics,
                        link_metrics_reliable=reliable, space_code=space_code)

    def _cid_descendant(self, pdf: PDFFile, font: dict):
        descendants = pdf.resolve(font.get("DescendantFonts"))
        if isinstance(descendants, list) and descendants:
            cid = pdf.resolve(descendants[0])
            if isinstance(cid, dict):
                return cid
        return font

    def _font_style_flags(self, pdf: PDFFile, font: dict, descriptor_font: dict):
        """BaseFont 이름과 FontDescriptor /Flags 로 bold/italic 판정."""
        base = str(pdf.resolve(font.get("BaseFont")) or "").lower()
        bold = "bold" in base
        italic = "italic" in base or "oblique" in base
        descriptor = pdf.resolve(descriptor_font.get("FontDescriptor"))
        if isinstance(descriptor, dict):
            flags = pdf.resolve(descriptor.get("Flags"))
            if isinstance(flags, int):
                italic = italic or bool(flags & (1 << 6))       # Italic 비트
                bold = bold or bool(flags & (1 << 18))          # ForceBold 비트
            weight = pdf.resolve(descriptor.get("FontWeight"))
            if isinstance(weight, (int, float)) and weight >= 600:
                bold = True
        return bold, italic

    def _simple_widths(self, pdf: PDFFile, font: dict) -> WidthMap:
        first = pdf.resolve(font.get("FirstChar"))
        arr = pdf.resolve(font.get("Widths"))
        if isinstance(first, int) and isinstance(arr, list):
            resolved = [pdf.resolve(w) for w in arr]
            return WidthMap.simple(first, resolved, default=500.0)
        base, names = self._core14_encoding(pdf, font)
        if names is not None and "Widths" not in font:
            metrics = GLYPH_WIDTHS[base]
            return WidthMap({code: metrics[glyph] for code, glyph in names.items()
                             if glyph in metrics}, 500.0)
        return WidthMap({}, 500.0)

    def _core14_encoding(self, pdf: PDFFile, font: dict):
        if str(font.get("Subtype", "")) not in ("Type1", "TrueType", "MMType1"):
            return None, None
        base = str(pdf.resolve(font.get("BaseFont")) or "")
        descriptor = pdf.resolve(font.get("FontDescriptor"))
        if isinstance(descriptor, dict) and any(key in descriptor for key in
                                               ("FontFile", "FontFile2", "FontFile3")):
            return None, None
        flags = pdf.resolve(descriptor.get("Flags")) if isinstance(descriptor, dict) else 0
        if (str(font.get("Subtype")) == "TrueType" and isinstance(flags, int) and flags & 4
                and canonical_font(base) not in ("Symbol", "ZapfDingbats")):
            # A symbolic TrueType cmap cannot be inferred from an Arial alias.
            return None, None
        encoding = pdf.resolve(font.get("Encoding"))
        if isinstance(encoding, dict):
            encoding = {key: pdf.resolve(value) for key, value in encoding.items()}
            if isinstance(encoding.get("Differences"), list):
                if len(encoding["Differences"]) > 4096:
                    pdf.warnings.append("WARN: PDF 글꼴 Differences 한도(4096) 초과 — 인코딩 보류")
                    return None, None
                encoding["Differences"] = [pdf.resolve(value) for value in encoding["Differences"][:4096]]
        return canonical_font(base), glyph_names(base, encoding,
                                                  truetype=str(font.get("Subtype")) == "TrueType")

    def _cid_widths(self, pdf: PDFFile, font: dict) -> WidthMap:
        descendants = pdf.resolve(font.get("DescendantFonts"))
        cid_font = None
        if isinstance(descendants, list) and descendants:
            cid_font = pdf.resolve(descendants[0])
        if not isinstance(cid_font, dict):
            return WidthMap({}, 1000.0)
        dw = pdf.resolve(cid_font.get("DW"))
        default = float(dw) if isinstance(dw, (int, float)) else 1000.0
        w = pdf.resolve(cid_font.get("W"))
        if isinstance(w, list):
            resolved = []
            budget = 65536
            truncated = len(w) > 65536
            for item in w[:65536]:
                value = pdf.resolve(item)
                if isinstance(value, list):
                    truncated = truncated or len(value) > budget
                    resolved.append([pdf.resolve(entry) for entry in value[:budget]])
                    budget -= min(len(value), budget)
                else:
                    resolved.append(value)
            widths = WidthMap.cid(resolved, default_width=default)
            if truncated:
                pdf.warnings.append("WARN: PDF CID 폭 배열 항목 한도(65536) 초과")
                widths.reliable = False
        else:
            widths = WidthMap.cid([], default_width=default)
        pdf.warnings.extend(widths.warnings)
        return widths

    def _build_font_decoder(self, pdf: PDFFile, name: str, font: dict) -> Callable[[bytes], str]:
        to_unicode = pdf.resolve(font.get("ToUnicode"))
        if isinstance(to_unicode, PDFStream):
            cmap_data = pdf.decode_stream_bytes(to_unicode)
            if cmap_data:
                cmap = parse_tounicode(cmap_data, pdf.warnings)
                if cmap.mapping:
                    return cmap.decode
        if str(font.get("Subtype", "")) == "Type0":
            recovered = self._cid_fallback_decoder(pdf, name, font)
            if recovered is not None:
                return recovered.decode
        # ToUnicode 없는 CID 폰트를 cp1252 로 해석하면 NUL 등 제어문자가
        # 본문으로 새어 나간다 — 경고를 남기고 해당 텍스트는 버린다 (감수 M4)
        encoding = pdf.resolve(font.get("Encoding"))
        if isinstance(encoding, dict):
            encoding = pdf.resolve(encoding.get("BaseEncoding"))
        encoding_name = str(encoding) if isinstance(encoding, PDFName) else ""
        _base, names = self._core14_encoding(pdf, font)
        if names is not None:
            macroman = encoding_name == "MacRomanEncoding"
            fallback = (lambda raw: raw.decode("mac_roman", errors="replace")) if macroman else default_byte_decoder
            return Core14Decoder(names, fallback, preserve_undefined=macroman).decode
        if str(font.get("Subtype", "")) == "Type0" or encoding_name.startswith("Identity-"):
            pdf.warnings.append(
                f"WARN: 폰트 {name}: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음"
            )
            return _drop_decoder
        if encoding_name == "MacRomanEncoding":
            return lambda raw: raw.decode("mac_roman", errors="replace")
        return default_byte_decoder

    def _cid_fallback_decoder(self, pdf: PDFFile, name: str, font: dict):
        encoding = pdf.resolve(font.get("Encoding"))
        if not isinstance(encoding, PDFName) or encoding not in ("Identity-H", "Identity-V"):
            return None  # 다른 미리 정의된 CMap은 코드→CID 표가 필요하다.
        descendant = self._cid_descendant(pdf, font)
        system = pdf.resolve(descendant.get("CIDSystemInfo"))
        descriptor = pdf.resolve(descendant.get("FontDescriptor"))
        font_stream = (pdf.resolve(descriptor.get("FontFile2"))
                       if isinstance(descriptor, dict) else None)
        gid_object = pdf.resolve(descendant.get("CIDToGIDMap"))
        embedded_identity_gid = (str(pdf.resolve(descendant.get("Subtype"))) == "CIDFontType2"
                                 and isinstance(font_stream, PDFStream)
                                 and not isinstance(gid_object, PDFStream))
        if isinstance(system, dict):
            registry = pdf.resolve(system.get("Registry"))
            ordering = pdf.resolve(system.get("Ordering"))
            registry = (registry.decode("ascii", "ignore") if isinstance(registry, bytes)
                        and len(registry) <= 32 else str(registry) if isinstance(registry, PDFName) else "")
            ordering = (ordering.decode("ascii", "ignore") if isinstance(ordering, bytes)
                        and len(ordering) <= 32 else str(ordering) if isinstance(ordering, PDFName) else "")
            if (registry == "Adobe" and ordering in ("Japan1", "GB1", "CNS1", "Korea1", "KR")
                    and not embedded_identity_gid):
                return CIDDecoder(lambda cid: adobe_cid(ordering, cid), pdf.warnings, name,
                                  adobe_space_cid(ordering))
        if pdf.resolve(descendant.get("Subtype")) != "CIDFontType2":
            return None
        if not isinstance(descriptor, dict):
            return None
        if not isinstance(font_stream, PDFStream) or len(font_stream.raw) > MAX_FONT_BYTES:
            return None
        cache = getattr(pdf, "_cid_cmap_cache", None)
        if cache is None:
            cache = {}
            pdf._cid_cmap_cache = cache
        cache_key = id(font_stream)
        entry = cache.get(cache_key)
        if entry is not None and entry[0] is font_stream:
            reverse = entry[1]
        else:
            if len(cache) >= 16:
                pdf.warnings.append("WARN: 문서 TrueType cmap 스캔 한도 초과 — CID 복원 보류")
                return None
            warning_count = len(pdf.warnings)
            font_bytes = pdf.decode_stream_bytes(font_stream)
            if not font_bytes:
                # The existing CID warning covers a corrupt optional font stream;
                # keep document-wide budget warnings from the decoder.
                pdf.warnings[warning_count:] = [warning for warning in pdf.warnings[warning_count:]
                                                if not warning.startswith("WARN: FlateDecode 실패")]
                cache[cache_key] = (font_stream, {})
                return None
            if len(font_bytes) > MAX_FONT_BYTES:
                pdf.warnings.append("WARN: 내장 TrueType 글꼴 크기 한도 초과 — CID 복원 보류")
                return None
            reverse = reverse_truetype_cmap(font_bytes)
            cache[cache_key] = (font_stream, reverse)
        if not reverse:
            return None
        gid_bytes = None
        if isinstance(gid_object, PDFStream):
            if len(gid_object.raw) > 131072:
                return None
            gid_bytes = pdf.decode_stream_bytes(gid_object)
            if len(gid_bytes) > 131072:
                return None
        elif gid_object is not None and gid_object != "Identity":
            return None
        if gid_bytes is None:
            return CIDDecoder(lambda cid: reverse.get(cid, ""), pdf.warnings, name,
                              next((gid for gid, value in reverse.items() if value == " "), None))
        space_gid = next((gid for gid, value in reverse.items() if value == " "), None)
        space_cid = (next((cid for cid in range(len(gid_bytes) // 2)
                           if int.from_bytes(gid_bytes[2 * cid:2 * cid + 2], "big") == space_gid), None)
                     if space_gid is not None else None)
        return CIDDecoder(lambda cid: reverse.get(int.from_bytes(gid_bytes[2 * cid:2 * cid + 2], "big"), "")
                          if 2 * cid + 2 <= len(gid_bytes) else "", pdf.warnings, name,
                          space_cid)

    def _page_images(self, pdf: PDFFile, resources, page_number: int) -> list:
        """페이지 XObject 이미지에서 바이너리를 추출해 Image 요소로 반환."""
        if not isinstance(resources, dict):
            return []
        xobjects = pdf.resolve(resources.get("XObject"))
        if not isinstance(xobjects, dict):
            return []
        images = []
        for name, ref in xobjects.items():
            if len(images) >= MAX_IMAGES_PER_PAGE:
                break
            xobj = pdf.resolve(ref)
            if not isinstance(xobj, PDFStream) \
                    or str(xobj.dictionary.get("Subtype", "")) != "Image":
                continue
            data, ext = extract_image_bytes(xobj, pdf.warnings, pdf.decode_image_bytes)
            if not data:
                continue
            images.append(Image(
                image_data=data,
                image_format=ext,
                provenance=Provenance(source_format="pdf", page=page_number, path=str(name)),
            ))
        return images

    def _page_has_images(self, pdf: PDFFile, resources) -> bool:
        if not isinstance(resources, dict):
            return False
        xobjects = pdf.resolve(resources.get("XObject"))
        if not isinstance(xobjects, dict):
            return False
        for ref in xobjects.values():
            xobj = pdf.resolve(ref)
            if isinstance(xobj, PDFStream) \
                    and str(xobj.dictionary.get("Subtype", "")) == "Image":
                return True
        return False
