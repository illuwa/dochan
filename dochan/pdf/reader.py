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
from .objects import PDFName, PDFRef, PDFStream
from .structure import PDFFile

MAX_FILE_SIZE = 500 * 1024 * 1024


def _drop_decoder(raw: bytes) -> str:
    return ""


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
            if pdf.encrypted:
                doc.errors.extend(pdf.warnings)
                return doc
            pages = pdf.pages()
        except Exception as e:
            doc.errors.append(f"ERR: PDF 구조 파싱 실패: {e!r}")
            return doc

        font_cache = {}
        for page_number, (page, resources) in enumerate(pages, start=1):
            section = Section(
                provenance=Provenance(source_format="pdf", page=page_number)
            )
            try:
                content_parts = self._page_content_parts(pdf, page)
                lines = []
                if content_parts:
                    extractor = ContentTextExtractor(
                        self._font_decoders(pdf, resources, font_cache)
                    )
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
            except Exception as e:
                pdf.warnings.append(f"WARN: {page_number}페이지 파싱 실패: {e!r}")
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

    def _font_decoders(self, pdf: PDFFile, resources, font_cache: dict) -> Dict[str, Callable[[bytes], str]]:
        decoders: Dict[str, Callable[[bytes], str]] = {}
        if not isinstance(resources, dict):
            return decoders
        fonts = pdf.resolve(resources.get("Font"))
        if not isinstance(fonts, dict):
            return decoders
        for name, font_ref in fonts.items():
            # 같은 폰트를 페이지마다 다시 해석하지 않는다 — 수백 페이지 문서에서
            # ToUnicode 압축 해제·CMap 파싱이 페이지 수만큼 반복되는 것을 막는다
            cache_key = font_ref if isinstance(font_ref, PDFRef) else None
            if cache_key is not None and cache_key in font_cache:
                decoders[str(name)] = font_cache[cache_key]
                continue
            font = pdf.resolve(font_ref)
            if not isinstance(font, dict):
                continue
            decoder = self._build_font_decoder(pdf, str(name), font)
            decoders[str(name)] = decoder
            if cache_key is not None:
                font_cache[cache_key] = decoder
        return decoders

    def _build_font_decoder(self, pdf: PDFFile, name: str, font: dict) -> Callable[[bytes], str]:
        to_unicode = pdf.resolve(font.get("ToUnicode"))
        if isinstance(to_unicode, PDFStream):
            cmap_data = decode_stream(to_unicode.dictionary, to_unicode.raw, pdf.warnings)
            if cmap_data:
                cmap = parse_tounicode(cmap_data)
                if cmap.mapping:
                    return cmap.decode
        # ToUnicode 없는 CID 폰트를 cp1252 로 해석하면 NUL 등 제어문자가
        # 본문으로 새어 나간다 — 경고를 남기고 해당 텍스트는 버린다 (감수 M4)
        encoding = font.get("Encoding")
        encoding_name = str(encoding) if isinstance(encoding, PDFName) else ""
        if str(font.get("Subtype", "")) == "Type0" or encoding_name.startswith("Identity-"):
            pdf.warnings.append(
                f"WARN: 폰트 {name}: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음"
            )
            return _drop_decoder
        return default_byte_decoder

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
