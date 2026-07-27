"""
tests/test_distdoc.py — 배포용(distribution-copy) 문서 ViewText 복호화 테스트

ViewText/SectionN 스트림 레이아웃 (HWP5 스펙 + hwplib/pyhwp 레퍼런스 구현 교차검증):
  [0:4]    레코드 헤더 (HWPTAG_DISTRIBUTE_DOC_DATA, size=256)
  [4:260]  DistributeDocData 256바이트 — LCG 기반 XOR 스크램블 상태
           (스크램블 해제 후 앞 4바이트가 LCG 시드, offset 4+(seed&0xF) 위치에
           AES-128 키로 쓰이는 16바이트가 있음)
  [260:]   AES-128-ECB 암호문 (그 안에 raw-deflate 압축된 섹션 레코드가 들어있음)

실제 사례로 corpus/hwp-public/hwp/alhangeul-macos-hwpspec.hwp 의
ViewText/Section0 을 이 정확한 알고리즘으로 복호화하면 실제 "글 문서 파일
구조" 스펙 문서 본문(한글 텍스트)이 나오는 것으로 수동 검증했다.
"""
import struct
import zlib

from dochan.hwp.distdoc import decode_distribution_section

from conftest import build_distdoc_view_text_stream


def test_decode_distribution_section_recovers_compressed_payload():
    aes_key = bytes(range(16))
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(b"hello distribution doc") + compressor.flush()

    raw_stream = build_distdoc_view_text_stream(
        seed=0x4D3D1806, aes_key=aes_key, plaintext_tail=compressed,
    )

    decrypted = decode_distribution_section(raw_stream)

    # 복호화 결과는 (패딩 포함) AES 블록 그대로이므로, raw-deflate 압축 해제까지
    # 마쳐야 원문이 나온다 — 기존 safe_zlib_decompress 경로와 동일하게 처리된다.
    assert zlib.decompressobj(-15).decompress(decrypted) == b"hello distribution doc"


def test_decode_distribution_section_rejects_wrong_tag():
    bad_header = struct.pack("<I", (256 << 20) | (0 << 10) | 999)
    raw_stream = bad_header + bytes(256) + bytes(16)

    try:
        decode_distribution_section(raw_stream)
        assert False, "should have raised"
    except ValueError as exc:
        assert "DISTRIBUTE_DOC_DATA" in str(exc)
