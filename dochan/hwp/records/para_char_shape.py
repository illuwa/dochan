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
    각 항목은 8바이트: UINT32 position (원시 WCHAR 위치) + UINT32 char_shape_id.
    실물 레코드 hexdump ``00000000 0a000000 0d000000 09000000`` 는
    (0, 10), (13, 9)를 뜻한다. 끝에 남는 8바이트 미만의 데이터는 무시한다.
    char_shape_id: DocInfo의 CharShape 배열 인덱스
    """
    pairs = []
    i = 0
    while i + 8 <= len(data):
        pairs.append(struct.unpack_from("<II", data, i))
        i += 8
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
