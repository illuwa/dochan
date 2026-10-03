"""Fraction token path regressions from public Excel display evidence."""

import os
import itertools
import random
import re
from fractions import Fraction
from pathlib import Path
from time import perf_counter

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("value, fmt, expected", [
    ("1.05", "[Red]# ?/10", "1 1/10"),
    ("-1.05", "# ??/100;-# ??/100", "-1  5/100"),
    ("0.5", "?/10", "5/10"),
    ("1.2", "???/100", "1 20/100"),
    ("1.05", "$# ??/100", "$1  5/100"),
    ("3.75", "_(# ?/?_)", " 3 3/4 "),
    ("3.75", "#,##0 ?/?", "3 3/4"),
    ("0.5", "#,##0 ?/?", "1/2"),
    ("10000000000", "#,##0 ?/?", "10000000000"),
    ("1225", "00/00", "12/25"),
    ("1.5", "?/?", "1 1/2"),
    ("3.75", "# ? / ?", "3 3/4"),
    ("3.75", "# ?-/-?", "3 3/4"),
])
def test_fraction_review_display(value, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("1", "?/2", "1"),
    ("2", "?/10", "2"),
    ("3", "???/100", "3"),
    ("-1", "?/8;-?/8", "-1"),
    ("1", "#_?/10", "1"),
    ("3.75", "$#,##0 ?/?", "$3 3/4"),
    ("1234567.5", "$#,##0 ?/?", "$1,234,567 1/2"),
    ("3.75", "# ?/?%", "3 3/4"),
    ("3.75", "# ?? / ??", "3 3/4"),
])
def test_fraction_second_review_regressions(value, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


def test_fraction_token_path_preserves_numeric_value_grid():
    """Check the rendered number across the review's synthetic format grid."""
    class TokenFormatter(SpreadsheetNumberFormatter):
        token_used = False

        def _fraction_tokens(self, section):
            self.token_used = True
            return super()._fraction_tokens(section)

    formatter = TokenFormatter()
    prefixes = ('', '[Red]', '$', '"약 "', '[$€-2] ', '_(')
    wholes = ('# ', '#,##0 ', '0 ', '', '#_', '? ')
    numerators = ('?', '??', '???', '#', '0')
    denominators = ('?', '??', '???', '2', '4', '8', '10', '16', '100', '1000')
    suffixes = ('', '" in"', '_)', ' [$€-2]', '""')
    values = (0, 1, 2, 3, .5, 1.5, 3.75, .99, .96, 1.05,
              12345.678, 1234567.5, -1, -3.75, -.5, .001)
    fraction_pattern = re.compile(r'\s*(-)?\s*(?:(\d[\d,]*)\s+)?(\d+)\s*/\s*(\d+)\s*')
    integer_pattern = re.compile(r'\s*(-)?\s*(\d[\d,]*)\s*')
    checked = 0
    for prefix, whole, numerator, denominator, suffix in itertools.product(
            prefixes, wholes, numerators, denominators, suffixes):
        fmt = prefix + whole + numerator + '/' + denominator + suffix
        limit = int(denominator) if denominator.isdigit() else 10 ** len(denominator) - 1
        tolerance = (Fraction(1, 2 * limit) + Fraction(1, 10 ** 9)
                     if denominator.isdigit() else Fraction(1))
        for value in values:
            formatter.token_used = False
            rendered = formatter._format_cell_value(repr(value), fmt)
            if not formatter.token_used or rendered == repr(value):
                continue
            numeric = re.sub(r'[^\d/ ,\-]', ' ', rendered)
            match = fraction_pattern.fullmatch(numeric)
            if match:
                sign = -1 if match[1] else 1
                shown = sign * (int((match[2] or '0').replace(',', '')) +
                                Fraction(int(match[3]), int(match[4])))
            else:
                match = integer_pattern.fullmatch(numeric)
                if not match:
                    continue
                shown = (-1 if match[1] else 1) * int(match[2].replace(',', ''))
            checked += 1
            assert abs(shown - Fraction(value)) <= tolerance, (fmt, value, rendered)
    assert checked > 10000


def test_fraction_inconsistent_parts_fall_back_before_rendering():
    class InconsistentFormatter(SpreadsheetNumberFormatter):
        calls = 0

        def _fraction_number(self, number, denominator_limit, fixed_denominator=0):
            self.calls += 1
            return "1/2"

    formatter = InconsistentFormatter()
    assert formatter._format_cell_value("3.75", '$# ?/?') == "1/2"
    assert formatter.calls == 2


def test_public_fraction_table_token_path():
    """The public 54686 table supplies 3,540 Excel display strings."""
    root = os.environ.get("DOCHAN_PUBLIC_SPREADSHEET_CORPUS")
    if not root:
        pytest.skip("set DOCHAN_PUBLIC_SPREADSHEET_CORPUS for the public POI corpus")
    from scripts.probe_xls_fraction_excel import token_compare

    result = token_compare(Path(root))
    assert result["total"] == 3540
    assert result["red_normalized"] == 3540
    assert result["empty_suffix_normalized"] == 3540
    assert result["red_exact"] == 3540
    assert result["empty_suffix_exact"] == 3540


def test_zero_fill_classification_uses_selected_section():
    formatter = SpreadsheetNumberFormatter()
    assert formatter._format_metadata("00;# ?/?").kind == "zero_fill"


def test_fraction_fuzz_reaches_token_path_and_public_length_limit():
    class CountingFormatter(SpreadsheetNumberFormatter):
        calls = 0

        def _fraction_tokens(self, section):
            self.calls += 1
            return super()._fraction_tokens(section)

    formatter = CountingFormatter()
    rng = random.Random(5441)
    alphabet = "abc#?0/-:_"
    for _ in range(1000):
        literal = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 90)))
        rendered = formatter._format_cell_value("1.50", '[Red]# ?/?"' + literal + '"')
        assert isinstance(rendered, str)
    assert formatter.calls == 1000
    short = '[Red]' + '#\\:' * 20 + '# ?/?'
    long = '[Red]' + '#\\:' * 48 + '# ?/?'
    assert len(long) <= 255
    start = perf_counter()
    for _ in range(500):
        formatter._format_cell_value("1.5", short)
    short_time = perf_counter() - start
    start = perf_counter()
    for _ in range(500):
        formatter._format_cell_value("1.5", long)
    long_time = perf_counter() - start
    assert long_time < max(short_time * 4, 0.25)
    assert formatter._format_cell_value("1.5", long + "#" * 256) == "1.5"


@pytest.mark.parametrize("value, fmt, expected", [
    ("1", '?/2" in"', "1 in"),
    ("1.5", '?/2" in"', "1 1/2 in"),
    ("-1", "?/8;-?/8", "-1"),
])
def test_fraction_fallback_keeps_literal_affixes(value, fmt, expected):
    """토큰 경로를 버릴 때는 리터럴 접두·접미까지 수정 전 표시와 같아야 한다."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected
