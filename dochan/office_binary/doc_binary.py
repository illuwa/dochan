"""Bounded Word 97 FIB/CLX/FKP/STSH decoding, using MS-DOC record layouts.

Offsets address the original streams. Text retains Word control characters and
UTF-16 code-unit positions so all PLCs share the same coordinate system.
"""
import bisect
import re
import struct
from dataclasses import dataclass
from typing import Iterator, Optional

MAX_CP = 16 * 1024 * 1024
MAX_RECORDS = 200000
# Limit work as well as output for overlapping fast-save piece ranges.
MAX_FKP_INTERSECTIONS = 2000000
MAX_PAPX_DEPTH = 32
MAX_PAPX_BYTES = 1024 * 1024
_PARAGRAPH_BREAK = re.compile(r'[\r\x07\x0c]')


def _u16(data, pos):
    return struct.unpack_from('<H', data, pos)[0]


def _u32(data, pos):
    return struct.unpack_from('<I', data, pos)[0]


_BOOL_SPRMS = {
    0x0835: 'bold', 0x0836: 'italic', 0x0837: 'strikeout',
    0x0800: 'deleted', 0x0801: 'inserted', 0x0855: 'special',
    0x2416: 'in_table', 0x2417: 'row_end',
    0x244b: 'inner_cell', 0x244c: 'inner_row',
}
_VALUE_SPRMS = {
    0x4600: 'istd', 0x6649: 'itap', 0x4863: 'author',
    0x4804: 'author', 0x6a03: 'pic_location', 0x4a30: 'char_style',
    0x6646: 'huge_papx', 0x646b: 'table_props',
}


def decode_grpprl(data: bytes) -> dict:
    """Decode known SPRMs, skipping unknown operands by their spra width."""
    props = {}
    pos = 0
    count = 0
    while pos + 2 <= len(data) and count < MAX_RECORDS:
        count += 1
        op = _u16(data, pos)
        pos += 2
        spra = op >> 13
        if spra == 6:
            if pos >= len(data):
                break
            if op in (0xd608, 0xd606):
                if pos + 2 > len(data):
                    break
                size = max(0, _u16(data, pos) - 1)
                pos += 2
            else:
                size = data[pos]
                pos += 1
                if op == 0xc615 and size == 255:
                    # MS-DOC PChgTabsOperand: cb=255 is a sentinel, not
                    # a length. Each deleted tab has position and tolerance;
                    # each added tab has position and one TBD byte.
                    if pos >= len(data):
                        break
                    added_at = pos + 1 + data[pos] * 4
                    if added_at >= len(data):
                        break
                    size = 2 + data[pos] * 4 + data[added_at] * 3
        else:
            size = (1, 1, 2, 4, 2, 2, 0, 3)[spra]
        if pos + size > len(data):
            break
        operand = data[pos:pos + size]
        pos += size
        if not operand:
            continue
        value = int.from_bytes(operand, 'little')
        if op in _BOOL_SPRMS:
            props[_BOOL_SPRMS[op]] = value if value in (128, 129) else bool(value)
        elif op in _VALUE_SPRMS:
            props[_VALUE_SPRMS[op]] = value
        elif op == 0x2a3e:
            props['underline'] = value != 0
        elif op == 0x2a48:
            # sprmCIss: 0=normal, 1=superscript, 2=subscript.
            props['superscript'] = value == 1
            props['subscript'] = value == 2
        elif op in (0xd608, 0xd606):
            props['table_def'] = operand
        elif op == 0xd62b:
            props.setdefault('vert_merge', []).append(operand)
    return props


def _merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if key in _BOOL_SPRMS.values() and type(value) is int and value in (128, 129):
            if value == 129:
                result[key] = not bool(result.get(key, False))
        else:
            result[key] = value
    return result


@dataclass
class Piece:
    start: int
    end: int
    fc: int
    compressed: bool


@dataclass
class ParagraphRecord:
    start: int
    end: int
    text: str
    props: dict


class DocBinary:
    def __init__(self, word: bytes, table: bytes, data: bytes = b''):
        self.word = word
        self.table = table
        self._data_source = data
        self._data = None
        self.warnings = []
        self.text = ''
        self.pieces = []  # type: List[Piece]
        self.stories = {}  # type: Dict[str, Tuple[int, int]]
        self.styles = {}  # type: Dict[int, dict]
        self._pairs = []
        self._pap = []
        self._chp = []
        self._pap_starts = []
        self._chp_starts = []
        self._piece_starts = []
        self._has_piece_table = False
        self._char_paragraph = (0, 0, {})
        self.valid = False
        try:
            self._fib()
            self._clx()
            if any(end > len(self.text) for _, end in self.stories.values()):
                raise ValueError('story CP range extends beyond piece text')
            self._piece_starts = [piece.start for piece in self.pieces]
            self._read_styles()
            self._pap = self._fkps(13, True)
            self._chp = self._fkps(12, False)
            self._pap_starts = [r[0] for r in self._pap]
            self._chp_starts = [r[0] for r in self._chp]
            self.valid = self._has_piece_table
        except (ValueError, IndexError, struct.error) as exc:
            self.warnings.append('DOC binary structure: ' + str(exc))

    @property
    def data(self):
        """Load optional Data only when PAPX or image parsing needs it."""
        if self._data is None:
            source = self._data_source
            self._data = source() if callable(source) else source
        return self._data

    def _fib(self):
        if len(self.word) < 34 or _u16(self.word, 0) != 0xa5ec:
            raise ValueError('unsupported or truncated FIB')
        csw = _u16(self.word, 32)
        pos = 34 + csw * 2
        if pos + 2 > len(self.word):
            raise ValueError('truncated FibRgW')
        cslw = _u16(self.word, pos)
        pos += 2
        if cslw < 11 or pos + cslw * 4 + 2 > len(self.word):
            raise ValueError('truncated FibRgLw')
        start = 0
        for name, idx in [('main', 3), ('footnote', 4), ('header', 5),
                          ('annotation', 7), ('endnote', 8), ('textbox', 9),
                          ('header_textbox', 10)]:
            length = _u32(self.word, pos + idx * 4)
            if start + length > MAX_CP:
                raise ValueError('story character limit exceeded')
            self.stories[name] = (start, start + length)
            start += length
        pos += cslw * 4
        count = _u16(self.word, pos)
        pos += 2
        if count > 4096 or pos + count * 8 > len(self.word):
            raise ValueError('truncated FibRgFcLcb')
        self._pairs = [struct.unpack_from('<II', self.word, pos + i * 8) for i in range(count)]

    def blob(self, index: int) -> bytes:
        if index < 0 or index >= len(self._pairs):
            return b''
        offset, size = self._pairs[index]
        if offset + size > len(self.table):
            if size:
                warning = 'DOC table entry %d is outside stream' % index
                if warning not in self.warnings:
                    self.warnings.append(warning)
            return b''
        return self.table[offset:offset + size]

    def _clx(self):
        clx = self.blob(33)
        pos = 0
        while pos < len(clx):
            marker = clx[pos]
            pos += 1
            if marker == 1 and pos + 2 <= len(clx):
                size = _u16(clx, pos)
                pos += 2 + size
                continue
            if marker != 2 or pos + 4 > len(clx):
                break
            size = _u32(clx, pos)
            pos += 4
            if size < 4 or (size - 4) % 12 or pos + size > len(clx):
                raise ValueError('invalid PlcPcd')
            plc = clx[pos:pos + size]
            count = (size - 4) // 12
            if count > MAX_RECORDS:
                raise ValueError('piece count limit exceeded')
            texts = []
            last = 0
            for i in range(count):
                start, end = struct.unpack_from('<II', plc, i * 4)
                if start != last or end < start or end > MAX_CP:
                    raise ValueError('invalid piece CP range')
                fc = _u32(plc, (count + 1) * 4 + i * 8 + 2)
                compressed = bool(fc & 0x40000000)
                fc &= 0x3fffffff
                if compressed:
                    fc //= 2
                size_bytes = (end - start) * (1 if compressed else 2)
                if fc + size_bytes > len(self.word):
                    raise ValueError('piece outside WordDocument')
                raw = self.word[fc:fc + size_bytes]
                if compressed:
                    text = raw.decode('cp1252', errors='replace')
                else:
                    # Python combines surrogate pairs; Word PLC coordinates count
                    # each UTF-16 code unit, so retain both until output rendering.
                    text = ''.join(chr(v[0]) for v in struct.iter_unpack('<H', raw))
                texts.append(text)
                self.pieces.append(Piece(start, end, fc, compressed))
                last = end
            self.text = ''.join(texts)
            self._has_piece_table = True
            return

    def cp_to_fc(self, cp: int) -> Optional[int]:
        index = bisect.bisect_right(self._piece_starts, cp) - 1
        if index >= 0:
            p = self.pieces[index]
            if p.start <= cp < p.end:
                return p.fc + (cp - p.start) * (1 if p.compressed else 2)
        if self.pieces and cp == self.pieces[-1].end:
            p = self.pieces[-1]
            return p.fc + (p.end - p.start) * (1 if p.compressed else 2)
        return None

    def fc_to_cp(self, fc: int, piece: Optional[Piece] = None) -> Optional[int]:
        # A physical FC can belong to several fast-save pieces. The caller
        # can supply the intersected piece to retain its logical CP identity.
        if piece is not None:
            step = 1 if piece.compressed else 2
            if piece.fc <= fc <= piece.fc + (piece.end - piece.start) * step:
                return piece.start + (fc - piece.fc) // step
            return None
        for p in self.pieces:
            step = 1 if p.compressed else 2
            if p.fc <= fc < p.fc + (p.end - p.start) * step:
                return p.start + (fc - p.fc) // step
        for p in reversed(self.pieces):
            if fc == p.fc + (p.end - p.start) * (1 if p.compressed else 2):
                return p.end
        return None

    def _expand_papx(self, props, path=(), budget=None):
        if budget is None:
            budget = [MAX_PAPX_BYTES]
        result = {key: value for key, value in props.items()
                  if key not in ('huge_papx', 'table_props')}
        for key, offset in props.items():
            if key not in ('huge_papx', 'table_props'):
                continue
            if offset in path:
                self.warnings.append('DOC huge PAPX reference cycle')
                continue
            if len(path) >= MAX_PAPX_DEPTH:
                self.warnings.append('DOC huge PAPX reference depth limit exceeded')
                continue
            data = self.data
            length = _u16(data, offset) if offset + 2 <= len(data) else -1
            if length < 0 or offset + 2 + length > len(data):
                self.warnings.append('DOC huge PAPX is outside Data stream')
                continue
            budget[0] -= length + 2
            if budget[0] < 0:
                self.warnings.append('DOC huge PAPX byte limit exceeded')
                break
            nested = decode_grpprl(data[offset + 2:offset + 2 + length])
            result.update(self._expand_papx(nested, path + (offset,), budget))
        return result

    def _fkps(self, index, paragraph):
        plc = self.blob(index)
        if not plc or len(plc) < 4 or (len(plc) - 4) % 8:
            return []
        count = (len(plc) - 4) // 8
        if count > MAX_RECORDS:
            self.warnings.append('DOC FKP page limit exceeded')
            return []
        records = []
        seen = set()
        intersections = 0
        # FC ordering differs from logical CP ordering after fast saves.
        # Prefix maximum ends preserve overlapping pieces while bisect skips
        # all pieces strictly before or after each FKP interval.
        pieces = sorted(self.pieces, key=lambda piece: piece.fc)
        starts = [piece.fc for piece in pieces]
        max_ends = []
        maximum = 0
        for piece in pieces:
            maximum = max(maximum, piece.fc + (piece.end - piece.start)
                          * (1 if piece.compressed else 2))
            max_ends.append(maximum)
        for i in range(count):
            pn = _u32(plc, 4 * (count + 1) + i * 4) & 0x3fffff
            if pn in seen:
                continue
            seen.add(pn)
            page = self.word[pn * 512:(pn + 1) * 512]
            if len(page) != 512:
                self.warnings.append('DOC FKP page outside stream')
                continue
            crun = page[511]
            width = 13 if paragraph else 1
            base = (crun + 1) * 4
            if base + crun * width > 511:
                self.warnings.append('DOC FKP run table is invalid')
                continue
            for j in range(crun):
                fc_start, fc_end = struct.unpack_from('<II', page, j * 4)
                at = page[base + j * width] * 2
                props = {}
                if at:
                    size = page[at]
                    at += 1
                    if paragraph:
                        if size == 0 and at < 511:
                            size = page[at] * 2
                            at += 1
                        else:
                            size = size * 2 - 1
                    if size < 0 or at + size > 511:
                        self.warnings.append('DOC FKP property payload is invalid')
                        continue
                    payload = page[at:at + size]
                    if paragraph:
                        if len(payload) < 2:
                            continue
                        props['istd'] = _u16(payload, 0)
                        props.update(decode_grpprl(payload[2:]))
                        props = self._expand_papx(props)
                    else:
                        props = decode_grpprl(payload)
                # FKP FC intervals may cross pieces and fast-save ordering.
                lo = bisect.bisect_right(max_ends, fc_start)
                hi = bisect.bisect_left(starts, fc_end)
                for piece in pieces[lo:hi]:
                    intersections += 1
                    if intersections > MAX_FKP_INTERSECTIONS:
                        self.warnings.append('DOC FKP piece intersection limit exceeded')
                        return sorted(records, key=lambda r: r[0])
                    step = 1 if piece.compressed else 2
                    a = max(fc_start, piece.fc)
                    b = min(fc_end, piece.fc + (piece.end - piece.start) * step)
                    if a < b:
                        records.append((self.fc_to_cp(a, piece),
                                        self.fc_to_cp(b, piece), props))
                if len(records) > MAX_RECORDS:
                    self.warnings.append('DOC FKP run limit exceeded')
                    return sorted(records[:MAX_RECORDS], key=lambda r: r[0])
        return sorted(records, key=lambda r: r[0])

    def _read_styles(self):
        data = self.blob(1)
        if len(data) < 6:
            return
        cb = _u16(data, 0)
        count, base_size = struct.unpack_from('<HH', data, 2)
        if cb < 4 or base_size < 6 or count > 4096:
            self.warnings.append('DOC STSH header is invalid')
            return
        pos = cb + 2
        raw_styles = {}
        for index in range(count):
            if pos + 2 > len(data):
                break
            size = _u16(data, pos)
            pos += 2
            raw = data[pos:pos + size]
            pos += size
            if len(raw) != size or size < base_size + 2:
                continue
            flags = _u16(raw, 2)
            kind = flags & 15
            base = flags >> 4
            cupx = _u16(raw, 4) & 15
            cch = _u16(raw, base_size)
            name_end = base_size + 2 + cch * 2
            if name_end + 2 > len(raw):
                continue
            name = raw[base_size + 2:name_end].decode('utf-16-le', errors='replace')
            p = (name_end + 3) & ~1
            props = {}
            for u in range(cupx):
                if p + 2 > len(raw):
                    break
                length = _u16(raw, p)
                p += 2
                if p + length > len(raw):
                    break
                payload = raw[p:p + length]
                p += length + (length % 2)
                if kind == 1 and u == 0:
                    payload = payload[2:]
                if kind in (1, 2):
                    props.update(decode_grpprl(payload))
            level = index if 1 <= index <= 9 else 0
            match = re.match(r'heading\s*([1-9])$', name, re.IGNORECASE)
            if match:
                level = int(match.group(1))
            raw_styles[index] = {'name': name, 'base': base, 'props': props, 'heading_level': level}
        def resolve(index, path):
            if index in self.styles:
                return self.styles[index]
            entry = dict(raw_styles[index])
            base = entry['base']
            if base in raw_styles and base not in path and len(path) < 32:
                inherited = resolve(base, path + [index])
                entry['props'] = _merge(inherited['props'], entry['props'])
                if not entry['heading_level']:
                    entry['heading_level'] = inherited['heading_level']
            else:
                entry['props'] = _merge({}, entry['props'])
            self.styles[index] = entry
            return entry
        for index in raw_styles:
            resolve(index, [index])

    @staticmethod
    def _at(records, starts, cp):
        i = bisect.bisect_right(starts, cp) - 1
        if i >= 0 and records[i][0] <= cp < records[i][1]:
            return records[i][2]
        return {}

    def paragraph_props(self, cp):
        direct = self._at(self._pap, self._pap_starts, cp)
        istd = direct.get('istd', 0)
        style = self.styles.get(istd, {})
        props = _merge(style.get('props', {}), direct)
        props.setdefault('istd', istd)
        props['style_name'] = style.get('name', '')
        if style.get('heading_level'):
            props['heading_level'] = style['heading_level']
        return props

    def char_props(self, cp: int) -> dict:
        if not 0 <= cp < len(self.text):
            return {}
        start, end, paragraph = self._char_paragraph
        if not start <= cp < end:
            # Only the final paragraph mark owns PAPX. A fast-saved paragraph
            # may join pieces whose preceding physical PAPX runs disagree.
            # Cache the remaining interval for the renderer's sequential reads.
            mark = _PARAGRAPH_BREAK.search(self.text, cp)
            end = mark.end() if mark else len(self.text)
            paragraph = self.paragraph_props(end - 1)
            self._char_paragraph = (cp, end, paragraph)
        style = self.styles.get(paragraph.get('istd', 0), {})
        props = dict(style.get('props', {}))
        direct = self._at(self._chp, self._chp_starts, cp)
        char_style = self.styles.get(direct.get('char_style'), {})
        props = _merge(props, char_style.get('props', {}))
        return _merge(props, direct)

    def paragraphs(self, start: int, end: int) -> Iterator[ParagraphRecord]:
        start = max(0, start)
        end = min(end, len(self.text))
        pos = start
        for match in _PARAGRAPH_BREAK.finditer(self.text[start:end]):
            stop = start + match.end()
            # The paragraph mark carries PAPX in fast-saved documents.
            props = self.paragraph_props(stop - 1)
            props['deleted_mark'] = bool(self.char_props(stop - 1).get('deleted'))
            # A deleted paragraph mark joins its text to the next paragraph.
            # Table/cell boundaries are structural even when their adjacent
            # CR was deleted. Joining body text into a deleted table would
            # incorrectly give that live text the table's deletion semantics.
            if (props['deleted_mark'] and self.text[stop - 1] == '\r'
                    and not props.get('row_end') and not props.get('inner_row')
                    and not props.get('inner_cell')
                    and stop < end):
                next_mark = _PARAGRAPH_BREAK.search(self.text, stop, end)
                next_props = self.paragraph_props(next_mark.start() if next_mark else end - 1)
                depth = max(1, props.get('itap', 0)) if props.get('in_table') else 0
                next_depth = (max(1, next_props.get('itap', 0))
                              if next_props.get('in_table') else 0)
                if (depth == next_depth and not next_props.get('row_end')
                        and not next_props.get('inner_row')):
                    continue
            yield ParagraphRecord(pos, stop, self.text[pos:stop], props)
            pos = stop
        if pos < end:
            yield ParagraphRecord(pos, end, self.text[pos:end], self.paragraph_props(end - 1))

    def iter_char_runs(self, start: int, end: int):
        """Yield constant properties at CHPX and paragraph boundaries."""
        cp = max(0, start)
        end = min(end, len(self.text))
        while cp < end:
            props = self.char_props(cp)
            stop = min(end, self._char_paragraph[1])
            index = bisect.bisect_right(self._chp_starts, cp) - 1
            if index >= 0 and self._chp[index][1] > cp:
                stop = min(stop, self._chp[index][1])
            if index + 1 < len(self._chp_starts):
                stop = min(stop, self._chp_starts[index + 1])
            yield cp, stop, props
            cp = stop
