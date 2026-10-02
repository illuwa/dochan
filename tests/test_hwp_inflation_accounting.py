import struct
import zlib

import pytest

from dochan.utils.safe_decompress import safe_zlib_decompress


def _deflate(data):
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


def test_invalid_deflate_has_zero_inflation_and_preserves_zlib_error():
    with pytest.raises(zlib.error, match="invalid block type") as error:
        safe_zlib_decompress(b"\xff")
    assert error.value.inflated == 0


def test_partial_invalid_header_accounting_has_at_most_one_probe_byte():
    # Stored LEN/NLEN disagree: no payload was emitted, but Python zlib does
    # not expose failed-call total_out. Bounded replay may reserve one byte.
    with pytest.raises(zlib.error, match="invalid stored block lengths") as error:
        safe_zlib_decompress(b"\x00\x00\x00\x00\x00")
    assert 0 <= error.value.inflated <= 1


@pytest.mark.parametrize("field", ["crc", "size"])
def test_failed_hwp_trailer_reports_completed_inflation(field):
    payload = b"section" * 20000
    crc = zlib.crc32(payload) ^ (1 if field == "crc" else 0)
    size = len(payload) + (1 if field == "size" else 0)
    with pytest.raises(ValueError, match="mismatch") as error:
        safe_zlib_decompress(_deflate(payload) + struct.pack("<II", crc, size))
    assert error.value.inflated == len(payload)


def test_truncated_deflate_reports_output_already_emitted():
    compressed = _deflate(b"section" * 20000)[:-3]
    expected = len(zlib.decompressobj(-15).decompress(compressed))
    assert expected > 0
    with pytest.raises(ValueError, match="truncated") as error:
        safe_zlib_decompress(compressed)
    assert error.value.inflated == expected


@pytest.mark.parametrize("size", [1, 4000, 65535])
def test_invalid_later_deflate_block_accounts_for_same_call_output(size):
    # A valid non-final stored block, followed by reserved BTYPE=3.
    payload = b"x" * size
    compressed = b"\x00" + struct.pack("<HH", size, size ^ 0xFFFF) + payload + b"\xff"
    with pytest.raises(zlib.error, match="invalid block type") as error:
        safe_zlib_decompress(compressed)
    assert error.value.inflated == size


def test_oversize_inflation_reports_only_limit_plus_probe_byte():
    with pytest.raises(ValueError, match="exceeds limit") as error:
        safe_zlib_decompress(_deflate(b"x" * 1000000), max_size=100)
    assert error.value.inflated == 101


def test_trailer_validator_observes_one_inflation_and_preserves_its_error():
    payload = b"section" * 10000
    seen = []
    failure = ValueError("custom trailer failure")

    def validate(trailing, checksum, size):
        seen.append((trailing, checksum, size))
        raise failure

    with pytest.raises(ValueError, match="custom trailer failure") as error:
        safe_zlib_decompress(_deflate(payload) + b"trailer", trailer_validator=validate)
    assert error.value is failure
    assert error.value.inflated == len(payload)
    assert seen == [(b"trailer", zlib.crc32(payload), len(payload))]
