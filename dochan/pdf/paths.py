"""콘텐츠 해석 중 장치 좌표의 수평·수직 괘선을 수집한다."""
from dataclasses import dataclass
from math import hypot, isfinite
from typing import List, Optional

MAX_SEGMENTS = 20_000  # 페이지당 변(edge)·서브패스 수 상한 — 칠하기 없는 m/l 반복의 메모리 폭주 방지
_THIN = 2.0            # 이 두께 이하의 채움 도형은 선으로 본다 (장치 단위)
_STRAIGHT = 1.0        # 곡선 제어점이 현에서 이만큼 이하로 벗어나면 직선으로 본다


@dataclass
class Segment:
    """정규화된 장치 좌표 선분."""
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        self.x0, self.x1 = sorted((self.x0, self.x1))
        self.y0, self.y1 = sorted((self.y0, self.y1))

    @property
    def length(self) -> float:
        return hypot(self.x1 - self.x0, self.y1 - self.y0)


def _axis_segment(p0, p1) -> Optional[Segment]:
    """두 점을 잇는 축 정렬 선분. 사선·아주 짧은 선·비정상 좌표는 None."""
    x0, y0 = p0
    x1, y1 = p1
    if not all(isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    if (abs(x1 - x0) <= 0.6 or abs(y1 - y0) <= 0.6) and hypot(x1 - x0, y1 - y0) >= 1:
        return Segment(x0, y0, x1, y1)
    return None


def _deviation(p0, p1, control) -> float:
    """제어점이 현(p0→p1)에서 벗어난 거리."""
    (x0, y0), (x1, y1), (cx, cy) = p0, p1, control
    dx, dy = x1 - x0, y1 - y0
    length = hypot(dx, dy)
    if length < 1e-9:
        return hypot(cx - x0, cy - y0)
    return abs(dx * (cy - y0) - dy * (cx - x0)) / length


class _Subpath:
    """서브패스 하나의 경계 상자와 변 목록. 점은 저장하지 않는다 — 메모리는 상수."""
    __slots__ = ("x0", "y0", "x1", "y1", "edges")

    def __init__(self, point):
        self.x0 = self.x1 = point[0]
        self.y0 = self.y1 = point[1]
        self.edges: List[Segment] = []

    def include(self, point) -> None:
        x, y = point
        if isfinite(x) and isfinite(y):
            self.x0, self.x1 = min(self.x0, x), max(self.x1, x)
            self.y0, self.y1 = min(self.y0, y), max(self.y1, y)

    @property
    def thin(self) -> bool:
        return min(self.x1 - self.x0, self.y1 - self.y0) <= _THIN


class PathCollector:
    """서브패스 단위로 경계 상자와 변을 모으고, 칠하기 연산자에서 괘선만 내보낸다."""

    def __init__(self):
        self.segments: List[Segment] = []
        self.warnings: List[str] = []
        self._groups: List[_Subpath] = []
        self._current: Optional[_Subpath] = None
        self._edge_count = 0
        self._overflow = False
        self._point = None
        self._start = None

    def _warn(self) -> None:
        if not self.warnings:
            self.warnings.append("WARN: PDF 선분 수 한도(20000) 초과 — 일부 괘선 생략")

    def _move(self, point) -> None:
        if len(self._groups) < MAX_SEGMENTS:
            self._current = _Subpath(point)
            self._groups.append(self._current)
        else:
            # 상한 이후의 서브패스는 버린다 — 현재 점만 따라가고 경고를 남긴다
            self._current = None
            self._overflow = True
            self._warn()
        self._point = self._start = point

    def _line(self, point, emit=True, extra_points=()) -> None:
        if self._point is None:
            self._move(point)
            return
        if self._current is None and not self._overflow:
            self._move(self._point)
        subpath = self._current
        if subpath is not None:
            for extra in extra_points:
                subpath.include(extra)
            subpath.include(point)
            if emit:
                segment = _axis_segment(self._point, point)
                if segment is not None:
                    if self._edge_count < MAX_SEGMENTS:
                        subpath.edges.append(segment)
                        self._edge_count += 1
                    else:
                        self._overflow = True
        self._point = point

    def _curve(self, controls, end) -> None:
        """제어점이 현에 붙어 있을 때만 직선으로 취급한다. 굽은 곡선은 변을 만들지 않는다."""
        if self._point is None:
            self._move(end)
            return
        straight = all(_deviation(self._point, end, c) <= _STRAIGHT for c in controls)
        self._line(end, emit=straight, extra_points=controls)

    def operate(self, op, values, ctm) -> None:
        def point(x, y):
            a, b, c, d, e, f = ctm
            return x * a + y * c + e, x * b + y * d + f

        if op == b"m" and len(values) >= 2:
            self._move(point(*values[-2:]))
        elif op == b"l" and len(values) >= 2:
            self._line(point(*values[-2:]))
        elif op == b"c" and len(values) >= 6:
            x1, y1, x2, y2, x3, y3 = values[-6:]
            self._curve((point(x1, y1), point(x2, y2)), point(x3, y3))
        elif op == b"v" and len(values) >= 4:
            x2, y2, x3, y3 = values[-4:]
            self._curve((point(x2, y2),), point(x3, y3))
        elif op == b"y" and len(values) >= 4:
            x1, y1, x3, y3 = values[-4:]
            self._curve((point(x1, y1),), point(x3, y3))
        elif op == b"re" and len(values) >= 4:
            x, y, w, h = values[-4:]
            corners = [point(x, y), point(x + w, y), point(x + w, y + h), point(x, y + h)]
            self._move(corners[0])
            for corner in corners[1:] + corners[:1]:
                self._line(corner)
        elif op == b"h" and self._start is not None:
            self._line(self._start)
        elif op in (b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"n"):
            if op in (b"s", b"b", b"b*") and self._start is not None:
                self._line(self._start)
            if op != b"n":
                self._paint(stroke=op not in (b"f", b"F", b"f*"))
            self._groups = []
            self._current = None
            self._edge_count = 0
            self._overflow = False
            self._point = self._start = None

    def _paint(self, stroke: bool) -> None:
        """획은 모든 변을, 채움은 얇은 서브패스(선처럼 그린 사각형)의 긴 변만 내보낸다."""
        if self._overflow:
            self._warn()
        for subpath in self._groups:
            if not subpath.edges or not (stroke or subpath.thin):
                continue
            for segment in subpath.edges:
                if not stroke and segment.length <= _THIN:
                    continue  # 얇은 사각형의 짧은 변은 열·행 경계가 아니다
                if len(self.segments) >= MAX_SEGMENTS:
                    self._warn()
                    return
                self.segments.append(segment)
