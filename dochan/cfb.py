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
    corruption affecting traversal/allocation is always a CFBError.
    """

    def __init__(self, filename, raise_defects=40):
        self._closed = False
        self._owned = False
        self._lock = threading.RLock()
        self._chains = {}
        self._raise_defects = raise_defects
        self.parsing_issues = []
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
        """Record bounded, non-addressing metadata deviations in legacy files."""
        if self._raise_defects <= DEFECT_INCORRECT:
            raise CFBError(message)
        if message not in self.parsing_issues:
            self.parsing_issues.append(message)

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
        if count is not None and count > bound:
            raise CFBError('CFB stream size exceeds available sectors')
        if limit is None:
            limit = bound
        while sid != ENDOFCHAIN:
            if len(result) >= limit:
                raise CFBError('CFB chain length limit or cycle')
            if not 0 <= sid < min(bound, len(table)):
                raise CFBError('CFB chain sector outside allocation table')
            self._claim(sid, owner, mini)
            result.append(sid)
            sid = table[sid]
        if count is not None and len(result) != count:
            if owner == 0 and len(result) > count:
                # Root mini streams in public legacy files can retain spare
                # sectors. Walk/claim the entire chain, expose only root.size.
                self._metadata_defect('CFB root mini stream has excess allocated sectors')
            else:
                raise CFBError('CFB chain length does not match declared size')
        return result

    def _parse(self):
        header = self._read_at(0, 512)
        if header[:8] != MAGIC:
            raise CFBError('not an OLE2 structured storage file')
        self.major_version = struct.unpack_from('<H', header, 26)[0]
        byte_order, shift, mini_shift = struct.unpack_from('<3H', header, 28)
        if self.major_version not in (3, 4) or shift != {3: 9, 4: 12}.get(self.major_version):
            raise CFBError('CFB invalid version or sector size')
        if byte_order != 0xfffe or mini_shift != 6 or _u32(header, 56) != 4096:
            raise CFBError('CFB invalid byte order, mini sector size, or cutoff')
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
        if not 1 <= fat_count <= self._sector_count or max(mini_count, dif_count) > self._sector_count:
            raise CFBError('CFB allocation table count limit')
        fat_ids = [sid for sid in struct.unpack_from('<109I', header, 76) if sid != FREESECT]
        dif_ids = []
        sid = first_dif
        for _ in range(dif_count):
            self._claim(sid, -2)
            dif_ids.append(sid)
            words = _words(self._sector(sid))
            fat_ids.extend(value for value in words[:-1] if value != FREESECT)
            if len(fat_ids) > fat_count:
                raise CFBError('CFB excess DIFAT FAT entries')
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
        for sid in fat_ids:
            self._claim(sid, -3)
            self._fat.extend(_words(self._sector(sid)))
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
            self._minifat.extend(_words(self._sector(sid)))
        self._check_size(self.root.size)
        self._root_chain = self._chain(self.root.start, self._fat, 0,
                                       count=(self.root.size + self.sectorsize - 1) // self.sectorsize) if self.root.size else array('I')
        self._mini_owners = array('i', [-1]) * ((self.root.size + 63) // 64)

    def _entry(self, index):
        if not 0 <= index < self._entry_count:
            raise CFBError('CFB directory entry outside directory stream')
        if index in self._entries:
            return self._entries[index]
        sector, offset = divmod(index * 128, self.sectorsize)
        data = self._read_at((self._directory[sector] + 1) * self.sectorsize + offset, 128)
        length, kind, color, left, right, child = struct.unpack_from('<HBBIII', data, 64)
        if kind not in (1, 2, 5) or color not in (0, 1):
            raise CFBError('CFB invalid live directory entry type or color')
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
        start = _u32(data, 116)
        size = _u32(data, 120) if self.major_version == 3 else struct.unpack_from('<Q', data, 120)[0]
        result = _Entry(name, kind, left, right, child, start, size)
        self._entries[index] = result
        return result

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
            ent = self._entry(index)
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
            if key in self._lookup:
                raise CFBError('CFB duplicate directory name')
            self._paths[path] = index
            self._lookup[key] = index
            pending.extend(((ent.right, parent, parent_id), (ent.left, parent, parent_id)))
            if ent.kind == STGTY_STORAGE:
                pending.append((ent.child, path, index))
            elif ent.child != NOSTREAM:
                raise CFBError('CFB stream directory entry has children')

    @staticmethod
    def _check_size(size):
        if size > MAX_STREAM_SIZE:
            raise CFBError('CFB stream size limit exceeded')

    def _mini_offset(self, sid):
        position = sid * 64
        sector, within = divmod(position, self.sectorsize)
        if position + 64 > self.root.size or sector >= len(self._root_chain):
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
            raise CFBError('object is not an OLE stream')
        return ent.size

    def openstream(self, path):
        index = self._find(path)
        ent = self._entries[index]
        if ent.kind != STGTY_STREAM:
            raise CFBError('object is not an OLE stream')
        self._check_size(ent.size)
        mini = ent.size < 4096
        if index not in self._chains:
            sector = 64 if mini else self.sectorsize
            chain = self._chain(ent.start, self._minifat if mini else self._fat,
                                index, count=(ent.size + sector - 1) // sector,
                                mini=mini) if ent.size else array('I')
            self._chains[index] = chain
        return _Stream(self, self._chains[index], ent.size, mini)

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
