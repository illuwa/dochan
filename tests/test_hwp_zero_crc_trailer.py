"""일부 HWP 작성기는 압축 스트림 끝 CRC32/ISIZE 꼬리의 CRC 를 0 으로 쓴다(공개 hwplib 생성 문서 27개)."""

import struct
import zlib

import pytest

from dochan.utils.safe_decompress import safe_zlib_decompress


def _stream(payload, crc=None, size=None):
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(payload) + compressor.flush()
    crc = zlib.crc32(payload) if crc is None else crc
    size = len(payload) if size is None else size
    return compressed + struct.pack("<II", crc, size)


def test_zero_crc_trailer_with_matching_size_is_accepted():
    payload = b"hwp record stream" * 100
    assert safe_zlib_decompress(_stream(payload, crc=0)) == payload


@pytest.mark.parametrize("crc, size", [(1, None), (0, 1)])
def test_wrong_nonzero_crc_or_size_is_still_rejected(crc, size):
    with pytest.raises(ValueError):
        safe_zlib_decompress(_stream(b"hwp record stream" * 100, crc=crc, size=size))
