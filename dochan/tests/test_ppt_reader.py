import struct

from dochan import Dochan
from dochan.cli import _cmd_info
from dochan.office_binary.ppt import PPTReader
from dochan.output.markdown import to_markdown


def _ppt_record(record_type, payload):
    return struct.pack("<HHI", 0, record_type, len(payload)) + payload


def _ppt_container(record_type, payload):
    return struct.pack("<HHI", 0x000F, record_type, len(payload)) + payload


def _ppt_text_header(text_type):
    return _ppt_record(3999, struct.pack("<I", text_type))


def _ppt_document_stream():
    return (
        _ppt_record(4000, "Title Slide".encode("utf-16-le"))
        + _ppt_record(4008, b"Latin note")
    )


class FakeOle:
    def __init__(self, path):
        self.path = path

    def exists(self, name):
        return name == "PowerPoint Document"

    def openstream(self, name):
        class Stream:
            def read(self):
                return _ppt_document_stream()

        return Stream()

    def close(self):
        pass


def test_ppt_reader_extracts_text_records(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", FakeOle)
    path = tmp_path / "legacy.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert doc.metadata["source_format"] == "ppt"
    assert doc.sections[0].elements[0].text == "Title Slide"
    assert doc.sections[0].elements[1].text == "Latin note"


def test_ppt_reader_returns_error_when_powerpoint_stream_unreadable(monkeypatch, tmp_path):
    class CorruptPptOle(FakeOle):
        def openstream(self, name):
            if name != "PowerPoint Document":
                raise KeyError(name)
            raise IOError("stream is unreadable")

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", CorruptPptOle)
    path = tmp_path / "corrupt.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert doc.metadata["source_format"] == "ppt"
    assert doc.sections == []
    assert doc.errors == ["ERR: PPT PowerPoint Document stream read 실패: stream is unreadable"]


def test_ppt_reader_preserves_cp1252_punctuation_in_byte_text_records(monkeypatch, tmp_path):
    class Cp1252Ole(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4008, b'Quote \x93Growth\x94 \x96 done')

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", Cp1252Ole)
    path = tmp_path / "cp1252.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ['Quote “Growth” – done']


def test_ppt_reader_restores_slide_sections_and_tables(monkeypatch, tmp_path):
    class StructuredOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    slide1 = (
                        _ppt_record(4000, "# Sales Update".encode("utf-16-le"))
                        + _ppt_record(4008, b"- Pipeline up")
                    )
                    slide2 = _ppt_record(4000, "Metric\tValue\nARR\t10".encode("utf-16-le"))
                    return _ppt_container(1006, slide1) + _ppt_container(1006, slide2)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", StructuredOle)
    path = tmp_path / "structured.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert len(doc.sections) == 2
    assert [section.provenance.slide for section in doc.sections] == [1, 2]
    assert doc.sections[0].provenance.path == "PowerPoint Document#slide1"
    assert doc.sections[1].provenance.path == "PowerPoint Document#slide2"
    table = doc.find_all("table")[0]
    assert table.rows[0][0].provenance.path == "PowerPoint Document#slide2"
    assert table.rows[0][0].provenance.cell == "R1C1"
    assert table.rows[0][0].paragraphs[0].runs[0].provenance.path == "PowerPoint Document#slide2"
    assert table.rows[0][0].paragraphs[0].runs[0].provenance.cell == "R1C1"
    assert doc.sections[0].elements[0].heading_level == 1
    assert table.row_count == 2
    assert table.rows[0][0].row == 0
    assert table.rows[0][0].col == 0
    assert table.rows[0][1].row == 0
    assert table.rows[0][1].col == 1
    assert table.rows[1][0].row == 1
    assert table.rows[1][0].col == 0
    assert table.rows[0][0].provenance.cell == "R1C1"
    assert table.rows[0][1].provenance.cell == "R1C2"
    assert table.rows[1][0].provenance.cell == "R2C1"
    assert markdown == (
        "## Slide 1\n\n"
        "# Sales Update\n\n"
        "- Pipeline up\n\n"
        "## Slide 2\n\n"
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |"
    )


def test_ppt_reader_restores_pipe_delimited_tables(monkeypatch, tmp_path):
    class PipeTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Metric | Value\nARR | 10\nMargin | 20\nClosing note".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", PipeTableOle)
    path = tmp_path / "pipe-table.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |\n\n"
        "Closing note"
    )


def test_ppt_reader_restores_fixed_width_space_aligned_tables(monkeypatch, tmp_path):
    class SpaceAlignedTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Metric    Value\nARR       10\nMargin    20\nClosing note".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", SpaceAlignedTableOle)
    path = tmp_path / "space-aligned-table.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |\n\n"
        "Closing note"
    )


def test_ppt_reader_restores_ideographic_space_aligned_tables(monkeypatch, tmp_path):
    class IdeographicSpaceTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "항목　　값\n매출　　10\n마진　　20\n본문".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", IdeographicSpaceTableOle)
    path = tmp_path / "ideographic-space-table.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| 항목 | 값 |\n"
        "| --- | --- |\n"
        "| 매출 | 10 |\n"
        "| 마진 | 20 |\n\n"
        "본문"
    )


def test_ppt_reader_restores_markdown_pipe_tables_with_separator(monkeypatch, tmp_path):
    class MarkdownPipeTableOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "| Metric | Value |\n| --- | --- |\n| ARR | 10 |\n| Margin | 20 |".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", MarkdownPipeTableOle)
    path = tmp_path / "markdown-pipe-table.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Metric | Value |\n"
        "| --- | --- |\n"
        "| ARR | 10 |\n"
        "| Margin | 20 |"
    )


def test_ppt_reader_restores_key_value_form_lines_as_table(monkeypatch, tmp_path):
    class KeyValueOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Owner: Finance\nDue Date: 2026-07-01\nStatus: Approved\nClosing note".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", KeyValueOle)
    path = tmp_path / "key-value-form.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Owner | Finance |\n"
        "| --- | --- |\n"
        "| Due Date | 2026-07-01 |\n"
        "| Status | Approved |\n\n"
        "Closing note"
    )


def test_ppt_reader_restores_fullwidth_colon_key_value_lines_as_table(monkeypatch, tmp_path):
    class KoreanKeyValueOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "담당자：재무팀\n상태：승인\n마감일：2026-07-01\n본문".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", KoreanKeyValueOle)
    path = tmp_path / "korean-key-value-form.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| 담당자 | 재무팀 |\n"
        "| --- | --- |\n"
        "| 상태 | 승인 |\n"
        "| 마감일 | 2026-07-01 |\n\n"
        "본문"
    )


def test_ppt_reader_restores_equal_sign_key_value_lines_as_table(monkeypatch, tmp_path):
    class KeyValueOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Owner = Finance\nDue Date = 2026-07-01\nStatus = Approved\nClosing note".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", KeyValueOle)
    path = tmp_path / "equal-key-value-form.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))
    markdown = to_markdown(doc)

    assert doc.find_all("table")[0].row_count == 3
    assert markdown == (
        "| Owner | Finance |\n"
        "| --- | --- |\n"
        "| Due Date | 2026-07-01 |\n"
        "| Status | Approved |\n\n"
        "Closing note"
    )


def test_ppt_reader_normalizes_legacy_bullet_markers(monkeypatch, tmp_path):
    class BulletOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "• Pipeline up\n◦ Costs down\n‣ Risks tracked".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", BulletOle)
    path = tmp_path / "bullets.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "- Pipeline up\n\n- Costs down\n\n- Risks tracked"


def test_ppt_reader_normalizes_legacy_numbered_list_markers(monkeypatch, tmp_path):
    class NumberedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "1) Pipeline up\n2) Costs down".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", NumberedOle)
    path = tmp_path / "numbered-list.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "1. Pipeline up\n\n2. Costs down"


def test_ppt_reader_normalizes_legacy_dotted_numbered_list_markers(monkeypatch, tmp_path):
    class NumberedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "1. Pipeline up\n2. Costs down".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", NumberedOle)
    path = tmp_path / "dotted-numbered-list.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "1. Pipeline up\n\n2. Costs down"


def test_ppt_reader_normalizes_parenthesized_numbered_list_markers(monkeypatch, tmp_path):
    class NumberedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "(1) Pipeline up\n(2) Costs down".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", NumberedOle)
    path = tmp_path / "parenthesized-numbered-list.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "1. Pipeline up\n\n2. Costs down"


def test_ppt_reader_normalizes_spaced_and_circled_numbered_list_markers(monkeypatch, tmp_path):
    class NumberedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "1 ) Pipeline up\n2 ) Costs down\n④ Risks tracked".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", NumberedOle)
    path = tmp_path / "numbered-list.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "1. Pipeline up\n\n2. Costs down\n\n- Risks tracked"


def test_ppt_reader_normalizes_legacy_alpha_and_roman_outline_markers(monkeypatch, tmp_path):
    class OutlineOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "A) Pipeline up\nb. Costs down\niv) Risks tracked".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", OutlineOle)
    path = tmp_path / "outline-list.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "- Pipeline up\n\n- Costs down\n\n- Risks tracked"


def test_ppt_reader_restores_legacy_checklist_markers(monkeypatch, tmp_path):
    class ChecklistOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "□ Legal review\n☑ Finance approved\n[x] Launch ready".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", ChecklistOle)
    path = tmp_path / "checklist.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "- [ ] Legal review\n\n- [x] Finance approved\n\n- [x] Launch ready"


def test_ppt_reader_restores_underline_style_headings(monkeypatch, tmp_path):
    class UnderlineHeadingOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Roadmap\n=======\nRisks\n-----\nBody text".encode("utf-16-le")
                    return _ppt_record(4000, text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", UnderlineHeadingOle)
    path = tmp_path / "underline-headings.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "# Roadmap\n\n## Risks\n\nBody text"


def test_ppt_reader_restores_explicit_legacy_heading_labels(monkeypatch, tmp_path):
    class HeadingOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "Title: Roadmap\nHeading 2: Risks".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", HeadingOle)
    path = tmp_path / "headings.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "# Roadmap\n\n## Risks"


def test_ppt_reader_restores_korean_legacy_heading_labels(monkeypatch, tmp_path):
    class KoreanHeadingOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_record(4000, "제목: 로드맵\n소제목: 위험\n본문".encode("utf-16-le"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", KoreanHeadingOle)
    path = tmp_path / "korean-headings.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "# 로드맵\n\n## 위험\n\n본문"


def test_ppt_reader_promotes_text_header_title_records(monkeypatch, tmp_path):
    class TextHeaderOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return (
                        _ppt_text_header(0)
                        + _ppt_record(4000, "Quarterly Results".encode("utf-16-le"))
                        + _ppt_text_header(1)
                        + _ppt_record(4000, "Operating update".encode("utf-16-le"))
                    )

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", TextHeaderOle)
    path = tmp_path / "text-header.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "# Quarterly Results\n\nOperating update"


def test_ppt_reader_promotes_center_title_text_header(monkeypatch, tmp_path):
    class CenterTitleOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return (
                        _ppt_text_header(6)
                        + _ppt_record(4000, "Centered Title".encode("utf-16-le"))
                    )

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", CenterTitleOle)
    path = tmp_path / "center-title.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    markdown = to_markdown(PPTReader().read(str(path)))

    assert markdown == "# Centered Title"


def test_ppt_reader_preserves_repeated_text_lines(monkeypatch, tmp_path):
    class RepeatedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_container(1006, _ppt_record(4008, b"- Repeat\n- Repeat\nDone"))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", RepeatedOle)
    path = tmp_path / "repeated.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["- Repeat", "- Repeat", "Done"]


def test_ppt_reader_normalizes_legacy_layout_characters(monkeypatch, tmp_path):
    class LayoutCharOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "A\u00a0B\u00adC\nD\u2011E".encode("utf-16-le")
                    return _ppt_container(1006, _ppt_record(4000, text))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", LayoutCharOle)
    path = tmp_path / "layout-chars.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["A BC", "D-E"]


def test_ppt_reader_preserves_legacy_soft_line_breaks(monkeypatch, tmp_path):
    class SoftBreakOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Title\x0bSubtitle\x0cFooter".encode("utf-16-le")
                    return _ppt_container(1006, _ppt_record(4000, text))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", SoftBreakOle)
    path = tmp_path / "soft-breaks.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Title", "Subtitle", "Footer"]


def test_ppt_reader_normalizes_legacy_mid_dot_bullet_markers(monkeypatch, tmp_path):
    class BulletOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    return _ppt_container(1006, _ppt_record(4000, "・ Revenue grew\n・ Costs fell".encode("utf-16-le")))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", BulletOle)
    path = tmp_path / "mid-dot-bullets.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["- Revenue grew", "- Costs fell"]


def test_ppt_reader_restores_hyperlink_field_result(monkeypatch, tmp_path):
    class HyperlinkOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = 'Intro\n\x13 HYPERLINK "https://example.com/deck" \x14Deck Link\x15'
                    return _ppt_container(1006, _ppt_record(4000, text.encode("utf-16-le")))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", HyperlinkOle)
    path = tmp_path / "hyperlink-field.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    def element_text(element):
        return element.text if hasattr(element, "text") else f"<{element.__class__.__name__}>"

    assert [element_text(element) for element in doc.sections[0].elements] == [
        "Intro",
        "Deck Link <https://example.com/deck>",
    ]


def test_ppt_reader_restores_unquoted_hyperlink_field_result(monkeypatch, tmp_path):
    class UnquotedHyperlinkOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Intro\n\x13 HYPERLINK https://example.com/deck \x14Deck Link\x15"
                    return _ppt_container(1006, _ppt_record(4000, text.encode("utf-16-le")))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", UnquotedHyperlinkOle)
    path = tmp_path / "unquoted-hyperlink-field.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Intro",
        "Deck Link <https://example.com/deck>",
    ]


def test_ppt_reader_restores_internal_hyperlink_field_result(monkeypatch, tmp_path):
    class InternalHyperlinkOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = 'Intro\n\x13 HYPERLINK \\l "Slide_2" \x14Jump\x15'
                    return _ppt_container(1006, _ppt_record(4000, text.encode("utf-16-le")))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", InternalHyperlinkOle)
    path = tmp_path / "internal-hyperlink-field.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Intro",
        "Jump <#Slide_2>",
    ]


def test_ppt_reader_restores_generic_field_display_result(monkeypatch, tmp_path):
    class GenericFieldOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    text = "Intro\n\x13 REF SlideTitle \\h \x14Quarterly Results\x15"
                    return _ppt_container(1006, _ppt_record(4000, text.encode("utf-16-le")))

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", GenericFieldOle)
    path = tmp_path / "generic-field.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Intro",
        "Quarterly Results",
    ]


def test_ppt_reader_restores_notes_container_text(monkeypatch, tmp_path):
    class NotesOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    slide = _ppt_container(1006, _ppt_record(4000, "Slide title".encode("utf-16-le")))
                    notes = _ppt_container(1008, _ppt_record(4008, b"Speaker note\nFollow up"))
                    return slide + notes

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", NotesOle)
    path = tmp_path / "notes.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Slide title",
        "Notes",
        "Speaker note",
        "Follow up",
    ]
    assert doc.sections[0].elements[1].heading_level == 2
    assert doc.sections[0].elements[0].provenance.path == "PowerPoint Document#slide1"
    assert doc.sections[0].elements[1].provenance.path == "PowerPoint Document#slide1#notes"
    assert doc.sections[0].elements[2].provenance.path == "PowerPoint Document#slide1#notes"
    assert doc.sections[0].elements[3].provenance.path == "PowerPoint Document#slide1#notes"
    assert doc.sections[0].elements[1].runs[0].provenance.path == "PowerPoint Document#slide1#notes"
    assert doc.sections[0].elements[2].runs[0].provenance.path == "PowerPoint Document#slide1#notes"
    assert doc.sections[0].elements[3].runs[0].provenance.path == "PowerPoint Document#slide1#notes"


def test_ppt_reader_recovers_from_truncated_text_record_in_slide_container(monkeypatch, tmp_path):
    class TruncatedTextOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    full = _ppt_record(4000, "Slide body".encode("utf-16-le"))
                    truncated_record = struct.pack("<HHI", 0, 4000, 10) + "N".encode("utf-16-le")[:2]
                    return _ppt_container(1006, full + truncated_record)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", TruncatedTextOle)
    path = tmp_path / "truncated-ppt-text.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Slide body", "N"]


def test_ppt_reader_recovers_truncated_notes_container_text(monkeypatch, tmp_path):
    class TruncatedNotesOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    slide = _ppt_container(1006, _ppt_record(4000, "Slide title".encode("utf-16-le")))
                    nested_notes = struct.pack("<HHI", 0, 4008, 2) + b"N"
                    truncated_notes = struct.pack("<HHI", 0, 1008, len(nested_notes)) + nested_notes
                    return slide + truncated_notes

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", TruncatedNotesOle)
    path = tmp_path / "truncated-ppt-notes.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == ["Slide title", "Notes", "N"]


def test_ppt_reader_recovers_notes_after_truncated_payload_record(monkeypatch, tmp_path):
    class MixedOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    slide = _ppt_record(4000, "Slide title".encode("utf-16-le"))
                    truncated = struct.pack("<HHI", 0x4000, 9999, 0) + b"X"
                    note_text = _ppt_record(4008, b"Recovered note")
                    return _ppt_container(1006, slide + truncated) + _ppt_container(1008, note_text)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", MixedOle)
    path = tmp_path / "mixed-corrupt.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Slide title",
        "Notes",
        "Recovered note",
    ]


def test_ppt_reader_attaches_nested_notes_to_previous_slide(monkeypatch, tmp_path):
    class NestedNotesOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    slide = _ppt_container(1006, _ppt_record(4000, "Slide title".encode("utf-16-le")))
                    notes = _ppt_container(1008, _ppt_record(4008, b"Nested speaker note"))
                    return slide + _ppt_container(5000, notes)

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", NestedNotesOle)
    path = tmp_path / "nested-notes.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert len(doc.sections) == 1
    assert [element.text for element in doc.sections[0].elements] == [
        "Slide title",
        "Notes",
        "Nested speaker note",
    ]
    assert doc.sections[0].elements[2].provenance.path == "PowerPoint Document#slide1#notes"
    assert doc.sections[0].elements[2].runs[0].provenance.path == "PowerPoint Document#slide1#notes"


def test_ppt_reader_restores_comments_container_text(monkeypatch, tmp_path):
    class CommentsOle(FakeOle):
        def openstream(self, name):
            class Stream:
                def read(self):
                    slide = _ppt_container(1006, _ppt_record(4000, "Slide title".encode("utf-16-le")))
                    comments = _ppt_container(1200, _ppt_record(4008, b"Reviewer comment"))
                    return slide + comments

            return Stream()

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", CommentsOle)
    path = tmp_path / "comments.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = PPTReader().read(str(path))

    assert [element.text for element in doc.sections[0].elements] == [
        "Slide title",
        "Comments",
        "Reviewer comment",
    ]
    assert doc.sections[0].elements[1].heading_level == 2
    assert doc.sections[0].elements[1].provenance.path == "PowerPoint Document#slide1#comments"
    assert doc.sections[0].elements[2].provenance.path == "PowerPoint Document#slide1#comments"
    assert doc.sections[0].elements[1].runs[0].provenance.path == "PowerPoint Document#slide1#comments"
    assert doc.sections[0].elements[2].runs[0].provenance.path == "PowerPoint Document#slide1#comments"


def test_dochan_routes_ppt_to_native_reader(monkeypatch, tmp_path):
    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", FakeOle)
    path = tmp_path / "legacy.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "ppt"
    assert doc.to_markdown() == "Title Slide\n\nLatin note"


def test_cli_info_reports_ppt_format(monkeypatch, tmp_path, capsys):
    class Args:
        pass

    monkeypatch.setattr("dochan.office_binary.ppt.olefile.OleFileIO", FakeOle)
    path = tmp_path / "info.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "ppt"' in out
