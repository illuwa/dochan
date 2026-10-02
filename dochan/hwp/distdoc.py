"""한컴 배포용 문서의 ViewText 섹션을 복호화한다.

근거: 「한글문서파일형식 배포용 문서 revision 1.2」 1절, 2.1~2.4절과
「한글문서파일형식 5.0 revision 1.3」 3.2.1절, 4.1절, 4.2.13절.
2.2절이 지정한 MS Visual C rand의 수치 상수는 해당 명세에 기재되어 있지 않다.
압축 후 trailer 배치 역시 명세에 없어 공개 실물의 CRC32와 길이로 검증한다.
"""
import struct

from dochan.constants import HWPTAG_DISTRIBUTE_DOC_DATA
from dochan.utils.aes import aes128_ecb_decrypt
from dochan.utils.bounded_io import MAX_OLE_STREAM_SIZE
from dochan.utils.safe_decompress import MAX_DECOMPRESSED_SIZE, safe_zlib_decompress


def _read_record_header(data: bytes):
    if len(data) < 4:
        raise ValueError("Truncated DISTRIBUTE_DOC_DATA header")
    word = int.from_bytes(data[:4], "little")
    size = word >> 20
    start = 4
    if size == 4095:
        if len(data) < 8:
            raise ValueError("Truncated DISTRIBUTE_DOC_DATA extended size")
        size = int.from_bytes(data[4:8], "little")
        start = 8
    if word & 1023 != HWPTAG_DISTRIBUTE_DOC_DATA:
        raise ValueError("Expected DISTRIBUTE_DOC_DATA record")
    if size != 256 or len(data) < start + size:
        raise ValueError("DISTRIBUTE_DOC_DATA requires 256 bytes")
    return start


def _msvc_rand(seed: int):
    """srand(seed) 뒤의 rand() 값을 차례로 낸다(MS Visual C 런타임의 선형 합동 생성기)."""
    # 2.2절은 MS Visual C rand를 지정하지만 이 상수들을 직접 싣지는 않는다.
    state = seed & 0xFFFFFFFF
    while True:
        state = (state * 214013 + 2531011) & 0xFFFFFFFF
        yield (state >> 16) & 0x7FFF


def _random_array(seed: int) -> bytes:
    """2.2절의 난수 배열: 홀수번째 rand() & 0xFF 를 짝수번째 (rand() & 0x0F) + 1 번 채운다."""
    rand = _msvc_rand(seed)
    array = bytearray()
    while len(array) < 256:
        fill = next(rand) & 0xFF
        array += bytes([fill]) * ((next(rand) & 0x0F) + 1)
    return bytes(array[:256])


def _descramble(seed_block: bytearray):
    """2.3절대로 256바이트 전체를 난수 배열과 XOR한다. offset은 호출부가 먼저 구한다."""
    if len(seed_block) != 256:
        raise ValueError("DISTRIBUTE_DOC_DATA requires 256 bytes")
    mask = _random_array(int.from_bytes(seed_block[:4], "little"))
    for index, value in enumerate(mask):
        seed_block[index] ^= value


def _compressed_payload(data: bytes, *, max_size=None, decompress=False):
    """검증과 본문 해제를 한 번에 수행하며 기존 압축 바이트 반환도 지원한다."""
    if max_size is None:
        max_size = MAX_DECOMPRESSED_SIZE
    end = 0

    def validate(trailer, checksum, total):
        nonlocal end
        end = len(data) - len(trailer)
        padding = bytes(-end % 16)
        # 공개 실물의 AES 정렬 CRC32/ISIZE 두 배치를 그대로 검증한다.
        check = struct.pack("<II", checksum & 0xFFFFFFFF, total)
        aligned = padding + check[:4] + bytes(12) + check[4:] + bytes(12)
        packed = check + bytes(-(end + 8) % 16)
        if trailer not in (padding, aligned, packed):
            raise ValueError("Invalid distribution CRC32/size trailer or alignment")

    output = safe_zlib_decompress(data, max_size=max_size, trailer_validator=validate)
    return output if decompress else data[:end]


def decode_distribution_section(raw_stream: bytes, *, is_compressed: bool = False,
                                max_size=None, decompress: bool = False):
    """AES 복호화 결과를 반환하며 압축된 경우 검증된 DEFLATE 부분만 반환한다."""
    if len(raw_stream) > MAX_OLE_STREAM_SIZE:
        raise ValueError("Distribution stream size exceeds limit")
    start = _read_record_header(raw_stream)
    ciphertext = raw_stream[start + 256:]
    if not ciphertext or len(ciphertext) % 16:
        raise ValueError("Distribution ciphertext requires complete AES blocks")
    key_data = bytearray(raw_stream[start:start + 256])
    offset = 4 + (key_data[0] & 15)  # 2.3절 1항: XOR 전에 seed로 구한다
    _descramble(key_data)
    plaintext = aes128_ecb_decrypt(bytes(key_data[offset:offset + 16]), ciphertext)
    if is_compressed:
        return _compressed_payload(plaintext, max_size=max_size, decompress=decompress)
    return plaintext
