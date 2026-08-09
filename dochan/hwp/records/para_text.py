"""
hwp/records/para_text.py — PARA_TEXT 바이너리 파서
제어 문자 크기 맵(control_char.py) 기반
"""
import struct
from ...control_char import get_advance_bytes, is_extended_ctrl


def parse_para_text(data: bytes) -> dict:
    """
    HWPTAG_PARA_TEXT 바이너리 → 텍스트 + 컨트롤 위치 정보

    반환: {
        'text': str,              # 추출된 텍스트
        'ctrl_positions': list,   # 확장 컨트롤 위치 목록 [(char_index, char_code)]
        'field_marks': list,      # 필드 경계 [(text_offset, 'start', ctrlId) | (text_offset, 'end', None)]
    }

    field_marks 의 text_offset 은 반환 text 문자열 안의 오프셋이다 (char_index 와
    달리 컨트롤 문자를 세지 않는다). 필드 시작(3)은 확장 컨트롤 블록 안에
    ctrlId 4바이트(LE, 예: b'klh%')가 내장되어 있어 그대로 기록한다 — 실측:
    수당 및 제수수료 지급규칙(2024년도 8월 개정).hwp hexdump.
    """
    text_parts = []
    ctrl_positions = []
    field_marks = []
    char_index = 0
    i = 0

    while i < len(data) - 1:
        char_code = struct.unpack_from("<H", data, i)[0]

        if char_code >= 32:
            # 일반 문자 (UTF-16LE)
            if 0xD800 <= char_code <= 0xDBFF and i + 3 < len(data):
                # High surrogate: 다음 16비트 유닛과 결합해 BMP 밖 코드포인트 복원
                low = struct.unpack_from("<H", data, i + 2)[0]
                if 0xDC00 <= low <= 0xDFFF:
                    cp = 0x10000 + (char_code - 0xD800) * 0x400 + (low - 0xDC00)
                    text_parts.append(chr(cp))
                    char_index += 1
                    i += 4
                    continue
                # 짝 없는 high surrogate → 대체 문자
                text_parts.append('\ufffd')
            elif 0xDC00 <= char_code <= 0xDFFF:
                # 짝 없는 low surrogate → 대체 문자
                text_parts.append('\ufffd')
            else:
                text_parts.append(chr(char_code))
            char_index += 1
            i += 2

        elif char_code == 13:
            # 문단 끝
            break

        elif char_code == 0:
            # 사용 안 함
            i += 2

        else:
            # 제어 문자 처리
            advance = get_advance_bytes(char_code)

            # 의미 있는 문자로 변환
            if char_code == 10:
                text_parts.append('\n')
            elif char_code == 9:
                text_parts.append('\t')
            elif char_code == 30:
                text_parts.append(' ')   # 묶음 빈칸 → 공백
            elif char_code == 31:
                text_parts.append(' ')   # 고정폭 빈칸 → 공백
            elif char_code == 24:
                text_parts.append('-')   # 하이픈

            # 필드 경계 기록 — 하이퍼링크(%hlk) 적용 범위 계산용.
            # 각 append 는 정확히 한 글자이므로 len(text_parts)가 곧 텍스트 오프셋.
            if char_code == 3 and i + 6 <= len(data):
                field_marks.append((len(text_parts), 'start', bytes(data[i + 2:i + 6])))
            elif char_code == 4:
                field_marks.append((len(text_parts), 'end', None))

            # 확장 컨트롤은 위치 기록 (나중에 CTRL_HEADER와 매칭)
            if is_extended_ctrl(char_code):
                ctrl_positions.append((char_index, char_code))

            char_index += 1
            i += advance

    return {
        'text': ''.join(text_parts),
        'ctrl_positions': ctrl_positions,
        'field_marks': field_marks,
    }
