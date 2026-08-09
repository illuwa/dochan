"""utils/aes.py — 순정 AES-128 ECB 복호화 (FIPS-197)

배포용(distribution-copy) HWP 문서의 ViewText 섹션 복호화 전용.
외부 암호화 라이브러리 의존성을 늘리지 않기 위해 AES-128 단일 모드만
FIPS-197 명세 그대로 구현한다 (일반 목적 암호화 라이브러리가 아님).
"""
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
    """128/256비트 키 → 라운드 키 워드 목록.

    Nk=4(AES-128,Nr=10) 또는 Nk=8(AES-256,Nr=14). AES-256 은
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
    return w


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


def _add_round_key(state: List[List[int]], round_keys: List[List[int]], round_idx: int) -> None:
    for c in range(4):
        word = round_keys[round_idx * 4 + c]
        for r in range(4):
            state[r][c] ^= word[r]


def _inv_sub_bytes(state: List[List[int]]) -> None:
    for r in range(4):
        for c in range(4):
            state[r][c] = INV_SBOX[state[r][c]]


def _inv_shift_rows(state: List[List[int]]) -> None:
    for r in range(1, 4):
        state[r] = state[r][-r:] + state[r][:-r]


def _inv_mix_columns(state: List[List[int]]) -> None:
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _gmul(a[0], 0x0E) ^ _gmul(a[1], 0x0B) ^ _gmul(a[2], 0x0D) ^ _gmul(a[3], 0x09)
        state[1][c] = _gmul(a[0], 0x09) ^ _gmul(a[1], 0x0E) ^ _gmul(a[2], 0x0B) ^ _gmul(a[3], 0x0D)
        state[2][c] = _gmul(a[0], 0x0D) ^ _gmul(a[1], 0x09) ^ _gmul(a[2], 0x0E) ^ _gmul(a[3], 0x0B)
        state[3][c] = _gmul(a[0], 0x0B) ^ _gmul(a[1], 0x0D) ^ _gmul(a[2], 0x09) ^ _gmul(a[3], 0x0E)


def _decrypt_block(block: bytes, round_keys: List[List[int]], nr: int = 10) -> bytes:
    state = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
    _add_round_key(state, round_keys, nr)
    for round_idx in range(nr - 1, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, round_keys, round_idx)
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, round_keys, 0)
    return bytes(state[r][c] for c in range(4) for r in range(4))


def _sub_bytes(state: List[List[int]]) -> None:
    for r in range(4):
        for c in range(4):
            state[r][c] = SBOX[state[r][c]]


def _shift_rows(state: List[List[int]]) -> None:
    for r in range(1, 4):
        state[r] = state[r][r:] + state[r][:r]


def _mix_columns(state: List[List[int]]) -> None:
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _gmul(a[0], 2) ^ _gmul(a[1], 3) ^ a[2] ^ a[3]
        state[1][c] = a[0] ^ _gmul(a[1], 2) ^ _gmul(a[2], 3) ^ a[3]
        state[2][c] = a[0] ^ a[1] ^ _gmul(a[2], 2) ^ _gmul(a[3], 3)
        state[3][c] = _gmul(a[0], 3) ^ a[1] ^ a[2] ^ _gmul(a[3], 2)


def _encrypt_block(block: bytes, round_keys: List[List[int]], nr: int) -> bytes:
    state = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
    _add_round_key(state, round_keys, 0)
    for round_idx in range(1, nr):
        _sub_bytes(state)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, round_keys, round_idx)
    _sub_bytes(state)
    _shift_rows(state)
    _add_round_key(state, round_keys, nr)
    return bytes(state[r][c] for c in range(4) for r in range(4))


def aes128_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-128-ECB 복호화. data 길이는 16의 배수여야 한다 (패딩은 호출자 책임)."""
    if len(key) != 16:
        raise ValueError(f"AES-128 키는 16바이트여야 함 (got {len(key)})")
    if len(data) % 16 != 0:
        raise ValueError(f"ECB 입력은 16바이트 배수여야 함 (got {len(data)})")

    round_keys = _key_expansion(key)
    return b"".join(
        _decrypt_block(data[i:i + 16], round_keys)
        for i in range(0, len(data), 16)
    )


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
