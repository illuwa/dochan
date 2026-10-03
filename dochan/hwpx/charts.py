"""Bounded, offline extraction of HWPX OOXML chart caches.

parse_chart_xml returns an optional explicit title Paragraph followed by one
Table per series. The first table's TOP caption uses the common OOXML chart
type/axis annotation once; the series name is its value-column heading. Series follow c:order (stable XML-order fallback),
rows follow zero-based c:pt/@idx. By default number strings remain unchanged.

Only stored caches/literals are read. display_values enables shared temporal
formatting and explicit automatic titles. Formula evaluation, workbook/ZIP
access and chart rendering remain outside this API.
See docs/benchmarks/hwpx/chart-validation.md for the supported/verified scope.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

import lxml.etree as etree

from ..model.document import Paragraph, TextRun
from ..model.table import Cell, Table
from ..ooxml.charts import chart_caption, chart_title, chart_point_formatter

MAX_XML_BYTES = 4 * 1024 * 1024
MAX_SERIES = 128
MAX_POINTS = 10_000             # Per cache: count, actual pt nodes, index + 1.
MAX_TOTAL_POINTS = 50_000       # Includes title/name caches and duplicate points.
MAX_GRID_CELLS = 50_000         # Across all output tables, including headers.

_C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_CATEGORY_CHARTS = frozenset(
    _C + name for name in (
        "pieChart", "pie3DChart", "doughnutChart", "lineChart", "line3DChart",
        "barChart", "bar3DChart", "areaChart", "area3DChart", "radarChart",
        "ofPieChart", "stockChart", "surfaceChart", "surface3DChart",
    )
)
_SCATTER = _C + "scatterChart"
_BUBBLE = _C + "bubbleChart"
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_UNSIGNED = re.compile(r"[0-9]+\Z")


class _LimitExceeded(Exception):
    """Internal signal: discard all output rather than silently truncate it."""


@dataclass
class _Budget:
    points: int = 0
    cells: int = 0
    display_values: bool = False

    def add_points(self, count: int) -> None:
        if count > MAX_POINTS or self.points + count > MAX_TOTAL_POINTS:
            raise _LimitExceeded("cache point budget exceeded")
        self.points += count

    def add_cells(self, count: int) -> None:
        if self.cells + count > MAX_GRID_CELLS:
            raise _LimitExceeded("output grid cell budget exceeded")
        self.cells += count


@dataclass
class _Cache:
    points: dict
    extent: int


def _warn(warnings: list[str], code: str, context: str) -> None:
    # Contexts use bounded series ordinals, never raw XML/formulas/values. The
    # same problem at thousands of points produces one warning per cache.
    message = "[chart:%s] %s" % (code, context)
    if message not in warnings:
        warnings.append(message)


def _unsigned(value: Optional[str], limit: int) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not _UNSIGNED.fullmatch(value):
        return None
    digits = value.lstrip("0") or "0"
    bound = str(limit)
    # Check lexically before int(), range() or allocating any sparse grid.
    if len(digits) > len(bound) or (len(digits) == len(bound) and digits > bound):
        raise _LimitExceeded("declared count/index exceeds its limit")
    return int(digits)


def _read_cache(node, numeric: bool, context: str, budget: _Budget,
                warnings: list[str]) -> _Cache:
    count_node = node.find(_C + "ptCount")
    declared = _unsigned(count_node.get("val") if count_node is not None else None, MAX_POINTS)
    if declared is None:
        _warn(warnings, "invalid_count", context + ": absent/invalid ptCount; using observed indices")

    # Count even invalid or duplicate pt nodes against both point budgets.
    point_nodes = node.findall(_C + "pt")
    budget.add_points(len(point_nodes))
    if declared is not None and declared != len(point_nodes):
        _warn(warnings, "count_mismatch", context + ": ptCount differs from point node count")
    points = {}
    format_point = chart_point_formatter(node) if budget.display_values and numeric else None
    for point in point_nodes:
        index = _unsigned(point.get("idx"), MAX_POINTS - 1)
        if index is None:
            _warn(warnings, "invalid_index", context + ": point with absent/invalid idx ignored")
            continue
        if index in points:
            _warn(warnings, "duplicate_index", context + ": duplicate idx; first value retained")
            continue
        value_nodes = point.findall(_C + "v")
        if len(value_nodes) != 1 or len(value_nodes[0]):
            _warn(warnings, "invalid_value", context + ": missing/structured/ambiguous v left blank")
            value = ""
        else:
            value = value_nodes[0].text or ""
        if numeric and value:
            try:
                valid = bool(_NUMBER.fullmatch(value.strip())) and Decimal(value.strip()).is_finite()
            except (InvalidOperation, ValueError):
                valid = False
            if not valid:
                _warn(warnings, "invalid_number", context + ": non-decimal value left blank")
                value = ""
        points[index] = format_point(point, value) if format_point is not None and value else value

    observed = max(points, default=-1) + 1
    if declared is not None and observed > declared:
        _warn(warnings, "count_mismatch", context + ": point index extends past ptCount")
    extent = max(declared or 0, observed)
    if len(points) < extent:
        _warn(warnings, "sparse_cache", context + ": absent indices remain blank")
    return _Cache(points, extent)


def _source(parent, context: str, budget: _Budget, warnings: list[str],
            numeric_only: bool = False) -> Optional[_Cache]:
    if parent is None:
        _warn(warnings, "missing_cache", context + ": no cached data")
        return None
    if parent.find(_C + "multiLvlStrRef") is not None:
        _warn(warnings, "unsupported_cache", context + ": multi-level categories are unsupported")
        return None
    sources = [child for child in parent if child.tag in {
        _C + "strRef", _C + "numRef", _C + "strLit", _C + "numLit",
    }]
    if len(sources) != 1:
        code = "ambiguous_cache" if sources else "missing_cache"
        _warn(warnings, code, context + ": expected one cached/literal source")
        return None
    source = sources[0]
    numeric = source.tag in {_C + "numRef", _C + "numLit"}
    if numeric_only and not numeric:
        _warn(warnings, "unsupported_cache", context + ": numeric cache required")
        return None
    if source.tag in {_C + "strRef", _C + "numRef"}:
        caches = source.findall(_C + ("numCache" if numeric else "strCache"))
        if len(caches) != 1:
            code = "ambiguous_cache" if caches else "missing_cache"
            _warn(warnings, code, context + ": reference has no unique cache; formula ignored")
            return None
        source = caches[0]
    return _read_cache(source, numeric, context, budget, warnings)


def _text(tx, context: str, budget: _Budget, warnings: list[str]) -> str:
    if tx is None:
        return ""
    rich = tx.find(_C + "rich")
    if rich is not None:
        # Only actual DrawingML text/break nodes under c:tx/c:rich, not txPr,
        # axis titles, number formats, formulas or other chart text.
        return "\n".join(
            ''.join((node.text or "") if node.tag == _A + "t" else "\n"
                    for node in paragraph.iter() if node.tag in {_A + "t", _A + "br"})
            for paragraph in rich.findall(_A + "p")
        )
    value = tx.find(_C + "v")
    if value is not None:
        return value.text or ""
    cache = _source(tx, context, budget, warnings)
    if cache is None or not cache.points:
        return ""
    if cache.extent != 1 or 0 not in cache.points:
        _warn(warnings, "text_cache", context + ": expected one text value; using lowest idx")
    return cache.points[min(cache.points)]


def _paragraph(text: str) -> Paragraph:
    return Paragraph(runs=[TextRun(text=text)])


def _series_table(series, position: int, scatter: bool, budget: _Budget,
                  warnings: list[str], bubble: bool = False,
                  shared_categories=None) -> Optional[Table]:
    context = "series %d" % (position + 1)
    name = _text(series.find(_C + "tx"), context + " name", budget, warnings)
    if not name:
        name = "계열 %d" % (position + 1)
        _warn(warnings, "missing_name", context + ": generated a series label")
    first, second = ("xVal", "yVal") if scatter else ("cat", "val")
    right = _source(series.find(_C + second), context + " " + second,
                    budget, warnings, numeric_only=True)
    if right is None:
        return None
    left_node = series.find(_C + first)
    if left_node is None and not scatter and shared_categories is not None:
        # 한컴오피스는 범주 없는 계열에 같은 그림 영역의 범주 축을 쓴다(화면 실측).
        _warn(warnings, "shared_categories", context + ": categories taken from another series")
        left_node = shared_categories
    if left_node is None:
        # 범주·X 가 하나도 없으면 한컴오피스 축처럼 1부터 번호를 붙인다(값은 지어내지 않는다).
        _warn(warnings, "implicit_categories", context + ": numbered points from 1")
        budget.add_points(right.extent)
        left = _Cache({index: str(index + 1) for index in range(right.extent)}, right.extent)
    else:
        left = _source(left_node, context + " " + first, budget, warnings, numeric_only=scatter)
    if left is None:
        return None
    caches = [left, right]
    headers = ["X", name] if scatter else ["범주", name]
    # 거품 크기는 선택 요소다. 있으면 같은 idx 의 셋째 열로 낸다.
    if bubble and series.find(_C + "bubbleSize") is not None:
        size = _source(series.find(_C + "bubbleSize"), context + " bubbleSize",
                       budget, warnings, numeric_only=True)
        if size is not None:
            caches.append(size)
            headers.append("크기")
    if len({cache.extent for cache in caches}) > 1:
        _warn(warnings, "length_mismatch", context + ": axis/cache lengths differ; missing cells stay blank")
    extent = max(cache.extent for cache in caches)
    if not extent:
        _warn(warnings, "empty_series", context + ": caches contain no points")
        return None
    budget.add_cells((extent + 1) * len(caches))
    rows = [[Cell(paragraphs=[_paragraph(text)], row=0, col=column)
             for column, text in enumerate(headers)]]
    for index in range(extent):
        rows.append([
            Cell(paragraphs=[_paragraph(cache.points.get(index, ""))], row=index + 1, col=column)
            for column, cache in enumerate(caches)
        ])
    return Table(rows=rows)


def _extract(root, budget: _Budget, warnings: list[str]) -> list[Union[Paragraph, Table]]:
    if root.tag != _C + "chartSpace":
        _warn(warnings, "invalid_root", "expected OOXML chartSpace QName")
        return []
    charts = root.findall(_C + "chart")
    if len(charts) != 1:
        _warn(warnings, "invalid_structure", "expected one chart")
        return []
    chart = charts[0]
    # Still validate/count stored title cache nodes before using the shared
    # display contract (space-separated title lines and heading level 3).
    stored_title = _text(chart.find(_C + "title/" + _C + "tx"), "title", budget, warnings)
    rich = chart.find(_C + "title/" + _C + "tx/" + _C + "rich")
    # Cache selection has already rejected duplicate/invalid indices. Only rich
    # text needs the shared line-break presentation; never re-read raw caches.
    title = chart_title(root) if rich is not None and stored_title.strip() else stored_title
    elements: list[Union[Paragraph, Table]] = [_paragraph(title)] if title else []
    if elements:
        elements[0].heading_level = 3
    if root.find(_C + "externalData") is not None:
        _warn(warnings, "external_data", "external workbook ignored; using stored caches only")
    plots = chart.findall(_C + "plotArea")
    if len(plots) != 1:
        _warn(warnings, "missing_plot", "expected one plotArea")
        return elements
    groups = [child for child in plots[0] if isinstance(child.tag, str)
              and child.tag.startswith(_C) and child.tag.endswith("Chart")]
    if sum(len(group.findall(_C + "ser")) for group in groups) > MAX_SERIES:
        raise _LimitExceeded("series budget exceeded")
    if len(groups) > 1:
        _warn(warnings, "mixed_chart", "multiple chart groups are unsupported")
        return elements
    if not groups or groups[0].tag not in _CATEGORY_CHARTS | {_SCATTER, _BUBBLE}:
        _warn(warnings, "unsupported_type", "unsupported or absent chart type")
        return elements
    group = groups[0]
    ordered, seen = [], set()
    for position, series in enumerate(group.findall(_C + "ser")):
        order_node = series.find(_C + "order")
        try:
            order = _unsigned(order_node.get("val") if order_node is not None else None, 2**32 - 1)
        except _LimitExceeded:
            order = None
        if order is None:
            _warn(warnings, "invalid_order", "series %d: using XML position for order" % (position + 1))
            order = position
        elif order in seen:
            _warn(warnings, "duplicate_order", "equal series orders retain XML order")
        else:
            seen.add(order)
        ordered.append((order, position, series))
    if not ordered:
        _warn(warnings, "empty_chart", "chart has no series")
    caption = chart_caption(root)
    ordered.sort(key=lambda item: item[:2])
    shared_categories = next((series.find(_C + "cat") for _, _, series in ordered
                              if series.find(_C + "cat") is not None), None)
    for display_position, (_, _, series) in enumerate(ordered):
        table = _series_table(series, display_position, group.tag in (_SCATTER, _BUBBLE), budget,
                              warnings, bubble=group.tag == _BUBBLE,
                              shared_categories=shared_categories)
        if table is not None:
            if caption:
                table.caption = [_paragraph(caption)]
                caption = ""
            table.caption_side = "TOP"
            elements.append(table)
    # Reuse the already validated series name; do not reread rejected title or
    # duplicate cache nodes through the permissive OOXML title helper.
    deleted = chart.find(_C + "autoTitleDeleted")
    auto_deleted = deleted is not None and deleted.get("val", "1").lower() in ("1", "true")
    if (budget.display_values and chart.find(_C + "title") is not None
            and chart.find(_C + "title/" + _C + "tx") is None and deleted is not None and not auto_deleted and len(ordered) == 1
            and len(elements) == 1 and isinstance(elements[0], Table)
            and not any('[chart:missing_name]' in warning for warning in warnings)):
        heading = _paragraph(elements[0].rows[0][1].text)
        heading.heading_level = 3
        elements.insert(0, heading)
    return elements


def parse_chart_xml(data: bytes, display_values: bool = False) -> tuple[list[Union[Paragraph, Table]], list[str]]:
    """Return title/series tables and separate diagnostics without any I/O.

    Malformed/unsafe XML and budget overruns return no elements. Missing caches
    skip the affected series; unsupported/mixed types may retain the explicit
    title. Callers own bounded ZIP part reads and placement in the document.
    display_values opts into formatted numbers and automatic titles; the default
    retains the raw-cache API. The HWPX document reader uses display values.
    Warnings start with '[chart:<code>]' and never include raw source text.
    """
    warnings: list[str] = []
    if not isinstance(data, bytes):
        _warn(warnings, "invalid_input", "expected bytes")
        return [], warnings
    if len(data) > MAX_XML_BYTES:
        _warn(warnings, "limit", "XML byte budget exceeded")
        return [], warnings
    parser = etree.XMLParser(resolve_entities=False, no_network=True,
                             load_dtd=False, huge_tree=False, recover=False)
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError):
        _warn(warnings, "invalid_xml", "malformed or excessively deep XML")
        return [], warnings
    if root.getroottree().docinfo.doctype:
        _warn(warnings, "doctype", "DTD/entity declarations are unsupported")
        return [], warnings
    try:
        elements = _extract(root, _Budget(display_values=display_values), warnings)
    except _LimitExceeded as error:
        _warn(warnings, "limit", str(error))
        return [], warnings
    return elements, warnings
