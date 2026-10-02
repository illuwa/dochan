"""Conservative text projections of binary HWP change-tracking ranges.

The public HWP 5 specification defines PARA_RANGE_TAG as start/end DWORDs
and an upper-byte kind/lower-24-bit value. Public HWP/HWPX paired documents
establish kinds 0x10=Insert and 0x11=Delete and one-based DocInfo references.
Tracked documents store the full marked text in compressed ViewText, while
BodyText contains the final text. ViewText is not distribution-encrypted
unless FileHeader's independent distribution bit is also set.
"""
from dataclasses import dataclass
from datetime import datetime
import struct


HWPTAG_TRACK_CHANGE = 96
HWPTAG_TRACK_CHANGE_AUTHOR = 97
MAX_REVISION_RANGES = 100_000
MAX_AUTHOR_UNITS = 4096
_KINDS = {0x10: 'Insert', 0x11: 'Delete'}


@dataclass(frozen=True)
class Change:
    kind: str
    author_id: int
    timestamp: tuple
    hidden: bool


@dataclass(frozen=True)
class Author:
    name: str
    mark: int
    color: int


def parse_change(data):
    """Decode the observed 26-byte text-change DocInfo record.

    The timestamp has no timezone in the binary record. Keep its five local
    components instead of inventing a UTC conversion or seconds value.
    Formatting kinds remain unsupported and must produce a parser warning.
    """
    if len(data) != 26:
        raise ValueError('unsupported HWP change record size')
    kind_code = struct.unpack_from('<I', data, 0)[0]
    if kind_code not in _KINDS:
        raise ValueError('unsupported HWP change kind')
    year, month, day, hour, minute, author = struct.unpack_from('<6H', data, 4)
    datetime(year, month, day, hour, minute)  # Reject invalid timestamps.
    hidden = struct.unpack_from('<I', data, 22)[0]
    if hidden not in (0, 1):
        raise ValueError('unsupported HWP change visibility')
    return Change(_KINDS[kind_code], author, (year, month, day, hour, minute), bool(hidden))


def parse_author(data):
    """Decode DWORD-counted UTF-16 name, mark and color fields."""
    if len(data) < 12:
        raise ValueError('truncated HWP change author')
    count = struct.unpack_from('<I', data, 0)[0]
    if count > MAX_AUTHOR_UNITS:
        raise ValueError('HWP change author name exceeds limit')
    end = 4 + count * 2
    if end + 8 != len(data):
        raise ValueError('unsupported HWP change author size')
    name = data[4:end].decode('utf-16-le', errors='replace')
    mark, color = struct.unpack_from('<II', data, end)
    return Author(name, mark, color)


def _removals(text_result, range_records, changes, mode, errors):
    """Validate raw WCHAR ranges and return selected visible-text offsets.

    ``changes`` maps one-based DocInfo record numbers to Change objects.
    Invalid references, overlaps and bounds preserve their text and report
    one warning per problem kind. Non-revision range tags are left alone.
    """
    if mode not in ('preserve', 'final', 'original'):
        raise ValueError('unsupported HWP revision mode')
    if mode == 'preserve' and not changes:
        return []
    problems = set()
    spans = []
    range_count = 0
    raw_map = text_result['raw_to_text']
    for data in range_records:
        if len(data) % 12:
            problems.add('truncated')
            continue
        range_count += len(data) // 12
        if range_count > MAX_REVISION_RANGES:
            problems.add('range-limit')
            spans = []
            break
        for start, end, tag in struct.iter_unpack('<III', data):
            kind = _KINDS.get(tag >> 24)
            if kind is None:
                continue
            change = changes.get(tag & 0xFFFFFF)
            if not isinstance(change, Change) or change.kind != kind:
                problems.add('reference')
                continue
            if start >= end or end >= len(raw_map):
                problems.add('bounds')
                continue
            a, b = raw_map[start], raw_map[end]
            if a >= b:
                problems.add('empty-range')
                continue
            spans.append([a, b, kind, True])
    spans.sort(key=lambda span: (span[0], span[1]))
    # Compare against the furthest previous end, not merely the immediate
    # predecessor: an invalid long span can enclose several later ranges.
    active = []
    for span in spans:
        active = [previous for previous in active if previous[1] > span[0]]
        if active:
            problems.add('overlap')
            span[3] = False
            for previous in active:
                previous[3] = False
        active.append(span)
        # Bound hostile mutually overlapping ranges independently of count.
        if len(active) > 128:
            problems.add('overlap-limit')
            for previous in spans:
                previous[3] = False
            break
    for problem in sorted(problems):
        severity = 'WARN' if mode == 'preserve' else 'ERR'
        warning = '{}: HWP revision partial [{}]; revision_mode={}; unresolved content preserved'.format(severity, problem, mode)
        if warning not in errors:
            errors.append(warning)
    if problems or mode == 'preserve':
        return []
    remove_kind = 'Delete' if mode == 'final' else 'Insert'
    return [(a, b) for a, b, kind, valid in spans if valid and kind == remove_kind]


def project_text_result(text_result, range_records, changes, mode, errors):
    """Project before run creation and remap all visible-text boundaries.

    Raw control positions remain in the unchanged binary paragraph's index
    space. raw_to_text translates their boundaries into the projected text;
    field_marks already use visible-text offsets and are remapped directly.
    """
    removals = _removals(text_result, range_records, changes, mode, errors)
    if not removals:
        return text_result
    text = text_result['text']
    offsets = [0]
    kept = []
    range_index = 0
    for index, char in enumerate(text):
        while range_index < len(removals) and removals[range_index][1] <= index:
            range_index += 1
        removed = range_index < len(removals) and removals[range_index][0] <= index < removals[range_index][1]
        if not removed:
            kept.append(char)
        offsets.append(len(kept))
    result = dict(text_result)
    result['text'] = ''.join(kept)
    result['raw_to_text'] = [offsets[value] for value in text_result['raw_to_text']]
    result['field_marks'] = [(offsets[pos], kind, identity) for pos, kind, identity in text_result.get('field_marks', [])]
    return result
