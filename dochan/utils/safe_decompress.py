"""utils/safe_decompress.py — 안전한 zlib 해제"""
import zlib

MAX_DECOMPRESSED_SIZE = 200 * 1024 * 1024  # 200MB


def safe_zlib_decompress(
    data: bytes, max_size: int = MAX_DECOMPRESSED_SIZE, *, trailer_validator=None
) -> bytes:
    """크기 제한이 있는 raw-DEFLATE 해제.

    출력은 64KiB 단위로 제한하며 예산보다 한 바이트만 더 요청한다.
    실패한 원래 예외의 ``inflated`` 속성으로 이미 해제한 양을 전한다.
    ``trailer_validator`` 는 배포용 AES 패딩처럼 형식별 꼬리를 검증한다.
    """
    total = 0
    try:
        if not isinstance(max_size, int) or isinstance(max_size, bool) or max_size < 0:
            raise ValueError("max_size must be a non-negative integer")

        decompressor = zlib.decompressobj(-15)
        chunks = []
        checksum = 0
        chunk_size = 65536
        had_input = False

        for i in range(0, len(data), chunk_size):
            pending = data[i:i + chunk_size]
            while True:
                before = len(pending)
                output_limit = min(chunk_size, max_size - total + 1)
                checkpoint = decompressor.copy()
                try:
                    chunk = decompressor.decompress(pending, output_limit)
                except zlib.error:
                    total += _failed_inflation_size(
                        checkpoint, pending, output_limit, had_input
                    )
                    raise
                had_input = True
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
                    if trailer_validator is not None:
                        trailer_validator(trailing, checksum, total)
                    elif len(trailing) == 8:
                        _validate_hwp_trailer(trailing, checksum, total)
                    elif trailing.strip(b"\x00"):
                        # 복호화한 배포용 스트림의 0x00 AES 패딩은 허용한다.
                        raise ValueError("Invalid compressed stream: trailing data")
                    return b''.join(chunks)
                if not pending and len(chunk) < output_limit:
                    break

        if not decompressor.eof:
            raise ValueError("Invalid compressed stream: truncated data")
    except (ValueError, zlib.error) as exc:
        exc.inflated = total
        raise


def _failed_inflation_size(checkpoint, pending, output_limit, had_input):
    """실패한 호출이 버린 출력을 제한된 재시도로 계상한다.

    Python zlib은 오류와 같은 호출에서 만든 출력을 반환하지 않는다.
    저장한 상태에서 입력 접두사와 출력 상한을 이분 탐색한다. 입력과 출력은
    각각 64KiB 이하이며 오류일 때만 최대 32회 재시도하므로 압축 폭탄을
    다시 전부 풀지 않는다. 출력 상한과 같은 순간의 오류는 마지막 1바이트가
    관측되지 않을 수 있어 최대 1바이트를 보수적으로 더 계상한다. 첫 입력
    바이트부터 거부된 스트림에는 해제한 출력이 없으므로 0을 돌려준다.
    """
    low = 0
    high = len(pending)
    while high - low > 1:
        middle = (low + high) // 2
        try:
            checkpoint.copy().decompress(pending[:middle], output_limit)
        except zlib.error:
            high = middle
        else:
            low = middle
    if not had_input and low == 0:
        return 0

    low_output = 0
    high_output = output_limit
    while high_output - low_output > 1:
        middle = (low_output + high_output) // 2
        try:
            checkpoint.copy().decompress(pending, middle)
        except zlib.error:
            high_output = middle
        else:
            low_output = middle
    return high_output


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
