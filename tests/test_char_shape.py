"""
tests/test_char_shape.py — CharShape 파싱 테스트
"""

import struct
import pytest
from dochan.hwp.records.char_shape import CharShape


class TestCharShape:

    def _make_data(self, base_size=1000, bold=False, italic=False):
        """테스트용 CharShape 데이터 생성"""
        data = bytearray(72)

        # 글꼴 ID (offset 0, WORD × 7)
        for i in range(7):
            struct.pack_into("<H", data, i * 2, 0)

        # 장평 (offset 14, 7바이트)
        for i in range(7):
            data[14 + i] = 100

        # 자간 (offset 21, 7바이트)
        # 상대크기 (offset 28, 7바이트)
        for i in range(7):
            data[28 + i] = 100
        # 글자위치 (offset 35, 7바이트)

        # 기준 크기 (offset 42)
        struct.pack_into("<i", data, 42, base_size)

        # 속성 (offset 46)
        props = 0
        if italic:
            props |= (1 << 0)
        if bold:
            props |= (1 << 1)
        struct.pack_into("<I", data, 46, props)

        return bytes(data)

    def test_basic_parse(self):
        data = self._make_data(base_size=1000)
        cs = CharShape.parse(data)
        assert cs.size_pt == 10.0
        assert not cs.bold
        assert not cs.italic

    def test_bold(self):
        data = self._make_data(bold=True)
        cs = CharShape.parse(data)
        assert cs.bold
        assert not cs.italic

    def test_italic(self):
        data = self._make_data(italic=True)
        cs = CharShape.parse(data)
        assert cs.italic
        assert not cs.bold

    def test_heading_size(self):
        data = self._make_data(base_size=2000)
        cs = CharShape.parse(data)
        assert cs.size_pt == 20.0
        assert cs.is_heading_size

    def test_small_data(self):
        """데이터 부족 시 기본값"""
        cs = CharShape.parse(b'\x00' * 10)
        assert cs.base_size == 0
        assert not cs.bold
