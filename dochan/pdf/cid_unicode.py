"""ISO 32000-1 §9.10.2: ToUnicode 없는 CID 글꼴의 제한된 복원."""
import base64
import json
import struct
import unicodedata
import zlib
from functools import lru_cache

from .cid_unicode_data import TABLES

MAX_FONT_BYTES = 8 * 1024 * 1024
MAX_CMAP_SUBTABLES = 8
MAX_CMAP_GROUPS = 4096
MAX_CMAP_SEGMENTS = 8192
MAX_CMAP_ENTRIES = 100_000


def _usable(value):
    return bool(value) and all(unicodedata.category(ch) not in ("Cc", "Co", "Cs", "Cn")
                               for ch in value)


@lru_cache(maxsize=5)
def _adobe_table(ordering):
    dense, extra = TABLES[ordering]
    numbers = zlib.decompress(base64.b85decode(dense))
    variants = json.loads(zlib.decompress(base64.b85decode(extra)))
    return numbers, variants


def adobe_cid(ordering, cid):
    if ordering not in TABLES or not 0 <= cid <= 65535:
        return ""
    numbers, variants = _adobe_table(ordering)
    value = variants.get(str(cid))
    if value is None and cid * 4 + 4 <= len(numbers):
        scalar = int.from_bytes(numbers[cid * 4:cid * 4 + 4], "big")
        value = chr(scalar) if scalar else ""
    return value if _usable(value) else ""


def _u16(data, offset):
    return struct.unpack_from(">H", data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def _reverse_format4(data, offset, limit, reverse):
    if offset + 16 > limit:
        return
    count = _u16(data, offset + 6) // 2
    if not 0 < count <= MAX_CMAP_SEGMENTS or offset + 16 + count * 8 > limit:
        return
    ends = offset + 14
    starts = ends + 2 * count + 2
    deltas = starts + 2 * count
    ranges = deltas + 2 * count
    scanned = 0
    for i in range(count):
        first, last = _u16(data, starts + 2 * i), _u16(data, ends + 2 * i)
        if last < first:
            continue
        delta, range_offset = _u16(data, deltas + 2 * i), _u16(data, ranges + 2 * i)
        for code in range(first, last + 1):
            scanned += 1
            if scanned > MAX_CMAP_ENTRIES:
                return
            if range_offset:
                pos = ranges + 2 * i + range_offset + 2 * (code - first)
                if pos + 2 > limit:
                    continue
                glyph = _u16(data, pos)
                glyph = (glyph + delta) & 0xffff if glyph else 0
            else:
                glyph = (code + delta) & 0xffff
            if glyph and _usable(chr(code)) and (glyph not in reverse or code < ord(reverse[glyph])):
                reverse[glyph] = chr(code)


def _reverse_format12(data, offset, limit, reverse):
    if offset + 16 > limit:
        return
    groups = _u32(data, offset + 12)
    if groups > MAX_CMAP_GROUPS or offset + 16 + 12 * groups > limit:
        return
    scanned = 0
    for i in range(groups):
        first, last, base = struct.unpack_from(">III", data, offset + 16 + 12 * i)
        if first > last or last > 0x10ffff or last - first > MAX_CMAP_ENTRIES:
            continue
        for code in range(first, last + 1):
            scanned += 1
            if scanned > MAX_CMAP_ENTRIES:
                return
            glyph = base + code - first
            if glyph <= 65535 and _usable(chr(code)) and (glyph not in reverse or code < ord(reverse[glyph])):
                reverse[glyph] = chr(code)


def reverse_truetype_cmap(data):
    """유니코드 cmap 형식 4/12의 GID→최소 유니코드 스칼라 매핑."""
    if not 12 <= len(data) <= MAX_FONT_BYTES:
        return {}
    tables = _u16(data, 4)
    if tables > 256 or 12 + tables * 16 > len(data):
        return {}
    cmap_offset = cmap_end = None
    for i in range(tables):
        pos = 12 + i * 16
        if data[pos:pos + 4] == b"cmap":
            start, length = _u32(data, pos + 8), _u32(data, pos + 12)
            if start <= len(data) and length <= len(data) - start:
                cmap_offset, cmap_end = start, start + length
            break
    if cmap_offset is None or cmap_offset + 4 > cmap_end:
        return {}
    records = _u16(data, cmap_offset + 2)
    if records > 256 or cmap_offset + 4 + records * 8 > cmap_end:
        return {}
    subtables = []
    for i in range(records):
        pos = cmap_offset + 4 + 8 * i
        platform, encoding, relative = struct.unpack_from(">HHI", data, pos)
        start = cmap_offset + relative
        if (platform == 0 or platform == 3 and encoding in (1, 10)) and start + 4 <= cmap_end:
            fmt = _u16(data, start)
            if fmt == 4:
                length = _u16(data, start + 2)
            elif fmt == 12 and start + 8 <= cmap_end:
                length = _u32(data, start + 4)
            else:
                continue
            if length >= 16 and length <= cmap_end - start:
                subtables.append((0 if fmt == 12 else 1, start, start + length, fmt))
    reverse = {}
    for _, start, end, fmt in sorted(subtables)[:MAX_CMAP_SUBTABLES]:
        if fmt == 4:
            _reverse_format4(data, start, end, reverse)
        else:
            _reverse_format12(data, start, end, reverse)
    return reverse


class CIDDecoder:
    def __init__(self, lookup, warnings, name):
        self.lookup = lookup
        self.warnings = warnings
        self.name = name
        self.warned = False

    def decode(self, data):
        output = []
        for i in range(0, len(data), 2):
            value = self.lookup(int.from_bytes(data[i:i + 2], "big")) if i + 2 <= len(data) else ""
            if not value and not self.warned:
                self.warnings.append(
                    "WARN: 폰트 %s: ToUnicode 없는 CID 폰트 — 일부 문자의 대응을 확인할 수 없음"
                    % self.name)
                self.warned = True
            output.append(value)
        return "".join(output)
