"""합성 HWP 레코드로 문서 단위 런 예산과 무손실 본문을 검증한다."""
import struct

from dochan.hwp.doc_info import DocInfo
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import SectionParser
from dochan.model.document import TextRun


def _record(tag, level, data):
    if len(data) >= 4095:
        return struct.pack("<II", tag | level << 10 | 4095 << 20, len(data)) + data
    return struct.pack("<I", tag | level << 10 | len(data) << 20) + data


def _paragraph(text, pairs, level=0):
    return (_record(66, level, bytes(22))
            + _record(67, level + 1, (text + "\r").encode("utf-16-le"))
            + _record(68, level + 1, b"".join(struct.pack("<II", *p) for p in pairs)))


def _parser(monkeypatch, limit=3):
    monkeypatch.setattr(SectionParser, "MAX_DOCUMENT_TEXT_RUNS", limit, raising=False)
    return SectionParser(DocInfo(char_shapes=[CharShape(bold=True), CharShape(italic=True)]))


def test_hwp_run_budget_preserves_prefix_and_plain_tail(monkeypatch):
    parser = _parser(monkeypatch)
    para = parser.parse_stream(_paragraph("abcdef", [(i, i % 2) for i in range(6)]), False).elements[0]
    assert [r.text for r in para.runs] == ["a", "b", "c", "def"]
    assert para.runs[-1] == TextRun("def")
    assert [r.bold for r in para.runs[:3]] == [True, False, True]
    assert len(parser.errors) == 1
    assert "document text run" in parser.errors[0]


def test_hwp_run_budget_is_shared_by_sections_and_plain_paragraphs(monkeypatch):
    parser = _parser(monkeypatch)
    first = parser.parse_stream(_paragraph("abc", [(0, 0), (1, 1), (2, 0)]), False)
    assert len(first.elements[0].runs) == 3
    assert not parser.errors
    for _ in range(3):
        para = parser.parse_stream(_paragraph("다음😀끝", [(0, 0), (2, 1)]), False).elements[0]
        assert para.runs == [TextRun("다음😀끝")]
    assert len(parser.errors) == 1
    fresh = _parser(monkeypatch)
    fresh.parse_stream(_paragraph("plain", []), False)
    para = fresh.parse_stream(_paragraph("abc", [(0, 0), (1, 1), (2, 0)]), False).elements[0]
    assert [r.text for r in para.runs] == ["a", "b", "c"]
    assert para.runs[-1] == TextRun("c")


def test_hwp_duplicate_positions_do_not_spend_run_budget(monkeypatch):
    parser = _parser(monkeypatch, limit=2)
    pairs = [(0, 0)] * 10000 + [(1, 1)] * 10000
    para = parser.parse_stream(_paragraph("ab", pairs), False).elements[0]
    assert [r.text for r in para.runs] == ["a", "b"]
    assert not parser.errors


def test_hwp_run_budget_covers_nested_note_and_does_not_reset(monkeypatch):
    parser = _parser(monkeypatch, limit=2)
    data = (_paragraph("ab", [(0, 0), (1, 1)])
            + _record(71, 1, b"  nf") + _record(72, 2, bytes(8))
            + _paragraph("note", [(0, 0), (1, 1)], level=3))
    section = parser.parse_stream(data, False)
    note = section.elements[1]
    assert note.paragraphs[0].runs == [TextRun("note")]
    assert len(parser.errors) == 1


def test_hwp_link_split_budget_preserves_all_remaining_text():
    from dochan.hwp.section import _apply_link_ranges
    warnings = []
    result = _apply_link_ranges(
        [TextRun("abcdef", bold=True), TextRun("ghi", italic=True)],
        [(i, i + 1, str(i)) for i in range(9)],
        max_runs=3, on_limit=lambda: warnings.append(True),
    )
    assert [r.text for r in result] == ["a", "b", "c", "defghi"]
    assert [r.link for r in result] == ["0", "1", "2", ""]
    assert result[-1] == TextRun("defghi")
    assert warnings == [True]


def test_hwp_run_budget_stops_allocating_before_large_tail(monkeypatch):
    parser = _parser(monkeypatch)
    allocated = []

    def tracked_run(*args, **kwargs):
        allocated.append(True)
        return TextRun(*args, **kwargs)

    monkeypatch.setattr("dochan.hwp.section.TextRun", tracked_run)
    text = "x" * 20000
    para = parser.parse_stream(_paragraph(text, [(i, i % 2) for i in range(len(text))]), False).elements[0]
    assert para.text == text
    assert len(para.runs) == 4
    assert len(allocated) <= 4


def test_hwp_link_overlay_cannot_reformat_plain_budget_tail(monkeypatch):
    parser = _parser(monkeypatch)
    monkeypatch.setattr(parser, "_hyperlink_ranges", lambda *args: [(0, 6, "https://example.org")])
    para = parser.parse_stream(_paragraph("abcdef", [(i, i % 2) for i in range(6)]), False).elements[0]
    assert [r.text for r in para.runs] == ["a", "b", "c", "def"]
    assert all(r.link == "https://example.org" for r in para.runs[:3])
    assert para.runs[-1] == TextRun("def")
    assert len(parser.errors) == 1


def test_hwp_char_and_link_budget_tails_join_once(monkeypatch):
    parser = _parser(monkeypatch)
    monkeypatch.setattr(parser, "_hyperlink_ranges", lambda *args: [(i, i + 1, str(i)) for i in range(8)])
    para = parser.parse_stream(_paragraph("abcdefgh", [(i, i % 2) for i in range(0, 8, 2)]), False).elements[0]
    assert [r.text for r in para.runs] == ["a", "b", "c", "defgh"]
    assert para.runs[-1] == TextRun("defgh")
    assert len(parser.errors) == 1
