"""공개 분수 XLS의 3,540개 표시를 Excel 저장 텍스트와 비교한다."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from dochan.office_binary.xls import _display_number_with_format
from dochan.spreadsheet_format import BUILTIN_NUM_FORMATS
from scripts.probe_chart_review_evidence import xls_cells

def _load_before(path):
    if path.is_dir():
        # Isolate a historical source tree from the already imported current
        # package. v1.12.0 has XLSXReader but no shared formatter module.
        source = ("import json, sys\n"
                  "if sys.argv[1] == 'shared':\n"
                  "    from dochan.spreadsheet_format import SpreadsheetNumberFormatter as Reader\n"
                  "else:\n"
                  "    from dochan.ooxml.xlsx import XLSXReader as Reader\n"
                  "reader = Reader()\n"
                  "for line in sys.stdin:\n"
                  "    value, fmt = json.loads(line)\n"
                  "    print(json.dumps(reader._format_cell_value(str(value), fmt)), flush=True)\n")
        kind = "shared" if (path / "dochan" / "spreadsheet_format.py").is_file() else "legacy"
        # nosemgrep: dangerous-subprocess-use-audit -- fixed Python argv, local snapshot only.
        process = subprocess.Popen([sys.executable, "-u", "-c", source, kind],
                                   cwd=str(path), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, bufsize=1)

        def before(value, fmt):
            process.stdin.write(json.dumps([value, fmt]) + "\n")
            process.stdin.flush()
            answer = process.stdout.readline()
            if not answer:
                raise RuntimeError("historical formatter failed: " + process.stderr.read()[:500])
            return json.loads(answer)

        def close():
            process.stdin.close()
            process.stdout.close()
            process.wait()
            process.stderr.close()

        before.close = close
        return before
    name = "dochan._fraction_before_probe"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    formatter = module.SpreadsheetNumberFormatter()
    def before(value, fmt):
        return formatter._format_cell_value(str(value), fmt)
    before.close = lambda: None
    return before


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
    try:
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
    finally:
        before_display.close()
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
