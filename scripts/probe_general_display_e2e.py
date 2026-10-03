"""공개 XLS/XLSX를 실제 리더로 읽어 변경 셀의 해시와 요약만 비교한다.

dump CODE_ROOT OUTPUT ROOT... / compare BASE HEAD MANIFEST /
values CODE_ROOT MANIFEST OUTPUT ROOT... / summarize MANIFEST BASE_VALUES HEAD_VALUES OUTPUT ROOT...
"""
import argparse
from collections import Counter
import gzip
import hashlib
from itertools import zip_longest
import json
from multiprocessing import Pool
from pathlib import Path
import random
import re
import sys


def _paths(roots):
    for root in roots:
        for suffix in ("xls", "xlsx"):
            for path in sorted(root.rglob("*." + suffix)):
                yield root.name + "/" + str(path.relative_to(root)), str(path)


def _initialize(code_root):
    sys.path.insert(0, str(code_root))


def _read_document(path):
    from dochan.office_binary.xls import XLSReader
    from dochan.ooxml.xlsx import XLSXReader
    return (XLSReader() if path.lower().endswith(".xls") else XLSXReader()).read(path)


def _document_cells(path, wanted=None):
    doc = _read_document(path)
    cells = {}
    for table_index, table in enumerate(doc.find_all("table")):
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row):
                key = "%d:%d:%d" % (table_index, row_index, col_index)
                if wanted is not None and key not in wanted:
                    continue
                value = cell.text
                if not value:
                    continue
                if wanted is None:
                    provenance = cell.provenance
                    cells[key] = [hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest(),
                                  len(value), provenance.sheet if provenance else "",
                                  provenance.cell if provenance else ""]
                else:
                    cells[key] = value
    return cells, doc.errors[:40]


def _dump_one(job):
    name, path = job
    try:
        cells, errors = _document_cells(path)
        return {"file": name, "cells": cells, "errors": errors}
    except Exception as exc:
        return {"file": name, "failure": type(exc).__name__}


def dump(code_root, output, roots, workers):
    jobs = sorted(_paths(roots))
    with Pool(workers, initializer=_initialize, initargs=(code_root,)) as pool:
        with gzip.open(output, "wt", encoding="utf-8") as target:
            for row in pool.imap(_dump_one, jobs, chunksize=1):
                target.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("files", len(jobs))


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            yield json.loads(line)


def compare(before, after, manifest_path):
    counts = Counter()
    changes = {}
    for left, right in zip_longest(_rows(before), _rows(after)):
        if left is None or right is None or left["file"] != right["file"]:
            raise ValueError("dump file order differs")
        counts["files"] += 1
        if "failure" in left or "failure" in right:
            counts["failed_files"] += 1
            continue
        before_cells, after_cells = left["cells"], right["cells"]
        counts["reader_error_files"] += any(error.startswith("ERR:")
                                            for error in left["errors"] + right["errors"])
        counts["empty_output_files"] += not before_cells and not after_cells
        counts["files_with_cells"] += bool(before_cells or after_cells)
        counts["aligned_cells"] += len(before_cells.keys() & after_cells.keys())
        changed = [key for key in before_cells.keys() | after_cells.keys()
                   if before_cells.get(key, [None])[0] != after_cells.get(key, [None])[0]]
        if changed:
            changes[left["file"]] = {key: after_cells.get(key, left_cells) for key in sorted(changed)
                                     for left_cells in [left["cells"].get(key, [])]}
            counts["changed_cells"] += len(changed)
            counts["changed_files"] += 1
    manifest_path.write_text(json.dumps({"counts": counts, "changes": changes},
                                        ensure_ascii=False) + "\n")
    print(dict(counts))


def values(code_root, manifest_path, output, roots):
    _initialize(code_root)
    manifest = json.loads(manifest_path.read_text())["changes"]
    lookup = dict(_paths(roots))
    with gzip.open(output, "wt", encoding="utf-8") as target:
        for name, changed in manifest.items():
            try:
                cells, errors = _document_cells(lookup[name], set(changed))
                row = {"file": name, "cells": cells, "errors": errors}
            except Exception as exc:
                row = {"file": name, "failure": type(exc).__name__}
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("changed files", len(manifest))


def summarize(manifest_path, before_path, after_path, output, roots):
    from dochan.ooxml.xlsx import XLSXReader
    from scripts.probe_chart_review_evidence import xls_cells
    from scripts.probe_spreadsheet_format_hashes import _format_code, _ooxml_cells, _kind

    manifest = json.loads(manifest_path.read_text())
    before = {row["file"]: row for row in _rows(before_path)}
    after = {row["file"]: row for row in _rows(after_path)}
    paths = dict(_paths(roots))
    counts = Counter(manifest["counts"])
    by_format = Counter()
    samples = []
    non_numeric_examples = []
    rng = random.Random(20261003)
    reader = XLSXReader()
    numeric = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
    for name, changed in manifest["changes"].items():
        raw = {}
        try:
            raw = xls_cells(Path(paths[name])) if name.endswith(".xls") else _ooxml_cells(Path(paths[name]))
        except Exception:
            counts["raw_metadata_unavailable_files"] += 1
        for key, metadata in changed.items():
            old = before[name].get("cells", {}).get(key, "")
            new = after[name].get("cells", {}).get(key, "")
            ref = ((metadata[2] or "") + "!" + (metadata[3] or "")
                   if len(metadata) > 3 and metadata[2] and metadata[3] else "")
            source = raw.get(ref)
            if source and source.get("type") == "b":
                kind = "boolean"
            elif source and source.get("type") in ("", "n") and source.get("raw") is not None:
                kind = "number"
            elif numeric.fullmatch(old) and numeric.fullmatch(new):
                kind = "number"
            elif old in ("0", "1") and new in ("TRUE", "FALSE"):
                kind = "boolean"
            else:
                kind = "string"
            counts[kind] += 1
            suffix = "xls" if name.endswith(".xls") else "xlsx"
            counts[suffix + "_" + kind] += 1
            if source:
                fmt = _format_code(source.get("format", ""))
                by_format[suffix + "/" + kind + "/" + _kind(fmt, reader)] += 1
            else:
                by_format[suffix + "/" + kind + "/unknown"] += 1
            if old and not new:
                counts["lost_text"] += 1
            if old and old in new and old != new:
                counts["decorated"] += 1
            if old != new and old.strip() == new.strip():
                counts["padding_only"] += 1
            if kind == "string" and old != new and old not in new:
                counts["string_replaced"] += 1
            item = {"file": name, "table_cell": key, "source_cell": ref,
                    "kind": kind, "before": old.split(" (=", 1)[0][:100],
                    "after": new.split(" (=", 1)[0][:100]}
            if kind != "number" and len(non_numeric_examples) < 50:
                non_numeric_examples.append(item)
            seen = counts["sampled_population"] = counts["sampled_population"] + 1
            if len(samples) < 30:
                samples.append(item)
            else:
                index = rng.randrange(seen)
                if index < 30:
                    samples[index] = item
    result = {"counts": dict(counts), "by_format": dict(by_format),
              "non_numeric_examples": non_numeric_examples, "sample": samples}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(dict(counts))
    print("by_format", dict(by_format))


def fraction(xls_path, text_path):
    from dochan.office_binary.xls import XLSReader
    doc = XLSReader().read(str(xls_path))
    cells = {cell.provenance.cell: cell.text for table in doc.find_all("table")
             for row in table.rows for cell in row
             if cell.provenance and cell.provenance.sheet == "Sheet1"}
    lines = text_path.read_text(encoding="utf-8").splitlines()
    counts = Counter()
    for row_number, line in enumerate(lines[1:355], start=2):
        columns = line.split("\t")
        for column_index, letter in enumerate("DEFGHIJKLM", start=3):
            shown = cells.get(letter + str(row_number), "").split(" (=", 1)[0]
            expected = columns[column_index]
            counts["total"] += 1
            counts["matched"] += "".join(shown.split()) == "".join(expected.split())
    counts["document_errors"] = len(doc.errors)
    print(dict(counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("dump")
    p.add_argument("code_root", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("roots", nargs="+", type=Path)
    p.add_argument("--workers", type=int, default=4)
    p = sub.add_parser("compare")
    for name in ("before", "after", "manifest"):
        p.add_argument(name, type=Path)
    p = sub.add_parser("values")
    for name in ("code_root", "manifest", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("roots", nargs="+", type=Path)
    p = sub.add_parser("summarize")
    for name in ("manifest", "before", "after", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("roots", nargs="+", type=Path)
    p = sub.add_parser("fraction")
    p.add_argument("xls_path", type=Path)
    p.add_argument("text_path", type=Path)
    args = parser.parse_args()
    if args.command == "dump":
        dump(args.code_root, args.output, args.roots, args.workers)
    elif args.command == "compare":
        compare(args.before, args.after, args.manifest)
    elif args.command == "values":
        values(args.code_root, args.manifest, args.output, args.roots)
    elif args.command == "fraction":
        fraction(args.xls_path, args.text_path)
    else:
        summarize(args.manifest, args.before, args.after, args.output, args.roots)


if __name__ == "__main__":
    main()
