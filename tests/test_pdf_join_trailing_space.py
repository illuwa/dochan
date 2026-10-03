"""줄 끝에 실제 공백 글리프가 있으면 다음 줄과 공백으로 잇는다.

PDF 가 줄 끝에 공백 문자를 그렸다면 원문의 그 자리는 띄어쓰기다. 공개 정책브리핑 보도자료 짝에서
이 경우의 HWPX 정답은 2,490/2,490, 내부 짝은 25/25 가 공백이었다(Opus 감수 집계, 2026-10-04).
공백 글리프가 없으면 지금처럼 한글 공백 통계 모델이 판정한다.
"""
from dochan.pdf.content import Fragment, _Line
from dochan.pdf.layout import merge_lines


def line(text, y, width=200.0):
    return _Line([Fragment(72, y, width, 10, text, 3, order=int(1000 - y))])


def test_trailing_space_glyph_forces_space_at_join():
    lines = [line("도서 ", 700), line("관리를 합니다", 686)]
    assert [block.text for block in merge_lines(lines)] == ["도서 관리를 합니다"]


def test_without_trailing_space_model_decides():
    lines = [line("도서", 700), line("관리를 합니다", 686)]
    assert [block.text for block in merge_lines(lines)] == ["도서관리를 합니다"]


def test_trailing_space_is_not_part_of_line_text():
    assert line("도서 ", 700).text == "도서"
    assert line("도서 ", 700).trailing_space and not line("도서", 700).trailing_space
