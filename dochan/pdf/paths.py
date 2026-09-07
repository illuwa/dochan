"""콘텐츠 해석 중 장치 좌표의 수평·수직 괘선을 수집한다."""
from dataclasses import dataclass
from math import hypot, isfinite

MAX_SEGMENTS = 20_000
_THIN = 2.0          # 이 두께 이하의 채움 도형은 선으로 본다 (장치 단위)
_STRAIGHT = 1.0      # 곡선 제어점이 현에서 이만큼 이하로 벗어나면 직선으로 본다


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


def _axis_segment(p0, p1):
    """두 점을 잇는 축 정렬 선분. 사선·아주 짧은 선·비정상 좌표는 None."""
    x0, y0 = p0
    x1, y1 = p1
    if not all(isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    if (abs(x1 - x0) <= 0.6 or abs(y1 - y0) <= 0.6) and hypot(x1 - x0, y1 - y0) >= 1:
        return Segment(x0, y0, x1, y1)
    return None


def _thin(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(max(xs) - min(xs), max(ys) - min(ys)) <= _THIN


def _deviation(p0, p1, control):
    """제어점이 현(p0→p1)에서 벗어난 거리."""
    (x0, y0), (x1, y1), (cx, cy) = p0, p1, control
    dx, dy = x1 - x0, y1 - y0
    length = hypot(dx, dy)
    if length < 1e-9:
        return hypot(cx - x0, cy - y0)
    return abs(dx * (cy - y0) - dy * (cx - x0)) / length


class PathCollector:
    """서브패스 단위로 점과 변을 모으고, 칠하기 연산자에서 괘선만 내보낸다."""

    def __init__(self):
        self.segments = []
        self.warnings = []
        self._groups = []       # 현재 경로의 서브패스: (점 목록, 변 목록)
        self._edge_count = 0
        self._overflow = False
        self._point = None
        self._start = None

    def _warn(self):
        if not self.warnings:
            self.warnings.append("WARN: PDF 선분 수 한도(20000) 초과 — 일부 괘선 생략")

    def _move(self, point):
        self._groups.append(([point], []))
        self._point = self._start = point

    def _line(self, point, emit=True, extra_points=()):
        if self._point is None:
            self._move(point)
            return
        if not self._groups:
            self._groups.append(([self._point], []))
        points, edges = self._groups[-1]
        points.extend(extra_points)
        points.append(point)
        if emit:
            segment = _axis_segment(self._point, point)
            if segment is not None:
                if self._edge_count < MAX_SEGMENTS:
                    edges.append(segment)
                    self._edge_count += 1
                else:
                    self._overflow = True
        self._point = point

    def _curve(self, controls, end):
        """제어점이 현에 붙어 있을 때만 직선으로 취급한다. 굽은 곡선은 변을 만들지 않는다."""
        if self._point is None:
            self._move(end)
            return
        straight = all(_deviation(self._point, end, c) <= _STRAIGHT for c in controls)
        self._line(end, emit=straight, extra_points=controls)

    def operate(self, op, values, ctm):
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
            self._edge_count = 0
            self._overflow = False
            self._point = self._start = None

    def _paint(self, stroke):
        """획은 모든 변을, 채움은 얇은 서브패스(선처럼 그린 사각형)의 변만 내보낸다."""
        if self._overflow:
            self._warn()
        for points, edges in self._groups:
            if not edges or not (stroke or _thin(points)):
                continue
            for segment in edges:
                if len(self.segments) >= MAX_SEGMENTS:
                    self._warn()
                    return
                self.segments.append(segment)
