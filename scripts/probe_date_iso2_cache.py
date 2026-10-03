"""Replay extracted public Excel TEXT() cache rows against two formatter versions."""

import argparse
from collections import Counter
import json
from pathlib import Path

from dochan.spreadsheet_format import SpreadsheetNumberFormatter
from scripts.probe_date_iso2_delta import load_formatter


def display(formatter, row):
    formatter._date_1904 = row["date1904"]
    raw = row["raw"]
    if row["input_type"] not in ("n", ""):
        shown = ("TRUE" if raw == "1" else "FALSE") if row["input_type"] == "b" else raw
        return formatter._format_text_cell_value(shown, row["format"])
    return formatter._format_cell_value(raw, row["format"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--baseline-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    before_class = load_formatter(args.baseline_file.resolve())
    counts = Counter()
    changed = Counter()
    for row in json.loads(args.rows.read_text()):
        before = display(before_class(), row)
        after = display(SpreadsheetNumberFormatter(), row)
        expected = row["excel"]
        counts["rows"] += 1
        counts["before_exact"] += before == expected
        counts["after_exact"] += after == expected
        counts["gained"] += before != expected and after == expected
        counts["lost"] += before == expected and after != expected
        if before != after:
            changed[row["format"]] += 1
    result = {"counts": dict(counts), "changed_by_format": dict(changed)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
