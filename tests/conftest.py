"""tests/conftest.py — 여러 테스트 파일이 공유하는 픽스처 빌더.

dochan/utils/aes.py 는 복호화만 제공한다 (운영 코드에 필요한 게 그것뿐이라서).
배포용 문서 테스트 픽스처를 만들려면 암호화도 필요한데, 그건 테스트 전용이라
운영 코드에는 넣지 않고 여기 모아둔다.
"""
import struct

from dochan.utils import aes as _aes


def scramble_distdoc_seed_block(seed_block: bytearray) -> None:
    """DistributeDocData 256바이트 스크램블 (XOR 은 자기 역산이라 인코드/디코드 동일)."""
    seed = struct.unpack_from("<I", seed_block, 0)[0]
    random_seed = seed

    def rand():
        nonlocal random_seed
        random_seed = (random_seed * 214013 + 2531011) & 0xFFFFFFFF
        return (random_seed >> 16) & 0x7FFF

    n = 0
    value = 0
    for i in range(256):
        if n == 0:
            value = rand() & 0xFF
            n = (rand() & 0xF) + 1
        if i >= 4:
            seed_block[i] ^= value
        n -= 1


def _sub_bytes(state):
    for r in range(4):
        for c in range(4):
            state[r][c] = _aes.SBOX[state[r][c]]


def _shift_rows(state):
    for r in range(1, 4):
        state[r] = state[r][r:] + state[r][:r]


def _mix_columns(state):
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _aes._gmul(a[0], 2) ^ _aes._gmul(a[1], 3) ^ a[2] ^ a[3]
        state[1][c] = a[0] ^ _aes._gmul(a[1], 2) ^ _aes._gmul(a[2], 3) ^ a[3]
        state[2][c] = a[0] ^ a[1] ^ _aes._gmul(a[2], 2) ^ _aes._gmul(a[3], 3)
        state[3][c] = _aes._gmul(a[0], 3) ^ a[1] ^ a[2] ^ _aes._gmul(a[3], 2)


def aes128_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    """테스트 픽스처 생성 전용 AES-128-ECB 암호화 (운영 코드는 복호화만 필요)."""
    assert len(data) % 16 == 0
    round_keys = _aes._key_expansion(key)
    out = bytearray()
    for block_start in range(0, len(data), 16):
        block = data[block_start:block_start + 16]
        state = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
        _aes._add_round_key(state, round_keys, 0)
        for round_idx in range(1, 10):
            _sub_bytes(state)
            _shift_rows(state)
            _mix_columns(state)
            _aes._add_round_key(state, round_keys, round_idx)
        _sub_bytes(state)
        _shift_rows(state)
        _aes._add_round_key(state, round_keys, 10)
        out.extend(state[r][c] for c in range(4) for r in range(4))
    return bytes(out)


def build_distdoc_view_text_stream(seed: int, aes_key: bytes, plaintext_tail: bytes) -> bytes:
    """ViewText/SectionN 원본(스크램블+암호화된) 스트림 생성 — 픽스처 빌더.

    AES 키를 심는 위치는 실제 알고리즘과 마찬가지로 seed 하위 니블로 정해진다
    (호출자가 별도로 고르지 않는다 — decode_distribution_section() 도 같은
    공식으로 오프셋을 계산하므로 여기서 독립적으로 고르면 어긋난다).
    """
    assert len(aes_key) == 16

    seed_block = bytearray(256)
    struct.pack_into("<I", seed_block, 0, seed)
    offset = 4 + (seed & 0xF)
    seed_block[offset:offset + 16] = aes_key

    scramble_distdoc_seed_block(seed_block)  # in-place: 평문 → 스크램블 상태

    header = struct.pack("<I", (256 << 20) | (0 << 10) | 28)  # tag=DISTRIBUTE_DOC_DATA size=256

    padded_tail = plaintext_tail + b"\x00" * ((-len(plaintext_tail)) % 16)
    ciphertext = aes128_ecb_encrypt(aes_key, padded_tail)

    return header + bytes(seed_block) + ciphertext
