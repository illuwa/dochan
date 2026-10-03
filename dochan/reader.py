"""
reader.py — 통합 진입점 (HWP/HWPX 자동 판별)
사용 예:
  from dochan import HWPReader
  doc = Dochan("공문서.hwp")
  print(doc.to_markdown())
"""

import os
import re

from dochan import cfb
from .cfb import append_recovery_warnings

from .hwp.bin_data import extract_bin_data, link_images_to_bin_data
from .hwp.distdoc import decode_distribution_section
from .hwp.doc_info import DocInfoParser
from .hwp.header import FileHeader
from .hwp.section import HWPRecordLimitError, SectionParser
from .hwpx.parser import HWPXParser
from .hwpx.revisions import validate_revision_mode
from .model.document import Document
from .office_binary.doc import DOCReader
from .office_binary.ppt import PPTReader
from .office_binary.xls import XLSReader
from .ooxml.docx import DOCXReader
from .ooxml.package import detect_ooxml_format
from .ooxml.pptx import PPTXReader
from .ooxml.xlsx import XLSXReader
from .output.json_out import to_dict, to_json
from .output.markdown import to_markdown
from .output.plain_text import to_plain_text
from .pdf.reader import PDFReader
from .utils.bounded_io import (
    MAX_OLE_DOCUMENT_SIZE,
    MAX_OLE_STREAM_SIZE,
    BoundedIOError,
    ByteBudget,
    ResourceLimitError,
    read_ole_stream,
    validate_file_size,
)

HWP_FILE_HEADER_SIZE = 256


class Dochan:
    """HWP/HWPX 통합 리더"""

    def __init__(self, file_path: str, ocr: bool = False, pdf_text_tables: bool = False, *,
                 include_assets: bool = True, revision_mode: str = "preserve", password=None):
        """
        Args:
            file_path: HWP/HWPX 파일 경로
            ocr: True면 이미지에서 텍스트 OCR 추출 (Tesseract 필요)
            pdf_text_tables: True면 PDF의 괘선 없는 표 복원
            include_assets: False면 HWPX 이미지 바이너리만 로드하지 않고
                참조·대체 텍스트·캡션은 보존한다. 기본 True는 기존 동작이다.
                False는 확장자와 무관하게 HWPX로 식별되는 패키지만 지원한다.
            revision_mode: preserve(기본, 삽입·삭제를 포함한 모든 텍스트 보존), final(삭제 제외),
                original(삽입 제외). 비기본 모드는 HWP 5와 HWPX를 지원하며 미확정
                범위·서식 변경은 보존하고 errors에 부분지원 사유를 기록한다.
                변경 추적 HWP의 preserve는 ViewText, final은 저장된 BodyText를 읽는다.
            password: str 형식의 문서 열기 암호. None이면 빈 암호 또는 형식의 기본 암호만 시도한다.

        Raises:
            TypeError: password가 str 또는 None이 아닌 경우.
            ValueError: include_assets=False인데 ocr=True이거나 입력이
                HWPX로 식별되지 않는 경우 (다른 포맷·모호한 패키지 포함).
                revision_mode가 잘못되었거나 비기본 모드에 유효 HWP 5/HWPX가 아닌 입력.
        """
        if password is not None and not isinstance(password, str):
            raise TypeError("password must be str or None")
        self.file_path = file_path
        self._zip_kind_cache = None
        # 옵션 오류는 문서 파싱 오류와 달리 호출자에게 직접 알린다.
        validate_revision_mode(revision_mode)
        if revision_mode != "preserve" and not self._is_plain_hwpx() and not self._is_plain_hwp():
            raise ValueError("revision_mode other than 'preserve' is supported only for HWPX packages or valid HWP 5 documents")
        if not include_assets:
            if ocr:
                raise ValueError("ocr=True cannot be used with include_assets=False")
            if not self._is_plain_hwpx():
                raise ValueError("include_assets=False is supported only for HWPX packages")
        self.doc = Document()
        self._ocr = ocr
        self._pdf_text_tables = pdf_text_tables
        self._include_assets = include_assets
        self._revision_mode = revision_mode
        self._password = password
        try:
            if password is not None and len(password) > 4096:
                self.doc.errors.append("ERR: 암호화된 문서 — 암호 형식 또는 길이가 지원 범위를 벗어남")
            else:
                self._parse()
        finally:
            # 파싱이 끝난 리더 객체에 암호를 보관하지 않는다.
            self._password = None
        if ocr:
            self._run_ocr()

    def save_images(self, out_dir: str, stem: str = "") -> list:
        """문서의 이미지 바이너리를 out_dir 에 `<stem>-image-NNN.<ext>` 로 저장하고 경로 목록을 돌려준다."""
        from .utils.image_export import export_images

        stem = stem or os.path.splitext(os.path.basename(self.file_path))[0]
        return export_images(self.doc, out_dir, stem)

    def _parse(self):
        # 손상/악성 문서는 정상 흐름이다 — 어떤 파서 예외도 라이브러리
        # 호출자에게 전파하지 않고 doc.errors 로 강등한다
        try:
            self._parse_dispatch()
        except Exception as e:
            self.doc.errors.append(f"ERR: 문서 파싱 실패: {e!r}")

    def _parse_dispatch(self):
        ext = os.path.splitext(self.file_path)[1].lower()
        try:
            with open(self.file_path, 'rb') as f:
                magic = f.read(8)
        except OSError:
            magic = b''

        # 컨테이너 시그니처가 확장자보다 우선한다. 확장자는 시그니처가
        # 없는 잘린 파일에서만 fallback 으로 쓴다.
        if magic[:4] == b'\xd0\xcf\x11\xe0':
            formats = self._detect_ole_formats()
            if len(formats) > 1:
                self.doc.errors.append(
                    "ERR: 모호한 OLE 파일 형식: " + ", ".join(formats)
                )
            elif formats == ["hwp"]:
                self._parse_hwp()
            elif formats == ["doc"]:
                self._parse_doc()
            elif formats == ["ppt"]:
                self._parse_ppt()
            elif formats == ["xls"]:
                self._parse_xls()
            elif formats == ["encrypted_ooxml"]:
                self._parse_encrypted_ooxml()
            else:
                self.doc.errors.append("ERR: 지원하지 않는 OLE 스트림 구조")
            return

        if magic[:2] == b'PK':
            ooxml_format, is_hwpx = self._zip_kind()
            if ooxml_format and ooxml_format != 'ambiguous' and is_hwpx:
                self.doc.errors.append("ERR: 모호한 ZIP 문서 형식")
            elif ooxml_format == 'docx':
                self._parse_docx()
            elif ooxml_format == 'pptx':
                self._parse_pptx()
            elif ooxml_format == 'xlsx':
                self._parse_xlsx()
            elif ooxml_format == 'ambiguous':
                self.doc.errors.append("ERR: 모호한 OOXML 파일 형식")
            elif is_hwpx:
                self._parse_hwpx()
            elif ext == '.docx':
                self._parse_docx()
            elif ext == '.pptx':
                self._parse_pptx()
            elif ext == '.xlsx':
                self._parse_xlsx()
            elif ext == '.hwpx':
                self._parse_hwpx()
            elif ooxml_format:
                self.doc.errors.append(f"ERR: 아직 지원하지 않는 OOXML 형식: {ooxml_format}")
            else:
                self.doc.errors.append("ERR: 지원하지 않는 ZIP 문서 형식")
            return

        # PDF 는 OLE/ZIP 컨테이너가 아니므로 시그니처로 따로 잡는다.
        if magic[:5] == b'%PDF-':
            self._parse_pdf_family()
            return

        if ext in ('.hwpx', '.hwp'):
            self._parse_hwp_family(ext)
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
        elif ext == '.pdf':
            self._parse_pdf_family()
        else:
            self.doc.errors.append(f"ERR: 알 수 없는 파일 형식: {self.file_path}")

    def _zip_kind(self):
        """(OOXML 형식, HWPX 여부)를 한 번만 판별한다 — 옵션 검증과 분기가 공유."""
        if self._zip_kind_cache is None:
            self._zip_kind_cache = (
                detect_ooxml_format(self.file_path), self._is_hwpx_package(),
            )
        return self._zip_kind_cache

    def _is_plain_hwpx(self) -> bool:
        ooxml_format, is_hwpx = self._zip_kind()
        return is_hwpx and not ooxml_format

    def _is_hwpx_package(self) -> bool:
        import zipfile

        try:
            with zipfile.ZipFile(self.file_path, "r") as archive:
                if len(archive.filelist) > 10000:
                    return False
                try:
                    info = archive.getinfo("mimetype")
                except KeyError:
                    return False
                if info.file_size > 128:
                    return False
                with archive.open(info) as stream:
                    marker = stream.read(129)
                return marker.strip() == b"application/hwp+zip"
        except (OSError, ValueError, zipfile.BadZipFile):
            return False

    def _is_plain_hwp(self):
        """비기본 변경 추적 옵션은 실제 HWP 5 컨테이너만 허용한다."""
        try:
            if self._detect_ole_formats() != ["hwp"]:
                return False
            with cfb.OleFileIO(self.file_path) as ole:
                data = read_ole_stream(ole, 'FileHeader', max_bytes=HWP_FILE_HEADER_SIZE,
                                       expected_size=HWP_FILE_HEADER_SIZE)
            header = FileHeader.parse(data)
            return 'HWP Document File' in header.signature and header.major_version >= 5
        except Exception:
            return False

    def _parse_hwp_family(self, ext: str):
        """확장자가 .hwp/.hwpx 인 파일을 파싱.

        일부 공개 출처는 파일명 확장자와 실제 내용이 어긋난 채로 배포한다
        (예: 파일명은 .hwp인데 실제로는 ZIP/HWPX 패키지, 또는 그 반대).
        확장자만 믿고 파서를 고정하면 실제로는 멀쩡한 문서도 그대로
        실패하므로, 매직바이트를 먼저 확인해 실제 포맷에 맞는 파서로
        보정한다. 매직바이트가 둘 다 아니면(잘린 파일 등) 확장자를
        그대로 신뢰해 기존과 동일하게 동작한다.
        """
        try:
            with open(self.file_path, 'rb') as f:
                magic = f.read(8)
            if magic[:4] == b'\xd0\xcf\x11\xe0':  # OLE 매직
                self._parse_hwp()
                return
            if magic[:2] == b'PK':  # ZIP 매직
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
                return
            if magic[:5] == b'%PDF-':
                self._parse_pdf()
                return
        except OSError:
            magic = b''

        # 매직바이트가 어느 쪽도 아니면(잘린 파일 등) 확장자를 그대로 신뢰한다.
        if ext.lstrip('.') == 'hwpx':
            self._parse_hwpx()
        else:
            self._parse_hwp()

    def _detect_ole_formats(self):
        """확장자 없는 OLE 문서를 표준 스트림 구성으로 식별한다."""
        validate_file_size(self.file_path, MAX_OLE_DOCUMENT_SIZE)
        ole = cfb.OleFileIO(self.file_path)
        try:
            # 암호 패키지에는 구버전 Office용 WordDocument 안내 스트림도
            # 함께 들어간다. 복호화한 패키지의 내용으로 실제 형식을 판별한다.
            if ole.exists("EncryptionInfo") or ole.exists("EncryptedPackage"):
                return ["encrypted_ooxml"]
            formats = []
            if ole.exists("FileHeader") and ole.exists("DocInfo"):
                formats.append("hwp")
            if ole.exists("WordDocument"):
                formats.append("doc")
            if ole.exists("PowerPoint Document"):
                formats.append("ppt")
            if ole.exists("Workbook") or ole.exists("Book"):
                formats.append("xls")
            return formats
        finally:
            # Option validation calls detection before the Document exists.
            if hasattr(self, "doc"):
                append_recovery_warnings(ole, self.doc.errors)
            ole.close()

    def _parse_hwp(self):
        """HWP (OLE 바이너리) 파싱"""
        self.doc.source_format = "hwp"
        try:
            validate_file_size(self.file_path, MAX_OLE_DOCUMENT_SIZE)
        except ResourceLimitError as e:
            self.doc.errors.append(f"ERR: HWP stream validation failed: {e}")
            return

        try:
            ole = cfb.OleFileIO(self.file_path)
        except Exception as e:
            self.doc.errors.append(f"ERR: OLE 파일 열기 실패: {e}")
            return

        try:
            stream_budget = ByteBudget(MAX_OLE_DOCUMENT_SIZE)
            # 1. FileHeader
            header_data = read_ole_stream(
                ole,
                'FileHeader',
                max_bytes=HWP_FILE_HEADER_SIZE,
                budget=stream_budget,
                expected_size=HWP_FILE_HEADER_SIZE,
            )
            file_header = FileHeader.parse(header_data)
            self.doc.file_header = file_header

            # 유효성 검사
            issues = file_header.validate()
            self.doc.errors.extend(issues)

            # 암호화/DRM 체크
            if file_header.is_encrypted or file_header.is_drm:
                self.doc.errors.append("ERR: 암호화/DRM 문서는 직접 파싱할 수 없음")
                return

            # 2. DocInfo
            doc_info_parser = DocInfoParser()
            doc_info_data = read_ole_stream(
                ole,
                'DocInfo',
                max_bytes=MAX_OLE_STREAM_SIZE,
                budget=stream_budget,
            )
            doc_info = doc_info_parser.parse_stream(doc_info_data, file_header.is_compressed)

            self.doc.char_shapes = doc_info.char_shapes
            self.doc.para_shapes = doc_info.para_shapes
            self.doc.styles = doc_info.styles
            self.doc.face_names = doc_info.face_names
            self.doc.bin_data_list = doc_info.bin_data_entries
            self.doc.errors.extend(doc_info.errors)
            if self._revision_mode == 'original':
                # HWPX와 같이 불완전한 변경 취소 투영은 성공 출력으로
                # 게시하지 않는다. 일반 서식 파싱 경고는 그대로 둔다.
                self.doc.errors = [
                    error.replace('WARN:', 'ERR:', 1)
                    if error.startswith('WARN: DocInfo 레코드 96 ') or
                    error.startswith('WARN: DocInfo 레코드 97 ') else error
                    for error in self.doc.errors
                ]

            # 3. BodyText 섹션들
            body_storage = file_header.body_storage
            if (file_header.is_track_change and not file_header.is_distribution
                    and self._revision_mode != 'final'):
                # 변경 추적 ViewText는 원본/삭제 구간을 포함한 압축 본문이며
                # 배포용 비트가 없으면 AES 암호문으로 다루지 않는다.
                if ole.exists('ViewText/Section0'):
                    body_storage = 'ViewText'
                else:
                    severity = 'WARN' if self._revision_mode == 'preserve' else 'ERR'
                    self.doc.errors.append(severity + ': HWP revision ViewText missing; final body preserved')
            VALID_STORAGES = {"BodyText", "ViewText"}
            if body_storage not in VALID_STORAGES:
                self.doc.errors.append(f"ERR: 잘못된 스토리지: {body_storage}")
                return

            # HWP BodyText already stores the accepted final text. Do not
            # project any residual range tags a second time. Distribution
            # ViewText remains subject to the existing range projection.
            section_parser = SectionParser(
                doc_info=doc_info, revision_mode=self._revision_mode,
                project_revisions=not (self._revision_mode == 'final' and body_storage == 'BodyText'),
            )
            MAX_SECTIONS = 1000

            section_indices = self._hwp_section_indices(
                ole,
                body_storage,
                doc_info.section_count,
                MAX_SECTIONS,
                self.doc.errors,
            )
            for section_idx in section_indices:
                stream_name = f"{body_storage}/Section{section_idx}"
                if not ole.exists(stream_name):
                    self.doc.errors.append(f"ERR: HWP section stream missing: {stream_name}")
                    continue

                try:
                    stream_data = read_ole_stream(
                        ole,
                        stream_name,
                        max_bytes=MAX_OLE_STREAM_SIZE,
                        budget=stream_budget,
                    )
                    fallback_name = f"BodyText/Section{section_idx}"
                    allow_body_fallback = (
                        self._revision_mode == 'preserve'
                        and file_header.is_track_change
                        and not file_header.is_distribution
                        and body_storage == 'ViewText'
                        and ole.exists(fallback_name)
                    )
                    try:
                        section = section_parser.parse_stream(
                            stream_data, file_header.is_compressed,
                            reject_record_limit=allow_body_fallback,
                            distribution_decoder=(decode_distribution_section
                                                  if file_header.is_distribution else None),
                        )
                    except HWPRecordLimitError:
                        # Reject ViewText before model/cell budgets are consumed.
                        # BodyText retains the same byte and record limits.
                        self.doc.errors.append(
                            f"WARN: HWP revision ViewText/Section{section_idx} record limit; "
                            f"{fallback_name} fallback attempted; deleted revision text unavailable"
                        )
                        stream_data = read_ole_stream(
                            ole, fallback_name, max_bytes=MAX_OLE_STREAM_SIZE,
                            budget=stream_budget,
                        )
                        section = section_parser.parse_stream(stream_data, file_header.is_compressed)
                    self.doc.sections.append(section)
                except BoundedIOError:
                    raise
                except Exception as e:
                    self.doc.errors.append(f"ERR: 섹션 {section_idx} 파싱 실패: {e}")
            self.doc.errors.extend(section_parser.errors)

            # 4. BinData 이미지 연결
            try:
                bin_items = extract_bin_data(
                    ole,
                    file_header.is_compressed,
                    stream_budget=stream_budget,
                    warnings=self.doc.errors,
                )
                link_images_to_bin_data(self.doc, bin_items, doc_info.bin_data_entries)
            except ResourceLimitError as e:
                # Body text is already parsed within its budgets; only the
                # images are dropped when their combined size runs out.
                self.doc.errors.append(f"WARN: HWP BinData 예산 초과로 그림 생략: {e}")
            except BoundedIOError:
                raise
            except Exception as e:
                self.doc.errors.append(f"WARN: BinData 연결 실패: {e}")

        except BoundedIOError as e:
            self.doc = Document(source_format="hwp")
            self.doc.errors.append(f"ERR: HWP stream validation failed: {e}")
        finally:
            append_recovery_warnings(ole, self.doc.errors)
            ole.close()

    @staticmethod
    def _hwp_section_indices(
        ole,
        body_storage: str,
        declared_count: int,
        limit: int,
        errors=None,
    ):
        discovered = set()
        try:
            for entry in ole.listdir(streams=True, storages=False):
                path = "/".join(entry) if isinstance(entry, (list, tuple)) else str(entry)
                match = re.fullmatch(re.escape(body_storage) + r"/Section(\d+)", path)
                if match:
                    discovered.add(int(match.group(1)))
        except (AttributeError, OSError):
            pass

        if declared_count > limit or any(index >= limit for index in discovered):
            error = f"ERR: HWP section index exceeds limit: maximum {limit - 1}"
            if errors is not None and error not in errors:
                errors.append(error)

        declared = set(range(min(max(declared_count, 0), limit)))
        if discovered or declared:
            return sorted(index for index in discovered | declared if index < limit)

        contiguous = []
        for index in range(limit):
            if not ole.exists(f"{body_storage}/Section{index}"):
                break
            contiguous.append(index)
        return contiguous

    def _parse_hwpx(self):
        """HWPX (ZIP/XML) 파싱"""
        parser = HWPXParser()
        self.doc = parser.parse(self.file_path, include_assets=self._include_assets,
                                revision_mode=self._revision_mode)

    def _parse_xls(self):
        """XLS (BIFF/OLE) 파싱"""
        options = {} if self._password is None else {'password': self._password}
        self.doc = XLSReader(**options).read(self.file_path)

    def _parse_doc(self):
        """DOC (Word Binary/OLE) 파싱"""
        options = {} if self._password is None else {'password': self._password}
        self.doc = DOCReader(**options).read(self.file_path)
        from .crypto.legacy import warn_irm_protection
        warn_irm_protection(self.file_path, self.doc.errors)

    def _parse_ppt(self):
        """PPT (PowerPoint Binary/OLE) 파싱"""
        options = {} if self._password is None else {'password': self._password}
        self.doc = PPTReader(**options).read(self.file_path)

    def _parse_encrypted_ooxml(self):
        """복호화한 ZIP을 디스크에 쓰지 않고 기존 OOXML 리더에 전달한다."""
        from io import BytesIO
        from .crypto.ooxml import decrypt_ooxml

        ole = None
        try:
            with cfb.OleFileIO(self.file_path) as ole:
                package_data = decrypt_ooxml(ole, self._password)
            with BytesIO(package_data) as package:
                kind = detect_ooxml_format(package)
                readers = {'docx': DOCXReader, 'pptx': PPTXReader, 'xlsx': XLSXReader}
                if kind not in readers:
                    import zipfile
                    with zipfile.ZipFile(package) as archive:
                        unsupported_xlsb = 'xl/workbook.bin' in archive.namelist()
                    reason = ("XLSB 형식은 미지원입니다." if unsupported_xlsb else
                              "복호화한 OOXML 패키지 형식이 잘못됨")
                    self.doc.errors.append("ERR: 암호화된 문서 — " + reason)
                    return
                package.seek(0)
                self.doc = readers[kind]().read(package)
        except Exception as exc:
            # Only native crypto diagnostics contain exclusively static text.
            from .crypto.ooxml import OOXMLCryptoError
            message = str(exc) if isinstance(exc, OOXMLCryptoError) else (
                "ERR: 암호화된 문서 — 암호가 없거나 틀림, 손상 또는 미지원 암호화 방식")
            self.doc.errors.append(message)
        finally:
            if ole is not None:
                append_recovery_warnings(ole, self.doc.errors)

    def _parse_docx(self):
        """DOCX (Office Open XML) 파싱"""
        self.doc = DOCXReader().read(self.file_path)

    def _parse_pptx(self):
        """PPTX (Office Open XML) 파싱"""
        self.doc = PPTXReader().read(self.file_path)

    def _parse_xlsx(self):
        """XLSX (Office Open XML) 파싱"""
        self.doc = XLSXReader().read(self.file_path)

    def _parse_pdf(self):
        """PDF (네이티브 파서) 파싱"""
        options = {} if self._password is None else {'password': self._password}
        self.doc = PDFReader(text_tables=self._pdf_text_tables, **options).read(self.file_path)
        if any(error.startswith(('WARN: 암호화된 PDF', 'WARN: 암호화 처리 실패'))
               for error in self.doc.errors):
            self.doc.errors.append("ERR: 암호화된 문서 — PDF 암호가 없거나 틀림 또는 미지원 암호화 방식")

    def _parse_pdf_family(self):
        """확장자가 .pdf 인 파일 파싱.

        _parse_hwp_family 와 같은 이유 — 일부 출처는 확장자와 실제 내용이
        어긋난 채로 배포하므로 매직바이트를 먼저 확인해 실제 포맷에 맞는
        파서로 보정한다. 어느 매직도 아니면 PDF 파서가 헤더 오류를 보고한다.
        """
        try:
            with open(self.file_path, 'rb') as f:
                magic = f.read(8)
        except OSError:
            magic = b''

        if magic[:4] == b'\xd0\xcf\x11\xe0':
            self._parse_hwp()
        elif magic[:2] == b'PK':
            ooxml_format = detect_ooxml_format(self.file_path)
            if ooxml_format == 'docx':
                self._parse_docx()
            elif ooxml_format == 'pptx':
                self._parse_pptx()
            elif ooxml_format == 'xlsx':
                self._parse_xlsx()
            else:
                self._parse_hwpx()
        else:
            self._parse_pdf()

    def _run_ocr(self):
        """모든 이미지에 OCR 실행 (표 셀 안 이미지 포함)"""
        from .utils.ocr import MIN_OCR_PYTHON, _python_supports_ocr, is_ocr_available

        if not is_ocr_available():
            if not _python_supports_ocr():
                required = '.'.join(map(str, MIN_OCR_PYTHON))
                self.doc.errors.append(f"WARN: OCR은 Python {required} 이상 필요 — OCR 건너뜀")
            else:
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
