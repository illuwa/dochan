"""PDF 표준 보안 핸들러 — RC4/AES 복호화 (stdlib 전용).

PDF 32000-1:2008 §7.6 Standard Security Handler 를 구현한다.
지원: V1/V2 (RC4), V4 (RC4 또는 AESV2=AES-128-CBC), V5/R6 (AESV3=AES-256-CBC).
빈 사용자 암호(소유자만 잠근 문서)와 사용자 제공 암호 모두 처리.
AES 블록 연산은 dochan/utils/aes.py 의 순정 구현을 CBC/256비트로 확장해 쓴다.
"""
import hashlib
import struct
import stringprep
import unicodedata
from typing import Optional, Union

from ..utils import aes as _aes

# 표준 패딩 문자열 (§7.6.3.3, Algorithm 2)
_PAD = bytes([
    0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41, 0x64, 0x00, 0x4E, 0x56,
    0xFF, 0xFA, 0x01, 0x08, 0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68, 0x3E, 0x80,
    0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A,
])


def rc4(key: bytes, data: bytes) -> bytes:
    """RC4 스트림 암호 (대칭 — 복호화도 동일)."""
    s = list(range(256))
    j = 0
    klen = len(key)
    for i in range(256):
        j = (j + s[i] + key[i % klen]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


class UnsupportedEncryption(Exception):
    """지원하지 않는 암호화 방식."""


class StandardSecurityHandler:
    """PDF 표준 보안 핸들러 — 파일 암호화 키 유도와 객체별 복호화."""

    def __init__(self, encrypt: dict, doc_id: bytes, password: Union[str, bytes] = b""):
        self.v = encrypt.get("V", 0)
        self.r = encrypt.get("R", 0)
        # AESV3 always uses 256 bits; /Length is not required for V5.
        self.length_bits = 256 if self.v == 5 else encrypt.get("Length", 40)
        if self.v == 4 and "Length" not in encrypt:
            self.length_bits = self._v4_filter_key_bits(encrypt)
        self.o = _as_bytes(encrypt.get("O", b""))
        self.u = _as_bytes(encrypt.get("U", b""))
        self.oe = _as_bytes(encrypt.get("OE", b""))
        self.ue = _as_bytes(encrypt.get("UE", b""))
        self.p = encrypt.get("P", 0) & 0xFFFFFFFF
        self.encrypt_metadata = encrypt.get("EncryptMetadata", True)
        self.doc_id = doc_id
        self._validate_parameters()
        self._cipher = self._detect_cipher(encrypt)
        self._string_cipher = self._detect_cipher(encrypt, "StrF")
        self.key = self._compute_key(_password_bytes(password, self.r))
        if self.key is None:
            raise UnsupportedEncryption("암호 인증 실패 — 빈/제공 암호로 열 수 없음")

    @staticmethod
    def _v4_filter_key_bits(encrypt: dict) -> int:
        """최상위 Length가 없는 V4에서 활성 필터의 바이트 키 길이를 읽는다."""
        lengths = set()
        filters = encrypt.get("CF", {})
        for field in ("StmF", "StrF"):
            name = str(encrypt.get(field, "Identity"))
            if name == "Identity":
                continue
            entry = filters.get(name) if isinstance(filters, dict) else None
            if not isinstance(entry, dict):
                raise UnsupportedEncryption("지원하지 않는 암호 필터")
            cipher = str(entry.get("CFM", "None"))
            if cipher in ("None", "Identity"):
                continue
            if cipher not in ("V2", "AESV2"):
                raise UnsupportedEncryption("지원하지 않는 V4 암호 필터")
            # ISO 32000-1 §7.6.5: AESV2 uses a 128-bit key. CF Length
            # is in bytes; absent RC4 length retains the 40-bit default.
            length = entry.get("Length", 16 if cipher == "AESV2" else 5)
            if (type(length) is not int or not 5 <= length <= 16 or
                    cipher == "AESV2" and length != 16):
                raise UnsupportedEncryption("잘못된 암호 필터 키 길이")
            lengths.add(length * 8)
        if len(lengths) > 1:
            raise UnsupportedEncryption("서로 다른 암호 필터 키 길이는 지원하지 않음")
        return next(iter(lengths)) if lengths else 40

    def _validate_parameters(self) -> None:
        if self.r not in (2, 3, 4, 5, 6) or self.v not in (1, 2, 4, 5):
            raise UnsupportedEncryption("지원하지 않는 표준 보안 핸들러 버전")
        if self.r >= 5:
            if (self.v != 5 or self.length_bits != 256 or len(self.o) < 48 or
                    len(self.u) < 48 or len(self.oe) != 32 or len(self.ue) != 32):
                raise UnsupportedEncryption("손상된 AES-256 암호화 사전")
        elif (not isinstance(self.length_bits, int) or self.length_bits < 40 or
              self.length_bits > 128 or self.length_bits % 8 or
              len(self.o) < 32 or len(self.u) < 32):
            raise UnsupportedEncryption("손상된 RC4/AES-128 암호화 사전")

    def _detect_cipher(self, encrypt: dict, field: str = "StmF") -> str:
        """RC4 / AESV2 / AESV3 중 무엇인지 판정."""
        if self.v >= 4:
            cf = encrypt.get("CF")
            stmf = encrypt.get(field, "Identity")
            if str(stmf) == "Identity":
                return "identity"
            if isinstance(cf, dict) and str(stmf) in cf:
                cfm = str(cf[str(stmf)].get("CFM", ""))
                if cfm == "AESV3":
                    return "aesv3"
                if cfm == "AESV2":
                    return "aesv2"
                if cfm == "V2":
                    return "rc4"
                if cfm in ("None", "Identity"):
                    return "identity"
            raise UnsupportedEncryption("지원하지 않는 암호 필터")
        return "rc4"

    def _compute_key(self, password: bytes) -> Optional[bytes]:
        if self.r >= 5:
            return self._compute_key_r5(password)
        return self._compute_key_rc4(password)

    def _compute_key_rc4(self, password: bytes, owner_retry: bool = True) -> Optional[bytes]:
        """Algorithm 2 (R2-R4) — 파일 키 유도 후 /U 로 인증."""
        n = self.length_bits // 8 if self.v >= 2 else 5
        padded = (password + _PAD)[:32]
        md = hashlib.md5()
        md.update(padded)
        md.update(self.o[:32])
        md.update(struct.pack("<I", self.p))
        md.update(self.doc_id)
        if self.r >= 4 and not self.encrypt_metadata:
            md.update(b"\xff\xff\xff\xff")
        key = md.digest()
        if self.r >= 3:
            for _ in range(50):
                key = hashlib.md5(key[:n]).digest()
        key = key[:n]
        if self._authenticate_rc4(key):
            return key
        # 사용자 암호가 소유자 암호로 주어졌을 수 있음 → 소유자 경로 시도
        if owner_retry:
            owner_key = self._owner_user_password(password)
            if owner_key is not None:
                return self._compute_key_rc4(owner_key, owner_retry=False)
        return None

    def _authenticate_rc4(self, key: bytes) -> bool:
        if self.r == 2:
            return rc4(key, _PAD) == self.u[:32]
        # R3/R4: MD5(pad + id) 를 RC4 반복 암호화한 값의 상위 16바이트 비교
        md = hashlib.md5()
        md.update(_PAD)
        md.update(self.doc_id)
        digest = md.digest()
        result = rc4(key, digest)
        for i in range(1, 20):
            result = rc4(bytes(b ^ i for b in key), result)
        return result[:16] == self.u[:16]

    def _owner_user_password(self, owner_password: bytes) -> Optional[bytes]:
        """소유자 암호로 사용자 암호를 복원 (Algorithm 3 역)."""
        n = self.length_bits // 8 if self.v >= 2 else 5
        padded = (owner_password + _PAD)[:32]
        key = hashlib.md5(padded).digest()
        if self.r >= 3:
            for _ in range(50):
                key = hashlib.md5(key).digest()
        key = key[:n]
        user = self.o[:32]
        if self.r == 2:
            return rc4(key, user)
        for i in range(19, -1, -1):
            user = rc4(bytes(b ^ i for b in key), user)
        return user

    def _compute_key_r5(self, password: bytes) -> Optional[bytes]:
        """Algorithm 2.A (R5/R6) — AES-256, SHA-2 기반."""
        pw = password[:127]
        # 사용자 암호 검증: SHA-256(pw + user validation salt) == U[:32]
        u_hash = self.u[:32]
        u_valid_salt = self.u[32:40]
        u_key_salt = self.u[40:48]
        if self._hash_r6(pw, u_valid_salt, b"") == u_hash:
            ik = self._hash_r6(pw, u_key_salt, b"")
            return _aes.aes_cbc_decrypt_no_pad(ik, b"\x00" * 16, self.ue[:32])
        # 소유자 암호 경로
        o_hash = self.o[:32]
        o_valid_salt = self.o[32:40]
        o_key_salt = self.o[40:48]
        if self._hash_r6(pw, o_valid_salt, self.u[:48]) == o_hash:
            ik = self._hash_r6(pw, o_key_salt, self.u[:48])
            return _aes.aes_cbc_decrypt_no_pad(ik, b"\x00" * 16, self.oe[:32])
        return None

    def _hash_r6(self, password: bytes, salt: bytes, extra: bytes) -> bytes:
        """R6 경화 해시 (Algorithm 2.B). R5 는 SHA-256 단일.

        256 ≡ 1 (mod 3) 이므로 E[:16] 바이트 합의 mod 3 은 빅엔디언 정수의
        mod 3 과 같다. 최소 64 라운드 후 E 의 마지막 바이트가 (라운드-32)
        이하가 되면 종료한다.
        """
        k = hashlib.sha256(password + salt + extra).digest()
        if self.r == 5:
            return k
        round_num = 0
        while True:
            k1 = (password + k + extra) * 64
            e = _aes.aes_cbc_encrypt_no_pad(k[:16], k[16:32], k1)
            mod = sum(e[:16]) % 3
            if mod == 0:
                k = hashlib.sha256(e).digest()
            elif mod == 1:
                k = hashlib.sha384(e).digest()
            else:
                k = hashlib.sha512(e).digest()
            round_num += 1
            if round_num >= 64 and e[-1] <= round_num - 32:
                break
        return k[:32]

    def decrypt(self, num: int, gen: int, data: bytes, is_stream: bool = True) -> bytes:
        """객체 (num, gen) 의 문자열/스트림 바이트를 복호화."""
        cipher = self._cipher if is_stream else self._string_cipher
        if cipher == "identity" or not data:
            return data
        if cipher == "aesv3":
            return _aes_cbc_decrypt(self.key, data)
        # RC4/AESV2 는 객체별 키 유도 (Algorithm 1)
        obj_key = self._object_key(num, gen, cipher == "aesv2")
        if cipher == "aesv2":
            return _aes_cbc_decrypt(obj_key, data)
        return rc4(obj_key, data)

    def _object_key(self, num: int, gen: int, is_aes: bool) -> bytes:
        md = hashlib.md5()
        md.update(self.key)
        md.update(struct.pack("<I", num)[:3])
        md.update(struct.pack("<I", gen)[:2])
        if is_aes:
            md.update(b"sAlT")
        n = min(len(self.key) + 5, 16)
        return md.digest()[:n]


def _aes_cbc_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-CBC 복호화 — 앞 16바이트가 IV, PKCS#7 패딩 제거."""
    if len(data) < 16:
        return b""
    iv, body = data[:16], data[16:]
    if len(body) % 16 != 0:
        body = body[:len(body) - (len(body) % 16)]
    if not body:
        return b""
    plain = _aes.aes_cbc_decrypt_no_pad(key, iv, body)
    if plain:
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
    return plain


def _as_bytes(value) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("latin-1", errors="replace")
    return b""


def _password_bytes(password: Union[str, bytes], revision: int) -> bytes:
    """R2–R4는 PDFDocEncoding, R5는 UTF-8, R6는 SASLprep 후 UTF-8."""
    if isinstance(password, bytes):
        # 바이트 API는 이미 인코딩/정규화한 암호를 전달하는 경로다.
        return password[:127] if revision >= 5 else password[:32]
    if not isinstance(password, str) or len(password) > 4096:
        raise UnsupportedEncryption("암호 형식 또는 길이 한도 오류")
    try:
        if revision <= 4:
            return _encode_pdfdoc_password(password[:32])
        if revision == 6:
            password = _saslprep(password)
        return password.encode("utf-8")[:127]
    except (UnicodeError, ValueError) as exc:
        raise UnsupportedEncryption("암호 문자 인코딩 또는 정규화 실패") from exc


def _encode_pdfdoc_password(value: str) -> bytes:
    """ISO 32000-1 Annex D의 단일 바이트 PDFDocEncoding 역매핑."""
    encoding = {chr(i): i for i in range(256)
                if not 0x18 <= i <= 0x1f and not 0x7f <= i <= 0xa0 and i != 0xad}
    encoding.update({char: 0x18 + i for i, char in enumerate("˘ˇˆ˙˝˛˚˜")})
    encoding.update({char: 0x80 + i for i, char in enumerate(
        "•†‡…—–ƒ⁄‹›−‰„“”‘’‚™ﬁﬂŁŒŠŸŽıłœšž")})
    encoding["€"] = 0xa0
    try:
        return bytes(encoding[char] for char in value)
    except KeyError as exc:
        raise ValueError("PDFDocEncoding에 없는 암호 문자") from exc


def _saslprep(value: str) -> str:
    """RFC 4013의 Unicode 3.2 매핑·NFKC·금지 문자·양방향 검사를 적용한다."""
    mapped = "".join(" " if stringprep.in_table_c12(c) else c for c in value
                     if not stringprep.in_table_b1(c))
    normalized = unicodedata.ucd_3_2_0.normalize("NFKC", mapped)
    prohibited = (stringprep.in_table_a1, stringprep.in_table_c12,
                  stringprep.in_table_c21_c22, stringprep.in_table_c3,
                  stringprep.in_table_c4, stringprep.in_table_c5,
                  stringprep.in_table_c6, stringprep.in_table_c7,
                  stringprep.in_table_c8, stringprep.in_table_c9)
    if any(check(c) for c in normalized for check in prohibited):
        raise ValueError("SASLprep 금지 문자")
    if any(stringprep.in_table_d1(c) for c in normalized):
        if (any(stringprep.in_table_d2(c) for c in normalized) or
                not stringprep.in_table_d1(normalized[0]) or
                not stringprep.in_table_d1(normalized[-1])):
            raise ValueError("SASLprep 양방향 문자 순서 오류")
    return normalized
