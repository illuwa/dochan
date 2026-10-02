"""한컴 배포용 문서의 고정 길이 및 손상 입력 경계를 합성 바이트로 검증한다."""
import struct

import pytest

from conftest import build_distdoc_view_text_stream
from dochan.constants import HWPTAG_DISTRIBUTE_DOC_DATA
from dochan.hwp import distdoc


@pytest.mark.parametrize("size", [0, 3, 255, 257])
def test_distribution_seed_block_requires_exact_spec_size(size):
    with pytest.raises(ValueError, match="256"):
        distdoc._descramble(bytearray(size))


def test_distribution_stream_limit_is_checked_before_decryption(monkeypatch):
    raw = build_distdoc_view_text_stream(1, bytes(16), bytes(16))
    monkeypatch.setattr(distdoc, "MAX_OLE_STREAM_SIZE", len(raw) - 1, raising=False)
    with pytest.raises(ValueError, match="limit"):
        distdoc.decode_distribution_section(raw)


@pytest.mark.parametrize("seed", [0, 1, 15, 16, 0x80000000, 0xFFFFFFFF])
def test_distribution_seed_offsets_and_unsigned_wrap(seed):
    payload = bytes(range(32))
    raw = build_distdoc_view_text_stream(seed, bytes(range(16)), payload)
    assert distdoc.decode_distribution_section(raw) == payload


def test_distribution_extended_record_size():
    raw = build_distdoc_view_text_stream(1, bytes(16), bytes(range(16)))
    extended = struct.pack("<II", (4095 << 20) | HWPTAG_DISTRIBUTE_DOC_DATA, 256) + raw[4:]
    assert distdoc.decode_distribution_section(extended) == bytes(range(16))


@pytest.mark.parametrize("size", [0, 255, 257])
def test_distribution_rejects_non_spec_record_size(size):
    raw = struct.pack("<I", (size << 20) | HWPTAG_DISTRIBUTE_DOC_DATA) + bytes(size + 16)
    with pytest.raises(ValueError):
        distdoc.decode_distribution_section(raw)


@pytest.mark.parametrize("tail", [b"", b"x", bytes(15), bytes(17)])
def test_distribution_rejects_empty_or_unaligned_ciphertext(tail):
    raw = struct.pack("<I", (256 << 20) | HWPTAG_DISTRIBUTE_DOC_DATA) + bytes(256) + tail
    with pytest.raises(ValueError):
        distdoc.decode_distribution_section(raw)


def test_msvc_rand_matches_known_srand_one_sequence():
    # srand(1) 직후 MS Visual C rand() 의 처음 다섯 값 (널리 알려진 고정 수열)
    from conftest import msvc_rand_sequence
    expected = [41, 18467, 6334, 26500, 19169]
    assert msvc_rand_sequence(1, 5) == expected
    rand = distdoc._msvc_rand(1)
    assert [next(rand) for _ in range(5)] == expected


@pytest.mark.parametrize("seed", [0, 1, 0x4D3D1806, 0xFFFFFFFF])
def test_descramble_xors_all_256_bytes_with_spec_random_array(seed):
    from conftest import distdoc_random_array
    block = bytearray(struct.pack("<I", seed) + bytes(252))
    distdoc._descramble(block)
    expected = distdoc_random_array(seed)
    # 2.3절: 앞 4바이트(seed)까지 포함한 256바이트 전체를 XOR 한다
    assert list(block[4:]) == expected[4:]
    assert list(block[:4]) == [s ^ m for s, m in zip(struct.pack("<I", seed), expected[:4])]


def test_random_array_count_uses_low_nibble_plus_one():
    # 명세의 "(rand() & 0x0F + 1)" 은 C 우선순위상 rand() & 0x10 으로도 읽히지만
    # 공개 실물 65섹션은 (rand() & 0x0F) + 1 해석에서만 복호화된다.
    from conftest import msvc_rand_sequence
    calls = msvc_rand_sequence(1, 2)
    array = distdoc._random_array(1)
    run = calls[1] % 16 + 1
    assert array[:run] == bytes([calls[0] % 256]) * run
