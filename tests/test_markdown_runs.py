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
