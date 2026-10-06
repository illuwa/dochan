"""Markdown 런 렌더링 — 강조 마커 안팎의 공백 처리."""
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.output.markdown import to_markdown


def _md(runs):
    doc = Document()
    doc.sections.append(Section(elements=[Paragraph(runs=runs)]))
    return to_markdown(doc).strip()


def test_bold_run_boundary_whitespace_moves_outside_markers():
    # "**제3조(소집) **①" 은 CommonMark 강조가 아니다 — 공백은 마커 밖으로 뺀다
    assert _md([TextRun(text="제3조(소집) ", bold=True), TextRun(text="① 본문")]) == "**제3조(소집)** ① 본문"
    assert _md([TextRun(text="앞 "), TextRun(text=" 굵게 ", bold=True, italic=True), TextRun(text="뒤")]) == "앞  ***굵게*** 뒤"


def test_whitespace_only_formatted_run_renders_no_markers():
    # 서식이 같은 인접 런은 한 번만 감싼다 — 가운데 공백 런도 같은 굵은 구간에 들어간다.
    assert _md([TextRun(text="앞", bold=True), TextRun(text=" ", bold=True), TextRun(text="뒤", bold=True)]) == "**앞 뒤**"
    assert _md([TextRun(text="앞", bold=True), TextRun(text=" "), TextRun(text="뒤", bold=True)]) == "**앞** **뒤**"


def test_adjacent_runs_with_same_formatting_share_one_pair_of_markers():
    # 한글·워드는 글자 크기나 글꼴만 달라도 런을 가른다. 런마다 마커를 치면 "**제1조(목적)****이 규칙은**" 이 되는데,
    # 구두점 뒤 글자 앞의 `****` 는 CommonMark 에서 닫는 구분자가 아니라서 별표가 글자로 남는다.
    assert _md([TextRun(text="제1조(목적)", bold=True, font_size_pt=12.0),
                TextRun(text="이 규칙은", bold=True, font_size_pt=10.0)]) == "**제1조(목적)이 규칙은**"
    assert _md([TextRun(text="가", bold=True, italic=True), TextRun(text="나", bold=True, italic=True)]) == "***가나***"
    assert _md([TextRun(text="가", underline=True), TextRun(text="나", underline=True)]) == "<u>가나</u>"
    assert _md([TextRun(text="가", strikeout=True), TextRun(text="나", strikeout=True)]) == "~~가나~~"
    assert _md([TextRun(text="1", superscript=True), TextRun(text="2", superscript=True)]) == "<sup>12</sup>"
    assert _md([TextRun(text="앞"), TextRun(text="가", bold=True), TextRun(text="나", bold=True),
                TextRun(text="뒤")]) == "앞**가나**뒤"


def test_runs_with_different_formatting_keep_their_own_markers():
    assert _md([TextRun(text="가", bold=True), TextRun(text="나", italic=True)]) == "**가***나*"
    assert _md([TextRun(text="가", bold=True), TextRun(text="나"), TextRun(text="다", bold=True)]) == "**가**나**다**"
    assert _md([TextRun(text="가", bold=True), TextRun(text="나", bold=True, underline=True)]) == "**가**<u>**나**</u>"


def test_merging_stops_at_links_note_references_and_provenance_changes():
    from dochan.conversion import Provenance

    assert _md([TextRun(text="가", bold=True, link="https://a.example"),
                TextRun(text="나", bold=True, link="https://b.example")]) == "[**가**](https://a.example)[**나**](https://b.example)"
    assert _md([TextRun(text="가", bold=True, link="https://a.example"),
                TextRun(text="나", bold=True, link="https://a.example")]) == "[**가나**](https://a.example)"
    assert _md([TextRun(text="가", bold=True), TextRun(text="", note_ref=1),
                TextRun(text="나", bold=True)]) == "**가**[^1]**나**"
    first, second = Provenance(source_format="pdf", page=1), Provenance(source_format="pdf", page=2)
    assert _md([TextRun(text="가", bold=True, provenance=first),
                TextRun(text="나", bold=True, provenance=second)]) == "**가****나**"
    assert _md([TextRun(text="가", bold=True, provenance=first),
                TextRun(text="나", bold=True, provenance=Provenance(source_format="pdf", page=1))]) == "**가나**"


def test_merging_for_markdown_leaves_the_model_runs_untouched():
    from dochan.output.json_out import to_dict

    runs = [TextRun(text="가", bold=True, font_size_pt=12.0), TextRun(text="나", bold=True, font_size_pt=10.0)]
    doc = Document()
    doc.sections.append(Section(elements=[Paragraph(runs=runs)]))
    assert to_markdown(doc) == "**가나**"
    assert [run.text for run in doc.sections[0].elements[0].runs] == ["가", "나"]
    assert [run["font_size_pt"] for run in to_dict(doc)["sections"][0]["elements"][0]["runs"]] == [12.0, 10.0]


# 본문 글자 `~~~~~~`·```` ``` ```` 로 시작하는 줄은 GFM 코드 펜스를 열어 뒤 문서 전체를 코드로 삼킨다(공개 hwp3-sample10).
# 줄 머리의 펜스 열기만 이스케이프하고, 줄 가운데의 물결표와 취소선 표기는 그대로 둔다.
import pytest  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("~~~~~~", "\\~~~~~~"),
    ("```code", "\\```code"),
    ("   ~~~ 들여쓴 펜스", "   \\~~~ 들여쓴 펜스"),
    ("앞\n~~~~\n뒤", "앞\n\\~~~~\n뒤"),
    ("a ~~~ b", "a ~~~ b"),
    ("~~ 두 개 ~~", "~~ 두 개 ~~"),
    ("    ~~~ 네 칸 들여쓰기", "    ~~~ 네 칸 들여쓰기"),
])
def test_paragraph_line_start_code_fence_is_escaped(text, expected):
    # 앞 문단을 두어 출력 끝 공백 정리가 들여쓰기를 지우지 않게 한다.
    doc = Document()
    doc.sections.append(Section(elements=[Paragraph(runs=[TextRun(text="앞 문단")]),
                                          Paragraph(runs=[TextRun(text=text)])]))
    assert to_markdown(doc).rstrip() == "앞 문단\n\n" + expected


def test_struck_run_markers_are_not_treated_as_fence():
    assert _md([TextRun(text="취소", strikeout=True)]) == "~~취소~~"
