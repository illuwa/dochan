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
    for entry in root:
        if entry.tag != _TAG + 'file-entry':
            continue
        node = entry.find(_TAG + 'encryption-data')
        if node is None:
            continue
        name = entry.get(_TAG + 'full-path') or entry.get('full-path')
        if not name or name not in names or name in encrypted:
            raise _unsupported()
        if len(encrypted) >= MAX_ENCRYPTED_PARTS:
            raise _unsupported()
        algorithm = node.find(_TAG + 'algorithm')
        derivation = node.find(_TAG + 'key-derivation')
        start = node.find(_TAG + 'start-key-generation')
        if algorithm is None or derivation is None or start is None:
            raise _unsupported()
        if (node.get('checksum-type') != NS + '#sha256-1k'
                or algorithm.get('algorithm-name') != 'http://www.w3.org/2001/04/xmlenc#aes256-cbc'
                or derivation.get('key-derivation-name') != NS + '#pbkdf2'
                or derivation.get('key-size') != '32'
                or start.get('start-key-generation-name') != 'http://www.w3.org/2000/09/xmldsig#sha256'
                or start.get('key-size') != '32'):
            raise _unsupported()
        count_text = derivation.get('iteration-count', '')
        size_text = entry.get('size', '')
        if not (1 <= len(count_text) <= 10 and 1 <= len(size_text) <= 10):
            raise _unsupported()
        try:
            count = int(count_text)
            size = int(size_text)
        except ValueError:
            raise _unsupported()
        limit = limits(name)
        if count < 1 or count > MAX_SPIN_COUNT or size < 0 or size > limit:
            raise _unsupported()
        total += size
        if total > MAX_ENCRYPTED_TOTAL:
            raise _unsupported()
        encrypted[name] = (
            _binary(algorithm.get('initialisation-vector'), 16),
            _binary(derivation.get('salt'), 16),
            _binary(node.get('checksum'), 32), count, size)
    return encrypted


def decrypt_part(ciphertext, metadata, password, max_size, budget):
    """AES-CBC -> raw DEFLATE; checksum is SHA-256 of first 1 KiB of plaintext."""
    iv, salt, checksum, count, size = metadata
    if (not ciphertext or len(ciphertext) % 16
            or len(ciphertext) > max_size + 16 or size > max_size):
        raise _unsupported()
    if budget[0] < count:
        raise _unsupported()
    budget[0] -= count
    try:
        start = hashlib.sha256(password.encode('utf-8')).digest()
    except (AttributeError, UnicodeError):
        raise _unsupported()
    key = hashlib.pbkdf2_hmac('sha1', start, salt, count, 32)
    try:
        compressed = _aes(key, ciphertext, iv)
        stream = zlib.decompressobj(-15)
        plain = stream.decompress(compressed, max_size + 1)
        plain += stream.flush(max_size + 1 - len(plain))
    except (ValueError, zlib.error):
        raise HWPXCryptoError('ERR: 암호화된 HWPX 문서 — 암호가 틀리거나 데이터가 손상됨')
    if not stream.eof or len(plain) != size:
        raise HWPXCryptoError('ERR: 암호화된 HWPX 문서 — 암호가 틀리거나 데이터가 손상됨')
    if not hmac.compare_digest(hashlib.sha256(plain[:1024]).digest(), checksum):
        raise HWPXCryptoError('ERR: 암호화된 HWPX 문서 — 암호가 틀리거나 데이터가 손상됨')
    return plain
