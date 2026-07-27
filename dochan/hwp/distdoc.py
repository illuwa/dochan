"""
hwp/distdoc.py — 배포용(distribution-copy) 문서 ViewText 섹션 복호화

HWP5 배포용 문서는 본문을 BodyText 대신 ViewText 스토리지에 저장하며,
각 ViewText/SectionN 스트림 맨 앞에 DistributeDocData 레코드(256바이트)가
붙고 그 뒤 본문은 AES-128-ECB 로 암호화되어 있다. 압축(zlib raw deflate)은
이 암호문을 복호화한 결과에 적용된다 — 즉 (스크램블 해제 → AES 키 추출)
→ AES 복호화 → zlib 압축 해제 순서.

알고리즘은 hwplib(Java, Apache-2.0)과 pyhwp(Python, AGPL-3.0)의 독립 구현이
상수 단위까지 일치하는 것으로 교차검증했고, 원저자로 알려진 Changwoo Ryu의
2010년 hwp-foss 메일링 리스트 글과도 일치한다. 두 구현 모두 참고했지만
코드는 그대로 옮기지 않고 이 파일에 새로 작성했다 (pyhwp 는 AGPL-3.0).
"""
import struct

from ..constants import HWPTAG_DISTRIBUTE_DOC_DATA
from ..utils.aes import aes128_ecb_decrypt

_DISTDOC_DATA_SIZE = 256
_HEADER_SIZE = 4


def _read_record_header(data: bytes) -> tuple:
    header = struct.unpack_from("<I", data, 0)[0]
    tag_id = header & 0x3FF
    level = (header >> 10) & 0x3FF
    size = (header >> 20) & 0xFFF
    return tag_id, level, size


def _descramble(seed_block: bytearray) -> None:
    """MSVC rand()/srand() 호환 LCG 기반 XOR 런렝스 스크램블 해제 (in-place)."""
    seed = struct.unpack_from("<I", seed_block, 0)[0]
    random_seed = seed

    def rand() -> int:
        nonlocal random_seed
        random_seed = (random_seed * 214013 + 2531011) & 0xFFFFFFFF
        return (random_seed >> 16) & 0x7FFF

    remaining = 0
    xor_value = 0
    for i in range(len(seed_block)):
        if remaining == 0:
            xor_value = rand() & 0xFF
            remaining = (rand() & 0xF) + 1
        if i >= 4:  # 앞 4바이트는 시드 자신이라 스크램블 대상이 아님
            seed_block[i] ^= xor_value
        remaining -= 1


def decode_distribution_section(raw_stream: bytes) -> bytes:
    """ViewText/SectionN 원본 바이트 → AES 복호화된 (아직 압축 상태인) 바이트.

    반환값은 기존 BodyText 경로와 동일하게 safe_zlib_decompress(wbits=-15)로
    풀어야 하는 raw-deflate 압축 스트림이다 — 호출자가 그 단계를 담당한다.
    """
    if len(raw_stream) < _HEADER_SIZE + _DISTDOC_DATA_SIZE:
        raise ValueError(
            f"ViewText 섹션이 너무 짧음: {len(raw_stream)}바이트 "
            f"(최소 {_HEADER_SIZE + _DISTDOC_DATA_SIZE}바이트 필요)"
        )

    tag_id, _level, size = _read_record_header(raw_stream)
    if tag_id != HWPTAG_DISTRIBUTE_DOC_DATA or size != _DISTDOC_DATA_SIZE:
        raise ValueError(
            f"첫 레코드가 HWPTAG_DISTRIBUTE_DOC_DATA(256바이트)가 아님: "
            f"tag={tag_id} size={size}"
        )

    seed_block = bytearray(raw_stream[_HEADER_SIZE:_HEADER_SIZE + _DISTDOC_DATA_SIZE])
    _descramble(seed_block)

    key_offset = _HEADER_SIZE + (seed_block[0] & 0xF)
    aes_key = bytes(seed_block[key_offset:key_offset + 16])

    tail = raw_stream[_HEADER_SIZE + _DISTDOC_DATA_SIZE:]
    if len(tail) % 16 != 0:
        raise ValueError(f"AES 암호문 길이가 16의 배수가 아님: {len(tail)}바이트")

    return aes128_ecb_decrypt(aes_key, tail)
