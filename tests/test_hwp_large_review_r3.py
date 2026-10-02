"""3차 리뷰: 소진된 변경 추적 예산과 배포용 오류 계약을 검증한다."""
import struct
import zlib

import pytest

from dochan.hwp.distdoc import _compressed_payload, decode_distribution_section
from dochan.hwp.section import SectionParser
from conftest import build_distdoc_view_text_stream
from test_hwp_large_review import _reader
from test_hwp_revision_reader import TrackedOle, _section


def test_exhausted_tracked_document_does_not_repeat_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 10)
    opened = []
    original = TrackedOle.openstream

    def counted(self, name):
        opened.append(name)
        return original(self, name)

    monkeypatch.setattr(TrackedOle, "openstream", counted)
    streams = {}
    for index in range(1000):
        streams["ViewText/Section%d" % index] = _section("view")
        streams["BodyText/Section%d" % index] = _section("body")
    reader = _reader(monkeypatch, tmp_path, streams, flags=1 << 14)
    assert len(reader.doc.sections) == 1000
    assert [e.text for s in reader.doc.sections for e in s.elements] == ["view"] * 5
    assert len(reader.errors) == 1
    assert "document record count" in reader.errors[0]
    assert not any(name.startswith("BodyText/") for name in opened)


def test_exhausted_record_budget_skips_decompression(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 2)
    parser = SectionParser()
    assert parser.parse_stream(_section("view"), False).elements
    for _ in range(3):
        assert not parser.parse_stream(b"\xff", True, reject_record_limit=True).elements
    assert len(parser.errors) == 1


@pytest.mark.parametrize("damage,expected", [
    ("invalid", "Invalid distribution DEFLATE stream"),
    ("truncated", "Truncated distribution DEFLATE stream"),
])
def test_distribution_error_contract_keeps_inflated(damage, expected):
    # A non-final stored block emits 11 bytes. Its AES-aligned last byte
    # either begins an invalid block or leaves the next block truncated.
    prefix = b"\x00" + struct.pack("<HH", 11, 0xffff ^ 11) + b"x" * 11
    payload = prefix + (b"\x07" if damage == "invalid" else b"")
    raw = build_distdoc_view_text_stream(1, bytes(range(16)), payload)
    with pytest.raises(ValueError, match="^" + expected + "$") as caught:
        decode_distribution_section(raw, is_compressed=True, decompress=True)
    assert 11 <= caught.value.inflated <= 12


def test_distribution_size_error_contract_keeps_budget_accounting(monkeypatch):
    compressor = zlib.compressobj(wbits=-15)
    payload = compressor.compress(b"x" * 100) + compressor.flush()
    with pytest.raises(ValueError, match="^Distribution decompressed size exceeds limit$") as caught:
        _compressed_payload(payload, max_size=10, decompress=True)
    assert caught.value.inflated == 11
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", 10)
    parser = SectionParser()
    assert not parser.parse_stream(
        payload, True,
        distribution_decoder=lambda data, **kw: _compressed_payload(
            data, max_size=kw["max_size"], decompress=True),
    ).elements
    assert parser._document_bytes == 10
    assert len(parser.errors) == 1
    assert "document size limit exhausted" in parser.errors[0]
