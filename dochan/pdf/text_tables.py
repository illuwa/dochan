"""괘선 없는 PDF 본문에서 반복되는 텍스트 열을 표로 복원한다 (옵션, 기본 꺼짐).

기하 근거가 없으므로 오탐 방어가 핵심이다: 글자마다 따로 놓인 조각은 먼저 칸으로 합치고,
번호·기호 목록은 제외하며, 열은 처음 세 줄에서 확정해 이후 줄은 적중만 검사한다(선형 시간).
"""
from bisect import bisect_right
from copy import copy
from typing import List, Optional, Tuple

from ..conversion import Provenance
from ..model.table import Cell, Table
from .layout import _BLOCK_MARKER, merge_lines

MAX_GROUP_LINES = 5_000
MAX_ROWS = 500
MAX_COLUMNS = 20
MIN_ROWS = 3


def _space_width(line) -> float:
    return max(3.0, 0.5 * line.size)


def _cells(line) -> List[Tuple[float, float, str]]:
    """인접 세그먼트를 칸으로 합친다 — 간격이 공백 폭의 2배 이상이면 새 칸, 절반보다 크면 칸 안의 공백."""
    space = _space_width(line)
    cells: List[Tuple[float, float, str]] = []
    for segment in line.segments:
        text = segment.text.strip()
        if cells and segment.x0 - cells[-1][1] < 2 * space:
            x0, x1, previous = cells[-1]
            sep = " " if previous and text and segment.x0 - x1 > 0.5 * space else ""
            cells[-1] = (x0, max(x1, segment.x1), previous + sep + text)
        else:
            cells.append((segment.x0, segment.x1, text))
    return cells


def _row_cells(line) -> Optional[List[Tuple[float, float, str]]]:
    """표 행 후보면 칸 목록, 아니면 None."""
    if line.direction not in ("ltr", "rtl"):
        return None
    cells = _cells(line)
    if not 2 <= len(cells) <= MAX_COLUMNS or not any(text for _, _, text in cells):
        return None
    return cells


def _tolerance(lines) -> float:
    return max(2.0, 0.25 * max(line.size for line in lines))


def _hits(cells, columns, tolerance) -> int:
    return sum(any(abs(x0 - center) <= tolerance for x0, _, _ in cells) for center in columns)


def _columns(rows, tolerance):
    """반복된 칸 시작 좌표를 열로 추린다. 60% 이상의 줄이 맞는 열이 2개 이상이고 모든 줄이 2열 이상에 닿아야 한다."""
    clusters: List[List[float]] = []
    for x in sorted(x0 for cells in rows for x0, _, _ in cells):
        if not clusters or x - clusters[-1][-1] > tolerance:
            clusters.append([])
        clusters[-1].append(x)
    if len(clusters) > MAX_COLUMNS * MAX_COLUMNS:
        return []
    columns = []
    for cluster in clusters:
        center = sum(cluster) / len(cluster)
        hits = sum(any(abs(x0 - center) <= tolerance for x0, _, _ in cells) for cells in rows)
        if 5 * hits >= 3 * len(rows):
            columns.append(center)
    if not 2 <= len(columns) <= MAX_COLUMNS:
        return []
    if any(_hits(cells, columns, tolerance) < 2 for cells in rows):
        return []
    return columns


def _cell_texts(cells, columns, tolerance) -> List[str]:
    texts = [[] for _ in columns]
    for x0, _, text in cells:
        col = max(0, min(bisect_right(columns, x0 + tolerance) - 1, len(columns) - 1))
        if text:
            texts[col].append(text)
    return [" ".join(parts) for parts in texts]


def _is_list(rows, columns, tolerance) -> bool:
    """번호·기호 목록이나 값이 반복되지 않는 라벨 줄은 표가 아니다."""
    texts = [_cell_texts(cells, columns, tolerance) for cells in rows]
    first = [row[0] for row in texts]
    if 3 * sum(1 for text in first if _BLOCK_MARKER.match(text)) >= 2 * len(first):
        return True
    if len(set(first)) == 1 and len(first[0]) == 1:
        return True
    return not any(len({row[col] for row in texts if row[col]}) >= 2
                   for col in range(1, len(columns)))


def _table(lines, rows, columns, tolerance, page_number):
    provenance = Provenance(source_format="pdf", page=page_number)
    table_rows = []
    for row, (line, cells) in enumerate(zip(lines, rows)):
        out = []
        for col, value in enumerate(_cell_texts(cells, columns, tolerance)):
            cell = Cell(row=row, col=col, provenance=provenance)
            if value:
                cell_line = copy(line)
                cell_line.text = value
                cell_line.runs = [(value, False, False)]
                cell.paragraphs = [block.paragraph(page_number) for block in merge_lines([cell_line])]
            out.append(cell)
        table_rows.append(out)
    return Table(rows=table_rows)


def detect_text_tables(lines, page_number: Optional[int] = None) -> List[Tuple[Table, set]]:
    """본문 한 그룹의 표와 소비한 줄 인덱스를 순서대로 돌려준다."""
    if len(lines) > MAX_GROUP_LINES:
        return []
    row_cells = [_row_cells(line) for line in lines]
    found = []
    index = 0
    while index < len(lines):
        head = row_cells[index:index + MIN_ROWS]
        if len(head) < MIN_ROWS or any(cells is None for cells in head):
            index += 1
            continue
        tolerance = _tolerance(lines[index:index + MIN_ROWS])
        columns = _columns(head, tolerance)
        if not columns or _is_list(head, columns, tolerance):
            index += 1
            continue
        end = index + MIN_ROWS
        # 열은 처음 세 줄에서 확정하고 이후 줄은 적중만 검사한다 — 줄마다 전체를 다시 세지 않는다
        while (end < len(lines) and end - index < MAX_ROWS and row_cells[end] is not None
               and _hits(row_cells[end], columns, tolerance) >= 2):
            end += 1
        rows = row_cells[index:end]
        refined = _columns(rows, tolerance)
        if refined:
            columns = refined
        found.append((_table(lines[index:end], rows, columns, tolerance, page_number),
                      set(range(index, end))))
        index = end
    return found
