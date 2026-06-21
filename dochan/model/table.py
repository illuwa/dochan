"""Table/Cell model — 표 및 셀 (병합 지원)"""
from dataclasses import dataclass, field
from typing import List, Any, Optional


@dataclass
class Cell:
    """표의 셀 하나"""
    paragraphs: list = field(default_factory=list)
    row: Optional[int] = None
    col: Optional[int] = None
    row_span: int = 1
    col_span: int = 1
    provenance: Any = None

    @property
    def text(self) -> str:
        parts = []
        for p in self.paragraphs:
            if hasattr(p, 'text'):
                parts.append(p.text)
        return '\n'.join(parts)

    @property
    def is_merged_away(self) -> bool:
        return self.row_span == 0 or self.col_span == 0


@dataclass
class Table:
    """표 전체"""
    rows: List[List[Cell]] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)
