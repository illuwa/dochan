"""HWP 명세는 압축에 zlib 을 쓴다고만 정한다. 한컴은 raw DEFLATE 로 쓰지만 다른 생성기는 zlib 헤더를 붙인다."""
import zlib

import pytest

from dochan.utils.safe_decompress import safe_zlib_decompress


def test_zlib_wrapped_stream_is_accepted_when_raw_inflate_fails():
    payload = b"\x42\x00\x10\x00" * 5000
    assert safe_zlib_decompress(zlib.compress(payload)) == payload


def test_raw_deflate_stays_the_primary_path():
    payload = b"hwp record " * 1000
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = compressor.compress(payload) + compressor.flush()
    assert safe_zlib_decompress(raw) == payload


def test_zlib_wrapped_stream_keeps_size_limit_and_checksum():
    payload = b"x" * 100_000
    with pytest.raises(ValueError):
        safe_zlib_decompress(zlib.compress(payload), max_size=1_000)
    damaged = bytearray(zlib.compress(payload))
    damaged[-1] ^= 0xFF  # Adler-32 mismatch
    with pytest.raises((ValueError, zlib.error)):
        safe_zlib_decompress(bytes(damaged))
