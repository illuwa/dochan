"""공개 XLS/XLSX 숫자 셀 표시 해시를 비교하고 서식 종류별 변경을 센다."""
import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile

from dochan.office_binary.xls import _display_number_with_format
from dochan.ooxml.xlsx import BUILTIN_NUM_FORMATS, XLSXReader
from scripts.probe_chart_review_evidence import ooxml_cells, xls_cells


def _ooxml_cells(path):
    try:
        return ooxml_cells(path)
    except zipfile.BadZipFile:
        # Encrypted OOXML is a CFB wrapper.  Keep the decrypted ZIP in memory.
        from dochan.cfb import OleFileIO
        from dochan.crypto.ooxml import decrypt_ooxml
        with OleFileIO(str(path)) as archive:
            package = decrypt_ooxml(archive)
        return ooxml_cells(BytesIO(package))


def _format_code(code):
    if code.startswith("builtin:"):
        return BUILTIN_NUM_FORMATS.get(int(code.split(":", 1)[1]), "")
    return code


def _kind(fmt, reader):
    if not fmt or fmt.lower() in ("general", "@"):
        return "General"
    metadata = reader._format_metadata(fmt)
    kind = metadata.kind or "General"
    if kind == "decimal":
        literals = [token for token, is_format in reader._format_literal_tokens(fmt)
                    if not is_format]
        accounting = any("(" in token or ")" in token for token in literals)
        return "currency/accounting" if metadata.currency_symbol or accounting else "decimal"
    return kind


def snapshot(roots, suffix):
    result = {}
    reader = XLSXReader()
    for root in roots:
        for path in sorted(root.rglob("*." + suffix)):
            name = root.name + "/" + str(path.relative_to(root))
            try:
                cells = xls_cells(path) if suffix == "xls" else _ooxml_cells(path)
                rows = {}
                for ref, cell in cells.items():
                    if cell["raw"] is None or cell["type"] not in ("", "n"):
                        continue
                    try:
                        number = float(cell["raw"])
                    except (ValueError, OverflowError):
                        continue
                    fmt = _format_code(cell["format"])
                    if suffix == "xls":
                        shown = _display_number_with_format(number, fmt)
                    else:
                        reader._date_1904 = cell["date1904"]
                        shown = reader._format_cell_value(cell["raw"], fmt)
                    rows[ref] = [hashlib.sha256(shown.encode("utf-8")).hexdigest(), _kind(fmt, reader)]
                result[name] = rows
            except Exception as error:
                result[name] = {"failure": type(error).__name__}
    return result


def compare(before, after):
    counts, kinds = Counter(), Counter()
    for filename in sorted(set(before) | set(after)):
        old, new = before.get(filename, {}), after.get(filename, {})
        counts["files"] += 1
        if "failure" in old or "failure" in new:
            counts["failures"] += 1
            continue
        for ref in set(old) | set(new):
            if ref not in old or ref not in new:
                counts["cell_set_difference"] += 1
                continue
            counts["aligned_cells"] += 1
            if old[ref][0] != new[ref][0]:
                counts["changed_cells"] += 1
                kinds[new[ref][1]] += 1
    return {"counts": dict(counts), "changed_by_format": dict(kinds)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "compare"))
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--suffix", choices=("xls", "xlsx"), default="xls")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot(args.roots, args.suffix)
        print("files=%d failures=%d" % (len(result), sum("failure" in row for row in result.values())))
    else:
        result = compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
        print(json.dumps(result, ensure_ascii=False))
    args.output.write_text(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
