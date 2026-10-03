"""Synthetic [MS-OLEPS] metadata and legacy reader contract tests."""
import struct

import pytest

from dochan.office_binary.summary_info import parse_summary_information
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.ppt import PPTReader
from dochan.output.markdown import to_markdown
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.header_footer import HeaderFooter
from dochan.conversion import Provenance


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


@pytest.mark.parametrize("codepage,encoding,title", [
    (51949, "euc_kr", "계획서"), (54936, "gb18030", "计划"),
    (10007, "mac_cyrillic", "План"), (20127, "ascii", "Plan"),
    (10006, "mac_greek", "Αθήνα"), (10029, "mac_latin2", "Čas"),
    (10079, "mac_iceland", "Ísland"), (10081, "mac_turkish", "İzmir"),
    (28591, "iso8859_1", "Café"), (28599, "iso8859_9", "İzmir"),
    (65001, "utf-8", "계획"), (10003, "euc_kr", "계획서"), (20866, "koi8_r", "План"),
    (51932, "euc_jp", "計画"), (28605, "iso8859_15", "Œuvre €"),
])
def test_summary_information_decodes_additional_valid_codepages(codepage, encoding, title):
    encoded = (title + "\0").encode(encoding)
    data = _summary_with_encoded_title(encoded, codepage)
    assert parse_summary_information(data, "DOC")["title"] == title


def _summary_with_encoded_title(encoded, codepage):
    entries = [(1, struct.pack("<IH", 2, codepage) + b"\0\0"),
               (2, _property(30, encoded, len(encoded))),
               (4, _property(30, b"Alice\0", 6))]
    offset = 8 + 8 * len(entries)
    table = []
    for identifier, value in entries:
        table.append(struct.pack("<II", identifier, offset))
        offset += len(value)
    section = struct.pack("<II", offset, len(entries)) + b"".join(table)
    section += b"".join(value for _, value in entries)
    return b"\xfe\xff\0\0" + b"\0" * 20 + struct.pack("<I", 1) + FMTID_SUMMARY + struct.pack("<I", 48) + section


def test_unknown_codepage_warns_before_fallback():
    errors = []
    assert parse_summary_information(_summary(), "DOC", errors)["title"] == "Board"
    data = _summary().replace(struct.pack("<H", 1252), struct.pack("<H", 65534), 1)
    assert parse_summary_information(data, "DOC", errors)["title"] == "Board"
    assert any("code page" in error for error in errors)


def test_unknown_codepage_without_codepage_strings_does_not_warn():
    errors = []
    data = _summary(wide=True).replace(struct.pack("<H", 1252), struct.pack("<H", 65534), 1)
    assert parse_summary_information(data, "DOC", errors)["title"] == "Board"
    assert errors == []


def test_empty_summary_stream_is_ignored_without_warning():
    from dochan.office_binary.summary_info import read_summary_elements
    from dochan.utils.bounded_io import ByteBudget
    from io import BytesIO

    class Ole:
        def exists(self, name):
            return True

        def openstream(self, name):
            return BytesIO(b"")

    errors = []
    assert read_summary_elements(Ole(), "DOC", errors, ByteBudget(1024)) == []
    assert errors == []


def test_doc_structure_path_places_properties_after_header(monkeypatch, tmp_path):
    from io import BytesIO

    word = bytearray(64)
    word[:2] = b"\xec\xa5"

    class Ole:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in ("WordDocument", "0Table", "\x05SummaryInformation")

        def openstream(self, name):
            return BytesIO({"WordDocument": bytes(word), "0Table": b"table",
                            "\x05SummaryInformation": _summary()}[name])

        def close(self):
            pass

    calls = []

    def structured(word_data, table_data, load_data, **kwargs):
        calls.append(table_data)
        return Document(source_format="doc", sections=[Section(elements=[
            HeaderFooter(type="header", paragraphs=[Paragraph(runs=[TextRun("Head")])]),
            Paragraph(runs=[TextRun("Body")]),
        ])])

    monkeypatch.setattr("dochan.office_binary.doc.cfb.OleFileIO", Ole)
    monkeypatch.setattr("dochan.office_binary.doc_structure.parse_structured_doc", structured)
    path = tmp_path / "structure.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    doc = DOCReader().read(str(path))
    assert calls == [b"table"]
    assert [type(e).__name__ for e in doc.sections[0].elements] == [
        "HeaderFooter", "Paragraph", "Paragraph", "Paragraph"]
    assert [e.text for e in doc.sections[0].elements[1:]] == ["Board", "Author: Alice", "Body"]


def test_doc_text_candidate_path_places_properties_before_body(monkeypatch, tmp_path):
    from io import BytesIO

    word = bytearray(64)
    word[:2] = b"\xec\xa5"

    class Ole:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in ("WordDocument", "0Table", "\x05SummaryInformation")

        def openstream(self, name):
            return BytesIO({"WordDocument": bytes(word), "0Table": b"table",
                            "\x05SummaryInformation": _summary()}[name])

        def close(self):
            pass

    # The native structure is unavailable, so the scored text candidate wins.
    monkeypatch.setattr("dochan.office_binary.doc.cfb.OleFileIO", Ole)
    monkeypatch.setattr("dochan.office_binary.doc_structure.parse_structured_doc",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr("dochan.office_binary.doc._extract_piece_table_lines",
                        lambda word_data, table_data: ["Body"])
    monkeypatch.setattr("dochan.office_binary.doc.parse_doc_word_stream",
                        lambda word_data, table_data=None: Document(
                            source_format="doc",
                            sections=[Section(elements=[Paragraph(runs=[TextRun("Body")])])]))
    path = tmp_path / "candidate.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    doc = DOCReader().read(str(path))
    assert [e.text for e in doc.sections[0].elements] == ["Board", "Author: Alice", "Body"]
    assert any("structure unavailable" in error for error in doc.errors)


def test_doc_fib_encryption_blocks_plaintext_properties(monkeypatch, tmp_path):
    from io import BytesIO
    word = bytearray(64)
    word[:2] = b"\xec\xa5"
    struct.pack_into("<H", word, 10, 0x0100)

    class Ole:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in ("WordDocument", "0Table", "\x05SummaryInformation")

        def openstream(self, name):
            return BytesIO({"WordDocument": bytes(word), "0Table": b"bad",
                            "\x05SummaryInformation": _summary()}[name])

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.doc.cfb.OleFileIO", Ole)
    path = tmp_path / "encrypted.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    for password in (None, "wrong"):
        doc = DOCReader(password=password).read(str(path))
        assert doc.sections == []
        assert any(error.startswith("ERR:") for error in doc.errors)


def test_ppt_decryption_failure_blocks_plaintext_properties(monkeypatch, tmp_path):
    from io import BytesIO

    class Ole:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name in ("PowerPoint Document", "Current User", "\x05SummaryInformation")

        def openstream(self, name):
            return BytesIO({"PowerPoint Document": b"encrypted", "Current User": b"current",
                            "\x05SummaryInformation": _summary()}[name])

        def close(self):
            pass

    def rejected(*args):
        raise ValueError("PPT password required")

    monkeypatch.setattr("dochan.office_binary.ppt.cfb.OleFileIO", Ole)
    monkeypatch.setattr("dochan.crypto.ppt.decrypt_presentation", rejected)
    path = tmp_path / "encrypted.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    for password in (None, "wrong"):
        doc = PPTReader(password=password).read(str(path))
        assert doc.sections == []
        assert any(error.startswith("ERR:") for error in doc.errors)


def test_probe_separates_metadata_after_header(monkeypatch, tmp_path):
    from scripts import probe_legacy_docprops as probe
    from dochan.output.markdown import to_markdown

    header = HeaderFooter(type="header", paragraphs=[Paragraph(runs=[TextRun("Head")])])
    property_element = Paragraph(runs=[TextRun("Author: Alice")],
                                 provenance=Provenance(source_format="doc", path="\x05SummaryInformation"))
    body = Paragraph(runs=[TextRun("Body")])
    doc = Document(source_format="doc", sections=[Section(elements=[header, property_element, body])])
    markdown = to_markdown(doc)

    class Converted:
        def __init__(self, path):
            self.doc = doc

        def to_markdown(self):
            return markdown

        def to_json(self):
            return "{}"

    monkeypatch.setattr(probe, "Dochan", Converted)
    result = probe.snapshot(tmp_path / "synthetic.doc", include_json=True)
    assert result["metadata"] == ["Author: Alice"]
    assert result["metadata_positions"] == [1]
    assert result["header_positions"] == [0]
    assert result["body_sha256"] == probe._digest(to_markdown(
        Document(source_format="doc", sections=[Section(elements=[header, body])])))
