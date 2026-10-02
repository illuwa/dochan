"""OOXML 차트 파트 공통 읽기(dochan.ooxml.charts) 단위 테스트."""
import pytest
from lxml import etree

import dochan.ooxml.charts as charts_module
from dochan.ooxml.charts import chart_caption, chart_series, chart_title, xy_series_rows

_NS = (
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
)


def _chart_space(chart_children: str):
    return etree.fromstring(
        f"<c:chartSpace {_NS}><c:chart>{chart_children}</c:chart></c:chartSpace>".encode("utf-8")
    )


def _rich_title(*paragraphs: str) -> str:
    body = "".join(f"<a:p>{paragraph}</a:p>" for paragraph in paragraphs)
    return f"<c:title><c:tx><c:rich>{body}</c:rich></c:tx></c:title>"


def _run(text: str) -> str:
    return f"<a:r><a:t>{text}</a:t></a:r>"


@pytest.mark.parametrize(
    "plot_xml, expected",
    [
        ("<c:barChart/>", "Chart type: column"),
        ('<c:barChart><c:barDir val="col"/></c:barChart>', "Chart type: column"),
        ('<c:barChart><c:barDir val="bar"/></c:barChart>', "Chart type: bar"),
        ('<c:bar3DChart><c:barDir val="bar"/></c:bar3DChart>', "Chart type: 3-D bar"),
        ("<c:bar3DChart/>", "Chart type: 3-D column"),
        ("<c:lineChart/>", "Chart type: line"),
        ("<c:line3DChart/>", "Chart type: 3-D line"),
        ("<c:pieChart/>", "Chart type: pie"),
        ("<c:pie3DChart/>", "Chart type: 3-D pie"),
        ("<c:doughnutChart/>", "Chart type: doughnut"),
        ("<c:ofPieChart/>", "Chart type: pie of pie"),
        ('<c:ofPieChart><c:ofPieType val="bar"/></c:ofPieChart>', "Chart type: bar of pie"),
        ("<c:areaChart/>", "Chart type: area"),
        ("<c:area3DChart/>", "Chart type: 3-D area"),
        ("<c:scatterChart/>", "Chart type: scatter"),
        ("<c:bubbleChart/>", "Chart type: bubble"),
        ("<c:radarChart/>", "Chart type: radar"),
        ("<c:stockChart/>", "Chart type: stock"),
        ("<c:surfaceChart/>", "Chart type: surface"),
        ("<c:surface3DChart/>", "Chart type: 3-D surface"),
    ],
)
def test_caption_names_chart_type_in_readable_words(plot_xml, expected):
    root = _chart_space(f"<c:plotArea>{plot_xml}</c:plotArea>")

    assert chart_caption(root) == expected


def test_caption_lists_each_type_of_combo_chart_once_in_document_order():
    root = _chart_space(
        "<c:plotArea><c:barChart/><c:lineChart/><c:barChart/></c:plotArea>"
    )

    assert chart_caption(root) == "Chart type: column + line"


def test_caption_is_empty_without_recognised_type_or_axis_title():
    root = _chart_space(
        "<c:plotArea><!-- note --><?pi x?><c:futureChart/><c:layout/></c:plotArea>"
    )

    assert chart_caption(root) == ""


def test_caption_does_not_leak_raw_tag_names_of_unknown_types():
    root = _chart_space("<c:plotArea><c:futureChart/><c:lineChart/></c:plotArea>")

    assert chart_caption(root) == "Chart type: line"


def test_caption_ignores_same_named_elements_outside_chart_namespace():
    root = etree.fromstring(
        f'<c:chartSpace {_NS} xmlns:x="urn:other"><c:chart><c:plotArea>'
        "<x:lineChart/></c:plotArea></c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_caption(root) == ""


def test_caption_appends_axis_titles_by_axis_kind():
    root = _chart_space(
        "<c:plotArea><c:barChart/>"
        f"<c:catAx>{_rich_title(_run('Quarter'))}</c:catAx>"
        f"<c:valAx>{_rich_title(_run('Revenue (KRW)'))}</c:valAx>"
        f"<c:dateAx>{_rich_title(_run('Month'))}</c:dateAx>"
        f"<c:serAx>{_rich_title(_run('Region'))}</c:serAx>"
        "</c:plotArea>"
    )

    assert chart_caption(root) == (
        "Chart type: column; Category axis: Quarter; Value axis: Revenue (KRW); "
        "Date axis: Month; Series axis: Region"
    )


def test_caption_does_not_guess_x_or_y_for_scatter_value_axes():
    # 생성기(openpyxl 등)는 두 값 축 모두 axPos="l" 로 쓰기도 한다 — 위치로 X/Y 를 단정하지 않는다.
    root = _chart_space(
        "<c:plotArea><c:scatterChart/>"
        f'<c:valAx><c:axPos val="l"/>{_rich_title(_run("Dose"))}</c:valAx>'
        f'<c:valAx><c:axPos val="l"/>{_rich_title(_run("Response"))}</c:valAx>'
        "</c:plotArea>"
    )

    assert chart_caption(root) == (
        "Chart type: scatter; Value axis: Dose; Value axis: Response"
    )


def test_caption_skips_deleted_axes_and_untitled_axes():
    root = _chart_space(
        "<c:plotArea><c:lineChart/>"
        f'<c:catAx><c:delete val="1"/>{_rich_title(_run("Hidden"))}</c:catAx>'
        "<c:valAx/>"
        "</c:plotArea>"
    )

    assert chart_caption(root) == "Chart type: line"


def test_caption_reads_delete_without_val_as_hidden_and_val_zero_as_shown():
    # CT_Boolean 의 val 기본값은 true — <c:delete/> 는 숨긴 축이다.
    root = _chart_space(
        "<c:plotArea><c:lineChart/>"
        f"<c:catAx><c:delete/>{_rich_title(_run('Hidden'))}</c:catAx>"
        f'<c:valAx><c:delete val="0"/>{_rich_title(_run("Shown"))}</c:valAx>'
        "</c:plotArea>"
    )

    assert chart_caption(root) == "Chart type: line; Value axis: Shown"


@pytest.mark.parametrize("value, shown", [("true", False), ("1", False), ("false", True), ("0", True)])
def test_caption_honours_explicit_delete_values(value, shown):
    root = _chart_space(
        "<c:plotArea><c:lineChart/>"
        f'<c:valAx><c:delete val="{value}"/>{_rich_title(_run("KRW"))}</c:valAx>'
        "</c:plotArea>"
    )

    expected = "Chart type: line; Value axis: KRW" if shown else "Chart type: line"
    assert chart_caption(root) == expected


_MC = 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'


def test_caption_reads_one_branch_of_alternate_content_in_plot_area():
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC} xmlns:c14=\"http://schemas.microsoft.com/office/drawing/2007/8/2/chart\">"
        "<c:chart><c:plotArea><mc:AlternateContent>"
        '<mc:Choice Requires="c14"><c14:futureGroup/></mc:Choice>'
        "<mc:Fallback><c:lineChart/>"
        f"<c:valAx>{_rich_title(_run('KRW'))}</c:valAx></mc:Fallback>"
        "</mc:AlternateContent></c:plotArea></c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_caption(root) == "Chart type: line; Value axis: KRW"


def test_caption_does_not_double_count_both_alternate_content_branches():
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC}><c:chart><c:plotArea><mc:AlternateContent>"
        f'<mc:Choice Requires="c14"><c:barChart/><c:valAx>{_rich_title(_run("A"))}</c:valAx></mc:Choice>'
        f"<mc:Fallback><c:lineChart/><c:valAx>{_rich_title(_run('B'))}</c:valAx></mc:Fallback>"
        "</mc:AlternateContent></c:plotArea></c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_caption(root) == "Chart type: column; Value axis: A"


def test_title_reads_text_wrapped_in_alternate_content():
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC}><c:chart><c:title><mc:AlternateContent>"
        '<mc:Choice Requires="c14"><c:tx><c:rich><a:p><a:r><a:t>Wrapped</a:t></a:r></a:p></c:rich></c:tx></mc:Choice>'
        "<mc:Fallback><c:tx><c:rich><a:p><a:r><a:t>Wrapped</a:t></a:r></a:p></c:rich></c:tx></mc:Fallback>"
        "</mc:AlternateContent></c:title></c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_title(root) == "Wrapped"


def test_caption_stops_listing_axes_at_the_cap(monkeypatch):
    monkeypatch.setattr(charts_module, "MAX_CAPTION_AXES", 3)
    axes = "".join(f"<c:valAx>{_rich_title(_run(f'A{index}'))}</c:valAx>" for index in range(10))
    root = _chart_space(f"<c:plotArea><c:barChart/>{axes}</c:plotArea>")

    assert chart_caption(root) == (
        "Chart type: column; Value axis: A0; Value axis: A1; Value axis: A2"
    )


def test_title_reads_only_the_chart_title_not_axis_titles():
    root = _chart_space(
        _rich_title(_run("Revenue Chart"))
        + "<c:plotArea><c:barChart/>"
        + f"<c:catAx>{_rich_title(_run('Quarter'))}</c:catAx>"
        + "</c:plotArea>"
    )

    assert chart_title(root) == "Revenue Chart"


def test_title_is_empty_when_only_an_axis_has_a_title():
    root = _chart_space(
        "<c:plotArea><c:barChart/>"
        f"<c:catAx>{_rich_title(_run('Quarter'))}</c:catAx>"
        "</c:plotArea>"
    )

    assert chart_title(root) == ""


def test_title_joins_runs_without_space_and_paragraphs_with_space():
    root = _chart_space(
        _rich_title(_run("Rev") + _run("enue"), _run("2026  plan"))
    )

    assert chart_title(root) == "Revenue 2026  plan"


def test_title_preserves_whitespace_inside_runs():
    root = _chart_space(_rich_title(_run(" Q1\u00a0실적 ")))

    assert chart_title(root) == "Q1\u00a0실적"


def test_title_keeps_words_apart_across_line_breaks():
    root = _chart_space(_rich_title(_run("Sales") + "<a:br/>" + _run("2024")))

    assert chart_title(root) == "Sales 2024"


def test_title_reads_field_text_next_to_runs():
    root = _chart_space(
        _rich_title(_run("Page ") + '<a:fld id="{1}" type="slidenum"><a:t>3</a:t></a:fld>')
    )

    assert chart_title(root) == "Page 3"


def test_title_falls_back_to_cached_string_reference():
    root = _chart_space(
        "<c:title><c:tx><c:strRef><c:f>Sheet1!$A$1</c:f><c:strCache>"
        '<c:pt idx="0"><c:v>Linked Title</c:v></c:pt>'
        "</c:strCache></c:strRef></c:tx></c:title>"
    )

    assert chart_title(root) == "Linked Title"


def test_title_and_caption_are_empty_without_chart_element():
    root = etree.fromstring(f"<c:chartSpace {_NS}/>".encode("utf-8"))

    assert chart_title(root) == ""
    assert chart_caption(root) == ""


def test_caption_skips_a_choice_branch_that_resolves_to_nothing():
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC}><c:chart><c:plotArea><mc:AlternateContent>"
        "<mc:Choice Requires=\"c14\"><mc:AlternateContent/></mc:Choice>"
        "<mc:Fallback><c:barChart/></mc:Fallback>"
        "</mc:AlternateContent></c:plotArea></c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_caption(root) == "Chart type: column"


def test_caption_reads_axis_title_wrapped_in_alternate_content():
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC}><c:chart><c:plotArea><c:barChart/><c:catAx>"
        "<mc:AlternateContent><mc:Choice Requires=\"c14\">"
        f"{_rich_title(_run('Quarter'))}</mc:Choice></mc:AlternateContent>"
        "</c:catAx></c:plotArea></c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_caption(root) == "Chart type: column; Category axis: Quarter"


def test_title_reads_nested_alternate_content_text_once():
    nested = (
        '<mc:AlternateContent><mc:Choice Requires="a14">' + _run("B") + "</mc:Choice>"
        "<mc:Fallback>" + _run("B") + "</mc:Fallback></mc:AlternateContent>"
    )
    title = _rich_title(
        '<mc:AlternateContent><mc:Choice Requires="a14">' + _run("A") + nested + "</mc:Choice>"
        "<mc:Fallback>" + _run("A") + _run("B") + "</mc:Fallback></mc:AlternateContent>"
    )
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC}><c:chart>{title}</c:chart></c:chartSpace>".encode("utf-8")
    )

    assert chart_title(root) == "AB"


def test_title_does_not_double_space_after_a_trailing_line_break():
    root = _chart_space(_rich_title(_run("Sales") + "<a:br/>", _run("2024")))

    assert chart_title(root) == "Sales 2024"


def test_chart_series_reads_one_alternate_content_branch_in_plot_area():
    series = "<c:ser><c:tx><c:v>{}</c:v></c:tx></c:ser>"
    root = etree.fromstring(
        f"<c:chartSpace {_NS} {_MC}><c:chart><c:plotArea><mc:AlternateContent>"
        f'<mc:Choice Requires="c14"><c:barChart>{series.format("Choice")}</c:barChart></mc:Choice>'
        f"<mc:Fallback><c:barChart>{series.format('Fallback')}</c:barChart></mc:Fallback>"
        f"</mc:AlternateContent><c:lineChart>{series.format('Line')}</c:lineChart>"
        "</c:plotArea></c:chart></c:chartSpace>".encode("utf-8")
    )

    names = [ser.find(f"{{{charts_module.C_NS}}}tx/{{{charts_module.C_NS}}}v").text for ser in chart_series(root)]

    assert names == ["Choice", "Line"]


def test_long_xy_rows_number_points_of_a_series_without_x_source():
    rows = xy_series_rows(
        [("A", {0: "1.5", 1: "2.5"}, {0: "5", 1: "6"}), ("B", {}, {0: "7", 1: "8"})],
        True,
        implicit_x=[False, True],
    )

    assert rows == [
        ["Series", "X", "Y"],
        ["A", "1.5", "5"],
        ["A", "2.5", "6"],
        ["B", "1", "7"],
        ["B", "2", "8"],
    ]


def test_long_xy_rows_leave_x_blank_when_the_x_cache_is_missing():
    rows = xy_series_rows(
        [("A", {0: "1.5"}, {0: "5"}), ("B", {}, {0: "7"})],
        True,
        implicit_x=[False, False],
    )

    assert rows == [["Series", "X", "Y"], ["A", "1.5", "5"], ["B", "", "7"]]


@pytest.mark.parametrize(
    "runs, expected",
    [
        (_run("Sales ") + "<a:br/>" + _run("2024"), "Sales 2024"),
        (_run("Sales") + "<a:br/>" + _run(" 2024"), "Sales 2024"),
        (_run("Sales") + "<a:br/><a:br/>" + _run("2024"), "Sales 2024"),
        ("<a:br/>" + _run("Sales"), "Sales"),
        (_run("A") + _run(" ") + _run(" B"), "A  B"),
    ],
)
def test_title_line_breaks_add_at_most_one_space(runs, expected):
    assert chart_title(_chart_space(_rich_title(runs))) == expected
