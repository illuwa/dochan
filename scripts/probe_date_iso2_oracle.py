"""Independently check changed public XLS partial-date cells using rational serials."""

import argparse
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
import json
from pathlib import Path
import random

from dochan.office_binary.xls import _display_number_with_format
from scripts.probe_chart_review_evidence import xls_cells


FILES = (
    "poi-src/test-data/spreadsheet/12843-1.xls",
    "lo-src/sc/qa/unit/data/xls/external_named_function.xls",
)


def calendar_components(raw):
    day = Fraction(raw).__floor__()
    if day == 0:
        return 1, 0
    if day == 60:
        return 2, 29
    if day < 60:
        actual = date(1900, 1, 1) + timedelta(days=day - 1)
    else:
        actual = date(1900, 3, 1) + timedelta(days=day - 61)
    return actual.month, actual.day


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    counts = Counter()
    candidates = {}
    for relative in FILES:
        for ref, cell in xls_cells(args.corpus / relative).items():
            fmt = cell["format"]
            if fmt not in ('d', 'm"月"d"日"') or cell["raw"] is None:
                continue
            month, day = calendar_components(cell["raw"])
            expected = str(day) if fmt == 'd' else "%d月%d日" % (month, day)
            actual = _display_number_with_format(float(cell["raw"]), fmt)
            counts[(fmt, "total")] += 1
            if expected == actual:
                counts[(fmt, "match")] += 1
            else:
                counts[(fmt, "mismatch")] += 1
            candidates.setdefault(fmt, []).append({
                "file": relative, "cell": ref, "raw": cell["raw"],
                "expected": expected, "actual": actual,
            })
    rng = random.Random(20261003)
    samples = []
    for fmt, rows in candidates.items():
        samples.extend(rng.sample(rows, min(10, len(rows))))
    result = {"counts": {fmt: {key: counts[(fmt, key)] for key in ("total", "match", "mismatch")}
                         for fmt in candidates}, "samples": samples}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
