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
