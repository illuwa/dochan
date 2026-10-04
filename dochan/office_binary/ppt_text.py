"""PPT text atoms, explicit formatting and hyperlink ranges.

Offsets and run lengths in [MS-PPT] text records count UTF-16 code units.
Paragraph levels are retained separately because the common Paragraph model
has no list-level field; they are not misrepresented as heading levels.
"""
import heapq
import re
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..model.document import Paragraph, TextRun
from .officeart import Record, walk_records
from .symbol_fonts import symbol_text as _symbol_text

MAX_TEXT_UNITS = 8 * 1024 * 1024
MAX_TEXT_RUNS = 100000
MAX_TEXT_FRAGMENTS = MAX_TEXT_UNITS
MAX_OUTPUT_RUN_CHARS = 65536
MAX_OUTPUT_CHARS = 8 * 1024 * 1024


@dataclass
class TextBlock:
    text: str = ''
    # Missing/truncated TextHeaderAtom has no evidence for body placeholder
    # inheritance. Use Other; an explicit header still supplies its own type.
    text_type: int = 4
    style: bytes = b''
    records: List[Record] = field(default_factory=list)
    paragraph_levels: List[Tuple[int, int, int]] = field(default_factory=list)
    character_runs: list = field(default_factory=list)
    paragraph_bullets: list = field(default_factory=list)
    character_fonts: list = field(default_factory=list)
    character_symbol_fonts: list = field(default_factory=list)
    paragraph_fonts: list = field(default_factory=list)
    paragraph_numbers: list = field(default_factory=list)
    character_masks: list = field(default_factory=list)


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
    baseline = cursor.read('<h') if mask & 0x80000 else 0
    return (bool(flags & mask & 1), bool(flags & mask & 2), bool(flags & mask & 4),
            float(size), baseline)


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
            block.character_masks.append(mask)
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


def apply_auto_numbers(blocks, data, errors=None):
    """Read StyleTextProp9Atom PF extensions in StyleTextProp run order.

    TextPFException9 mask bits 23/25/24 serialize blip reference, auto-number
    flag, then the scheme/start pair. Completed entries survive truncation.
    TextCFException9's pp10ext field (bit 20) occupies four bytes. It is
    separate from the base TextCFException, where that bit is reserved.
    Unknown trailing CF/SI properties stop parsing rather than guessing sizes.
    """
    cursor = _Cursor(data)
    try:
        for block in blocks:
            for _start, _end, _level in block.paragraph_levels:
                # StyleTextProp9Atom may contain extensions for only a prefix
                # of the base paragraph runs. A complete boundary is not a
                # truncated property; a partial trailing record still warns.
                if cursor.pos == len(data):
                    return
                if len(block.paragraph_numbers) >= MAX_TEXT_RUNS:
                    raise ValueError('auto-number run limit exceeded')
                mask = cursor.read('<I')
                if mask & ~0x03800000:
                    raise ValueError('unsupported auto-number paragraph mask')
                if mask & 0x00800000:
                    cursor.skip(2)
                enabled = cursor.read('<H') if mask & 0x02000000 else 0
                scheme, start = cursor.read('<Hh') if mask & 0x01000000 else (3, 1)
                block.paragraph_numbers.append((scheme, start) if enabled else None)
                cf_mask = cursor.read('<I')
                if cf_mask & ~0x100000:
                    raise ValueError('unsupported auto-number CF/SI extension')
                if cf_mask & 0x100000:
                    cursor.skip(4)
                si_mask = cursor.read('<I')
                if si_mask & ~0x40:
                    raise ValueError('unsupported auto-number CF/SI extension')
                if si_mask & 0x40:
                    cursor.skip(2)  # TextSIException.bidi
    except (ValueError, struct.error) as exc:
        _warn(errors, str(exc))


_NUMBER_SCHEMES = (
    'alphaLcPeriod', 'alphaUcPeriod', 'arabicParenR', 'arabicPeriod',
    'romanLcParenBoth', 'romanLcParenR', 'romanLcPeriod', 'romanUcPeriod',
    'alphaLcParenBoth', 'alphaLcParenR', 'alphaUcParenBoth', 'alphaUcParenR',
    'arabicParenBoth', 'arabicPlain', 'romanUcParenBoth', 'romanUcParenR',
)


def read_hyperlinks(document_records, slide_ids=None, labels=None) -> Dict[int, str]:
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
        display_name = ''
        for atom in record.children:
            if atom.header.rec_type == 4051 and len(atom.data) >= 4:
                link_id = struct.unpack_from('<I', atom.data)[0]
            elif atom.header.rec_type == 4026 and atom.header.rec_instance in (0, 1, 3):
                value = bytes(atom.data[:65536]).decode('utf-16le', errors='replace').rstrip('\x00')
                if atom.header.rec_instance == 0:
                    display_name = value
                elif atom.header.rec_instance == 1:
                    target = value
                else:
                    location = value
        if link_id is None:
            continue
        if labels is not None and display_name:
            labels[link_id] = display_name
        if not (target or location):
            # Older producers can save only the default slide display name.
            # Resolve a bounded, exact name, never arbitrary display text.
            match = re.fullmatch(r'Slide ([0-9]{1,10})', display_name)
            if match and 1 <= int(match.group(1)) <= len(slide_ids):
                links[link_id] = '#PowerPoint Document#slide%d' % int(match.group(1))
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


def _interaction_target(record, hyperlinks, slide_index=0, slide_count=0):
    for atom in walk_records([record]):
        if atom.header.rec_type == 4083 and len(atom.data) >= 16:
            link_id = struct.unpack_from('<I', atom.data, 4)[0]
            # action=4 is a hyperlink. Ignore sound/OLE/macro interactions.
            if atom.data[8] == 4:
                return hyperlinks.get(link_id, '')
            if atom.data[8] == 3:
                # InteractiveInfoAtom jump: next, previous, first, last.
                target = {1: slide_index + 1, 2: slide_index - 1,
                          3: 1, 4: slide_count}.get(atom.data[10], 0)
                if slide_index and 1 <= target <= slide_count:
                    return '#PowerPoint Document#slide%d' % target
    return ''


def shape_hyperlink(records, hyperlinks, slide_index=0, slide_count=0) -> str:
    for record in records:
        if record.header.rec_type == 4082:
            target = _interaction_target(record, hyperlinks, slide_index, slide_count)
            if target:
                return target
    return ''


def _ranges(block, hyperlinks, slide_index=0, slide_count=0):
    pending = ''
    ranges = []
    for record in block.records:
        kind = record.header.rec_type
        if kind == 4082:
            pending = _interaction_target(record, hyperlinks, slide_index, slide_count)
        elif kind == 4063:
            if pending and len(record.data) >= 8:
                start, end = struct.unpack_from('<II', record.data)
                if start < end:
                    ranges.append((start, end, pending))
            pending = ''
    return ranges



def render_text(block, provenance, hyperlinks=None, default_hyperlink='',
                max_output_chars=MAX_OUTPUT_CHARS, errors=None, font_names=None,
                fragment_budget=None, slide_index=0, slide_count=0,
                default_styles=None) -> List[Paragraph]:
    """Return PPTX-compatible paragraphs and literal ``label <target>`` links."""
    # ppt_styles uses this module's binary readers; defer the import once per
    # call rather than importing for every styled fragment in the text loop.
    from .ppt_styles import style_for

    font_names = font_names or {}
    if fragment_budget is None:
        fragment_budget = [MAX_TEXT_FRAGMENTS]
    units = len(block.text.encode('utf-16le')) // 2
    styles = block.character_runs
    links = _ranges(block, hyperlinks or {}, slide_index, slide_count)
    # Keep only explicit style/link boundaries. Newline boundaries are streamed;
    # large blank atoms must not allocate one integer/set entry per character.
    boundaries = {0, units}
    for start, end, _props in styles + links:
        boundaries.update((max(0, min(start, units)), max(0, min(end, units))))
    if default_styles:
        for start, end, _level in block.paragraph_levels:
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
    level_index = 0
    bullet_index = 0
    link_index = 0
    link_events = sorted((start, order, end, target) for order, (start, end, target) in enumerate(links))
    active_links = []
    remaining = max(0, min(max_output_chars, MAX_OUTPUT_CHARS))
    output_runs = 0
    number_counts = {}
    number_formatter = None

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
                                font_size_pt=props[3], superscript=len(props) > 4 and props[4] > 0,
                                subscript=len(props) > 4 and props[4] < 0, provenance=provenance))
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
    for first, last in spans():
        if fragment_budget[0] <= 0:
            _warn(errors, 'fragment processing count limit exceeded')
            break
        fragment_budget[0] -= 1
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
        props = [False, False, False, 10.0, 0]
        if default_styles:
            while level_index < len(block.paragraph_levels) and block.paragraph_levels[level_index][1] <= start:
                level_index += 1
            level = block.paragraph_levels[level_index][2] if level_index < len(block.paragraph_levels) else 0
            for prop, value in style_for(default_styles, block.text_type, level).items():
                props[prop] = value
        if style_index < len(styles) and styles[style_index][0] <= start < styles[style_index][1]:
            explicit = styles[style_index][2]
            mask = block.character_masks[style_index] if style_index < len(block.character_masks) else 0xEFFFFF
            for prop, bit in enumerate((1, 2, 4, 0x20000, 0x80000)):
                if mask & bit and prop < len(explicit):
                    props[prop] = explicit[prop]
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
                numbering = (block.paragraph_numbers[bullet_index]
                             if bullet_index < len(block.paragraph_numbers) else None)
                if numbering:
                    scheme, initial = numbering
                    level = block.paragraph_levels[bullet_index][2]
                    key = (level, scheme)
                    count = number_counts.get(key, max(1, initial) - 1) + 1
                    if scheme < len(_NUMBER_SCHEMES) and count <= 32767:
                        # Reuse the established PPTX spelling (letters, Roman
                        # numerals and punctuation), including its fallbacks.
                        if number_formatter is None:
                            from ..ooxml.pptx import PPTXReader
                            number_formatter = PPTXReader()
                        bullet = number_formatter._auto_number_marker(_NUMBER_SCHEMES[scheme], count)
                        number_counts[key] = count
                        for nested in list(number_counts):
                            if nested[0] > level:
                                del number_counts[nested]
                    else:
                        _warn(errors, 'unsupported auto-number scheme or count')
                prefix_start = len(runs)
                append_run(bullet + ' ')
                for prefix_run in runs[prefix_start:]:
                    prefix_run._ppt_generated_list_prefix = True
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
