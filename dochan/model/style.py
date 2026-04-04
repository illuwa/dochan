"""Style model — CharShape, ParaShape, Style, FaceName"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class FaceName:
    """글꼴 이름"""
    name: str = ""
    family: int = 0
    type_info: int = 0


@dataclass
class ParaShape:
    """문단 모양"""
    align: int = 0         # 0=양쪽, 1=왼쪽, 2=오른쪽, 3=가운데
    left_margin: int = 0
    right_margin: int = 0
    indent: int = 0
    line_spacing_type: int = 0
    line_spacing: int = 0
    heading_type: int = 0

    @property
    def align_str(self) -> str:
        return {0: 'justify', 1: 'left', 2: 'right', 3: 'center'}.get(self.align, 'left')


@dataclass
class StyleEntry:
    """스타일"""
    name: str = ""
    type: int = 0          # 0=문단, 1=글자
    char_shape_id: int = -1
    para_shape_id: int = -1
    next_style_id: int = -1
