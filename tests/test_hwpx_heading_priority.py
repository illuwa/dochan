"""문단 직접 지정과 스타일 기본 개요 간 우선순위 회귀."""

import zipfile

import pytest

from dochan.hwpx.parser import HWPXParser


def _heading_document(tmp_path, direct_type, direct_level, style_name,
                      style_level, font_size=1000, direct_present=True):
    path = tmp_path / "heading-priority.hwpx"
    head_ns = "http://www.hancom.co.kr/hwpml/2011/head"
    para_ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    section_ns = "http://www.hancom.co.kr/hwpml/2011/section"
    direct = (
        '<hh:paraPr id="1"><hh:heading type="%s" level="%d"/></hh:paraPr>'
        % (direct_type, direct_level)
    ) if direct_present else ""
    header = (
        '<hh:head xmlns:hh="%s"><hh:charProperties>'
        '<hh:charPr id="0" height="%d"/></hh:charProperties>'
        '<hh:paraProperties>%s'
        '<hh:paraPr id="2"><hh:heading type="OUTLINE" level="%d"/></hh:paraPr>'
        '</hh:paraProperties><hh:styles>'
        '<hh:style id="1" name="%s" engName="Custom" paraPrIDRef="2"/>'
        '</hh:styles></hh:head>'
    ) % (head_ns, font_size, direct, style_level, style_name)
    section = (
        '<hs:sec xmlns:hs="%s" xmlns:hp="%s">'
        '<hp:p paraPrIDRef="1" styleIDRef="1">'
        '<hp:run charPrIDRef="0"><hp:t>우선순위 확인</hp:t></hp:run>'
        '</hp:p></hs:sec>'
    ) % (section_ns, para_ns)
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/hwp+zip")
        package.writestr("Contents/header.xml", header)
        package.writestr("Contents/section0.xml", section)
    return HWPXParser().parse(str(path)).sections[0].elements[0]


@pytest.mark.parametrize("style_name", ["사용자 개요", "개요 1"])
def test_hwpx_direct_outline_precedes_style(tmp_path, style_name):
    para = _heading_document(tmp_path, "OUTLINE", 1, style_name, 0)
    assert para.heading_level == 2


def test_hwpx_direct_nonoutline_suppresses_style_para_outline(tmp_path):
    para = _heading_document(tmp_path, "NONE", 0, "사용자 정의", 0)
    assert para.heading_level == 0


def test_hwpx_missing_direct_para_falls_back_to_style(tmp_path):
    para = _heading_document(tmp_path, "NONE", 0, "사용자 정의", 1,
                             direct_present=False)
    assert para.heading_level == 2


def test_hwpx_direct_nonoutline_keeps_named_heading_style(tmp_path):
    para = _heading_document(tmp_path, "NONE", 0, "개요 2", 0)
    assert para.heading_level == 2


@pytest.mark.parametrize("direct_level", [3, 4, 5])
@pytest.mark.parametrize("font_size", [1000, 1600])
def test_hwpx_deep_direct_outline_stays_body(
        tmp_path, direct_level, font_size):
    para = _heading_document(tmp_path, "OUTLINE", direct_level, "개요 1", 0,
                             font_size=font_size)
    assert para.heading_level == 0
