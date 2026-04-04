"""
control_char.py — 제어 문자별 WCHAR 단위 크기
1 WCHAR = 2 bytes. 실제 바이트 크기 = 값 × 2
스펙 표 6 (p.10-11) 기준
"""

CTRL_CHAR_WCHAR_SIZE = {
    # ── char 타입 (1 WCHAR = 2 bytes) ──
    10: 1,   # 줄바꿈 (line break)
    13: 1,   # 문단 끝 (para break)
    24: 1,   # 하이픈
    25: 1, 26: 1, 27: 1, 28: 1, 29: 1,  # 예약 (char)
    30: 1,   # 묶음 빈칸
    31: 1,   # 고정폭 빈칸

    # ── inline 타입 (8 WCHAR = 16 bytes) ──
    4: 8,    # 필드 끝
    5: 8, 6: 8, 7: 8,   # 예약 (inline)
    8: 8,    # title mark
    9: 8,    # 탭
    19: 8, 20: 8,  # 예약 (inline)

    # ── extended 타입 (8 WCHAR = 16 bytes) ──
    1: 8,    # 예약
    2: 8,    # 구역/단 정의
    3: 8,    # 필드 시작
    11: 8,   # 그리기 개체/표
    12: 8,   # 예약
    14: 8,   # 예약
    15: 8,   # 숨은 설명
    16: 8,   # 머리말/꼬리말
    17: 8,   # 각주/미주
    18: 8,   # 자동번호
    21: 8,   # 페이지 컨트롤
    22: 8,   # 책갈피/찾아보기
    23: 8,   # 덧말/글자겹침
}

# extended 타입 ctrlId (이 코드의 컨트롤은 별도 오브젝트가 존재)
EXTENDED_CTRL_CHARS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}


def get_advance_bytes(char_code: int) -> int:
    """제어 문자 하나가 차지하는 바이트 수 반환"""
    wchar_count = CTRL_CHAR_WCHAR_SIZE.get(char_code, 1)
    return wchar_count * 2


def is_extended_ctrl(char_code: int) -> bool:
    """별도 오브젝트(표, 그림 등)를 가리키는 확장 컨트롤인지"""
    return char_code in EXTENDED_CTRL_CHARS
