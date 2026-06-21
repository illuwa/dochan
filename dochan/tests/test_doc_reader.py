import struct

from dochan import Dochan
from dochan.cli import _cmd_info
from dochan.office_binary.doc import DOCReader
from dochan.output.markdown import to_markdown


class FakeOle:
    def __init__(self, path):
        self.path = path

    def exists(self, name):
        return name == "WordDocument"

    def openstream(self, name):
        class Stream:
            def read(self):
                return "Legacy Word\n본문 텍스트".encode("utf-16-le")

        return Stream()

    def close(self):
        pass


def test_doc_reader_extracts_utf16_text(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", FakeOle)
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert doc.metadata["source_format"] == "doc"
    assert doc.sections[0].elements[0].text == "Legacy Word"
    assert doc.sections[0].elements[1].text == "본문 텍스트"


def test_doc_reader_uses_fib_text_range_when_available(monkeypatch, tmp_path):
    class FibOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    prefix = bytearray("Binary junk\n".encode("utf-16-le") + b"\x00" * 64)
                    fc_min = 96
                    text = "Scoped Body\nOnly this text".encode("utf-16-le")
                    fc_mac = fc_min + len(text)
                    if len(prefix) < fc_min:
                        prefix.extend(b"\x00" * (fc_min - len(prefix)))
                    struct.pack_into("<I", prefix, 0x18, fc_min)
                    struct.pack_into("<I", prefix, 0x1C, fc_mac)
                    return bytes(prefix[:fc_min]) + text + "Trailing junk".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", FibOle)
    path = tmp_path / "fib.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Scoped Body", "Only this text"]


def _doc_piece_table(cps, pieces):
    body = b"".join(struct.pack("<I", cp) for cp in cps)
    for fc_encoded in pieces:
        body += struct.pack("<HIH", 0, fc_encoded, 0)
    return b"\x02" + struct.pack("<I", len(body)) + body


def _doc_piece_table_segments(segments):
    return b"".join(_doc_piece_table(cps, pieces) for cps, pieces in segments)


def test_doc_reader_uses_clx_piece_table_from_table_stream(monkeypatch, tmp_path):
    class PieceTableOle(FakeOle):
        def exists(self, name):
            return name in {"WordDocument", "0Table"}

        def openstream(self, name):
            class Stream:
                def __init__(self, data):
                    self.data = data

                def read(self):
                    return self.data

            word_data = bytearray(b"\x00" * 512)
            first = "First line\n".encode("utf-16-le")
            second = b"Second line"
            word_data[128:128 + len(first)] = first
            word_data[200:200 + len(second)] = second
            clx = _doc_piece_table(
                [0, len("First line\n"), len("First line\nSecond line")],
                [128, (200 << 1) | 1],
            )
            if name == "WordDocument":
                struct.pack_into("<I", word_data, 0x01A2, 0)
                struct.pack_into("<I", word_data, 0x01A6, len(clx))
                return Stream(bytes(word_data))
            return Stream(clx)

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", PieceTableOle)
    path = tmp_path / "piece-table.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["First line", "Second line"]


def test_doc_reader_joins_multiple_clx_piece_segments(monkeypatch, tmp_path):
    class MultiSegmentClxOle(FakeOle):
        def exists(self, name):
            return name in {"WordDocument", "0Table"}

        def openstream(self, name):
            class Stream:
                def __init__(self, data):
                    self.data = data

                def read(self):
                    return self.data

            word_data = bytearray(b"\x00" * 512)
            first = "First line\n".encode("utf-16-le")
            second = "Second line".encode("utf-16-le")
            word_data[128:128 + len(first)] = first
            word_data[200:200 + len(second)] = second
            clx = _doc_piece_table_segments(
                [
                    ([0, len(first)], [128]),
                    ([0, len(second)], [200]),
                ]
            )
            if name == "WordDocument":
                struct.pack_into("<I", word_data, 0x01A2, 0)
                struct.pack_into("<I", word_data, 0x01A6, len(clx))
                return Stream(bytes(word_data))
            return Stream(clx)

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", MultiSegmentClxOle)
    path = tmp_path / "multi-clx.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["First line", "Second line"]


def test_doc_reader_decodes_clx_compressed_piece_flag(monkeypatch, tmp_path):
    class CompressedPieceOle(FakeOle):
        def exists(self, name):
            return name in {"WordDocument", "0Table"}

        def openstream(self, name):
            class Stream:
                def __init__(self, data):
                    self.data = data

                def read(self):
                    return self.data

            word_data = bytearray(b"\x00" * 512)
            text = b"Compressed piece"
            word_data[160:160 + len(text)] = text
            clx = _doc_piece_table([0, len("Compressed piece")], [0x40000000 | (160 * 2)])
            if name == "WordDocument":
                struct.pack_into("<I", word_data, 0x01A2, 0)
                struct.pack_into("<I", word_data, 0x01A6, len(clx))
                return Stream(bytes(word_data))
            return Stream(clx)

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", CompressedPieceOle)
    path = tmp_path / "compressed-piece.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Compressed piece"]


def test_doc_reader_prefers_latin_text_when_fib_range_is_compressed(monkeypatch, tmp_path):
    class LatinFibOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    prefix = bytearray(b"\x00" * 96)
                    fc_min = 96
                    text = b"Latin Body\nPlain text"
                    fc_mac = fc_min + len(text)
                    struct.pack_into("<I", prefix, 0x18, fc_min)
                    struct.pack_into("<I", prefix, 0x1C, fc_mac)
                    return bytes(prefix) + text + b"Trailing junk"

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", LatinFibOle)
    path = tmp_path / "latin-fib.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Latin Body", "Plain text"]


def test_doc_reader_preserves_cp1252_punctuation_in_compressed_text(monkeypatch, tmp_path):
    class Cp1252FibOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    prefix = bytearray(b"\x00" * 96)
                    fc_min = 96
                    text = b'Quote \x93Growth\x94 \x96 done'
                    fc_mac = fc_min + len(text)
                    struct.pack_into("<I", prefix, 0x18, fc_min)
                    struct.pack_into("<I", prefix, 0x1C, fc_mac)
                    return bytes(prefix) + text

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", Cp1252FibOle)
    path = tmp_path / "cp1252.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ['Quote “Growth” – done']


def test_doc_reader_normalizes_legacy_layout_characters(monkeypatch, tmp_path):
    class LayoutCharOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "A\u00a0B\u00adC\nD\u2011E".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", LayoutCharOle)
    path = tmp_path / "layout-chars.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["A BC", "D-E"]


def test_doc_reader_preserves_legacy_soft_line_breaks(monkeypatch, tmp_path):
    class SoftBreakOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Title\x0bSubtitle\x0bFooter".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", SoftBreakOle)
    path = tmp_path / "soft-break.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Title", "Subtitle", "Footer"]


def test_doc_reader_restores_hyperlink_field_result(monkeypatch, tmp_path):
    class HyperlinkOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return 'Intro\n\x13 HYPERLINK "https://example.com/report" \x14Example Report\x15'.encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", HyperlinkOle)
    path = tmp_path / "hyperlink-field.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    def element_text(element):
        return element.text if hasattr(element, "text") else f"<{element.__class__.__name__}>"

    assert [element_text(element) for element in doc.sections[0].elements] == [
        "Intro",
        "Example Report <https://example.com/report>",
    ]


def test_doc_reader_restores_unquoted_hyperlink_field_result(monkeypatch, tmp_path):
    class UnquotedHyperlinkOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Intro\n\x13 HYPERLINK https://example.com/report \x14Report\x15".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", UnquotedHyperlinkOle)
    path = tmp_path / "unquoted-hyperlink-field.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Intro",
        "Report <https://example.com/report>",
    ]


def test_doc_reader_restores_internal_hyperlink_field_result(monkeypatch, tmp_path):
    class InternalHyperlinkOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return 'Intro\n\x13 HYPERLINK \\l "Section_2" \x14Jump\x15'.encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", InternalHyperlinkOle)
    path = tmp_path / "internal-hyperlink-field.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Intro",
        "Jump <#Section_2>",
    ]


def test_doc_reader_restores_generic_field_display_result(monkeypatch, tmp_path):
    class GenericFieldOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Intro\n\x13 PAGEREF Section_2 \\h \x143\x15".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", GenericFieldOle)
    path = tmp_path / "generic-field.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Intro",
        "3",
    ]


def test_doc_reader_restores_headings_lists_and_tables(monkeypatch, tmp_path):
    class StructuredOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return (
                        "# Quarterly Report\n"
                        "- Revenue grew\n"
                        "- Costs fell\n"
                        "Name\tValue\n"
                        "ARR\t10\n"
                        "Margin\t20\n"
                        "Closing note"
                    ).encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", StructuredOle)
    path = tmp_path / "structured.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.sections[0].elements[0].heading_level == 1
    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "# Quarterly Report\n\n"
        "- Revenue grew\n\n"
        "- Costs fell\n\n"
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |\n\n"
        "Closing note"
    )


def test_doc_reader_restores_pipe_delimited_tables(monkeypatch, tmp_path):
    class PipeTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Metric | Value\nARR | 10\nMargin | 20\nClosing note".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", PipeTableOle)
    path = tmp_path / "pipe-table.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |\n\n"
        "Closing note"
    )


def test_doc_reader_restores_fixed_width_space_aligned_tables(monkeypatch, tmp_path):
    class SpaceAlignedTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Metric    Value\nARR       10\nMargin    20\nClosing note".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", SpaceAlignedTableOle)
    path = tmp_path / "space-aligned-table.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |\n\n"
        "Closing note"
    )


def test_doc_reader_restores_ideographic_space_aligned_tables(monkeypatch, tmp_path):
    class IdeographicSpaceTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "항목　　값\n매출　　10\n마진　　20\n본문".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", IdeographicSpaceTableOle)
    path = tmp_path / "ideographic-space-table.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| 항목 | 값 |\n"
        "| --- | --- |\n"
        "| 매출 | 10 |\n"
        "| 마진 | 20 |\n\n"
        "본문"
    )


def test_doc_reader_restores_markdown_pipe_tables_with_separator(monkeypatch, tmp_path):
    class MarkdownPipeTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "| Metric | Value |\n| --- | --- |\n| ARR | 10 |\n| Margin | 20 |".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", MarkdownPipeTableOle)
    path = tmp_path / "markdown-pipe-table.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |"
    )


def test_doc_reader_restores_key_value_form_lines_as_table(monkeypatch, tmp_path):
    class KeyValueOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Owner: Finance\nDue Date: 2026-07-01\nStatus: Approved\nClosing note".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", KeyValueOle)
    path = tmp_path / "key-value-form.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Owner | Finance |\n"
        "| --- | --- |\n"
        "| Due Date | 2026-07-01 |\n"
        "| Status | Approved |\n\n"
        "Closing note"
    )


def test_doc_reader_restores_fullwidth_colon_key_value_lines_as_table(monkeypatch, tmp_path):
    class KoreanKeyValueOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "담당자：재무팀\n상태：승인\n마감일：2026-07-01\n본문".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", KoreanKeyValueOle)
    path = tmp_path / "korean-key-value-form.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| 담당자 | 재무팀 |\n"
        "| --- | --- |\n"
        "| 상태 | 승인 |\n"
        "| 마감일 | 2026-07-01 |\n\n"
        "본문"
    )


def test_doc_reader_normalizes_legacy_bullet_markers(monkeypatch, tmp_path):
    class BulletOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "• Revenue grew\n◦ Costs fell\n‣ Risks tracked".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", BulletOle)
    path = tmp_path / "bullets.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "- Revenue grew\n\n- Costs fell\n\n- Risks tracked"


def test_doc_reader_normalizes_legacy_numbered_list_markers(monkeypatch, tmp_path):
    class NumberedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "1) Revenue grew\n2) Costs fell".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", NumberedOle)
    path = tmp_path / "numbered-list.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "1. Revenue grew\n\n2. Costs fell"


def test_doc_reader_normalizes_parenthesized_numbered_list_markers(monkeypatch, tmp_path):
    class NumberedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "(1) Revenue grew\n(2) Costs fell".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", NumberedOle)
    path = tmp_path / "parenthesized-numbered-list.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "1. Revenue grew\n\n2. Costs fell"


def test_doc_reader_normalizes_legacy_alpha_and_roman_outline_markers(monkeypatch, tmp_path):
    class OutlineOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "A) Revenue grew\nb. Costs fell\niv) Risks tracked".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", OutlineOle)
    path = tmp_path / "outline-list.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "- Revenue grew\n\n- Costs fell\n\n- Risks tracked"


def test_doc_reader_restores_legacy_checklist_markers(monkeypatch, tmp_path):
    class ChecklistOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "□ Legal review\n☑ Finance approved\n[x] Launch ready".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", ChecklistOle)
    path = tmp_path / "checklist.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "- [ ] Legal review\n\n- [x] Finance approved\n\n- [x] Launch ready"


def test_doc_reader_restores_underline_style_headings(monkeypatch, tmp_path):
    class UnderlineHeadingOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Annual Plan\n===========\nScope\n-----\nBody text".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", UnderlineHeadingOle)
    path = tmp_path / "underline-headings.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "# Annual Plan\n\n## Scope\n\nBody text"


def test_doc_reader_restores_explicit_legacy_heading_labels(monkeypatch, tmp_path):
    class HeadingOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Title: Annual Plan\nHeading 2: Scope\nBody text".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", HeadingOle)
    path = tmp_path / "headings.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "# Annual Plan\n\n## Scope\n\nBody text"


def test_doc_reader_restores_korean_legacy_heading_labels(monkeypatch, tmp_path):
    class KoreanHeadingOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "제목: 연간 계획\n소제목: 범위\n본문".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", KoreanHeadingOle)
    path = tmp_path / "korean-headings.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(DOCReader().read(str(path)))

    assert markdown == "# 연간 계획\n\n## 범위\n\n본문"


def test_doc_reader_restores_word_table_cell_markers(monkeypatch, tmp_path):
    class TableMarkerOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "Name\x07Value\x07\rARR\x0710\x07\rClosing note".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", TableMarkerOle)
    path = tmp_path / "cell-markers.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 2
    assert markdown == (
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n\n"
        "Closing note"
    )


def test_doc_reader_restores_section_breaks(monkeypatch, tmp_path):
    class SectionBreakOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return "First section\n\x0cSecond section\nTail".encode("utf-16-le")

            return Stream()

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", SectionBreakOle)
    path = tmp_path / "section-break.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = DOCReader().read(str(path))

    assert len(doc.sections) == 2
    assert [element.text for element in doc.sections[0].elements] == ["First section"]
    assert [element.text for element in doc.sections[1].elements] == ["Second section", "Tail"]
    assert doc.sections[1].provenance.section == 1


def test_dochan_routes_doc_to_native_reader(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", FakeOle)
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "doc"
    assert doc.to_plain_text() == "Legacy Word\n\n본문 텍스트"


def test_cli_info_reports_doc_format(monkeypatch, tmp_path, capsys):
    class Args:
        pass

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", FakeOle)
    path = tmp_path / "info.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "doc"' in out
