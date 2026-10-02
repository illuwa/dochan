"""공유 괘선 하나를 제거했을 때 분리되는 닫힌 내부 격자를 찾는다."""
from bisect import bisect_left, bisect_right

MAX_SPLIT_CHECKS = 2_000_000


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
                    max_checks=MAX_SPLIT_CHECKS, warnings=None):
    """모호한 후보·예산 초과는 입력을 그대로 반환한다. 원본 괘선은 바꾸지 않는다."""
    from .tables import (MAX_COMPONENT_LINES, MAX_PAGE_CELLS, _inside,
                         _make_grid, _fragments_inside, _reference_point, _warn)

    unchanged = [(horizontal, vertical)]

    def exhausted():
        _warn(warnings, 'WARN: PDF 연결형 중첩 표 검사 한도 초과 — 기존 격자 유지')
        return unchanged

    if not fragment_index[0]:
        return unchanged
    size = len(horizontal) + len(vertical)
    if size > MAX_COMPONENT_LINES or len(horizontal) < 2 or len(vertical) < 2:
        return unchanged
    adjacency = [set() for _ in range(size)]
    xs = [line[0] for line in vertical]
    checks = 0
    for i, (y, left, right) in enumerate(horizontal):
        lo, hi = bisect_left(xs, left - tolerance), bisect_right(xs, right + tolerance)
        checks += hi - lo
        if checks > max_checks:
            return exhausted()
        for j in range(lo, hi):
            if vertical[j][1] - tolerance <= y <= vertical[j][2] + tolerance:
                adjacency[i].add(len(horizontal) + j)
                adjacency[len(horizontal) + j].add(i)
    checks += sum(len(neighbours) for neighbours in adjacency)
    if checks > max_checks:
        return exhausted()
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
                checks += len(adjacency[item])
                if checks > max_checks:
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
            px = sorted(set(v[0] for v in parent_v))
            py = sorted(set(h[0] for h in parent_h), reverse=True)
            cells = (len(px) - 1) * (len(py) - 1)
            checks += cells
            if cells > MAX_PAGE_CELLS or checks > max_checks:
                return exhausted()
            _, _, boxes = _make_grid(parent_h, parent_v, px, py, tolerance, None)
            containers = [outer for outer in boxes.values() if _inside(box, outer)]
            if len(containers) != 1:
                continue
            gaps = [abs(a - b) for a, b in zip(box, containers[0])]
            if sum(gap <= tolerance for gap in gaps) != 1:
                continue
            cx = sorted(set(v[0] for v in vs))
            cy = sorted(set(h[0] for h in hs), reverse=True)
            child_cells = (len(cx) - 1) * (len(cy) - 1)
            checks += child_cells
            if child_cells + cells > MAX_PAGE_CELLS or checks > max_checks:
                return exhausted()
            _, owners, child_boxes = _make_grid(hs, vs, cx, cy, tolerance, None)
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
            # 기존 중첩 노드 채택 조건을 먼저 확인하여 거부할 자식 때문에
            # 부모의 격자를 바꾸지 않는다. 빈 도형은 연결형으로 승격하지 않는다.
            if not filled or not (len(filled) >= 2 or child_cells >= 4 or
                                  (child_cells == 1 and right - left >= 30 and top - bottom >= 12)):
                continue
            return [(parent_h, parent_v), (hs, vs)]
    return unchanged
