"""벡터 괘선으로 PDF 표와 셀 안의 독립 중첩 표를 복원한다."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..conversion import Provenance
from ..model.table import Cell, Table
from .content import Fragment, assemble_lines
from .layout import merge_lines
from .paths import Segment

MAX_PAGE_CELLS = 50_000
MAX_DOCUMENT_CELLS = 200_000
MAX_COMPONENT_LINES = 2_000
MAX_INTERSECTION_CHECKS = 2_000_000  # 가로×세로 교차 검사 상한 — 촘촘한 괘선의 CPU 폭주 방지
MAX_NESTED_DEPTH = 32
MAX_PAGE_COMPONENTS = 1_000  # 페이지당 표 후보 상한 — 부모 탐색이 후보 수²으로 자라는 것을 막는다


@dataclass
class TableCandidate:
    table: Table
    bbox: Tuple[float, float, float, float]
    fragment_orders: Set[int]
    anchor_order: int
    xs: Tuple[float, ...] = ()
    ys: Tuple[float, ...] = ()


@dataclass
class TableBudget:
    """여러 페이지가 공유하는 남은 셀 수."""
    remaining: int = MAX_DOCUMENT_CELLS


@dataclass
class _TableNode:
    bbox: Tuple[float, float, float, float]
    xs: List[float]
    ys: List[float]
    grid: List[List[Cell]]
    owners: List[int]
    boxes: Dict[int, Tuple[float, float, float, float]]
    cells: int
    parent: Optional['_TableNode'] = None
    owner_key: Optional[int] = None
    depth: int = 0
    fragment_orders: Set[int] = field(default_factory=set)
    anchor_order: int = -1
    children: List['_TableNode'] = field(default_factory=list)


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
    """가로선과 세로선이 맞닿는 관계로 연결 성분을 만든다. 예산 초과 시 None."""
    union = _Union(len(horizontal) + len(vertical))
    xs = [v[0] for v in vertical]
    checks = 0
    for i, (y, left, right) in enumerate(horizontal):
        lo = bisect_left(xs, left - tolerance)
        hi = bisect_right(xs, right + tolerance)
        checks += hi - lo
        if checks > MAX_INTERSECTION_CHECKS:
            return None
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


def _assign_text(grid, owners, boxes, xs, ys, fragments, page_number, breaks=None):
    by_cell = defaultdict(list)
    cols = len(xs) - 1
    ascending_y = list(reversed(ys))
    consumed = set()
    for frag in fragments:
        x, y = _reference_point(frag)
        c = bisect_right(xs, x) - 1
        r = len(ys) - 2 - (bisect_right(ascending_y, y) - 1)
        if not (0 <= c < cols and 0 <= r < len(grid)):
            continue
        key = owners[r * cols + c]
        left, bottom, right, top = boxes[key]
        if left + 0.5 <= x <= right - 0.5 and bottom + 0.5 <= y <= top - 0.5:
            by_cell[key].append(frag)
            consumed.add(frag.order)
    events = defaultdict(list)
    for key, frags in by_cell.items():
        lines = assemble_lines(sorted(frags, key=lambda f: (-f.y, f.x)))
        left, _, right, _ = boxes[key]
        groups = [[]]
        for line in lines:
            # 기준선이 중첩 표 윗변에 닿은 줄은 표 '위'의 줄이다 — 그 다음 줄부터 끊는다
            if groups[-1] and any(line.y < y <= groups[-1][-1].y
                                  for y in (breaks or {}).get(key, ())):
                groups.append([])
            groups[-1].append(line)
        for group in groups:
            for block in merge_lines(group, (left + 0.5, right - 0.5)):
                events[key].append((block.y, 0, block.order, block.paragraph(page_number)))
    return consumed, events


def _shared_extent(values, tolerance, outermost):
    """두 개 이상의 괘선이 함께 닿는 가장 바깥 좌표. 하나만 튀어나온 이상치는 무시한다."""
    ordered = sorted(values, reverse=outermost)
    for first, second in zip(ordered, ordered[1:]):
        if abs(first - second) <= tolerance:
            return first
    return None


def _extend_to_rule_extents(xs, horizontal, tolerance):
    """바깥 세로 괘선이 없는 표는 가로 괘선이 뻗은 범위까지 열 경계를 보탠다.

    개정 이력 표처럼 좌우 테두리를 생략한 표에서 첫/끝 열의 텍스트가 본문으로 새는
    것을 막는다. 선 끝 오버슈트(선 굵기 수준)는 경계로 보지 않고, 괘선 하나만 길게
    튀어나온 경우도 무시한다. 세로 방향(행)은 확장하지 않는다 — 실측 이득이 없고
    세로선 오버슈트가 본문을 표로 빨아들일 수 있다.
    """
    margin = max(6.0, 4 * tolerance)
    left = _shared_extent([h[1] for h in horizontal], tolerance, outermost=False)
    right = _shared_extent([h[2] for h in horizontal], tolerance, outermost=True)
    if left is not None and xs[0] - left > margin:
        xs.insert(0, left)
    if right is not None and right - xs[-1] > margin:
        xs.append(right)


def _inside(inner, outer):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def _owner_region(bbox, parent):
    """네 모서리가 같은 병합 셀 영역 안에 있으면 그 소유자 키를 돌려준다."""
    left, bottom, right, top = bbox
    xs, ys = parent.xs, parent.ys
    ascending_y = list(reversed(ys))
    columns = (bisect_right(xs, left) - 1, bisect_left(xs, right) - 1)
    rows = (len(ys) - 2 - (bisect_right(ascending_y, bottom) - 1),
            len(ys) - 2 - (bisect_left(ascending_y, top) - 1))
    if any(not 0 <= col < len(xs) - 1 for col in columns):
        return None
    if any(not 0 <= row < len(ys) - 1 for row in rows):
        return None
    keys = {parent.owners[row * (len(xs) - 1) + col]
            for row in rows for col in columns}
    if len(keys) != 1:
        return None
    key = keys.pop()
    return key if _inside(bbox, parent.boxes[key]) else None


def _text_cell_count(node):
    return sum(bool(cell.text) for row in node.grid for cell in row
               if not cell.is_merged_away)


def _area(bbox):
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def _fragment_index(fragments):
    """y 오름차순 색인 — 후보 bbox 범위의 조각만 bisect 로 잘라내기 위해 페이지당 한 번 만든다.

    기준점은 가로 조각에서 기준선보다 0.35·크기 위에, 회전 조각에서는 폭의 절반까지 위아래로
    벗어날 수 있으므로 그만큼의 여유를 y 범위 양쪽에 둔다.
    """
    ordered = sorted(fragments, key=lambda frag: frag.y)
    below = above = 0.0
    for frag in ordered:
        rotated = abs(frag.dir_y) > abs(frag.dir_x)
        below = max(below, 0.35 * frag.size + (0.5 * frag.width if rotated else 0.0))
        if rotated:
            above = max(above, 0.5 * frag.width + 0.35 * frag.size)
    return ordered, [frag.y for frag in ordered], (below, above)


def _reference_point(frag):
    """조각의 셀 배정 기준점 — 쓰기 축으로 폭의 절반, 수직축으로 크기의 0.35 만큼 이동한 점."""
    scale = (frag.dir_x ** 2 + frag.dir_y ** 2) ** 0.5
    dx, dy = (frag.dir_x / scale, frag.dir_y / scale) if scale else (1.0, 0.0)
    return (frag.x + dx * frag.width / 2 - dy * 0.35 * frag.size,
            frag.y + dy * frag.width / 2 + dx * 0.35 * frag.size)


def _fragments_inside(index, bbox):
    """기준점이 bbox 안에 놓일 수 있는 조각의 상위집합 (y 는 색인으로, x 는 기준점으로 거른다)."""
    ordered, ys, (below, above) = index
    lo, hi = bisect_left(ys, bbox[1] - below), bisect_right(ys, bbox[3] + above)
    return [frag for frag in ordered[lo:hi]
            if bbox[0] <= _reference_point(frag)[0] <= bbox[2]]


def _has_fragment_inside(index, bbox):
    """기준점이 정확히 bbox 안에 있는 조각이 하나라도 있는가 (조기 거부용 정밀 판정)."""
    for frag in _fragments_inside(index, bbox):
        _, y = _reference_point(frag)
        if bbox[1] <= y <= bbox[3]:
            return True
    return False


def _empty_form(xs, ys, cells):
    """텍스트 없이도 표로 인정하는 빈 서식 격자인가."""
    return len(xs) >= 3 and len(ys) >= 3 and cells >= 6


def build_tables(segments: List[Segment], fragments: List[Fragment], tolerance: float = 1.5,
                 page_number: Optional[int] = None, warnings: Optional[List[str]] = None,
                 budget: Optional[TableBudget] = None) -> List[TableCandidate]:
    """괘선 연결 성분에서 병합 셀을 갖춘 표 후보를 만든다.

    page_number/warnings/budget은 선택 인자라 기존 두 인자 호출도 가능하다.
    셀 안의 독립 괘선 성분은 해당 셀의 중첩 표로 넣는다.
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
    grouped = _components(horizontal, vertical, tolerance)
    if grouped is None:
        _warn(warnings, 'WARN: PDF 괘선 교차 검사 수 한도(2000000) 초과 — 표 생략')
        return []
    for hs, vs in grouped:
        if len(hs) < 2 or len(vs) < 2:
            continue
        xs, ys = sorted(set(v[0] for v in vs)), sorted(set(h[0] for h in hs), reverse=True)
        _extend_to_rule_extents(xs, hs, tolerance)
        bbox = (xs[0], ys[-1], xs[-1], ys[0])
        if bbox[2] - bbox[0] >= 8 and bbox[3] - bbox[1] >= 8:
            components.append((bbox, hs, vs, xs, ys))
    components.sort(key=lambda v: -_area(v[0]))
    index = _fragment_index(fragments)
    remaining = MAX_PAGE_CELLS
    reserved = 0  # 1단계 잠정 예약 — 실제 차감은 2단계 채택 시점에만 한다
    nodes = []
    for bbox, hs, vs, xs, ys in components:
        if len(hs) + len(vs) > MAX_COMPONENT_LINES:
            _warn(warnings, 'WARN: PDF 표 연결 성분의 선 수 한도(2000) 초과 — 표 생략')
            continue
        # 텍스트가 없는 작은 성분은 노드가 되기 전에 버린다 — 예산도 부모 탐색 비용도 쓰지 않는다
        has_text = _has_fragment_inside(index, bbox)
        if not has_text and (len(xs) < 3 or len(ys) < 3):
            continue
        if len(nodes) >= MAX_PAGE_COMPONENTS:
            _warn(warnings, 'WARN: PDF 페이지 표 후보 수 한도(1000) 초과 — 작은 후보 생략')
            break
        parent = min((node for node in nodes if _inside(bbox, node.bbox)),
                     key=lambda node: _area(node.bbox), default=None)
        owner_key = _owner_region(bbox, parent) if parent is not None else None
        if parent is not None and owner_key is None:
            continue
        # 중첩 후보는 텍스트 셀이 있거나 빈 서식 격자여야 채택되므로, 둘 다 아니면 예산을 점유하기 전에 버린다
        cells = (len(xs) - 1) * (len(ys) - 1)
        if parent is not None and not has_text and not _empty_form(xs, ys, cells):
            continue
        depth = parent.depth + 1 if parent is not None else 0
        if depth > MAX_NESTED_DEPTH:
            _warn(warnings, 'WARN: PDF 중첩 표 깊이 한도(32) 초과 — 표 생략')
            continue
        if cells > remaining - reserved:
            _warn(warnings, 'WARN: PDF 페이지 표 셀 수 한도(50000) 초과 — 표 생략')
            continue
        if budget is not None and cells > budget.remaining - reserved:
            _warn(warnings, 'WARN: PDF 문서 표 셀 수 한도(200000) 초과 — 표 생략')
            continue
        grid, owners, boxes = _make_grid(hs, vs, xs, ys, tolerance, page_number)
        reserved += cells
        nodes.append(_TableNode(bbox, xs, ys, grid, owners, boxes, cells,
                                parent, owner_key, depth))

    used_orders = set()
    result = []
    for node in sorted(nodes, key=lambda item: _area(item.bbox)):
        breaks = defaultdict(list)
        for child in node.children:
            breaks[child.owner_key].append(child.bbox[3])
        own_orders, events = _assign_text(
            node.grid, node.owners, node.boxes, node.xs, node.ys,
            [frag for frag in _fragments_inside(index, node.bbox)
             if frag.order not in used_orders],
            page_number, breaks)
        for child in node.children:
            events[child.owner_key].append((child.bbox[3], 1, child.anchor_order,
                                            Table(rows=child.grid)))
        for key, blocks in events.items():
            row, col = divmod(key, len(node.xs) - 1)
            node.grid[row][col].paragraphs = [block for _, _, _, block in sorted(
                blocks, key=lambda item: (-item[0], item[1], item[2]))]
        subtree_orders = own_orders.union(*(child.fragment_orders for child in node.children))
        if node.parent is None:
            keep = bool(subtree_orders) or (len(node.xs) >= 3 and len(node.ys) >= 3)
        else:
            text_cells = _text_cell_count(node)
            width = node.bbox[2] - node.bbox[0]
            height = node.bbox[3] - node.bbox[1]
            keep = (text_cells >= 1 and (text_cells >= 2 or node.cells >= 4 or
                                              (node.cells == 1 and width >= 30 and height >= 12))
                    or (text_cells == 0 and _empty_form(node.xs, node.ys, node.cells)))
        if not keep:
            # 거부된 노드의 텍스트는 상위로 돌려주고, 이미 채택된 자식은 조부모 셀(없으면 최상위)로 올린다
            used_orders.difference_update(own_orders)
            for child in node.children:
                child.parent, child.owner_key = node.parent, node.owner_key
                if node.parent is not None:
                    node.parent.children.append(child)
                else:
                    result.append(TableCandidate(Table(rows=child.grid), child.bbox,
                                                 child.fragment_orders, child.anchor_order,
                                                 tuple(child.xs), tuple(child.ys)))
            continue
        if budget is not None:
            budget.remaining -= node.cells
        node.fragment_orders = subtree_orders
        node.anchor_order = min(subtree_orders, default=-1)
        used_orders.update(own_orders)
        if node.parent is None:
            result.append(TableCandidate(Table(rows=node.grid), node.bbox,
                                         subtree_orders, node.anchor_order,
                                         tuple(node.xs), tuple(node.ys)))
        else:
            node.parent.children.append(node)
    return sorted(result, key=lambda candidate: candidate.anchor_order)
