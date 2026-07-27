"""
tests/test_reader_magic_byte_fallback.py — 확장자/실제 내용 불일치 폴백 테스트

docs/benchmarks/2026-07-27-hwp-corpus-collection-and-quality-scan.md finding #3:
공공 웹사이트에서 내려받은 파일 중 일부는 확장자가 실제 내용과 다르다
(예: 파일명은 .hwp인데 실제로는 ZIP/HWPX, 또는 그 반대). Dochan() 은 지금까지
확장자만으로 파서를 정하고 실패하면 그대로 에러를 냈다 — 매직바이트를 한 번 더
확인해서 실제 포맷에 맞는 파서로 보정해야 한다.
"""
import struct

from dochan import Dochan

from test_hwpx_reader import _write_hwpx, _section, _para, _run


def _file_header_bytes() -> bytes:
    data = bytearray(256)
    data[0:32] = b"HWP Document File".ljust(32, b"\x00")
    struct.pack_into("<BBBB", data, 32, 0, 0, 0, 5)  # major version 5
    struct.pack_into("<I", data, 36, 0)  # 비압축, 배포용 아님
    return bytes(data)


def _para_section_bytes(text: str) -> bytes:
    HWPTAG_PARA_HEADER = 66
    HWPTAG_PARA_TEXT = 67
    text_bytes = text.encode("utf-16-le") + struct.pack("<H", 13)
    para_header_payload = bytes(22)
    text_record = struct.pack("<I", (len(text_bytes) << 20) | (1 << 10) | HWPTAG_PARA_TEXT) + text_bytes
    header_record = struct.pack("<I", (len(para_header_payload) << 20) | (0 << 10) | HWPTAG_PARA_HEADER) + para_header_payload
    return header_record + text_record


class FakeHwpOle:
    """확장자 없이 순수 HWP OLE 구조만 흉내내는 최소 FakeOle (비압축)."""

    def __init__(self, path):
        self.path = path

    def exists(self, name):
        return name in ("FileHeader", "DocInfo", "BodyText/Section0")

    def openstream(self, name):
        if name == "FileHeader":
            data = _file_header_bytes()
        elif name == "DocInfo":
            data = b""  # 비압축이므로 그대로 빈 DocInfo
        elif name == "BodyText/Section0":
            data = _para_section_bytes("확장자는 hwpx지만 실제로는 HWP")
        else:
            raise IOError(f"unexpected stream: {name}")

        class Stream:
            def read(self):
                return data

        return Stream()

    def close(self):
        pass


def test_dochan_falls_back_to_hwpx_when_hwp_extension_holds_zip_content(tmp_path):
    """파일명은 .hwp 인데 실제 바이트는 ZIP(HWPX) — 흔한 출처 표기 실수."""
    path = tmp_path / "mislabeled.hwp"
    _write_hwpx(path, _section(_para(_run('<hp:t>%s</hp:t>' % "실제로는 HWPX 내용"))))

    doc = Dochan(str(path))

    assert "실제로는 HWPX 내용" in doc.to_plain_text()
    assert not any("OLE 파일 열기 실패" in err for err in doc.errors)


def test_dochan_falls_back_to_hwp_when_hwpx_extension_holds_ole_content(monkeypatch, tmp_path):
    """파일명은 .hwpx 인데 실제 바이트는 OLE2(HWP) — 흔한 출처 표기 실수."""
    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", FakeHwpOle)
    path = tmp_path / "mislabeled.hwpx"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake-ole-body")

    doc = Dochan(str(path))

    assert "확장자는 hwpx지만 실제로는 HWP" in doc.to_plain_text()
    assert not any("유효하지 않은 HWPX 파일" in err for err in doc.errors)
