"""네이티브 PDF 리더 — 단순 디지털 PDF 의 페이지 텍스트 추출.

Phase 1 범위: 고전 xref 테이블, Flate/ASCIIHex/ASCII85 필터,
텍스트 연산자, ToUnicode CMap. 암호화·xref 스트림·객체 스트림·
스캔 전용 페이지는 명확한 경고로 보고한다.
"""
import os
from typing import Callable, Dict, Optional

from ..conversion import Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.image import Image
from .content import ContentTextExtractor, FontInfo, default_byte_decoder
from .cmap import parse_tounicode
from .images import extract_image_bytes
from .objects import PDFName, PDFRef, PDFStream
from .structure import PDFFile
from .widths import WidthMap
from .tables import TableBudget, build_tables
from .layout import merge_lines

MAX_IMAGES_PER_PAGE = 64

MAX_FILE_SIZE = 500 * 1024 * 1024
MAX_CONTENT_PARTS = 256  # 페이지당 콘텐츠 스트림 수 — 반복 참조 CPU 증폭 방지
MAX_OUTLINE_ITEMS = 1000
MAX_OUTLINE_DEPTH = 32


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
    if not isinstance(value, bytes):
        return ""
    if value[:2] == b"\xfe\xff":
        return value[2:].decode("utf-16-be", errors="replace")
    return default_byte_decoder(value)


class PDFReader:
    format_name = "pdf"
    extensions = (".pdf",)

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
            pdf = PDFFile(data)
            if pdf.encrypted and not pdf.decrypt_ok:
                doc.errors.extend(pdf.warnings)
                return doc
            pages = pdf.pages()
        except Exception as e:
            doc.errors.append(f"ERR: PDF 구조 파싱 실패: {e!r}")
            return doc

        outline_section = self._outline_section(pdf, pages)
        if outline_section is not None:
            doc.sections.append(outline_section)

        font_cache = {}
        table_budget = TableBudget()
        for page_number, (page, resources) in enumerate(pages, start=1):
            section = Section(
                provenance=Provenance(source_format="pdf", page=page_number)
            )
            try:
                content_parts = self._page_content_parts(pdf, page)
                lines = []
                groups = []
                tables = []
                page_content = None
                if content_parts:
                    extractor = ContentTextExtractor.from_fonts(
                        self._font_infos(pdf, resources, font_cache)
                    )
                    page_content = extractor.extract_page(b"\n".join(content_parts))
                    pdf.warnings.extend(page_content.warnings)
                    try:
                        tables = build_tables(page_content.segments, page_content.fragments,
                                              page_number=page_number, warnings=pdf.warnings,
                                              budget=table_budget)
                    except Exception as e:
                        pdf.warnings.append(f"WARN: {page_number}페이지 표 복원 실패: {e!r}")
                    groups = self._body_groups(extractor, page_content.fragments, tables)
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
                median_size = _median_font_size([(ln.text, ln.size) for ln in lines])
                ordered = [(t.anchor_order, 0, t.table) for t in tables]
                for group in groups:
                    for block in merge_lines(group):
                        paragraph = block.paragraph(page_number)
                        paragraph.heading_level = _heading_level_for_size(
                            block.text, block.size, median_size)
                        ordered.append((block.order, 1, paragraph))
                section.elements.extend(item for _, _, item in sorted(
                    ordered, key=lambda event: (event[0], event[1])))
                section.elements.extend(self._link_paragraphs(pdf, page, page_number))
                section.elements.extend(image_elems)
                for img in image_elems:
                    if img.image_data:
                        doc.assets.append(img)
            except Exception as e:
                pdf.warnings.append(f"WARN: {page_number}페이지 파싱 실패: {e!r}")
            doc.sections.append(section)

        # 같은 경고가 페이지 수만큼 중복 누적되지 않게 순서 보존 dedup
        seen = set()
        for warning in pdf.warnings:
            if warning not in seen:
                seen.add(warning)
                doc.errors.append(warning)
        return doc

    @staticmethod
    def _body_groups(extractor, fragments, tables):
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
        pending = []
        for _, kind, event in sorted(events, key=lambda e: (e[0], e[1])):
            if kind:
                pending.append(event)
            else:
                groups.append(extractor._assemble_lines(pending))
                pending = []
        groups.append(extractor._assemble_lines(pending))
        # 크기 없는 비정상 텍스트는 좌표로 같은 줄임을 보장할 수 없다.
        if fragments and all(f.size == 0 for f in fragments):
            groups = [extractor._assemble_lines([f]) for f in fragments
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
        for annot_ref in annots[:MAX_CONTENT_PARTS]:
            annot = pdf.resolve(annot_ref)
            if not isinstance(annot, dict) or str(annot.get("Subtype", "")) != "Link":
                continue
            action = pdf.resolve(annot.get("A"))
            uri = None
            if isinstance(action, dict) and str(action.get("S", "")) == "URI":
                uri = pdf.resolve(action.get("URI"))
            url = _pdf_text_string(uri).strip() if isinstance(uri, bytes) else ""
            if not url or url in seen:
                continue
            seen.add(url)
            provenance = Provenance(source_format="pdf", page=page_number, path="annots")
            paragraphs.append(
                Paragraph(
                    runs=[TextRun(text=f"<{url}>", link=url, provenance=provenance)],
                    provenance=provenance,
                )
            )
        return paragraphs

    def _page_content_parts(self, pdf: PDFFile, page: dict) -> list:
        contents = pdf.resolve(page.get("Contents"))
        streams = contents if isinstance(contents, list) else [contents]
        if len(streams) > MAX_CONTENT_PARTS:
            pdf.warnings.append(
                f"WARN: 페이지 콘텐츠 스트림 수가 한도({MAX_CONTENT_PARTS})를 초과 — 일부만 파싱"
            )
            streams = streams[:MAX_CONTENT_PARTS]
        parts = []
        for item in streams:
            stream = pdf.resolve(item)
            if isinstance(stream, PDFStream):
                decoded = pdf.decode_stream_bytes(stream)
                if decoded:
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
        return FontInfo(decode=decoder, widths=widths, code_bytes=code_bytes,
                        bold=bold, italic=italic)

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
        return WidthMap({}, 500.0)

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
            resolved = [pdf.resolve(x) for x in w]
            return WidthMap.cid(resolved, default_width=default)
        return WidthMap({}, default)

    def _build_font_decoder(self, pdf: PDFFile, name: str, font: dict) -> Callable[[bytes], str]:
        to_unicode = pdf.resolve(font.get("ToUnicode"))
        if isinstance(to_unicode, PDFStream):
            cmap_data = pdf.decode_stream_bytes(to_unicode)
            if cmap_data:
                cmap = parse_tounicode(cmap_data, pdf.warnings)
                if cmap.mapping:
                    return cmap.decode
        # ToUnicode 없는 CID 폰트를 cp1252 로 해석하면 NUL 등 제어문자가
        # 본문으로 새어 나간다 — 경고를 남기고 해당 텍스트는 버린다 (감수 M4)
        encoding = pdf.resolve(font.get("Encoding"))
        if isinstance(encoding, dict):
            encoding = pdf.resolve(encoding.get("BaseEncoding"))
        encoding_name = str(encoding) if isinstance(encoding, PDFName) else ""
        if str(font.get("Subtype", "")) == "Type0" or encoding_name.startswith("Identity-"):
            pdf.warnings.append(
                f"WARN: 폰트 {name}: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음"
            )
            return _drop_decoder
        if encoding_name == "MacRomanEncoding":
            return lambda raw: raw.decode("mac_roman", errors="replace")
        return default_byte_decoder

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
            data, ext = extract_image_bytes(xobj, pdf.warnings)
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
