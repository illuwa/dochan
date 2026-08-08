"""ToUnicode CMap 파싱 — 문자 코드를 유니코드 문자열로 매핑.

한국어 PDF 는 대부분 Identity-H CID 폰트 + ToUnicode CMap 조합이므로
bfchar/bfrange 해석이 한글 텍스트 추출의 핵심이다.
"""
import re
from typing import Dict, Set, Tuple

_CODESPACE_RE = re.compile(rb"begincodespacerange(.*?)endcodespacerange", re.S)
_BF_CHAR_RE = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
_BF_RANGE_RE = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
_HEX_RE = re.compile(rb"<([0-9A-Fa-f]+)>")
_TOKEN_RE = re.compile(rb"<([0-9A-Fa-f]+)>|(\[)|(\])")

_MAX_RANGE = 65536
# 누적 매핑 총량 상한 — 개별 bfrange 만 제한하면 압축 1KB 짜리 CMap 으로
# 수 GB 매핑을 강제할 수 있다 (감수 2차 C1)
MAX_MAPPING_ENTRIES = 100_000


class ToUnicodeCMap:
    def __init__(self):
        # (코드 바이트 길이, 코드값) → 유니코드 문자열
        self.mapping: Dict[Tuple[int, int], str] = {}
        self.code_lengths: Set[int] = set()
        self.truncated = False

    def _mapping_full(self) -> bool:
        if len(self.mapping) >= MAX_MAPPING_ENTRIES:
            self.truncated = True
            return True
        return False

    def decode(self, data: bytes) -> str:
        # 긴 코드 우선 — 1/2바이트 혼재 CMap 에서 2바이트 코드가
        # 1바이트로 오매칭되는 것을 막는다 (감수 2차 M3)
        sizes = sorted((s for s in self.code_lengths if s > 0), reverse=True) or [1]
        min_size = sizes[-1]
        out = []
        i = 0
        n = len(data)
        while i < n:
            matched = False
            for size in sizes:
                if i + size > n:
                    continue
                code = int.from_bytes(data[i:i + size], "big")
                if (size, code) in self.mapping:
                    out.append(self.mapping[(size, code)])
                    i += size
                    matched = True
                    break
            if not matched:
                # 최소 길이만 전진 — 최대 길이만큼 건너뛰면 뒤 문자를 삼킨다 (감수 2차 M2)
                out.append("�")
                i += max(min(min_size, n - i), 1)
        return "".join(out)

    def _parse_bfrange_block(self, block: bytes) -> None:
        tokens = []
        for m in _TOKEN_RE.finditer(block):
            if m.group(1) is not None:
                tokens.append(m.group(1))
            elif m.group(2):
                tokens.append(b"[")
            else:
                tokens.append(b"]")
        i = 0
        n = len(tokens)
        while i < n - 2:
            lo_tok, hi_tok = tokens[i], tokens[i + 1]
            if lo_tok in (b"[", b"]") or hi_tok in (b"[", b"]"):
                i += 1
                continue
            length = max(len(lo_tok) // 2, 1)  # 홀수 한 자리 토큰이 길이 0 이 되면 decode 가 멈추지 못한다
            lo, hi = int(lo_tok, 16), int(hi_tok, 16)
            if hi < lo or hi - lo >= _MAX_RANGE:
                i += 3
                continue
            if tokens[i + 2] == b"]":  # 손상된 CMap — 목적지 없는 범위는 건너뜀
                i += 3
                continue
            self.code_lengths.add(length)
            if tokens[i + 2] == b"[":
                j = i + 3
                code = lo
                while j < n and tokens[j] != b"]":
                    if code <= hi and not self._mapping_full():
                        self.mapping[(length, code)] = _hex_to_text(tokens[j])
                    code += 1
                    j += 1
                i = j + 1
            else:
                base = int(tokens[i + 2], 16)
                digits = len(tokens[i + 2])
                for k in range(hi - lo + 1):
                    if self._mapping_full():
                        break
                    self.mapping[(length, lo + k)] = _int_to_text(base + k, digits)
                i += 3


def parse_tounicode(data: bytes, warnings=None) -> ToUnicodeCMap:
    cmap = ToUnicodeCMap()
    for block in _CODESPACE_RE.findall(data):
        for hex_tok in _HEX_RE.findall(block):
            cmap.code_lengths.add(max(len(hex_tok) // 2, 1))
    for block in _BF_CHAR_RE.findall(data):
        toks = _HEX_RE.findall(block)
        for i in range(0, len(toks) - 1, 2):
            if cmap._mapping_full():
                break
            src, dst = toks[i], toks[i + 1]
            length = max(len(src) // 2, 1)
            cmap.code_lengths.add(length)
            cmap.mapping[(length, int(src, 16))] = _hex_to_text(dst)
    for block in _BF_RANGE_RE.findall(data):
        try:
            cmap._parse_bfrange_block(block)
        except (ValueError, OverflowError):
            continue  # 손상된 블록 하나가 문서 전체를 막으면 안 된다
    if cmap.truncated and warnings is not None:
        warnings.append(
            f"WARN: ToUnicode CMap 매핑 수가 한도({MAX_MAPPING_ENTRIES})를 초과 — 일부만 사용"
        )
    if not cmap.code_lengths:
        cmap.code_lengths.add(1)
    return cmap


def _hex_to_text(hex_tok: bytes) -> str:
    """<0041> 형태의 UTF-16BE 16진 문자열을 파이썬 str 로 변환."""
    if len(hex_tok) % 2:
        hex_tok += b"0"
    raw = bytes.fromhex(hex_tok.decode("ascii"))
    return raw.decode("utf-16-be", errors="replace")


def _int_to_text(value: int, hex_digits: int) -> str:
    width = max(hex_digits, 4)
    if width % 4:
        width += 4 - (width % 4)
    try:
        raw = value.to_bytes(width // 2, "big")
    except OverflowError:
        return ""
    return raw.decode("utf-16-be", errors="replace")
