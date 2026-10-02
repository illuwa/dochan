"""Bounded [MS-PPT] CryptSession10Container and persistent-object decryption.

The unencrypted CurrentUserAtom locates UserEditAtom and PersistDirectoryAtom.
[MS-OFFCRYPTO] RC4 CryptoAPI uses the persist ID as the block number, resetting
RC4 at each object. Picture records instead use block zero for each field.
"""
import struct
from typing import Optional, Tuple

from ..utils.bounded_io import MAX_OLE_STREAM_SIZE

MAX_EDITS = 4096
MAX_OBJECTS = 100000
ENCRYPTED_TOKEN = 0xF3D1C4DF
# [MS-OFFCRYPTO] 2.4.2.3: encrypted presentations without a user-supplied
# opening password use these specified characters (UTF-8 hex in the spec).
DEFAULT_POWERPOINT_PASSWORD = '/01Hannes Ruescher/01'


def _fail():
    return ValueError('암호화된 문서 PPT: 암호가 없거나 올바르지 않거나 암호화 구조가 손상되었습니다')


def _record(data, offset, types):
    if offset < 0 or offset + 8 > len(data):
        raise _fail()
    _, kind, size = struct.unpack_from('<HHI', data, offset)
    if kind not in types or size > len(data) - offset - 8:
        raise _fail()
    return data[offset + 8:offset + 8 + size]


def is_encrypted_presentation(current_user: bytes) -> bool:
    return len(current_user) >= 16 and struct.unpack_from('<I', current_user, 12)[0] == ENCRYPTED_TOKEN


def _directory(data, current_user):
    user = _record(current_user, 0, {4086})
    if len(user) < 20:
        raise _fail()
    offset = struct.unpack_from('<I', user, 8)[0]
    visited = set()
    entries = {}
    encryption_id = None
    work = 0
    for _ in range(MAX_EDITS):
        if offset in visited:
            raise _fail()
        visited.add(offset)
        edit = _record(data, offset, {4085})
        if len(edit) < 28:
            raise _fail()
        if encryption_id is None:
            if len(edit) < 32:
                raise _fail()
            encryption_id = struct.unpack_from('<I', edit, 28)[0]
        previous, directory = struct.unpack_from('<II', edit, 8)
        body = _record(data, directory, {6001, 6002})
        pos = 0
        while pos < len(body):
            if len(body) - pos < 4:
                raise _fail()
            packed = struct.unpack_from('<I', body, pos)[0]
            start, count = packed & 0xFFFFF, packed >> 20
            pos += 4
            work += count
            if not count or start + count > 0x100000 or count * 4 > len(body) - pos or work > MAX_OBJECTS:
                raise _fail()
            for i in range(count):
                entries.setdefault(start + i, struct.unpack_from('<I', body, pos + 4 * i)[0])
            pos += count * 4
        if not previous:
            if encryption_id not in entries:
                raise _fail()
            return entries, encryption_id
        offset = previous
    raise _fail()


def _decrypt_pictures(pictures, cipher):
    # [MS-ODRAW] BLIP record instances identify a second UID. Each encrypted
    # header, UID, tag/metafile-header and image-data field starts at RC4 byte 0.
    single_uid = {0xF01A: (0x3D4,), 0xF01B: (0x216,), 0xF01C: (0x542,),
                  0xF01D: (0x46A, 0x6E2), 0xF01E: (0x6E0,), 0xF01F: (0x7A8,),
                  0xF029: (0x6E4,), 0xF02A: (0x6E2,)}
    out = bytearray(pictures)
    pos = 0
    count = 0
    while pos < len(pictures):
        count += 1
        if count > MAX_OBJECTS or len(pictures) - pos < 8:
            raise _fail()
        header = cipher.crypt_block(pictures[pos:pos + 8], 0)
        options, kind, size = struct.unpack('<HHI', header)
        if kind not in single_uid or size > len(pictures) - pos - 8:
            raise _fail()
        out[pos:pos + 8] = header
        end = pos + 8 + size
        pos += 8
        instance = options >> 4
        uid_count = next((1 + instance - base for base in single_uid[kind]
                          if instance in (base, base + 1)), 0)
        if not uid_count:
            raise _fail()
        # A secondary UID is its own independently encrypted field.
        lengths = [16] * uid_count
        lengths.append(34 if kind in (0xF01A, 0xF01B, 0xF01C) else 1)
        for length in lengths:
            if pos + length > end:
                raise _fail()
            out[pos:pos + length] = cipher.crypt_block(pictures[pos:pos + length], 0)
            pos += length
        out[pos:end] = cipher.crypt_block(pictures[pos:end], 0)
        pos = end
    return bytes(out)


def decrypt_presentation(data: bytes, current_user: bytes, pictures: bytes,
                         password: Optional[str] = None) -> Tuple[bytes, bytes]:
    """Return plaintext streams without altering the unencrypted edit directory."""
    if not is_encrypted_presentation(current_user):
        return data, pictures
    if max(len(data), len(current_user), len(pictures)) > MAX_OLE_STREAM_SIZE:
        raise _fail()
    from .legacy import parse_rc4_header
    entries, encryption_id = _directory(data, current_user)
    info = _record(data, entries[encryption_id], {12052})
    candidates = ('', DEFAULT_POWERPOINT_PASSWORD) if password is None else (password,)
    for candidate in candidates:
        try:
            cipher = parse_rc4_header(info, candidate)
            break
        except (ValueError, TypeError, struct.error):
            continue
    else:
        raise _fail() from None
    out = bytearray(data)
    occupied = []
    total = 0
    for pid, offset in entries.items():
        if pid == encryption_id:
            continue
        if offset < 0 or offset + 8 > len(data):
            raise _fail()
        header = cipher.crypt_block(data[offset:offset + 8], pid)
        size = struct.unpack_from('<I', header, 4)[0] + 8
        total += size
        if size > len(data) - offset or total > MAX_OLE_STREAM_SIZE:
            raise _fail()
        occupied.append((offset, offset + size))
        out[offset:offset + size] = cipher.crypt_block(data[offset:offset + size], pid)
    occupied.sort()
    if any(a[1] > b[0] for a, b in zip(occupied, occupied[1:])):
        raise _fail()
    return bytes(out), _decrypt_pictures(pictures, cipher) if pictures else b''
