"""PPT text atoms, explicit formatting and hyperlink ranges.

Offsets and run lengths in [MS-PPT] text records count UTF-16 code units.
Paragraph levels are retained separately because the common Paragraph model
has no list-level field; they are not misrepresented as heading levels.
"""
import heapq
import re
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..model.document import Paragraph, TextRun
from .officeart import Record, walk_records

MAX_TEXT_UNITS = 8 * 1024 * 1024
MAX_TEXT_RUNS = 100000
MAX_TEXT_FRAGMENTS = 100000
MAX_OUTPUT_RUN_CHARS = 65536
MAX_OUTPUT_CHARS = 8 * 1024 * 1024


@dataclass
class TextBlock:
    text: str = ''
    text_type: int = 1
    style: bytes = b''
    records: List[Record] = field(default_factory=list)
    paragraph_levels: List[Tuple[int, int, int]] = field(default_factory=list)
    character_runs: list = field(default_factory=list)
    paragraph_bullets: list = field(default_factory=list)
    character_fonts: list = field(default_factory=list)
    character_symbol_fonts: list = field(default_factory=list)
    paragraph_fonts: list = field(default_factory=list)


def _warn(errors, message):
    if errors is not None and len(errors) < 1000:
        warning = 'WARN: PPT text ' + message
        if warning not in errors:
            errors.append(warning)


class _Cursor:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read(self, fmt):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise ValueError('truncated style')
        value = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return value[0] if len(value) == 1 else value

    def skip(self, size):
        if size > len(self.data) - self.pos:
            raise ValueError('truncated style property')
        self.pos += size


def _paragraph_properties(cursor, mask, font_ids=None):
    # TextPFException fields are serialized by schema order, not bit order.
    flags = cursor.read('<H') if mask & 0xF else 0
    bullet_char = cursor.read('<H') if mask & 0x80 else 0x2022
    font_id = cursor.read('<H') if mask & 0x10 else None
    if font_ids is not None:
        font_ids.append(font_id)
    for flag, size in ((0x40, 2), (0x20, 4),
                       (0x800, 2), (0x1000, 2), (0x2000, 2), (0x4000, 2),
                       (0x100, 2), (0x400, 2), (0x8000, 2)):
        if mask & flag:
            cursor.skip(size)
    if mask & 0x100000:
        count = cursor.read('<H')
        if count > 4096:
            raise ValueError('style tab count limit exceeded')
        cursor.skip(count * 4)
    if mask & 0x10000:
        cursor.skip(2)
    if mask & 0xE0000:
        cursor.skip(2)  # three wrap flags share a single value
    if mask & 0x200000:
        cursor.skip(2)
    if mask & ~0x3FFDFF:
        raise ValueError('unsupported paragraph style mask')
    if 0xD800 <= bullet_char <= 0xDFFF:
        bullet_char = 0xFFFD
    return chr(bullet_char) if mask & 1 and flags & 1 and bullet_char else ''


def _character_properties(cursor, mask, font_ids=None, symbol_ids=None):
    if mask & ~0xEFFFFF:
        raise ValueError('unsupported character style mask')
    flags = cursor.read('<H') if mask & 0xFFFF else 0
    font_id = None
    symbol_id = None
    for bit in (0x10000, 0x200000, 0x400000, 0x800000):
        if mask & bit:
            value = cursor.read('<H')
            if bit == 0x10000:
                font_id = value
            elif bit == 0x800000:
                symbol_id = value
    if font_ids is not None:
        font_ids.append(font_id)
    if symbol_ids is not None:
        symbol_ids.append(symbol_id)
    size = cursor.read('<H') if mask & 0x20000 else 10
    if mask & 0x40000:
        cursor.skip(4)
    if mask & 0x80000:
        cursor.skip(2)
    return (bool(flags & 1), bool(flags & 2), bool(flags & 4), float(size))


def _parse_style(block, errors):
    if not block.style:
        return
    cursor = _Cursor(block.style)
    units = len(block.text.encode('utf-16le')) // 2
    try:
        end = 0
        while end <= units:
            if len(block.paragraph_levels) >= MAX_TEXT_RUNS:
                raise ValueError('style run count limit exceeded')
            count, level, mask = cursor.read('<IHI')
            if not count:
                raise ValueError('style run has zero length')
            bullet = _paragraph_properties(cursor, mask, block.paragraph_fonts)
            block.paragraph_bullets.append((end, end + count, bullet))
            block.paragraph_levels.append((end, end + count, level))
            end += count
        end = 0
        while end <= units and cursor.pos < len(cursor.data):
            if len(block.character_runs) >= MAX_TEXT_RUNS:
                raise ValueError('style run count limit exceeded')
            count, mask = cursor.read('<II')
            if not count:
                raise ValueError('style run has zero length')
            props = _character_properties(cursor, mask, block.character_fonts, block.character_symbol_fonts)
            block.character_runs.append((end, end + count, props))
            end += count
    except (ValueError, struct.error) as exc:
        # An unknown property's length prevents reading subsequent runs, but
        # completed earlier runs and the separate PF stream remain trustworthy.
        # Discard only metadata provisionally read for the failed run.
        block.character_fonts = block.character_fonts[:len(block.character_runs)]
        block.character_symbol_fonts = block.character_symbol_fonts[:len(block.character_runs)]
        block.paragraph_fonts = block.paragraph_fonts[:len(block.paragraph_levels)]
        _warn(errors, str(exc))


def text_blocks(records, errors=None) -> List[TextBlock]:
    """Read sibling TextHeader/Text atoms, never treating CString as slide text."""
    blocks = []
    current = None
    total = 0
    for record in records:
        kind = record.header.rec_type
        if kind in (3999, 1011):
            if current is not None:
                _parse_style(current, errors)
                blocks.append(current)
            current = None
            if kind == 3999:
                if len(record.data) < 4:
                    _warn(errors, 'truncated TextHeaderAtom')
                else:
                    current = TextBlock(text_type=struct.unpack_from('<I', record.data)[0])
            continue
        if kind in (4000, 4008):
            if current is None:
                current = TextBlock()
            total += len(record.data)
            if total > MAX_TEXT_UNITS * 2:
                _warn(errors, 'text byte limit exceeded')
                break
            codec = 'utf-16le' if kind == 4000 else 'latin1'
            # TextBytesAtom stores the low byte of each Unicode code unit.
            current.text += bytes(record.data).decode(codec, errors='replace')
        if current is not None:
            current.records.append(record)
            if kind == 4001:
                current.style = bytes(record.data)
    if current is not None:
        _parse_style(current, errors)
        blocks.append(current)
    return blocks


def read_hyperlinks(document_records, slide_ids=None) -> Dict[int, str]:
    """Decode ExHyperlinkAtom ID and CString instance 1 (the address).

    Native internal addresses contain ``slideID,slideIndex,slideTitle``.
    Resolve slideID against the latest presentation order supplied by caller.
    """
    links = {}
    slide_ids = slide_ids or {}
    if not isinstance(slide_ids, dict):
        slide_ids = {slide_id: index for index, slide_id in enumerate(slide_ids, 1)}
    for record in walk_records(document_records):
        if record.header.rec_type != 4055:
            continue
        link_id = None
        target = ''
        location = ''
        for atom in record.children:
            if atom.header.rec_type == 4051 and len(atom.data) >= 4:
                link_id = struct.unpack_from('<I', atom.data)[0]
            elif atom.header.rec_type == 4026 and atom.header.rec_instance in (1, 3):
                value = bytes(atom.data[:65536]).decode('utf-16le', errors='replace').rstrip('\x00')
                if atom.header.rec_instance == 1:
                    target = value
                else:
                    location = value
        if link_id is None or not (target or location):
            continue
        # A location belongs to its external document when an address exists.
        # With no address it denotes this presentation's slide or bookmark.
        if target and location:
            links[link_id] = target.split('#', 1)[0] + '#' + location.lstrip('#')
            continue
        internal = location or target
        match = re.match(r'^([0-9]{1,10}),([0-9]{1,10}),', internal)
        if match:
            slide_id, index = map(int, match.groups())
            index = slide_ids.get(slide_id, index)
            if index > 0:
                target = '#PowerPoint Document#slide%d' % index
        if location and not match:
            target = '#' + location.lstrip('#')
        links[link_id] = target
    return links


def _interaction_target(record, hyperlinks):
    for atom in walk_records([record]):
        if atom.header.rec_type == 4083 and len(atom.data) >= 16:
            link_id = struct.unpack_from('<I', atom.data, 4)[0]
            # action=4 is a hyperlink. Ignore sound/OLE/macro interactions.
            if atom.data[8] == 4:
                return hyperlinks.get(link_id, '')
    return ''


def shape_hyperlink(records, hyperlinks) -> str:
    for record in records:
        if record.header.rec_type == 4082:
            target = _interaction_target(record, hyperlinks)
            if target:
                return target
    return ''


def _ranges(block, hyperlinks):
    pending = ''
    ranges = []
    for record in block.records:
        kind = record.header.rec_type
        if kind == 4082:
            pending = _interaction_target(record, hyperlinks)
        elif kind == 4063:
            if pending and len(record.data) >= 8:
                start, end = struct.unpack_from('<II', record.data)
                if start < end:
                    ranges.append((start, end, pending))
            pending = ''
    return ranges


# Symbol's legacy byte encoding and Unicode cmap share these glyphs.
# Font cmap observations are data, not a dependency on a font or font library.
_SYMBOL_UNICODE = {
    0x22: 0x2200, 0x24: 0x2203, 0x27: 0x220D, 0x2A: 0x2217, 0x2D: 0x2212, 0x40: 0x2245,
    0x41: 0x0391, 0x42: 0x0392, 0x43: 0x03A7, 0x44: 0x0394, 0x45: 0x0395, 0x46: 0x03A6,
    0x47: 0x0393, 0x48: 0x0397, 0x49: 0x0399, 0x4A: 0x03D1, 0x4B: 0x039A, 0x4C: 0x039B,
    0x4D: 0x039C, 0x4E: 0x039D, 0x4F: 0x039F, 0x50: 0x03A0, 0x51: 0x0398, 0x52: 0x03A1,
    0x53: 0x03A3, 0x54: 0x03A4, 0x55: 0x03A5, 0x56: 0x03C2, 0x57: 0x03A9, 0x58: 0x039E,
    0x59: 0x03A8, 0x5A: 0x0396, 0x5C: 0x2234, 0x5E: 0x22A5, 0x61: 0x03B1, 0x62: 0x03B2,
    0x63: 0x03C7, 0x64: 0x03B4, 0x65: 0x03B5, 0x66: 0x03C6, 0x67: 0x03B3, 0x68: 0x03B7,
    0x69: 0x03B9, 0x6A: 0x03D5, 0x6B: 0x03BA, 0x6C: 0x03BB, 0x6D: 0x03BC, 0x6E: 0x03BD,
    0x6F: 0x03BF, 0x70: 0x03C0, 0x71: 0x03B8, 0x72: 0x03C1, 0x73: 0x03C3, 0x74: 0x03C4,
    0x75: 0x03C5, 0x76: 0x03D6, 0x77: 0x03C9, 0x78: 0x03BE, 0x79: 0x03C8, 0x7A: 0x03B6,
    0x7E: 0x223C, 0xA0: 0x20AC, 0xA1: 0x03D2, 0xA2: 0x2032, 0xA3: 0x2264, 0xA4: 0x2044,
    0xA5: 0x221E, 0xA6: 0x0192, 0xA7: 0x2663, 0xA8: 0x2666, 0xA9: 0x2665, 0xAA: 0x2660,
    0xAB: 0x2194, 0xAC: 0x2190, 0xAD: 0x2191, 0xAE: 0x2192, 0xAF: 0x2193, 0xB2: 0x2033,
    0xB3: 0x2265, 0xB4: 0x00D7, 0xB5: 0x221D, 0xB6: 0x2202, 0xB7: 0x2022, 0xB8: 0x00F7,
    0xB9: 0x2260, 0xBA: 0x2261, 0xBB: 0x2248, 0xBC: 0x2026, 0xBD: 0x23D0, 0xBE: 0x23AF,
    0xBF: 0x21B5, 0xC0: 0x2135, 0xC1: 0x2111, 0xC2: 0x211C, 0xC3: 0x2118, 0xC4: 0x2297,
    0xC5: 0x2295, 0xC6: 0x2205, 0xC7: 0x2229, 0xC8: 0x222A, 0xC9: 0x2283, 0xCA: 0x2287,
    0xCB: 0x2284, 0xCC: 0x2282, 0xCD: 0x2286, 0xCE: 0x2208, 0xCF: 0x2209, 0xD0: 0x2220,
    0xD1: 0x2207, 0xD5: 0x220F, 0xD6: 0x221A, 0xD7: 0x22C5, 0xD8: 0x00AC, 0xD9: 0x2227,
    0xDA: 0x2228, 0xDB: 0x21D4, 0xDC: 0x21D0, 0xDD: 0x21D1, 0xDE: 0x21D2, 0xDF: 0x21D3,
    0xE0: 0x25CA, 0xE1: 0x3008, 0xE2: 0x00AE, 0xE3: 0x00A9, 0xE4: 0x2122, 0xE5: 0x2211,
    0xE6: 0x239B, 0xE7: 0x239C, 0xE8: 0x239D, 0xE9: 0x23A1, 0xEA: 0x23A2, 0xEB: 0x23A3,
    0xEC: 0x23A7, 0xED: 0x23A8, 0xEE: 0x23A9, 0xEF: 0x23AA, 0xF1: 0x3009, 0xF2: 0x222B,
    0xF3: 0x2320, 0xF4: 0x23AE, 0xF5: 0x2321, 0xF6: 0x239E, 0xF7: 0x239F, 0xF8: 0x23A0,
    0xF9: 0x23A4, 0xFA: 0x23A5, 0xFB: 0x23A6, 0xFC: 0x23AB, 0xFD: 0x23AC, 0xFE: 0x23AD,
}
_WINGDINGS_UNICODE = {
    0x6C: 0x25CF, 0x6E: 0x25A0, 0x75: 0x25C6, 0x76: 0x2756,
    0xA7: 0x25AA, 0xD8: 0x27A2, 0xFC: 0x2714, 0xFE: 0x2611,
}


def _symbol_text(text, font_name, private_only=False):
    mapping = {'symbol': _SYMBOL_UNICODE, 'wingdings': _WINGDINGS_UNICODE}.get(font_name.lower())
    if mapping is None:
        return text
    translation = {} if private_only else dict(mapping)
    translation.update((0xF000 + code, value) for code, value in mapping.items())
    # Unknown symbol bytes remain unchanged; never guess their meaning.
    return text.translate(translation)


def render_text(block, provenance, hyperlinks=None, default_hyperlink='',
                max_output_chars=MAX_OUTPUT_CHARS, errors=None, font_names=None) -> List[Paragraph]:
    """Return PPTX-compatible paragraphs and literal ``label <target>`` links."""
    font_names = font_names or {}
    units = len(block.text.encode('utf-16le')) // 2
    styles = block.character_runs
    links = _ranges(block, hyperlinks or {})
    # Keep only explicit style/link boundaries. Newline boundaries are streamed;
    # large blank atoms must not allocate one integer/set entry per character.
    boundaries = {0, units}
    for start, end, _props in styles + links:
        boundaries.update((max(0, min(start, units)), max(0, min(end, units))))
    if units == len(block.text):
        offsets = sorted(boundaries)
    else:
        offsets = []
        astrals = iter(re.finditer(r'[\U00010000-\U0010ffff]', block.text))
        astral = next(astrals, None)
        extra = 0
        for boundary in sorted(boundaries):
            while astral is not None and astral.start() + extra + 2 <= boundary:
                extra += 1
                astral = next(astrals, None)
            if astral is None or boundary != astral.start() + extra + 1:
                offsets.append(boundary - extra)

    def newline_offsets():
        for match in re.finditer(r'[\r\n]', block.text):
            yield match.start()
            yield match.end()

    def spans():
        previous = None
        for offset in heapq.merge(offsets, newline_offsets()):
            if previous is not None and previous != offset:
                yield previous, offset
            previous = offset

    paragraphs = []
    runs = []
    linked_paragraph = False
    style_index = 0
    bullet_index = 0
    link_index = 0
    link_events = sorted((start, order, end, target) for order, (start, end, target) in enumerate(links))
    active_links = []
    remaining = max(0, min(max_output_chars, MAX_OUTPUT_CHARS))
    output_runs = 0

    def append_run(text, props=(False, False, False, 10.0)):
        nonlocal remaining, output_runs
        accepted = min(len(text), remaining)
        if accepted < len(text):
            _warn(errors, 'output character limit exceeded')
        for offset in range(0, accepted, MAX_OUTPUT_RUN_CHARS):
            if output_runs >= MAX_TEXT_RUNS:
                _warn(errors, 'output run count limit exceeded')
                return
            chunk = text[offset:min(offset + MAX_OUTPUT_RUN_CHARS, accepted)]
            runs.append(TextRun(text=chunk, bold=props[0], italic=props[1], underline=props[2],
                                font_size_pt=props[3], provenance=provenance))
            remaining -= len(chunk)
            output_runs += 1

    def append_target(target, props):
        nonlocal remaining
        # Check the expansion before constructing a suffix or concatenating it.
        # Omit a target that cannot fit, retaining the original label text.
        length = len(target) + 3
        if length > remaining:
            _warn(errors, 'output character limit exceeded by hyperlink')
            return
        if runs and len(runs[-1].text) + length <= MAX_OUTPUT_RUN_CHARS:
            runs[-1].text += ' <%s>' % target
            remaining -= length
        else:
            needed = (length + MAX_OUTPUT_RUN_CHARS - 1) // MAX_OUTPUT_RUN_CHARS
            if output_runs + needed > MAX_TEXT_RUNS:
                _warn(errors, 'output run count limit exceeded by hyperlink')
                return
            append_run(' <%s>' % target, props)

    def finish():
        nonlocal runs, linked_paragraph
        if runs:
            if default_hyperlink and not linked_paragraph:
                last_run = runs[-1]
                append_target(default_hyperlink, (last_run.bold, last_run.italic, last_run.underline,
                                                  last_run.font_size_pt))
            paragraphs.append(Paragraph(runs=runs, heading_level=1 if block.text_type in (0, 6) else 0,
                                        provenance=provenance))
        runs = []
        linked_paragraph = False

    end = 0
    for fragment_index, (first, last) in enumerate(spans()):
        if fragment_index >= MAX_TEXT_FRAGMENTS:
            _warn(errors, 'fragment processing count limit exceeded')
            break
        if remaining <= 0 or output_runs >= MAX_TEXT_RUNS:
            _warn(errors, 'output character or run count limit exceeded')
            break
        start = end
        end += last - first
        if units != len(block.text):
            end += sum(1 for _match in re.finditer(r'[\U00010000-\U0010ffff]', block.text[first:last]))
        raw_limit = min(last, first + remaining)
        truncated = raw_limit < last
        if truncated:
            _warn(errors, 'output character limit exceeded')
        text = block.text[first:raw_limit]
        if text in ('\r', '\n'):
            finish()
            continue
        text = text.replace('\x00', '').replace('\x0b', '\n').replace('\x0c', '\n')
        if not runs:
            text = text.lstrip()
        if not text:
            if truncated:
                break
            continue
        while style_index < len(styles) and styles[style_index][1] <= start:
            style_index += 1
        props = (False, False, False, 10.0)
        if style_index < len(styles) and styles[style_index][0] <= start < styles[style_index][1]:
            props = styles[style_index][2]
        while link_index < len(link_events) and link_events[link_index][0] <= start:
            _begin, order, link_end, target = link_events[link_index]
            heapq.heappush(active_links, (order, link_end, target))
            link_index += 1
        while active_links and active_links[0][1] <= start:
            heapq.heappop(active_links)
        while bullet_index < len(block.paragraph_bullets) and block.paragraph_bullets[bullet_index][1] <= start:
            bullet_index += 1
        if not runs and bullet_index < len(block.paragraph_bullets):
            bullet_start, _bullet_end, bullet = block.paragraph_bullets[bullet_index]
            if bullet and bullet_start <= start:
                font_id = block.paragraph_fonts[bullet_index] if bullet_index < len(block.paragraph_fonts) else None
                bullet = _symbol_text(bullet, font_names.get(font_id, ''))
                append_run(bullet + ' ')
        # Append a link only on the final visible fragment of its range. A
        # terminal CR belongs to the link range in actual Office files.
        target_to_append = ''
        if active_links:
            _order, link_end, target = active_links[0]
            linked_paragraph = True
            next_char = block.text[last:last + 1]
            if not truncated and (end >= min(link_end, units) or next_char in ('\r', '\n')):
                target_to_append = target
        font_id = block.character_fonts[style_index] if style_index < len(block.character_fonts) else None
        text = _symbol_text(text, font_names.get(font_id, ''))
        symbol_id = block.character_symbol_fonts[style_index] if style_index < len(block.character_symbol_fonts) else None
        text = _symbol_text(text, font_names.get(symbol_id, ''), private_only=True)
        append_run(text, props)
        if target_to_append:
            append_target(target_to_append, props)
        if truncated:
            break
    finish()
    return paragraphs
