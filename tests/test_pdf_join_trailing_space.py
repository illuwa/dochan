"""줄 끝에 보이는 공백 글리프가 있으면 다음 줄과 공백으로 잇는다.

한컴이 만든 PDF 에서 앞 단어와 같은 텍스트 그리기 명령 안에 줄 끝 공백이 그려졌으면 원문의 그 자리는 띄어쓰기였다. 공개 정책브리핑 보도자료 짝에서
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


def test_invisible_ocr_text_layer_does_not_use_trailing_space(monkeypatch):
    """OCR 텍스트층(Tr 3)은 단어마다 공백을 붙여 그리므로 줄 끝 공백이 줄바꿈 신호가 아니다(감수 반례)."""
    from dochan.pdf.content import ContentTextExtractor, FontInfo, assemble_lines
    from dochan.pdf.widths import WidthMap
    from dochan.pdf import layout

    class Model:
        def joins_with_space(self, last, first):
            return False

    monkeypatch.setattr(layout, "load_model", lambda: Model())
    font = FontInfo(decode=lambda raw: raw.decode("utf-16-be"), widths=WidthMap({}, 1000.0), code_bytes=2)
    def text(value):
        return "<" + value.encode("utf-16-be").hex() + ">"

    lines = []
    for mode, name in ((0, "visible"), (3, "invisible")):
        content = ("BT %d Tr /F1 10 Tf 72 700 Td %s Tj 0 -14 Td %s Tj ET"
                   % (mode, text("가나다라마바 "), text("사아자차카타"))).encode()
        extractor = ContentTextExtractor.from_fonts({"F1": font})
        assembled = assemble_lines(extractor.extract_fragments(content))
        lines.append((name, [block.text for block in merge_lines(assembled)]))
    assert dict(lines)["visible"] == ["가나다라마바 사아자차카타"]
    assert dict(lines)["invisible"] == ["가나다라마바사아자차카타"]
