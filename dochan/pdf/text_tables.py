"""괘선 없는 PDF 본문에서 반복되는 텍스트 열을 표로 복원한다."""
from bisect import bisect_right
from copy import copy
from typing import List, Optional, Tuple

from ..conversion import Provenance
from ..model.table import Cell, Table
from .layout import merge_lines

MAX_GROUP_LINES = 5_000
MAX_ROWS = 500
MAX_COLUMNS = 20


def _row_candidate(line) -> bool:
    if line.direction not in ("ltr", "rtl") or not 2 <= len(line.segments) <= MAX_COLUMNS:
        return False
    space_width = max(3.0, 0.5 * line.size)
    return any(right.x0 - left.x1 >= 2 * getattr(left, "space_width", space_width)
               for left, right in zip(line.segments, line.segments[1:]))


def _columns(lines):
    """반복된 시작 좌표를 열로 추리고 각 줄의 적중 수를 확인한다."""
    tolerance = max(2.0, 0.25 * max(line.size for line in lines))
    clusters: List[List[float]] = []
    for x in sorted(segment.x0 for line in lines for segment in line.segments):
        if not clusters or x - sum(clusters[-1]) / len(clusters[-1]) > tolerance:
            clusters.append([])
        clusters[-1].append(x)
    if len(clusters) > MAX_COLUMNS * MAX_COLUMNS:
        return [], tolerance
    centers = [sum(cluster) / len(cluster) for cluster in clusters]
    columns = []
    for center in centers:
        hits = sum(any(abs(segment.x0 - center) <= tolerance for segment in line.segments)
                   for line in lines)
        if 5 * hits >= 3 * len(lines):
            columns.append(center)
    if not 2 <= len(columns) <= MAX_COLUMNS:
        return [], tolerance
    if any(sum(any(abs(segment.x0 - center) <= tolerance for segment in line.segments)
               for center in columns) < 2 for line in lines):
        return [], tolerance
    return columns, tolerance


def _cell_texts(line, columns, tolerance):
    cells = [[] for _ in columns]
    for segment in line.segments:
        col = bisect_right(columns, segment.x0 + tolerance) - 1
        if col >= 0:
            cells[min(col, len(columns) - 1)].append(segment.text.strip())
    return [" ".join(part for part in parts if part) for parts in cells]


def _is_list(lines, columns, tolerance) -> bool:
    texts = [_cell_texts(line, columns, tolerance) for line in lines]
    first = [row[0] for row in texts]
    if len(set(first)) == 1 and len(first[0]) == 1:
        return True
    return not any(len({row[col] for row in texts if row[col]}) >= 2
                   for col in range(1, len(columns)))


def _table(lines, columns, tolerance, page_number):
    provenance = Provenance(source_format="pdf", page=page_number)
    rows = []
    for row, line in enumerate(lines):
        cells = []
        for col, value in enumerate(_cell_texts(line, columns, tolerance)):
            cell = Cell(row=row, col=col, provenance=provenance)
            if value:
                cell_line = copy(line)
                cell_line.text = value
                cell_line.runs = [(value, False, False)]
                cell.paragraphs = [block.paragraph(page_number)
                                   for block in merge_lines([cell_line])]
            cells.append(cell)
        rows.append(cells)
    return Table(rows=rows)


def detect_text_tables(lines, page_number: Optional[int] = None) -> List[Tuple[Table, set]]:
    """본문 한 그룹의 표와 소비한 줄 인덱스를 순서대로 돌려준다."""
    if len(lines) > MAX_GROUP_LINES:
        return []
    found = []
    index = 0
    while index < len(lines):
        first = lines[index:index + 3]
        if len(first) < 3 or not all(_row_candidate(line) for line in first):
            index += 1
            continue
        columns, tolerance = _columns(first)
        if not columns or _is_list(first, columns, tolerance):
            index += 1
            continue
        end = index + 3
        while end < len(lines) and end - index < MAX_ROWS and _row_candidate(lines[end]):
            next_columns, next_tolerance = _columns(lines[index:end + 1])
            if not next_columns:
                break
            columns, tolerance = next_columns, next_tolerance
            end += 1
        found.append((_table(lines[index:end], columns, tolerance, page_number),
                      set(range(index, end))))
        index = end
    return found
