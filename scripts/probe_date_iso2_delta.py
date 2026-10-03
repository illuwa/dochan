"""Count public numeric-cell hash changes against one historical formatter file."""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from dochan.office_binary.xls import _display_number_with_format
from dochan.ooxml.xlsx import XLSXReader
from scripts.probe_chart_review_evidence import xls_cells
from scripts.probe_spreadsheet_format_hashes import _format_code, _kind, _ooxml_cells


def load_formatter(path):
    spec = importlib.util.spec_from_file_location("date_iso2_baseline", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SpreadsheetNumberFormatter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--baseline-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    baseline = load_formatter(args.baseline_file.resolve())
    counts = Counter()
    by_format = Counter()
    examples = []
    current_xlsx = XLSXReader()
    previous = baseline()
    for suffix in ("xls", "xlsx"):
        for root in (args.corpus / "poi-src/test-data", args.corpus / "lo-src"):
            for path in sorted(root.rglob("*." + suffix)):
                counts[(suffix, "files")] += 1
                try:
                    cells = xls_cells(path) if suffix == "xls" else _ooxml_cells(path)
                    for ref, cell in cells.items():
                        raw = cell["raw"]
                        if raw is None or cell["type"] not in ("", "n"):
                            continue
                        try:
                            number = float(raw)
                        except (ValueError, OverflowError):
                            continue
                        fmt = _format_code(cell["format"])
                        if suffix == "xls":
                            previous._date_1904 = False
                            old = _display_number_with_format(number, fmt, formatter=previous)
                            new = _display_number_with_format(number, fmt)
                        else:
                            previous._date_1904 = cell["date1904"]
                            current_xlsx._date_1904 = cell["date1904"]
                            old = previous._format_cell_value(raw, fmt)
                            new = current_xlsx._format_cell_value(raw, fmt)
                        counts[(suffix, "cells")] += 1
                        if hashlib.sha256(old.encode()).digest() != hashlib.sha256(new.encode()).digest():
                            counts[(suffix, "changed")] += 1
                            by_format[(suffix, fmt)] += 1
                            if len(examples) < 40:
                                examples.append({"file": str(path.relative_to(args.corpus)),
                                                 "cell": ref, "format": fmt,
                                                 "kind": _kind(fmt, current_xlsx)})
                except Exception as error:
                    counts[(suffix, "failures")] += 1
                    if len(examples) < 40:
                        examples.append({"file": str(path.relative_to(args.corpus)),
                                         "exception": type(error).__name__})
    result = {
        "counts": {suffix: {key: counts[(suffix, key)] for key in
                             ("files", "cells", "changed", "failures")}
                   for suffix in ("xls", "xlsx")},
        "changed_by_format": {suffix: {fmt: count for (kind, fmt), count in by_format.items()
                                       if kind == suffix} for suffix in ("xls", "xlsx")},
        "examples": examples,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"counts": result["counts"], "changed_by_format":
                      result["changed_by_format"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
