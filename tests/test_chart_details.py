"""합성 OOXML로 차트의 축 역할과 표시 계약을 검증한다."""
import pytest
from lxml import etree

from dochan.ooxml import charts
from dochan.ooxml.xlsx import XLSXReader
from dochan.ooxml.pptx import PPTXReader

C = charts.C_NS
A = charts.A_NS


def root(plot, extra='', space=''):
    return etree.fromstring(('<c:chartSpace xmlns:c="%s" xmlns:a="%s">%s'
                             '<c:chart>%s<c:plotArea>%s</c:plotArea></c:chart>'
                             '</c:chartSpace>' % (C, A, space, extra, plot)).encode())


def source(role, values, fmt='General', numeric=True):
    cache = 'numLit' if numeric else 'strLit'
    points = ''.join('<c:pt idx="%d"><c:v>%s</c:v></c:pt>' % (i, v) for i, v in enumerate(values))
    return '<c:%s><c:%s><c:formatCode>%s</c:formatCode>%s</c:%s></c:%s>' % (role, cache, fmt, points, cache, role)


def series(name, x, y, xy=False, xfmt='General', yfmt='General'):
    return '<c:ser><c:tx><c:v>%s</c:v></c:tx>%s%s</c:ser>' % (
        name, source('xVal' if xy else 'cat', x, xfmt, numeric=xy or xfmt != 'General'),
        source('yVal' if xy else 'val', y, yfmt))


def axis(identity, cross, pos, title, numfmt=''):
    return ('<c:valAx><c:axId val="%s"/><c:axPos val="%s"/><c:crossAx val="%s"/>'
            '<c:title><c:tx><c:rich><a:p><a:r><a:t>%s</a:t></a:r></a:p></c:rich></c:tx></c:title>%s</c:valAx>'
            % (identity, pos, cross, title, numfmt))


def table(reader_type, chart):
    reader = reader_type()
    reader._errors = []
    result = reader._chart_series_table(chart)
    return [[cell.text for cell in row] for row in result.rows]


@pytest.mark.parametrize('positions', [('b', 'l'), ('l', 'l')])
def test_scatter_axis_ids_identify_x_y_even_when_axis_elements_are_reversed(positions):
    chart = root('<c:scatterChart><c:axId val="20"/><c:axId val="10"/></c:scatterChart>'
                 + axis('10', '20', positions[1], 'Response') + axis('20', '10', positions[0], 'Dose'))
    assert charts.chart_caption(chart) == 'Chart type: scatter; Y axis: Response; X axis: Dose'


def test_scatter_axis_positions_disambiguate_reversed_references():
    chart = root('<c:scatterChart><c:axId val="10"/><c:axId val="20"/></c:scatterChart>'
                 + axis('10', '20', 'l', 'Response') + axis('20', '10', 'b', 'Dose'))
    assert charts.chart_caption(chart) == 'Chart type: scatter; Y axis: Response; X axis: Dose'


@pytest.mark.parametrize('reader_type', [XLSXReader, PPTXReader])
def test_mixed_chart_separates_category_and_numeric_x(reader_type):
    chart = root('<c:barChart>' + series('Sales', ['Q1'], ['2']) + '</c:barChart>'
                 '<c:scatterChart>' + series('Sample', ['1.5'], ['3'], xy=True) + '</c:scatterChart>')
    assert table(reader_type, chart) == [['Series', 'Category', 'X', 'Y'],
                                       ['Sales', 'Q1', '', '2'], ['Sample', '', '1.5', '3']]


@pytest.mark.parametrize('reader_type', [XLSXReader, PPTXReader])
@pytest.mark.parametrize('xfmt,x,yfmt,y,expected_x,expected_y', [
    ('h:mm', '42213.2916666667', '0.0%', '0.125', '2015-07-28 07:00', '0.125'),
    ('yyyy-mm-dd', '42213', 'h:mm:ss', '0.5', '2015-07-28', '12:00:00'),
    ('General', '1.50', 'General', '2.00', '1.50', '2.00'),
])
def test_chart_numeric_formats_reuse_spreadsheet_display(reader_type, xfmt, x, yfmt, y, expected_x, expected_y):
    chart = root('<c:scatterChart>' + series('S', [x], [y], True, xfmt, yfmt) + '</c:scatterChart>')
    assert table(reader_type, chart)[1] == [expected_x, expected_y]


@pytest.mark.parametrize('linked,expected', [('0', '0.125'), ('1', '0.125')])
def test_axis_number_format_is_not_a_data_format(linked, expected):
    chart = root('<c:scatterChart>' + series('S', ['1'], ['0.125'], True, yfmt='0.00')
                 + '<c:axId val="1"/><c:axId val="2"/></c:scatterChart>'
                 + axis('1', '2', 'b', 'X')
                 + axis('2', '1', 'l', 'Y', '<c:numFmt formatCode="0.0%%" sourceLinked="%s"/>' % linked))
    assert table(XLSXReader, chart)[1][1] == expected


def test_chart_1904_dates_and_non_numeric_cache_strings():
    chart = root('<c:lineChart>' + series('S', ['0'], ['1'], xfmt='yyyy-mm-dd') + '</c:lineChart>',
                 space='<c:date1904 val="1"/>')
    assert table(XLSXReader, chart)[1] == ['1904-01-01', '1']


@pytest.mark.parametrize('deleted,expected', [('', ''), ('<c:autoTitleDeleted val="0"/>', 'Revenue'),
                                                           ('<c:autoTitleDeleted/>', ''), ('<c:autoTitleDeleted val="1"/>', '')])
def test_single_named_series_automatic_title(deleted, expected):
    chart = root('<c:barChart>' + series('Revenue', ['Q1'], ['1']) + '</c:barChart>', extra=deleted)
    assert charts.chart_title(chart) == expected


def test_automatic_title_does_not_invent_names_or_combine_multiple_series():
    assert charts.chart_title(root('<c:barChart>' + series('', [], []) + '</c:barChart>')) == ''
    assert charts.chart_title(root('<c:barChart>' + series('A', [], []) + series('B', [], []) + '</c:barChart>')) == ''


def test_explicit_empty_title_does_not_trigger_automatic_title():
    assert charts.chart_title(root('<c:barChart>' + series('A', [], []) + '</c:barChart>', extra='<c:title/>')) == ''


def test_formatted_date_time_preserves_fraction_and_ignores_invalid_format():
    assert charts.format_chart_number('42213.5', 'm/d/yy h:mm') == '2015-07-28 12:00'
    assert charts.format_chart_number('1e999', 'yyyy-mm-dd') == '1e999'
    assert charts.format_chart_number('7', '0' * 5000) == '7'


def test_source_linked_missing_cache_reads_cell_style(tmp_path):
    from zipfile import ZipFile
    from dochan.ooxml.package import OOXMLPackage
    path = tmp_path / 'synthetic.xlsx'
    s = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    with ZipFile(path, 'w') as package:
        package.writestr('xl/workbook.xml', '<workbook xmlns="%s" xmlns:r="%s"><workbookPr date1904="1"/><sheets><sheet name="S" sheetId="1" r:id="r1"/></sheets></workbook>' % (s, r))
        package.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        package.writestr('xl/styles.xml', '<styleSheet xmlns="%s"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="10"/></cellXfs></styleSheet>' % s)
        package.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="%s"><sheetData><row r="1"><c r="A1" s="1"><v>0</v></c><c r="B1" s="2"><v>0.125</v></c></row></sheetData></worksheet>' % s)
    chart = root('<c:scatterChart><c:ser><c:xVal><c:numRef><c:f>S!A1</c:f></c:numRef></c:xVal>'
                 '<c:yVal><c:numRef><c:f>S!B1</c:f></c:numRef></c:yVal></c:ser></c:scatterChart>')
    with OOXMLPackage(str(path)) as package:
        errors = []
        charts.hydrate_chart_references(chart, package, 'xl/charts/chart1.xml', errors,
                                        charts.workbook_chart_resolver(package, errors))
    assert not errors
    assert table(XLSXReader, chart)[1] == ['1904-01-01', '0.125']


def test_hwpx_chart_cache_uses_same_number_formats():
    from dochan.hwpx.charts import parse_chart_xml
    chart = root('<c:scatterChart>' + series('S', ['0.5'], ['0.125'], True, 'h:mm', '0.0%') + '</c:scatterChart>', extra='<c:autoTitleDeleted val="0"/>')
    elements, warnings = parse_chart_xml(etree.tostring(chart), display_values=True)
    result = next(e for e in elements if hasattr(e, 'rows'))
    assert [[c.text for c in row] for row in result.rows] == [['X', 'S'], ['12:00', '0.125']]
    assert elements[0].text == 'S'


def test_chartex_txdata_title_and_numeric_level_format_survive_normalization():
    cx = charts.CX_NS
    chart = etree.fromstring(('<cx:chartSpace xmlns:cx="%s"><cx:chartData><cx:data id="0">'
        '<cx:strDim type="cat"><cx:lvl><cx:pt idx="0">A</cx:pt></cx:lvl></cx:strDim>'
        '<cx:numDim type="val"><cx:lvl formatCode="0.0%%"><cx:pt idx="0">0.125</cx:pt></cx:lvl></cx:numDim>'
        '</cx:data></cx:chartData><cx:chart><cx:title><cx:tx><cx:txData><cx:v>Growth</cx:v></cx:txData></cx:tx></cx:title>'
        '<cx:plotArea><cx:plotAreaRegion><cx:series layoutId="paretoLine"><cx:dataId val="0"/></cx:series>'
        '</cx:plotAreaRegion></cx:plotArea></cx:chart></cx:chartSpace>' % cx).encode())
    errors = []
    normalized = charts.normalize_chart(chart, errors)
    assert not errors
    assert charts.chart_title(normalized) == 'Growth'
    assert charts.chart_caption(normalized) == 'Chart type: Pareto'
    assert normalized.findtext('.//{%s}formatCode' % C) == '0.0%'
    assert table(XLSXReader, normalized)[1] == ['A', '0.125']


def test_mixed_chart_separates_even_identical_category_and_x_and_keeps_bubble_size():
    chart = root('<c:barChart>' + series('A', ['1'], ['2']) + '</c:barChart>'
                 '<c:bubbleChart>' + series('B', ['1'], ['3'], True).replace('</c:ser>', source('bubbleSize', ['4']) + '</c:ser>')
                 + '</c:bubbleChart>')
    assert table(XLSXReader, chart) == [['Series', 'Category', 'X', 'Y', 'Bubble size'],
                                       ['A', '1', '', '2', ''], ['B', '', '1', '3', '4']]


def test_unrelated_cross_axes_are_not_assigned_xy_labels():
    chart = root('<c:scatterChart><c:axId val="1"/><c:axId val="2"/></c:scatterChart>'
                 + axis('1', '3', 'b', 'A') + axis('2', '4', 'l', 'B'))
    assert charts.chart_caption(chart) == 'Chart type: scatter; Value axis: A; Value axis: B'


def test_3d_chart_number_formats_resolve_category_value_and_series_axis_ids():
    chart = root('<c:bar3DChart>' + series('S', ['42213'], ['0.125'], xfmt='General')
                 + '<c:axId val="1"/><c:axId val="2"/><c:axId val="3"/></c:bar3DChart>'
                 '<c:catAx><c:axId val="1"/><c:numFmt formatCode="yyyy-mm-dd" sourceLinked="0"/></c:catAx>'
                 '<c:valAx><c:axId val="2"/><c:numFmt formatCode="0.0%" sourceLinked="0"/></c:valAx>'
                 '<c:serAx><c:axId val="3"/></c:serAx>')
    # Numeric category source is distinct from a string that happens to be digits.
    cat = chart.find('.//{%s}cat' % C)
    cat[0].tag = '{%s}numLit' % C
    assert table(XLSXReader, chart)[1] == ['42213', '0.125']


def test_axis_resolution_cost_does_not_multiply_with_cached_points(monkeypatch):
    original = charts._group_axes
    calls = []

    def measured(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(charts, '_group_axes', measured)
    chart = root('<c:scatterChart>' + series('S', ['1'] * 1000, ['0.5'] * 1000, True,
                                           yfmt='0.0%') + '</c:scatterChart>')
    result = table(XLSXReader, chart)
    assert len(result) == 1001
    assert result[-1] == ['1', '0.5']
    assert len(calls) <= 2
