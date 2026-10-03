"""Bounded HWPX ODF-style manifest decryption for opening passwords."""
import base64
import binascii
import hashlib
import hmac
import zlib

from ..crypto.ooxml import MAX_SPIN_COUNT, _aes
from ..utils import safe_xml as etree


NS = 'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0'
_TAG = '{' + NS + '}'
MAX_MANIFEST_SIZE = 1024 * 1024
MAX_ENCRYPTED_PARTS = 1000
MAX_ENCRYPTED_TOTAL = 512 * 1024 * 1024
MAX_AES_BYTES = 16 * 1024 * 1024
AES_CHUNK = 16 * 1024


class HWPXCryptoError(ValueError):
    """A static, password-free public diagnostic."""


def _unsupported():
    return HWPXCryptoError('ERR: 지원하지 않는 HWPX 암호화 또는 손상된 암호화 데이터')


def _binary(value, size):
    if not value or len(value) > 4 * ((size + 2) // 3):
        raise _unsupported()
    try:
        result = base64.b64decode(value or '', validate=True)
    except (ValueError, binascii.Error):
        raise _unsupported()
    if len(result) != size:
        raise _unsupported()
    return result


def _attr(node, name, default=None):
    value = node.get(name)
    return node.get(_TAG + name, default) if value is None else value


def _work_limit():
    return HWPXCryptoError('ERR: 암호화된 HWPX 문서 — 암호 반복 작업량 상한 초과')


class AESBudget:
    def __init__(self):
        self.remaining = MAX_AES_BYTES

    def reserve_bytes(self, count):
        if count > self.remaining:
            raise HWPXCryptoError('ERR: 암호화된 HWPX 문서 — AES 작업량 상한 초과')
        self.remaining -= count


def read_encryption_manifest(data, names, limits):
    """Return encrypted part metadata; reject unknown methods before reading XML."""
    if len(data) > MAX_MANIFEST_SIZE:
        raise _unsupported()
    try:
        root = etree.fromstring(data)
    except Exception:
        raise _unsupported()
    if root.tag != _TAG + 'manifest':
        raise _unsupported()
    encrypted = {}
    total = 0
    key_work = {}
    for entry in root:
        if entry.tag != _TAG + 'file-entry':
            continue
        node = entry.find(_TAG + 'encryption-data')
        if node is None:
            continue
        name = _attr(entry, 'full-path')
        if (not name or name not in names or name in encrypted
                or name in ('mimetype', 'META-INF/manifest.xml')):
            raise _unsupported()
        if len(encrypted) >= MAX_ENCRYPTED_PARTS:
            raise _unsupported()
        algorithm = node.find(_TAG + 'algorithm')
        derivation = node.find(_TAG + 'key-derivation')
        start = node.find(_TAG + 'start-key-generation')
        if algorithm is None or derivation is None or start is None:
            raise _unsupported()
        if (_attr(node, 'checksum-type') != NS + '#sha256-1k'
                or _attr(algorithm, 'algorithm-name') != 'http://www.w3.org/2001/04/xmlenc#aes256-cbc'
                or _attr(derivation, 'key-derivation-name') != NS + '#pbkdf2'
                or _attr(derivation, 'key-size') != '32'
                or _attr(start, 'start-key-generation-name') != 'http://www.w3.org/2000/09/xmldsig#sha256'
                or _attr(start, 'key-size') != '32'):
            raise _unsupported()
        count_text = _attr(derivation, 'iteration-count', '')
        size_text = _attr(entry, 'size', '')
        if not (1 <= len(count_text) <= 10 and 1 <= len(size_text) <= 10):
            raise _unsupported()
        try:
            count = int(count_text)
            size = int(size_text)
        except ValueError:
            raise _unsupported()
        limit = limits(name)
        if count < 1 or count > MAX_SPIN_COUNT:
            raise _work_limit()
        if size < 0 or size > limit:
            raise _unsupported()
        total += size
        if total > MAX_ENCRYPTED_TOTAL:
            raise _unsupported()
        iv = _binary(_attr(algorithm, 'initialisation-vector'), 16)
        salt = _binary(_attr(derivation, 'salt'), 16)
        checksum = _binary(_attr(node, 'checksum'), 32)
        key_work[(salt, count)] = count
        if sum(key_work.values()) > MAX_SPIN_COUNT:
            raise _work_limit()
        encrypted[name] = (iv, salt, checksum, count, size)
    return encrypted


def decrypt_part(ciphertext, metadata, password, max_size, budget, key_cache=None,
                 aes_budget=None):
    """AES-CBC -> raw DEFLATE; checksum is SHA-256 of first 1 KiB of plaintext."""
    iv, salt, checksum, count, size = metadata
    if (not ciphertext or len(ciphertext) % 16
            or len(ciphertext) > max_size + 16 or size > max_size):
        raise _unsupported()
    cache_key = (salt, count)
    key = key_cache.get(cache_key) if key_cache is not None else None
    if key is None:
        if budget[0] < count:
            raise _work_limit()
        budget[0] -= count
        try:
            start = hashlib.sha256(password.encode('utf-8')).digest()
        except (AttributeError, UnicodeError):
            raise _unsupported()
        key = hashlib.pbkdf2_hmac('sha1', start, salt, count, 32)
        if key_cache is not None:
            key_cache[cache_key] = key
    stream = zlib.decompressobj(-15)
    chunks = []
    plain_size = 0
    prefix = bytearray()
    checked = False
    limit = min(size, max_size)
    try:
        for offset in range(0, len(ciphertext), AES_CHUNK):
            block = ciphertext[offset:offset + AES_CHUNK]
            compressed = _aes(key, block, iv, budget=aes_budget)
            iv = block[-16:]
            remaining = limit - plain_size
            if remaining < 0:
                raise ValueError('plaintext exceeds limit')
            piece = stream.decompress(compressed, remaining + 1)
            if len(piece) > remaining or stream.unconsumed_tail:
                raise ValueError('plaintext exceeds limit')
            chunks.append(piece)
            plain_size += len(piece)
            if len(prefix) < 1024:
                prefix.extend(piece[:1024 - len(prefix)])
            if not checked and len(prefix) >= min(size, 1024):
                if not hmac.compare_digest(hashlib.sha256(prefix).digest(), checksum):
                    raise ValueError('checksum mismatch')
                checked = True
            if stream.eof:
                break
    except HWPXCryptoError:
        raise
    except (ValueError, zlib.error):
        raise HWPXCryptoError('ERR: 암호화된 HWPX 문서 — 암호가 틀리거나 데이터가 손상됨')
    if not stream.eof or plain_size != size or not checked:
        raise HWPXCryptoError('ERR: 암호화된 HWPX 문서 — 암호가 틀리거나 데이터가 손상됨')
    return b''.join(chunks)
