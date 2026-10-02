"""Large HWP streams and bounded adversarial inputs, assembled without corpus data."""
import os
from pathlib import Path
import struct
import zlib

import pytest

from dochan import Dochan
from dochan.hwp.doc_info import DocInfoParser
from dochan.hwp.section import HWPRecordLimitError, RawRecord, SectionParser
from test_hwp_revision_reader import _section


def _deflate(data):
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


@pytest.mark.parametrize("compressed", [False, True])
def test_large_section_preserves_every_paragraph_and_tail(compressed):
    data = _section("body") * 100_001 + _section("END")
    parser = SectionParser()
    section = parser.parse_stream(_deflate(data) if compressed else data, compressed)
    assert len(section.elements) == 100_002
    assert section.elements[-1].text == "END"
    assert not parser.errors


def test_large_doc_info_preserves_last_record():
    data = struct.pack("<I", 1023) * 199_999 + struct.pack("<IH", 16 | (2 << 20), 7)
    info = DocInfoParser().parse_stream(data, False)
    assert info.section_count == 7
    assert not info.errors


@pytest.mark.parametrize("parser_class,module", [
    (SectionParser, "dochan.hwp.section"), (DocInfoParser, "dochan.hwp.doc_info"),
])
@pytest.mark.parametrize("compressed", [False, True])
def test_stream_byte_limit_includes_uncompressed_input(monkeypatch, parser_class, module, compressed):
    monkeypatch.setattr(module + ".MAX_DECOMPRESSED_SIZE", 8, raising=False)
    parser = parser_class()
    data = struct.pack("<I", 1023) * 3
    result = parser.parse_stream(_deflate(data) if compressed else data, compressed)
    errors = parser.errors if isinstance(parser, SectionParser) else result.errors
    assert any("size" in e.lower() and "limit" in e.lower() for e in errors)


def test_document_record_budget_cannot_be_reset_by_next_section(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 4, raising=False)
    parser = SectionParser()
    assert parser.parse_stream(_section("first"), False).elements[0].text == "first"
    assert parser.parse_stream(_section("second"), False).elements[0].text == "second"
    assert not parser.parse_stream(_section("rejected"), False).elements
    assert any("document record count" in e for e in parser.errors)


def test_document_byte_budget_is_cumulative(monkeypatch):
    data = _section("same")
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", len(data) * 2, raising=False)
    parser = SectionParser()
    for _ in range(2):
        assert parser.parse_stream(_deflate(data), True).elements
    assert not parser.parse_stream(_deflate(data), True).elements
    assert any("size" in e.lower() and "limit" in e.lower() for e in parser.errors)


@pytest.mark.parametrize("damage", ["truncated", "checksum", "invalid"])
def test_failed_inflation_cannot_restart_document_work_budget(monkeypatch, damage):
    data = _section("same")
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_BYTES", len(data) * 2)
    compressed = _deflate(data)
    if damage == "truncated":
        compressed = compressed[:-1]
    elif damage == "checksum":
        compressed += struct.pack("<II", 1, len(data))
    else:
        compressed = b"\xff"
    parser = SectionParser()
    with pytest.raises((ValueError, zlib.error)):
        parser.parse_stream(compressed, True)
    # The failed stream spends only emitted bytes; corruption must not erase
    # unrelated sections. Repeated CRC failures are covered separately.
    assert parser.parse_stream(_deflate(data), True).elements[0].text == "same"
    assert parser._document_bytes <= len(data) * 2


def test_rejected_view_attempt_still_consumes_document_work_budget(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_RECORDS", 3)
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 4, raising=False)
    parser = SectionParser()
    with pytest.raises(HWPRecordLimitError):
        parser.parse_stream(_section("view") * 2, False, reject_record_limit=True)
    parser.parse_stream(_section("fallback"), False)
    assert any("document record count" in e for e in parser.errors)


def test_record_boundary_rejects_first_excess_record_deterministically(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_RECORDS", 4)
    data = _section("ok") * 2
    parser = SectionParser()
    assert len(parser.parse_stream(data, False).elements) == 2
    assert not parser.errors
    for _ in range(2):
        parser = SectionParser()
        parser.parse_stream(data + struct.pack("<I", 1023), False)
        assert parser.errors == ["ERR: HWP section record count exceeds limit: more than 4"]


def test_empty_list_header_repair_does_not_repeatedly_shift_siblings():
    class MeasuredList(list):
        shifted = 0

        def pop(self, index=-1):
            self.shifted += len(self) - index - 1 if index >= 0 else 0
            return super().pop(index)

    nodes = MeasuredList()
    for group in range(100):
        nodes.append(dict(record=RawRecord(72, 0, 0, b"", group), children=[]))
        for item in range(100):
            nodes.append(dict(record=RawRecord(66, 0, 0, b"", item), children=[]))
    original_count = len(nodes)
    SectionParser()._fix_empty_list_headers(nodes)
    assert len(nodes) == 100
    assert all([c["record"].offset for c in node["children"]] == list(range(100))
               for node in nodes)
    assert nodes.shifted <= original_count


def test_public_large_document_when_available():
    root = os.environ.get("DOCHAN_HWP_PUBLIC")
    if not root:
        pytest.skip("DOCHAN_HWP_PUBLIC is not configured")
    path = Path(root) / "hwp" / "rhwp-1130000-201900011_D0150004-1-002_2017년기준_시장구조조사.hwp"
    if not path.is_file():
        pytest.skip("public large HWP is absent")
    for mode, markdown_length in (("preserve", 529_172), ("final", 529_136)):
        reader = Dochan(path, revision_mode=mode)
        assert not [error for error in reader.errors if error.startswith("ERR:")]
        assert len(reader.to_plain_text()) == 402_642
        assert len(reader.to_markdown()) == markdown_length
