"""[MS-OFFCRYPTO] binary RC4 / CryptoAPI and legacy stream framing.

The key derivation follows sections 2.3.5.2 and 2.3.6.2. Stream positions
are absolute: clear record headers still consume cipher keystream bytes.
"""
import hashlib
import hmac
import struct

from ..pdf.crypto import rc4


MAX_STREAM = 256 * 1024 * 1024
MAX_RECORDS = 1000000


class LegacyCryptoError(ValueError):
    """A static, password-free diagnosis safe for reader error output."""


class PasswordError(LegacyCryptoError):
    """Authentication failed; another documented default may be tried."""


class RC4Encryption:
    def __init__(self, base, cryptoapi=False, key_bits=128):
        self._base = base
        self._cryptoapi = cryptoapi
        self._key_bits = key_bits

    def key(self, block_number):
        suffix = struct.pack("<I", block_number)
        if not self._cryptoapi:
            return hashlib.md5(self._base + suffix).digest()
        key = hashlib.sha1(self._base + suffix).digest()[:self._key_bits // 8]
        return key + b"\x00" * 11 if self._key_bits == 40 else key

    def crypt_block(self, data, block_number):
        if len(data) > MAX_STREAM:
            raise LegacyCryptoError("암호화 스트림 크기 상한 초과")
        return rc4(self.key(block_number), data)

    def crypt(self, data, block_size=512):
        if len(data) > MAX_STREAM or block_size <= 0:
            raise LegacyCryptoError("암호화 스트림 크기 상한 초과")
        return b"".join(self.crypt_block(data[i:i + block_size], i // block_size)
                        for i in range(0, len(data), block_size))


def parse_rc4_header(data, password):
    """Authenticate EncryptionInfo (including the four-byte version)."""
    if not isinstance(password, str):
        password = "" if password is None else password
    if not isinstance(password, str) or len(password) > 255:
        raise PasswordError("암호 인증 실패 또는 지원하지 않는 암호 길이")
    if len(data) < 4:
        raise LegacyCryptoError("암호화 헤더가 잘렸습니다")
    version = struct.unpack_from("<HH", data)
    password_bytes = password.encode("utf-16le")
    if version == (1, 1):
        if len(data) < 52:
            raise LegacyCryptoError("암호화 RC4 헤더가 잘렸습니다")
        salt, encrypted = data[4:20], data[20:52]
        first = hashlib.md5(password_bytes).digest()[:5]
        base = hashlib.md5((first + salt) * 16).digest()[:5]
        context = RC4Encryption(base)
        digest = hashlib.md5
    elif version[0] in (2, 3, 4) and version[1] == 2:
        if len(data) < 44:
            raise LegacyCryptoError("암호화 CryptoAPI 헤더가 잘렸습니다")
        flags, size = struct.unpack_from("<II", data, 4)
        if not 32 <= size <= 4096 or 12 + size + 60 > len(data):
            raise LegacyCryptoError("암호화 CryptoAPI 헤더 크기가 잘못되었습니다")
        _, extra, algorithm, hash_algorithm, key_bits, provider, _, _ = struct.unpack_from("<8I", data, 12)
        if algorithm not in (0, 0x6801) or hash_algorithm not in (0, 0x8004) or flags & 0x20:
            raise LegacyCryptoError("지원하지 않는 암호화 CryptoAPI 알고리즘입니다")
        key_bits = key_bits or 40
        if key_bits < 40 or key_bits > 128 or key_bits % 8:
            raise LegacyCryptoError("잘못된 암호화 RC4 키 길이입니다")
        position = 12 + size
        salt_size = struct.unpack_from("<I", data, position)[0]
        hash_size = struct.unpack_from("<I", data, position + 36)[0]
        if salt_size != 16 or hash_size != 20:
            raise LegacyCryptoError("잘못된 암호화 검증자 크기입니다")
        salt = data[position + 4:position + 20]
        encrypted = data[position + 20:position + 36] + data[position + 40:position + 60]
        context = RC4Encryption(hashlib.sha1(salt + password_bytes).digest(), True, key_bits)
        digest = hashlib.sha1
    else:
        raise LegacyCryptoError("지원하지 않는 Office 암호화 버전입니다")
    clear = context.crypt_block(encrypted, 0)
    if not hmac.compare_digest(digest(clear[:16]).digest(), clear[16:]):
        raise PasswordError("암호 인증 실패")
    return context


def decrypt_doc_streams(word, table, password=None):
    """Return decrypted WordDocument, table and a Data-stream decryptor."""
    if len(word) < 68:
        raise LegacyCryptoError("암호화 DOC FIB가 잘렸습니다")
    flags = struct.unpack_from("<H", word, 10)[0]
    if flags & 0x8000:
        decrypt = _doc_xor_decryptor(word, password)
    else:
        decrypt = parse_rc4_header(table, password).crypt
    clear_word = bytearray(decrypt(word))
    clear_word[:68] = word[:68]
    struct.pack_into("<H", clear_word, 10, flags & ~0x8100)
    return bytes(clear_word), decrypt(table), decrypt


def _xor_array(password, key, verifier):
    # [MS-OFFCRYPTO] 2.3.7.1 / 2.3.7.2, method 1 byte-password.
    if not isinstance(password, str) or not 1 <= len(password) <= 15:
        raise PasswordError("암호 인증 실패 또는 지원하지 않는 XOR 암호 길이")
    encoded = password.encode("utf-16le")
    raw = bytes(encoded[i] or encoded[i + 1] for i in range(0, len(encoded), 2))
    return _xor_array_bytes(raw, key, verifier)


def _xor_array_bytes(raw, key, verifier):
    if not 1 <= len(raw) <= 15:
        raise PasswordError("암호 인증 실패 또는 지원하지 않는 XOR 암호 길이")
    calculated = 0
    for byte in raw[::-1]:
        calculated = ((calculated << 1) & 0x7FFF) | (calculated >> 14)
        calculated ^= byte
    calculated = ((calculated << 1) & 0x7FFF) | (calculated >> 14)
    calculated ^= len(raw) ^ 0xCE4B
    if calculated != verifier:
        raise PasswordError("암호 인증 실패")
    # MS-OFFCRYPTO InitialCode / XorMatrix constants. The seven-bit rows of
    # XorMatrix are expanded using the documented CRC-16 polynomial.
    initial = (0xE1F0, 0x1D0F, 0xCC9C, 0x84C0, 0x110C, 0x0E10,
               0xF1CE, 0x313E, 0x1872, 0xE139, 0xD40F, 0x84F9,
               0x280C, 0xA96A, 0x4EC3)
    seeds = (0xAEFC, 0x7B61, 0x4563, 0x0375, 0xD849, 0x6F45,
             0xEB23, 0x47D3, 0xB861, 0x45A0, 0xAA51, 0x76B4,
             0x3730, 0x3331, 0x1021)
    matrix = []
    for value in seeds:
        for _ in range(7):
            matrix.append(value)
            value = ((value << 1) ^ (0x1021 if value & 0x8000 else 0)) & 0xFFFF
    derived = initial[len(raw) - 1]
    index = 104
    for byte in raw[::-1]:
        for _ in range(7):
            if byte & 0x40:
                derived ^= matrix[index]
            byte <<= 1
            index -= 1
    if derived != key:
        raise PasswordError("암호 인증 실패")
    padding = bytes.fromhex("bbffffbaffffb98000be0f00bf0f00")
    values = (raw + padding)[:16]
    array = []
    for i, value in enumerate(values):
        value ^= (key >> (8 * (i % 2))) & 255
        array.append(((value >> 1) | (value << 7)) & 255)
    return array


def _doc_ansi_encoding(lcid):
    # [MS-LCID] Windows ANSI code pages for the FIB language identifier.
    language = lcid & 0x3FF
    # Azerbaijani and Uzbek distinguish Latin and Cyrillic sublanguages.
    if lcid in (0x082C, 0x0843):
        return "cp1251"
    if language == 0x04:
        return "cp950" if lcid in (0x0404, 0x0C04, 0x1404) else "cp936"
    if language == 0x11:
        return "cp932"
    if language == 0x12:
        return "cp949"
    if language == 0x1E:
        return "cp874"
    if language in (0x01, 0x20, 0x29):
        return "cp1256"
    if language == 0x0D:
        return "cp1255"
    if language == 0x08:
        return "cp1253"
    if language in (0x1F, 0x2C, 0x43):
        return "cp1254"
    if language in (0x25, 0x26, 0x27):
        return "cp1257"
    if language == 0x2A:
        return "cp1258"
    if language in (0x02, 0x19, 0x22, 0x23, 0x28, 0x2F, 0x3F, 0x40, 0x44, 0x50):
        return "cp1251"
    if language in (0x05, 0x0E, 0x15, 0x18, 0x1A, 0x1B, 0x1C, 0x24):
        return "cp1251" if lcid in (0x0C1A, 0x1C1A, 0x201A) else "cp1250"
    return "cp1252"


def _doc_xor_decryptor(word, password):
    # [MS-OFFCRYPTO] 2.3.7.4-.6 and [MS-DOC] 2.2.6.1. The lKey
    # verifier is CreateXorKey_Method1 in its high word, verifier1 low.
    if not isinstance(password, str) or len(password) > 4096:
        raise PasswordError("DOC XOR 암호 인증 실패")
    lcid = struct.unpack_from("<H", word, 6)[0]
    verifier, key = struct.unpack_from("<HH", word, 14)
    # Readers must try both documented Unicode-to-byte conversions.
    encoded = password[:15].encode("utf-16le", errors="surrogatepass")
    low_or_high = bytes(encoded[i] or encoded[i + 1] for i in range(0, len(encoded), 2))[:15]
    ansi = password[:15].encode(_doc_ansi_encoding(lcid), errors="replace")[:15]
    array = None
    for raw in (ansi, low_or_high):
        try:
            array = _xor_array_bytes(raw, key, verifier)
            break
        except PasswordError:
            continue
    if array is None:
        raise PasswordError("DOC XOR 암호 인증 실패")

    def decrypt(data):
        if len(data) > MAX_STREAM:
            raise LegacyCryptoError("암호화 DOC XOR 스트림 크기 상한 초과")
        # Zero and key-equal bytes are invariant; offsets stay absolute even
        # across WordDocument's 68 clear prefix bytes.
        result = bytearray(data)
        for index, value in enumerate(data):
            transformed = value ^ array[index % 16]
            if value and transformed:
                result[index] = transformed
        return bytes(result)
    return decrypt


def decrypt_xls_workbook(data, password=None):
    """Decrypt BIFF record bodies, retaining clear headers and offsets."""
    if len(data) > MAX_STREAM:
        raise LegacyCryptoError("암호화 XLS 스트림 크기 상한 초과")
    records = []
    offset = 0
    filepass = None
    while offset + 4 <= len(data):
        kind, size = struct.unpack_from("<HH", data, offset)
        end = offset + 4 + size
        if end > len(data):
            raise LegacyCryptoError("암호화 XLS 레코드가 잘렸습니다")
        records.append((kind, offset, end))
        if len(records) > MAX_RECORDS:
            raise LegacyCryptoError("암호화 XLS 레코드 개수 상한 초과")
        if kind == 0x002F:
            if filepass is not None:
                raise LegacyCryptoError("중복된 암호화 FILEPASS 레코드입니다")
            filepass = (offset, end)
        offset = end
    if filepass is None:
        return data
    start, end = filepass
    info = data[start + 4:end]
    if len(info) < 2:
        raise LegacyCryptoError("암호화 FILEPASS가 잘렸습니다")
    kind = struct.unpack_from("<H", info)[0]
    passwords = ("", "VelvetSweatshop") if password is None else (password,)
    array = None
    if kind == 0:
        if len(info) != 6:
            raise LegacyCryptoError("암호화 XOR FILEPASS 크기가 잘못되었습니다")
        key, verifier = struct.unpack_from("<HH", info, 2)
        for candidate in passwords:
            try:
                array = _xor_array(candidate, key, verifier)
                break
            except PasswordError:
                continue
        if array is None:
            raise PasswordError("암호 인증 실패")
        result = bytearray(data)
    elif kind == 1:
        context = None
        for candidate in passwords:
            try:
                context = parse_rc4_header(info[2:], candidate)
                break
            except PasswordError:
                continue
        if context is None:
            raise PasswordError("암호 인증 실패")
        result = bytearray(context.crypt(data, 1024))
    else:
        raise LegacyCryptoError("지원하지 않는 FILEPASS 암호화 방식입니다")
    result[:end] = data[:end]
    encryption_start = end
    # [MS-XLS] 2.2.10: these records and BoundSheet8.lbPlyPos are clear.
    clear_records = {0x0809, 0x0009, 0x0209, 0x0409, 0x002F,
                     0x0194, 0x0195, 0x00E1, 0x0196, 0x0138}
    for record_type, start, end in records:
        result[start:start + 4] = data[start:start + 4]
        if start < encryption_start:
            continue
        if array is not None and record_type not in clear_records:
            for position in range(start + 4, end):
                value = data[position] ^ array[(end + position - start - 4) % 16]
                result[position] = ((value << 3) | (value >> 5)) & 255
        if record_type in clear_records:
            result[start + 4:end] = data[start + 4:end]
        elif record_type == 0x0085:
            result[start + 4:min(start + 8, end)] = data[start + 4:min(start + 8, end)]
    return bytes(result)
