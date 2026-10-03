"""ToUnicode CMap 파싱 — 문자 코드를 유니코드 문자열로 매핑.

한국어 PDF 는 대부분 Identity-H CID 폰트 + ToUnicode CMap 조합이므로
bfchar/bfrange 해석이 한글 텍스트 추출의 핵심이다.
"""
import re
import base64
import bisect
import heapq
import zlib
from functools import lru_cache
from typing import Dict, Set, Tuple

_TO_UNICODE_BLOCK_TOKEN = re.compile(rb"(begin|end)(codespacerange|bfchar|bfrange)")
_HEX_RE = re.compile(rb"<([0-9A-Fa-f]+)>")
_TOKEN_RE = re.compile(rb"<([0-9A-Fa-f]+)>|(\[)|(\])")

MAX_ENCODING_BYTES = 4 * 1024 * 1024
MAX_TOUNICODE_BYTES = 16 * 1024 * 1024
MAX_ENCODING_RANGES = 100_000
MAX_CODESPACE_RANGES = 100
MAX_CID_SPAN = 0x10ffff
_ENC_BLOCK_TOKEN = re.compile(rb"(begin|end)(codespacerange|cidrange|cidchar|notdefrange|notdefchar)")
_HEX_PAIR = re.compile(rb"<((?:[0-9A-Fa-f]{2}){1,4})>\s*<((?:[0-9A-Fa-f]{2}){1,4})>")
_CID_RANGE = re.compile(rb"<((?:[0-9A-Fa-f]{2}){1,4})>\s*<((?:[0-9A-Fa-f]{2}){1,4})>\s*([0-9]{1,5})(?![0-9])")
_CID_CHAR = re.compile(rb"<((?:[0-9A-Fa-f]{2}){1,4})>\s*([0-9]{1,5})(?![0-9])")


def _blocks(source, token_pattern, kinds):
    """Find blocks in one forward pass; an unclosed begin cannot rescan the tail."""
    active = None
    for token in token_pattern.finditer(source):
        operation, kind = token.groups()
        if operation == b"begin":
            active = (kind, token.end())
        elif active and active[0] == kind:
            if kind in kinds:
                yield kind, source[active[1]:token.start()]
            active = None


def _flatten_ranges(rows, constant=False):
    """Overlay intersecting rows in source order, in O(n log n) time."""
    events = []
    for index, (lo, hi, cid) in enumerate(rows):
        events.append((lo, 1, index))
        events.append((hi + 1, 0, index))
    events.sort()
    active = set()
    heap = []
    result = []
    pos = 0
    while pos < len(events):
        point = events[pos][0]
        while pos < len(events) and events[pos][0] == point:
            _, entering, index = events[pos]
            if entering:
                active.add(index)
                heapq.heappush(heap, -index)
            else:
                active.discard(index)
            pos += 1
        while heap and -heap[0] not in active:
            heapq.heappop(heap)
        if heap and pos < len(events) and events[pos][0] > point:
            index = -heap[0]
            lo, _hi, cid = rows[index]
            result.append((point, events[pos][0] - 1, cid if constant else cid + point - lo))
    return result


class EncodingCMap:
    """ISO 32000-1 §9.7.5: 바이트 코드 공간과 CID 범위."""

    def __init__(self, codespaces=(), cidranges=(), notdefranges=(), parent=None,
                 registry="", ordering="", supplement=0, wmode=0, warnings=None):
        self.codespaces = tuple(codespaces)
        self.cidranges = tuple(cidranges)
        self.notdefranges = tuple(notdefranges)
        self.parent = parent
        self.registry = registry or (parent.registry if parent else "")
        self.ordering = ordering or (parent.ordering if parent else "")
        self.supplement = supplement
        self.wmode = wmode
        self.warnings = warnings
        # A codespace is a byte-wise box, not an integer interval (§9.7.6.2).
        # usecmap 부모 사슬의 상자를 한 색인으로 합친다. 단계마다 다시 훑으면
        # 사슬 길이만큼 비용이 곱해진다. 합친 수도 MAX_CODESPACE_RANGES 로 묶는다.
        boxes = {(size, lo.to_bytes(size, "big"), hi.to_bytes(size, "big"))
                 for size, lo, hi in self.codespaces}
        if parent is not None:
            boxes |= parent._boxes
        if len(boxes) > MAX_CODESPACE_RANGES:
            boxes = set(sorted(boxes)[:MAX_CODESPACE_RANGES])
            if warnings is not None:
                message = "WARN: Encoding CMap 코드 공간 수 상한(100) 초과 — 일부 범위 생략"
                if message not in warnings:
                    warnings.append(message)
        self._boxes = frozenset(boxes)
        self._lengths = sorted({size for size, _lo, _hi in self._boxes})
        self._spaces = {length: {} for length in (1, 2, 3, 4)}
        for size, lo, hi in sorted(self._boxes):
            for byte in range(lo[0], hi[0] + 1):
                self._spaces[size].setdefault(byte, []).append((lo, hi))
        self._ranges = {}
        self._notdef = {}
        for source, target in ((self.cidranges, self._ranges),
                               (self.notdefranges, self._notdef)):
            for length in (1, 2, 3, 4):
                rows = _flatten_ranges([(lo, hi, cid) for size, lo, hi, cid in source
                                        if size == length], source is self.notdefranges)
                target[length] = ([row[0] for row in rows], rows)

    def _space(self, length, code):
        value = code.to_bytes(length, "big")
        for lo, hi in self._spaces[length].get(value[0], ()):
            if all(lower <= byte <= upper
                   for byte, lower, upper in zip(value, lo, hi)):
                return True
        return False

    def has_codespace(self):
        return bool(self._boxes)

    def _prefix(self, length, prefix_length, value):
        """Whether a partial code can still fall in a declared code space."""
        prefix = value.to_bytes(prefix_length, "big")
        for lo, hi in self._spaces[length].get(prefix[0], ()):
            if all(lower <= byte <= upper
                   for byte, lower, upper in zip(prefix, lo, hi)):
                return True
        return False

    def _codespace_lengths(self):
        return self._lengths

    def _invalid_length(self, raw, pos):
        remaining = len(raw) - pos
        lengths = self._codespace_lengths()
        if not lengths:
            return 1
        # §9.7.6.3: longest matching prefix, then shortest range on a tie.
        chosen = lengths[0]
        for prefix_length in range(1, min(3, remaining) + 1):
            value = int.from_bytes(raw[pos:pos + prefix_length], "big")
            matching = next((length for length in lengths if length > prefix_length
                             and self._prefix(length, prefix_length, value)), None)
            if matching is None:
                break
            chosen = matching
        return min(chosen, remaining)

    def _lookup(self, length, code, notdef=False):
        starts, rows = (self._notdef if notdef else self._ranges)[length]
        pos = bisect.bisect_right(starts, code) - 1
        if pos >= 0:
            lo, hi, cid = rows[pos]
            if code <= hi:
                return cid if notdef else cid + code - lo
        return self.parent._lookup(length, code, notdef) if self.parent else None

    def iter_codes(self, raw, warnings=None):
        warned = False
        pos = 0
        while pos < len(raw):
            match = None
            for size in (1, 2, 3, 4):
                if pos + size <= len(raw):
                    value = int.from_bytes(raw[pos:pos + size], "big")
                    if self._space(size, value):
                        match = (size, value)
                        break
            if match is None:
                if warnings is not None and not warned:
                    message = "WARN: Encoding CMap 코드가 코드 공간 밖이거나 잘림 — CID 0 사용"
                    if message not in warnings:
                        warnings.append(message)
                    warned = True
                size = self._invalid_length(raw, pos)
                yield raw[pos:pos + size], 0
                pos += size
                continue
            size, value = match
            cid = self._lookup(size, value)
            if cid is None:
                cid = self._lookup(size, value, True)
            if cid is None and warnings is not None and not warned:
                message = "WARN: Encoding CMap에 코드→CID 대응이 없음 — CID 0 사용"
                if message not in warnings:
                    warnings.append(message)
                warned = True
            yield raw[pos:pos + size], cid if cid is not None else 0
            pos += size


def parse_encoding_cmap(data, warnings=None, parents=None, _seen=None, parent_cmap=None):
    """내장 CMap의 유한한 범위만 읽는다. usecmap은 이름으로 상속한다."""
    if len(data) > MAX_ENCODING_BYTES:
        if warnings is not None:
            warnings.append("WARN: Encoding CMap 크기 한도 초과")
        return EncodingCMap()
    source = re.sub(rb"%[^\r\n]*", b"", data)
    parent = parent_cmap
    seen = set(_seen or ())
    names = re.findall(rb"/([A-Za-z0-9-]+)\s+usecmap\b", source)
    if names:
        name = names[-1].decode("ascii")
        if name not in seen and len(seen) < 8:
            seen.add(name)
            if parents and name in parents:
                parent = parse_encoding_cmap(parents[name], warnings, parents, seen)
            else:
                parent = predefined_cmap(name) or parent
        elif warnings is not None:
            warnings.append("WARN: Encoding CMap usecmap 순환 또는 깊이 한도")
    fields = {}
    for key in (b"Registry", b"Ordering"):
        match = re.search(rb"/" + key + rb"\s*\(([A-Za-z0-9-]{1,32})\)", source)
        fields[key] = match.group(1).decode("ascii") if match else ""
    supplement = re.search(rb"/Supplement\s+([0-9]{1,3})\b", source)
    mode = re.search(rb"/WMode\s+([01])\s+def\b", source)
    spaces, ranges, notdef = [], [], []
    count = 0
    truncated = False
    for kind, body in _blocks(source, _ENC_BLOCK_TOKEN,
                              (b"codespacerange", b"cidrange", b"cidchar",
                               b"notdefrange", b"notdefchar")):
        if kind == b"codespacerange":
            matches = _HEX_PAIR.finditer(body)
        elif kind in (b"cidrange", b"notdefrange"):
            matches = _CID_RANGE.finditer(body)
        else:
            matches = _CID_CHAR.finditer(body)
        for item in matches:
            if count >= MAX_ENCODING_RANGES:
                truncated = True
                break
            first = item.group(1)
            size = len(first) // 2
            lo = int(first, 16)
            if kind in (b"cidchar", b"notdefchar"):
                hi, cid = lo, int(item.group(2))
            else:
                second = item.group(2)
                if len(second) != len(first):
                    continue
                hi = int(second, 16)
                cid = int(item.group(3)) if kind != b"codespacerange" else 0
            if (hi < lo or (kind != b"codespacerange" and hi - lo > MAX_CID_SPAN)
                    or cid > 65535 or kind == b"cidrange" and cid + hi - lo > 65535):
                truncated = True
                continue
            row = (size, lo, hi, cid) if kind != b"codespacerange" else (size, lo, hi)
            if kind == b"codespacerange" and len(spaces) >= MAX_CODESPACE_RANGES:
                truncated = True
                continue
            (spaces if kind == b"codespacerange" else
             notdef if kind.startswith(b"notdef") else ranges).append(row)
            count += 1
        if truncated and count >= MAX_ENCODING_RANGES:
            break
    if truncated and warnings is not None:
        warnings.append("WARN: Encoding CMap 항목 또는 범위 한도 초과 — 일부만 사용")
    return EncodingCMap(spaces, ranges, notdef, parent, fields[b"Registry"],
                        fields[b"Ordering"], int(supplement.group(1)) if supplement else 0,
                        int(mode.group(1)) if mode else (parent.wmode if parent else 0), warnings)


@lru_cache(maxsize=32)
def predefined_cmap(name):
    from .predefined_cmap_data import TABLES

    if name in ("Identity-H", "Identity-V"):
        return EncodingCMap(((2, 0, 65535),), ((2, 0, 65535, 0),),
                            registry="Adobe", ordering="Identity",
                            wmode=int(name == "Identity-V"))
    payload = TABLES.get(name)
    if payload is None:
        return None
    meta, packed = payload
    parent = predefined_cmap(meta[3]) if meta[3] and meta[3] != name else None
    binary = zlib.decompress(base64.b85decode(packed))
    pos = 0

    def integer():
        nonlocal pos
        value, shift = 0, 0
        while True:
            byte = binary[pos]
            pos += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value // 2 if value % 2 == 0 else -(value // 2) - 1
            shift += 7

    tables = []
    for _kind in range(2):
        rows = []
        for size in (1, 2, 3, 4):
            count = integer()
            hi, next_cid = -1, 0
            for _ in range(count):
                lo = hi + 1 + integer()
                hi = lo + integer()
                cid = next_cid + integer()
                rows.append((size, lo, hi, cid))
                next_cid = cid + hi - lo + 1
        tables.append(rows)
    return EncodingCMap(meta[0], tables[0], tables[1], parent, meta[1], meta[2],
                        meta[4], meta[5])

_MAX_RANGE = 65536
# 누적 매핑 총량 상한 — 개별 bfrange 만 제한하면 압축 1KB 짜리 CMap 으로
# 수 GB 매핑을 강제할 수 있다 (감수 2차 C1)
MAX_MAPPING_ENTRIES = 100_000


def encoding_wmode(name: str = "", data: bytes = b"", dictionary_mode=None) -> int:
    """인코딩 CMap의 쓰기 모드. ISO 32000-1 §9.7.5 및 표 118.

    ToUnicode가 아닌 Encoding에 적용한다. 등록된 세로 CMap 이름과
    embedded CMap의 WMode/usecmap만 사용하여 임의 이름을 추측하지 않는다.
    """
    if dictionary_mode in (0, 1):
        return int(dictionary_mode)
    # 주석의 /WMode를 실제 선언으로 오인하지 않는다.
    source = re.sub(rb"%[^\r\n]*", b"", data[:16 * 1024 * 1024])
    modes = re.findall(rb"/WMode\s+([01])\s+def\b", source)
    if modes:
        return int(modes[-1])
    parents = re.findall(rb"/([A-Za-z0-9-]+)\s+usecmap\b", source)
    if parents:
        name = parents[-1].decode("ascii")
    if name == "Identity-V":
        return 1
    # ISO 32000-1 표 118에 있는 Adobe CJK 인코딩 계열.
    if name.endswith("-V") and (name.startswith(("UniJIS-", "UniKS-", "UniGB-", "UniCNS-"))
                               or name in {"90ms-RKSJ-V", "90msp-RKSJ-V", "90pv-RKSJ-V",
                                           "Add-RKSJ-V", "EUC-V", "Ext-RKSJ-V", "GB-EUC-V",
                                           "GBK-EUC-V", "GBKp-EUC-V", "GBK2K-V", "B5pc-V",
                                           "HKscs-B5-V", "ETen-B5-V", "ETenms-B5-V",
                                           "CNS-EUC-V", "KSC-EUC-V", "KSCms-UHC-V",
                                           "KSCms-UHC-HW-V", "KSCpc-EUC-V"}):
        return 1
    return 0


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
    if len(data) > MAX_TOUNICODE_BYTES:
        if warnings is not None:
            warnings.append("WARN: ToUnicode CMap 크기 한도 초과")
        cmap.code_lengths.add(1)
        return cmap
    blocks = {b"codespacerange": [], b"bfchar": [], b"bfrange": []}
    for kind, block in _blocks(data, _TO_UNICODE_BLOCK_TOKEN, blocks):
        blocks[kind].append(block)
    for kind in (b"codespacerange", b"bfchar", b"bfrange"):
        for block in blocks[kind]:
            if kind == b"codespacerange":
                for hex_tok in _HEX_RE.findall(block):
                    cmap.code_lengths.add(max(len(hex_tok) // 2, 1))
            elif kind == b"bfchar":
                toks = _HEX_RE.findall(block)
                for i in range(0, len(toks) - 1, 2):
                    if cmap._mapping_full():
                        break
                    src, dst = toks[i], toks[i + 1]
                    length = max(len(src) // 2, 1)
                    cmap.code_lengths.add(length)
                    cmap.mapping[(length, int(src, 16))] = _hex_to_text(dst)
            else:
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
