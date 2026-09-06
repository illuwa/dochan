"""벡터 괘선으로 PDF 표를 복원한다. 중첩 표는 바깥 표의 평면 격자로 취급한다."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from ..conversion import Provenance
from ..model.table import Cell, Table
from .content import ContentTextExtractor, Fragment, Segment
from .layout import merge_lines

MAX_PAGE_CELLS = 50_000
MAX_DOCUMENT_CELLS = 200_000
MAX_COMPONENT_LINES = 2_000


@dataclass
class TableCandidate:
    table: Table
    bbox: Tuple[float, float, float, float]
    fragment_orders: Set[int]
    anchor_order: int


@dataclass
class TableBudget:
    """여러 페이지가 공유하는 남은 셀 수."""
    remaining: int = MAX_DOCUMENT_CELLS


def _warn(warnings, message):
    if warnings is not None and message not in warnings:
        warnings.append(message)


class _Union:
    def __init__(self, count):
        self.parents = list(range(count))
        self.sizes = [1] * count

    def find(self, item):
        while self.parents[item] != item:
            self.parents[item] = self.parents[self.parents[item]]
            item = self.parents[item]
        return item

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.sizes[a] < self.sizes[b]:
            a, b = b, a
        self.parents[b] = a
        self.sizes[a] += self.sizes[b]


def _snap_runs(lines, tolerance):
    """(고정 좌표, 시작, 끝)을 군집화하고 공선 조각을 합친다."""
    clusters = []
    for line in sorted(lines):
        if not clusters or line[0] - clusters[-1][0][0] > tolerance:
            clusters.append([])
        clusters[-1].append(line)
    runs = []
    for cluster in clusters:
        coord = sum(v[0] for v in cluster) / len(cluster)
        spans = sorted((v[1], v[2]) for v in cluster)
        start, end = spans[0]
        for lo, hi in spans[1:]:
            if lo <= end + tolerance:
                end = max(end, hi)
            else:
                runs.append((coord, start, end))
                start, end = lo, hi
        runs.append((coord, start, end))
    return runs


def _components(horizontal, vertical, tolerance):
    union = _Union(len(horizontal) + len(vertical))
    xs = [v[0] for v in vertical]
    for i, (y, left, right) in enumerate(horizontal):
        lo = bisect_left(xs, left - tolerance)
        hi = bisect_right(xs, right + tolerance)
        for j in range(lo, hi):
            _, bottom, top = vertical[j]
            if bottom - tolerance <= y <= top + tolerance:
                union.join(i, len(horizontal) + j)
    groups = defaultdict(lambda: ([], []))
    for i, line in enumerate(horizontal):
        groups[union.find(i)][0].append(line)
    for j, line in enumerate(vertical):
        groups[union.find(len(horizontal) + j)][1].append(line)
    return list(groups.values())


def _covered(runs, lo, hi, tolerance):
    coverage = sum(max(0, min(hi, end + tolerance) - max(lo, start - tolerance))
                   for start, end in runs)
    return coverage >= (hi - lo) * 0.5


def _rectangles(indices, cols):
    """직사각형이 아닌 연결 영역은 행별 연속 구간으로 되돌린다."""
    rows = defaultdict(list)
    for index in indices:
        r, c = divmod(index, cols)
        rows[r].append(c)
    r0, r1 = min(rows), max(rows)
    c0 = min(min(cs) for cs in rows.values())
    c1 = max(max(cs) for cs in rows.values())
    if len(indices) == (r1 - r0 + 1) * (c1 - c0 + 1):
        return [(r0, c0, r1 + 1, c1 + 1)]
    result = []
    for r, cs in sorted(rows.items()):
        start = end = min(cs)
        for c in sorted(cs)[1:]:
            if c != end + 1:
                result.append((r, start, r + 1, end + 1))
                start = c
            end = c
        result.append((r, start, r + 1, end + 1))
    return result


def _make_grid(horizontal, vertical, xs, ys, tolerance, page_number):
    rows, cols = len(ys) - 1, len(xs) - 1
    union = _Union(rows * cols)
    h_runs, v_runs = defaultdict(list), defaultdict(list)
    for coord, lo, hi in horizontal:
        h_runs[coord].append((lo, hi))
    for coord, lo, hi in vertical:
        v_runs[coord].append((lo, hi))
    for r in range(rows):
        for c in range(cols):
            index = r * cols + c
            if c + 1 < cols and not _covered(v_runs[xs[c + 1]], ys[r + 1], ys[r], tolerance):
                union.join(index, index + 1)
            if r + 1 < rows and not _covered(h_runs[ys[r + 1]], xs[c], xs[c + 1], tolerance):
                union.join(index, index + cols)
    regions = defaultdict(list)
    for i in range(rows * cols):
        regions[union.find(i)].append(i)
    provenance = Provenance(source_format='pdf', page=page_number)
    grid = [[Cell(row=r, col=c, row_span=0, col_span=0, provenance=provenance)
             for c in range(cols)] for r in range(rows)]
    owners = [None] * (rows * cols)
    boxes = {}
    for indices in regions.values():
        for r0, c0, r1, c1 in _rectangles(indices, cols):
            cell = Cell(row=r0, col=c0, row_span=r1 - r0, col_span=c1 - c0,
                        provenance=provenance)
            grid[r0][c0] = cell
            key = r0 * cols + c0
            boxes[key] = (xs[c0], ys[r1], xs[c1], ys[r0])
            for r in range(r0, r1):
                for c in range(c0, c1):
                    owners[r * cols + c] = key
    return grid, owners, boxes


def _assign_text(grid, owners, boxes, xs, ys, fragments, page_number):
    by_cell = defaultdict(list)
    cols = len(xs) - 1
    ascending_y = list(reversed(ys))
    consumed = set()
    for frag in fragments:
        x, y = frag.x + frag.width / 2, frag.y + 0.35 * frag.size
        c = bisect_right(xs, x) - 1
        r = len(ys) - 2 - (bisect_right(ascending_y, y) - 1)
        if not (0 <= c < cols and 0 <= r < len(grid)):
            continue
        key = owners[r * cols + c]
        left, bottom, right, top = boxes[key]
        if left + 0.5 <= x <= right - 0.5 and bottom + 0.5 <= y <= top - 0.5:
            by_cell[key].append(frag)
            consumed.add(frag.order)
    extractor = ContentTextExtractor()
    for key, frags in by_cell.items():
        lines = extractor._assemble_lines(sorted(frags, key=lambda f: (-f.y, f.x)))
        left, _, right, _ = boxes[key]
        r, c = divmod(key, cols)
        grid[r][c].paragraphs = [block.paragraph(page_number)
                                 for block in merge_lines(lines, (left + 0.5, right - 0.5))]
    return consumed


def _inside(inner, outer):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def build_tables(segments: List[Segment], fragments: List[Fragment], tolerance: float = 1.5,
                 page_number: Optional[int] = None, warnings: Optional[List[str]] = None,
                 budget: Optional[TableBudget] = None) -> List[TableCandidate]:
    """괘선 연결 성분에서 병합 셀을 갖춘 표 후보를 만든다.

    page_number/warnings/budget은 선택 인자라 기존 두 인자 호출도 가능하다.
    셀 안에 따로 그린 중첩 표는 독립 표로 내보내지 않는다.
    """
    horizontal, vertical = [], []
    for s in segments:
        if abs(s.y1 - s.y0) <= tolerance:
            horizontal.append(((s.y0 + s.y1) / 2, s.x0, s.x1))
        elif abs(s.x1 - s.x0) <= tolerance:
            vertical.append(((s.x0 + s.x1) / 2, s.y0, s.y1))
    horizontal = _snap_runs(horizontal, tolerance)
    vertical = _snap_runs(vertical, tolerance)
    components = []
    for hs, vs in _components(horizontal, vertical, tolerance):
        if len(hs) < 2 or len(vs) < 2:
            continue
        xs, ys = sorted(set(v[0] for v in vs)), sorted(set(h[0] for h in hs), reverse=True)
        bbox = (xs[0], ys[-1], xs[-1], ys[0])
        if bbox[2] - bbox[0] >= 8 and bbox[3] - bbox[1] >= 8:
            components.append((bbox, hs, vs, xs, ys))
    components.sort(key=lambda v: -(v[0][2] - v[0][0]) * (v[0][3] - v[0][1]))
    remaining = MAX_PAGE_CELLS
    result, outer_boxes = [], []
    used_orders = set()
    for bbox, hs, vs, xs, ys in components:
        if any(_inside(bbox, box) for box in outer_boxes):
            continue
        if len(hs) + len(vs) > MAX_COMPONENT_LINES:
            _warn(warnings, 'WARN: PDF 표 연결 성분의 선 수 한도(2000) 초과 — 표 생략')
            continue
        cells = (len(xs) - 1) * (len(ys) - 1)
        if cells > remaining:
            _warn(warnings, 'WARN: PDF 페이지 표 셀 수 한도(50000) 초과 — 표 생략')
            continue
        if budget is not None and cells > budget.remaining:
            _warn(warnings, 'WARN: PDF 문서 표 셀 수 한도(200000) 초과 — 표 생략')
            continue
        grid, owners, boxes = _make_grid(hs, vs, xs, ys, tolerance, page_number)
        consumed = _assign_text(grid, owners, boxes, xs, ys,
                                [f for f in fragments if f.order not in used_orders], page_number)
        if not consumed and (len(xs) < 3 or len(ys) < 3):
            continue
        remaining -= cells
        if budget is not None:
            budget.remaining -= cells
        used_orders.update(consumed)
        outer_boxes.extend(boxes.values())
        result.append(TableCandidate(Table(rows=grid), bbox, consumed, min(consumed, default=-1)))
    return sorted(result, key=lambda candidate: candidate.anchor_order)
