"""Cached chart data: synthetic edge cases and independent public XML gold."""
import hashlib
import importlib
import socket
# Independent gold uses only SHA-256-pinned XML, never arbitrary document input.
import xml.etree.ElementTree as ET  # nosemgrep: use-defused-xml
import zipfile
from pathlib import Path
# Output escaping only; this function does not parse XML.
from xml.sax.saxutils import escape  # nosemgrep: use-defused-xml

import pytest

from dochan.model.document import Paragraph, TextRun
from dochan.model.table import Cell, Table


C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"c": C, "a": A}
ROOT = Path(__file__).resolve().parents[1]


def _module():
    # Import inside tests so the initial TDD run records failing tests, not a
    # collection failure, when the new implementation module does not exist.
    return importlib.import_module("dochan.hwpx.charts")


def _parse(data):
    return _module().parse_chart_xml(data)


def _chart(series, kind="lineChart", title="", extra=""):
    return (
        '<c:chartSpace xmlns:c="%s" xmlns:a="%s"><c:chart>%s'
        '<c:plotArea><c:%s>%s</c:%s></c:plotArea></c:chart>%s'
        '</c:chartSpace>' % (C, A, title, kind, series, kind, extra)
    ).encode("utf-8")


def _cache(points, numeric=False, count=None, literal=False):
    kind = "num" if numeric else "str"
    count = len(points) if count is None else count
    body = '<c:ptCount val="%s"/>' % count
    body += ''.join(
        '<c:pt idx="%s"><c:v>%s</c:v></c:pt>' % (idx, escape(value))
        for idx, value in points
    )
    if literal:
        return '<c:%sLit>%s</c:%sLit>' % (kind, body, kind)
    return (
        '<c:%sRef><c:f>Sheet1!A1:A4</c:f><c:%sCache>%s'
        '</c:%sCache></c:%sRef>' % (kind, kind, body, kind, kind)
    )


def _series(name="판매", order=0, categories=None, values=None, scatter=False,
            sources=None):
    if categories is None:
        categories = [(0, "첫째"), (1, "둘째")]
    if values is None:
        values = [(0, "0"), (1, "2.00")]
    if sources is None:
        first, second = ("xVal", "yVal") if scatter else ("cat", "val")
        sources = '<c:%s>%s</c:%s><c:%s>%s</c:%s>' % (
            first, _cache(categories, numeric=scatter), first,
            second, _cache(values, numeric=True), second,
        )
    order_xml = '' if order is None else '<c:order val="%s"/>' % order
    return (
        '<c:ser><c:idx val="7"/>%s<c:tx><c:v>%s</c:v></c:tx>%s</c:ser>'
        % (order_xml, escape(name), sources)
    )


def _tables(elements):
    return [element for element in elements if isinstance(element, Table)]


def _rows(table):
    return [[cell.text for cell in row] for row in table.rows]


def _warned(warnings, code):
    return any('[chart:%s]' % code in warning for warning in warnings)


def test_cached_series_order_points_zero_and_lexical_values():
    later = _series("나중", 9, categories=[(1, "B"), (0, "A")],
                    values=[(1, "-0.00"), (0, "0")])
    earlier = _series("먼저", 2, values=[(1, "1e3"), (0, "2.00")])
    elements, warnings = _parse(_chart(later + earlier))
    assert warnings == []
    tables = _tables(elements)
    assert [table.caption_text for table in tables] == ["먼저", "나중"]
    assert _rows(tables[0]) == [["범주", "값"], ["첫째", "2.00"], ["둘째", "1e3"]]
    assert _rows(tables[1]) == [["범주", "값"], ["A", "0"], ["B", "-0.00"]]
    for table in tables:
        assert table.caption_side == "TOP"
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row):
                assert isinstance(cell, Cell)
                assert (cell.row, cell.col) == (row_index, col_index)
                assert isinstance(cell.paragraphs[0], Paragraph)
                assert isinstance(cell.paragraphs[0].runs[0], TextRun)


def test_rich_title_preserves_text_order_breaks_and_ignores_style_text():
    title = (
        '<c:title><c:tx><c:rich><a:p><a:r><a:t>매출</a:t></a:r>'
        '<a:r><a:t> 2026</a:t></a:r><a:br/><a:fld><a:t>상반기</a:t>'
        '</a:fld></a:p><a:p><a:r><a:t>합계</a:t></a:r></a:p>'
        '</c:rich></c:tx><c:txPr><a:p><a:r><a:t>서식 아님</a:t>'
        '</a:r></a:p></c:txPr></c:title>'
    )
    elements, warnings = _parse(_chart(_series(), title=title))
    assert warnings == []
    assert isinstance(elements[0], Paragraph)
    assert elements[0].text == "매출 2026\n상반기\n합계"
    assert len(elements) == 2


def test_cached_title_and_series_name_and_absent_explicit_title():
    title = '<c:title><c:tx>%s</c:tx></c:title>' % _cache([(0, "제목")])
    series = _series().replace('<c:v>판매</c:v>', _cache([(0, "이름")]))
    elements, warnings = _parse(_chart(series, title=title))
    assert warnings == []
    assert elements[0].text == "제목"
    assert elements[1].caption_text == "이름"
    no_title = '<c:title><c:txPr><a:p><a:r><a:t>서식</a:t></a:r></a:p></c:txPr></c:title>'
    elements, warnings = _parse(_chart(series, title=no_title))
    assert len(elements) == 1 and isinstance(elements[0], Table)
    assert warnings == []


def test_sparse_empty_and_unequal_lengths_do_not_shift_or_fill_zero():
    sources = '<c:cat>%s</c:cat><c:val>%s</c:val>' % (
        _cache([(0, "A"), (1, "B"), (2, "C"), (3, "D")]),
        _cache([(2, "0"), (0, "")], numeric=True, count=3),
    )
    elements, warnings = _parse(_chart(_series(sources=sources)))
    assert _rows(elements[0]) == [["범주", "값"], ["A", ""], ["B", ""], ["C", "0"], ["D", ""]]
    assert _warned(warnings, "sparse_cache")
    assert _warned(warnings, "length_mismatch")


def test_duplicate_invalid_indices_and_invalid_numbers_are_diagnosed():
    sources = '<c:cat>%s</c:cat><c:val>%s</c:val>' % (
        _cache([(0, "A"), (1, "B")]),
        _cache([(0, "0"), (0, "99"), (1, "not-number"), (-1, "4"), ("bad", "5")],
               numeric=True, count=2),
    )
    elements, warnings = _parse(_chart(_series(sources=sources)))
    assert _rows(elements[0]) == [["범주", "값"], ["A", "0"], ["B", ""]]
    for code in ("duplicate_index", "invalid_index", "invalid_number", "count_mismatch"):
        assert _warned(warnings, code)


@pytest.mark.parametrize("value", ["NaN", "INF", "-Infinity", "1,200", "1_000", "0x10"])
def test_non_decimal_number_is_blank_with_warning(value):
    elements, warnings = _parse(_chart(_series(values=[(0, value), (1, "0")])))
    assert _rows(elements[0])[1:] == [["첫째", ""], ["둘째", "0"]]
    assert _warned(warnings, "invalid_number")


def test_scatter_pairs_each_series_by_idx_without_sorting_x_or_joining_series():
    first = _series("궤적 A", categories=[(1, "0"), (0, "10.00")],
                    values=[(0, "-2"), (1, "0")], scatter=True)
    second = _series("궤적 B", order=1, categories=[(0, "100")],
                     values=[(0, "1e-2")], scatter=True)
    elements, warnings = _parse(_chart(first + second, kind="scatterChart"))
    assert warnings == []
    assert _rows(elements[0]) == [["X", "Y"], ["10.00", "-2"], ["0", "0"]]
    assert _rows(elements[1]) == [["X", "Y"], ["100", "1e-2"]]
    assert [table.caption_text for table in elements] == ["궤적 A", "궤적 B"]


def test_literal_and_numeric_category_caches_keep_date_serials_unformatted():
    sources = '<c:cat>%s</c:cat><c:val>%s</c:val>' % (
        _cache([(0, "45000"), (1, "45001")], numeric=True, literal=True).replace(
            '<c:numLit>', '<c:numLit><c:formatCode>yyyy-mm-dd</c:formatCode>'),
        _cache([(0, "0"), (1, "1.50")], numeric=True, literal=True),
    )
    elements, warnings = _parse(_chart(_series(sources=sources), kind="barChart"))
    assert warnings == []
    assert _rows(elements[0])[1:] == [["45000", "0"], ["45001", "1.50"]]
    sources = '<c:cat>%s</c:cat><c:val>%s</c:val>' % (
        _cache([(0, "문자")], literal=True),
        _cache([(0, "3")], numeric=True, literal=True),
    )
    elements, warnings = _parse(_chart(_series(sources=sources)))
    assert warnings == []
    assert _rows(elements[0])[1:] == [["문자", "3"]]


@pytest.mark.parametrize("kind", [
    "pieChart", "pie3DChart", "doughnutChart", "lineChart", "line3DChart",
    "barChart", "bar3DChart", "areaChart", "area3DChart", "radarChart",
])
def test_category_value_families_extract_only_their_data(kind):
    elements, warnings = _parse(_chart(_series(), kind=kind))
    assert warnings == []
    assert _rows(elements[0]) == [["범주", "값"], ["첫째", "0"], ["둘째", "2.00"]]


def test_scatter_sparse_indices_and_unequal_lengths_remain_paired():
    sources = '<c:xVal>%s</c:xVal><c:yVal>%s</c:yVal>' % (
        _cache([(0, "5"), (2, "0")], numeric=True, count=3),
        _cache([(0, "0")], numeric=True),
    )
    elements, warnings = _parse(_chart(_series(sources=sources), kind="scatterChart"))
    assert _rows(elements[0]) == [["X", "Y"], ["5", "0"], ["", ""], ["0", ""]]
    assert _warned(warnings, "sparse_cache") and _warned(warnings, "length_mismatch")


def test_empty_caches_and_ambiguous_sources_are_not_reported_as_valid_series():
    sources = '<c:cat>%s</c:cat><c:val>%s</c:val>' % (
        _cache([]), _cache([], numeric=True),
    )
    elements, warnings = _parse(_chart(_series(sources=sources)))
    assert elements == [] and _warned(warnings, "empty_series")
    sources = '<c:cat>%s%s</c:cat><c:val>%s</c:val>' % (
        _cache([(0, "A")]), _cache([(0, "B")], literal=True),
        _cache([(0, "0")], numeric=True),
    )
    elements, warnings = _parse(_chart(_series(sources=sources)))
    assert elements == [] and _warned(warnings, "ambiguous_cache")


@pytest.mark.parametrize("bad_source,code", [
    ('<c:numRef><c:f>https://example.invalid/book.xlsx!A1</c:f></c:numRef>', "missing_cache"),
    ('<c:multiLvlStrRef><c:multiLvlStrCache/></c:multiLvlStrRef>', "unsupported_cache"),
])
def test_missing_or_unsupported_cache_skips_series_without_inventing_values(bad_source, code):
    role = 'cat' if code == 'unsupported_cache' else 'val'
    other = '<c:val>%s</c:val>' % _cache([(0, "1")], numeric=True) if role == 'cat' else (
        '<c:cat>%s</c:cat>' % _cache([(0, "A")])
    )
    elements, warnings = _parse(_chart(_series(sources='<c:%s>%s</c:%s>%s' % (role, bad_source, role, other))))
    assert elements == []
    assert _warned(warnings, code)


def test_missing_cache_does_not_drop_other_valid_series_or_title():
    title = '<c:title><c:tx><c:rich><a:p><a:r><a:t>남김</a:t></a:r></a:p></c:rich></c:tx></c:title>'
    elements, warnings = _parse(_chart(_series(sources="") + _series("정상", 1), title=title))
    assert elements[0].text == "남김"
    assert len(elements) == 2 and elements[1].caption_text == "정상"
    assert _warned(warnings, "missing_cache")


def test_fallback_series_name_and_tied_or_missing_order_are_explicit():
    series = _series("", None).replace('<c:tx><c:v></c:v></c:tx>', '')
    elements, warnings = _parse(_chart(series + _series("B", 0) + _series("C", 0)))
    assert [table.caption_text for table in elements] == ["계열 1", "B", "C"]
    assert _warned(warnings, "missing_name")
    assert _warned(warnings, "invalid_order")
    assert _warned(warnings, "duplicate_order")


def test_external_workbook_is_not_opened_and_only_cached_values_are_used(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("chart parsing attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    xml = _chart(_series(), extra='<c:externalData xmlns:r="urn:r" r:id="remote"/>')
    xml = xml.replace(b'Sheet1!A1:A4', b'https://example.invalid/book.xlsx!A1:A4')
    elements, warnings = _parse(xml)
    assert _rows(elements[0])[1:] == [["첫째", "0"], ["둘째", "2.00"]]
    assert _warned(warnings, "external_data")
    assert calls == []


@pytest.mark.parametrize("entity", [
    '<!ENTITY leak SYSTEM "file:///etc/passwd">',
    '<!ENTITY leak SYSTEM "https://example.invalid/leak">',
    '<!ENTITY leak "expanded internal text">',
])
def test_doctype_and_entities_are_rejected_without_resolving(entity, monkeypatch):
    from lxml import etree

    module = _module()
    original_parser = etree.XMLParser
    configurations, resolutions = [], []

    class WatchResolver(etree.Resolver):
        def resolve(self, url, public_id, context):
            resolutions.append(url)
            raise AssertionError("entity resolver must not run")

    def watched_parser(*args, **kwargs):
        configurations.append(kwargs)
        parser = original_parser(*args, **kwargs)
        parser.resolvers.add(WatchResolver())
        return parser

    monkeypatch.setattr(module.etree, "XMLParser", watched_parser)
    xml = ('<!DOCTYPE c:chartSpace [%s]>' % entity).encode() + _chart(_series())
    xml = xml.replace('판매'.encode(), b'&leak;')
    elements, warnings = module.parse_chart_xml(xml)
    assert elements == [] and _warned(warnings, "doctype")
    assert configurations[0]['resolve_entities'] is False
    assert configurations[0]['no_network'] is True
    assert configurations[0]['load_dtd'] is False
    assert resolutions == []


def test_utf16_external_dtd_and_excessive_depth_are_rejected():
    dtd = '<!DOCTYPE c:chartSpace SYSTEM "https://example.invalid/chart.dtd">'
    xml = '<?xml version="1.0" encoding="UTF-16"?>' + dtd + _chart(_series()).decode()
    elements, warnings = _parse(xml.encode('utf-16'))
    assert elements == [] and _warned(warnings, "doctype")
    elements, warnings = _parse(b'<nested>' * 300 + b'</nested>' * 300)
    assert elements == [] and _warned(warnings, "invalid_xml")


@pytest.mark.parametrize("data,code", [
    (b'<broken', 'invalid_xml'),
    (b'', 'invalid_xml'),
    (b'<chartSpace xmlns="urn:impostor"><chart/></chartSpace>', 'invalid_root'),
    (('<c:chartSpace xmlns:c="%s"><c:chart/></c:chartSpace>' % C).encode(), 'missing_plot'),
])
def test_invalid_documents_return_diagnostics(data, code):
    elements, warnings = _parse(data)
    assert elements == [] and _warned(warnings, code)


def test_namespace_prefix_is_arbitrary_but_uri_is_not():
    xml = _chart(_series()).replace(b'c:', b'q:').replace(b'xmlns:c=', b'xmlns:q=')
    elements, warnings = _parse(xml)
    assert warnings == [] and _rows(elements[0])[1] == ["첫째", "0"]
    spoof = xml.replace(C.encode(), b'urn:impostor')
    assert _parse(spoof)[0] == []


def test_unsupported_bubble_and_mixed_charts_have_no_misleading_tables():
    elements, warnings = _parse(_chart(_series(), kind="bubbleChart"))
    assert elements == [] and _warned(warnings, "unsupported_type")
    mixed = _chart(_series()).replace(b'</c:plotArea>', b'<c:pieChart/>' + b'</c:plotArea>')
    elements, warnings = _parse(mixed)
    assert elements == [] and _warned(warnings, "mixed_chart")


@pytest.mark.parametrize("constant,limit,data", [
    ("MAX_XML_BYTES", 20, _chart(_series())),
    ("MAX_SERIES", 1, _chart(_series() + _series("B", 1))),
    ("MAX_POINTS", 1, _chart(_series())),
    ("MAX_TOTAL_POINTS", 7, _chart(_series() + _series("B", 1))),
    ("MAX_GRID_CELLS", 11, _chart(_series() + _series("B", 1))),
])
def test_resource_limits_fail_atomically(constant, limit, data, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, constant, limit)
    elements, warnings = module.parse_chart_xml(data)
    assert elements == [] and _warned(warnings, "limit")


@pytest.mark.parametrize("attribute", ['idx="999999999999999999999999"', 'count'])
def test_huge_declared_indices_or_counts_never_allocate_a_grid(attribute):
    xml = _chart(_series())
    if attribute == 'count':
        xml = xml.replace(b'ptCount val="2"', b'ptCount val="999999999999999999999999"')
    else:
        xml = xml.replace(b'pt idx="0"', ('pt ' + attribute).encode())
    elements, warnings = _parse(xml)
    assert elements == [] and _warned(warnings, "limit")


def test_grid_budget_is_checked_before_cell_construction(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "MAX_GRID_CELLS", 3)

    def forbidden_cell(*args, **kwargs):
        pytest.fail("a Cell was constructed before checking the grid budget")

    monkeypatch.setattr(module, "Cell", forbidden_cell)
    elements, warnings = module.parse_chart_xml(_chart(_series()))
    assert elements == [] and _warned(warnings, "limit")


def test_exact_budget_boundaries_are_accepted_and_budgets_reset_per_call(monkeypatch):
    module = _module()
    xml = _chart(_series())
    for constant, limit in (("MAX_XML_BYTES", len(xml)), ("MAX_SERIES", 1),
                            ("MAX_POINTS", 2), ("MAX_TOTAL_POINTS", 4), ("MAX_GRID_CELLS", 6)):
        monkeypatch.setattr(module, constant, limit)
    for _ in range(2):
        elements, warnings = module.parse_chart_xml(xml)
        assert warnings == [] and len(elements) == 1
        assert _rows(elements[0])[1:] == [["첫째", "0"], ["둘째", "2.00"]]


def test_duplicate_points_count_against_budget_even_with_small_declared_count(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "MAX_POINTS", 2)
    sources = '<c:cat>%s</c:cat><c:val>%s</c:val>' % (
        _cache([(0, "A")]),
        _cache([(0, "0"), (0, "1"), (0, "2")], numeric=True, count=1),
    )
    elements, warnings = module.parse_chart_xml(_chart(_series(sources=sources)))
    assert elements == [] and _warned(warnings, "limit")


def test_existing_outputters_keep_series_names_values_and_empty_cells():
    from dochan.model.document import Document, Section
    from dochan.output.json_out import to_dict
    from dochan.output.markdown import to_markdown
    from dochan.output.plain_text import to_plain_text

    elements, warnings = _parse(_chart(_series(values=[(0, ""), (1, "0")])))
    assert warnings == []
    document = Document(sections=[Section(elements=elements)])
    table = to_dict(document)['sections'][0]['elements'][0]
    assert table['caption']['text'] == "판매"
    assert table['rows'][1][1]['text'] == ""
    assert table['rows'][2][1]['text'] == "0"
    markdown = to_markdown(document)
    assert "판매" in markdown and "| 첫째 |  |" in markdown and "| 둘째 | 0 |" in markdown
    plain = to_plain_text(document)
    assert "판매" in plain and "둘째\t0" in plain


PUBLIC_CASES = [
    ("2차원원형.hwpx", "ce4304b8aa4fba79d493647d6fb1204b527bc2aac50c55a94bea9ec67f8994a8",
     "d97cfe9edf27f2b41116ac9d6d7102554743972934ebfa098136d688eddd3a26", "pieChart",
     ["판매"], [["10", "3.5", "1.5", "1.2"]]),
    ("꺽은선형.hwpx", "a8a4449c3641c107aadb6e597dbb780b5b7ae3dc50d4a144a2e87075af2fc398",
     "9c869af6b69e6eeba07a1d81e8d15f6ba701367def9baac3c21cb6ab1c0cfb14", "lineChart",
     ["계열 1", "계열 2", "계열 3"],
     [["4.3", "2.5", "3.5", "4.5"], ["2.4", "4.4", "1.8", "2.8"], ["2", "2", "3", "5"]]),
]


def _independent_public_gold(raw, kind):
    """Standard-library XML only; no implementation helpers or dochan output."""
    tree = ET.fromstring(raw)
    assert tree.tag == '{%s}chartSpace' % C
    assert tree.findall('c:chart/c:title/c:tx', NS) == []
    group = tree.find('c:chart/c:plotArea/c:' + kind, NS)
    assert group is not None
    gold = []
    for series in sorted(group.findall('c:ser', NS), key=lambda s: int(s.find('c:order', NS).attrib['val'])):
        name = series.findtext('c:tx/c:strRef/c:strCache/c:pt/c:v', namespaces=NS)
        columns = []
        for path in ('c:cat/c:strRef/c:strCache', 'c:val/c:numRef/c:numCache'):
            cache = series.find(path, NS)
            points = {int(point.attrib['idx']): point.findtext('c:v', namespaces=NS)
                      for point in cache.findall('c:pt', NS)}
            count = int(cache.find('c:ptCount', NS).attrib['val'])
            assert count == 4 and set(points) == set(range(count))
            columns.append([points[index] for index in range(count)])
        gold.append((name, list(map(list, zip(*columns)))))
    return gold


@pytest.mark.parametrize("filename,digest,part_digest,kind,names,values", PUBLIC_CASES,
                         ids=["public-pie", "public-line"])
def test_public_corpus_matches_independent_xml_gold(filename, digest, part_digest, kind, names, values):
    path = ROOT / 'corpus/hwp-public/hwpx' / filename
    if not path.is_file():
        pytest.skip("public corpus not installed; do not count this as real-document validation")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(path) as archive:
        raw = archive.read('Chart/chart1.xml')
    assert hashlib.sha256(raw).hexdigest() == part_digest
    gold = _independent_public_gold(raw, kind)
    # Fixed values were transcribed from XML in chart-spec.md, not from parser output.
    assert [name for name, rows in gold] == names
    assert [[row[1] for row in rows] for name, rows in gold] == values
    elements, warnings = _parse(raw)
    assert warnings == []
    assert all(isinstance(element, Table) for element in elements)
    assert len(elements) == len(gold)
    for table, (name, rows) in zip(elements, gold):
        assert table.caption_text == name
        assert _rows(table) == [["범주", "값"]] + rows
