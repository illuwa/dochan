"""
tests/test_hwp_distribution_reader.py — 배포용 문서 reader.py 통합 테스트

Dochan(path) 이 배포용(distribution) HWP 파일을 만났을 때 ViewText 섹션을
실제로 복호화해서 본문 텍스트를 뽑아내는지 확인한다 (지금까지는 크래시 없이
빈 결과만 냈다 — docs/benchmarks/2026-07-27-hwp-corpus-collection-and-quality-scan.md
finding #1).

FakeOle 로 olefile.OleFileIO 를 대체하는 패턴은 tests/test_doc_reader.py 와 동일.
"""
import struct
import zlib

from dochan import Dochan

from conftest import build_distdoc_view_text_stream


def _file_header_bytes(is_compressed: bool, is_distribution: bool) -> bytes:
    data = bytearray(256)
    data[0:32] = b"HWP Document File".ljust(32, b"\x00")
    struct.pack_into("<BBBB", data, 32, 0, 0, 0, 5)  # major version 5
    props = 0
    if is_compressed:
        props |= 1 << 0
    if is_distribution:
        props |= 1 << 2
    struct.pack_into("<I", data, 36, props)
    return bytes(data)


def _para_section_bytes(text: str) -> bytes:
    """PARA_HEADER(level0) + PARA_TEXT(level1) 레코드 트리 하나짜리 섹션 바이트."""
    HWPTAG_PARA_HEADER = 66
    HWPTAG_PARA_TEXT = 67

    text_bytes = text.encode("utf-16-le") + struct.pack("<H", 13)  # 13 = 문단 끝

    para_header_payload = bytes(22)  # 최소 길이만 채움 (세부 필드는 이 테스트에 불필요)
    text_record = struct.pack("<I", (len(text_bytes) << 20) | (1 << 10) | HWPTAG_PARA_TEXT) + text_bytes
    header_record = struct.pack("<I", (len(para_header_payload) << 20) | (0 << 10) | HWPTAG_PARA_HEADER) + para_header_payload

    return header_record + text_record


class FakeDistributionOle:
    def __init__(self, path):
        self.path = path

    def exists(self, name):
        return name in ("FileHeader", "DocInfo", "ViewText/Section0")

    def openstream(self, name):
        if name == "FileHeader":
            data = _file_header_bytes(is_compressed=True, is_distribution=True)
        elif name == "DocInfo":
            compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
            data = compressor.compress(b"") + compressor.flush()
        elif name == "ViewText/Section0":
            plaintext_section = _para_section_bytes("배포용 문서 본문 텍스트")
            compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
            compressed_section = compressor.compress(plaintext_section) + compressor.flush()
            aes_key = bytes(range(16))
            data = build_distdoc_view_text_stream(
                seed=0x1234ABCD, aes_key=aes_key,
                plaintext_tail=compressed_section,
            )
        else:
            raise IOError(f"unexpected stream: {name}")

        class Stream:
            def read(self):
                return data

        return Stream()

    def close(self):
        pass


def test_dochan_extracts_text_from_distribution_document(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", FakeDistributionOle)
    path = tmp_path / "distributed.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = Dochan(str(path))

    assert "배포용 문서 본문 텍스트" in doc.to_plain_text()
    assert not any("파싱 실패" in err for err in doc.errors)
