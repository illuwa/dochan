"""Table/Cell model — 표 및 셀 (병합 지원)"""
from dataclasses import dataclass, field
from typing import List, Any, Optional

# 중첩 표를 평탄화할 때의 재귀 상한. ooxml/docx.py 의 MAX_NESTED_TABLE_DEPTH 와 같은 값.
MAX_FLATTEN_DEPTH = 32


def flatten_block_texts(blocks, cell_sep: str = '\t', row_sep: str = '\n', _depth: int = 0) -> list:
    """블록(Paragraph / 중첩 Table / Image) 목록에서 텍스트 조각을 순서대로 추출한다.

    저장소 전역이 ``hasattr(x, 'text')`` 를 암묵적 타입 판별자로 쓰기 때문에
    Table 에 text 프로퍼티를 달 수 없다. 그래서 평탄화 규칙을 이 헬퍼 하나로 모아
    Cell.text / HeaderFooter.text / Footnote.text / Markdown 셀 렌더가 같은 규칙을 쓰게 한다.

    Args:
        blocks: Paragraph, Table, Image 가 섞인 목록
        cell_sep: 중첩 표의 열 구분자
        row_sep: 중첩 표의 행 구분자
    """
    if _depth > MAX_FLATTEN_DEPTH:
        return []

    parts = []
    for block in blocks:
        # 각주/미주/머리글은 본문이 아니다. 셀 텍스트 한가운데에 각주 본문이
        # 끼어들면 셀 값이 오염된다. 출력 계층이 따로 렌더한다.
        if hasattr(block, 'paragraphs') and hasattr(block, 'type'):
            continue
        if hasattr(block, 'rows'):  # 중첩 Table
            rows = []
            for row in block.rows:
                cells = []
                for cell in row:
                    if cell.is_merged_away:
                        continue
                    inner = flatten_block_texts(
                        cell.paragraphs, cell_sep, row_sep, _depth + 1
                    )
                    joined = cell_sep.join(t for t in inner if t)
                    if joined:
                        cells.append(joined)
                if cells:
                    rows.append(cell_sep.join(cells))
            if rows:
                parts.append(row_sep.join(rows))
        elif hasattr(block, 'ocr_text'):  # Image
            # alt_text(HWPX shapeComment)는 한글이 자동 생성한 '그림입니다. 원본 그림의
            # 이름: ...' 메타데이터라 본문 텍스트로 흘리면 품질을 떨어뜨린다.
            # 대체 텍스트 슬롯에서만 쓰고 여기서는 OCR 결과만 취한다.
            if block.ocr_text:
                parts.append(block.ocr_text)
        elif hasattr(block, 'script'):  # Equation
            text = block.latex or block.script
            if text:
                parts.append(text)
        elif hasattr(block, 'text'):  # Paragraph 등
            if block.text:
                parts.append(block.text)
    return parts


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
        return '\n'.join(flatten_block_texts(self.paragraphs))

    @property
    def is_merged_away(self) -> bool:
        return self.row_span == 0 or self.col_span == 0


@dataclass
class Table:
    """표 전체"""
    rows: List[List[Cell]] = field(default_factory=list)
    caption: list = field(default_factory=list)   # 캡션 문단 목록
    caption_side: str = "BOTTOM"                  # TOP | BOTTOM | LEFT | RIGHT

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    @property
    def caption_text(self) -> str:
        return '\n'.join(flatten_block_texts(self.caption))
