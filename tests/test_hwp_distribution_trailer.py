"""실물 ViewText에서 관찰한 AES 정렬 CRC32/ISIZE trailer를 검증한다."""

import struct
import zlib

import pytest

from conftest import build_distdoc_view_text_stream
from dochan.hwp.distdoc import decode_distribution_section
from dochan.utils.safe_decompress import safe_zlib_decompress


def _stream(payload, corrupt=""):
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(payload) + compressor.flush()
    padding = b"\x00" * (-len(compressed) % 16)
    crc = zlib.crc32(payload) ^ (1 if corrupt == "crc" else 0)
    size = len(payload) + (1 if corrupt == "size" else 0)
    trailer = struct.pack("<I", crc) + bytes(12) + struct.pack("<I", size) + bytes(12)
    if corrupt == "padding":
        trailer = trailer[:5] + b"X" + trailer[6:]
    raw = build_distdoc_view_text_stream(0x12345678, bytes(range(16)), compressed + padding + trailer)
    return raw, compressed


def test_distribution_aligned_crc_and_size_are_verified():
    payload = b"distribution body" * 200
    raw, compressed = _stream(payload)
    result = decode_distribution_section(raw, is_compressed=True)
    assert result == compressed
    assert safe_zlib_decompress(result) == payload


@pytest.mark.parametrize("corrupt", ["crc", "size", "padding"])
def test_distribution_rejects_corrupt_aligned_trailer(corrupt):
    raw, _ = _stream(b"body", corrupt)
    with pytest.raises(ValueError):
        decode_distribution_section(raw, is_compressed=True)


def test_distribution_decompression_probe_enforces_size_limit(monkeypatch):
    raw, _ = _stream(b"a" * 1000)
    monkeypatch.setattr("dochan.hwp.distdoc.MAX_DECOMPRESSED_SIZE", 20)
    with pytest.raises(ValueError, match="limit"):
        decode_distribution_section(raw, is_compressed=True)


def test_distribution_packed_crc_and_size_before_alignment():
    payload = b"packed trailer"
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(payload) + compressor.flush()
    trailer = struct.pack("<II", zlib.crc32(payload), len(payload))
    raw = build_distdoc_view_text_stream(1, bytes(range(16)), compressed + trailer)
    assert decode_distribution_section(raw, is_compressed=True) == compressed


def test_distribution_drains_buffered_deflate_output_at_chunk_boundary():
    payload = b"a" * 65537
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(payload) + compressor.flush()
    raw = build_distdoc_view_text_stream(1, bytes(range(16)), compressed)
    assert decode_distribution_section(raw, is_compressed=True) == compressed
