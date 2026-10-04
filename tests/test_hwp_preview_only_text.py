"""본문 레코드에 글자가 없는데 미리보기(PrvText)에만 글자가 있으면 조용히 빈 출력을 내지 않는다."""
import struct

from dochan import Dochan
from test_hwp_revision_reader import TrackedOle, _record


class PreviewOnlyOle(TrackedOle):
    no_view = True
    preview = "계약서 본문 미리보기"

    def __init__(self, path):
        super().__init__(path)
        header = bytearray(self.streams["FileHeader"])
        struct.pack_into("<I", header, 36, 0)  # 압축·변경 추적 플래그 없음
        self.streams["FileHeader"] = bytes(header)
        self.streams["DocInfo"] = b""
        self.streams["BodyText/Section0"] = _record(66, 0, bytes(22))
        if self.preview is not None:
            self.streams["PrvText"] = self.preview.encode("utf-16-le")


class NoPreviewOle(PreviewOnlyOle):
    preview = None


class EmptyTablePreviewOle(PreviewOnlyOle):
    preview = "<><><>\r\n<>"


def _read(monkeypatch, tmp_path, ole):
    monkeypatch.setattr("dochan.reader.cfb.OleFileIO", ole)
    path = tmp_path / "preview.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    return Dochan(str(path))


def test_preview_text_without_body_text_warns(monkeypatch, tmp_path):
    parsed = _read(monkeypatch, tmp_path, PreviewOnlyOle)
    assert not parsed.to_plain_text().strip()
    assert any("PrvText" in error and error.startswith("WARN:") for error in parsed.doc.errors)


def test_empty_document_without_preview_text_stays_quiet(monkeypatch, tmp_path):
    parsed = _read(monkeypatch, tmp_path, NoPreviewOle)
    assert not any("PrvText" in error for error in parsed.doc.errors)


def test_preview_with_only_empty_table_markers_stays_quiet(monkeypatch, tmp_path):
    parsed = _read(monkeypatch, tmp_path, EmptyTablePreviewOle)
    assert not any("PrvText" in error for error in parsed.doc.errors)
