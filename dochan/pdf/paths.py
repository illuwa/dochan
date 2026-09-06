"""콘텐츠 해석 중 장치 좌표의 수평·수직 괘선을 수집한다."""
from dataclasses import dataclass
from math import hypot, isfinite

MAX_SEGMENTS = 20_000


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


class PathCollector:
    """현재 경로와 출력 모두에 상한을 적용한다."""

    def __init__(self):
        self.segments = []
        self.warnings = []
        self.pending = []
        self.pending_overflow = False
        self.point = None
        self.start = None

    def _warn(self):
        if not self.warnings:
            self.warnings.append("WARN: PDF 선분 수 한도(20000) 초과 — 일부 괘선 생략")

    def _edge(self, point, fill=True):
        if self.point is not None:
            x0, y0 = self.point
            x1, y1 = point
            if (all(isfinite(v) for v in (x0, y0, x1, y1))
                    and (abs(x1 - x0) <= 0.6 or abs(y1 - y0) <= 0.6)
                    and hypot(x1 - x0, y1 - y0) >= 1):
                if len(self.pending) < MAX_SEGMENTS:
                    self.pending.append((Segment(x0, y0, x1, y1), fill))
                else:
                    self.pending_overflow = True
        self.point = point

    def operate(self, op, values, ctm):
        def point(x, y):
            a, b, c, d, e, f = ctm
            return x * a + y * c + e, x * b + y * d + f

        if op == b"m" and len(values) >= 2:
            self.point = self.start = point(*values[-2:])
        elif op in (b"l", b"c", b"v", b"y") and len(values) >= 2:
            self._edge(point(*values[-2:]))
        elif op == b"re" and len(values) >= 4:
            x, y, w, h = values[-4:]
            corners = [point(x, y), point(x + w, y), point(x + w, y + h), point(x, y + h)]
            thin = min(hypot(ctm[0] * w, ctm[1] * w),
                       hypot(ctm[2] * h, ctm[3] * h)) <= 2
            self.point = self.start = corners[0]
            for corner in corners[1:] + corners[:1]:
                self._edge(corner, thin)
        elif op == b"h" and self.start is not None:
            self._edge(self.start)
        elif op in (b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"n"):
            if op in (b"s", b"b", b"b*") and self.start is not None:
                self._edge(self.start)
            if op != b"n":
                if self.pending_overflow:
                    self._warn()
                stroke = op not in (b"f", b"F", b"f*")
                for segment, fill in self.pending:
                    if stroke or fill:
                        if len(self.segments) >= MAX_SEGMENTS:
                            self._warn()
                            break
                        self.segments.append(segment)
            self.pending = []
            self.pending_overflow = False
            self.point = self.start = None
