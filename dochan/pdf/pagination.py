"""인접 PDF 페이지의 표 연속 여부와 행 병합."""
from dataclasses import dataclass
import math
from typing import Tuple

from ..model.table import Table
from .tables import TableCandidate

HEADER_FOOTER_ZONE = 60.0
_DEFAULT_BOUNDS = (0.0, 842.0)


MAX_HEADER_ROWS = 4  # 반복 제목으로 인정하는 최대 행 수
EDGE_FRACTION = 0.12  # 페이지 높이의 이 비율 안이면 행 높이와 무관하게 가장자리에 닿은 것으로 본다


@dataclass
class TailInfo:
    candidate: TableCandidate
    reaches_bottom: bool
    gap_below: float = 0.0      # 표 하단 ~ 본문 하단 사이 빈 공간
    page_height: float = 842.0


@dataclass
class HeadInfo:
    candidate: TableCandidate
    starts_top: bool


def _inherited(pdf, page: dict, key: str):
    """페이지 트리를 거슬러 올라가며 상속 가능한 항목을 찾는다 (순환·깊이 방어)."""
    visited = set()
    node = page
    for _ in range(33):
        if not isinstance(node, dict) or id(node) in visited:
            return None
        visited.add(id(node))
        if key in node:
            return pdf.resolve(node[key])
        node = pdf.resolve(node.get("Parent"))
    return None


def page_bounds(pdf, page: dict) -> Tuple[float, float]:
    """페이지 트리에서 MediaBox의 아래/위 y 좌표를 찾는다. 손상값은 기본 크기로 대체."""
    box = _inherited(pdf, page, "MediaBox")
    if not isinstance(box, list) or len(box) != 4:
        return _DEFAULT_BOUNDS
    try:
        resolved = [pdf.resolve(value) for value in box]
        if any(isinstance(value, bool) for value in resolved):
            return _DEFAULT_BOUNDS
        values = [float(value) for value in resolved]
        if not all(math.isfinite(v) for v in values):
            return _DEFAULT_BOUNDS
    except (TypeError, ValueError, OverflowError):  # 거대 정수·비수치 값
        return _DEFAULT_BOUNDS
    bottom, top = sorted((values[1], values[3]))
    return bottom, max(top, bottom + 1.0)


def page_rotation(pdf, page: dict) -> int:
    """/Rotate (상속) 를 0/90/180/270 으로 정규화한다. 손상값은 0."""
    value = _inherited(pdf, page, "Rotate")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    try:
        return int(round(float(value) / 90.0)) * 90 % 360
    except (ValueError, OverflowError):
        return 0


def body_between(fragments, consumed, y_low: float, y_high: float) -> bool:
    """표 밖의 비어 있지 않은 본문 조각이 세로 구간에 있는지 확인."""
    return any(frag.order not in consumed and y_low < frag.y < y_high
               and frag.text.strip() for frag in fragments)


def same_columns(xs_a, xs_b, tolerance: float = 1.5) -> bool:
    """두 표의 열 경계가 모두 같은 위치에 있는지 확인."""
    return (len(xs_a) == len(xs_b) and len(xs_a) >= 2
            and all(abs(a - b) <= tolerance for a, b in zip(xs_a, xs_b)))


def _row_key(row):
    return [(" ".join(cell.text.split()), cell.row_span, cell.col_span) for cell in row]


def repeated_header_rows(prev_table: Table, next_table: Table) -> int:
    """뒤 표 첫머리에 반복된 제목 행 수.

    제목 높이는 첫 행 셀의 최대 row_span 으로만 정한다. 열 병합만 쓰는 2단 제목의 둘째 행은
    구조만으로는 우연히 같은 데이터 행과 구별할 수 없으므로 제목으로 보지 않는다(둘째 행이
    데이터처럼 남는 쪽이 데이터 행을 지우는 쪽보다 낫다). 뒤 표에는 제목 뒤에 데이터 행이
    하나는 남아야 한다.
    """
    if not prev_table.rows or not next_table.rows:
        return 0
    span_height = max(1, max((cell.row_span for cell in prev_table.rows[0]), default=1))
    limit = min(MAX_HEADER_ROWS, len(prev_table.rows), len(next_table.rows) - 1)
    if span_height > limit:
        return 0
    prev_keys = [_row_key(row) for row in prev_table.rows[:limit]]
    next_keys = [_row_key(row) for row in next_table.rows[:limit]]
    if prev_keys[:span_height] != next_keys[:span_height]:
        return 0
    if not any(text for row in prev_keys[:span_height] for text, _, _ in row):
        return 0
    return span_height


def header_repeated(prev_table: Table, next_table: Table) -> bool:
    """첫 제목 행(들)이 반복됐는지 — repeated_header_rows 의 불리언 형태."""
    return repeated_header_rows(prev_table, next_table) > 0


def merge_continued(prev_table: Table, next_table: Table, drop_rows) -> None:
    """이어지는 행의 셀 좌표를 옮겨 앞 표에 붙인다. drop_rows 는 버릴 반복 제목 행 수(불리언은 1행)."""
    drop = int(drop_rows)
    offset = len(prev_table.rows) - drop
    for row_index, row in enumerate(next_table.rows):
        if row_index < drop:
            continue
        for cell in row:
            cell.row = offset + (cell.row if cell.row is not None else row_index)
        prev_table.rows.append(row)


def first_data_row_height(head: HeadInfo, drop_rows: int) -> float:
    """뒤 표에서 제목 행을 제외한 첫 행의 높이 (ys 는 내림차순)."""
    ys = head.candidate.ys
    index = min(drop_rows, max(len(ys) - 2, 0))
    if len(ys) < 2:
        return 0.0
    return ys[index] - ys[index + 1]


def continues(prev_tail: TailInfo, head: HeadInfo, tolerance: float = 1.5) -> bool:
    """양쪽 표가 본문 경계에 닿고 열 경계가 일치하며, 앞 표 아래 남은 공간에 다음 행이 들어갈 수
    없었을 때만 연속으로 본다 (남은 공간 < 다음 데이터 행 높이, 또는 페이지 높이의 12% 이내)."""
    if not (prev_tail.reaches_bottom and head.starts_top
            and same_columns(prev_tail.candidate.xs, head.candidate.xs, tolerance)):
        return False
    drop = repeated_header_rows(prev_tail.candidate.table, head.candidate.table)
    allowed = max(first_data_row_height(head, drop) + tolerance,
                  EDGE_FRACTION * prev_tail.page_height)
    return prev_tail.gap_below <= allowed
