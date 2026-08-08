"""페이지 콘텐츠 스트림 해석 — 텍스트 연산자만 다룬다.

그래픽 연산자는 무시하고 BT/ET 블록의 텍스트 배치 연산자
(Tf, Td, TD, Tm, T*, Tj, TJ, ', ")로 줄 단위 텍스트를 재구성한다.
"""
from typing import Callable, Dict, List, Optional

from .objects import PDFLexer, PDFName, PDFSyntaxError

# TJ 배열에서 이보다 작은(더 음수인) 조정값은 단어 간격으로 본다 (1/1000 em 단위)
_SPACE_ADJUST_THRESHOLD = -180.0

_OPERAND_START = b"(</[0123456789+-."


def default_byte_decoder(raw: bytes) -> str:
    """ToUnicode 가 없는 단순 폰트의 기본 바이트 해석."""
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


class ContentTextExtractor:
    """콘텐츠 스트림에서 줄 단위 텍스트를 추출한다."""

    def __init__(self, font_decoders: Dict[str, Callable[[bytes], str]]):
        self._decoders = font_decoders
        self._decoder: Optional[Callable[[bytes], str]] = None
        self._last_y: Optional[float] = None

    def extract(self, content: bytes) -> List[str]:
        lexer = PDFLexer(content)
        lines: List[str] = []
        current: List[str] = []
        operands: List[object] = []
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
                continue
            token = lexer.read_token()
            if not token:
                lexer.pos += 1
                continue
            self._apply_operator(token, operands, lines, current, lexer)
            operands = []
        self._flush(lines, current)
        return lines

    def _apply_operator(self, op, operands, lines, current, lexer) -> None:
        if op == b"Tf":
            if len(operands) >= 2 and isinstance(operands[0], PDFName):
                self._decoder = self._decoders.get(str(operands[0]))
        elif op in (b"BT", b"ET"):
            # 텍스트 블록 경계 자체는 줄바꿈이 아니다 — HWP→PDF 내보내기처럼
            # 단어(어절)마다 BT/ET 를 쓰는 생성기가 많아 y 좌표 변화로만 판단한다
            pass
        elif op == b"T*":
            self._flush(lines, current)
            self._last_y = None  # leading 만큼 이동 — 절대 y 를 모르므로 리셋
        elif op in (b"Td", b"TD"):
            tx = operands[0] if len(operands) >= 2 and isinstance(operands[0], (int, float)) else 0
            ty = operands[1] if len(operands) >= 2 and isinstance(operands[1], (int, float)) else 0
            if ty != 0:
                self._flush(lines, current)
                if self._last_y is not None:
                    self._last_y += ty
            elif tx > 0:
                self._append_space(current)
        elif op == b"Tm" and len(operands) >= 6:
            y = operands[5] if isinstance(operands[5], (int, float)) else None
            if self._last_y is not None and y is not None and abs(y - self._last_y) <= 0.5:
                self._append_space(current)  # 같은 기준선 — 단어 간 이동으로 본다
            else:
                self._flush(lines, current)
            self._last_y = y
        elif op == b"Tj":
            if operands:
                self._show(operands[-1], current)
        elif op in (b"'", b'"'):
            self._flush(lines, current)
            self._last_y = None
            if operands:
                self._show(operands[-1], current)
        elif op == b"TJ":
            if operands and isinstance(operands[-1], list):
                for item in operands[-1]:
                    if isinstance(item, bytes):
                        self._show(item, current)
                    elif isinstance(item, (int, float)) and item < _SPACE_ADJUST_THRESHOLD:
                        if current and not current[-1].endswith(" "):
                            current.append(" ")
        elif op == b"BI":
            # 인라인 이미지 — 텍스트 흐름을 끊고, 이진 데이터를 렉서가
            # 오해하지 않도록 EI 까지 건너뜀
            self._flush(lines, current)
            self._last_y = None
            end = lexer.data.find(b"EI", lexer.pos)
            lexer.pos = len(lexer.data) if end < 0 else end + 2

    def _show(self, raw, current) -> None:
        if not isinstance(raw, bytes):
            return
        decoder = self._decoder or default_byte_decoder
        current.append(decoder(raw))

    @staticmethod
    def _append_space(current) -> None:
        if current and not current[-1].endswith(" "):
            current.append(" ")

    @staticmethod
    def _flush(lines, current) -> None:
        if current:
            text = "".join(current).strip()
            if text:
                lines.append(text)
            current.clear()
