"""PDF 객체 문법 파서 — 렉서와 기본 객체 파싱.

PDF 32000-1:2008 §7.3 의 객체 문법(불리언, 숫자, 문자열, 이름, 배열,
사전, 스트림, null, 간접 참조)을 표준 라이브러리만으로 파싱한다.
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"

MAX_COLLECTION_ITEMS = 100_000
MAX_NESTING_DEPTH = 64


class PDFSyntaxError(ValueError):
    """PDF 객체 문법 위반."""


@dataclass(frozen=True)
class PDFRef:
    """간접 객체 참조 (`12 0 R`)."""
    num: int
    gen: int


class PDFName(str):
    """PDF 이름 객체 (`/Name`). str 부분클래스라 사전 키로 그대로 쓴다."""


@dataclass
class PDFStream:
    """스트림 객체 — 사전과 원본(필터 미해제) 바이트."""
    dictionary: dict
    raw: bytes


class PDFLexer:
    """바이트 버퍼 위의 순차 파서."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos
        self._depth = 0

    def _peek(self) -> int:
        if self.pos >= len(self.data):
            return -1
        return self.data[self.pos]

    def skip_whitespace(self) -> None:
        data, n = self.data, len(self.data)
        while self.pos < n:
            ch = data[self.pos]
            if ch in WHITESPACE:
                self.pos += 1
            elif ch == 0x25:  # '%' 주석은 줄 끝까지
                while self.pos < n and data[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                return

    def read_token(self) -> bytes:
        start = self.pos
        data, n = self.data, len(self.data)
        while self.pos < n:
            ch = data[self.pos]
            if ch in WHITESPACE or ch in DELIMITERS:
                break
            self.pos += 1
        return data[start:self.pos]

    def parse_object(self) -> Any:
        self.skip_whitespace()
        ch = self._peek()
        if ch < 0:
            raise PDFSyntaxError("예상치 못한 EOF")
        if ch == 0x3C:  # '<'
            if self.data[self.pos:self.pos + 2] == b"<<":
                return self._parse_dict()
            return self._parse_hex_string()
        if ch == 0x28:  # '('
            return self._parse_literal_string()
        if ch == 0x2F:  # '/'
            return self._parse_name()
        if ch == 0x5B:  # '['
            return self._parse_array()
        token = self.read_token()
        if not token:
            raise PDFSyntaxError(
                f"파싱할 수 없는 문자: {self.data[self.pos:self.pos + 8]!r}"
            )
        if token == b"true":
            return True
        if token == b"false":
            return False
        if token == b"null":
            return None
        return self._parse_number_or_ref(token)

    def _parse_number_or_ref(self, token: bytes) -> Any:
        try:
            if b"." in token:
                return float(token)
            value = int(token)
        except ValueError:
            raise PDFSyntaxError(f"잘못된 숫자 토큰: {token!r}")
        if value >= 0:
            saved = self.pos
            self.skip_whitespace()
            token2 = self.read_token()
            if token2.isdigit():
                self.skip_whitespace()
                if self.read_token() == b"R":
                    return PDFRef(value, int(token2))
            self.pos = saved
        return value

    def _parse_name(self) -> PDFName:
        self.pos += 1  # '/'
        raw = self.read_token()
        out = bytearray()
        i = 0
        while i < len(raw):
            if raw[i:i + 1] == b"#" and i + 2 < len(raw):
                try:
                    out.append(int(raw[i + 1:i + 3], 16))
                    i += 3
                    continue
                except ValueError:
                    pass
            out.append(raw[i])
            i += 1
        return PDFName(out.decode("utf-8", errors="replace"))

    def _parse_literal_string(self) -> bytes:
        self.pos += 1  # '('
        out = bytearray()
        depth = 1
        data, n = self.data, len(self.data)
        while self.pos < n:
            ch = data[self.pos]
            if ch == 0x5C:  # '\'
                self.pos += 1
                if self.pos >= n:
                    break
                esc = data[self.pos]
                if esc == 0x6E:
                    out.append(0x0A)
                elif esc == 0x72:
                    out.append(0x0D)
                elif esc == 0x74:
                    out.append(0x09)
                elif esc == 0x62:
                    out.append(0x08)
                elif esc == 0x66:
                    out.append(0x0C)
                elif esc in (0x28, 0x29, 0x5C):
                    out.append(esc)
                elif 0x30 <= esc <= 0x37:  # 8진 이스케이프 최대 3자리
                    octal = chr(esc)
                    for _ in range(2):
                        nxt = data[self.pos + 1] if self.pos + 1 < n else -1
                        if 0x30 <= nxt <= 0x37:
                            self.pos += 1
                            octal += chr(nxt)
                        else:
                            break
                    out.append(int(octal, 8) & 0xFF)
                elif esc in (0x0D, 0x0A):  # 줄 연속은 무시
                    if esc == 0x0D and self.pos + 1 < n and data[self.pos + 1] == 0x0A:
                        self.pos += 1
                else:
                    out.append(esc)
                self.pos += 1
            elif ch == 0x28:
                depth += 1
                out.append(ch)
                self.pos += 1
            elif ch == 0x29:
                depth -= 1
                self.pos += 1
                if depth == 0:
                    return bytes(out)
                out.append(ch)
            else:
                out.append(ch)
                self.pos += 1
        raise PDFSyntaxError("닫히지 않은 리터럴 문자열")

    def _parse_hex_string(self) -> bytes:
        self.pos += 1  # '<'
        end = self.data.find(b">", self.pos)
        if end < 0:
            raise PDFSyntaxError("닫히지 않은 16진 문자열")
        hex_chars = bytes(c for c in self.data[self.pos:end] if c not in WHITESPACE)
        self.pos = end + 1
        if len(hex_chars) % 2:
            hex_chars += b"0"
        try:
            return bytes.fromhex(hex_chars.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            raise PDFSyntaxError("잘못된 16진 문자열")

    def _parse_array(self) -> list:
        self.pos += 1  # '['
        self._depth += 1
        try:
            if self._depth > MAX_NESTING_DEPTH:
                raise PDFSyntaxError("중첩 깊이가 한도를 초과")
            items = []
            while True:
                self.skip_whitespace()
                if self._peek() == 0x5D:
                    self.pos += 1
                    return items
                if self._peek() < 0:
                    raise PDFSyntaxError("닫히지 않은 배열")
                if len(items) >= MAX_COLLECTION_ITEMS:
                    raise PDFSyntaxError("배열 항목 수가 한도를 초과")
                items.append(self.parse_object())
        finally:
            self._depth -= 1

    def _parse_dict(self) -> dict:
        self.pos += 2  # '<<'
        self._depth += 1
        try:
            if self._depth > MAX_NESTING_DEPTH:
                raise PDFSyntaxError("중첩 깊이가 한도를 초과")
            result = {}
            while True:
                self.skip_whitespace()
                if self.data[self.pos:self.pos + 2] == b">>":
                    self.pos += 2
                    return result
                if self._peek() != 0x2F:
                    raise PDFSyntaxError("사전 키는 이름이어야 함")
                if len(result) >= MAX_COLLECTION_ITEMS:
                    raise PDFSyntaxError("사전 항목 수가 한도를 초과")
                key = self._parse_name()
                result[str(key)] = self.parse_object()
        finally:
            self._depth -= 1


def parse_indirect_object(
    data: bytes,
    offset: int,
    resolve: Optional[Callable[[PDFRef], Any]] = None,
) -> Tuple[int, int, Any]:
    """`num gen obj ... endobj` 를 파싱한다.

    resolve: 스트림 /Length 가 간접 참조일 때 정수로 해석하는 콜백.
    /Length 가 틀리거나 없으면 `endstream` 탐색으로 보정한다.
    """
    lexer = PDFLexer(data, offset)
    lexer.skip_whitespace()
    num_tok = lexer.read_token()
    lexer.skip_whitespace()
    gen_tok = lexer.read_token()
    lexer.skip_whitespace()
    obj_tok = lexer.read_token()
    if not num_tok.isdigit() or not gen_tok.isdigit() or obj_tok != b"obj":
        raise PDFSyntaxError(f"오프셋 {offset}: 간접 객체 헤더가 아님")
    obj = lexer.parse_object()
    lexer.skip_whitespace()
    keyword_pos = lexer.pos
    keyword = lexer.read_token()
    if keyword == b"stream" and isinstance(obj, dict):
        if lexer.data[lexer.pos:lexer.pos + 2] == b"\r\n":
            lexer.pos += 2
        elif lexer.data[lexer.pos:lexer.pos + 1] in (b"\n", b"\r"):
            lexer.pos += 1
        start = lexer.pos
        length = obj.get("Length")
        if resolve is not None and isinstance(length, PDFRef):
            length = resolve(length)
        raw = None
        if isinstance(length, int) and 0 <= length <= len(data) - start:
            candidate_end = start + length
            tail = data[candidate_end:candidate_end + 20]
            if tail.lstrip(WHITESPACE).startswith(b"endstream"):
                raw = data[start:candidate_end]
        if raw is None:
            end = data.find(b"endstream", start)
            if end < 0:
                raise PDFSyntaxError("endstream 누락")
            raw = data[start:end]
            # 스트림 끝의 EOL 은 구분자 하나만 제거 — 전부 지우면 0x0A 로 끝나는
            # 이진 payload 가 손상된다
            if raw.endswith(b"\r\n"):
                raw = raw[:-2]
            elif raw.endswith((b"\n", b"\r")):
                raw = raw[:-1]
        return int(num_tok), int(gen_tok), PDFStream(obj, raw)
    lexer.pos = keyword_pos
    return int(num_tok), int(gen_tok), obj
