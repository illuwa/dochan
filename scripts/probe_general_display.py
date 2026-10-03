"""원시 셀의 General 표시 후보를 조사한다. 실제 리더 검증은 probe_general_display_e2e를 쓴다."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import re

from dochan.office_binary.xls import _display_number_with_format, _format_number
from dochan.ooxml.xlsx import XLSXReader
from scripts.probe_chart_review_evidence import xls_cells
from scripts.probe_spreadsheet_format_hashes import _format_code, _ooxml_cells


def inspect(roots, sample_size=30):
    counts = Counter()
    sample = []
    rng = random.Random(20261003)
    reader = XLSXReader()
    for suffix, loader in (("xls", xls_cells), ("xlsx", _ooxml_cells)):
        for root in roots:
            for path in sorted(root.rglob("*." + suffix)):
                try:
                    cells = loader(path)
                except Exception:
                    counts[suffix + "_unreadable_files"] += 1
                    continue
                for ref, cell in cells.items():
                    if cell["raw"] is None or cell["type"] not in ("", "n"):
                        continue
                    fmt = _format_code(cell["format"])
                    if fmt and not re.search(r"general", reader._format_code_tokens(fmt), re.I):
                        continue
                    try:
                        number = float(cell["raw"])
                    except (ValueError, OverflowError):
                        continue
                    if not math.isfinite(number):
                        continue
                    counts[suffix + "_general_cells"] += 1
                    before = _format_number(number) if suffix == "xls" else cell["raw"]
                    after = (_display_number_with_format(number, fmt) if suffix == "xls"
                             else reader._format_cell_value(cell["raw"], fmt))
                    if before == after:
                        continue
                    counts[suffix + "_changed"] += 1
                    if number.is_integer() and abs(number) >= 10 ** 15:
                        kind = "integer_16plus"
                    elif number.is_integer():
                        kind = "integer_15orless"
                    elif abs(number) < 10 ** -7 or abs(number) >= 10 ** 11:
                        kind = "very_small_or_large"
                    else:
                        kind = "decimal"
                    counts[suffix + "_" + kind] += 1
                    item = {"file": root.name + "/" + str(path.relative_to(root)),
                            "cell": ref, "kind": kind, "before": before, "after": after}
                    seen = counts["all_changed"] = counts["all_changed"] + 1
                    if len(sample) < sample_size:
                        sample.append(item)
                    else:
                        index = rng.randrange(seen)
                        if index < sample_size:
                            sample[index] = item
    return {"counts": dict(counts), "sample": sample}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = inspect(args.roots)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["counts"])


if __name__ == "__main__":
    main()
