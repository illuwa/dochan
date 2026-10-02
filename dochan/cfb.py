"""Read-only Compound File Binary reader, independently implemented from MS-CFB.

Specification: https://learn.microsoft.com/openspecs/windows_protocols/ms-cfb/
53989ce4-7b05-4f8d-829b-d08d6148375b (sections 2.2--2.6 and 4.1).
Only the small read API used by dochan is provided; this is not an OLE writer
or a general replacement for third-party property-set/metadata APIs.

Allocation tables and reachable directory entries are indexed, while stream
payloads (including the root mini stream) are read on demand. File offsets and
chain lengths are bounded before any payload allocation. Unallocated directory
slots and allocation-table slack are never interpreted as live objects.
"""

import io
import os
import struct
import sys
import threading
from array import array
from dataclasses import dataclass


MAGIC = bytes.fromhex('d0cf11e0a1b11ae1')
FREESECT = NOSTREAM = 0xffffffff
ENDOFCHAIN = 0xfffffffe
FATSECT = 0xfffffffd
DIFSECT = 0xfffffffc
STGTY_STORAGE, STGTY_STREAM, STGTY_ROOT = 1, 2, 5
# Accepted for the existing embedded-storage validation call. All dangerous
# defects are rejected regardless of this compatibility keyword.
DEFECT_INCORRECT = 30
MAX_FILE_SIZE = 512 * 1024 * 1024
MAX_STREAM_SIZE = 256 * 1024 * 1024
MAX_SECTORS = 1024 * 1024
MAX_DIRECTORY_ENTRIES = 131072
MAX_STORAGE_DEPTH = 128
MAX_PATH_COMPONENTS = 1024 * 1024
MAX_CHAIN_STEPS = 4 * 1024 * 1024
MAX_RECOVERY_WARNINGS = 16
# Metadata-only deviations remain available to strict callers, but do not
# imply lost content. These fixed categories do affect addresses or payloads.
_RECOVERY_CATEGORIES = frozenset((
    'truncated allocation table sector', 'inaccessible FAT suffix omitted',
    'stream size exceeds available sectors',
    'truncated chain points outside allocation table',
    'truncated chain does not match declared size', 'truncated stream payload',
    'inaccessible directory branch omitted', 'invalid directory entry omitted',
    'duplicate directory name omitted', 'stream read failed',
))
_WARNING_PREFIX = 'WARN: OLE/CFB 컨테이너 손상 복구: '


def append_recovery_warnings(ole, errors, path=''):
    """Forward content-loss diagnostics once per category, across all readers.

    The optional path describes a container or stream, not a filesystem path.
    Reference backends and older test doubles have no recovery diagnostics.
    """
    issues = getattr(ole, 'recovery_issues', ())
    if not isinstance(issues, (list, tuple)):
        return
    seen = {message[len(_WARNING_PREFIX):].split(' (', 1)[0]
            for message in errors if message.startswith(_WARNING_PREFIX)}
    for category, stream_path in issues[:MAX_RECOVERY_WARNINGS]:
        if len(seen) >= MAX_RECOVERY_WARNINGS:
            break
        if category not in _RECOVERY_CATEGORIES or category in seen:
            continue
        location = stream_path or path or '/'
        location = ''.join(ch if ch.isprintable() else '?' for ch in str(location)[:256])
        errors.append(_WARNING_PREFIX + category + ' (' + location + ')')
        seen.add(category)


class CFBError(OSError):
    """Malformed, truncated, or resource-limited compound file."""

    def __init__(self, message):
        super().__init__('OLE/CFB: ' + message)


OleFileError = CFBError


def _u32(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]


def _words(data):
    result = array('I')
    result.frombytes(data)
    if sys.byteorder != 'little':
        result.byteswap()
    return result


def _name_key(name):
    # MS-CFB 2.6.4 compares single UTF-16 units, with simple (not expanding)
    # uppercase conversion. Surrogates are intentionally left unchanged.
    raw = name.encode('utf-16le', errors='surrogatepass')
    units = struct.unpack('<%dH' % (len(raw) // 2), raw)
    result = []
    for unit in units:
        upper = chr(unit).upper()
        if len(upper) != 1:
            # Greek prosgegrammeni has a single-unit titlecase mapping where
            # Python's full uppercase expands. Sharp-s/ligatures stay intact.
            upper = chr(unit).title()
        result.append(ord(upper) if len(upper) == 1 else unit)
    return tuple(result)


@dataclass
class _Entry:
    name: str
    kind: int
    left: int
    right: int
    child: int
    start: int
    size: int


class _Stream(io.RawIOBase):
    """Seekable view over a validated chain; no eager payload copy."""

    def __init__(self, owner, chain, size, mini=False):
        super().__init__()
        self._owner, self._chain, self._size = owner, chain, size
        self._mini, self._position = mini, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        self._checkClosed()
        return self._position

    def seek(self, offset, whence=0):
        self._checkClosed()
        if whence not in (0, 1, 2):
            raise ValueError('invalid whence')
        offset = offset.__index__()
        position = offset + (0 if whence == 0 else self._position if whence == 1 else self._size)
        if position < 0:
            raise ValueError('negative seek position')
        self._position = position
        return position

    def read(self, size=-1):
        self._checkClosed()
        self._owner._check_open()
        size = -1 if size is None else size.__index__()
        remaining = max(0, self._size - self._position)
        size = remaining if size < 0 else min(size, remaining)
        if not size:
            return b''
        sector = 64 if self._mini else self._owner.sectorsize
        chunks = []
        position, stop = self._position, self._position + size
        while position < stop:
            index, within = divmod(position, sector)
            sid = self._chain[index]
            offset = self._owner._mini_offset(sid) if self._mini else (sid + 1) * sector
            take = min(sector - within, stop - position)
            # Coalesce physically consecutive regular sectors into one read.
            if not self._mini:
                last = index
                while position + take < stop and take + within == (last - index + 1) * sector:
                    if last + 1 >= len(self._chain) or self._chain[last + 1] != self._chain[last] + 1:
                        break
                    last += 1
                    take += min(sector, stop - position - take)
            chunks.append(self._owner._read_at(offset + within, take))
            position += take
        self._position = stop
        return b''.join(chunks)

    def readinto(self, buffer):
        view = memoryview(buffer).cast('B')
        data = self.read(len(view))
        view[:len(data)] = data
        return len(data)


class OleFileIO:
    """Open a path, raw bytes, or a seekable binary file without taking its ownership.

    File paths and byte buffers opened here are closed here. Supplied file-like
    objects remain open. ``raise_defects`` is retained for call compatibility;
    unambiguous prefixes survive local truncation in the default mode.
    Live cycles, ambiguous allocations and resource limits remain CFBErrors.
    """

    def __init__(self, filename, raise_defects=40, strict_recovery=False):
        self._closed = False
        self._owned = False
        self._lock = threading.RLock()
        self._chains = {}
        self._sizes = {}
        self._chain_steps = 0
        self._raise_defects = raise_defects
        self._strict_recovery = strict_recovery
        self.parsing_issues = []
        self.recovery_issues = []
        self._issue_path = ''
        self._fp = None
        try:
            if isinstance(filename, (bytes, bytearray, memoryview)):
                if len(filename) > MAX_FILE_SIZE:
                    raise CFBError('CFB file size limit exceeded')
                self._fp = io.BytesIO(filename)
                self._owned = True
            elif isinstance(filename, (str, os.PathLike)):
                self._fp = open(filename, 'rb')
                self._owned = True
            else:
                self._fp = filename
            self._fp.seek(0, 2)
            self._file_size = self._fp.tell()
            if self._file_size > MAX_FILE_SIZE:
                raise CFBError('CFB file size limit exceeded')
            self._parse()
        except Exception:
            self.close()
            raise

    def _check_open(self):
        if self._closed:
            raise ValueError('I/O operation on closed compound file')

    def _metadata_defect(self, message):
        """Separate metadata deviations from recovery that may omit content."""
        category = message.removeprefix('CFB ')
        recovery = category in _RECOVERY_CATEGORIES
        if self._raise_defects <= DEFECT_INCORRECT or (self._strict_recovery and recovery):
            raise CFBError(message)
        if message not in self.parsing_issues:
            self.parsing_issues.append(message)
        if recovery:
            self._record_recovery(category)

    def _record_recovery(self, category):
        if (len(self.recovery_issues) < MAX_RECOVERY_WARNINGS
                and not any(item[0] == category for item in self.recovery_issues)):
            self.recovery_issues.append((category, self._issue_path))

    def _read_at(self, offset, size):
        self._check_open()
        if offset < 0 or size < 0 or offset + size > self._file_size:
            raise CFBError('CFB truncated data or offset outside file')
        with self._lock:
            self._fp.seek(offset)
            data = self._fp.read(size)
        if len(data) != size:
            raise CFBError('CFB truncated read')
        return data

    def _sector(self, sid):
        if not 0 <= sid < self._sector_count:
            raise CFBError('CFB sector outside file')
        return self._read_at((sid + 1) * self.sectorsize, self.sectorsize)

    def _table_sector(self, sid):
        """Read only present allocation words; never invent missing links."""
        if not 0 <= sid < self._sector_count:
            raise CFBError('CFB sector outside file')
        offset = (sid + 1) * self.sectorsize
        available = min(self.sectorsize, self._file_size - offset)
        if available < self.sectorsize:
            self._metadata_defect('CFB truncated allocation table sector')
        return _words(self._read_at(offset, available - available % 4))

    def _claim(self, sid, owner, mini=False):
        owners = self._mini_owners if mini else self._owners
        if not 0 <= sid < len(owners):
            raise CFBError('CFB mini sector outside root stream' if mini else 'CFB sector outside file')
        if owners[sid] != -1:
            raise CFBError('CFB duplicate sector allocation or cyclic chain')
        owners[sid] = owner

    def _chain(self, start, table, owner, count=None, mini=False, limit=None):
        result = array('I')
        sid = start
        bound = len(self._mini_owners) if mini else self._sector_count
        recover = owner >= 0 or owner in (-4, -5)
        if count is not None and count > bound:
            if not recover:
                raise CFBError('CFB stream size exceeds available sectors')
            self._metadata_defect('CFB stream size exceeds available sectors')
        if limit is None:
            limit = bound
        owners = self._mini_owners if mini else self._owners
        visited = set()
        claimed = []
        try:
            while sid != ENDOFCHAIN:
                self._chain_steps += 1
                if self._chain_steps > MAX_CHAIN_STEPS:
                    raise CFBError('CFB cumulative chain work limit exceeded')
                if sid in visited:
                    raise CFBError('CFB duplicate sector allocation or cyclic chain')
                if not 0 <= sid < min(bound, len(table)):
                    if not recover or (not result and owner < 0 and owner != -5):
                        raise CFBError('CFB chain sector outside allocation table')
                    self._metadata_defect('CFB truncated chain points outside allocation table')
                    break
                if len(result) >= limit:
                    raise CFBError('CFB chain length limit or cycle')
                if (recover and count is not None and len(result) >= count
                        and owners[sid] not in (-1, owner)):
                    self._metadata_defect('CFB unused stream tail aliases another allocation')
                    break
                if (owner < 0 and owner != -5) or count is None or len(result) < count:
                    self._claim(sid, owner, mini)
                    claimed.append(sid)
                visited.add(sid)
                result.append(sid)
                sid = table[sid]
            if count is not None and len(result) != count:
                if (owner >= 0 or owner == -5) and len(result) > count:
                    # Validate spare links without claiming them as payload;
                    # expose only the declared logical stream extent.
                    self._metadata_defect('CFB stream has excess allocated sectors')
                else:
                    if not recover:
                        raise CFBError('CFB chain length does not match declared size')
                    self._metadata_defect('CFB truncated chain does not match declared size')
        except Exception:
            # A failed optional stream must not poison ownership for subsequent
            # reads. Only claims from this attempt are rolled back.
            for sid in claimed:
                owners[sid] = -1
            raise
        # Extra MiniFAT links are checked, but never become allocator words
        # or steal ownership from streams beyond the header's declared count.
        return result[:count] if owner == -5 and count is not None else result

    def _extent(self, chain, size, mini=False):
        """Size of the contiguous, physically present prefix of a stream."""
        unit = 64 if mini else self.sectorsize
        available = 0
        for sid in chain:
            if available >= size:
                break
            if mini:
                take = min(unit, self._root_size - sid * unit)
            else:
                take = min(unit, self._file_size - (sid + 1) * unit)
            available += max(0, take)
            if take < unit:
                break
        if available < size:
            self._metadata_defect('CFB truncated stream payload')
        return min(size, available)

    def _parse(self):
        header = self._read_at(0, 512)
        if header[:8] != MAGIC:
            raise CFBError('not an OLE2 structured storage file')
        self.major_version = struct.unpack_from('<H', header, 26)[0]
        byte_order, shift, mini_shift = struct.unpack_from('<3H', header, 28)
        if self.major_version not in (3, 4) or shift != {3: 9, 4: 12}.get(self.major_version):
            raise CFBError('CFB invalid version or sector size')
        if byte_order != 0xfffe:
            self._metadata_defect('CFB invalid byte order marker')
        if mini_shift != 6 or _u32(header, 56) != 4096:
            raise CFBError('CFB invalid mini sector size or cutoff')
        self.sectorsize = 1 << shift
        # A last sector can have its unused padding omitted by older writers.
        # Keep that sector addressable, but _read_at still requires every byte
        # actually requested to exist; no truncated payload is zero-filled.
        self._sector_count = (self._file_size - 1) // self.sectorsize
        if not 2 <= self._sector_count <= MAX_SECTORS:
            raise CFBError('CFB sector count limit or truncated file')
        self._owners = array('i', [-1]) * self._sector_count
        dir_count, fat_count, first_dir = struct.unpack_from('<3I', header, 40)
        first_mini, mini_count, first_dif, dif_count = struct.unpack_from('<4I', header, 60)
        if not 1 <= fat_count <= self._sector_count or dif_count > self._sector_count:
            raise CFBError('CFB allocation table count limit')
        slots = list(struct.unpack_from('<109I', header, 76))
        fat_ids = slots[:min(fat_count, 109)]
        if any(sid != FREESECT for sid in slots[len(fat_ids):]):
            self._metadata_defect('CFB unused DIFAT slots are not free')
        dif_ids = []
        sid = first_dif
        for _ in range(dif_count):
            self._claim(sid, -2)
            dif_ids.append(sid)
            words = _words(self._sector(sid))
            take = min(fat_count - len(fat_ids), len(words) - 1)
            fat_ids.extend(words[:take])
            if any(value != FREESECT for value in words[take:-1]):
                self._metadata_defect('CFB unused DIFAT slots are not free')
            sid = words[-1]
        if dif_count and sid != ENDOFCHAIN:
            if sid == FREESECT:
                # Observed in 10 public HWP files. Count and all visited IDs
                # have already been checked; never follow this sentinel.
                self._metadata_defect('CFB DIFAT uses FREESECT terminator')
            else:
                raise CFBError('CFB DIFAT chain termination or cycle')
        if len(fat_ids) != fat_count:
            raise CFBError('CFB DIFAT FAT count mismatch')
        self._fat = array('I')
        for index, sid in enumerate(fat_ids):
            if not 0 <= sid < self._sector_count:
                if not index:
                    raise CFBError('CFB first FAT sector outside file')
                self._metadata_defect('CFB inaccessible FAT suffix omitted')
                fat_ids = fat_ids[:index]
                break
            self._claim(sid, -3)
            words = self._table_sector(sid)
            if len(words) != self.sectorsize // 4 and sid != fat_ids[-1]:
                raise CFBError('CFB missing interior FAT words')
            # FAT slack cannot address any physical sector. Still visit and
            # reserve every declared FAT sector, without retaining slack words.
            self._fat.extend(words[:max(0, self._sector_count - len(self._fat))])
        for ids, marker in ((fat_ids, FATSECT), (dif_ids, DIFSECT)):
            for sid in ids:
                if sid >= len(self._fat) or self._fat[sid] != marker:
                    self._metadata_defect('CFB incorrect FAT/DIFAT sector marker')
        directory = self._chain(first_dir, self._fat, -4,
                                count=dir_count if self.major_version == 4 else None,
                                limit=MAX_DIRECTORY_ENTRIES // (self.sectorsize // 128))
        if not directory:
            raise CFBError('CFB missing root directory')
        self._directory = directory
        self._entry_count = len(directory) * (self.sectorsize // 128)
        self._entries = {}
        self.root = self._entry(0)
        if self.root.kind != STGTY_ROOT:
            raise CFBError('CFB invalid root directory type')
        self._paths = {}
        self._lookup = {}
        self._index_directory()
        if mini_count and first_mini == ENDOFCHAIN and not self.root.size:
            if not any(ent.kind == STGTY_STREAM and 0 < ent.size < 4096
                       for ent in self._entries.values()):
                # The absent allocator is unused by every live stream. A stale
                # count (public 46904.xls) does not alter any stream address.
                self._metadata_defect('CFB unused absent MiniFAT has nonzero count')
                mini_count = 0
        mini_fat_chain = self._chain(first_mini, self._fat, -5, count=mini_count) if mini_count else array('I')
        self._minifat = array('I')
        for sid in mini_fat_chain:
            words = self._table_sector(sid)
            if len(words) != self.sectorsize // 4 and sid != mini_fat_chain[-1]:
                raise CFBError('CFB missing interior MiniFAT words')
            self._minifat.extend(words)
        self._root_chain = None
        if self.root.size <= MAX_STREAM_SIZE:
            self._load_mini_stream()

    def _load_mini_stream(self):
        if self._root_chain is not None:
            return
        # A corrupt, unused root size must not prevent regular stream reads.
        # Enforce the same budget before the first actual mini-stream access.
        self._check_size(self.root.size)
        self._root_chain = self._chain(self.root.start, self._fat, 0,
                                       count=(self.root.size + self.sectorsize - 1) // self.sectorsize) if self.root.size else array('I')
        self._root_size = self._extent(self._root_chain, self.root.size)
        self._mini_owners = array('i', [-1]) * ((self._root_size + 63) // 64)

    def _entry_bytes(self, index):
        if not 0 <= index < self._entry_count:
            raise CFBError('CFB directory entry outside directory stream')
        sector, offset = divmod(index * 128, self.sectorsize)
        return self._read_at((self._directory[sector] + 1) * self.sectorsize + offset, 128)

    def _entry(self, index):
        if index in self._entries:
            return self._entries[index]
        data = self._entry_bytes(index)
        length, kind, color, left, right, child = struct.unpack_from('<HBBIII', data, 64)
        if kind not in (1, 2, 5):
            raise CFBError('CFB invalid live directory entry type')
        if color not in (0, 1):
            self._metadata_defect('CFB invalid directory tree color')
        try:
            name = self._directory_name(data, length, index)
        except CFBError:
            if index != 0:
                raise
            self._metadata_defect('CFB nonessential root label is invalid')
            name = ''
        start = _u32(data, 116)
        size = _u32(data, 120) if self.major_version == 3 else struct.unpack_from('<Q', data, 120)[0]
        result = _Entry(name, kind, left, right, child, start, size)
        self._entries[index] = result
        return result

    def _directory_name(self, data, length, index):
        if length < 2 or length > 64 or length % 2:
            raise CFBError('CFB invalid directory name length or terminator')
        if data[length - 2:length] != b'\0\0':
            if index != 0:
                raise CFBError('CFB invalid directory name terminator')
            # Root labels never participate in lookup (MS-CFB 2.6.2). Public
            # older producers write a one-unit root label without a terminator.
            self._metadata_defect('CFB root label terminator missing')
        try:
            name = data[:length - 2].decode('utf-16le')
        except UnicodeError as exc:
            raise CFBError('CFB invalid UTF-16 directory name') from exc
        if (not name and index != 0) or '\0' in name:
            raise CFBError('CFB empty or embedded-NUL directory name')
        return name

    def _index_directory(self):
        # Walk both sibling links rather than relying on writer balancing or
        # ordering. A single visited set rejects cycles and multiply owned nodes.
        visited = {0}
        pending = [(self.root.child, (), 0)]
        path_components = 0
        while pending:
            index, parent, parent_id = pending.pop()
            if index == NOSTREAM:
                continue
            if index in visited:
                raise CFBError('CFB cyclic or duplicate directory entry')
            visited.add(index)
            try:
                data = self._entry_bytes(index)
            except CFBError:
                self._metadata_defect('CFB inaccessible directory branch omitted')
                continue
            try:
                ent = self._entry(index)
            except CFBError:
                self._metadata_defect('CFB invalid directory entry omitted')
                # A live but unnameable object cannot be assigned an invented
                # path. Its sibling links remain at known offsets; its children
                # stay orphaned. Unallocated slots have no meaningful links.
                if data[66] in (STGTY_STORAGE, STGTY_STREAM):
                    left, right = struct.unpack_from('<II', data, 68)
                    pending.extend(((right, parent, parent_id), (left, parent, parent_id)))
                continue
            if ent.kind == STGTY_ROOT:
                raise CFBError('CFB duplicate root entry')
            path = parent + (ent.name,)
            if len(path) > MAX_STORAGE_DEPTH:
                raise CFBError('CFB storage depth limit exceeded')
            path_components += len(path)
            if path_components > MAX_PATH_COMPONENTS:
                raise CFBError('CFB cumulative path component limit exceeded')
            # Index each local name once. Re-encoding every ancestor for every
            # leaf would multiply memory use by attacker-controlled depth.
            key = (parent_id, _name_key(ent.name))
            pending.extend(((ent.right, parent, parent_id), (ent.left, parent, parent_id)))
            if key in self._lookup:
                self._metadata_defect('CFB duplicate directory name omitted')
                continue
            self._paths[path] = index
            self._lookup[key] = index
            if ent.kind == STGTY_STORAGE:
                pending.append((ent.child, path, index))
            elif ent.child != NOSTREAM:
                self._metadata_defect('CFB stream directory entry has unused children')

    @staticmethod
    def _check_size(size):
        if size > MAX_STREAM_SIZE:
            raise CFBError('CFB stream size limit exceeded')

    def _mini_offset(self, sid):
        position = sid * 64
        sector, within = divmod(position, self.sectorsize)
        if position >= self._root_size or sector >= len(self._root_chain):
            raise CFBError('CFB mini sector outside root stream')
        return (self._root_chain[sector] + 1) * self.sectorsize + within

    def _find(self, path):
        self._check_open()
        parts = path.split('/') if isinstance(path, str) else list(path)
        if not parts:
            raise CFBError('file not found')
        index = 0
        for part in parts:
            key = (index, _name_key(part))
            if key not in self._lookup:
                raise CFBError('file not found')
            index = self._lookup[key]
        return index

    def listdir(self, streams=True, storages=False):
        self._check_open()
        return [list(path) for path, index in sorted(self._paths.items())
                if (streams and self._entries[index].kind == STGTY_STREAM)
                or (storages and self._entries[index].kind == STGTY_STORAGE)]

    def exists(self, path):
        try:
            self._find(path)
            return True
        except CFBError:
            return False

    def get_type(self, path):
        try:
            return self._entries[self._find(path)].kind
        except CFBError:
            return False

    def get_size(self, path):
        ent = self._entries[self._find(path)]
        if ent.kind != STGTY_STREAM:
            raise OSError('this file is not a stream')
        return ent.size

    def openstream(self, path):
        # Probing an absent optional stream is not evidence of lost content.
        index = self._find(path)
        previous_path = self._issue_path
        self._issue_path = path if isinstance(path, str) else '/'.join(path)
        try:
            return self._openstream(index)
        except CFBError:
            self._record_recovery('stream read failed')
            raise
        finally:
            self._issue_path = previous_path

    def _openstream(self, index):
        ent = self._entries[index]
        if ent.kind != STGTY_STREAM:
            raise OSError('this file is not a stream')
        self._check_size(ent.size)
        mini = ent.size < 4096
        if mini and ent.size:
            self._load_mini_stream()
        if index not in self._chains:
            sector = 64 if mini else self.sectorsize
            chain = self._chain(ent.start, self._minifat if mini else self._fat,
                                index, count=(ent.size + sector - 1) // sector,
                                mini=mini) if ent.size else array('I')
            try:
                size = self._extent(chain, ent.size, mini)
            except Exception:
                owners = self._mini_owners if mini else self._owners
                for sid in chain:
                    if owners[sid] == index:
                        owners[sid] = -1
                raise
            self._chains[index], self._sizes[index] = chain, size
        return _Stream(self, self._chains[index], self._sizes[index], mini)

    def close(self):
        if not self._closed:
            self._closed = True
            if self._owned and self._fp is not None:
                self._fp.close()

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *exc):
        self.close()


def isOleFile(filename=None, data=None):
    """Signature probe, not validation; preserve an external stream's position."""
    if data is not None:
        return bytes(data[:8]) == MAGIC
    if isinstance(filename, (bytes, bytearray, memoryview)):
        return bytes(filename[:8]) == MAGIC
    if isinstance(filename, (str, os.PathLike)):
        with open(filename, 'rb') as stream:
            return stream.read(8) == MAGIC
    position = filename.tell()
    try:
        filename.seek(0)
        return filename.read(8) == MAGIC
    finally:
        filename.seek(position)
