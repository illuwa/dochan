"""
hwp/records/para_header.py — PARA_HEADER 파싱
스펙 표 58 기준
"""
import struct
from dataclasses import dataclass


@dataclass
class ParaHeaderInfo:
    text_char_count: int = 0
    control_mask: int = 0
    para_shape_id: int = 0
    style_id: int = 0
    column_type: int = 0
    num_char_shape: int = 0
    num_range_tag: int = 0
    num_line_seg: int = 0
    para_instance_id: int = 0


def parse_para_header(data: bytes) -> ParaHeaderInfo:
    """PARA_HEADER 레코드 데이터 파싱"""
    info = ParaHeaderInfo()
    if len(data) < 4:
        return info

    # offset 0: UINT32 — 텍스트 WCHAR 개수 (마지막 문단 끝 포함)
    info.text_char_count = struct.unpack_from("<I", data, 0)[0]

    # offset 4: UINT32 — 컨트롤 마스크
    if len(data) >= 8:
        info.control_mask = struct.unpack_from("<I", data, 4)[0]

    # offset 8: UINT16 — 문단 모양 ID 참조
    if len(data) >= 10:
        info.para_shape_id = struct.unpack_from("<H", data, 8)[0]

    # offset 10: UINT8 — 스타일 ID
    if len(data) >= 11:
        info.style_id = data[10]

    # offset 11: UINT8 — 단 나누기 종류
    if len(data) >= 12:
        info.column_type = data[11]

    # offset 12: UINT16 — CharShape 참조 수
    if len(data) >= 14:
        info.num_char_shape = struct.unpack_from("<H", data, 12)[0]

    # offset 14: UINT16 — RangeTag 수
    if len(data) >= 16:
        info.num_range_tag = struct.unpack_from("<H", data, 14)[0]

    # offset 16: UINT16 — LineSeg 수
    if len(data) >= 18:
        info.num_line_seg = struct.unpack_from("<H", data, 16)[0]

    # offset 18: UINT32 — 문단 인스턴스 ID
    if len(data) >= 22:
        info.para_instance_id = struct.unpack_from("<I", data, 18)[0]

    return info
