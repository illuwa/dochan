"""인접 PDF 페이지의 표 연속 여부와 행 병합."""
from dataclasses import dataclass
import math
from typing import Tuple

from ..model.table import Table
from .tables import TableCandidate

HEADER_FOOTER_ZONE = 60.0
_DEFAULT_BOUNDS = (0.0, 842.0)


@dataclass
class TailInfo:
    candidate: TableCandidate
    reaches_bottom: bool


@dataclass
class HeadInfo:
    candidate: TableCandidate
    starts_top: bool


def page_bounds(pdf, page: dict) -> Tuple[float, float]:
    """페이지 트리에서 MediaBox의 아래/위 y 좌표를 찾는다."""
    visited = set()
    node = page
    for _ in range(33):
        if not isinstance(node, dict) or id(node) in visited:
            break
        visited.add(id(node))
        if "MediaBox" in node:
            box = pdf.resolve(node["MediaBox"])
            if not isinstance(box, list) or len(box) != 4:
                return _DEFAULT_BOUNDS
            values = [pdf.resolve(value) for value in box]
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in values):
                return _DEFAULT_BOUNDS
            bottom, top = sorted((float(values[1]), float(values[3])))
            return bottom, max(top, bottom + 1.0)
        node = pdf.resolve(node.get("Parent"))
    return _DEFAULT_BOUNDS


def body_between(fragments, consumed, y_low: float, y_high: float) -> bool:
    """표 밖의 비어 있지 않은 본문 조각이 세로 구간에 있는지 확인."""
    return any(frag.order not in consumed and y_low < frag.y < y_high
               and frag.text.strip() for frag in fragments)


def same_columns(xs_a, xs_b, tolerance: float = 1.5) -> bool:
    """두 표의 열 경계가 모두 같은 위치에 있는지 확인."""
    return (len(xs_a) == len(xs_b) and len(xs_a) >= 2
            and all(abs(a - b) <= tolerance for a, b in zip(xs_a, xs_b)))


def header_repeated(prev_table: Table, next_table: Table) -> bool:
    """첫 행의 표시 텍스트와 병합 형태가 같은지 확인."""
    if not prev_table.rows or not next_table.rows:
        return False
    prev, next_row = prev_table.rows[0], next_table.rows[0]
    return (len(prev) == len(next_row)
            and all(" ".join(a.text.split()) == " ".join(b.text.split())
                    and (a.row_span, a.col_span) == (b.row_span, b.col_span)
                    for a, b in zip(prev, next_row)))


def merge_continued(prev_table: Table, next_table: Table, drop_header: bool) -> None:
    """이어지는 행의 셀 좌표를 옮겨 앞 표에 붙인다."""
    offset = len(prev_table.rows)
    for row_index, row in enumerate(next_table.rows):
        if drop_header and row_index == 0:
            continue
        for cell in row:
            cell.row = offset + (cell.row if cell.row is not None else row_index)
            if drop_header:
                cell.row -= 1
        prev_table.rows.append(row)


def continues(prev_tail: TailInfo, head: HeadInfo, tolerance: float = 1.5) -> bool:
    """양쪽 표가 본문 경계에 닿고 열 경계가 일치하는지 확인."""
    return (prev_tail.reaches_bottom and head.starts_top
            and same_columns(prev_tail.candidate.xs, head.candidate.xs, tolerance))
