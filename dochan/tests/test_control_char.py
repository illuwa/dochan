"""
tests/test_control_char.py — 제어 문자 크기 맵 테스트
"""

import pytest
from dochan.control_char import (
    get_advance_bytes, is_extended_ctrl,
    CTRL_CHAR_WCHAR_SIZE, EXTENDED_CTRL_CHARS,
)


class TestControlChar:

    def test_char_type_size(self):
        """char 타입은 1 WCHAR = 2 bytes"""
        assert get_advance_bytes(10) == 2   # 줄바꿈
        assert get_advance_bytes(13) == 2   # 문단 끝
        assert get_advance_bytes(24) == 2   # 하이픈
        assert get_advance_bytes(30) == 2   # 묶음 빈칸
        assert get_advance_bytes(31) == 2   # 고정폭 빈칸

    def test_inline_type_size(self):
        """inline 타입은 8 WCHAR = 16 bytes"""
        assert get_advance_bytes(4) == 16   # 필드 끝
        assert get_advance_bytes(9) == 16   # 탭

    def test_extended_type_size(self):
        """extended 타입은 8 WCHAR = 16 bytes"""
        assert get_advance_bytes(2) == 16   # 구역/단
        assert get_advance_bytes(11) == 16  # 그리기 개체/표
        assert get_advance_bytes(17) == 16  # 각주/미주

    def test_unknown_char_default(self):
        """알 수 없는 문자코드는 1 WCHAR = 2 bytes"""
        assert get_advance_bytes(99) == 2

    def test_extended_ctrl_set(self):
        assert is_extended_ctrl(11)   # 표/그리기
        assert is_extended_ctrl(17)   # 각주/미주
        assert not is_extended_ctrl(10)  # 줄바꿈은 확장 아님
        assert not is_extended_ctrl(9)   # 탭은 확장 아님


class TestCtrlHeaderConstants:

    def test_make_4chid(self):
        from dochan.hwp.records.ctrl_header import (
            _make_4chid, CTRL_TABLE, CTRL_EQUATION,
            ctrl_id_to_str, identify_control,
        )

        # "tbl " → LE bytes
        assert CTRL_TABLE == bytes([0x20, 0x6C, 0x62, 0x74])

        # "eqed" → LE bytes
        assert CTRL_EQUATION == bytes([0x64, 0x65, 0x71, 0x65])

        # 역변환
        assert ctrl_id_to_str(CTRL_TABLE) == "tbl "
        assert ctrl_id_to_str(CTRL_EQUATION) == "eqed"

        # 식별
        assert identify_control(CTRL_TABLE) == 'table'
        assert identify_control(CTRL_EQUATION) == 'equation'


class TestParaText:

    def test_simple_text(self):
        """간단한 텍스트 파싱"""
        from dochan.hwp.records.para_text import parse_para_text
        import struct

        # "AB" + 문단끝(13)
        data = struct.pack("<HHH", ord('A'), ord('B'), 13)
        result = parse_para_text(data)
        assert result['text'] == 'AB'
        assert result['ctrl_positions'] == []

    def test_tab_handling(self):
        """탭 제어 문자 처리 (inline, 16바이트)"""
        from dochan.hwp.records.para_text import parse_para_text
        import struct

        # 'A' + 탭(9, inline 16바이트) + 'B' + 끝(13)
        data = struct.pack("<H", ord('A'))
        data += struct.pack("<H", 9) + b'\x00' * 14  # 탭 = 16바이트 total
        data += struct.pack("<HH", ord('B'), 13)
        result = parse_para_text(data)
        assert result['text'] == 'A\tB'
