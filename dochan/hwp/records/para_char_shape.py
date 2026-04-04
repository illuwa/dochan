"""
hwp/records/para_char_shape.py — PARA_CHAR_SHAPE 참조 인덱스 파싱
문단 내 각 위치별 CharShape ID 매핑
"""
import struct
from typing import List, Tuple


def parse_para_char_shape(data: bytes) -> List[Tuple[int, int]]:
    """
    PARA_CHAR_SHAPE 레코드 파싱

    반환: [(position, char_shape_id), ...] 쌍 목록
    position: 텍스트 내 WCHAR 단위 시작 위치
    char_shape_id: DocInfo의 CharShape 배열 인덱스
    """
    pairs = []
    i = 0
    while i + 5 < len(data):
        pos = struct.unpack_from("<I", data, i)[0]
        cs_id = struct.unpack_from("<H", data, i + 4)[0]
        pairs.append((pos, cs_id))
        i += 6  # 4(pos) + 2(id) = 6바이트씩
    return pairs


def get_char_shape_id_at(pairs: List[Tuple[int, int]], position: int) -> int:
    """주어진 위치에 적용되는 CharShape ID 반환"""
    result = 0
    for pos, cs_id in pairs:
        if pos <= position:
            result = cs_id
        else:
            break
    return result
