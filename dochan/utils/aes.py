"""FIPS-197 순정 AES 블록 연산과 HWP/PDF/Office용 ECB·CBC.

SubBytes·ShiftRows·MixColumns를 32비트 표로 합쳐 문서 크기에 비례하는
GF(2^8) 곱셈 반복을 없앤다. 일반 목적 암호화 라이브러리는 아니며,
표 참조 기반 구현이므로 상수 시간 실행을 보장하지 않는다.
"""
import struct
from typing import List


def _build_sbox() -> bytes:
    # Rijndael S-box via multiplicative inverse in GF(2^8) + affine transform.
    def gf_mul(a: int, b: int) -> int:
        p = 0
        for _ in range(8):
            if b & 1:
                p ^= a
            hi = a & 0x80
            a = (a << 1) & 0xFF
            if hi:
                a ^= 0x1B
            b >>= 1
        return p

    inv = [0] * 256
    for x in range(1, 256):
        for y in range(1, 256):
            if gf_mul(x, y) == 1:
                inv[x] = y
                break

    sbox = [0] * 256
    for x in range(256):
        v = inv[x]
        s = v
        for _ in range(4):
            v = ((v << 1) | (v >> 7)) & 0xFF
            s ^= v
        s ^= 0x63
        sbox[x] = s
    return bytes(sbox)


SBOX = _build_sbox()
INV_SBOX = bytes(SBOX.index(i) for i in range(256))

_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _key_expansion(key: bytes) -> List[List[int]]:
    """128/192/256비트 키 → 라운드 키 워드 목록.

    Nk=4/6/8(AES-128/192/256), Nr=10/12/14이다. AES-256 은
    Nk>6 전용의 추가 SubWord 단계(i % nk == 4)를 포함한다 (FIPS-197 §5.2).
    """
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return _RoundKeys(w)


def _gmul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _make_tables(inverse: bool):
    """FIPS-197 §5.1.3/5.3.3 행렬을 한 열에 적용한 32비트 값."""
    sbox = INV_SBOX if inverse else SBOX
    factors = (14, 9, 13, 11) if inverse else (2, 1, 1, 3)
    first = tuple(
        (_gmul(value, factors[0]) << 24)
        | (_gmul(value, factors[1]) << 16)
        | (_gmul(value, factors[2]) << 8)
        | _gmul(value, factors[3])
        for value in sbox
    )
    return (first,) + tuple(
        tuple(((word >> shift) | (word << (32 - shift))) & 0xFFFFFFFF
              for word in first)
        for shift in (8, 16, 24)
    )


_ENC_TABLES = _make_tables(False)
_DEC_TABLES = _make_tables(True)
_BLOCK = struct.Struct(">4I")


class _RoundKeys(list):
    """기존 워드 목록 계약을 유지하고 블록마다 재사용할 키를 보관한다."""

    def __init__(self, words):
        super().__init__(words)
        self.encrypt = tuple(int.from_bytes(bytes(word), "big") for word in words)
        # Equivalent Inverse Cipher (FIPS-197 §5.3.5): 중간 라운드 키에만
        # InvMixColumns를 적용한다. D-table의 InvSubBytes는 SBOX로 상쇄한다.
        d0, d1, d2, d3 = _DEC_TABLES
        self.decrypt = tuple(
            self.encrypt[i] if i < 4 or i >= len(words) - 4 else
            d0[SBOX[word[0]]] ^ d1[SBOX[word[1]]]
            ^ d2[SBOX[word[2]]] ^ d3[SBOX[word[3]]]
            for i, word in enumerate(words)
        )


def _add_round_key(state: List[List[int]], round_keys: List[List[int]], round_idx: int) -> None:
    """기존 행렬 기반 픽스처 생성기의 키 적용 계약을 유지한다."""
    for c in range(4):
        word = round_keys[round_idx * 4 + c]
        for r in range(4):
            state[r][c] ^= word[r]


def _decrypt_block(block: bytes, round_keys: List[List[int]], nr: int = 10) -> bytes:
    keys = round_keys if isinstance(round_keys, _RoundKeys) else _RoundKeys(round_keys)
    rk = keys.decrypt
    d0, d1, d2, d3 = _DEC_TABLES
    s0, s1, s2, s3 = _BLOCK.unpack(block)
    offset = nr * 4
    s0, s1, s2, s3 = s0 ^ rk[offset], s1 ^ rk[offset + 1], s2 ^ rk[offset + 2], s3 ^ rk[offset + 3]
    for round_idx in range(nr - 1, 0, -1):
        offset = round_idx * 4
        s0, s1, s2, s3 = (
            d0[s0 >> 24] ^ d1[(s3 >> 16) & 255] ^ d2[(s2 >> 8) & 255] ^ d3[s1 & 255] ^ rk[offset],
            d0[s1 >> 24] ^ d1[(s0 >> 16) & 255] ^ d2[(s3 >> 8) & 255] ^ d3[s2 & 255] ^ rk[offset + 1],
            d0[s2 >> 24] ^ d1[(s1 >> 16) & 255] ^ d2[(s0 >> 8) & 255] ^ d3[s3 & 255] ^ rk[offset + 2],
            d0[s3 >> 24] ^ d1[(s2 >> 16) & 255] ^ d2[(s1 >> 8) & 255] ^ d3[s0 & 255] ^ rk[offset + 3],
        )
    inv = INV_SBOX
    return _BLOCK.pack(
        ((inv[s0 >> 24] << 24) | (inv[(s3 >> 16) & 255] << 16) | (inv[(s2 >> 8) & 255] << 8) | inv[s1 & 255]) ^ rk[0],
        ((inv[s1 >> 24] << 24) | (inv[(s0 >> 16) & 255] << 16) | (inv[(s3 >> 8) & 255] << 8) | inv[s2 & 255]) ^ rk[1],
        ((inv[s2 >> 24] << 24) | (inv[(s1 >> 16) & 255] << 16) | (inv[(s0 >> 8) & 255] << 8) | inv[s3 & 255]) ^ rk[2],
        ((inv[s3 >> 24] << 24) | (inv[(s2 >> 16) & 255] << 16) | (inv[(s1 >> 8) & 255] << 8) | inv[s0 & 255]) ^ rk[3],
    )


def _encrypt_block(block: bytes, round_keys: List[List[int]], nr: int) -> bytes:
    keys = round_keys if isinstance(round_keys, _RoundKeys) else _RoundKeys(round_keys)
    rk = keys.encrypt
    e0, e1, e2, e3 = _ENC_TABLES
    s0, s1, s2, s3 = _BLOCK.unpack(block)
    s0, s1, s2, s3 = s0 ^ rk[0], s1 ^ rk[1], s2 ^ rk[2], s3 ^ rk[3]
    for round_idx in range(1, nr):
        offset = round_idx * 4
        s0, s1, s2, s3 = (
            e0[s0 >> 24] ^ e1[(s1 >> 16) & 255] ^ e2[(s2 >> 8) & 255] ^ e3[s3 & 255] ^ rk[offset],
            e0[s1 >> 24] ^ e1[(s2 >> 16) & 255] ^ e2[(s3 >> 8) & 255] ^ e3[s0 & 255] ^ rk[offset + 1],
            e0[s2 >> 24] ^ e1[(s3 >> 16) & 255] ^ e2[(s0 >> 8) & 255] ^ e3[s1 & 255] ^ rk[offset + 2],
            e0[s3 >> 24] ^ e1[(s0 >> 16) & 255] ^ e2[(s1 >> 8) & 255] ^ e3[s2 & 255] ^ rk[offset + 3],
        )
    sub = SBOX
    offset = nr * 4
    return _BLOCK.pack(
        ((sub[s0 >> 24] << 24) | (sub[(s1 >> 16) & 255] << 16) | (sub[(s2 >> 8) & 255] << 8) | sub[s3 & 255]) ^ rk[offset],
        ((sub[s1 >> 24] << 24) | (sub[(s2 >> 16) & 255] << 16) | (sub[(s3 >> 8) & 255] << 8) | sub[s0 & 255]) ^ rk[offset + 1],
        ((sub[s2 >> 24] << 24) | (sub[(s3 >> 16) & 255] << 16) | (sub[(s0 >> 8) & 255] << 8) | sub[s1 & 255]) ^ rk[offset + 2],
        ((sub[s3 >> 24] << 24) | (sub[(s0 >> 16) & 255] << 16) | (sub[(s1 >> 8) & 255] << 8) | sub[s2 & 255]) ^ rk[offset + 3],
    )


def aes128_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-128-ECB 복호화. data 길이는 16의 배수여야 한다 (패딩은 호출자 책임)."""
    if len(key) != 16:
        raise ValueError(f"AES-128 키는 16바이트여야 함 (got {len(key)})")
    if len(data) % 16 != 0:
        raise ValueError(f"ECB 입력은 16바이트 배수여야 함 (got {len(data)})")

    round_keys = _key_expansion(key)
    out = bytearray(len(data))
    for i in range(0, len(data), 16):
        out[i:i + 16] = _decrypt_block(data[i:i + 16], round_keys)
    return bytes(out)


def aes_cbc_decrypt_no_pad(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128/256-CBC 복호화 (패딩 제거는 호출자 책임). PDF 암호 복호화용."""
    if len(key) not in (16, 32) or len(iv) != 16 or len(data) % 16 != 0:
        return b""
    round_keys = _key_expansion(key)
    nr = len(key) // 4 + 6
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        dec = _decrypt_block(block, round_keys, nr)
        out.extend(a ^ b for a, b in zip(dec, prev))
        prev = block
    return bytes(out)


def aes_cbc_encrypt_no_pad(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128/256-CBC 암호화 (패딩 없음). PDF R6 경화 해시 전용."""
    if len(key) not in (16, 32) or len(iv) != 16 or len(data) % 16 != 0:
        return b""
    round_keys = _key_expansion(key)
    nr = len(key) // 4 + 6
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        enc = _encrypt_block(block, round_keys, nr)
        out.extend(enc)
        prev = enc
    return bytes(out)
