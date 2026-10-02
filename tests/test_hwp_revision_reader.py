"""HWP 변경 추적 ViewText와 DocInfo를 통합 진입점에서 읽는다."""
import io
import struct

import pytest

from dochan import Dochan


def _record(tag, level, data):
    return struct.pack("<I", tag | level << 10 | len(data) << 20) + data


def _section(text, ranges=b""):
    return (_record(66, 0, bytes(22)) + _record(67, 1, (text + "\r").encode("utf-16-le"))
            + (_record(70, 1, ranges) if ranges else b""))


def _metadata():
    def change(kind):
        return struct.pack("<I6H6sI", kind, 2026, 10, 2, 10, 30, 1, bytes(6), int(kind == 0x11))
    return (_record(96, 0, change(0x10)) + _record(96, 0, change(0x11))
            + _record(97, 0, struct.pack("<I", 4) + "user".encode("utf-16-le") + bytes(8)))


class TrackedOle:
    no_view = False
    encrypted = False

    def __init__(self, path):
        header = bytearray(256)
        header[:32] = b"HWP Document File".ljust(32, b"\x00")
        struct.pack_into("<BBBBI", header, 32, 0, 0, 0, 5,
                         (1 << 14) | (2 if self.encrypted else 0))
        self.streams = {"FileHeader": bytes(header), "DocInfo": _metadata(),
                        "BodyText/Section0": _section("aNEWz")}
        if not self.no_view:
            self.streams["ViewText/Section0"] = _section(
                "aNEWoldz", struct.pack("<6I", 1, 4, 0x10000001, 4, 7, 0x11000002))

    def exists(self, name):
        return name in self.streams

    def openstream(self, name):
        return io.BytesIO(self.streams[name])

    def get_size(self, name):
        return len(self.streams[name])

    def listdir(self, **kwargs):
        return [name.split('/') for name in self.streams]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@pytest.mark.parametrize("mode,expected", [("preserve", "aNEWoldz"), ("final", "aNEWz"), ("original", "aoldz")])
def test_reader_projects_tracked_view_without_distribution_decryption(monkeypatch, tmp_path, mode, expected):
    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", TrackedOle)
    def forbidden(*args, **kwargs):
        pytest.fail("tracked ViewText must not use distribution AES")
    monkeypatch.setattr("dochan.reader.decode_distribution_section", forbidden)
    path = tmp_path / "tracked.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    reader = Dochan(path, revision_mode=mode)
    assert reader.doc.sections[0].elements[0].text == expected
    assert not reader.errors


def test_missing_tracked_view_keeps_body_and_reports_original_failure(monkeypatch, tmp_path):
    class MissingView(TrackedOle):
        no_view = True
    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", MissingView)
    path = tmp_path / "missing-view.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    reader = Dochan(path, revision_mode="original")
    assert reader.doc.sections[0].elements[0].text == "aNEWz"
    assert any(error.startswith("ERR:") and "ViewText missing" in error for error in reader.errors)


def test_unresolved_nondefault_revision_is_an_error():
    from dochan.hwp.records.para_text import parse_para_text
    from dochan.hwp.revisions import project_text_result
    errors = []
    text = parse_para_text("body\r".encode("utf-16-le"))
    projected = project_text_result(text, [struct.pack("<III", 0, 4, 0x10000001)], {}, "original", errors)
    assert projected == text
    assert all(error.startswith("ERR:") for error in errors)


def test_password_protected_document_still_has_clear_error(monkeypatch, tmp_path):
    class PasswordOle(TrackedOle):
        encrypted = True
    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", PasswordOle)
    path = tmp_path / "password.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    reader = Dochan(path)
    assert not reader.doc.sections
    assert any(error.startswith("ERR:") and "암호화" in error for error in reader.errors)


def test_final_reads_body_without_opening_tracked_view(monkeypatch, tmp_path):
    class FinalBodyOle(TrackedOle):
        def __init__(self, path):
            super().__init__(path)
            # BodyText is authoritative even when stored ViewText is stale.
            self.streams["BodyText/Section0"] = _section(
                "FINAL BODY", struct.pack("<III", 0, 5, 0x11000002))

        def openstream(self, name):
            assert not name.startswith("ViewText/"), "final must not load marked ViewText"
            return super().openstream(name)

    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", FinalBodyOle)
    path = tmp_path / "final-body.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    reader = Dochan(path, revision_mode="final")
    assert reader.doc.sections[0].elements[0].text == "FINAL BODY"
    assert not reader.errors


def test_preserve_without_change_metadata_ignores_stray_range_tags():
    from dochan.hwp.records.para_text import parse_para_text
    from dochan.hwp.revisions import project_text_result
    errors = []
    text = parse_para_text("body\r".encode("utf-16-le"))
    result = project_text_result(text, [struct.pack("<III", 0, 4, 0x10000001)], {}, "preserve", errors)
    assert result is text
    assert errors == []


@pytest.mark.parametrize("mode", ["preserve", "original"])
def test_revision_problem_warning_is_deduplicated_across_paragraphs(mode):
    from dochan.hwp.records.para_text import parse_para_text
    from dochan.hwp.revisions import Change, project_text_result
    errors = []
    text = parse_para_text("body\r".encode("utf-16-le"))
    changes = {2: Change("Insert", 1, (2026, 10, 2, 10, 30), False)}
    for _ in range(1000):
        project_text_result(text, [struct.pack("<III", 0, 4, 0x10000001)], changes, mode, errors)
    assert len(errors) == 1
    assert "[reference]" in errors[0]
