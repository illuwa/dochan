"""
hwp/records/style.py — Style 레코드 파서
스펙 표 42 기준
"""
import struct
from dataclasses import dataclass


@dataclass
class StyleRecord:
    """스타일 레코드 파싱 결과"""
    name: str = ""
    type: int = 0          # 0=문단, 1=글자
    next_style_id: int = 0
    lang_id: int = 0
    para_shape_id: int = -1
    char_shape_id: int = -1


def parse_style_record(data: bytes) -> StyleRecord:
    """STYLE 레코드 데이터 파싱"""
    style = StyleRecord()
    if len(data) < 2:
        return style

    i = 0

    # 스타일 이름 (WORD len + WCHAR[len])
    if i + 2 > len(data):
        return style
    name_len = struct.unpack_from("<H", data, i)[0]
    i += 2
    if name_len > 0 and i + name_len * 2 <= len(data):
        style.name = data[i:i + name_len * 2].decode('utf-16-le', errors='replace').rstrip('\x00')
        i += name_len * 2

    # 영문 스타일 이름 (WORD len + WCHAR[len])
    if i + 2 > len(data):
        return style
    eng_name_len = struct.unpack_from("<H", data, i)[0]
    i += 2
    i += eng_name_len * 2  # skip

    # 속성 (UINT8)
    if i + 1 <= len(data):
        style.type = data[i] & 0x7  # bit 0-2
        i += 1

    # 다음 스타일 ID (UINT8)
    if i + 1 <= len(data):
        style.next_style_id = data[i]
        i += 1

    # 언어 ID (INT16)
    if i + 2 <= len(data):
        style.lang_id = struct.unpack_from("<h", data, i)[0]
        i += 2

    # 문단 모양 ID (UINT16)
    if i + 2 <= len(data):
        style.para_shape_id = struct.unpack_from("<H", data, i)[0]
        i += 2

    # 글자 모양 ID (UINT16)
    if i + 2 <= len(data):
        style.char_shape_id = struct.unpack_from("<H", data, i)[0]

    return style
