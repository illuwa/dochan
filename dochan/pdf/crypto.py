"""PDF 표준 보안 핸들러 — RC4/AES 복호화 (stdlib 전용).

PDF 32000-1:2008 §7.6 Standard Security Handler 를 구현한다.
지원: V1/V2 (RC4), V4 (RC4 또는 AESV2=AES-128-CBC), V5/R6 (AESV3=AES-256-CBC).
빈 사용자 암호(소유자만 잠근 문서)와 사용자 제공 암호 모두 처리.
AES 블록 연산은 dochan/utils/aes.py 의 순정 구현을 CBC/256비트로 확장해 쓴다.
"""
import hashlib
import struct
from typing import Optional

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

    def __init__(self, encrypt: dict, doc_id: bytes, password: bytes = b""):
        self.v = encrypt.get("V", 0)
        self.r = encrypt.get("R", 0)
        self.length_bits = encrypt.get("Length", 40)
        self.o = _as_bytes(encrypt.get("O", b""))
        self.u = _as_bytes(encrypt.get("U", b""))
        self.oe = _as_bytes(encrypt.get("OE", b""))
        self.ue = _as_bytes(encrypt.get("UE", b""))
        self.p = encrypt.get("P", 0) & 0xFFFFFFFF
        self.encrypt_metadata = encrypt.get("EncryptMetadata", True)
        self.doc_id = doc_id
        self._cipher = self._detect_cipher(encrypt)
        self.key = self._compute_key(password)
        if self.key is None:
            raise UnsupportedEncryption("암호 인증 실패 — 빈/제공 암호로 열 수 없음")

    def _detect_cipher(self, encrypt: dict) -> str:
        """RC4 / AESV2 / AESV3 중 무엇인지 판정."""
        if self.v >= 4:
            cf = encrypt.get("CF")
            stmf = encrypt.get("StmF", "Identity")
            if isinstance(cf, dict) and str(stmf) in cf:
                cfm = str(cf[str(stmf)].get("CFM", ""))
                if cfm == "AESV3":
                    return "aesv3"
                if cfm == "AESV2":
                    return "aesv2"
                if cfm == "V2":
                    return "rc4"
                if cfm == "Identity":
                    return "identity"
            if self.v == 5 or self.r >= 5:
                return "aesv3"
            return "rc4"
        return "rc4"

    def _compute_key(self, password: bytes) -> Optional[bytes]:
        if self.r >= 5:
            return self._compute_key_r5(password)
        return self._compute_key_rc4(password)

    def _compute_key_rc4(self, password: bytes) -> Optional[bytes]:
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
        owner_key = self._owner_user_password(password)
        if owner_key is not None:
            return self._compute_key_rc4(owner_key)
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

    def decrypt(self, num: int, gen: int, data: bytes) -> bytes:
        """객체 (num, gen) 의 문자열/스트림 바이트를 복호화."""
        if self._cipher == "identity" or not data:
            return data
        if self._cipher == "aesv3":
            return _aes_cbc_decrypt(self.key, data)
        # RC4/AESV2 는 객체별 키 유도 (Algorithm 1)
        obj_key = self._object_key(num, gen, self._cipher == "aesv2")
        if self._cipher == "aesv2":
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
