"""utils/safe_decompress.py — 안전한 zlib 해제"""
import zlib

MAX_DECOMPRESSED_SIZE = 200 * 1024 * 1024  # 200MB


def safe_zlib_decompress(data: bytes, max_size: int = MAX_DECOMPRESSED_SIZE) -> bytes:
    """크기 제한이 있는 zlib 해제"""
    decompressor = zlib.decompressobj(-15)
    chunks = []
    total = 0
    chunk_size = 65536

    for i in range(0, len(data), chunk_size):
        chunk = decompressor.decompress(data[i:i+chunk_size], max_size - total)
        chunks.append(chunk)
        total += len(chunk)
        if total > max_size:
            raise ValueError(f"Decompressed size exceeds limit ({max_size} bytes)")

    remaining = decompressor.flush()
    chunks.append(remaining)
    total += len(remaining)
    if total > max_size:
        raise ValueError(f"Decompressed size exceeds limit ({max_size} bytes)")

    return b''.join(chunks)
