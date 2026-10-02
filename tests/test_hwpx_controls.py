"""HWPX form objects use the existing displayed-text output contract."""
import zipfile

import pytest

from dochan.hwpx.parser import HWPXParser
from dochan.output.markdown import to_markdown

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def package(tmp_path, body, header=""):
    path = tmp_path / "controls.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", '<hh:head xmlns:hh="%s">%s</hh:head>' % (HH, header))
        archive.writestr("Contents/section0.xml", '<hs:sec xmlns:hs="%s" xmlns:hp="%s">%s</hs:sec>' % (HS, HP, body))
    return path


@pytest.mark.parametrize("wrapped", [False, True])
def test_hwpx_form_display_text_keeps_inline_order(tmp_path, wrapped):
    controls = [
        '<hp:btn caption="실행" command="DO_NOT_OUTPUT"/>',
        '<hp:checkBtn caption="동의" value="CHECKED"/>',
        '<hp:radioBtn caption="선택" value="UNCHECKED"/>',
        '<hp:comboBox selectedValue="second"><hp:listItem value="first" displayText="비선택"/>'
        '<hp:listItem value="second" displayText="선택값"/></hp:comboBox>',
        '<hp:edit><hp:text>입력 내용</hp:text></hp:edit>',
    ]
    if wrapped:
        controls = ['<hp:ctrl>%s</hp:ctrl>' % control for control in controls]
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % ''.join(controls)
    doc = HWPXParser().parse(package(tmp_path, body))
    assert doc.errors == []
    assert [p.text for p in doc.sections[0].elements] == ["앞실행[x]동의[ ]선택선택값입력 내용뒤"]
    assert "DO_NOT_OUTPUT" not in to_markdown(doc)
    assert "비선택" not in to_markdown(doc)


@pytest.mark.parametrize("selected,items,expected", [
    ("", '<hp:listItem value="one" displayText="선택 안내"/>', ""),
    ("free text", '<hp:listItem value="one" displayText="후보"/>', "free text"),
    ("one", '<hp:listItem value="one" displayText=""/>', "one"),
])
def test_hwpx_combo_only_emits_current_value(tmp_path, selected, items, expected):
    body = '<hp:p><hp:run><hp:t>앞</hp:t><hp:comboBox selectedValue="%s">%s</hp:comboBox><hp:t>뒤</hp:t></hp:run></hp:p>' % (selected, items)
    doc = HWPXParser().parse(package(tmp_path, body))
    assert doc.sections[0].elements[0].text == "앞" + expected + "뒤"


def test_hwpx_click_here_keeps_guide_or_input_once(tmp_path):
    begin = '<hp:ctrl><hp:fieldBegin type="CLICK_HERE" id="1"><hp:parameters><hp:stringParam name="Direction">안내문</hp:stringParam></hp:parameters></hp:fieldBegin></hp:ctrl>'
    end = '<hp:ctrl><hp:fieldEnd beginIDRef="1"/></hp:ctrl>'
    body = ''.join('<hp:p><hp:run>%s<hp:t>%s</hp:t>%s</hp:run></hp:p>' % (begin, text, end) for text in ("안내문", "입력값"))
    doc = HWPXParser().parse(package(tmp_path, body))
    assert [p.text for p in doc.sections[0].elements] == ["안내문", "입력값"]


def test_hwpx_form_text_uses_form_char_properties(tmp_path):
    header = '<hh:charPr id="0" height="1000"/><hh:charPr id="7" height="1100"><hh:bold/></hh:charPr>'
    body = '<hp:p><hp:run charPrIDRef="0"><hp:t>앞</hp:t><hp:edit><hp:formCharPr charPrIDRef="7" followContext="0"/><hp:text>값</hp:text></hp:edit><hp:t>뒤</hp:t></hp:run></hp:p>'
    doc = HWPXParser().parse(package(tmp_path, body, header))
    runs = doc.sections[0].elements[0].runs
    assert [(r.text, r.bold) for r in runs] == [("앞", False), ("값", True), ("뒤", False)]


def test_hwpx_style_shape_references_preserve_direct_override(tmp_path):
    header = ('<hh:charPr id="0" height="1000"/><hh:charPr id="7" height="1100"><hh:bold/></hh:charPr>'
              '<hh:paraPr id="3"><hh:heading type="OUTLINE" level="1"/></hh:paraPr>'
              '<hh:style id="2" type="PARA" name="사용자 제목" paraPrIDRef="3" charPrIDRef="7" nextStyleIDRef="2"/>')
    body = '<hp:p styleIDRef="2" paraPrIDRef="3"><hp:run charPrIDRef="7"><hp:t>제목</hp:t></hp:run><hp:run charPrIDRef="0"><hp:t>보통</hp:t></hp:run></hp:p>'
    doc = HWPXParser().parse(package(tmp_path, body, header))
    para = doc.sections[0].elements[0]
    assert para.heading_level == 2
    assert [(r.text, r.bold) for r in para.runs] == [("제목", True), ("보통", False)]
    assert (doc.styles[0].char_shape_id, doc.styles[0].para_shape_id) == (7, 3)


@pytest.mark.parametrize("wrapped", [False, True])
def test_hwpx_form_follow_context_preserves_host_format(tmp_path, wrapped):
    header = '<hh:charPr id="7" height="1100"><hh:bold/></hh:charPr>'
    form = '<hp:edit><hp:formCharPr charPrIDRef="0" followContext="1"/><hp:text>값</hp:text></hp:edit>'
    if wrapped:
        form = '<hp:ctrl>' + form + '</hp:ctrl>'
    body = '<hp:p><hp:run charPrIDRef="7"><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % form
    doc = HWPXParser().parse(package(tmp_path, body, header))
    assert [(r.text, r.bold, r.font_size_pt) for r in doc.sections[0].elements[0].runs] == [("앞", True, 11), ("값", True, 11), ("뒤", True, 11)]


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("password_char", ["*", "X"])
def test_hwpx_password_edit_never_outputs_contents(tmp_path, wrapped, password_char):
    control = '<hp:edit passwordChar="%s"><hp:text>secret123</hp:text></hp:edit>' % password_char
    if wrapped:
        control = '<hp:ctrl>' + control + '</hp:ctrl>'
    body = '<hp:p><hp:run><hp:t>before</hp:t>' + control + '<hp:t>after</hp:t></hp:run></hp:p>'
    doc = HWPXParser().parse(package(tmp_path, body))
    assert doc.sections[0].elements[0].text == "beforeafter"
    assert "secret123" not in to_markdown(doc)


@pytest.mark.parametrize("tag", ["checkBtn", "radioBtn"])
@pytest.mark.parametrize("value,marker", [("CHECKED", "[x]"), ("UNCHECKED", "[ ]")])
@pytest.mark.parametrize("caption", ["선택", ""])
def test_hwpx_check_and_radio_preserve_state(tmp_path, tag, value, marker, caption):
    body = '<hp:p><hp:run><hp:%s caption="%s" value="%s"/></hp:run></hp:p>' % (tag, caption, value)
    doc = HWPXParser().parse(package(tmp_path, body))
    assert doc.sections[0].elements[0].text == marker + caption
