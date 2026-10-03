"""공개 분수 XLS의 3,540개 표시를 Excel 저장 텍스트와 비교한다."""
import argparse
from collections import Counter
import json
from pathlib import Path

from dochan.office_binary.xls import _display_number_with_format
from dochan.spreadsheet_format import BUILTIN_NUM_FORMATS
from scripts.probe_chart_review_evidence import xls_cells
from scripts.probe_xls_format_pairs import _load_before


def _normalize(value):
    # Excel .txt의 열 너비 맞춤 공백은 Markdown 셀의 표시 정보가 아니다.
    return "".join(value.split())


def compare(corpus, before_code):
    cells = xls_cells(corpus / "54686_fraction_formats.xls")
    lines = (corpus / "54686_fraction_formats.txt").read_text(encoding="utf-8").splitlines()
    before_display = _load_before(before_code)
    counts = Counter()
    categories = Counter()
    mismatches = Counter()
    examples = []
    for row_number, line in enumerate(lines[1:355], 2):
        columns = line.split("\t")
        for column_index, letter in enumerate("DEFGHIJKLM", 3):
            cell = cells["Sheet1!" + letter + str(row_number)]
            fmt = cell["format"]
            if fmt.startswith("builtin:"):
                fmt = BUILTIN_NUM_FORMATS[int(fmt.split(":", 1)[1])]
            value = float(cell["raw"])
            expected = columns[column_index]
            before = before_display(value, fmt)
            after = _display_number_with_format(value, fmt)
            was_exact = _normalize(before) == _normalize(expected)
            is_exact = _normalize(after) == _normalize(expected)
            counts["total"] += 1
            counts["before_match"] += was_exact
            counts["after_match"] += is_exact
            counts["gained"] += not was_exact and is_exact
            counts["lost"] += was_exact and not is_exact
            counts["exact_space_after"] += after.strip() == expected.strip()
            kind = "fixed denominator" if letter in "GHIJKL" else "variable denominator"
            if before != after:
                categories[kind] += 1
            if not is_exact:
                mismatches[kind] += 1
            if not is_exact and len(examples) < 20:
                examples.append({"cell": letter + str(row_number), "format": fmt,
                                 "expected": expected.strip(), "before": before, "after": after})
    return {"counts": dict(counts), "changed_by_kind": dict(categories),
            "mismatch_by_kind": dict(mismatches), "mismatch_examples": examples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--before-code", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.corpus, args.before_code)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
