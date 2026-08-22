"""utils/safe_decompress.py — 안전한 zlib 해제"""
import zlib

MAX_DECOMPRESSED_SIZE = 200 * 1024 * 1024  # 200MB


def safe_zlib_decompress(data: bytes, max_size: int = MAX_DECOMPRESSED_SIZE) -> bytes:
    """크기 제한이 있는 raw-DEFLATE 해제.

    ``zlib.decompressobj.flush()`` 는 출력 길이를 제한하지 않으므로 압축
    폭탄을 모두 메모리에 만든 뒤 거부하게 된다. 입력과 ``unconsumed_tail``
    을 작은 조각으로 소비하고 항상 남은 예산보다 한 바이트만 더 요청해
    상한을 넘는 즉시 중단한다.
    """
    if not isinstance(max_size, int) or isinstance(max_size, bool) or max_size < 0:
        raise ValueError("max_size must be a non-negative integer")

    decompressor = zlib.decompressobj(-15)
    chunks = []
    total = 0
    checksum = 0
    chunk_size = 65536

    for i in range(0, len(data), chunk_size):
        pending = data[i:i + chunk_size]
        while pending:
            before = len(pending)
            chunk = decompressor.decompress(pending, max_size - total + 1)
            if chunk:
                chunks.append(chunk)
                total += len(chunk)
                checksum = zlib.crc32(chunk, checksum)
                if total > max_size:
                    raise ValueError(f"Decompressed size exceeds limit ({max_size} bytes)")

            pending = decompressor.unconsumed_tail
            consumed = before - len(pending)
            if pending and consumed <= 0 and not chunk:
                raise ValueError("Invalid compressed stream: decompressor made no progress")

            if decompressor.eof:
                trailing = decompressor.unused_data + data[i + chunk_size:]
                if trailing:
                    _validate_hwp_trailer(trailing, checksum, total)
                return b''.join(chunks)

    if not decompressor.eof:
        raise ValueError("Invalid compressed stream: truncated data")


def _validate_hwp_trailer(trailing: bytes, checksum: int, output_size: int) -> None:
    """Validate the optional CRC32/ISIZE trailer used by compressed HWP streams."""
    if len(trailing) != 8:
        raise ValueError("Invalid compressed stream: trailing data")

    expected_checksum = int.from_bytes(trailing[:4], "little")
    expected_size = int.from_bytes(trailing[4:], "little")
    if expected_checksum != checksum & 0xFFFFFFFF:
        raise ValueError("Invalid compressed stream: trailing data checksum mismatch")
    if expected_size != output_size & 0xFFFFFFFF:
        raise ValueError("Invalid compressed stream: trailing data size mismatch")
