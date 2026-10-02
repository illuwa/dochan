"""Attach DOC captions using source paragraph boundaries, never label guesses.

MS-DOC STSH/StdfBase stores the built-in sti in its low twelve bits (34 is
Caption). Names and based-on links come from the existing style reader. Field
instructions and cached results remain owned by Stories; SEQ is not evaluated.
"""
import bisect
import itertools
import re
import struct

from ..model.document import Paragraph
from ..model.image import Image
from ..model.table import Table
from .doc_tables import assemble_blocks

_SEQ = re.compile(r'^\s*SEQ\s+(?:"([^"]+)"|([^\s\\]+))', re.IGNORECASE)
_MAX_STYLES = 4096
_MAX_STYLE_DEPTH = 32


def _edge_image(blocks):
    """A single inline image may share text, but cannot cross another object."""
    image = None
    for block in blocks:
        if isinstance(block, Image):
            if image is not None:
                return None
            image = block
        elif not isinstance(block, Paragraph):
            break
    return image


def builtin_caption_styles(binary, warnings):
    """Read only sti; keep the core style parser and its output unchanged."""
    data = binary.blob(1)
    result = set()
    if not data:
        return result
    try:
        if len(data) < 6:
            raise ValueError('truncated STSH header')
        cb, count, base_size = struct.unpack_from('<HHH', data)
        if cb < 4 or base_size < 6 or count > _MAX_STYLES:
            raise ValueError('invalid STSH limits')
        pos = cb + 2
        for index in range(count):
            if pos + 2 > len(data):
                raise ValueError('truncated STD length')
            size = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            if pos + size > len(data):
                raise ValueError('truncated STD')
            if size >= base_size + 2 and index in binary.styles:
                sti, flags = struct.unpack_from('<HH', data, pos)
                if sti & 0xfff == 34 and flags & 15 == 1:
                    result.add(index)
            pos += size
    except (ValueError, struct.error) as exc:
        warnings.append('WARN: DOC caption styles: %s' % exc)
    return result


class DocCaptions:
    def __init__(self, binary, stories, warnings):
        self.binary = binary
        self.stories = stories
        self.builtin = builtin_caption_styles(binary, warnings)
        self.fields = stories.fields
        self.starts = [field.start for field in self.fields]

    def kind(self, record):
        # A caption must be a single, ordinary paragraph, not a host containing
        # an inline object or a textbox whose content was expanded into blocks.
        if record.props.get('in_table') or '\x01' in record.text or '\x08' in record.text:
            return ''
        start = bisect.bisect_left(self.starts, record.start)
        stop = bisect.bisect_left(self.starts, record.end)
        for index in range(start, stop):
            field = self.fields[index]
            if (field.end >= record.end or field.separator < 0
                    or self.stories.in_instruction(field.start)
                    or self.binary.char_props(field.start).get('deleted')):
                continue
            match = _SEQ.match(field.instruction)
            if match:
                # A hidden SEQ is a counter update, not a visible caption.
                # Tokenize quoted arguments so a literal \\h is not a switch.
                switches = re.findall(r'"[^"]*"|\\[A-Za-z*]+|[^\s\\]+',
                                      field.instruction[match.end():])
                if any(token.casefold() == r'\h' for token in switches):
                    continue
                name = (match.group(1) or match.group(2)).casefold()
                if name in {'table', '표'}:
                    return 'table'
                if name in {'figure', '그림'}:
                    return 'image'
                return '' if name in {'equation', '수식'} else 'any'
        style = record.props.get('istd', 0)
        visited = set()
        while style in self.binary.styles and style not in visited and len(visited) < _MAX_STYLE_DEPTH:
            visited.add(style)
            entry = self.binary.styles[style]
            if style in self.builtin or entry.get('name', '').casefold() == 'caption':
                return 'any'
            style = entry.get('base')
        return ''

    def render(self, records, render, warnings, textbox_at=None):
        """Keep empty source groups as barriers; retain only three groups at once."""
        def groups():
            for in_table, group in itertools.groupby(records, lambda r: bool(r.props.get('in_table'))):
                if in_table:
                    blocks = assemble_blocks(group, render, warnings)
                    target = blocks[0] if len(blocks) == 1 and isinstance(blocks[0], Table) else None
                    yield blocks, '', (target, target)
                    continue
                for record in group:
                    blocks = render(record)
                    kind = self.kind(record) if len(blocks) == 1 and isinstance(blocks[0], Paragraph) else ''
                    targets = (_edge_image(blocks), _edge_image(reversed(blocks)))
                    # Textbox contents are not targets even when flattened into
                    # the main flow by the native renderer.
                    if textbox_at and any(textbox_at(record.start + m.start()) is not None
                                          for m in re.finditer('\x08', record.text)):
                        targets = (None, None)
                    yield blocks, kind, targets

        source = iter(groups())
        previous = ([], '', (None, None))
        current = next(source, None)
        output = []
        while current is not None:
            following = next(source, None)
            blocks, kind, _ = current
            if kind:
                candidates = []
                for neighbor, edge, side in ((previous, 1, 'BOTTOM'), (following, 0, 'TOP')):
                    target = neighbor[2][edge] if neighbor else None
                    if target is not None and not target.caption and (
                            kind == 'any' or kind == 'table' and isinstance(target, Table)
                            or kind == 'image' and isinstance(target, Image)):
                        candidates.append((target, side))
                if len(candidates) == 1:
                    target, side = candidates[0]
                    target.caption = blocks
                    target.caption_side = side
                    blocks = []
            output.extend(blocks)
            previous, current = current, following
        return output
