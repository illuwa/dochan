"""PDF 폰트 글리프 폭 맵 — 텍스트 전진량(advance) 계산용.

폭은 텍스트 공간 단위(1/1000 em)로 저장한다. 단순 폰트는 /Widths+/FirstChar,
합성(Type0/CID) 폰트는 /W 배열 + /DW 기본폭으로 구성한다. 이 폭이 있어야
글리프 단위 x 좌표를 정확히 누적해 열 경계·읽기 순서·단어 간격을 재구성한다.
"""
from typing import Dict, List


class WidthMap:
    """문자 코드(또는 CID) → 전진 폭(1/1000 em)."""

    def __init__(self, widths: Dict[int, float], default: float):
        self._widths = widths
        self._default = default

    def advance(self, code: int) -> float:
        return self._widths.get(code, self._default)

    @classmethod
    def simple(cls, first_char: int, widths: List, default: float = 500.0) -> "WidthMap":
        table: Dict[int, float] = {}
        for i, w in enumerate(widths):
            if isinstance(w, (int, float)):
                table[first_char + i] = float(w)
        return cls(table, default)

    @classmethod
    def cid(cls, w_array: List, default_width: float = 1000.0) -> "WidthMap":
        """/W 배열 파싱. 두 형식: `c [w1 w2 ...]` 와 `c_first c_last w`."""
        table: Dict[int, float] = {}
        i = 0
        n = len(w_array)
        while i < n:
            if not isinstance(w_array[i], (int, float)):
                i += 1
                continue
            start = int(w_array[i])
            if i + 1 < n and isinstance(w_array[i + 1], list):
                for j, w in enumerate(w_array[i + 1]):
                    if isinstance(w, (int, float)):
                        table[start + j] = float(w)
                i += 2
            elif i + 2 < n and isinstance(w_array[i + 1], (int, float)) \
                    and isinstance(w_array[i + 2], (int, float)):
                end = int(w_array[i + 1])
                w = float(w_array[i + 2])
                if 0 <= end - start < 65536:
                    for code in range(start, end + 1):
                        table[code] = w
                i += 3
            else:
                i += 1
        return cls(table, default_width)
