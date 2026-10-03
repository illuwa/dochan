"""HWP와 HWPX는 글꼴 제목을 문서 본문 크기에 상대적으로 판정한다."""

from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Paragraph, TextRun
from dochan.utils.heading_font import relative_heading_level
from test_hwpx_controls import package


def _paragraph(text, size):
    return Paragraph(runs=[TextRun(text=text, font_size_pt=size)])


def test_twenty_point_title_on_fourteen_point_body_is_h1():
    assert relative_heading_level(_paragraph('문서 제목', 20).runs, 14) == 1


def test_hwp_font_headings_use_document_body_size():
    parser = SectionParser()
    paragraphs = [
        _paragraph("문서 제목", 21),
        _paragraph("본문 문단은 길게 이어지고 여러 글자를 포함합니다.", 14),
        _paragraph("다른 본문 문단 역시 글자 크기가 같습니다.", 14),
        _paragraph("여기에도 본문 문장이 충분히 들어 있습니다.", 14),
        _paragraph("절 제목", 18),
        _paragraph("소제목", 16),
    ]
    for para in paragraphs:
        para.heading_level = parser._detect_heading_level(para)
    parser.finalize_font_headings()
    assert [para.heading_level for para in paragraphs] == [1, 0, 0, 0, 2, 3]


def test_hwpx_font_headings_use_document_body_size(tmp_path):
    items = [("문서 제목", 21),
             ("본문 문단은 길게 이어지고 여러 글자를 포함합니다.", 14),
             ("다른 본문 문단 역시 글자 크기가 같습니다.", 14),
             ("여기에도 본문 문장이 충분히 들어 있습니다.", 14),
             ("절 제목", 18), ("소제목", 16)]
    header = ''.join('<hh:charPr id="%d" height="%d"/>' % (size, size * 100)
                     for _, size in items)
    body = ''.join('<hp:p><hp:run charPrIDRef="%d"><hp:t>%s</hp:t>'
                   '</hp:run></hp:p>' % (size, text) for text, size in items)
    doc = HWPXParser().parse(package(tmp_path, body, header))
    assert doc.errors == []
    assert [para.heading_level for para in doc.sections[0].elements] == [1, 0, 0, 0, 2, 3]
