"""페이지 콘텐츠 스트림 해석 — 텍스트 배치를 좌표까지 재구성한다.

텍스트 행렬(Tm/Td/TD/T*)과 글리프 폭(WidthMap)으로 각 텍스트 조각의
실제 x/y 를 누적한다. 이 좌표가 있어야 단어 간격, 열 경계(표), 읽기
순서를 어림짐작이 아닌 실측으로 복원할 수 있다. 그래픽 연산자는 무시한다.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .objects import DELIMITERS, WHITESPACE, PDFLexer, PDFName, PDFSyntaxError
from .widths import WidthMap

_OPERAND_START = b"(</[0123456789+-."

# 같은 기준선으로 볼 y 허용오차 (device 단위)
_LINE_Y_TOLERANCE = 3.0


def default_byte_decoder(raw: bytes) -> str:
    """ToUnicode 가 없는 단순 폰트의 기본 바이트 해석."""
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


@dataclass
class FontInfo:
    """폰트별 텍스트 해석 정보."""
    decode: Callable[[bytes], str]
    widths: WidthMap
    code_bytes: int = 1  # 1=단순 폰트, 2=Type0/Identity-H CID
    bold: bool = False
    italic: bool = False


@dataclass
class Fragment:
    """한 번의 Tj/TJ 로 그려진 텍스트 조각과 그 시작 위치."""
    x: float
    y: float
    width: float   # device 폭
    size: float    # 유효 폰트 크기
    text: str
    space_width: float  # 이 조각 폰트의 공백 1칸 device 폭 (간격 판정용)
    bold: bool = False
    italic: bool = False


def _matmul(m1, m2):
    """2x3 아핀 행렬 곱 (m1 × m2). 각 행렬은 (a,b,c,d,e,f)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


class ContentTextExtractor:
    """콘텐츠 스트림에서 위치 인식 텍스트를 추출한다."""

    def __init__(self, font_decoders: Optional[Dict[str, Callable[[bytes], str]]] = None,
                 fonts: Optional[Dict[str, FontInfo]] = None):
        # 하위 호환: 디코더 dict 만 주어지면 폭 정보 없는 FontInfo 로 감싼다
        if fonts is not None:
            self._fonts = fonts
        else:
            decoders = font_decoders or {}
            self._fonts = {
                name: FontInfo(decode=dec, widths=WidthMap({}, 500.0), code_bytes=1)
                for name, dec in decoders.items()
            }

    @classmethod
    def from_fonts(cls, fonts: Dict[str, FontInfo]) -> "ContentTextExtractor":
        return cls(fonts=fonts)

    # ── 공개 API ──

    def extract(self, content: bytes) -> List[str]:
        return [text for text, _size in self.extract_sized(content)]

    def extract_sized(self, content: bytes) -> List[Tuple[str, float]]:
        """읽기 순서로 정렬된 (줄 텍스트, 최대 폰트 크기) 목록."""
        frags = self.extract_fragments(content)
        return [(line.text, line.size) for line in self._assemble_lines(frags)]

    def extract_lines(self, content: bytes) -> List["_Line"]:
        """열 경계 재구성을 위한 라인 객체(세그먼트 좌표 포함) 목록."""
        return self._assemble_lines(self.extract_fragments(content))

    # ── 좌표 기반 조각 추출 ──

    def extract_fragments(self, content: bytes) -> List[Fragment]:
        lexer = PDFLexer(content)
        frags: List[Fragment] = []
        operands: List[object] = []
        # 텍스트 상태
        tm = (1, 0, 0, 1, 0, 0)   # 텍스트 행렬
        tlm = (1, 0, 0, 1, 0, 0)  # 텍스트 라인 행렬
        font: Optional[FontInfo] = None
        fs = 0.0     # Tf 크기
        tc = 0.0     # 문자 간격
        tw = 0.0     # 단어 간격
        th = 1.0     # 수평 스케일 (Tz/100)
        tl = 0.0     # 행간
        n = len(content)
        while True:
            lexer.skip_whitespace()
            if lexer.pos >= n:
                break
            ch = content[lexer.pos]
            if ch in _OPERAND_START:
                try:
                    operands.append(lexer.parse_object())
                except PDFSyntaxError:
                    lexer.pos += 1
                if len(operands) > 64:
                    del operands[:-8]
                continue
            op = lexer.read_token()
            if not op:
                lexer.pos += 1
                continue

            if op == b"BT":
                tm = (1, 0, 0, 1, 0, 0)
                tlm = (1, 0, 0, 1, 0, 0)
            elif op == b"Tf":
                if len(operands) >= 2 and isinstance(operands[-2], PDFName):
                    font = self._fonts.get(str(operands[-2]))
                if operands and isinstance(operands[-1], (int, float)):
                    fs = float(operands[-1])
            elif op == b"Tc" and operands and isinstance(operands[-1], (int, float)):
                tc = float(operands[-1])
            elif op == b"Tw" and operands and isinstance(operands[-1], (int, float)):
                tw = float(operands[-1])
            elif op == b"Tz" and operands and isinstance(operands[-1], (int, float)):
                th = float(operands[-1]) / 100.0
            elif op == b"TL" and operands and isinstance(operands[-1], (int, float)):
                tl = float(operands[-1])
            elif op == b"Td" and len(operands) >= 2:
                tx = _num(operands[-2])
                ty = _num(operands[-1])
                tlm = _matmul((1, 0, 0, 1, tx, ty), tlm)
                tm = tlm
            elif op == b"TD" and len(operands) >= 2:
                tx = _num(operands[-2])
                ty = _num(operands[-1])
                tl = -ty
                tlm = _matmul((1, 0, 0, 1, tx, ty), tlm)
                tm = tlm
            elif op == b"Tm" and len(operands) >= 6:
                tm = tuple(_num(o) for o in operands[-6:])
                tlm = tm
            elif op == b"T*":
                tlm = _matmul((1, 0, 0, 1, 0, -tl), tlm)
                tm = tlm
            elif op == b"Tj":
                if operands and isinstance(operands[-1], bytes):
                    tm = self._show(operands[-1], tm, font, fs, tc, tw, th, frags)
            elif op in (b"'", b'"'):
                tlm = _matmul((1, 0, 0, 1, 0, -tl), tlm)
                tm = tlm
                if op == b'"' and len(operands) >= 3:
                    tw = _num(operands[-3])
                    tc = _num(operands[-2])
                if operands and isinstance(operands[-1], bytes):
                    tm = self._show(operands[-1], tm, font, fs, tc, tw, th, frags)
            elif op == b"TJ":
                if operands and isinstance(operands[-1], list):
                    for item in operands[-1]:
                        if isinstance(item, bytes):
                            tm = self._show(item, tm, font, fs, tc, tw, th, frags)
                        elif isinstance(item, (int, float)):
                            adj = -item / 1000.0 * fs * th
                            tm = _matmul((1, 0, 0, 1, adj, 0), tm)
            elif op == b"BI":
                lexer.pos = self._skip_inline_image(content, lexer.pos)
            operands = []
        return frags

    def _show(self, raw, tm, font, fs, tc, tw, th, frags):
        if not raw:
            return tm
        if font is None:
            # Tf 미지정/미해석 폰트 — 텍스트 유실 방지용 기본 폰트
            font = FontInfo(decode=default_byte_decoder, widths=WidthMap({}, 500.0), code_bytes=1)
        text = font.decode(raw)
        start_tm = tm
        # 조각 전체 device 폭을 계산하며 tm 을 전진
        total_adv = 0.0
        codes = self._iter_codes(raw, font.code_bytes)
        for code in codes:
            w0 = font.widths.advance(code) / 1000.0
            disp = (w0 * fs + tc + (tw if (font.code_bytes == 1 and code == 32) else 0.0)) * th
            total_adv += disp
        scale = (start_tm[0] ** 2 + start_tm[1] ** 2) ** 0.5 or 1.0
        space_w = font.widths.advance(32) / 1000.0 * fs * th * scale
        if space_w <= 0:
            space_w = 0.25 * fs * scale
        eff_size = fs * ((abs(start_tm[0] * start_tm[3] - start_tm[1] * start_tm[2])) ** 0.5 or 1.0)
        if text.strip():
            frags.append(Fragment(
                x=start_tm[4], y=start_tm[5],
                width=total_adv * scale, size=eff_size,
                text=text, space_width=space_w,
                bold=font.bold, italic=font.italic,
            ))
        return _matmul((1, 0, 0, 1, total_adv, 0), tm)

    @staticmethod
    def _iter_codes(raw: bytes, code_bytes: int):
        if code_bytes == 2:
            return [(raw[i] << 8) | raw[i + 1] for i in range(0, len(raw) - 1, 2)]
        return list(raw)

    @staticmethod
    def _skip_inline_image(data: bytes, pos: int) -> int:
        """이진 데이터 속 우연한 'EI' 를 피해 공백 구분된 종결자를 찾는다."""
        n = len(data)
        while True:
            end = data.find(b"EI", pos)
            if end < 0:
                return n
            before_ok = end == 0 or data[end - 1] in WHITESPACE
            after = data[end + 2:end + 3]
            after_ok = not after or after[0] in WHITESPACE or after[0] in DELIMITERS
            if before_ok and after_ok:
                return end + 2
            pos = end + 1

    # ── 조각 → 줄 조립 (읽기 순서) ──

    def _assemble_lines(self, frags: List[Fragment]) -> List["_Line"]:
        """콘텐츠 스트림 순서를 보존하며 같은 기준선 조각을 한 줄로 묶는다.

        전역 y 정렬은 CTM(그래픽 행렬)을 반영하지 않아 각주/머리말이
        본문 위로 튀는 등 읽기 순서를 망가뜨린다. 생성기가 의도한
        그리기 순서(대개 곧 읽기 순서)를 유지하고, y 가 크게 바뀔 때만
        줄을 나눈다. 줄 안에서만 x 로 정렬해 좌→우 배치를 바로잡는다.
        """
        if not frags:
            return []
        rows: List[List[Fragment]] = []
        current: List[Fragment] = []
        current_y: Optional[float] = None
        for frag in frags:
            if current_y is None or abs(frag.y - current_y) <= _LINE_Y_TOLERANCE:
                current.append(frag)
                current_y = frag.y if current_y is None else current_y
            else:
                rows.append(current)
                current = [frag]
                current_y = frag.y
        if current:
            rows.append(current)
        # 줄 안에서 x 재정렬은 하지 않는다 — 생성기의 그리기 순서가 곧 읽기
        # 순서이고, 불완전한 x(=CTM 미반영) 로 정렬하면 문자가 뒤섞인다.
        # x 는 간격/열 판정에만 쓴다.
        return [_Line(row) for row in rows]


@dataclass
class _Segment:
    x0: float
    x1: float
    text: str


class _Line:
    """한 기준선의 텍스트 — 세그먼트 좌표와 조립된 문자열."""

    def __init__(self, frags: List[Fragment]):
        self.y = frags[0].y
        self.size = max((f.size for f in frags), default=0.0)
        self.segments: List[_Segment] = []
        parts: List[str] = []
        # 서식이 같은 인접 조각은 하나의 run 으로 묶는다 (부분 굵게 보존)
        self.runs: List[Tuple[str, bool, bool]] = []
        prev_end: Optional[float] = None
        prev_space: float = 0.0
        for f in frags:
            gap = (f.x - prev_end) if prev_end is not None else 0.0
            threshold = max(prev_space, f.space_width) * 0.5
            sep = ""
            if prev_end is not None and gap > threshold and parts and not parts[-1].endswith(" "):
                sep = " "
            if sep:
                parts.append(sep)
                self._append_run(sep, f.bold, f.italic)
            parts.append(f.text)
            self._append_run(f.text, f.bold, f.italic)
            self.segments.append(_Segment(f.x, f.x + f.width, f.text))
            prev_end = f.x + f.width
            prev_space = f.space_width
        self.text = "".join(parts).strip()

    def _append_run(self, text: str, bold: bool, italic: bool) -> None:
        if self.runs and self.runs[-1][1] == bold and self.runs[-1][2] == italic:
            prev = self.runs[-1]
            self.runs[-1] = (prev[0] + text, bold, italic)
        else:
            self.runs.append((text, bold, italic))


def _num(value) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
