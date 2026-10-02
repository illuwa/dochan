"""OOXML 차트 파트(c:chartSpace)에서 형식과 무관하게 같은 방식으로 읽는 부분.

PPTX·XLSX 리더가 함께 쓴다. 계열 데이터 표와 자원 한도는 각 리더가 맡고, 여기서는
차트 제목, "데이터 표에 붙일 설명 한 줄"(차트 종류·축 제목), 그리고 둘을 표와 엮는 순서를 맡는다.

- 제목은 `c:chart/c:title` 만 본다. 축 제목(`c:catAx/c:title` 등)은 차트 제목이 아니다.
- 종류는 `c:plotArea` 의 직계 자식만 보고 사람이 읽는 말로 바꾼다. 모르는 종류의 태그
  이름은 내보내지 않는다. 혼합 차트는 문서 순서대로 ` + ` 로 잇는다.
- 세로/가로 막대는 태그가 아니라 `c:barDir` 로 갈린다(스키마 기본값 col).
- 축 제목은 축 종류(범주·값·날짜·계열)로 부르고, 숨긴 축(`c:delete`)은 뺀다. 분산형의 두 값 축을
  X/Y 로 가르지는 않는다 — `c:axPos` 는 생성기에 따라 두 축 모두 `l` 이라 믿을 수 없다.
- `mc:AlternateContent` 는 차트 요소를 가진 첫 갈래(Choice 순서, 그다음 Fallback) 하나만 읽는다.
  두 갈래를 다 읽으면 같은 내용이 두 번 나온다.
"""
from typing import Callable, List, Optional, Tuple

from ..model.document import Paragraph, TextRun
from ..model.table import Cell, Table

C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS = {"c": C_NS, "a": A_NS}
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_C = f"{{{C_NS}}}"
_A = f"{{{A_NS}}}"
_MC = f"{{{MC_NS}}}"
_MAX_ALTERNATE_DEPTH = 4

# 실제 차트의 축은 주·보조 범주/값 축과 3-D 계열 축을 합쳐도 다섯 개 남짓이다.
# 조작된 파트가 축 수십만 개로 한 줄 캡션을 수 MB 로 키우지 못하게 막는다.
MAX_CAPTION_AXES = 8

_TYPE_LABELS = {
    "areaChart": "area",
    "area3DChart": "3-D area",
    "lineChart": "line",
    "line3DChart": "3-D line",
    "pieChart": "pie",
    "pie3DChart": "3-D pie",
    "doughnutChart": "doughnut",
    "scatterChart": "scatter",
    "bubbleChart": "bubble",
    "radarChart": "radar",
    "stockChart": "stock",
    "surfaceChart": "surface",
    "surface3DChart": "3-D surface",
}
_AXIS_LABELS = {
    "catAx": "Category axis",
    "valAx": "Value axis",
    "dateAx": "Date axis",
    "serAx": "Series axis",
}


def chart_elements(chart_root, table, paragraph: Callable[[str], object]) -> List[object]:
    """차트 하나의 출력 요소: 제목 문단(3단계) → 데이터 표(종류·축 제목은 위쪽 캡션).

    paragraph(text) 는 리더가 출처 정보를 채운 Paragraph 를 돌려준다. 데이터 표가 비면
    (계열 없음, 자원 한도 초과) 캡션을 붙일 곳이 없으므로, 원문 글자인 축 제목이 있을 때만
    캡션을 일반 문단 하나로 낸다. 종류만 있는 빈 차트는 아무것도 내지 않는다.
    """
    elements = []
    title = chart_title(chart_root)
    if title:
        heading = paragraph(title)
        heading.heading_level = 3
        elements.append(heading)
    type_labels, axis_titles = _annotations(chart_root)
    caption = _caption(type_labels, axis_titles)
    if table.rows:
        if caption:
            table.caption = [paragraph(caption)]
            table.caption_side = "TOP"
        elements.append(table)
    elif axis_titles:
        elements.append(paragraph(caption))
    return elements


def xy_series_rows(series_items, xy: bool) -> Optional[List[List[str]]]:
    """분산형·거품형 계열의 X 값이 계열마다 다르면 (계열, X, Y) 긴 표의 행들. 아니면 None.

    series_items 는 리더가 모은 (계열 이름, {idx: X 또는 범주}, {idx: Y 또는 값}) 목록이다.
    X 를 공유하는 계열은 X 한 열과 계열별 Y 열로 묶는 편이 읽기 쉬우니 리더의 기존 표를 쓴다.
    X 가 다른데 idx 로 묶으면 첫 계열의 X 가 다른 계열의 Y 에 붙어 좌표가 틀어진다.
    """
    if not xy or len(series_items) < 2:
        return None
    first_xs = series_items[0][1]
    if all(xs == first_xs for _, xs, _ in series_items[1:]):
        return None
    rows = [["Series", "X", "Y"]]
    for position, (name, xs, ys) in enumerate(series_items):
        label = name or f"Series {position + 1}"
        for index in sorted(set(xs) | set(ys)):
            rows.append([label, xs.get(index, ""), ys.get(index, "")])
    return rows


def text_table(rows: List[List[str]]) -> Table:
    return Table(
        rows=[
            [Cell(paragraphs=[Paragraph(runs=[TextRun(text=text)])]) for text in row]
            for row in rows
        ]
    )


def chart_title(chart_root) -> str:
    """차트 자체의 제목. 축 제목만 있는 차트는 빈 문자열."""
    chart = _chart(chart_root)
    if chart is None:
        return ""
    return _title_text(_child(chart, "title"))


def chart_caption(chart_root) -> str:
    """데이터 표 위에 붙일 한 줄: `Chart type: column + line; Category axis: 분기`.

    알아볼 종류도 축 제목도 없으면 빈 문자열.
    """
    return _caption(*_annotations(chart_root))


def _annotations(chart_root) -> Tuple[List[str], List[str]]:
    chart = _chart(chart_root)
    if chart is None:
        return [], []
    plot_area = _child(chart, "plotArea")
    if plot_area is None:
        return [], []
    return _type_labels(plot_area), _axis_titles(plot_area)


def _caption(type_labels: List[str], axis_titles: List[str]) -> str:
    parts = []
    if type_labels:
        parts.append("Chart type: " + " + ".join(type_labels))
    parts.extend(axis_titles)
    return "; ".join(parts)


def _chart(chart_root):
    if chart_root is None:
        return None
    if chart_root.tag == _C + "chart":
        return chart_root
    return _child(chart_root, "chart")


def _child(parent, name: str):
    for child_name, child in _chart_children(parent):
        if child_name == name:
            return child
    return None


def _chart_children(parent, depth: int = 0):
    """(지역 이름, 요소) — 차트 네임스페이스의 자식만. 주석·PI·다른 네임스페이스는 건너뛰고,
    mc:AlternateContent 는 고른 한 갈래의 자식을 제자리에 펼친다."""
    for child in parent:
        tag = child.tag
        if not isinstance(tag, str):
            continue
        if tag.startswith(_C):
            yield tag[len(_C):], child
        elif tag == _MC + "AlternateContent" and depth < _MAX_ALTERNATE_DEPTH:
            branch = _alternate_branch(child, _has_chart_child)
            if branch is not None:
                yield from _chart_children(branch, depth + 1)


def _alternate_branch(alternate, wanted):
    """조건에 맞는 첫 갈래: mc:Choice 를 문서 순서로, 그다음 mc:Fallback."""
    for branch in alternate:
        if branch.tag == _MC + "Choice" and wanted(branch):
            return branch
    for branch in alternate:
        if branch.tag == _MC + "Fallback" and wanted(branch):
            return branch
    return None


def _has_chart_child(branch) -> bool:
    return any(
        isinstance(child.tag, str)
        and (child.tag.startswith(_C) or child.tag == _MC + "AlternateContent")
        for child in branch
    )


def _has_text(branch) -> bool:
    return branch.find(".//a:t", namespaces=_NS) is not None


def _type_labels(plot_area) -> List[str]:
    labels = []
    for name, child in _chart_children(plot_area):
        label = _type_label(name, child)
        if label and label not in labels:
            labels.append(label)
    return labels


def _type_label(name: str, elem) -> str:
    if name in ("barChart", "bar3DChart"):
        direction = "bar" if _val(elem, "c:barDir") == "bar" else "column"
        return f"3-D {direction}" if name == "bar3DChart" else direction
    if name == "ofPieChart":
        return "bar of pie" if _val(elem, "c:ofPieType") == "bar" else "pie of pie"
    return _TYPE_LABELS.get(name, "")


def _axis_titles(plot_area) -> List[str]:
    titles = []
    for name, child in _chart_children(plot_area):
        label = _AXIS_LABELS.get(name)
        if not label or _flag(child, "c:delete"):
            continue
        text = _title_text(child.find("c:title", namespaces=_NS))
        if text:
            titles.append(f"{label}: {text}")
            if len(titles) >= MAX_CAPTION_AXES:
                break
    return titles


def _val(elem, path: str) -> str:
    child = elem.find(path, namespaces=_NS)
    return (child.get("val") or "").strip() if child is not None else ""


def _flag(elem, path: str) -> bool:
    """CT_Boolean: 요소가 없으면 거짓, val 이 없으면 스키마 기본값인 참."""
    child = elem.find(path, namespaces=_NS)
    if child is None:
        return False
    value = child.get("val")
    return value is None or value.strip().lower() in ("1", "true")


def _title_text(title) -> str:
    """c:title 의 글자. 서식 때문에 쪼개진 런은 그대로 붙이고(런 안의 공백은 보존), 줄바꿈(a:br)과
    문단은 공백 하나로 잇는다."""
    if title is None:
        return ""
    tx = _child(title, "tx")
    if tx is None:
        return ""
    rich = _child(tx, "rich")
    if rich is not None:
        paragraphs = [
            _paragraph_text(paragraph)
            for paragraph in rich.iterfind("a:p", namespaces=_NS)
        ]
        text = " ".join(paragraph for paragraph in paragraphs if paragraph.strip()).strip()
        if text:
            return text
    str_ref = _child(tx, "strRef")
    if str_ref is None:
        return ""
    return " ".join(
        node.text
        for node in str_ref.iterfind("c:strCache/c:pt/c:v", namespaces=_NS)
        if node.text
    ).strip()


def _paragraph_text(paragraph) -> str:
    parts = []
    for child in paragraph:
        tag = child.tag
        if not isinstance(tag, str):
            continue
        if tag == _A + "br":
            if parts and parts[-1] and not parts[-1][-1].isspace():
                parts.append(" ")
            continue
        if tag == _MC + "AlternateContent":
            child = _alternate_branch(child, _has_text)
            if child is None:
                continue
        # a:r·a:fld 의 글자 (pPr·endParaRPr 에는 a:t 가 없다).
        text = "".join(node.text or "" for node in child.iterfind(".//a:t", namespaces=_NS))
        if text:
            parts.append(text)
    return "".join(parts)
