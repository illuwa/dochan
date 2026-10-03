"""공개 XLS/XLSX 짝의 같은 숫자 셀 표시를 전후 비교한다.

이전 XLS 소스 스냅숏, 코퍼스 경로, 출력 경로는 명령행 인자로 받는다.
출력에는 집계와 소수의 차이 예만 남기며 문서 전체 출력은 저장하지 않는다.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

from dochan.office_binary.xls import _display_number_with_format
from dochan.ooxml.xlsx import BUILTIN_NUM_FORMATS, XLSXReader
from scripts.compare_office_pairs import find_pairs
from scripts.probe_chart_review_evidence import ooxml_cells, xls_cells


def _format_code(code):
    if code.startswith("builtin:"):
        return BUILTIN_NUM_FORMATS.get(int(code.split(":", 1)[1]), "")
    return code


def _load_before(path):
    name = "dochan.office_binary._xls_before_format_probe"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module._display_number_with_format


def compare(roots, before_code):
    before_display = _load_before(before_code)
    reader = XLSXReader()
    counts, reasons, examples, remaining = Counter(), Counter(), [], []
    pair_names, failures = [], []
    pairs = [pair for pair in find_pairs([str(root) for root in roots]) if pair[0].endswith(".xls")]
    for name, xlsx_path, xls_path in pairs:
        try:
            answer, candidate = ooxml_cells(Path(xlsx_path)), xls_cells(Path(xls_path))
        except Exception as error:
            failures.append({"file": name, "error": type(error).__name__})
            continue
        pair_names.append(name)
        for coordinate, cell in candidate.items():
            other = answer.get(coordinate)
            if not other or other["raw"] is None or other["type"] not in ("n", ""):
                continue
            try:
                value, expected_value = float(cell["raw"]), float(other["raw"])
            except (ValueError, OverflowError):
                continue
            if abs(value - expected_value) > max(1e-9, abs(expected_value) * 1e-12):
                continue
            fmt, other_fmt = _format_code(cell["format"]), _format_code(other["format"])
            reader._date_1904 = other["date1904"]
            expected = reader._format_cell_value(other["raw"], other_fmt)
            before = before_display(value, fmt, other["date1904"])
            after = _display_number_with_format(value, fmt, other["date1904"])
            counts["aligned"] += 1
            counts["before_match" if before == expected else "before_mismatch"] += 1
            counts["after_match" if after == expected else "after_mismatch"] += 1
            verdict = "improved" if before != expected and after == expected else (
                "regressed" if before == expected and after != expected else "unchanged")
            counts[verdict] += 1
            if before != expected:
                reasons[(reader._format_metadata(fmt).kind or "General", fmt, other_fmt)] += 1
            if before != after and len(examples) < 30:
                examples.append({"file": name, "cell": coordinate, "format": fmt,
                                 "expected": expected, "before": before, "after": after,
                                 "verdict": verdict})
            if after != expected and len(remaining) < 30:
                remaining.append({"file": name, "cell": coordinate, "format": fmt,
                                  "expected": expected, "before": before, "after": after,
                                  "verdict": verdict})
    return {"counts": dict(counts), "pair_count": len(pairs), "measured_pairs": len(pair_names),
            "failures": failures, "top20_before_mismatch": [
                {"kind": kind, "xls_format": fmt, "xlsx_format": other_fmt, "count": count}
                for (kind, fmt, other_fmt), count in reasons.most_common(20)],
            "examples": examples, "remaining": remaining}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--before-code", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.roots, args.before_code)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
