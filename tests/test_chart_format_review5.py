"""5차 리뷰의 선택 구역·시간 정밀도·리터럴 표시를 검증한다."""
import pytest

from dochan.ooxml.xlsx import XLSXReader
from dochan.ooxml.charts import format_chart_number


@pytest.mark.parametrize('fmt', ['h:mm;h:m:s', 'h:mm;[h]:mm'])
def test_unused_negative_section_does_not_change_positive_time(fmt):
    assert XLSXReader()._format_cell_value('0.5', fmt) == '12:00'
    assert format_chart_number('0.5', fmt) == '12:00'


@pytest.mark.parametrize('fmt,expected', [
    ('[$-409][h]:mm:ss', '36:00:00'),
    ('[$-409][h]:mm:ss;@', '36:00:00'),
    ('[Red][h]:mm', '36:00'), ('[h]:mm:ss_)', '36:00:00 '),
    ('[h]"시간" mm"분"', '36시간 00분'),
    (r'[h]\h mm\m', '36h 00m'), ('[h]*x:mm', '36:00'),
    ('[h]":"mm', '36:00'), ('[h] mm', '36 00'),
])
def test_elapsed_annotations_and_literals(fmt, expected):
    assert XLSXReader()._format_cell_value('1.5', fmt) == expected
    assert format_chart_number('1.5', fmt) == expected


def test_negative_elapsed_1904():
    reader = XLSXReader()
    reader._date_1904 = True
    assert reader._format_cell_value('-0.25', '[h]:mm') == '-6:00'
    assert format_chart_number('-0.25', '[h]:mm', True) == '-6:00'
    assert format_chart_number('-0.25', '[h]:mm', False) == '-0.25'


@pytest.mark.parametrize('fmt', ['[h]:[m]', '[h]:ss', 'hh:mm:ss.0000', '[s].0000'])
def test_unsupported_combinations_still_preserve_raw(fmt):
    assert XLSXReader()._format_cell_value('0.5', fmt) == '0.5'
    assert format_chart_number('0.5', fmt) == '0.5'


@pytest.mark.parametrize('value,fmt,expected', [
    ('0.5', 'hh:mm:ss.000', '12:00:00.000'),
    ('0.1702084490740741', 'h:m:s.00', '4:5:6.01'),
    ('0.1702084490740741', 'h:m:s', '4:5:6'),
    ('1.5', '[h]:mm:ss.000', '36:00:00.000'),
    ('3.14159', '[ss].000', '271433.376'),
    ('0.5', 'ss.00', '00.00'), ('0.5', 'ss', '00'), ('0.5', 's', '0'),
    ('43831.5', 'yyyy-mm-dd hh:mm:ss.0', '2020-01-01 12:00:00.0'),
    ('43831.00006944444', 'yyyy-mm-dd ss', '2020-01-01 00:00:06'),
    ('4.6875000000000004E-4', '[h]:mm:ss', '0:00:41'),
    ('4.6875000000000004E-4', 'mm:ss', '00:41'),
    ('0.999999999', 'hh:mm:ss.000', '00:00:00.000'),
    ('43831.999999999', 'yyyy-mm-dd hh:mm:ss.000', '2020-01-02 00:00:00.000'),
])
def test_temporal_precision_and_half_up(value, fmt, expected):
    assert XLSXReader()._format_cell_value(value, fmt) == expected
    assert format_chart_number(value, fmt) == expected


def test_chart_minute_second_keeps_serial_date():
    assert format_chart_number('1.5', 'mm:ss') == '1900-01-01 12:00:00'


def test_conditional_empty_literal_is_empty():
    assert XLSXReader()._format_cell_value('-1E-8', '[<0]"";0%') == ''
    assert XLSXReader()._format_cell_value('0.5', '[<0]"";0%') == '50%'


@pytest.mark.parametrize('value,fmt,expected', [
    ('1.5', '[$-409][h]:mm:ss', '36:00:00'),
    ('1.5', '[h]"시간" mm"분"', '36시간 00분'),
    ('0.125', 'hh:mm:ss.000', '03:00:00.000'),
    ('0.5', 'ss', '00'),
    ('4.6875000000000004E-4', '[h]:mm:ss', '0:00:41'),
])
def test_review5_display_reaches_four_chart_readers(value, fmt, expected):
    from test_chart_format_revision import test_elapsed_display_reaches_all_four_chart_readers
    test_elapsed_display_reaches_all_four_chart_readers(value, fmt, expected)


def test_selected_time_section_in_real_reader(tmp_path):
    from test_xlsx_reader import _write_xlsx
    path = tmp_path / 'sections.xlsx'
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    _write_xlsx(
        path,
        '<workbook xmlns="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>' % ns,
        {'xl/worksheets/sheet1.xml': '<worksheet xmlns="%s"><sheetData><row r="1">'
         '<c r="A1" s="0"><v>0.5</v></c><c r="B1" s="1"><v>0.5</v></c>'
         '</row></sheetData></worksheet>' % ns},
        styles_xml='<styleSheet xmlns="%s"><numFmts>'
        '<numFmt numFmtId="164" formatCode="h:mm;h:m:s"/>'
        '<numFmt numFmtId="165" formatCode="h:mm;[h]:mm"/>'
        '</numFmts><cellXfs><xf numFmtId="164"/><xf numFmtId="165"/></cellXfs></styleSheet>' % ns,
    )
    doc = XLSXReader().read(str(path))
    assert [cell.text for cell in doc.sections[0].elements[0].rows[0]] == ['12:00', '12:00']
