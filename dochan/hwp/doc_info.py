"""
hwp/doc_info.py — DocInfo 스트림 파싱
DocInfo에는 문서 전체에서 참조하는 서식 정보가 포함됨:
- FaceName (글꼴 이름)
- CharShape (글자 모양)
- ParaShape (문단 모양)
- Style (스타일)
- BinData (바이너리 데이터 참조)
"""

import struct
from dataclasses import dataclass, field
from typing import List

from ..utils.safe_decompress import safe_zlib_decompress

from ..constants import (
    HWPTAG_DOCUMENT_PROPERTIES, HWPTAG_BIN_DATA, HWPTAG_FACE_NAME, HWPTAG_CHAR_SHAPE,
    HWPTAG_PARA_SHAPE, HWPTAG_STYLE,
)
from ..model.style import FaceName, ParaShape, StyleEntry
from .records.char_shape import CharShape
from .records.style import parse_style_record


MAX_HWP_RECORDS = 200_000


@dataclass
class BinDataEntry:
    """BinData 항목 (DocInfo 내)"""
    type: int = 0        # 0=LINK, 1=EMBEDDING, 2=STORAGE
    abs_path: str = ""
    rel_path: str = ""
    bin_data_id: int = 0
    extension: str = ""


@dataclass
class DocInfo:
    """DocInfo 스트림 전체 파싱 결과"""
    face_names: List[FaceName] = field(default_factory=list)
    char_shapes: List[CharShape] = field(default_factory=list)
    para_shapes: List[ParaShape] = field(default_factory=list)
    styles: List[StyleEntry] = field(default_factory=list)
    bin_data_entries: List[BinDataEntry] = field(default_factory=list)
    section_count: int = 0
    errors: List[str] = field(default_factory=list)


class DocInfoParser:

    def __init__(self):
        self.errors = []

    def parse_stream(self, stream_data: bytes, is_compressed: bool) -> DocInfo:
        if is_compressed:
            stream_data = safe_zlib_decompress(stream_data)

        doc_info = DocInfo()
        records = self._read_all_records(stream_data)

        for rec_tag, rec_data in records:
            try:
                if rec_tag == HWPTAG_DOCUMENT_PROPERTIES:
                    self._parse_doc_properties(rec_data, doc_info)
                elif rec_tag == HWPTAG_FACE_NAME:
                    self._parse_face_name(rec_data, doc_info)
                elif rec_tag == HWPTAG_CHAR_SHAPE:
                    doc_info.char_shapes.append(CharShape.parse(rec_data))
                elif rec_tag == HWPTAG_PARA_SHAPE:
                    self._parse_para_shape(rec_data, doc_info)
                elif rec_tag == HWPTAG_STYLE:
                    sr = parse_style_record(rec_data)
                    doc_info.styles.append(StyleEntry(
                        name=sr.name,
                        type=sr.type,
                        char_shape_id=sr.char_shape_id,
                        para_shape_id=sr.para_shape_id,
                        next_style_id=sr.next_style_id,
                    ))
                elif rec_tag == HWPTAG_BIN_DATA:
                    self._parse_bin_data(rec_data, doc_info)
            except Exception as e:
                doc_info.errors.append(f"WARN: DocInfo 레코드 {rec_tag} 파싱 실패: {e}")

        doc_info.errors.extend(self.errors)
        return doc_info

    def _read_all_records(self, data: bytes):
        """레코드 순차 읽기 (트리 구축 불필요 — DocInfo는 flat)"""
        records = []
        i = 0
        while i < len(data) - 3:
            if len(records) >= MAX_HWP_RECORDS:
                self.errors.append(
                    "ERR: HWP DocInfo record count exceeds limit: "
                    f"more than {MAX_HWP_RECORDS}"
                )
                break
            try:
                header = struct.unpack_from("<I", data, i)[0]
                tag_id = header & 0x3FF
                size = (header >> 20) & 0xFFF

                if size == 0xFFF:
                    if i + 8 > len(data):
                        raise ValueError("truncated extended record header")
                    size = struct.unpack_from("<I", data, i + 4)[0]
                    payload_start = i + 8
                    payload_end = payload_start + size
                    if payload_end > len(data):
                        raise ValueError(
                            f"truncated record payload: declared={size}, "
                            f"available={max(len(data) - payload_start, 0)}"
                        )
                    rec_data = data[payload_start:payload_end]
                    records.append((tag_id, rec_data))
                    i = payload_end
                else:
                    payload_start = i + 4
                    payload_end = payload_start + size
                    if payload_end > len(data):
                        raise ValueError(
                            f"truncated record payload: declared={size}, "
                            f"available={max(len(data) - payload_start, 0)}"
                        )
                    rec_data = data[payload_start:payload_end]
                    records.append((tag_id, rec_data))
                    i = payload_end
            except ValueError as e:
                self.errors.append(f"ERR: DocInfo 레코드 읽기 실패 offset={i}: {e}")
                break
            except Exception as e:
                self.errors.append(f"ERR: DocInfo 레코드 읽기 실패 offset={i}: {e}")
                i += 4
        return records

    def _parse_doc_properties(self, data: bytes, doc_info: DocInfo):
        """DOCUMENT_PROPERTIES — 섹션 수 등"""
        if len(data) >= 2:
            doc_info.section_count = struct.unpack_from("<H", data, 0)[0]

    def _parse_face_name(self, data: bytes, doc_info: DocInfo):
        """FACE_NAME — 글꼴 이름 파싱"""
        fn = FaceName()
        if len(data) < 3:
            doc_info.face_names.append(fn)
            return

        # offset 0: UINT8 속성
        fn.type_info = data[0]
        i = 1

        # 이름 (WORD len + WCHAR[len])
        if i + 2 > len(data):
            doc_info.face_names.append(fn)
            return
        name_len = struct.unpack_from("<H", data, i)[0]
        i += 2
        if name_len > 0 and i + name_len * 2 <= len(data):
            fn.name = data[i:i + name_len * 2].decode('utf-16-le', errors='replace').rstrip('\x00')

        doc_info.face_names.append(fn)

    def _parse_para_shape(self, data: bytes, doc_info: DocInfo):
        """PARA_SHAPE — 문단 모양 파싱"""
        ps = ParaShape()
        if len(data) < 4:
            doc_info.para_shapes.append(ps)
            return

        # offset 0: UINT32 속성1
        props = struct.unpack_from("<I", data, 0)[0]
        ps.align = props & 0x7  # bit 0-2: 정렬

        # offset 4: INT32 왼쪽 여백
        if len(data) >= 8:
            ps.left_margin = struct.unpack_from("<i", data, 4)[0]
        # offset 8: INT32 오른쪽 여백
        if len(data) >= 12:
            ps.right_margin = struct.unpack_from("<i", data, 8)[0]
        # offset 12: INT32 들여쓰기
        if len(data) >= 16:
            ps.indent = struct.unpack_from("<i", data, 12)[0]

        # offset 20: INT32 줄 간격 종류
        if len(data) >= 24:
            ps.line_spacing_type = struct.unpack_from("<i", data, 20)[0]
        # offset 24: INT32 줄 간격
        if len(data) >= 28:
            ps.line_spacing = struct.unpack_from("<i", data, 24)[0]

        doc_info.para_shapes.append(ps)

    def _parse_bin_data(self, data: bytes, doc_info: DocInfo):
        """BIN_DATA — 바이너리 데이터 참조"""
        entry = BinDataEntry()
        if len(data) < 2:
            doc_info.bin_data_entries.append(entry)
            return

        # offset 0: UINT16 속성
        props = struct.unpack_from("<H", data, 0)[0]
        entry.type = props & 0xF  # bit 0-3: Type

        i = 2

        if entry.type == 0:  # LINK
            # 절대 경로
            if i + 2 <= len(data):
                path_len = struct.unpack_from("<H", data, i)[0]
                i += 2
                if path_len > 0 and i + path_len * 2 <= len(data):
                    entry.abs_path = data[i:i + path_len * 2].decode('utf-16-le', errors='replace').rstrip('\x00')
                    i += path_len * 2
            # 상대 경로
            if i + 2 <= len(data):
                path_len = struct.unpack_from("<H", data, i)[0]
                i += 2
                if path_len > 0 and i + path_len * 2 <= len(data):
                    entry.rel_path = data[i:i + path_len * 2].decode('utf-16-le', errors='replace').rstrip('\x00')
                    i += path_len * 2

        elif entry.type == 1:  # EMBEDDING
            # BinData ID
            if i + 2 <= len(data):
                entry.bin_data_id = struct.unpack_from("<H", data, i)[0]
                i += 2
            # 확장자
            if i + 2 <= len(data):
                ext_len = struct.unpack_from("<H", data, i)[0]
                i += 2
                if ext_len > 0 and i + ext_len * 2 <= len(data):
                    entry.extension = data[i:i + ext_len * 2].decode('utf-16-le', errors='replace').rstrip('\x00')

        doc_info.bin_data_entries.append(entry)
