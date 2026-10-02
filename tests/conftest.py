"""tests/conftest.py — 여러 테스트 파일이 공유하는 픽스처 빌더.

dochan/utils/aes.py 는 복호화만 제공한다 (운영 코드에 필요한 게 그것뿐이라서).
배포용 문서 테스트 픽스처를 만들려면 암호화도 필요한데, 그건 테스트 전용이라
운영 코드에는 넣지 않고 여기 모아둔다.
"""
import struct

from dochan.utils import aes as _aes


def msvc_rand_sequence(seed: int, count: int) -> list:
    """srand(seed) 뒤 rand() 결과 count 개.

    MS Visual C 런타임: 상태 = 상태 × 214013 + 2531011 (mod 2^32), 반환 = 상태의 16~30비트.
    """
    values, state = [], seed % 2 ** 32
    for _ in range(count):
        state = (state * 214013 + 2531011) % 2 ** 32
        values.append(state // 2 ** 16 % 2 ** 15)
    return values


def distdoc_random_array(seed: int) -> list:
    """배포용 문서 명세 2.2절의 256바이트 난수 배열 (테스트 정답지용 독립 작성).

    rand() 를 두 번씩 묶어 (값, 횟수) 로 쓴다. 한 쌍이 최소 1바이트를 채우므로 256쌍이면 충분하다.
    """
    calls = msvc_rand_sequence(seed, 512)
    array = []
    for value, count in zip(calls[0::2], calls[1::2]):
        array.extend([value % 256] * (count % 16 + 1))
        if len(array) >= 256:
            break
    return array[:256]


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

    # 2.1절: 저장된 첫 4바이트가 seed. 2.3절: offset = (seed & 0x0F) + 4 에 해시코드(앞 16바이트가 AES 키).
    offset = 4 + (seed & 0x0F)
    merged = bytearray(256)
    merged[offset:offset + 16] = aes_key
    mask = distdoc_random_array(seed)
    seed_block = struct.pack("<I", seed) + bytes(m ^ x for m, x in zip(merged[4:], mask[4:]))

    header = struct.pack("<I", (256 << 20) | (0 << 10) | 28)  # tag=DISTRIBUTE_DOC_DATA size=256

    padded_tail = plaintext_tail + b"\x00" * ((-len(plaintext_tail)) % 16)
    ciphertext = aes128_ecb_encrypt(aes_key, padded_tail)

    return header + seed_block + ciphertext
