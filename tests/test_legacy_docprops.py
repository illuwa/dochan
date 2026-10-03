"""Synthetic [MS-OLEPS] metadata and legacy reader contract tests."""
import struct

import pytest

from dochan.office_binary.summary_info import parse_summary_information
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.ppt import PPTReader
from dochan.output.markdown import to_markdown


FMTID_SUMMARY = bytes.fromhex("e0859ff2f94f6810ab9108002b27b3d9")


def _property(value_type, payload, count):
    return struct.pack("<II", value_type, count) + payload


def _summary(title="Board", author="Alice", codepage=1252, fmtid=FMTID_SUMMARY,
             wide=False):
    encoding = ("utf-16-le" if wide or codepage == 1200
                else "mac_roman" if codepage == 10000 else "cp1252")
    value_type = 31 if wide else 30
    entries = [
        (1, struct.pack("<IH", 2, codepage) + b"\0\0"),
        (2, _property(value_type, (title + "\0").encode(encoding),
                      len(title) + 1 if wide else len((title + "\0").encode(encoding)))),
        (4, _property(value_type, (author + "\0").encode(encoding),
                      len(author) + 1 if wide else len((author + "\0").encode(encoding)))),
    ]
    table_size = 8 + 8 * len(entries)
    offset = table_size
    table = []
    values = []
    for identifier, value in entries:
        table.append(struct.pack("<II", identifier, offset))
        values.append(value)
        offset += len(value)
    section = struct.pack("<II", offset, len(entries)) + b"".join(table) + b"".join(values)
    return (b"\xfe\xff\0\0" + b"\0" * 20 + struct.pack("<I", 1)
            + fmtid + struct.pack("<I", 48) + section)


def test_summary_information_decodes_lpstr_lpwstr_and_codepages():
    assert parse_summary_information(_summary("Café", "René"), "DOC") == {
        "title": "Café", "creator": "René"}
    assert parse_summary_information(_summary("Résumé", "André", codepage=10000), "PPT") == {
        "title": "Résumé", "creator": "André"}
    assert parse_summary_information(_summary("계획", "홍길동", codepage=1200, wide=True), "DOC") == {
        "title": "계획", "creator": "홍길동"}
    assert parse_summary_information(_summary("계획", "홍길동", codepage=1200), "DOC") == {
        "title": "계획", "creator": "홍길동"}
    assert parse_summary_information(_summary("A\0hidden", "Alice"), "DOC")["title"] == "A"


def test_summary_information_rejects_wrong_fmtid_and_truncation_with_warning():
    for data in (_summary(fmtid=b"\0" * 16), _summary()[:-2]):
        errors = []
        assert parse_summary_information(data, "DOC", errors) == {}
        assert errors == ["WARN: DOC malformed SummaryInformation ignored"]


@pytest.mark.parametrize("reader,module,stream,body", [
    (DOCReader, "doc", "WordDocument", "Body text".encode("utf-16-le")),
    (PPTReader, "ppt", "PowerPoint Document",
     struct.pack("<HHI", 0, 4000, 18) + "Body text".encode("utf-16-le")),
])
def test_legacy_document_properties_precede_body(monkeypatch, tmp_path, reader, module, stream, body):
    class FakeOle:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in (stream, "\x05SummaryInformation")

        def openstream(self, name):
            from io import BytesIO
            return BytesIO(_summary() if name == "\x05SummaryInformation" else body)

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.%s.cfb.OleFileIO" % module, FakeOle)
    path = tmp_path / ("synthetic." + module)
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    doc = reader().read(str(path))
    assert to_markdown(doc).startswith("# Board\n\nAuthor: Alice\n\nBody text")
    assert [p.provenance.path for p in doc.sections[0].elements[:2]] == [
        "\x05SummaryInformation", "\x05SummaryInformation"]


@pytest.mark.parametrize("reader,module,stream", [
    (DOCReader, "doc", "WordDocument"),
    (PPTReader, "ppt", "PowerPoint Document"),
])
def test_encrypted_legacy_document_does_not_emit_plaintext_properties(
        monkeypatch, tmp_path, reader, module, stream):
    class FakeOle:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in (stream, "\x05SummaryInformation")

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.%s.cfb.OleFileIO" % module, FakeOle)
    monkeypatch.setattr("dochan.office_binary.%s.is_encrypted_container" % module,
                        lambda ole: True)
    path = tmp_path / ("encrypted." + module)
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    doc = reader().read(str(path))
    assert doc.sections == []
    assert any(error.startswith("ERR:") for error in doc.errors)
