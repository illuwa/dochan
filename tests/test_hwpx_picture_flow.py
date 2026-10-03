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
        archive.writestr("Contents/header.xml", ('<hh:head %s><hh:charPr id="7" height="1000">'
                         '<hh:bold/></hh:charPr><hh:charPr id="8" height="2000"/>'
                         '</hh:head>') % NS)
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
    assert "앞뒤\n\n![그림 1]" in to_markdown(doc)


def test_textbox_picture_stays_before_outer_suffix(tmp_path):
    box = ('<hp:rect><hp:drawText><hp:subList><hp:p><hp:run>'
           '<hp:t>상자 앞</hp:t>%s<hp:t>상자 뒤</hp:t>'
           '</hp:run></hp:p></hp:subList></hp:drawText></hp:rect>') % _pic()
    body = '<hp:p><hp:run><hp:t>밖 앞</hp:t>%s<hp:t>밖 뒤</hp:t></hp:run></hp:p>' % box
    elements = _document(tmp_path, body).sections[0].elements
    assert _types_and_text(elements) == [
        (Paragraph, "밖 앞"), (Paragraph, "상자 앞상자 뒤"),
        (Image, ""), (Paragraph, "밖 뒤")]


def test_direct_picture_in_textbox_and_group_keeps_deferred_order(tmp_path):
    textbox = ('<hp:rect><hp:drawText><hp:subList><hp:p><hp:run>'
               '<hp:t>상자</hp:t></hp:run></hp:p></hp:subList></hp:drawText></hp:rect>')
    for drawing in (_pic() + textbox, '<hp:container>%s%s</hp:container>' % (_pic(), textbox)):
        body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % drawing
        elements = _document(tmp_path, body).sections[0].elements
        assert _types_and_text(elements) == [
            (Paragraph, "앞"), (Image, ""), (Paragraph, "상자"), (Paragraph, "뒤")]


def test_picture_only_textbox_stays_deferred(tmp_path):
    box = ('<hp:rect><hp:drawText><hp:subList><hp:p><hp:run>%s'
           '</hp:run></hp:p></hp:subList></hp:drawText></hp:rect>') % _pic()
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % box
    assert _types_and_text(_document(tmp_path, body).sections[0].elements) == [
        (Paragraph, '앞뒤'), (Image, '')]


def test_header_footer_picture_stays_with_nested_paragraph(tmp_path):
    controls = ''.join(
        '<hp:ctrl><hp:%s><hp:subList><hp:p><hp:run><hp:t>%s 앞</hp:t>%s'
        '<hp:t>%s 뒤</hp:t></hp:run></hp:p></hp:subList></hp:%s></hp:ctrl>'
        % (kind, kind, _pic(number), kind, kind)
        for number, kind in ((1, 'header'), (2, 'footer')))
    body = '<hp:p><hp:run>%s<hp:t>본문</hp:t></hp:run></hp:p>' % controls
    elements = _document(tmp_path, body).sections[0].elements
    assert [item.type for item in elements[:2]] == ['header', 'footer']
    for item, kind in zip(elements[:2], ('header', 'footer')):
        assert _types_and_text(item.paragraphs) == [(Paragraph, kind + ' 앞' + kind + ' 뒤'), (Image, '')]
    assert _types_and_text(elements[2:]) == [(Paragraph, '본문')]


def test_equation_after_picture_keeps_boundary(tmp_path):
    body = ('<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>중</hp:t>'
            '<hp:equation><hp:script>x+1</hp:script></hp:equation>'
            '<hp:t>뒤</hp:t></hp:run></hp:p>') % _pic()
    from dochan.model.equation import Equation
    elements = _document(tmp_path, body).sections[0].elements
    assert _types_and_text(elements) == [
        (Paragraph, '앞중'), (Image, ''), (Equation, ''), (Paragraph, '뒤')]


def test_heading_uses_first_nonblank_run(tmp_path):
    for first, second, expected in ((7, 8, 1), (8, 7, 0)):
        body = ('<hp:p><hp:run charPrIDRef="%d"><hp:t> </hp:t></hp:run>'
                '<hp:run charPrIDRef="%d"><hp:t>실제 제목</hp:t></hp:run></hp:p>') % (first, second)
        paragraph = _document(tmp_path, body).sections[0].elements[0]
        assert paragraph.heading_level == expected


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
