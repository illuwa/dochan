"""PDF 폰트 글리프 폭 맵 — 텍스트 전진량(advance) 계산용.

폭은 텍스트 공간 단위(1/1000 em)로 저장한다. 단순 폰트는 /Widths+/FirstChar,
합성(Type0/CID) 폰트는 /W 배열 + /DW 기본폭으로 구성한다. 이 폭이 있어야
글리프 단위 x 좌표를 정확히 누적해 열 경계·읽기 순서·단어 간격을 재구성한다.
"""
import math
from typing import Dict, List


class WidthMap:
    """문자 코드(또는 CID) → 전진 폭(1/1000 em)."""

    def __init__(self, widths: Dict[int, float], default: float, cid_default: bool = False):
        self._widths = widths
        self._default = default
        self._cid_default = cid_default
        self.reliable = True
        self.warnings = []

    def advance(self, code: int) -> float:
        return self._widths.get(code, self._default)

    def explicit(self, code: int) -> bool:
        """문서/AFM/표준 CID 폭과 근거 없는 추정 기본 폭을 구분한다."""
        return self.reliable and (code in self._widths or (self._cid_default and 0 <= code <= 65535))

    @classmethod
    def simple(cls, first_char: int, widths: List, default: float = 500.0) -> "WidthMap":
        table: Dict[int, float] = {}
        for i, w in enumerate(widths):
            if isinstance(w, (int, float)) and math.isfinite(w) and 0 <= first_char + i < 256:
                table[first_char + i] = float(w)
        return cls(table, default)

    @classmethod
    def cid(cls, w_array: List, default_width: float = 1000.0) -> "WidthMap":
        """/W 배열 파싱. 두 형식: `c [w1 w2 ...]` 와 `c_first c_last w`."""
        table: Dict[int, float] = {}
        warnings = []
        if not math.isfinite(default_width):
            default_width = 1000.0
            warnings.append("WARN: PDF CID 기본 폭이 비유한 수 — 표준 기본 폭 사용")
        i = 0
        n = min(len(w_array), 65536)
        budget = 65536
        while i < n:
            if not isinstance(w_array[i], int):
                i += 1
                continue
            start = int(w_array[i])
            if i + 1 < n and isinstance(w_array[i + 1], list):
                count = min(len(w_array[i + 1]), budget)
                for j, w in enumerate(w_array[i + 1][:count]):
                    if 0 <= start + j <= 65535 and isinstance(w, (int, float)) and math.isfinite(w):
                        table[start + j] = float(w)
                budget -= len(w_array[i + 1])
                i += 2
            elif i + 2 < n and isinstance(w_array[i + 1], int) \
                    and isinstance(w_array[i + 2], (int, float)) and math.isfinite(w_array[i + 2]):
                end = int(w_array[i + 1])
                w = float(w_array[i + 2])
                if 0 <= start <= end <= 65535:
                    for code in range(start, min(end + 1, start + budget)):
                        table[code] = w
                    budget -= end - start + 1
                i += 3
            else:
                i += 1
            if budget <= 0 and i < n:
                break
        if i < len(w_array) or budget < 0:
            warnings.append("WARN: PDF CID 폭 배열 처리 한도(65536)를 초과 — 일부만 사용")
        result = cls(table, default_width, cid_default=not warnings)
        result.reliable = not warnings
        result.warnings = warnings
        return result
