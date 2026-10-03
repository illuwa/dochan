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
        '<hp:comboBox selectedValue=""><hp:listItem value="선택값" displayText=""/>'
        '<hp:listItem value="비선택" displayText="표시글"/></hp:comboBox>',
        '<hp:edit><hp:text>입력 내용</hp:text></hp:edit>',
    ]
    if wrapped:
        controls = ['<hp:ctrl>%s</hp:ctrl>' % control for control in controls]
    body = '<hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t></hp:run></hp:p>' % ''.join(controls)
    doc = HWPXParser().parse(package(tmp_path, body))
    assert doc.errors == []
    assert [p.text for p in doc.sections[0].elements] == ["앞실행[x]동의[ ]선택선택값입력 내용뒤"]
    assert "DO_NOT_OUTPUT" not in to_markdown(doc)
    assert "비선택" not in to_markdown(doc) and "표시글" not in to_markdown(doc)


# 한컴오피스 HWP(Mac) 화면 실측(form-01.hwpx 의 XML 만 바꾼 통제 표본 6개): 콤보 상자는 selectedValue 와
# displayText 에 관계없이 첫 listItem 의 value 를 표시하고, 항목이 없으면 컨트롤 이름을 자리표시자로 보인다.
# 한컴은 HWP 의 ComboBoxSet Text 를 HWPX 첫 listItem value 로 저장한다(공개 form-01 짝).
@pytest.mark.parametrize("selected,items,expected", [
    ("", '<hp:listItem value="첫째값" displayText=""/><hp:listItem value="둘째값" displayText=""/>', "첫째값"),
    ("둘째값", '<hp:listItem value="첫째값" displayText=""/><hp:listItem value="둘째값" displayText=""/>', "첫째값"),
    ("", '<hp:listItem value="저장값" displayText="보이는글"/>', "저장값"),
    ("저장값2", '<hp:listItem value="저장값1" displayText="보이는글1"/>'
                '<hp:listItem value="저장값2" displayText="보이는글2"/>', "저장값1"),
    ("목록밖", '<hp:listItem value="첫째값" displayText=""/>', "첫째값"),
    ("", '', ""),
])
def test_hwpx_combo_shows_first_list_value_like_hancom(tmp_path, selected, items, expected):
    body = '<hp:p><hp:run><hp:t>앞</hp:t><hp:comboBox name="ComboBox1" selectedValue="%s">%s</hp:comboBox><hp:t>뒤</hp:t></hp:run></hp:p>' % (selected, items)
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


@pytest.mark.parametrize("raw,shown", [
    ("가&amp;나 A&amp;&amp;B 끝&amp;", "가나 A&B 끝"),
    ("&amp;첫 중&amp;&amp;&amp;간", "첫 중&간"),
    ("R&amp;&amp;D &amp;&amp;&amp;&amp;", "R&D &&"),
])
def test_hwpx_button_captions_hide_mnemonic_ampersands_like_hancom(tmp_path, raw, shown):
    # 한컴오피스 화면 실측(form-01.hwpx 캡션만 바꾼 통제 표본). 입력 상자 글은 캡션이 아니라 그대로다.
    body = ('<hp:p><hp:run><hp:btn caption="%s"/></hp:run></hp:p>'
            '<hp:p><hp:run><hp:checkBtn caption="%s" value="CHECKED"/></hp:run></hp:p>'
            '<hp:p><hp:run><hp:radioBtn caption="%s"/></hp:run></hp:p>'
            '<hp:p><hp:run><hp:edit><hp:text>%s</hp:text></hp:edit></hp:run></hp:p>') % (raw, raw, raw, raw)
    doc = HWPXParser().parse(package(tmp_path, body))
    literal = raw.replace("&amp;", "&")
    assert [p.text for p in doc.sections[0].elements] == [shown, "[x]" + shown, "[ ]" + shown, literal]
    combo = '<hp:p><hp:run><hp:comboBox selectedValue=""><hp:listItem value="%s"/></hp:comboBox></hp:run></hp:p>' % raw
    assert HWPXParser().parse(package(tmp_path, combo)).sections[0].elements[0].text == literal
