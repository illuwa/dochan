"""Synthetic MS-OFFCRYPTO containers; no corpus dependency."""
import base64
import hashlib
import hmac
import io
import struct
import zipfile
from lxml import etree as ET

import pytest

from dochan.crypto.ooxml import decrypt_ooxml
from dochan.utils.aes import _encrypt_block, _key_expansion


class Streams:
    def __init__(self, info, package):
        self.streams = {"EncryptionInfo": info, "EncryptedPackage": package}

    def openstream(self, name):
        return io.BytesIO(self.streams[name])

    def get_size(self, name):
        return len(self.streams[name])


def _encrypt(key, data, iv=None):
    schedule = _key_expansion(key)
    out = bytearray()
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        if iv is not None:
            block = bytes(a ^ b for a, b in zip(block, iv))
        block = _encrypt_block(block, schedule, len(key) // 4 + 6)
        out.extend(block)
        if iv is not None:
            iv = block
    return bytes(out)


def _pad(data):
    return data + b"\0" * (-len(data) % 16)


def _zip():
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("word/document.xml", b"<document>synthetic office payload</document>" * 100)
    return target.getvalue()


def _standard(password="secret", bits=128):
    payload = _zip()
    salt = bytes(range(16))
    digest = hashlib.sha1(salt + password.encode("utf-16le")).digest()
    for i in range(50000):
        digest = hashlib.sha1(struct.pack("<I", i) + digest).digest()
    digest = hashlib.sha1(digest + b"\0" * 4).digest()
    wide = digest + b"\0" * (64 - len(digest))
    key = (hashlib.sha1(bytes(x ^ 0x36 for x in wide)).digest()
           + hashlib.sha1(bytes(x ^ 0x5C for x in wide)).digest())[:bits // 8]
    header = struct.pack("<8I", 0x24, 0, {128: 0x660e, 192: 0x660f, 256: 0x6610}[bits], 0x8004, bits, 0x18, 0, 0)
    verifier = b"fixed verifier!!"
    info = struct.pack("<HHII", 4, 2, 0x24, len(header)) + header
    info += struct.pack("<I", 16) + salt + _encrypt(key, verifier)
    info += struct.pack("<I", 20) + _encrypt(key, _pad(hashlib.sha1(verifier).digest()))
    package = struct.pack("<Q", len(payload)) + _encrypt(key, _pad(payload))
    return Streams(info, package), payload


def _agile(password="secret", bits=256, algorithm="sha512"):
    payload = _zip()
    salt = bytes(range(16))
    data_salt = bytes(range(16, 32))
    secret = bytes(range(bits // 8))
    size = hashlib.new(algorithm).digest_size
    def digest(data):
        return hashlib.new(algorithm, data).digest()

    h = digest(salt + password.encode("utf-16le"))
    for i in range(3):
        h = digest(struct.pack("<I", i) + h)
    def encrypt_password(block, value):
        key = (digest(h + bytes.fromhex(block)) + b"\x36" * 32)[:bits // 8]
        return _encrypt(key, _pad(value), salt)
    def enc_data(block, value):
        return _encrypt(secret, _pad(value), digest(data_salt + bytes.fromhex(block))[:16])
    ns = "http://schemas.microsoft.com/office/2006/encryption"
    pns = "http://schemas.microsoft.com/office/2006/keyEncryptor/password"
    attrs = dict(saltSize="16", blockSize="16", keyBits=str(bits), hashSize=str(size), cipherAlgorithm="AES", cipherChaining="ChainingModeCBC", hashAlgorithm=algorithm.upper())
    def b64(value):
        return base64.b64encode(value).decode()

    root = ET.Element("{" + ns + "}encryption")
    ET.SubElement(root, "{" + ns + "}keyData", dict(attrs, saltValue=b64(data_salt)))
    package = bytearray(struct.pack("<Q", len(payload)))
    for i, offset in enumerate(range(0, len(payload), 4096)):
        iv = digest(data_salt + struct.pack("<I", i))[:16]
        package.extend(_encrypt(secret, _pad(payload[offset:offset + 4096]), iv))
    mac_key = b"H" * size
    mac = hmac.new(mac_key, package, algorithm).digest()
    ET.SubElement(root, "{" + ns + "}dataIntegrity", encryptedHmacKey=b64(enc_data("5fb2ad010cb9e1f6", mac_key)), encryptedHmacValue=b64(enc_data("a0677f02b22c8433", mac)))
    keys = ET.SubElement(root, "{" + ns + "}keyEncryptors")
    key = ET.SubElement(keys, "{" + ns + "}keyEncryptor", uri=pns)
    verifier = b"fixed verifier!!"
    ET.SubElement(key, "{" + pns + "}encryptedKey", dict(attrs, spinCount="3", saltValue=b64(salt), encryptedVerifierHashInput=b64(encrypt_password("fea7d2763b4b9e79", verifier)), encryptedVerifierHashValue=b64(encrypt_password("d7aa0f6d3061344e", digest(verifier))), encryptedKeyValue=b64(encrypt_password("146e0be7abacd0d6", secret))))
    return Streams(struct.pack("<HHI", 4, 4, 0x40) + ET.tostring(root), bytes(package)), payload


@pytest.mark.parametrize("bits", [128, 192, 256])
def test_standard_aes_round_trip(bits):
    streams, expected = _standard(bits=bits)
    assert decrypt_ooxml(streams, "secret") == expected


@pytest.mark.parametrize("bits,algorithm", [(128, "sha1"), (192, "sha256"), (256, "sha512")])
def test_agile_segments_hashes_and_key_sizes(bits, algorithm):
    streams, expected = _agile(bits=bits, algorithm=algorithm)
    assert decrypt_ooxml(streams, "secret") == expected


@pytest.mark.parametrize("factory", [_standard, _agile])
@pytest.mark.parametrize("password", [None, "wrong-private-password"])
def test_wrong_or_missing_password_is_clear_and_redacted(factory, password):
    streams, _ = factory()
    with pytest.raises(ValueError, match="ERR: 암호화된 문서") as exc:
        decrypt_ooxml(streams, password)
    assert "wrong-private-password" not in str(exc.value)


@pytest.mark.parametrize("factory", [_standard, _agile])
@pytest.mark.parametrize("password", ["", "VelvetSweatshop"])
def test_empty_and_default_password_without_explicit_password(factory, password):
    streams, expected = factory(password=password)
    assert decrypt_ooxml(streams) == expected


def test_agile_rejects_tampered_hmac_package():
    streams, _ = _agile()
    package = bytearray(streams.streams["EncryptedPackage"])
    package[-17] ^= 1
    streams.streams["EncryptedPackage"] = bytes(package)
    with pytest.raises(ValueError, match="무결성"):
        decrypt_ooxml(streams, "secret")


def test_agile_rejects_spin_count_before_hashing():
    streams, _ = _agile()
    streams.streams["EncryptionInfo"] = streams.streams["EncryptionInfo"].replace(b'spinCount="3"', b'spinCount="999999999"')
    with pytest.raises(ValueError, match="상한"):
        decrypt_ooxml(streams, "secret")


def test_rejects_package_size_before_stream_read():
    streams, _ = _agile()
    streams.get_size = lambda name: 2 ** 40
    streams.openstream = lambda name: pytest.fail("oversized stream read")
    with pytest.raises(ValueError, match="상한"):
        decrypt_ooxml(streams, "secret")


def test_rejects_xml_entities():
    info = struct.pack("<HHI", 4, 4, 0x40) + b'<!DOCTYPE a [<!ENTITY e "secret">]><a>&e;</a>'
    with pytest.raises(ValueError, match="ERR: 암호화된 문서"):
        decrypt_ooxml(Streams(info, b"\0" * 24), "secret")


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_rejects_non_utf8_xml_entities(encoding):
    streams, _ = _agile()
    info = streams.streams["EncryptionInfo"]
    xml = info[8:].decode("utf-8").replace('spinCount="3"', 'spinCount="&e;"')
    xml = '<!DOCTYPE a [<!ENTITY e "3">]>' + xml
    streams.streams["EncryptionInfo"] = info[:8] + xml.encode(encoding)
    with pytest.raises(ValueError, match="ERR: 암호화된 문서"):
        decrypt_ooxml(streams, "secret")
