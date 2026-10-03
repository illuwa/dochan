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
    assert _md([TextRun(text="앞", bold=True), TextRun(text=" ", bold=True), TextRun(text="뒤", bold=True)]) == "**앞** **뒤**"


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
