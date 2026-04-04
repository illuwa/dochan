"""Document model — 전체 문서 구조"""
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class TextRun:
    """서식이 동일한 텍스트 조각"""
    text: str = ""
    char_shape_id: int = -1
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikeout: bool = False
    superscript: bool = False
    subscript: bool = False
    font_size_pt: float = 10.0


@dataclass
class Paragraph:
    """문단 하나"""
    runs: List[TextRun] = field(default_factory=list)
    para_shape_id: int = -1
    style_id: int = -1
    heading_level: int = 0  # 0=not heading, 1-6=heading level

    @property
    def text(self) -> str:
        return ''.join(r.text for r in self.runs)

    @property
    def is_heading(self) -> bool:
        return self.heading_level > 0


@dataclass
class Section:
    """섹션 (BodyText/SectionN 하나)"""
    elements: List[Any] = field(default_factory=list)


@dataclass
class Document:
    """최상위 문서 모델"""
    sections: List[Section] = field(default_factory=list)
    char_shapes: list = field(default_factory=list)
    para_shapes: list = field(default_factory=list)
    styles: list = field(default_factory=list)
    face_names: list = field(default_factory=list)
    bin_data_list: list = field(default_factory=list)
    file_header: Any = None
    errors: List[str] = field(default_factory=list)

    def find_all(self, element_type: str):
        """타입별 요소 검색 (table, equation, image 등)"""
        from .table import Table
        from .equation import Equation
        from .image import Image

        type_map = {
            'table': Table,
            'equation': Equation,
            'image': Image,
            'paragraph': Paragraph,
        }
        cls = type_map.get(element_type)
        if not cls:
            return []

        results = []
        for section in self.sections:
            self._find_recursive(section.elements, cls, results)
        return results

    def _find_recursive(self, elements, cls, results):
        """재귀적으로 모든 요소 검색 (표 셀 내부 포함)"""
        from .table import Table
        for elem in elements:
            if isinstance(elem, cls):
                results.append(elem)
            # 표 안의 셀 내부도 검색
            if isinstance(elem, Table):
                for row in elem.rows:
                    for cell in row:
                        self._find_recursive(cell.paragraphs, cls, results)

    @property
    def metadata(self) -> dict:
        return {
            'sections': len(self.sections),
            'char_shapes': len(self.char_shapes),
            'para_shapes': len(self.para_shapes),
            'styles': len(self.styles),
            'face_names': len(self.face_names),
            'errors': self.errors,
        }
