"""차트 리뷰에서 확인된 값 손실과 자원 사용 회귀를 재현한다."""
from zipfile import ZipFile

import pytest
from lxml import etree

from dochan.hwpx.charts import parse_chart_xml
from dochan.ooxml import charts
from dochan.ooxml.package import OOXMLPackage
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.xlsx import XLSXReader
from test_chart_details import axis, root, series, table


@pytest.mark.parametrize('value,fmt', [
    ('121.5', '0"°"'), ('15848.931', '0.00E+00'),
    ('0.0891', '0%'), ('0.99984', '0.000'), ('70.5234', '0.0'),
    ('19239.04', '_(* $#,##0.00_)'), ('1.25', '[$-412]General'),
    ('12.5', '0.0"mm"'), ('12.5', '0"yy"'), ('0.5', '0.0"%"'),
])
def test_chart_non_temporal_formats_preserve_raw_numbers(value, fmt):
    assert charts.format_chart_number(value, fmt) == value


@pytest.mark.parametrize('reader_type', [XLSXReader, PPTXReader])
def test_axis_tick_format_never_formats_chart_data(reader_type):
    chart = root('<c:scatterChart>' + series('S', ['1'], ['121.5'], True, yfmt='0.00"°"')
                 + '<c:axId val="1"/><c:axId val="2"/></c:scatterChart>'
                 + axis('1', '2', 'b', 'X')
                 + axis('2', '1', 'l', 'Y', '<c:numFmt formatCode="yyyy-mm-dd" sourceLinked="0"/>'))
    assert table(reader_type, chart)[1] == ['1', '121.5']


@pytest.mark.parametrize('reader_type', [XLSXReader, PPTXReader])
@pytest.mark.parametrize('first,second,fmt', [('1.11', '1.12', '0.0'),
                                           ('43831.1', '43831.2', 'yyyy-mm-dd')])
def test_distinct_raw_x_coordinates_are_never_merged(reader_type, first, second, fmt):
    chart = root('<c:scatterChart>' + series('A', [first], ['10'], True, fmt)
                 + series('B', [second], ['20'], True, fmt) + '</c:scatterChart>')
    rows = table(reader_type, chart)
    assert rows[0] == ['Series', 'X', 'Y']
    assert len(rows) == 3
    assert [row[0] for row in rows[1:]] == ['A', 'B']


def test_chart_format_length_bounds_output_amplification():
    assert charts.format_chart_number('1.25', '0.' + '0' * 4088) == '1.25'


def test_chart_temporal_sections_use_numeric_branch_and_preserve_hidden_values():
    assert charts.format_chart_number('40091', 'dd;"";""') == '2009-10-05'
    assert charts.format_chart_number('0', 'dd;"";""') == '0'
    assert charts.format_chart_number('0.5', '[>=1]yyyy-mm-dd;0.00') == '0.5'


def test_chart_temporal_formatting_reuses_bounded_metadata_cache(monkeypatch):
    original = XLSXReader.__init__
    calls = []

    def init(self, *args, **kwargs):
        calls.append(1)
        original(self, *args, **kwargs)

    monkeypatch.setattr(XLSXReader, '__init__', init)
    for _ in range(100):
        assert charts.format_chart_number('42213', 'yyyy-mm-dd') == '2015-07-28'
    assert len(calls) <= 1


def test_caption_axes_index_is_built_once_for_many_groups(monkeypatch):
    original = charts._chart_children
    visits = []
    chart = root('<c:scatterChart><c:axId val="1"/><c:axId val="2"/></c:scatterChart>' * 1000
                 + axis('1', '2', 'b', 'X') + axis('2', '1', 'l', 'Y'))
    plot = chart.find('.//{%s}plotArea' % charts.C_NS)

    def measured(parent, *args):
        for item in original(parent, *args):
            if parent is plot:
                visits.append(1)
            yield item

    monkeypatch.setattr(charts, '_chart_children', measured)
    assert 'X axis: X' in charts.chart_caption(chart)
    assert len(visits) <= 4 * len(plot)


def test_excessive_chart_groups_warn_and_discard_optional_chart():
    chart = root('<c:scatterChart/>' * 1001)
    errors = []
    normalized = charts.normalize_chart(chart, errors)
    assert any('group limit' in error for error in errors)
    assert not charts.chart_series(normalized)


@pytest.mark.parametrize('format_code,expected', [('mm:ss', '00:00'),
                                                ('h:mm', '2015-07-28 07:00')])
def test_temporal_chart_formats_preserve_date_or_minute_semantics(format_code, expected):
    value = '0.5' if format_code == 'mm:ss' else '42213.2916666667'
    assert charts.format_chart_number(value, format_code) == expected


def test_automatic_title_without_tx_is_supported_in_ooxml_and_hwpx():
    chart = root('<c:barChart>' + series('Revenue', ['Q1'], ['1']) + '</c:barChart>',
                 extra='<c:title><c:overlay val="0"/></c:title><c:autoTitleDeleted val="0"/>')
    assert charts.chart_title(chart) == 'Revenue'
    elements, _ = parse_chart_xml(etree.tostring(chart), display_values=True)
    assert elements[0].text == 'Revenue'


def test_format_only_reference_does_not_spend_missing_cache_budget(tmp_path):
    path = tmp_path / 'source.xlsx'
    s = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    with ZipFile(path, 'w') as package:
        package.writestr('xl/workbook.xml', '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="S" sheetId="1" r:id="r1"/></sheets></workbook>' % (s, r))
        package.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        package.writestr('xl/styles.xml', '<styleSheet xmlns="%s"><cellXfs><xf numFmtId="0"/></cellXfs></styleSheet>' % s)
        package.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="%s"><sheetData><row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>42</v></c></row><row r="2"><c r="B2"><v>43</v></c></row></sheetData></worksheet>' % s)
    first = root('<c:lineChart><c:ser><c:val><c:numRef><c:f>S!$A$1:$A$150000</c:f><c:numCache><c:pt idx="0"><c:v>1</c:v></c:pt></c:numCache></c:numRef></c:val></c:ser></c:lineChart>')
    second = root('<c:lineChart><c:ser><c:val><c:numRef><c:f>S!$B$1:$B$60000</c:f></c:numRef></c:val></c:ser></c:lineChart>')
    errors = []
    with OOXMLPackage(str(path)) as package:
        resolver = charts.workbook_chart_resolver(package, errors)
        charts.hydrate_chart_references(first, package, '', errors, resolver)
        charts.hydrate_chart_references(second, package, '', errors, resolver)
    assert [p.text for p in second.findall('.//{%s}pt/{%s}v' % (charts.C_NS, charts.C_NS))] == ['42', '43']
    assert not errors
