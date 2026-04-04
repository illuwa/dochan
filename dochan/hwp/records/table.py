"""
hwp/records/table.py — TABLE 레코드 보조 파서
스펙 표 75 (p.44) 기준
"""
import struct
from dataclasses import dataclass, field
from typing import List


@dataclass
class TableInfo:
    """TABLE(77) 레코드 파싱 결과"""
    properties: int = 0
    row_count: int = 0
    col_count: int = 0
    cell_spacing: int = 0
    left_margin: int = 0
    right_margin: int = 0
    top_margin: int = 0
    bottom_margin: int = 0
    row_sizes: List[int] = field(default_factory=list)
    border_fill_id: int = 0


def parse_table_record(data: bytes) -> TableInfo:
    """TABLE 레코드 데이터 파싱"""
    info = TableInfo()
    if len(data) < 8:
        return info

    # offset 0: UINT32 속성 (표 76)
    info.properties = struct.unpack_from("<I", data, 0)[0]

    # offset 4: UINT16 행 수
    info.row_count = struct.unpack_from("<H", data, 4)[0]

    # offset 6: UINT16 열 수
    info.col_count = struct.unpack_from("<H", data, 6)[0]

    # offset 8: HWPUNIT16 셀 간격
    if len(data) >= 10:
        info.cell_spacing = struct.unpack_from("<H", data, 8)[0]

    # offset 10-17: 안쪽 여백 (좌/우/상/하, 각 HWPUNIT16)
    if len(data) >= 18:
        info.left_margin = struct.unpack_from("<H", data, 10)[0]
        info.right_margin = struct.unpack_from("<H", data, 12)[0]
        info.top_margin = struct.unpack_from("<H", data, 14)[0]
        info.bottom_margin = struct.unpack_from("<H", data, 16)[0]

    # offset 18~: UINT16[RowCount] 각 행 크기
    offset = 18
    for _ in range(info.row_count):
        if offset + 2 <= len(data):
            info.row_sizes.append(struct.unpack_from("<H", data, offset)[0])
            offset += 2

    # BorderFillID (행 크기 배열 직후)
    if offset + 2 <= len(data):
        info.border_fill_id = struct.unpack_from("<H", data, offset)[0]

    return info
