"""반복된 BIFF 숫자 표시 서식의 결과 캐시가 출력과 상한을 지킨다."""

from unittest.mock import patch

from dochan.office_binary.xls import _display_number_with_format
from dochan.spreadsheet_format import SpreadsheetNumberFormatter


def test_repeated_xls_number_format_reuses_result_without_changing_output():
    formatter = SpreadsheetNumberFormatter()
    formatter._date_1904 = False
    formatter._errors = []
    original = SpreadsheetNumberFormatter._format_cell_value
    calls = []

    def counted(self, value, fmt):
        calls.append((value, fmt))
        return original(self, value, fmt)

    with patch.object(SpreadsheetNumberFormatter, "_format_cell_value", counted):
        actual = [_display_number_with_format(0.0, "#,##0;[Red](#,##0)", formatter=formatter)
                  for _ in range(1000)]
    assert actual == ["0"] * 1000
    assert calls == [("0", "#,##0;[Red](#,##0)")]
    assert formatter._errors == []


def test_xls_number_format_cache_is_bounded():
    formatter = SpreadsheetNumberFormatter()
    formatter._date_1904 = False
    formatter._errors = []
    for number in range(5000):
        _display_number_with_format(float(number), "0.00", formatter=formatter)
    assert len(formatter._display_value_cache) <= 4096


def test_xls_number_format_cache_keeps_epoch_and_warning_context():
    formatter = SpreadsheetNumberFormatter()
    formatter._date_1904 = False
    formatter._errors = []
    assert _display_number_with_format(61.0, "m/d/yy", formatter=formatter) == "1900-03-01"
    formatter._date_1904 = True
    assert _display_number_with_format(61.0, "m/d/yy", formatter=formatter) == "1904-03-02"

    _display_number_with_format(1e20, "m/d/yy", formatter=formatter)
    first_warning = formatter._errors[:]
    assert len(first_warning) == 1
    _display_number_with_format(1e20, "m/d/yy", formatter=formatter)
    assert formatter._errors == first_warning
    formatter._errors = []
    _display_number_with_format(1e20, "m/d/yy", formatter=formatter)
    assert formatter._errors == first_warning


def test_custom_formatter_side_effects_are_not_cached():
    class CustomFormatter(SpreadsheetNumberFormatter):
        calls = 0

        def _format_cell_value(self, value, fmt):
            self.calls += 1
            return str(self.calls)

    formatter = CustomFormatter()
    assert _display_number_with_format(1.0, formatter=formatter) == '1'
    assert _display_number_with_format(1.0, formatter=formatter) == '2'


def test_warning_source_and_error_sink_are_not_shared():
    formatter = SpreadsheetNumberFormatter()
    formatter._errors = []
    formatter._format_warning_source = 'first'
    _display_number_with_format(1e20, 'm/d/yy', formatter=formatter)
    _display_number_with_format(1e20, 'm/d/yy', formatter=formatter)
    formatter._format_warning_source = 'second'
    _display_number_with_format(1e20, 'm/d/yy', formatter=formatter)
    assert len(formatter._errors) == 2
    assert 'first' in formatter._errors[0]
    assert 'second' in formatter._errors[1]
    formatter._errors = []
    _display_number_with_format(1e20, 'm/d/yy', formatter=formatter)
    assert len(formatter._errors) == 1
    assert 'second' in formatter._errors[0]
