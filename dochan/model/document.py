"""Document model — 전체 문서 구조"""
from dataclasses import dataclass, field
from typing import Any, List, Optional


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
    # 신규 필드는 반드시 뒤에 붙일 것 — ooxml/core.py 가 TextRun(text) 위치 인자로 생성한다.
    link: str = ""        # 하이퍼링크 대상 URL (없으면 빈 문자열)
    note_ref: int = 0     # 이 런이 각주/미주 참조 마커면 그 번호 (0=마커 아님)
    provenance: Any = None
    note_reference_type: str = ""
    note_reference_number: Optional[int] = None


@dataclass
class Paragraph:
    """문단 하나"""
    runs: List[TextRun] = field(default_factory=list)
    para_shape_id: int = -1
    style_id: int = -1
    heading_level: int = 0  # 0=not heading, 1-6=heading level
    provenance: Any = None

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
    provenance: Any = None


@dataclass
class Document:
    """최상위 문서 모델"""
    sections: List[Section] = field(default_factory=list)
    char_shapes: list = field(default_factory=list)
    para_shapes: list = field(default_factory=list)
    styles: list = field(default_factory=list)
    face_names: list = field(default_factory=list)
    bin_data_list: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    file_header: Any = None
    errors: List[str] = field(default_factory=list)
    source_format: str = ""
    provenance: Any = None

    def find_all(self, element_type: str):
        """타입별 요소를 문서 순서대로 중복 없이 재귀 검색한다."""
        from .table import Table
        from .equation import Equation
        from .image import Image
        from .header_footer import Comment, Footnote, HeaderFooter

        type_map = {
            'table': (Table, None),
            'equation': (Equation, None),
            'image': (Image, None),
            'paragraph': (Paragraph, None),
            'header': (HeaderFooter, {'header'}),
            'footer': (HeaderFooter, {'footer'}),
            'header_footer': (HeaderFooter, None),
            'footnote': (Footnote, {'footnote'}),
            'endnote': (Footnote, {'endnote'}),
            'comment': (Comment, None),
            'note': (Footnote, {'footnote', 'endnote', 'comment'}),
        }
        target = type_map.get(str(element_type).lower())
        if target is None:
            return []
        cls, allowed_types = target

        results = []
        seen = set()
        for section in self.sections:
            self._find_recursive(section.elements, cls, results, seen, allowed_types)
        return results

    def _find_recursive(self, elements, cls, results, seen=None, allowed_types=None,
                        _depth: int = 0):
        """표 셀·머리글/바닥글·각주 내부를 재귀 탐색한다.

        seen 으로 순환 참조를 끊고, _depth 로 병적으로 깊은 문서에서도
        재귀가 끝나도록 막는다.
        """
        if _depth > 32:
            return
        from .table import Table
        from .header_footer import HeaderFooter, Footnote

        if seen is None:
            seen = set()
        for elem in elements:
            identity = id(elem)
            if identity in seen:
                continue
            seen.add(identity)

            type_matches = allowed_types is None or getattr(elem, 'type', None) in allowed_types
            if isinstance(elem, cls) and type_matches:
                results.append(elem)

            if isinstance(elem, Table):
                for row in elem.rows:
                    for cell in row:
                        self._find_recursive(
                            cell.paragraphs, cls, results, seen, allowed_types,
                            _depth + 1,
                        )
                # 표 캡션 안의 요소도 놓치지 않는다
                self._find_recursive(
                    elem.caption, cls, results, seen, allowed_types, _depth + 1,
                )
            # 머리글/바닥글/각주 내부도 검색 — 여기 있는 이미지가 통째로 누락되고 있었다
            elif isinstance(elem, (HeaderFooter, Footnote)):
                self._find_recursive(
                    elem.paragraphs, cls, results, seen, allowed_types, _depth + 1,
                )

    @property
    def metadata(self) -> dict:
        metadata = {
            'sections': len(self.sections),
            'char_shapes': len(self.char_shapes),
            'para_shapes': len(self.para_shapes),
            'styles': len(self.styles),
            'face_names': len(self.face_names),
            'assets': len(self.assets),
            'errors': list(self.errors),
        }
        if self.source_format:
            metadata['source_format'] = self.source_format
        return metadata
