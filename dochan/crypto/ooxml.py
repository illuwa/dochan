"""Native OOXML Standard/Agile decryption (MS-OFFCRYPTO 2.3.4, 2.3.5).

Only AES Standard and AES-CBC Agile password key encryptors are accepted.
The returned ZIP stays in memory and is parsed by the existing OOXML readers.
"""
import base64
import binascii
import hashlib
import hmac
import struct
import time
from typing import Optional
from lxml import etree as ET

from ..utils.aes import _decrypt_block, _key_expansion

# Conservative per-document limits, including automatic password attempts.
MAX_PACKAGE_SIZE = 16 * 1024 * 1024
MAX_PASSWORD_CANDIDATES = 2
MAX_CRYPTO_SECONDS = 20.0
MAX_INFO_SIZE = 64 * 1024
MAX_SPIN_COUNT = 1000000
_NS = "http://schemas.microsoft.com/office/2006/encryption"
_PNS = "http://schemas.microsoft.com/office/2006/keyEncryptor/password"


class OOXMLCryptoError(ValueError):
    """Static diagnostics safe for the public reader to display."""


class _WorkBudget:
    def __init__(self):
        self.deadline = time.monotonic() + MAX_CRYPTO_SECONDS
        self.hashes = MAX_SPIN_COUNT
        self.bytes = MAX_PACKAGE_SIZE + 16384

    def check(self):
        if time.monotonic() > self.deadline:
            raise _error("복호화 작업 시간 상한을 초과했습니다.")

    def reserve_hashes(self, count):
        self.hashes -= count
        if self.hashes < 0:
            raise _error("문서당 암호 반복 작업량 상한을 초과했습니다.")
        self.check()

    def reserve_bytes(self, count):
        self.bytes -= count
        if self.bytes < 0:
            raise _error("문서당 AES 작업량 상한을 초과했습니다.")
        self.check()


class _PasswordMismatch(ValueError):
    pass


def _error(reason):
    return OOXMLCryptoError("ERR: 암호화된 문서 — " + reason)


def _aes(key, data, iv=None, *, output=None, budget=None, schedule=None):
    if len(key) not in (16, 24, 32) or not data or len(data) % 16:
        raise _error("잘못된 AES 블록입니다.")
    if iv is not None and len(iv) != 16:
        raise _error("잘못된 초기화 벡터입니다.")
    if budget is not None:
        budget.reserve_bytes(len(data))
    if schedule is None:
        schedule = _key_expansion(key)
    rounds = len(key) // 4 + 6
    own_output = output is None
    result = bytearray(len(data)) if own_output else output
    data = memoryview(data)
    for offset in range(0, len(data), 16):
        if budget is not None and offset % 4096 == 0:
            budget.check()
        block = data[offset:offset + 16]
        plain = _decrypt_block(block, schedule, rounds)
        if iv is not None:
            plain = bytes(a ^ b for a, b in zip(plain, iv))
            iv = block
        count = min(16, len(result) - offset)
        if count > 0:
            result[offset:offset + count] = plain[:count]
    return bytes(result) if own_output else None


def _read(ole, name, limit):
    if ole.get_size(name) > limit:
        raise _error("스트림 크기 상한을 초과했습니다.")
    with ole.openstream(name) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise _error("스트림 크기 상한을 초과했습니다.")
    return data


def _hash(name, data):
    return hashlib.new(name, data).digest()


def _password_hash(password, salt, algorithm, count, budget=None):
    if budget is not None:
        budget.reserve_hashes(count)
    digest = _hash(algorithm, salt + password.encode("utf-16le"))
    for index in range(count):
        if budget is not None and index % 1024 == 0:
            budget.check()
        digest = _hash(algorithm, struct.pack("<I", index) + digest)
    return digest


def _standard(info, package, password, budget=None):
    if len(info) < 12:
        raise _error("Standard 헤더가 잘렸습니다.")
    flags, size = struct.unpack_from("<II", info, 4)
    if size < 32 or size > len(info) - 12:
        raise _error("Standard 헤더 길이가 잘못되었습니다.")
    fields = struct.unpack_from("<8I", info, 12)
    algorithm, hash_id, bits = fields[2:5]
    if (algorithm, bits) not in ((0x660e, 128), (0x660f, 192), (0x6610, 256)) or hash_id != 0x8004:
        raise _error("지원하지 않는 Standard 암호 알고리즘입니다.")
    if not flags & 0x20 or not fields[0] & 0x20:
        raise _error("Standard AES 플래그가 잘못되었습니다.")
    offset = 12 + size
    if len(info) < offset + 72:
        raise _error("Standard 검증 정보가 잘렸습니다.")
    salt_size = struct.unpack_from("<I", info, offset)[0]
    hash_size = struct.unpack_from("<I", info, offset + 36)[0]
    if salt_size != 16 or hash_size != 20:
        raise _error("Standard 검증 정보 크기가 잘못되었습니다.")
    salt = info[offset + 4:offset + 20]
    digest = _password_hash(password, salt, "sha1", 50000, budget)
    digest = hashlib.sha1(digest + b"\0" * 4).digest()
    wide = digest.ljust(64, b"\0")
    key = (hashlib.sha1(bytes(b ^ 0x36 for b in wide)).digest()
           + hashlib.sha1(bytes(b ^ 0x5c for b in wide)).digest())[:bits // 8]
    verifier = _aes(key, info[offset + 20:offset + 36], budget=budget)
    expected = _aes(key, info[offset + 40:offset + 72], budget=budget)[:20]
    if not hmac.compare_digest(hashlib.sha1(verifier).digest(), expected):
        raise _PasswordMismatch()
    result = bytearray(struct.unpack_from("<Q", package)[0])
    _aes(key, memoryview(package)[8:], output=result, budget=budget)
    return bytes(result)


def _binary(element, attribute):
    value = element.attrib[attribute]
    if len(value) > 1024:
        raise _error("암호 매개변수 크기 상한을 초과했습니다.")
    return base64.b64decode(value, validate=True)


def _parameters(element):
    if element is None:
        raise _error("Agile 암호 매개변수가 없습니다.")
    attrs = element.attrib
    algorithm = attrs["hashAlgorithm"].lower().replace("-", "")
    if algorithm not in ("sha1", "sha256", "sha384", "sha512"):
        raise _error("지원하지 않는 Agile 해시 알고리즘입니다.")
    bits = int(attrs["keyBits"])
    if attrs["cipherAlgorithm"] != "AES" or attrs["cipherChaining"] != "ChainingModeCBC" or bits not in (128, 192, 256):
        raise _error("지원하지 않는 Agile 암호 알고리즘입니다.")
    salt = _binary(element, "saltValue")
    if int(attrs["blockSize"]) != 16 or int(attrs["saltSize"]) != len(salt) or len(salt) != 16:
        raise _error("Agile 블록 또는 salt 크기가 잘못되었습니다.")
    if int(attrs["hashSize"]) != hashlib.new(algorithm).digest_size:
        raise _error("Agile 해시 크기가 잘못되었습니다.")
    return algorithm, bits // 8, salt


def _agile(info, package, password, budget=None):
    # MS-OFFCRYPTO specifies UTF-8; decoding first also closes UTF-16/32
    # entity-declaration bypasses of byte-only DOCTYPE checks.
    xml = info[8:].decode("utf-8-sig")
    if "\0" in xml or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise _error("Agile XML 선언이 허용되지 않습니다.")
    parser = ET.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    root = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml, parser)
    if root.tag != "{" + _NS + "}encryption":
        raise _error("Agile XML 루트가 잘못되었습니다.")
    key_data = root.find("{" + _NS + "}keyData")
    key = root.find("{" + _NS + "}keyEncryptors/{" + _NS + "}keyEncryptor/{" + _PNS + "}encryptedKey")
    data_algorithm, data_key_size, data_salt = _parameters(key_data)
    algorithm, key_size, salt = _parameters(key)
    count = int(key.attrib["spinCount"])
    if count < 0 or count > MAX_SPIN_COUNT:
        raise _error("암호 반복 횟수 상한을 초과했습니다.")
    digest = _password_hash(password, salt, algorithm, count, budget)

    def unwrap(block, attr):
        wrapping_key = _hash(algorithm, digest + bytes.fromhex(block)).ljust(key_size, b"\x36")[:key_size]
        return _aes(wrapping_key, _binary(key, attr), salt, budget=budget)

    verifier = unwrap("fea7d2763b4b9e79", "encryptedVerifierHashInput")[:16]
    hash_size = hashlib.new(algorithm).digest_size
    expected = unwrap("d7aa0f6d3061344e", "encryptedVerifierHashValue")[:hash_size]
    if not hmac.compare_digest(_hash(algorithm, verifier), expected):
        raise _PasswordMismatch()
    secret = unwrap("146e0be7abacd0d6", "encryptedKeyValue")[:data_key_size]
    integrity = root.find("{" + _NS + "}dataIntegrity")
    if integrity is None:
        raise _error("Agile 무결성 정보가 없습니다.")
    mac_size = hashlib.new(data_algorithm).digest_size

    def unwrap_mac(block, attr):
        iv = _hash(data_algorithm, data_salt + bytes.fromhex(block)).ljust(16, b"\x36")[:16]
        return _aes(secret, _binary(integrity, attr), iv, budget=budget)[:mac_size]

    mac_key = unwrap_mac("5fb2ad010cb9e1f6", "encryptedHmacKey")
    expected_mac = unwrap_mac("a0677f02b22c8433", "encryptedHmacValue")
    actual_mac = hmac.new(mac_key, package, data_algorithm).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        raise _error("Agile 무결성 HMAC 검증에 실패했습니다.")
    result = bytearray(struct.unpack_from("<Q", package)[0])
    destination = memoryview(result)
    source = memoryview(package)
    schedule = _key_expansion(secret)
    for index, offset in enumerate(range(8, len(package), 4096)):
        iv = _hash(data_algorithm, data_salt + struct.pack("<I", index)).ljust(16, b"\x36")[:16]
        _aes(secret, source[offset:offset + 4096], iv,
             output=destination[offset - 8:offset - 8 + 4096], budget=budget,
             schedule=schedule)
    return bytes(result)


def decrypt_ooxml(ole, password: Optional[str] = None) -> bytes:
    """Decrypt CFB EncryptionInfo/EncryptedPackage; never include passwords in errors.

    Missing passwords try only the empty string and Office's default password.
    Metadata, encrypted payload, declared plaintext size and KDF work are bounded.
    """
    try:
        budget = _WorkBudget()
        info = _read(ole, "EncryptionInfo", MAX_INFO_SIZE)
        package = _read(ole, "EncryptedPackage", MAX_PACKAGE_SIZE + 24)
        if len(info) < 8 or len(package) < 24:
            raise _error("암호 스트림이 잘렸습니다.")
        size = struct.unpack_from("<Q", package)[0]
        if size > MAX_PACKAGE_SIZE:
            raise _error("복호화 크기 상한을 초과했습니다.")
        if size == 0 or len(package) - 8 != (size + 15) // 16 * 16:
            raise _error("암호 패키지 길이가 잘못되었습니다.")
        version = struct.unpack_from("<HH", info)
        if version in ((2, 2), (3, 2), (4, 2)):
            decrypt = _standard
        elif version == (4, 4):
            decrypt = _agile
        else:
            raise _error("지원하지 않는 Office 암호 버전입니다.")
        candidates = ("", "VelvetSweatshop") if password is None else (password,)
        if len(candidates) > MAX_PASSWORD_CANDIDATES:
            raise _error("암호 후보 수 상한을 초과했습니다.")
        for candidate in candidates:
            if not isinstance(candidate, str) or len(candidate) > 255:
                raise _error("암호 형식 또는 길이가 잘못되었습니다.")
            try:
                plain = decrypt(info, package, candidate, budget)
            except _PasswordMismatch:
                continue
            if not plain.startswith(b"PK\x03\x04"):
                raise _error("복호화된 패키지가 ZIP 형식이 아닙니다.")
            return plain
        raise _error("암호가 필요하거나 암호가 올바르지 않습니다.")
    except (KeyError, TypeError, struct.error, ET.XMLSyntaxError, binascii.Error, UnicodeError, OSError) as exc:
        raise _error("암호 정보가 손상되었습니다.") from None
    except ValueError as exc:
        if str(exc).startswith("ERR: 암호화된 문서"):
            raise
        raise _error("암호 정보가 손상되었습니다.") from None
