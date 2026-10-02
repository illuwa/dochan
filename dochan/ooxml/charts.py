"""OOXML 차트 파트(c:chartSpace)에서 형식과 무관하게 같은 방식으로 읽는 부분.

DOCX·PPTX·XLSX·HWPX 리더가 함께 쓴다. 계열 데이터 표와 자원 한도는 각 리더가 맡고, 여기서는
차트 제목, "데이터 표에 붙일 설명 한 줄"(차트 종류·축 제목), 그리고 둘을 표와 엮는 순서를 맡는다.

- 명시적 제목을 우선하고, 자동 생성을 명시한 단일 계열 제목은 계열 이름을 쓴다.
- 종류는 `c:plotArea` 의 직계 자식만 보고 사람이 읽는 말로 바꾼다. 모르는 종류의 태그
  이름은 내보내지 않는다. 혼합 차트는 문서 순서대로 ` + ` 로 잇는다.
- 세로/가로 막대는 태그가 아니라 `c:barDir` 로 갈린다(스키마 기본값 col).
- 숨긴 축은 빼고, 분산형의 참조된 값 축 쌍은 위치와 교차 참조로 X/Y를 구분한다.
- `mc:AlternateContent` 는 차트 요소를 가진 첫 갈래(Choice 순서, 그다음 Fallback) 하나만 읽는다.
  두 갈래를 다 읽으면 같은 내용이 두 번 나온다.
"""
from functools import lru_cache
from itertools import islice
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
_DISPLAY = "{urn:dochan:chart-display}"
_MAX_ALTERNATE_DEPTH = 4

# 실제 차트의 축은 주·보조 범주/값 축과 3-D 계열 축을 합쳐도 다섯 개 남짓이다.
# 조작된 파트가 축 수십만 개로 한 줄 캡션을 수 MB 로 키우지 못하게 막는다.
MAX_CAPTION_AXES = 8
MAX_CHART_GROUPS = 1000
MAX_NUMBER_FORMAT_LENGTH = 255

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
    "sunburstChart": "sunburst",
    "boxWhiskerChart": "box and whisker",
    "treemapChart": "treemap",
    "waterfallChart": "waterfall",
    "histogramChart": "histogram",
    "paretoChart": "Pareto",
    "funnelChart": "funnel",
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


def xy_series_rows(series_items, xy: bool, implicit_x=None) -> Optional[List[List[str]]]:
    """분산형·거품형 계열의 X 값이 계열마다 다르면 (계열, X, Y) 긴 표의 행들. 아니면 None.

    series_items 는 리더가 모은 (계열 이름, {idx: X 또는 범주}, {idx: Y 또는 값}) 목록이다.
    X 를 공유하는 계열은 X 한 열과 계열별 Y 열로 묶는 편이 읽기 쉬우니 리더의 기존 표를 쓴다.
    X 가 다른데 idx 로 묶으면 첫 계열의 X 가 다른 계열의 Y 에 붙어 좌표가 틀어진다.

    implicit_x[i] 가 참이면 그 계열은 X 원천(c:xVal·c:cat)이 아예 없다. Office 는 이런 계열을
    1, 2, … 위치에 그리므로 X 를 그 번호로 채운다. 원천은 있는데 캐시가 없으면 X 를 비운다.
    """
    if not xy or len(series_items) < 2:
        return None
    raw_xs = [{index: getattr(value, 'raw', value) for index, value in xs.items()}
              for _, xs, _ in series_items]
    if all(xs == raw_xs[0] for xs in raw_xs[1:]):
        return None
    implicit_x = implicit_x or [False] * len(series_items)
    rows = [["Series", "X", "Y"]]
    for position, ((name, xs, ys), implicit) in enumerate(zip(series_items, implicit_x)):
        label = name or f"Series {position + 1}"
        for index in sorted(set(xs) | set(ys)):
            x = xs.get(index, str(index + 1) if implicit and not xs else "")
            rows.append([label, x, ys.get(index, "")])
    return rows


def chart_series(chart_root) -> list:
    """c:chart/c:plotArea/<차트 그룹>/c:ser — 확장 래퍼는 캡션과 같은 한 갈래만 읽는다."""
    chart = _chart(chart_root)
    plot_area = _child(chart, "plotArea") if chart is not None else None
    if plot_area is None:
        return []
    return [
        series
        for _, group in _chart_children(plot_area)
        for name, series in _chart_children(group)
        if name == "ser"
    ]


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
    title = _child(chart, "title")
    if title is None:
        return ""
    if title is not None and _child(title, "tx") is not None:
        return _title_text(title)
    # Preserve omitted-state behavior until its Office display is verified.
    # Only an explicit non-deleted automatic title enables this fallback.
    if _child(chart, "autoTitleDeleted") is None or _flag(chart, "autoTitleDeleted"):
        return ""
    series = chart_series(chart_root)
    if len(series) != 1:
        return ""
    tx = _child(series[0], "tx")
    if tx is None:
        return ""
    value = _child(tx, "v")
    if value is not None:
        return (value.text or "").strip()
    ref = _child(tx, "strRef")
    return " ".join(node.text or "" for node in ref.iterfind(
        "c:strCache/c:pt/c:v", namespaces=_NS)).strip() if ref is not None else ""


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
            # 펼쳤을 때 실제로 차트 요소가 나오는 갈래만 고른다(빈 래퍼·깊이 상한에 걸리는 갈래 제외).
            branch = _alternate_branch(
                child,
                lambda candidate: next(_chart_children(candidate, depth + 1), None) is not None,
            )
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
        direction = "bar" if _val(elem, "barDir") == "bar" else "column"
        return f"3-D {direction}" if name == "bar3DChart" else direction
    if name == "ofPieChart":
        return "bar of pie" if _val(elem, "ofPieType") == "bar" else "pie of pie"
    return _TYPE_LABELS.get(name, "")


def _axis_titles(plot_area) -> List[str]:
    titles = []
    roles = {}
    children = list(_chart_children(plot_area))
    axes = _axis_index(children)
    groups = 0
    for name, group in children:
        if name in ("scatterChart", "bubbleChart"):
            groups += 1
            if groups > MAX_CHART_GROUPS:
                break
            x_axis, y_axis = _group_axes(group, plot_area, axes)
            if x_axis is not None:
                roles[x_axis] = "X axis"
            if y_axis is not None:
                roles[y_axis] = "Y axis"
    for name, child in children:
        label = roles.get(child, _AXIS_LABELS.get(name))
        if not label or _flag(child, "delete"):
            continue
        text = _title_text(_child(child, "title"))
        if text:
            titles.append(f"{label}: {text}")
            if len(titles) >= MAX_CAPTION_AXES:
                break
    return titles


def _axis_index(children):
    axes = {}
    for name, node in children:
        if name in _AXIS_LABELS:
            identity = _val(node, "axId")
            if identity in axes or len(axes) >= MAX_CAPTION_AXES:
                return {}
            axes[identity] = node
    return axes


def _group_axes(group, plot_area, axis_index=None):
    """ECMA-376 21.2: axId selects axes; axPos gives their orientation.

    Cross references keep primary/secondary pairs separate. When a producer
    stores the same axPos twice, use its X/Y reference order only for a mutually
    crossing pair. Unreferenced or ambiguous axes retain their generic labels.
    """
    ids = list(islice((_val_id.get("val", "") for name, _val_id in _chart_children(group)
                      if name == "axId"), 4))
    xy = group.tag in (_C + "scatterChart", _C + "bubbleChart")
    if len(ids) not in ((2,) if xy else (2, 3)) or len(set(ids)) != len(ids):
        return None, None
    if axis_index is None:
        axis_index = _axis_index(_chart_children(plot_area))
    axes = {identity: axis_index[identity] for identity in ids if identity in axis_index}
    if len(axes) != len(ids):
        return None, None
    if not xy:
        categories = [axis for axis in axes.values() if axis.tag in (_C + "catAx", _C + "dateAx")]
        values = [axis for axis in axes.values() if axis.tag == _C + "valAx"]
        if len(categories) == len(values) == 1:
            return categories[0], values[0]
        return None, None
    first, second = (axes[i] for i in ids)
    if first.tag != _C + "valAx" or second.tag != _C + "valAx":
        return None, None
    if _val(first, "crossAx") != ids[1] or _val(second, "crossAx") != ids[0]:
        return None, None
    positions = (_val(first, "axPos"), _val(second, "axPos"))
    if positions[0] in ("l", "r") and positions[1] in ("b", "t"):
        return second, first
    return first, second


def is_xy_series(series):
    group = series.getparent()
    return (group is not None and group.tag in (_C + "scatterChart", _C + "bubbleChart")) or _child(series, "xVal") is not None


def mixed_series_rows(series_items, xy_flags, sizes=None, implicit_x=None):
    """범주 계열과 XY 계열이 공존하면 Category와 X를 서로 다른 열로 보존한다."""
    if not any(xy_flags) or all(xy_flags):
        return None
    sizes = sizes or [{} for _ in series_items]
    implicit_x = implicit_x or [False] * len(series_items)
    bubbles = any(sizes)
    rows = [["Series", "Category", "X", "Y"] + (["Bubble size"] if bubbles else [])]
    for position, ((name, xs, ys), xy, size, implicit) in enumerate(zip(series_items, xy_flags, sizes, implicit_x)):
        for index in sorted(set(xs) | set(ys) | set(size)):
            x = xs.get(index, str(index + 1) if implicit and not xs else "")
            rows.append([name or "Series %d" % (position + 1), "" if xy else x,
                         x if xy else "", ys.get(index, "")]
                        + ([size.get(index, "")] if bubbles else []))
    return rows


class _ChartDisplayValue(str):
    """표시 문자열과 표 병합에 필요한 원시 좌표를 함께 보존한다."""

    def __new__(cls, text, raw):
        result = super().__new__(cls, text)
        result.raw = raw
        return result

    def __getnewargs__(self):
        return str(self), self.raw


@lru_cache(maxsize=128)
def _number_format_reader(format_code, date_1904):
    from .xlsx import XLSXReader
    reader = XLSXReader()
    reader._date_1904 = date_1904
    reader._errors = None
    reader._format_metadata(format_code)
    return reader


def format_chart_number(value: str, format_code: str, date_1904=False) -> str:
    """지원하는 날짜·시각·경과 시간을 표시하며 나머지는 원시 숫자를 보존한다.

    시각 일련값이 하루 이상이면 정수 일수를 잃지 않도록 날짜를 붙인다.
    이는 시각 서식만 표시하는 Excel과 의도적으로 다른 출력이다.
    단순 경과 시간은 총 단위를 표시한다. 소수 초·단일 s 시각·음수
    날짜/시각/경과 시간과 미지원 경과 서식은 원시 값으로 남긴다.
    """
    if not format_code or format_code.lower() == "general" or len(format_code) > MAX_NUMBER_FORMAT_LENGTH:
        return value
    reader = _number_format_reader(format_code, date_1904)
    try:
        number = float(value)
    except ValueError:
        return value
    selected = reader._conditional_format_section(format_code, number)
    if selected == format_code:
        sections = reader._format_sections(format_code)
        position = 1 if number < 0 and len(sections) > 1 else 2 if number == 0 and len(sections) > 2 else 0
        selected = sections[position]
    format_code = selected
    kind = reader._format_metadata(format_code).kind
    if kind not in ("date", "time", "duration"):
        return value
    formatted = reader._format_cell_value(value, format_code)
    if kind == "time" and formatted != value:
        try:
            if abs(float(value)) >= 1:
                formatted = reader._format_cell_value(value, "yyyy-mm-dd " + format_code)
        except (ValueError, OverflowError):
            return value
    if len(formatted) > len(value) + 64 or len(formatted) > 128:
        return value
    return _ChartDisplayValue(formatted, value) if formatted != value else value


def chart_point_formatter(parent):
    """한 데이터 원천의 표시 정책을 한 번만 계산하여 점 수 × 축 수 순회를 피한다."""
    caches = [parent] if parent.tag in (_C + "numCache", _C + "numLit") else [
        node for node in parent.iter() if node.tag in (_C + "numCache", _C + "numLit")]
    formatters = {cache: _numeric_cache_formatter(cache) for cache in caches}

    def display(point, value):
        formatter = formatters.get(point.getparent())
        return formatter(point, value) if formatter is not None else value

    return display


def _numeric_cache_formatter(cache):
    cache_format = cache.findtext(_C + "formatCode", "")
    root = cache
    while root.getparent() is not None:
        root = root.getparent()
    explicit_epoch = _child(root, "date1904") is not None
    epoch = _flag(root, "date1904")

    def display(point, value):
        fmt = cache_format or point.get(_DISPLAY + "format", "")
        date_1904 = epoch if explicit_epoch else point.get(_DISPLAY + "date1904") == "1"
        return format_chart_number(value, fmt, date_1904)

    return display


def _val(elem, name: str) -> str:
    child = _child(elem, name)
    return (child.get("val") or "").strip() if child is not None else ""


def _flag(elem, name: str) -> bool:
    """CT_Boolean: 요소가 없으면 거짓, val 이 없으면 스키마 기본값인 참."""
    child = _child(elem, name)
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
    _collect_text(paragraph, parts, 0)
    text = []
    pending_break = False
    for part in parts:
        if part is _BREAK:
            pending_break = True
            continue
        if not part:
            continue
        # 줄바꿈은 앞뒤 글자가 모두 공백이 아닐 때만 공백 하나가 된다. 문단 끝의 줄바꿈은 버린다.
        if pending_break and text and not text[-1][-1].isspace() and not part[0].isspace():
            text.append(" ")
        pending_break = False
        text.append(part)
    return "".join(text)


_BREAK = object()


def _collect_text(container, parts: list, depth: int) -> None:
    for child in container:
        tag = child.tag
        if not isinstance(tag, str):
            continue
        if tag == _A + "br":
            parts.append(_BREAK)
        elif tag == _MC + "AlternateContent":
            if depth >= _MAX_ALTERNATE_DEPTH:
                continue
            branch = _alternate_branch(child, _has_text)
            if branch is not None:
                _collect_text(branch, parts, depth + 1)
        else:
            # a:r·a:fld 의 글자 (pPr·endParaRPr 에는 a:t 가 없다).
            parts.append("".join(node.text or "" for node in child.iterfind(".//a:t", namespaces=_NS)))


CX_NS = "http://schemas.microsoft.com/office/drawing/2014/chartex"
_CX = "{%s}" % CX_NS
MAX_REFERENCE_CELLS = 200000
MAX_REFERENCE_SERIES = 1000
MAX_REFERENCE_BYTES_TOTAL = 64 * 1024 * 1024


class _ChartValues(dict):
    """Resolver 값과 좌표별 표시 메타데이터. 기존 dict 호출 계약을 유지한다."""
    def __init__(self, values, formats, date_1904):
        super().__init__(values)
        self.formats = formats
        self.date_1904 = date_1904


def _reference_state(package):
    state = getattr(package, "_chart_reference_state", None)
    if state is None:
        state = {"remaining": MAX_REFERENCE_CELLS, "loaded": 0, "bytes": 0,
                 "resolvers": {}}
        package._chart_reference_state = state
    return state


def workbook_chart_resolver(package, errors, budget=None):
    """같은 통합문서의 유한 A1 범위를 캐시 값으로 읽는 지연 resolver.

    수식은 계산하지 않고 저장된 v를 쓴다. 외부 통합문서·이름·수식은 실행하지 않는다.
    XLSX 리더의 시트/공유문자열 코드를 재사용하며 조회한 시트만 희소 맵으로 보관한다.
    """
    import re
    from .xlsx import XLSXReader, _namespaces, _column_index

    reader = XLSXReader()
    # 선택적인 차트 참조의 잘못된 좌표가 본문 전체를 ERR로 만들지 않는다.
    reader._errors = []
    budget = _reference_state(package) if budget is None else budget
    initialized = False
    sheets = {}
    shared = []
    styles = []
    cells_by_sheet = {}
    formats_by_sheet = {}
    exhausted = False

    def resolve(formula):
        nonlocal initialized, shared, sheets, styles, exhausted
        if exhausted:
            return {}
        match = re.fullmatch(
            r"(?:'((?:[^']|'')+)'|([^'!\[\]]+))!\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})(?::\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6}))?",
            (formula or "").strip(),
        )
        if match is None:
            return {}
        name = (match.group(1) or match.group(2)).replace("''", "'")
        col1 = _column_index(match.group(3))
        row1 = int(match.group(4)) - 1
        col2 = _column_index(match.group(5) or match.group(3))
        row2 = int(match.group(6) or match.group(4)) - 1
        count = (col2 - col1 + 1) * (row2 - row1 + 1)
        if col2 < col1 or row2 < row1 or col2 >= 16384 or row2 >= 1048576:
            _chart_warning(errors, "invalid chart formula range")
            return {}
        if count > budget["remaining"]:
            _chart_warning(errors, "chart reference cell limit exceeded")
            return {}
        if not initialized:
            workbook = package.read_xml_part("xl/workbook.xml")
            sheets = dict(reader._read_sheets(workbook, reader._read_workbook_relationships(package)))
            shared = reader._read_shared_strings(package)
            styles = reader._read_styles(package)
            properties = workbook.find("s:workbookPr", namespaces=_namespaces(workbook))
            reader._date_1904 = properties is not None and properties.get("date1904", "0").lower() in ("1", "true")
            initialized = True
        path = sheets.get(name)
        if not path or not package.exists(path):
            return {}
        if name not in cells_by_sheet:
            if budget["loaded"] >= MAX_REFERENCE_CELLS:
                _chart_warning(errors, "chart source cell limit exceeded")
                exhausted = True
                return {}
            root = package.read_xml_part(path)
            cells = {}
            formats = {}
            for fallback_row, row in enumerate(root.iterfind("s:sheetData/s:row", namespaces=_namespaces(root))):
                row_index = reader._sheet_row_index(row, fallback_row)
                if row_index is None:
                    continue
                next_column = 0
                for cell in row.iterfind("s:c", namespaces=_namespaces(row)):
                    budget["loaded"] += 1
                    if budget["loaded"] > MAX_REFERENCE_CELLS:
                        _chart_warning(errors, "chart source cell limit exceeded")
                        exhausted = True
                        return {}
                    reference = cell.get("r", "")
                    coordinate = reader._validated_cell_coordinates(reference) if reference else (row_index, next_column)
                    if coordinate is None or coordinate[0] != row_index or coordinate[1] >= 16384:
                        _chart_warning(errors, "invalid chart source cell coordinate")
                        continue
                    next_column = coordinate[1] + 1
                    kind = cell.get("t", "")
                    value = cell.find("s:v", namespaces=_namespaces(cell))
                    text = value.text or "" if value is not None else ""
                    if kind == "s":
                        try:
                            text = shared[int(text)] if int(text) >= 0 else ""
                        except (ValueError, IndexError):
                            text = ""
                    elif kind == "inlineStr":
                        text = reader._text_runs(cell.find("s:is", namespaces=_namespaces(cell)))
                    cells[coordinate] = text
                    if kind in ("", "n"):
                        formats[coordinate] = reader._cell_format(cell, styles)
            if reader._errors:
                _chart_warning(errors, "invalid chart source cell coordinate")
                reader._errors.clear()
            cells_by_sheet[name] = cells
            formats_by_sheet[name] = formats
        budget["remaining"] -= count
        cells = cells_by_sheet[name]
        width = col2 - col1 + 1
        values = {
            (row - row1) * width + col - col1: cells[(row, col)]
            for row in range(row1, row2 + 1)
            for col in range(col1, col2 + 1)
            if cells.get((row, col), "") != ""
        }
        formats = {
            (row - row1) * width + col - col1: formats_by_sheet[name].get((row, col), "")
            for row in range(row1, row2 + 1)
            for col in range(col1, col2 + 1)
            if cells.get((row, col), "") != ""
        }
        return _ChartValues(values, formats, reader._date_1904)

    return resolve


def _chart_warning(errors, message):
    warning = "WARN: OOXML " + message
    if warning not in errors:
        errors.append(warning)


def hydrate_chart_references(chart_root, package, chart_path, errors, resolver=None):
    """캐시 없는 c:strRef/c:numRef를 c:f가 참조한 셀의 저장값으로 보강한다.

    기존 캐시는 그대로 두고 외부 TargetMode는 참조하지 않는다.
    DOCX/PPTX의 내장 통합문서는 안전한 OOXMLPackage로 열어 같은 resolver를 쓴다.
    """
    import io
    import posixpath
    import zipfile
    from lxml import etree
    from .package import OOXMLPackage

    references = []
    for ref in chart_root.iter():
        if ref.tag not in (_C + "strRef", _C + "numRef"):
            continue
        cache_name = "strCache" if ref.tag == _C + "strRef" else "numCache"
        cache = ref.find(_C + cache_name)
        if cache is not None:
            # A complete cache without formatCode still supplies usable raw
            # numbers. Optional formatting must not consume the shared budget
            # required by subsequent charts with no data cache at all.
            continue
        formula = ref.find(_C + "f")
        if formula is not None and formula.text:
            references.append((ref, cache_name, formula.text))
    if not references:
        return
    if len(references) > MAX_REFERENCE_SERIES * 4:
        _chart_warning(errors, "chart reference count limit exceeded")
        return

    def fill(resolve):
        for ref, cache_name, formula in references:
            values = resolve(formula)
            if not values:
                continue
            if len(values) > MAX_REFERENCE_CELLS:
                _chart_warning(errors, "chart reference cell limit exceeded")
                continue
            cache = ref.find(_C + cache_name)
            if cache is None:
                cache = etree.SubElement(ref, _C + cache_name)
                etree.SubElement(cache, _C + "ptCount", val=str(max(values) + 1))
                for index, value in sorted(values.items()):
                    point = etree.SubElement(cache, _C + "pt", idx=str(index))
                    etree.SubElement(point, _C + "v").text = str(value)
            if cache_name == "numCache" and isinstance(values, _ChartValues):
                for point in cache.iterfind(_C + "pt"):
                    raw = point.get("idx", "")
                    if not raw.isascii() or not raw.isdigit() or len(raw) > 10:
                        continue
                    fmt = values.formats.get(int(raw), "")
                    if fmt:
                        point.set(_DISPLAY + "format", fmt)
                    point.set(_DISPLAY + "date1904", "1" if values.date_1904 else "0")

    try:
        if resolver is not None:
            fill(resolver)
            return
        if package is None:
            return
        external = chart_root.find(_C + "externalData")
        if external is None:
            return
        rel_id = external.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        directory = posixpath.dirname(chart_path)
        rels_path = posixpath.join(directory, "_rels", posixpath.basename(chart_path) + ".rels")
        if not package.exists(rels_path):
            return
        rels = package.read_xml_part(rels_path)
        for rel in rels:
            if rel.get("Id") != rel_id or rel.get("TargetMode", "").lower() == "external":
                continue
            target = rel.get("Target", "")
            target = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(directory, target))
            if not target.endswith(".xlsx") or not package.exists(target):
                return
            state = _reference_state(package)
            if target not in state["resolvers"]:
                # 실패한 대상도 기억해 반복된 손상 파트 해제를 막는다.
                state["resolvers"][target] = None
                size = package.part_size(target)
                if state["bytes"] + size > MAX_REFERENCE_BYTES_TOTAL:
                    _chart_warning(errors, "chart workbook byte limit exceeded")
                    return
                state["bytes"] += size
                embedded = OOXMLPackage(io.BytesIO(package.read_part(target)))
                resolve = workbook_chart_resolver(embedded, errors, state)
                with embedded:
                    fill(resolve)
                state["resolvers"][target] = (embedded, resolve)
            elif state["resolvers"][target] is not None:
                embedded, resolve = state["resolvers"][target]
                with embedded:
                    fill(resolve)
            return
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        _chart_warning(errors, "chart workbook reference could not be read: " + str(exc)[:256])


def bubble_series_rows(series_items, sizes, implicit_x=None):
    """거품 계열을 값이 빠지지 않는 Series/X/Y/Bubble size 긴 표로 낸다."""
    if not any(sizes):
        return None
    rows = [["Series", "X", "Y", "Bubble size"]]
    implicit_x = implicit_x or [False] * len(series_items)
    for position, ((name, xs, ys), size, implicit) in enumerate(zip(series_items, sizes, implicit_x)):
        for index in sorted(set(xs) | set(ys) | set(size)):
            rows.append([
                name or "Series %s" % (position + 1),
                xs.get(index, str(index + 1) if implicit and not xs else ""),
                ys.get(index, ""), size.get(index, ""),
            ])
    return rows


def normalize_chart(chart_root, errors):
    """chartEx의 명시적 차원 캐시를 기존 c:chart 출력 계약으로 변환한다.

    상자 수염의 통계값이나 sunburst 배치를 계산하지 않고 원본 데이터를 낸다.
    계층 범주는 바깥쪽부터 안쪽까지 /로 이어 정보를 보존한다.
    """
    from copy import deepcopy
    from lxml import etree

    if chart_root.tag != _CX + "chartSpace":
        chart = _chart(chart_root)
        plot = _child(chart, "plotArea") if chart is not None else None
        if plot is not None:
            groups = 0
            for name, _ in _chart_children(plot):
                if name.endswith("Chart"):
                    groups += 1
                    if groups > MAX_CHART_GROUPS:
                        _chart_warning(errors, "chart group limit exceeded")
                        return etree.Element(_C + "chartSpace")
        return chart_root
    root = etree.Element(_C + "chartSpace")
    chart = etree.SubElement(root, _C + "chart")
    source = chart_root.find(_CX + "chart")
    if source is None:
        return root
    title = source.find(_CX + "title")
    if title is not None:
        title = deepcopy(title)
        for node in title.iter():
            if isinstance(node.tag, str) and node.tag.startswith(_CX):
                node.tag = _C + node.tag[len(_CX):]
        tx_data = title.find(_C + "tx/" + _C + "txData")
        if tx_data is not None:
            # chartEx 셀 연결 제목의 저장된 v와 f를 classic strRef로 옮긴다.
            tx_data.tag = _C + "strRef"
            value = tx_data.find(_C + "v")
            if value is not None:
                tx_data.remove(value)
                cache = etree.SubElement(tx_data, _C + "strCache")
                point = etree.SubElement(cache, _C + "pt", idx="0")
                point.append(value)
        chart.append(title)
    plot = etree.SubElement(chart, _C + "plotArea")
    data = {node.get("id"): node for node in chart_root.findall(_CX + "chartData/" + _CX + "data")}
    series = source.findall(".//" + _CX + "plotAreaRegion/" + _CX + "series")
    if len(series) > MAX_REFERENCE_SERIES:
        _chart_warning(errors, "chartEx series limit exceeded")
        return root
    used = 0
    for source_series in series:
        layout = source_series.get("layoutId", "")
        known_layouts = {"sunburst", "boxWhisker", "treemap", "waterfall", "clusteredColumn", "paretoLine", "funnel", "regionMap"}
        if layout not in known_layouts:
            _chart_warning(errors, "unknown chartEx layout")
            layout = "unknown"
        layout = {"clusteredColumn": "histogram", "paretoLine": "pareto"}.get(layout, layout)
        group = etree.SubElement(plot, _C + layout + "Chart")
        ser = etree.SubElement(group, _C + "ser")
        name = source_series.find(_CX + "tx/" + _CX + "txData/" + _CX + "v")
        if name is not None:
            etree.SubElement(etree.SubElement(ser, _C + "tx"), _C + "v").text = name.text
        data_id = source_series.find(_CX + "dataId")
        dimension_data = data.get(data_id.get("val")) if data_id is not None else None
        if dimension_data is None:
            continue
        for dim in dimension_data:
            kind = dim.get("type", "")
            destination = "cat" if kind == "cat" else "val" if kind in ("val", "size", "y") else "xVal" if kind == "x" else ""
            if not destination:
                continue
            levels = []
            for level in dim.findall(_CX + "lvl"):
                points = {}
                for point in level.findall(_CX + "pt"):
                    used += 1
                    if used > MAX_REFERENCE_CELLS:
                        _chart_warning(errors, "chartEx point limit exceeded")
                        return etree.Element(_C + "chartSpace")
                    raw = point.get("idx", "")
                    if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or int(raw) > 4294967295:
                        _chart_warning(errors, "invalid chartEx point index")
                        continue
                    points[int(raw)] = point.text or ""
                levels.append(points)
            parent = etree.SubElement(ser, _C + destination)
            numeric = dim.tag == _CX + "numDim"
            ref = etree.SubElement(parent, _C + ("numRef" if numeric else "strRef"))
            formula = dim.find(_CX + "f")
            if formula is not None:
                etree.SubElement(ref, _C + "f").text = formula.text
            if levels:
                cache = etree.SubElement(ref, _C + ("numCache" if numeric else "strCache"))
                if numeric:
                    # A numeric dimension's first level supplies the values
                    # below, so its format belongs to the same emitted cache.
                    level = dim.find(_CX + "lvl")
                    code = level.get("formatCode", "") if level is not None else ""
                    if code:
                        etree.SubElement(cache, _C + "formatCode").text = code
                indexes = set(index for level in levels for index in level)
                for index in sorted(indexes):
                    values = [level.get(index, "") for level in reversed(levels)]
                    value = " / ".join(value for value in values if value) if not numeric else values[-1]
                    point = etree.SubElement(cache, _C + "pt", idx=str(index))
                    etree.SubElement(point, _C + "v").text = value
    external = chart_root.find(_CX + "chartData/" + _CX + "externalData")
    if external is not None:
        external = deepcopy(external)
        external.tag = _C + "externalData"
        root.append(external)
    return root


def chart_drawing_references(container, depth=0):
    """그리기 앵커의 classic/chartEx 참조를 찾고 AlternateContent는 한 갈래만 고른다."""
    if depth > 64:
        return
    for child in container:
        if child.tag in (_C + "chart", _CX + "chart"):
            yield child
        elif child.tag == _MC + "AlternateContent":
            branch = _alternate_branch(child, lambda candidate: next(chart_drawing_references(candidate, depth + 1), None) is not None)
            if branch is not None:
                yield from chart_drawing_references(branch, depth + 1)
        else:
            yield from chart_drawing_references(child, depth + 1)
