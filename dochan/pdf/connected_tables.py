"""공유 괘선 하나를 제거했을 때 분리되는 닫힌 내부 격자를 찾는다."""
from bisect import bisect_left, bisect_right
from collections import Counter

MAX_SPLIT_CHECKS = 2_000_000


class SplitBudget:
    """페이지의 모든 연결형 성분이 공유하는 그래프·격자 검사 예산이다."""

    def __init__(self, remaining=None):
        self.remaining = MAX_SPLIT_CHECKS if remaining is None else remaining

    def spend(self, checks):
        if checks > self.remaining:
            self.remaining = 0
            return False
        self.remaining -= checks
        return True


def _grid_cost(horizontal, vertical, xs, ys):
    """셀 할당과 _covered가 실제 순회하는 경계별 선분 수의 상한이다."""
    rows, cols = len(ys) - 1, len(xs) - 1
    hs = Counter(line[0] for line in horizontal)
    vs = Counter(line[0] for line in vertical)
    return (rows * cols + len(horizontal) + len(vertical)
            + rows * sum(vs[x] for x in xs[1:-1])
            + cols * sum(hs[y] for y in ys[1:-1]))


def _articulations(adjacency):
    """반복 DFS로 단절점을 구한다. 긴 선 연결도 Python 재귀를 쓰지 않는다."""
    discovered = [-1] * len(adjacency)
    low = [0] * len(adjacency)
    parents = [-1] * len(adjacency)
    children = [0] * len(adjacency)
    cuts = set()
    clock = 0
    for root in range(len(adjacency)):
        if discovered[root] >= 0:
            continue
        discovered[root] = low[root] = clock
        clock += 1
        stack = [(root, iter(adjacency[root]))]
        while stack:
            node, neighbours = stack[-1]
            other = next(neighbours, None)
            if other is None:
                stack.pop()
                parent = parents[node]
                if parent >= 0:
                    low[parent] = min(low[parent], low[node])
                    if parents[parent] >= 0 and low[node] >= discovered[parent]:
                        cuts.add(parent)
                elif children[node] > 1:
                    cuts.add(node)
                continue
            if discovered[other] < 0:
                parents[other] = node
                children[node] += 1
                discovered[other] = low[other] = clock
                clock += 1
                stack.append((other, iter(adjacency[other])))
            elif other != parents[node]:
                low[node] = min(low[node], discovered[other])
    return sorted(cuts)


def _has_cycle(adjacency):
    """차수 0·1 정점을 제거해 닫힌 격자가 없는 숲을 선형 비용으로 거른다."""
    degrees = [len(neighbours) for neighbours in adjacency]
    pending = [i for i, degree in enumerate(degrees) if degree < 2]
    removed = 0
    while pending:
        node = pending.pop()
        removed += 1
        for other in adjacency[node]:
            degrees[other] -= 1
            if degrees[other] == 1:
                pending.append(other)
    return removed < len(adjacency)


def _bbox(hs, vs):
    points = [(lo, y, hi, y) for y, lo, hi in hs]
    points += [(x, lo, x, hi) for x, lo, hi in vs]
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[2] for p in points), max(p[3] for p in points))


def _closed(hs, vs, box, tolerance):
    left, bottom, right, top = box
    return (all(any(abs(y - edge) <= tolerance and lo <= left + tolerance
                    and hi >= right - tolerance for y, lo, hi in hs)
                for edge in (bottom, top))
            and all(any(abs(x - edge) <= tolerance and lo <= bottom + tolerance
                        and hi >= top - tolerance for x, lo, hi in vs)
                    for edge in (left, right)))


def split_connected(horizontal, vertical, tolerance, fragment_index,
                    max_checks=None, warnings=None, split_budget=None,
                    dash_runs=None, max_cells=None):
    """모호한 후보·예산 초과는 입력을 그대로 반환한다. 원본 괘선은 바꾸지 않는다."""
    from .tables import (MAX_COMPONENT_LINES, MAX_PAGE_CELLS, _inside,
                         _make_grid, _fragments_inside, _reference_point, _warn,
                         _extend_to_rule_extents, _supplement_rules)

    unchanged = [(horizontal, vertical)]
    if split_budget is None:
        split_budget = SplitBudget(max_checks)
    cell_limit = MAX_PAGE_CELLS if max_cells is None else min(MAX_PAGE_CELLS, max_cells)

    def axes(hs, vs):
        xs = sorted(set(line[0] for line in vs))
        _extend_to_rule_extents(xs, hs, tolerance)
        return xs, sorted(set(line[0] for line in hs), reverse=True)

    def grid_rules(hs, vs, xs, ys):
        return (_supplement_rules(hs, vs, xs, ys, dash_runs)
                if dash_runs is not None else (hs, vs))

    def exhausted():
        _warn(warnings, 'WARN: PDF 연결형 중첩 표 검사 한도 초과 — 기존 격자 유지')
        return unchanged

    if not fragment_index[0]:
        return unchanged
    size = len(horizontal) + len(vertical)
    if size > MAX_COMPONENT_LINES or len(horizontal) < 2 or len(vertical) < 2:
        return unchanged
    if not split_budget.spend(size):
        return exhausted()
    adjacency = [set() for _ in range(size)]
    xs = [line[0] for line in vertical]
    for i, (y, left, right) in enumerate(horizontal):
        lo, hi = bisect_left(xs, left - tolerance), bisect_right(xs, right + tolerance)
        if not split_budget.spend(hi - lo):
            return exhausted()
        for j in range(lo, hi):
            if vertical[j][1] - tolerance <= y <= vertical[j][2] + tolerance:
                adjacency[i].add(len(horizontal) + j)
                adjacency[len(horizontal) + j].add(i)
    graph_cost = size + sum(len(neighbours) for neighbours in adjacency)
    if not split_budget.spend(graph_cost):
        return exhausted()
    # 합친 축의 곱은 분리 후 셀 수의 하한이 아니다. 닫힘 가능성만
    # 먼저 검사하고, 셀 상한은 아래 후보별 부모·자식 합으로 판정한다.
    if graph_cost - size < 2 * size:
        if not _has_cycle(adjacency):
            return unchanged
        if not split_budget.spend(graph_cost):
            return exhausted()
    accepted = None
    # 단절점만 조사하여 보통의 격자는 선 수마다 그래프 전체를 다시 걷지 않는다.
    for cut in _articulations(adjacency):
        neighbours = adjacency[cut]
        if len(neighbours) < 3:
            continue
        seen = {cut}
        branches = []
        for start in sorted(neighbours):
            if start in seen:
                continue
            branch, pending = set(), [start]
            seen.add(start)
            while pending:
                item = pending.pop()
                branch.add(item)
                if not split_budget.spend(1 + len(adjacency[item])):
                    return exhausted()
                for other in adjacency[item]:
                    if other not in seen:
                        seen.add(other)
                        pending.append(other)
            branches.append(branch)
        if len(branches) < 2:
            continue
        for branch in branches:
            if len(branch) < 3:
                continue
            if not split_budget.spend(size):
                return exhausted()
            hs = [line for i, line in enumerate(horizontal) if i in branch]
            vs = [line for i, line in enumerate(vertical) if len(horizontal) + i in branch]
            if not hs or not vs:
                continue
            box = _bbox(hs, vs)
            left, bottom, right, top = box
            if right - left < 8 or top - bottom < 8:
                continue
            if cut < len(horizontal):
                hs = sorted(hs + [(horizontal[cut][0], left, right)])
            else:
                vs = sorted(vs + [(vertical[cut - len(horizontal)][0], bottom, top)])
            if not _closed(hs, vs, box, tolerance):
                continue
            fragments = [f for f in _fragments_inside(fragment_index, box) if f.text.strip()]
            if not fragments:
                continue
            parent_h = [line for i, line in enumerate(horizontal) if i not in branch]
            parent_v = [line for i, line in enumerate(vertical) if len(horizontal) + i not in branch]
            if len(parent_h) < 2 or len(parent_v) < 2:
                continue
            parent_box = _bbox(parent_h, parent_v)
            if box == parent_box or not _inside(box, parent_box):
                continue
            # 작은 자식부터 판정한다. 거부할 가지마다 큰 부모 격자를 만들지 않는다.
            cx, cy = axes(hs, vs)
            child_cells = (len(cx) - 1) * (len(cy) - 1)
            grid_hs, grid_vs = grid_rules(hs, vs, cx, cy)
            if (child_cells > cell_limit or not split_budget.spend(
                    _grid_cost(grid_hs, grid_vs, cx, cy) + len(fragments))):
                return exhausted()
            _, owners, child_boxes = _make_grid(grid_hs, grid_vs, cx, cy, tolerance, None)
            filled = set()
            ascending_y = list(reversed(cy))
            for fragment in fragments:
                x, y = _reference_point(fragment)
                c = bisect_right(cx, x) - 1
                r = len(cy) - 2 - (bisect_right(ascending_y, y) - 1)
                if not (0 <= c < len(cx) - 1 and 0 <= r < len(cy) - 1):
                    continue
                key = owners[r * (len(cx) - 1) + c]
                left_edge, bottom_edge, right_edge, top_edge = child_boxes[key]
                if (left_edge + 0.5 <= x <= right_edge - 0.5
                        and bottom_edge + 0.5 <= y <= top_edge - 0.5):
                    filled.add(key)
            if not filled or not (len(filled) >= 2 or child_cells >= 4 or
                                  (child_cells == 1 and right - left >= 30 and top - bottom >= 12)):
                continue
            px, py = axes(parent_h, parent_v)
            cells = (len(px) - 1) * (len(py) - 1)
            grid_ph, grid_pv = grid_rules(parent_h, parent_v, px, py)
            if (cells + child_cells > cell_limit or not split_budget.spend(
                    _grid_cost(grid_ph, grid_pv, px, py))):
                return exhausted()
            # 실제 노드와 같은 점선 보강 격자로 부모·자식의 동시 채택을 확인한다.
            _, _, boxes = _make_grid(grid_ph, grid_pv, px, py, tolerance, None)
            containers = [outer for outer in boxes.values() if _inside(box, outer)]
            if len(containers) != 1:
                continue
            gaps = [abs(a - b) for a, b in zip(box, containers[0])]
            if sum(gap <= tolerance for gap in gaps) != 1:
                continue
            if accepted is not None:
                return unchanged
            accepted = [(parent_h, parent_v), (hs, vs)]
    return accepted if accepted is not None else unchanged
