"""
hwp/records/ctrl_header.py — CTRL_HEADER ctrlId 파싱
스펙 4.3.6 + 표 67 확인:
  MAKE_4CHID(a,b,c,d) = ((a)<<24)|((b)<<16)|((c)<<8)|(d)
  → LE 저장 시 바이트 순서 역전!
  → data[0:4] = [d, c, b, a]
  → "tbl " → 파일 내 bytes = b' lbt' (0x20, 0x6C, 0x62, 0x74)
"""

import struct


def _make_4chid(a: str, b: str, c: str, d: str) -> bytes:
    """MAKE_4CHID 매크로 재현 → LE 바이트 순서 반환"""
    return bytes([ord(d), ord(c), ord(b), ord(a)])


# ★ 상수는 LE 바이트 순서 (파일 내 실제 바이트 패턴)
CTRL_TABLE       = _make_4chid('t', 'b', 'l', ' ')   # b'\x20\x6c\x62\x74'
CTRL_EQUATION    = _make_4chid('e', 'q', 'e', 'd')   # b'\x64\x65\x71\x65'
CTRL_GSO         = _make_4chid('g', 's', 'o', ' ')
CTRL_SECTION_DEF = _make_4chid('s', 'e', 'c', 'd')
CTRL_COLUMN_DEF  = _make_4chid('c', 'o', 'l', 'd')
CTRL_HEADER_HF   = _make_4chid('h', 'd', 'r', ' ')
CTRL_FOOTER_HF   = _make_4chid('f', 't', 'r', ' ')
CTRL_FOOTNOTE    = _make_4chid('f', 'n', ' ', ' ')
CTRL_ENDNOTE     = _make_4chid('e', 'n', ' ', ' ')
CTRL_AUTO_NUMBER = _make_4chid('a', 't', 'n', 'o')
CTRL_NEW_NUMBER  = _make_4chid('n', 'w', 'n', 'o')
CTRL_MEMO        = _make_4chid('t', 'c', 'm', 't')
CTRL_PICTURE     = _make_4chid('$', 'p', 'i', 'c')
CTRL_LINE        = _make_4chid('$', 'l', 'i', 'n')
CTRL_RECT        = _make_4chid('$', 'r', 'e', 'c')
CTRL_ELLIPSE     = _make_4chid('$', 'e', 'l', 'l')
CTRL_ARC         = _make_4chid('$', 'a', 'r', 'c')
CTRL_POLYGON     = _make_4chid('$', 'p', 'o', 'l')
CTRL_CURVE       = _make_4chid('$', 'c', 'u', 'r')
CTRL_OLE         = _make_4chid('$', 'o', 'l', 'e')
CTRL_CONTAINER   = _make_4chid('$', 'c', 'o', 'n')


def parse_ctrl_id(data: bytes) -> bytes:
    """CTRL_HEADER 데이터에서 ctrlId 4바이트 추출 (LE 바이트 그대로)"""
    return data[0:4] if len(data) >= 4 else b''


def ctrl_id_to_str(ctrl_id: bytes) -> str:
    """LE 바이트 → 사람이 읽을 수 있는 문자열 (디버깅/로깅용)"""
    return ctrl_id[::-1].decode('latin-1') if len(ctrl_id) == 4 else ""


def identify_control(ctrl_id: bytes) -> str:
    """ctrlId 바이트 → 컨트롤 유형 문자열"""
    mapping = {
        CTRL_TABLE: 'table',
        CTRL_EQUATION: 'equation',
        CTRL_GSO: 'image',
        CTRL_PICTURE: 'image',
        CTRL_HEADER_HF: 'header',
        CTRL_FOOTER_HF: 'footer',
        CTRL_FOOTNOTE: 'footnote',
        CTRL_ENDNOTE: 'endnote',
        CTRL_SECTION_DEF: 'section_def',
        CTRL_COLUMN_DEF: 'column_def',
        CTRL_MEMO: 'memo',
    }
    return mapping.get(ctrl_id, 'unknown')
