"""
hwp/records/char_shape.py — CharShape 파싱
스펙 표 33 (p.24) 기준. 총 72바이트.

오프셋 맵:
  0-13  : WORD[7]   언어별 글꼴 ID (14바이트)
  14-20 : UINT8[7]  장평 (7바이트)
  21-27 : INT8[7]   자간 (7바이트)
  28-34 : UINT8[7]  상대 크기 (7바이트)
  35-41 : INT8[7]   글자 위치 (7바이트)
  42-45 : INT32     기준 크기 (0pt~4096pt)
  46-49 : UINT32    속성 (표 35)
  50    : INT8      그림자 간격 X
  51    : INT8      그림자 간격 Y
  52-55 : COLORREF  글자 색
  56-59 : COLORREF  밑줄 색
  60-63 : COLORREF  음영 색
  64-67 : COLORREF  그림자 색
  68-69 : UINT16    글자 테두리/배경 ID (5.0.2.1+)
  70-73 : COLORREF  취소선 색 (5.0.3.0+)
"""

import struct
from dataclasses import dataclass, field
from typing import List


@dataclass
class CharShape:
    face_name_ids: List[int] = field(default_factory=list)  # 7개 언어별
    ratios: List[int] = field(default_factory=list)          # 장평
    spacings: List[int] = field(default_factory=list)        # 자간
    rel_sizes: List[int] = field(default_factory=list)       # 상대 크기
    positions: List[int] = field(default_factory=list)       # 글자 위치
    base_size: int = 0          # 기준 크기 (pt × 100)
    italic: bool = False        # bit 0
    bold: bool = False          # bit 1
    underline_type: int = 0     # bit 2-3
    outline_type: int = 0       # bit 8-10
    shadow_type: int = 0        # bit 11-12
    superscript: bool = False   # bit 15
    subscript: bool = False     # bit 16
    strikeout: int = 0          # bit 18-20
    text_color: int = 0         # COLORREF
    underline_color: int = 0
    shade_color: int = 0
    shadow_color: int = 0

    @property
    def size_pt(self) -> float:
        """기준 크기 → pt 변환. 저장값은 pt×100 (예: 10pt = 1000)."""
        return self.base_size / 100.0

    @property
    def is_heading_size(self) -> bool:
        return self.size_pt > 12.0

    @classmethod
    def parse(cls, data: bytes) -> 'CharShape':
        cs = cls()
        if len(data) < 50:
            return cs

        # 글꼴 ID (offset 0, WORD × 7)
        for i in range(7):
            cs.face_name_ids.append(struct.unpack_from("<H", data, i * 2)[0])

        # 장평 (offset 14, UINT8 × 7)
        for i in range(7):
            cs.ratios.append(data[14 + i])

        # 자간 (offset 21, INT8 × 7)
        for i in range(7):
            cs.spacings.append(struct.unpack_from("<b", data, 21 + i)[0])

        # 상대 크기 (offset 28)
        for i in range(7):
            cs.rel_sizes.append(data[28 + i])

        # 글자 위치 (offset 35)
        for i in range(7):
            cs.positions.append(struct.unpack_from("<b", data, 35 + i)[0])

        # 기준 크기 (offset 42, INT32)
        cs.base_size = struct.unpack_from("<i", data, 42)[0]

        # 속성 (offset 46, UINT32) — 스펙 표 35
        if len(data) >= 50:
            props = struct.unpack_from("<I", data, 46)[0]
            cs.italic         = bool(props & (1 << 0))   # bit 0 = 기울임
            cs.bold           = bool(props & (1 << 1))   # bit 1 = 진하게
            cs.underline_type = (props >> 2) & 0x3        # bit 2-3
            cs.outline_type   = (props >> 8) & 0x7        # bit 8-10
            cs.shadow_type    = (props >> 11) & 0x3       # bit 11-12
            cs.superscript    = bool(props & (1 << 15))   # bit 15
            cs.subscript      = bool(props & (1 << 16))   # bit 16
            cs.strikeout      = (props >> 18) & 0x7       # bit 18-20

        # 글자 색 (offset 52)
        if len(data) >= 56:
            cs.text_color = struct.unpack_from("<I", data, 52)[0]

        # 밑줄 색 (offset 56)
        if len(data) >= 60:
            cs.underline_color = struct.unpack_from("<I", data, 56)[0]

        # 음영 색 (offset 60)
        if len(data) >= 64:
            cs.shade_color = struct.unpack_from("<I", data, 60)[0]

        # 그림자 색 (offset 64)
        if len(data) >= 68:
            cs.shadow_color = struct.unpack_from("<I", data, 64)[0]

        return cs
