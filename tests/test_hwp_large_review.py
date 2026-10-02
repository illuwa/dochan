"""리뷰에서 재현된 문서 예산·손상 섹션·배포용 검증 회귀."""
import struct
import zlib

import pytest

from dochan import Dochan
from dochan.hwp.section import HWPRecordLimitError, SectionParser
from test_hwp_large_limits import _deflate
from test_hwp_revision_reader import TrackedOle, _record, _section
from test_hwp_distribution_trailer import _stream


@pytest.mark.parametrize("damage", ["invalid", "truncated", "checksum"])
def test_damaged_section_keeps_following_sections(monkeypatch, damage):
    data = _section("body")
    compressed = _deflate(data)
    damaged = {"invalid": b"\xff", "truncated": compressed[:-1],
               "checksum": compressed + struct.pack("<II", 1, len(data))}[damage]
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", len(data) * 4)
    parser = SectionParser()
    with pytest.raises((ValueError, zlib.error)):
        parser.parse_stream(damaged, True)
    for _ in range(3):
        assert parser.parse_stream(compressed, True).elements[0].text == "body"
    assert parser._document_bytes <= len(data) * 4


def test_repeated_crc_failure_spends_only_emitted_bytes(monkeypatch):
    data = _section("body")
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", len(data) * 2)
    parser = SectionParser()
    for expected in (len(data), len(data) * 2):
        with pytest.raises(ValueError, match="checksum"):
            parser.parse_stream(_deflate(data) + struct.pack("<II", 1, len(data)), True)
        assert parser._document_bytes == expected
    assert not parser.parse_stream(_deflate(data), True).elements


@pytest.mark.parametrize("budget", ["bytes", "records"])
def test_exhausted_document_reports_limit_only_once(monkeypatch, budget):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_" + budget.upper(), 0)
    parser = SectionParser()
    for _ in range(1000):
        parser.parse_stream(_deflate(_section("body")), True)
    assert len(parser.errors) == 1
    assert "document" in parser.errors[0]
    assert "(0 bytes)" not in parser.errors[0]


def test_document_record_limit_rejects_view_before_building_model(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 1)
    parser = SectionParser()
    with pytest.raises(HWPRecordLimitError, match="document record"):
        parser.parse_stream(_section("view"), False, reject_record_limit=True)
    assert parser._document_records == 1


def test_default_record_caps_match_measured_policy():
    from dochan.hwp import doc_info, section
    assert section.MAX_HWP_RECORDS == 1_000_000
    assert section.MAX_HWP_DOCUMENT_RECORDS == 1_300_000
    assert doc_info.MAX_HWP_RECORDS == 200_000


def _reader(monkeypatch, tmp_path, streams, flags):
    class FixtureOle(TrackedOle):
        def __init__(self, path):
            header = bytearray(256)
            header[:32] = b"HWP Document File".ljust(32, b"\0")
            struct.pack_into("<BBBBI", header, 32, 0, 0, 0, 5, flags)
            self.streams = dict(streams, FileHeader=bytes(header),
                                DocInfo=_deflate(b"") if flags & 1 else b"")
    monkeypatch.setattr("dochan.reader.cfb.OleFileIO", FixtureOle)
    path = tmp_path / "synthetic.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    return Dochan(path)


def test_distribution_failures_share_document_inflation_budget(monkeypatch, tmp_path):
    data = _section("body")
    raw, _ = _stream(data, "crc")
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", len(data) * 2)
    streams = {"ViewText/Section%d" % index: raw for index in range(5)}
    reader = _reader(monkeypatch, tmp_path, streams, flags=5)
    # Only two streams reach trailer validation; later ones share one budget error.
    assert len([e for e in reader.errors if "CRC32" in e]) == 2
    assert len([e for e in reader.errors if "document" in e and "limit" in e]) == 1


def test_distribution_success_inflates_once(monkeypatch, tmp_path):
    data = _section("body")
    raw, _ = _stream(data)
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", len(data))
    original = zlib.decompressobj
    outputs = []
    class MeasuredInflater:
        def __init__(self, *args, **kwargs):
            self.inner = original(*args, **kwargs)
        def decompress(self, *args, **kwargs):
            result = self.inner.decompress(*args, **kwargs)
            outputs.append(len(result))
            return result
        def __getattr__(self, name):
            return getattr(self.inner, name)
    monkeypatch.setattr(zlib, "decompressobj", MeasuredInflater)
    reader = _reader(monkeypatch, tmp_path, {"ViewText/Section0": raw}, flags=5)
    assert reader.doc.sections[0].elements[0].text == "body"
    assert not reader.errors
    assert sum(outputs) == len(data)


def test_document_record_limit_attempts_body_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 1)
    reader = _reader(monkeypatch, tmp_path, {
        "ViewText/Section0": _section("view"),
        "BodyText/Section0": _section("fallback"),
    }, flags=1 << 14)
    assert any("ViewText/Section0 record limit" in e for e in reader.errors)
    assert any("document record count" in e for e in reader.errors)


def test_docinfo_stops_at_original_cap():
    from dochan.hwp.doc_info import DocInfoParser
    data = _record(1023, 0, b"") * 200_000 + _record(16, 0, struct.pack("<H", 7))
    info = DocInfoParser().parse_stream(data, False)
    assert info.section_count == 0
    assert info.errors == ["ERR: HWP DocInfo record count exceeds limit: more than 200000"]
