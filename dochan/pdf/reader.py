"""네이티브 PDF 리더 — 단순 디지털 PDF 의 페이지 텍스트 추출.

Phase 1 범위: 고전 xref 테이블, Flate/ASCIIHex/ASCII85 필터,
텍스트 연산자, ToUnicode CMap. 암호화·xref 스트림·객체 스트림·
스캔 전용 페이지는 명확한 경고로 보고한다.
"""
import os
from typing import Callable, Dict

from ..conversion import Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from .content import ContentTextExtractor, default_byte_decoder
from .cmap import parse_tounicode
from .filters import decode_stream
from .objects import PDFStream
from .structure import PDFFile

MAX_FILE_SIZE = 500 * 1024 * 1024


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

        pdf = PDFFile(data)
        if pdf.encrypted:
            doc.errors.extend(pdf.warnings)
            return doc

        for page_number, (page, resources) in enumerate(pdf.pages(), start=1):
            section = Section(
                provenance=Provenance(source_format="pdf", page=page_number)
            )
            content_parts = self._page_content_parts(pdf, page)
            lines = []
            if content_parts:
                extractor = ContentTextExtractor(self._font_decoders(pdf, resources))
                for part in content_parts:
                    lines.extend(extractor.extract(part))
            if not lines and self._page_has_images(pdf, resources):
                pdf.warnings.append(
                    f"WARN: {page_number}페이지: 텍스트 없음 — 스캔 이미지로 추정 (OCR 미지원)"
                )
            for line in lines:
                section.elements.append(
                    Paragraph(
                        runs=[TextRun(line)],
                        provenance=Provenance(source_format="pdf", page=page_number),
                    )
                )
            doc.sections.append(section)

        doc.errors.extend(pdf.warnings)
        return doc

    def _page_content_parts(self, pdf: PDFFile, page: dict) -> list:
        contents = pdf.resolve(page.get("Contents"))
        streams = contents if isinstance(contents, list) else [contents]
        parts = []
        for item in streams:
            stream = pdf.resolve(item)
            if isinstance(stream, PDFStream):
                decoded = decode_stream(stream.dictionary, stream.raw, pdf.warnings)
                if decoded:
                    parts.append(decoded)
        return parts

    def _font_decoders(self, pdf: PDFFile, resources) -> Dict[str, Callable[[bytes], str]]:
        decoders: Dict[str, Callable[[bytes], str]] = {}
        if not isinstance(resources, dict):
            return decoders
        fonts = pdf.resolve(resources.get("Font"))
        if not isinstance(fonts, dict):
            return decoders
        for name, font_ref in fonts.items():
            font = pdf.resolve(font_ref)
            if not isinstance(font, dict):
                continue
            to_unicode = pdf.resolve(font.get("ToUnicode"))
            if isinstance(to_unicode, PDFStream):
                cmap_data = decode_stream(to_unicode.dictionary, to_unicode.raw, pdf.warnings)
                if cmap_data:
                    cmap = parse_tounicode(cmap_data)
                    if cmap.mapping:
                        decoders[str(name)] = cmap.decode
                        continue
            decoders[str(name)] = default_byte_decoder
        return decoders

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
