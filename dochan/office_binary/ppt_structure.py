"""MS-PPT persistent presentation objects, independent of rendering.

CurrentUserAtom -> UserEditAtom -> PersistDirectoryAtom. Offsets refer to the
PowerPoint Document stream, not to OLE sectors. Latest directory entries win.
The record layout is [MS-PPT] 2.3 (document structure), 2.4 (slides/notes).
"""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .officeart import Limits, Record, RecordHeader, parse_header, parse_records, walk_records

MAX_EDITS = 4096
MAX_OBJECTS = 100000
MAX_DIRECTORY_ENTRIES = 100000
MAX_PARSED_BYTES = 128 * 1024 * 1024


def warn(errors, message):
    message = "WARN: PPT " + message
    if errors is not None and len(errors) < 1000 and message not in errors:
        errors.append(message)


@dataclass
class Sheet:
    slide_id: int
    persist_id: int
    record: Record
    text_records: List[Record] = field(default_factory=list)
    master_id: int = 0
    notes_id: int = 0
    flags: int = 0
    unresolved: bool = False
    recovery_record: Optional[Record] = None


@dataclass
class Presentation:
    document: Record
    slides: List[Sheet] = field(default_factory=list)
    masters: Dict[int, Sheet] = field(default_factory=dict)
    notes: Dict[int, Sheet] = field(default_factory=dict)


def resolve_presentation(data: bytes, current_user: bytes, errors=None) -> Optional[Presentation]:
    if not current_user:
        return None
    user_header = parse_header(current_user)
    if (user_header is None or user_header.rec_type != 4086
            or user_header.rec_len < 20 or user_header.rec_len > len(current_user) - 8):
        warn(errors, "invalid CurrentUserAtom; using legacy text recovery")
        return None
    edit_offset = struct.unpack_from("<I", current_user, 16)[0]
    visited = set()
    offsets = {}
    visited_directories = set()
    remaining_entries = MAX_DIRECTORY_ENTRIES
    document_id = None
    parsed_bytes = [0]
    remaining_records = [MAX_OBJECTS]
    cache = {}

    def read_object(offset, expected=None):
        header = parse_header(data, offset)
        if (header is None or header.rec_len > len(data) - offset - 8
                or header.rec_len > 64 * 1024 * 1024):
            warn(errors, "invalid persistent object offset or size")
            return None
        if expected and header.rec_type not in expected:
            warn(errors, "unexpected persistent object type %d" % header.rec_type)
            return None
        if offset in cache:
            return cache[offset]
        parsed_bytes[0] += header.rec_len + 8
        if remaining_records[0] <= 0:
            warn(errors, "persistent record budget exceeded")
            return None
        if parsed_bytes[0] > MAX_PARSED_BYTES or len(cache) >= MAX_OBJECTS:
            warn(errors, "persistent object budget exceeded")
            return None
        records = parse_records(data, offset, header.rec_len + 8,
                                limits=Limits(max_records=remaining_records[0]), errors=errors)
        remaining_records[0] -= sum(1 for _ in walk_records(records))
        obj = records[0] if records else None
        cache[offset] = obj
        return obj

    for _ in range(MAX_EDITS):
        if edit_offset in visited:
            warn(errors, "UserEditAtom cycle; older edits ignored")
            break
        visited.add(edit_offset)
        edit = read_object(edit_offset, {4085})
        if edit is None or len(edit.data) < 28:
            warn(errors, "invalid UserEditAtom; using available persistent objects")
            break
        previous, directory_offset, current_doc = struct.unpack_from("<III", edit.data, 8)
        if document_id is None:
            document_id = current_doc
        if directory_offset not in visited_directories:
            visited_directories.add(directory_offset)
            directory = read_object(directory_offset, {6001, 6002})
            if directory is None:
                break
            position = 0
            while position + 4 <= len(directory.data):
                entry = struct.unpack_from("<I", directory.data, position)[0]
                start, count = entry & 0xFFFFF, entry >> 20
                position += 4
                if (not count or start + count > 0x100000
                        or count * 4 > len(directory.data) - position):
                    warn(errors, "invalid or oversized persist directory entry")
                    break
                # Count work, not unique IDs: duplicate IDs must not bypass
                # the shared budget across distinct edit directories.
                if count > remaining_entries:
                    warn(errors, "persist directory entry budget exceeded")
                    remaining_entries = 0
                    break
                remaining_entries -= count
                for i in range(count):
                    offsets.setdefault(start + i, struct.unpack_from("<I", directory.data, position + i * 4)[0])
                position += count * 4
            if remaining_entries <= 0 and previous:
                warn(errors, "persist directory entry budget exceeded")
                break
        if not previous:
            break
        edit_offset = previous
    else:
        warn(errors, "UserEditAtom count limit exceeded")
    if document_id not in offsets:
        warn(errors, "document persist reference missing; using legacy text recovery")
        return None
    document = read_object(offsets[document_id], {1000})
    if document is None:
        return None
    result = Presentation(document)
    for listing in document.children:
        if listing.header.rec_type != 4080 or listing.header.rec_instance not in (0, 1, 2):
            continue
        instance = listing.header.rec_instance
        current = None
        for atom in listing.children:
            if atom.header.rec_type != 1011:
                if current is not None:
                    current.text_records.append(atom)
                continue
            current = None
            if len(atom.data) < 20:
                warn(errors, "truncated SlidePersistAtom")
                continue
            pid, _, _, sid = struct.unpack_from("<4I", atom.data)
            if pid not in offsets:
                warn(errors, "slide persist reference missing")
                obj = None
            else:
                obj = read_object(offsets[pid], {1006} if instance == 0 else {1016, 1006} if instance == 1 else {1008})
            unresolved = obj is None
            if obj is None:
                # Retain list position and its outline text even when its
                # drawing persist is missing; never shift later slide IDs.
                kind = (1006, 1016, 1008)[instance]
                obj = Record(RecordHeader(15, 0, kind, 0), -1, memoryview(b""))
            current = Sheet(sid, pid, obj, unresolved=unresolved)
            for child in obj.children:
                if child.header.rec_type == 1007 and len(child.data) >= 22:
                    current.master_id, current.notes_id, current.flags = struct.unpack_from("<IIH", child.data, 12)
            if instance == 0:
                result.slides.append(current)
            elif instance == 1:
                result.masters[sid] = current
            else:
                result.notes[sid] = current
    # A corrupt SlidePersistAtom may point away from the sole surviving
    # slide object. Recover only an unambiguous object in the *latest*
    # directory map. Scanning historical stream containers would resurrect
    # superseded edits, and guessing among multiple orphans misassigns text.
    missing = [slide for slide in result.slides if slide.unresolved]
    if len(missing) == 1 and not missing[0].text_records:
        listed = result.slides + list(result.masters.values()) + list(result.notes.values())
        referenced_ids = {sheet.persist_id for sheet in listed}
        referenced_offsets = {sheet.record.offset for sheet in listed if not sheet.unresolved}
        candidates = set()
        for pid, offset in offsets.items():
            if pid in referenced_ids or offset in referenced_offsets:
                continue
            header = parse_header(data, offset)
            if header is not None and header.rec_type == 1006:
                candidates.add(offset)
                if len(candidates) > 1:
                    break
        if len(candidates) == 1:
            recovery = read_object(next(iter(candidates)), {1006})
            if recovery is not None:
                missing[0].recovery_record = recovery
                for child in recovery.children:
                    if child.header.rec_type == 1007 and len(child.data) >= 22:
                        missing[0].master_id, missing[0].notes_id, missing[0].flags = struct.unpack_from("<IIH", child.data, 12)
                warn(errors, "missing slide reference recovered from unique latest persistent slide")
    return result
