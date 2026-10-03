"""Fraction token path regressions from public Excel display evidence."""

import os
import random
from pathlib import Path
from time import perf_counter

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("value, fmt, expected", [
    ("1.05", "[Red]# ?/10", "1 1/10"),
    ("-1.05", "# ??/100;-# ??/100", "-1  5/100"),
    ("0.5", "?/10", "5/10"),
    ("1.2", "???/100", "120/100"),
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
