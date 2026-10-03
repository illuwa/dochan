"""Pictures in a HWPX paragraph follow its text without splitting the paragraph."""
import zipfile

from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Paragraph
from dochan.model.image import Image
from dochan.model.table import Table
from dochan.output.markdown import to_markdown


NS = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
      'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
      'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" '
      'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"')


def _document(tmp_path, paragraph):
    path = tmp_path / "picture-flow.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", '<hh:head %s><hh:charPr id="7" height="1000"><hh:bold/></hh:charPr></hh:head>' % NS)
        archive.writestr("Contents/section0.xml", '<hs:sec %s>%s</hs:sec>' % (NS, paragraph))
        archive.writestr("Contents/content.hpf", '<package><manifest><item id="image1" href="BinData/image1.png"/>'
                         '<item id="image2" href="BinData/image2.png"/></manifest></package>')
        archive.writestr("BinData/image1.png", b"first-image")
        archive.writestr("BinData/image2.png", b"second-image")
    return HWPXParser().parse(path)


def _pic(number=1, treat_as_char="0"):
    return ('<hp:pic treatAsChar="%s" textWrap="SQUARE">'
            '<hc:img binaryItemIDRef="image%d"/>'
            '<hp:shapeComment>그림 %d</hp:shapeComment></hp:pic>') % (treat_as_char, number, number)


def _types_and_text(elements):
    return [(type(item), item.text if isinstance(item, Paragraph) else "") for item in elements]


def test_picture_inside_sentence_keeps_one_paragraph_and_asset(tmp_path):
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % _pic()
    doc = _document(tmp_path, body)
    elements = doc.sections[0].elements
    assert _types_and_text(elements) == [(Paragraph, "앞뒤"), (Image, "")]
    assert elements[1].alt_text == "그림 1"
    assert elements[1].filename == "BinData/image1.png"
    assert elements[1].image_data == b"first-image"
    assert elements[0]._image_target is elements[1]
    assert "앞뒤\n\n![그림 1]" in to_markdown(doc)


def test_picture_at_start_and_picture_only(tmp_path):
    body = ('<hp:p><hp:run>%s<hp:t>문장</hp:t></hp:run></hp:p>'
            '<hp:p><hp:run>%s</hp:run></hp:p>') % (_pic(treat_as_char="1"), _pic(2))
    doc = _document(tmp_path, body)
    assert _types_and_text(doc.sections[0].elements) == [
        (Paragraph, "문장"), (Image, ""), (Image, "")]


def test_multiple_pictures_keep_source_order_after_text(tmp_path):
    body = '<hp:p><hp:run><hp:t>A</hp:t>%s<hp:t>B</hp:t>%s<hp:t>C</hp:t></hp:run></hp:p>' % (_pic(), _pic(2))
    elements = _document(tmp_path, body).sections[0].elements
    assert _types_and_text(elements) == [(Paragraph, "ABC"), (Image, ""), (Image, "")]
    assert [item.alt_text for item in elements[1:]] == ["그림 1", "그림 2"]


def test_picture_and_table_keep_table_boundary(tmp_path):
    table = ('<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
             '<hp:subList><hp:p><hp:run><hp:t>칸</hp:t></hp:run></hp:p></hp:subList>'
             '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:cellSpan rowSpan="1" colSpan="1"/>'
             '</hp:tc></hp:tr></hp:tbl>')
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>중간</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % (_pic(), table)
    elements = _document(tmp_path, body).sections[0].elements
    assert _types_and_text(elements) == [
        (Paragraph, "앞중간"), (Image, ""), (Table, ""), (Paragraph, "뒤")]


def test_picture_between_link_and_formatted_runs(tmp_path):
    begin = ('<hp:ctrl><hp:fieldBegin type="HYPERLINK" id="1"><hp:parameters>'
             '<hp:stringParam name="Path">https://example.org</hp:stringParam>'
             '</hp:parameters></hp:fieldBegin></hp:ctrl>')
    end = '<hp:ctrl><hp:fieldEnd beginIDRef="1"/></hp:ctrl>'
    body = ('<hp:p><hp:run>%s<hp:t>링크</hp:t>%s<hp:t>계속</hp:t>%s</hp:run>'
            '<hp:run charPrIDRef="7"><hp:t>굵게</hp:t></hp:run></hp:p>') % (begin, _pic(), end)
    elements = _document(tmp_path, body).sections[0].elements
    assert _types_and_text(elements) == [(Paragraph, "링크계속굵게"), (Image, "")]
    assert [(run.text, run.bold, run.link) for run in elements[0].runs] == [
        ("링크", False, "https://example.org"),
        ("계속", False, "https://example.org"),
        ("굵게", True, "")]


def test_picture_in_table_cell_keeps_cell_paragraph(tmp_path):
    body = ('<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
            '<hp:subList><hp:p><hp:run><hp:t>셀 앞</hp:t>%s<hp:t>셀 뒤</hp:t></hp:run></hp:p></hp:subList>'
            '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:cellSpan rowSpan="1" colSpan="1"/>'
            '</hp:tc></hp:tr></hp:tbl></hp:run></hp:p>') % _pic()
    table = _document(tmp_path, body).sections[0].elements[0]
    assert _types_and_text(table.rows[0][0].paragraphs) == [
        (Paragraph, "셀 앞셀 뒤"), (Image, "")]


def test_picture_caption_and_ctrl_wrapper_stay_with_image(tmp_path):
    caption = ('<hp:caption side="TOP"><hp:subList><hp:p><hp:run>'
               '<hp:t>그림 설명</hp:t></hp:run></hp:p></hp:subList></hp:caption>')
    picture = _pic().replace('</hp:pic>', caption + '</hp:pic>')
    body = '<hp:p><hp:run><hp:t>앞</hp:t><hp:ctrl>%s</hp:ctrl><hp:t>뒤</hp:t></hp:run></hp:p>' % picture
    doc = _document(tmp_path, body)
    elements = doc.sections[0].elements
    assert _types_and_text(elements) == [(Paragraph, "앞뒤"), (Image, "")]
    assert elements[1].caption_text == "그림 설명"
    assert elements[1].caption_side == "TOP"
    assert "*그림 설명*" in to_markdown(doc)
