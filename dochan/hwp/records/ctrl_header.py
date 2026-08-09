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
# ★ 실파일 실측(회계규칙 등 test_pairs) + hwplib 확인: 머리말/꼬리말은
#   'hdr '/'ftr ' 가 아니라 'head'/'foot' 다.
CTRL_HEADER_HF   = _make_4chid('h', 'e', 'a', 'd')
CTRL_FOOTER_HF   = _make_4chid('f', 'o', 'o', 't')
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

# 필드 컨트롤 (ctrlId 가 '%' 로 시작 — LE 저장 시 바이트 3이 '%')
CTRL_FIELD_HYPERLINK = _make_4chid('%', 'h', 'l', 'k')   # b'klh%'


def parse_ctrl_id(data: bytes) -> bytes:
    """CTRL_HEADER 데이터에서 ctrlId 4바이트 추출 (LE 바이트 그대로)"""
    return data[0:4] if len(data) >= 4 else b''


def ctrl_id_to_str(ctrl_id: bytes) -> str:
    """LE 바이트 → 사람이 읽을 수 있는 문자열 (디버깅/로깅용)"""
    return ctrl_id[::-1].decode('latin-1') if len(ctrl_id) == 4 else ""


def is_field_ctrl_id(ctrl_id: bytes) -> bool:
    """필드 컨트롤(%hlk, %bmk, %dte ...) 여부 — LE 저장이라 '%' 가 바이트 3에 온다"""
    return len(ctrl_id) == 4 and ctrl_id[3:4] == b'%'


def parse_field_command_url(data: bytes) -> str:
    """필드 CTRL_HEADER 에서 하이퍼링크 URL 을 추출한다.

    레이아웃 (실측 — 수당 및 제수수료 지급규칙(2024년도 8월 개정).hwp hexdump,
    HWPX 동일 문서의 fieldBegin id/Command 와 대조 확인):
      ctrlId(4) + 속성(DWORD 4) + 기타 속성(BYTE 1)
      + Command 길이(UINT16) + Command(UTF-16LE) + 인스턴스 ID(DWORD 4)

    Command 는 'http\\://host;1;0;0;' 꼴로 백슬래시 이스케이프('\\:','\\;','\\\\')가
    걸려 있고 첫 비이스케이프 ';' 뒤는 옵션 플래그다 (corpus 실측 표본:
    'www.hufscit.com;1;0;0;', 'javascript\\:\\;;1;0;0;', '?참조;0;0;0;').
    HWPX 파서는 Path 파라미터가 있을 때만 링크를 만드는데, 책갈피형('?...')과
    스크립트형('javascript...')은 Path 가 없다 — 같은 문서 쌍에서 동일한 결과가
    나오도록 여기서도 그 둘은 버린다.
    """
    if len(data) < 11:
        return ""
    cmd_len = struct.unpack_from("<H", data, 9)[0]
    end = 11 + cmd_len * 2
    if end > len(data):
        end = 11 + ((len(data) - 11) // 2) * 2
    command = data[11:end].decode('utf-16-le', errors='replace')
    return field_command_to_url(command)


def field_command_to_url(command: str) -> str:
    """필드 Command 문자열 → URL. HWPX(Path 부재 시 폴백)와 공유한다."""
    out = []
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == '\\' and i + 1 < len(command):
            out.append(command[i + 1])
            i += 2
            continue
        if ch == ';':
            break
        out.append(ch)
        i += 1
    url = ''.join(out).strip().strip('\x00')

    if not url or url.startswith('?') or url.lower().startswith('javascript'):
        return ""
    return url


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
