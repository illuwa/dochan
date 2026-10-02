"""Synthetic Office encryption records; no external corpus required."""
import hashlib
import struct

import pytest

from dochan.crypto.legacy import decrypt_doc_streams, decrypt_xls_workbook, parse_rc4_header
from dochan.pdf.crypto import rc4


def rc4_fixture(password="secret", cryptoapi=False):
    salt, verifier = bytes(range(16)), b"verification1234"
    if cryptoapi:
        base = hashlib.sha1(salt + password.encode("utf-16le")).digest()
        def key(block):
            return hashlib.sha1(base + struct.pack("<I", block)).digest()[:16]
        header = struct.pack("<HHII", 4, 2, 4, 32)
        header += struct.pack("<8I", 4, 0, 0x6801, 0x8004, 128, 1, 0, 0)
        encrypted = rc4(key(0), verifier + hashlib.sha1(verifier).digest())
        header += struct.pack("<I", 16) + salt + encrypted[:16]
        header += struct.pack("<I", 20) + encrypted[16:]
    else:
        first = hashlib.md5(password.encode("utf-16le")).digest()[:5]
        base = hashlib.md5((first + salt) * 16).digest()[:5]
        def key(block):
            return hashlib.md5(base + struct.pack("<I", block)).digest()
        header = struct.pack("<HH", 1, 1) + salt
        header += rc4(key(0), verifier + hashlib.md5(verifier).digest())
    return header, key


@pytest.mark.parametrize("cryptoapi", [False, True])
def test_rc4_password_verifier_and_independent_blocks(cryptoapi):
    header, key = rc4_fixture(cryptoapi=cryptoapi)
    context = parse_rc4_header(header, "secret")
    plaintext = bytes(range(256)) * 5
    encrypted = b"".join(rc4(key(i // 512), plaintext[i:i + 512])
                         for i in range(0, len(plaintext), 512))
    assert context.crypt(encrypted) == plaintext
    assert context.crypt_block(rc4(key(25), plaintext), 25) == plaintext
    with pytest.raises(ValueError, match="암호"):
        parse_rc4_header(header, "wrong")


def test_rc4_header_bounds():
    for data in (b"", b"\x04\x00\x02\x00", struct.pack("<HHII", 4, 2, 4, 2**32 - 1)):
        with pytest.raises(ValueError):
            parse_rc4_header(data, "secret")


@pytest.mark.parametrize("cryptoapi", [False, True])
def test_doc_decryption_preserves_clear_fib_and_stream_alignment(cryptoapi):
    header, key = rc4_fixture(cryptoapi=cryptoapi)
    word = bytearray(1100)
    struct.pack_into("<HH", word, 0, 0xA5EC, 0xC1)
    struct.pack_into("<H", word, 10, 0x0300)
    word[80:90] = b"WORD TEXT!"
    table = header + b"T" * 1300
    data = b"D" * 1200
    def encrypt(value):
        return b"".join(rc4(key(i // 512), value[i:i + 512])
                        for i in range(0, len(value), 512))
    encrypted_word = bytes(word[:68]) + encrypt(word)[68:]
    encrypted_table = header + encrypt(table)[len(header):]
    actual_word, actual_table, decrypt_data = decrypt_doc_streams(
        encrypted_word, encrypted_table, "secret")
    assert actual_word[:10] == word[:10]
    assert actual_word[12:] == word[12:]
    assert actual_word[80:90] == b"WORD TEXT!"
    assert actual_table[len(header):] == table[len(header):]
    assert decrypt_data(encrypt(data)) == data


@pytest.mark.parametrize("cryptoapi", [False, True])
def test_xls_record_headers_and_boundsheet_prefix_remain_clear(cryptoapi):
    header, key = rc4_fixture(cryptoapi=cryptoapi)
    def record(kind, body):
        return struct.pack("<HH", kind, len(body)) + body
    prefix = record(0x0809, b"\x00\x06\x05\x00") + record(47, b"\x01\x00" + header)
    bodies = [(0x0085, struct.pack("<I", 1234) + b"\x00\x00\x01\x00A"),
              (0x00FC, b"data" * 300), (10, b"")]
    plain = prefix + b"".join(record(k, b) for k, b in bodies)
    encrypted = bytearray(b"".join(rc4(key(i // 1024), plain[i:i + 1024])
                                  for i in range(0, len(plain), 1024)))
    encrypted[:len(prefix)] = prefix
    offset = len(prefix)
    for kind, body in bodies:
        encrypted[offset:offset + 4] = plain[offset:offset + 4]
        if kind == 0x85:
            encrypted[offset + 4:offset + 8] = plain[offset + 4:offset + 8]
        offset += len(body) + 4
    assert decrypt_xls_workbook(bytes(encrypted), "secret") == plain
    with pytest.raises(ValueError, match="암호"):
        decrypt_xls_workbook(bytes(encrypted), "bad-password")


def test_xls_xor_method1_known_verifier_and_record_positions():
    # MS-OFFCRYPTO method 1: abc has key 0x514a, verifier 0xcc1a.
    # The synthetic record ciphertext is formed independently from those constants.
    array = bytes.fromhex("95999475da577857da7465a87a2f2577")
    prefix = struct.pack("<HH", 47, 6) + struct.pack("<HHH", 0, 0x514A, 0xCC1A)
    body = b"\x00\x00\x06\x00Sheet1"
    plain = prefix + struct.pack("<HH", 0x85, len(body) + 4) + struct.pack("<I", 1234) + body
    encrypted_body = bytes((((v >> 3) | (v << 5)) & 255) ^ array[(len(plain) + 4 + i) % 16]
                           for i, v in enumerate(body))
    encrypted = plain[:-len(body)] + encrypted_body
    assert decrypt_xls_workbook(encrypted, "abc") == plain
    with pytest.raises(ValueError, match="암호"):
        decrypt_xls_workbook(encrypted, "xyz")


def test_xls_default_password_and_malformed_record():
    header, key = rc4_fixture(password="VelvetSweatshop")
    workbook = struct.pack("<HHH", 47, len(header) + 2, 1) + header
    assert decrypt_xls_workbook(workbook) == workbook
    with pytest.raises(ValueError):
        decrypt_xls_workbook(b"\x2f\x00\xff\xff")


def test_xls_xor_checks_key_as_well_as_short_password_verifier():
    record = struct.pack("<HHHHH", 47, 6, 0, 0x514B, 0xCC1A)
    with pytest.raises(ValueError, match="암호"):
        decrypt_xls_workbook(record, "abc")


def test_doc_xor_rejected_explicitly_instead_of_emitting_ciphertext():
    word = bytearray(68)
    struct.pack_into("<H", word, 10, 0x8100)
    with pytest.raises(ValueError, match="XOR"):
        decrypt_doc_streams(word, b"", "secret")


@pytest.mark.parametrize("kind,streams", [
    ("doc", {"WordDocument": b"\xec\xa5" + bytes(8) + b"\x00\x01" + bytes(56),
             "0Table": b"\x04\x00\x02\x00"}),
    ("xls", {"Workbook": struct.pack("<HHH", 47, 6, 1) + b"\x04\x00\x02\x00"}),
])
def test_legacy_reader_preserves_safe_crypto_failure_detail(monkeypatch, tmp_path, kind, streams):
    import io
    from dochan.office_binary.doc import DOCReader
    from dochan.office_binary.xls import XLSReader
    class Ole:
        def __init__(self, *args, **kwargs):
            pass
        def exists(self, name):
            return name in streams
        def openstream(self, name):
            return io.BytesIO(streams[name])
        def get_size(self, name):
            return len(streams[name])
        def close(self):
            pass
    monkeypatch.setattr("dochan.office_binary.%s.cfb.OleFileIO" % kind, Ole)
    path = tmp_path / ("encrypted." + kind)
    path.write_bytes(b"\xd0\xcf\x11\xe0" + bytes(508))
    reader = DOCReader if kind == "doc" else XLSReader
    doc = reader(password="PRIVATE_PASSWORD").read(str(path))
    assert not doc.sections
    assert any("CryptoAPI 헤더가 잘렸습니다" in error for error in doc.errors)
    assert "PRIVATE_PASSWORD" not in repr(doc.errors)


def test_xls_crypto_header_error_is_not_relabelled_wrong_password():
    workbook = struct.pack("<HHH", 47, 6, 1) + b"\x04\x00\x02\x00"
    with pytest.raises(ValueError, match="CryptoAPI 헤더가 잘렸습니다"):
        decrypt_xls_workbook(workbook, "secret")


def test_doc_xor_method2_known_verifier_and_all_stream_positions():
    # MS-OFFCRYPTO 2.3.7.4-.6. For abc, high word is 0x514a and low
    # word 0xcc1a. Byte transform is involutive, retaining zero bytes and
    # bytes equal to their XOR-array entry. The first 68 Word bytes are clear.
    array = bytes.fromhex("95999475da577857da7465a87a2f2577")
    def crypt(data):
        return bytes((byte ^ array[index % 16]) if byte and byte != array[index % 16]
                     else byte for index, byte in enumerate(data))
    word = bytearray(bytes(range(256)) * 5)
    struct.pack_into("<HH", word, 0, 0xA5EC, 0xC1)
    struct.pack_into("<H", word, 6, 0x0409)
    struct.pack_into("<H", word, 10, 0x8300)
    struct.pack_into("<I", word, 14, 0x514ACC1A)
    table = bytes(range(256)) * 5 + array
    data = bytes(range(255, -1, -1)) * 5
    encrypted_word = bytes(word[:68]) + crypt(word)[68:]
    actual, actual_table, decrypt_data = decrypt_doc_streams(encrypted_word, crypt(table), "abc")
    assert actual[:10] == word[:10]
    assert struct.unpack_from("<H", actual, 10)[0] == 0x0200
    assert actual[12:] == word[12:]
    assert actual_table == table
    assert decrypt_data(crypt(data)) == data
    for wrong in (None, "wrong"):
        with pytest.raises(ValueError, match="XOR.*암호 인증 실패"):
            decrypt_doc_streams(encrypted_word, crypt(table), wrong)


def test_doc_xor_uses_low_byte_or_high_byte_unicode_password():
    # U+0161 -> 0x61; U+0162 -> 0x62; U+0163 -> 0x63.
    word = bytearray(68)
    struct.pack_into("<H", word, 6, 0x0409)
    struct.pack_into("<H", word, 10, 0x8100)
    struct.pack_into("<I", word, 14, 0x514ACC1A)
    result, table, _ = decrypt_doc_streams(word, b"", "šŢţ")
    assert not struct.unpack_from("<H", result, 10)[0] & 0x8100
    assert table == b""


@pytest.mark.parametrize("password,lcid,verifier", [
    ("€bc", 0x0409, 0xFD11CDD8),  # CP1252: euro is byte 0x80, not 0xac.
    ("a" * 15 + "ignored suffix", 0x0409, 0xB64BB1BB),
    ("\u6100\u6200\u6300", 0x0409, 0x514ACC1A),  # zero low byte -> high byte.
])
def test_doc_xor_password_conversion_and_truncation(password, lcid, verifier):
    word = bytearray(68)
    struct.pack_into("<H", word, 6, lcid)
    struct.pack_into("<H", word, 10, 0x8100)
    struct.pack_into("<I", word, 14, verifier)
    result, _, _ = decrypt_doc_streams(word, b"", password)
    assert not struct.unpack_from("<H", result, 10)[0] & 0x8100


def test_doc_xor_bounds_all_streams(monkeypatch):
    monkeypatch.setattr("dochan.crypto.legacy.MAX_STREAM", 68)
    word = bytearray(68)
    struct.pack_into("<H", word, 10, 0x8100)
    struct.pack_into("<I", word, 14, 0x514ACC1A)
    with pytest.raises(ValueError, match="상한"):
        decrypt_doc_streams(word, bytes(69), "abc")
    _, _, decrypt_data = decrypt_doc_streams(word, b"", "abc")
    with pytest.raises(ValueError, match="상한"):
        decrypt_data(bytes(69))


def test_doc_xor_reader_and_public_api_preserve_native_model(monkeypatch, tmp_path):
    import io
    from dochan import Dochan
    from dochan.office_binary.doc import DOCReader
    from test_doc_structure import _native_streams

    streams = _native_streams()
    word = bytearray(streams["WordDocument"])
    struct.pack_into("<H", word, 6, 0x0409)
    struct.pack_into("<H", word, 10, 0x8100)
    struct.pack_into("<I", word, 14, 0x514ACC1A)
    array = bytes.fromhex("95999475da577857da7465a87a2f2577")
    def encrypt(data):
        return bytes((value ^ array[index % 16]) if value and value != array[index % 16]
                     else value for index, value in enumerate(data))
    streams["WordDocument"] = bytes(word[:68]) + encrypt(word)[68:]
    streams["0Table"] = encrypt(streams["0Table"])
    class Ole:
        def __init__(self, *args, **kwargs):
            pass
        def exists(self, name):
            return name in streams
        def openstream(self, name):
            return io.BytesIO(streams[name])
        def get_size(self, name):
            return len(streams[name])
        def close(self):
            pass
    monkeypatch.setattr("dochan.office_binary.doc.cfb.OleFileIO", Ole)
    path = tmp_path / "xor-native.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(504))
    document = DOCReader(password="abc").read(str(path))
    assert document.errors == []
    assert document.sections[0].elements[0].text == "Native text"
    assert document.sections[0].elements[0].provenance.path == "WordDocument#cp0"
    api = Dochan(str(path), password="abc")
    assert api.errors == []
    assert api.to_plain_text().strip() == "Native text"
