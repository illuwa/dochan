"""
reader.py — 통합 진입점 (HWP/HWPX 자동 판별)
사용 예:
  from dochan import HWPReader
  doc = Dochan("공문서.hwp")
  print(doc.to_markdown())
"""

import os
import olefile

from .model.document import Document
from .hwp.header import FileHeader
from .hwp.doc_info import DocInfoParser
from .hwp.section import SectionParser
from .hwp.bin_data import extract_bin_data, link_images_to_bin_data
from .hwpx.parser import HWPXParser
from .office_binary.doc import DOCReader
from .office_binary.ppt import PPTReader
from .office_binary.xls import XLSReader
from .ooxml.docx import DOCXReader
from .ooxml.package import detect_ooxml_format
from .ooxml.pptx import PPTXReader
from .ooxml.xlsx import XLSXReader
from .output.markdown import to_markdown
from .output.json_out import to_json, to_dict
from .output.plain_text import to_plain_text


class Dochan:
    """HWP/HWPX 통합 리더"""

    def __init__(self, file_path: str, ocr: bool = False):
        """
        Args:
            file_path: HWP/HWPX 파일 경로
            ocr: True면 이미지에서 텍스트 OCR 추출 (Tesseract 필요)
        """
        self.file_path = file_path
        self.doc = Document()
        self._ocr = ocr
        self._parse()
        if ocr:
            self._run_ocr()

    def _parse(self):
        ext = os.path.splitext(self.file_path)[1].lower()

        if ext == '.hwpx':
            self._parse_hwpx()
        elif ext == '.hwp':
            self._parse_hwp()
        elif ext == '.doc':
            self._parse_doc()
        elif ext == '.ppt':
            self._parse_ppt()
        elif ext == '.xls':
            self._parse_xls()
        elif ext == '.docx':
            self._parse_docx()
        elif ext == '.pptx':
            self._parse_pptx()
        elif ext == '.xlsx':
            self._parse_xlsx()
        else:
            # 매직 바이트로 판별
            with open(self.file_path, 'rb') as f:
                magic = f.read(8)
            if magic[:4] == b'\xd0\xcf\x11\xe0':  # OLE 매직
                self._parse_hwp()
            elif magic[:2] == b'PK':  # ZIP 매직
                ooxml_format = detect_ooxml_format(self.file_path)
                if ooxml_format == 'docx':
                    self._parse_docx()
                elif ooxml_format == 'pptx':
                    self._parse_pptx()
                elif ooxml_format == 'xlsx':
                    self._parse_xlsx()
                elif ooxml_format:
                    self.doc.errors.append(f"ERR: 아직 지원하지 않는 OOXML 형식: {ooxml_format}")
                else:
                    self._parse_hwpx()
            else:
                self.doc.errors.append(f"ERR: 알 수 없는 파일 형식: {self.file_path}")

    def _parse_hwp(self):
        """HWP (OLE 바이너리) 파싱"""
        try:
            ole = olefile.OleFileIO(self.file_path)
        except Exception as e:
            self.doc.errors.append(f"ERR: OLE 파일 열기 실패: {e}")
            return

        try:
            # 1. FileHeader
            header_data = ole.openstream('FileHeader').read()
            file_header = FileHeader.parse(header_data)
            self.doc.file_header = file_header

            # 유효성 검사
            issues = file_header.validate()
            self.doc.errors.extend(issues)

            # 암호화/DRM 체크
            if file_header.is_encrypted or file_header.is_drm:
                self.doc.errors.append("WARN: 암호화/DRM 문서 — 파싱 제한적")
                return

            # 2. DocInfo
            doc_info_parser = DocInfoParser()
            doc_info_data = ole.openstream('DocInfo').read()
            doc_info = doc_info_parser.parse_stream(doc_info_data, file_header.is_compressed)

            self.doc.char_shapes = doc_info.char_shapes
            self.doc.para_shapes = doc_info.para_shapes
            self.doc.styles = doc_info.styles
            self.doc.face_names = doc_info.face_names
            self.doc.bin_data_list = doc_info.bin_data_entries
            self.doc.errors.extend(doc_info.errors)

            # 3. BodyText 섹션들
            body_storage = file_header.body_storage
            VALID_STORAGES = {"BodyText", "ViewText"}
            if body_storage not in VALID_STORAGES:
                self.doc.errors.append(f"ERR: 잘못된 스토리지: {body_storage}")
                ole.close()
                return

            section_parser = SectionParser(doc_info=doc_info)
            MAX_SECTIONS = 1000

            section_idx = 0
            while section_idx < MAX_SECTIONS:
                stream_name = f"{body_storage}/Section{section_idx}"
                if not ole.exists(stream_name):
                    break

                try:
                    stream_data = ole.openstream(stream_name).read()
                    section = section_parser.parse_stream(stream_data, file_header.is_compressed)
                    self.doc.sections.append(section)
                except Exception as e:
                    self.doc.errors.append(f"섹션 {section_idx} 파싱 실패: {e}")

                section_idx += 1

            self.doc.errors.extend(section_parser.errors)

            # 4. BinData 이미지 연결
            try:
                bin_items = extract_bin_data(ole, file_header.is_compressed)
                link_images_to_bin_data(self.doc, bin_items, doc_info.bin_data_entries)
            except Exception as e:
                self.doc.errors.append(f"BinData 연결 실패: {e}")

        finally:
            ole.close()

    def _parse_hwpx(self):
        """HWPX (ZIP/XML) 파싱"""
        parser = HWPXParser()
        self.doc = parser.parse(self.file_path)

    def _parse_xls(self):
        """XLS (BIFF/OLE) 파싱"""
        self.doc = XLSReader().read(self.file_path)

    def _parse_doc(self):
        """DOC (Word Binary/OLE) 파싱"""
        self.doc = DOCReader().read(self.file_path)

    def _parse_ppt(self):
        """PPT (PowerPoint Binary/OLE) 파싱"""
        self.doc = PPTReader().read(self.file_path)

    def _parse_docx(self):
        """DOCX (Office Open XML) 파싱"""
        self.doc = DOCXReader().read(self.file_path)

    def _parse_pptx(self):
        """PPTX (Office Open XML) 파싱"""
        self.doc = PPTXReader().read(self.file_path)

    def _parse_xlsx(self):
        """XLSX (Office Open XML) 파싱"""
        self.doc = XLSXReader().read(self.file_path)

    def _run_ocr(self):
        """모든 이미지에 OCR 실행 (표 셀 안 이미지 포함)"""
        from .utils.ocr import is_ocr_available

        if not is_ocr_available():
            self.doc.errors.append("WARN: Tesseract OCR 미설치 — OCR 건너뜀")
            return

        images = self.doc.find_all('image')
        for img in images:
            if img.has_data and not img.ocr_text:
                img.run_ocr()

    # ── 출력 메서드 ──

    def to_markdown(self) -> str:
        return to_markdown(self.doc)

    def to_json(self, indent: int = 2) -> str:
        return to_json(self.doc, indent=indent)

    def to_dict(self) -> dict:
        return to_dict(self.doc)

    def to_plain_text(self) -> str:
        return to_plain_text(self.doc)

    def find_all(self, element_type: str):
        return self.doc.find_all(element_type)

    @property
    def metadata(self) -> dict:
        return self.doc.metadata

    @property
    def errors(self) -> list:
        return self.doc.errors

# 하위 호환 별칭
HWPReader = Dochan
