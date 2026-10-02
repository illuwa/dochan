"""MS-DOC field PLCs, bookmarks and secondary document stories.

The binary layer owns CP-to-byte translation.  All positions here remain in the
common CP space; PLC positions for a secondary story are relative to that story.
Only standard-library parsing and the existing document model are used.
"""
import bisect
from copy import copy
import heapq
import re
import struct
from dataclasses import dataclass
from typing import Dict, List

from ..model.document import TextRun
from ..model.header_footer import Comment, Footnote, HeaderFooter

_MAX_RECORDS = 100000
_MAX_FIELD_DEPTH = 64
_FIELDS = {'main': 16, 'header': 17, 'footnote': 18, 'annotation': 19,
           'endnote': 48, 'textbox': 57, 'header_textbox': 59}


def _plc(data, record_size):
    """Return bounded CPs and fixed-sized records; reject partial PLCs."""
    if not data:
        return [], []
    if len(data) < 4 or (len(data) - 4) % (4 + record_size):
        raise ValueError('invalid PLC length')
    count = (len(data) - 4) // (4 + record_size)
    if count > _MAX_RECORDS:
        raise ValueError('PLC record limit exceeded')
    cps = list(struct.unpack_from('<' + 'I' * (count + 1), data))
    if any(a > b for a, b in zip(cps, cps[1:])):
        raise ValueError('non-monotonic PLC positions')
    offset = 4 * (count + 1)
    records = [data[offset + i * record_size:offset + (i + 1) * record_size]
               for i in range(count)] if record_size else []
    return cps, records


def _strings(data, counted=True):
    """STTBF (Unicode or ANSI) and the uncounted GrpXstAtnOwners."""
    if not data:
        return []
    offset, extra, wide, count = 0, 0, True, _MAX_RECORDS
    if counted:
        if len(data) < 4:
            raise ValueError('truncated STTBF')
        wide = data[:2] == b'\xff\xff'
        offset = 2 if wide else 0
        count, extra = struct.unpack_from('<HH', data, offset)
        offset += 4
        if count > _MAX_RECORDS:
            raise ValueError('STTBF record limit exceeded')
    result = []
    for _ in range(count):
        if offset == len(data) and not counted:
            break
        size_bytes = 2 if wide else 1
        if offset + size_bytes > len(data):
            raise ValueError('truncated string length')
        length = int.from_bytes(data[offset:offset + size_bytes], 'little')
        offset += size_bytes
        if length == (0xffff if wide else 0xff):
            result.append('')
            continue
        byte_size = length * size_bytes
        if offset + byte_size + extra > len(data):
            raise ValueError('truncated string data')
        result.append(data[offset:offset + byte_size].decode(
            'utf-16-le' if wide else 'cp1252', errors='replace'))
        offset += byte_size + extra
    return result


@dataclass
class Field:
    start: int
    separator: int
    end: int
    instruction: str
    target: str = ''


class Stories:
    """CP annotations for the main renderer and model objects for other stories.

    ``suffix(cp)`` preserves DOCX's visible `` <URL>`` contract. ``link(cp)`` is
    available to callers that need the target, but a renderer must not use both
    the suffix and ``TextRun.link`` (which would duplicate the Markdown link).
    """
    def __init__(self, binary, doc):
        self.binary, self.doc = binary, doc
        self.fields = []
        self._hidden = []
        self._hidden_starts = []
        self._instructions = []
        self._instruction_starts = []
        self._markers: Dict[int, List[TextRun]] = {}
        self._notes = []
        self._textboxes = {}
        self._textboxes_emitted = set()
        self.revision_authors = self._try_strings(51)
        for name, index in _FIELDS.items():
            if name in binary.stories:
                self._read_fields(name, index)
        self.fields.sort(key=lambda item: item.start)
        self._merge_hidden()
        self._index_links()
        self._read_textboxes()
        self._read_bookmarks()
        self._read_notes()
        # Field delimiters are hidden themselves, but a top-level field can
        # generate a form value at its start or a URL at its end. Suppress
        # those additions only inside another field's instruction interval.
        self._markers = {cp: runs for cp, runs in self._markers.items()
                         if not self.in_instruction(cp)}
        self._event_cps = sorted(set(self._markers) | set(self._suffixes))

    def event_positions(self, start, end):
        begin = bisect.bisect_left(self._event_cps, start)
        stop = bisect.bisect_left(self._event_cps, end)
        return self._event_cps[begin:stop]

    def _warn(self, context, exc):
        warning = 'WARN: DOC %s: %s' % (context, exc)
        if len(self.doc.errors) < 1000 and warning not in self.doc.errors:
            self.doc.errors.append(warning)

    def _try_strings(self, index, counted=True):
        try:
            return _strings(self.binary.blob(index), counted)
        except (ValueError, struct.error) as exc:
            self._warn('string table %s' % index, exc)
            return []

    def _read_fields(self, name, index):
        start, end = self.binary.stories[name]
        text = self.binary.text
        positions = []
        try:
            cps, records = _plc(self.binary.blob(index), 2)
            for cp, record in zip(cps, records):
                absolute = start + cp
                marker = record[0] & 0x1f
                if start <= absolute < end and marker in (19, 20, 21):
                    if ord(text[absolute]) == marker:
                        positions.append(absolute)
        except (ValueError, struct.error, IndexError) as exc:
            self._warn('field PLC %s' % name, exc)
        # Old/malformed producers can omit PlcFld. Controls still delimit the
        # cached result, but never interpret instructions as executable input.
        if not positions:
            for cp in range(start, min(end, len(text))):
                if text[cp] in '\x13\x14\x15':
                    positions.append(cp)
                    if len(positions) > _MAX_RECORDS:
                        break
        if len(positions) > _MAX_RECORDS:
            self._warn('fields', 'record limit exceeded')
            return
        stack = []
        for cp in positions:
            char = text[cp]
            if char == '\x13':
                if len(stack) >= _MAX_FIELD_DEPTH:
                    self._warn('fields', 'nesting limit exceeded')
                    return
                stack.append([cp, -1])
            elif char == '\x14' and stack:
                stack[-1][1] = cp
            elif char == '\x15' and stack:
                if len(self.fields) >= _MAX_RECORDS:
                    self._warn('fields', 'field count limit exceeded')
                    return
                begin, separator = stack.pop()
                instruction_end = separator if separator >= 0 else cp
                instruction = text[begin + 1:instruction_end]
                field = Field(begin, separator, cp, instruction,
                              self._hyperlink_target(instruction))
                self.fields.append(field)
                if separator < 0:
                    display = re.match(r'^\s*MACROBUTTON\s+\S+\s+(.*)', instruction, re.IGNORECASE | re.DOTALL)
                    if display:
                        value = display.group(1)
                        if hasattr(self.binary, 'display_range'):
                            value = self.binary.display_range(begin + 1 + display.start(1), cp)
                        self._markers.setdefault(begin, []).append(TextRun(value.strip()))
                    elif re.match(r'^\s*FORM(?:TEXT|CHECKBOX|DROPDOWN)\b', instruction, re.IGNORECASE):
                        value = self._form_value(begin, cp, instruction)
                        if value:
                            self._markers.setdefault(begin, []).append(TextRun(value))
                self._hidden.append((begin, instruction_end + 1))
                self._hidden.append((cp, cp + 1))
                self._instructions.append((begin + 1, instruction_end + 1))
        if stack:
            self._warn('fields', 'unterminated field; text retained')

    def _form_value(self, start, end, instruction):
        """Read FFData after its NilPICF; never follow a macro or external URL."""
        data = getattr(self.binary, 'data', b'')
        if not data or not hasattr(self.binary, 'char_props'):
            return ''
        marker = self.binary.text.find('\x01', start, end)
        if marker < 0:
            return ''
        props = self.binary.char_props(marker)
        offset = props.get('pic_location')
        if not props.get('special') or not isinstance(offset, int):
            return ''
        try:
            if offset < 0 or offset + 68 > len(data):
                raise ValueError('FFData PICF outside Data stream')
            size, header_size, mapping = struct.unpack_from('<IHH', data, offset)
            if header_size != 68 or mapping != 0 or size < 78 or size > 1024 * 1024 or offset + size > len(data):
                raise ValueError('invalid FFData PICF')
            raw = data[offset + header_size:offset + size]
            version, bits, _, _ = struct.unpack_from('<IHHH', raw)
            if version != 0xffffffff:
                raise ValueError('unsupported FFData version')
            kind, result = bits & 3, (bits >> 2) & 31
            expected = {'FORMTEXT': 0, 'FORMCHECKBOX': 1, 'FORMDROPDOWN': 2}
            if expected.get(instruction.strip().split()[0].upper()) != kind:
                raise ValueError('FFData type disagrees with field instruction')
            pos = 10

            def string():
                nonlocal pos
                if pos + 2 > len(raw):
                    raise ValueError('truncated FFData string')
                length = struct.unpack_from('<H', raw, pos)[0]
                pos += 2
                stop = pos + length * 2
                if stop + 2 > len(raw) or raw[stop:stop + 2] != b'\0\0':
                    raise ValueError('invalid FFData Xstz')
                value = raw[pos:stop].decode('utf-16-le', errors='replace')
                pos = stop + 2
                return value

            string()  # xstzName
            if kind == 0:
                default = string()
            else:
                if pos + 2 > len(raw):
                    raise ValueError('truncated FFData default')
                default = struct.unpack_from('<H', raw, pos)[0]
                pos += 2
            # Text format, help, status, entry macro and exit macro strings.
            # Macros are metadata only and are never evaluated.
            for _ in range(5):
                string()
            selected = default if result == 25 else result
            if kind == 0:
                return default
            if kind == 1:
                if selected not in (0, 1):
                    raise ValueError('invalid checkbox state')
                return '[x]' if selected else '[ ]'
            choices = _strings(raw[pos:])
            if not choices and selected == 0:
                return ''
            if not 0 <= selected < len(choices):
                raise ValueError('dropdown selection outside list')
            return choices[selected]
        except (ValueError, struct.error) as exc:
            self._warn('form field', exc)
            return ''

    @staticmethod
    def _hyperlink_target(instruction):
        if not re.match(r'^\s*HYPERLINK\b', instruction, re.IGNORECASE):
            return ''
        anchor = re.search(r'\\l\s+(?:"([^"]*)"|([^\s\\]+))', instruction, re.IGNORECASE)
        target = re.match(r'^\s*HYPERLINK\s+(?:"([^"]*)"|([^\s\\]+))', instruction, re.IGNORECASE)
        url = (target.group(1) or target.group(2) or '') if target else ''
        if anchor:
            url += '#' + (anchor.group(1) or anchor.group(2) or '')
        return url

    def _merge_hidden(self):
        def merge(intervals):
            merged = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            return merged
        self._hidden = merge(self._hidden)
        self._hidden_starts = [start for start, _ in self._hidden]
        self._instructions = merge(self._instructions)
        self._instruction_starts = [start for start, _ in self._instructions]

    def in_instruction(self, cp):
        index = bisect.bisect_right(self._instruction_starts, cp) - 1
        return index >= 0 and cp < self._instructions[index][1]

    def hidden(self, cp):
        if 0 <= cp < len(self.binary.text) and self.binary.text[cp] in '\x13\x14\x15':
            return True
        index = bisect.bisect_right(self._hidden_starts, cp) - 1
        return index >= 0 and cp < self._hidden[index][1]

    def _index_links(self):
        events = {}
        self._suffixes = {}
        for index, field in enumerate(self.fields):
            if field.target and field.separator >= 0 and not self.in_instruction(field.end):
                self._suffixes[field.end] = self._suffixes.get(field.end, '') + ' <%s>' % field.target
                events.setdefault(field.separator + 1, []).append((index, field))
                events.setdefault(field.end, [])
        self._links, self._link_starts = [], []
        active = []
        for cp in sorted(events):
            for index, field in events[cp]:
                heapq.heappush(active, (-field.start, field.end, index, field.target))
            while active and active[0][1] <= cp:
                heapq.heappop(active)
            self._link_starts.append(cp)
            self._links.append(active[0][3] if active else '')

    def link(self, cp):
        index = bisect.bisect_right(self._link_starts, cp) - 1
        return self._links[index] if index >= 0 else ''

    def suffix(self, cp):
        return self._suffixes.get(cp, '')

    def _read_textboxes(self):
        for name, index in (('textbox', 56), ('header_textbox', 58)):
            if name not in self.binary.stories:
                continue
            base, end = self.binary.stories[name]
            if base == end:
                continue
            try:
                positions, records = _plc(self.binary.blob(index), 22)
                valid = False
                for i in range(len(records)):
                    start, stop = base + positions[i], base + positions[i + 1]
                    if base <= start < stop <= end:
                        self._textboxes[(name, i)] = (start, stop)
                        valid = True
                if not valid:
                    self._textboxes[(name, 0)] = (base, end)
            except (ValueError, struct.error) as exc:
                self._warn('textbox', exc)
                self._textboxes[(name, 0)] = (base, end)

    def textbox(self, index, render, header=False):
        key = ('header_textbox' if header else 'textbox', index)
        if key not in self._textboxes or key in self._textboxes_emitted:
            return []
        self._textboxes_emitted.add(key)
        return render(*self._textboxes[key])

    def markers(self, cp):
        # Return fresh runs so a renderer may add style without mutating state.
        return [copy(run) for run in self._markers.get(cp, [])]

    def _read_bookmarks(self):
        names = self._try_strings(21)
        if not names:
            return
        try:
            starts, records = _plc(self.binary.blob(22), 4)
            ends, _ = _plc(self.binary.blob(23), 0)
            # PlcfBkf/PlcfBkl use the global CP space, including header stories.
            story_end = max((end for _, end in self.binary.stories.values()), default=0)
            for name, cp, record in zip(names, starts, records):
                end_index = struct.unpack_from('<h', record)[0]
                if not (0 <= end_index < len(ends) - 1 and cp <= ends[end_index] <= story_end):
                    self._warn('bookmark', 'invalid end position')
                    continue
                if name and not name.startswith('_'):
                    marker = TextRun('[bookmark: %s] ' % name)
                    marker._bookmark_annotation = True
                    self._markers.setdefault(cp, []).append(marker)
        except (ValueError, struct.error) as exc:
            self._warn('bookmarks', exc)

    def _read_notes(self):
        owners = self._try_strings(36, counted=False)
        pending = []
        for name, ref_index, txt_index, record_size in (
                ('footnote', 2, 3, 2), ('endnote', 46, 47, 2), ('annotation', 4, 5, 30)):
            if name not in self.binary.stories:
                continue
            story_start, story_end = self.binary.stories[name]
            if story_start == story_end:
                continue
            try:
                refs, records = _plc(self.binary.blob(ref_index), record_size)
                offsets, _ = _plc(self.binary.blob(txt_index), 0)
                if len(offsets) < len(records) + 1:
                    raise ValueError('note text PLC has too few positions')
                for i, (cp, record) in enumerate(zip(refs, records)):
                    start, end = story_start + offsets[i], story_start + offsets[i + 1]
                    main_end = self.binary.stories.get('main', (0, 0))[1]
                    if not (0 <= cp < main_end and story_start <= start <= end <= story_end):
                        self._warn(name, 'invalid note CP range')
                        continue
                    author = ''
                    if name == 'annotation':
                        author_index = struct.unpack_from('<H', record, 20)[0]
                        if author_index < len(owners):
                            author = owners[author_index]
                        if not author:
                            length = min(struct.unpack_from('<H', record)[0], 9)
                            author = record[2:2 + length * 2].decode('utf-16-le', errors='replace')
                    pending.append((cp, name, start, end, author))
            except (ValueError, struct.error) as exc:
                self._warn(name, exc)
        number = comment_number = 0
        for cp, name, start, end, author in sorted(pending):
            if name == 'annotation':
                comment_number += 1
                note = Comment(number=comment_number, author=author)
                marker = TextRun('[comment %s]' % comment_number,
                                 note_reference_type='comment', note_reference_number=comment_number)
            else:
                number += 1
                note = Footnote(type=name, number=number)
                marker = TextRun('[%s]' % number, note_ref=number,
                                 note_reference_type=name, note_reference_number=number)
            self._markers.setdefault(cp, []).append(marker)
            self._notes.append((note, start, end))

    def extras(self, render):
        """Render content with the same callback used for main-story blocks."""
        headers, trailers = [], []
        if 'header' in self.binary.stories:
            base, end = self.binary.stories['header']
            try:
                positions, _ = _plc(self.binary.blob(11), 0)
                # First six slots are footnote/endnote separator stories.
                for index in range(6, len(positions) - 1):
                    start, stop = base + positions[index], base + positions[index + 1]
                    if not (base <= start < stop <= end):
                        continue
                    content = render(start, stop)
                    kind = 'header' if (index - 6) % 6 in (0, 1, 4) else 'footer'
                    item = HeaderFooter(type=kind, paragraphs=content)
                    (headers if kind == 'header' else trailers).append(item)
            except (ValueError, struct.error) as exc:
                self._warn('headers', exc)
                # Invalid PLCs cannot assign header/footer variants, but FIB
                # still supplies a bounded story. Retain it as ordinary blocks.
                trailers.extend(render(base, end))
        for note, start, end in self._notes:
            note.paragraphs = render(start, end)
            trailers.append(note)
        # Preserve unanchored textboxes without duplicating anchored placements.
        for name, index in self._textboxes:
            trailers.extend(self.textbox(index, render, header=name == 'header_textbox'))
        return headers, trailers
