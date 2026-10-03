"""공개 Excel TEXT() 저장값으로 확인한 분수 자리와 리터럴 규칙."""

import random
import string
from time import perf_counter

import pytest

from dochan.spreadsheet_format import SpreadsheetNumberFormatter


@pytest.mark.parametrize("value, fmt, expected", [
    ("23.75", r"|#\:#=/=?|", "|23:3=/=4|"),
    ("0.75", r"|#\:#/#|", "|3/4|"),
    ("23.75", r"|#\:? ?=/=#|", "|2:3 3=/=4|"),
    ("3.75", "|#_#=/=?|", "|15 =/=4|"),
    ("0", r"|#\:#=/=?|", "|0      |"),
    ("0", r"|#\:0=/=?|", "|0=/=1|"),
    ("0.75", r"|?\:#=/=#|", "|  3=/=4|"),
    ("0.75", r"|0\:#=/=#|", "|0:3=/=4|"),
    ("0", "|#_#/#|", "|0 /1|"),
    ("23.75", "|#-#-#\\:#/#|", "|-2-3:3/4|"),
])
def test_fraction_literal_excel_text_cache(value, fmt, expected):
    """NumberFormatTests.xlsx의 A139, A122, A149, A177, A141, A205, A234, A243, A169, A127."""
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


@pytest.mark.parametrize("value, fmt, expected", [
    ("1.5", "?/?", "1 1/2"),
    ("3.75", "# ?/?", "3 3/4"),
    ("0.5", "# ?/?", "1/2"),
])
def test_fraction_mixed_and_improper_slots(value, fmt, expected):
    assert SpreadsheetNumberFormatter()._format_cell_value(value, fmt) == expected


def test_fraction_malformed_formats_fall_back_without_exception():
    formatter = SpreadsheetNumberFormatter()
    rng = random.Random(42027)
    alphabet = string.ascii_letters + '0#?/\\_ *[];:=|-'
    for _ in range(1000):
        fmt = '# ?/?"' + "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 300)))
        assert formatter._format_cell_value("1.50", fmt) == "1.50"
    assert formatter._format_cell_value("1.50", "# ?/?" * 43) == "1.50"


def test_fraction_token_scan_scales_linearly():
    formatter = SpreadsheetNumberFormatter()
    short = r"#\:" * 5000 + "#/?"
    long = r"#\:" * 10000 + "#/?"
    started = perf_counter()
    formatter._fraction_tokens(short)
    short_time = perf_counter() - started
    started = perf_counter()
    formatter._fraction_tokens(long)
    long_time = perf_counter() - started
    assert long_time < max(short_time * 3.5, 0.5)
