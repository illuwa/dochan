"""Hash chart table values from public OOXML files without storing document output."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def snapshot(corpus: Path, tree: Path):
    sys.path.insert(0, str(tree.resolve()))
    from dochan import Dochan

    records = {}
    for root in (corpus / "poi-src/test-data", corpus / "lo-src"):
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in (".pptx", ".xlsx", ".docx"):
                continue
            try:
                with zipfile.ZipFile(path) as archive:
                    if not any("chart" in name.lower() and name.endswith(".xml")
                               for name in archive.namelist()):
                        continue
                doc = Dochan(str(path))
                chart_rows = []
                for table in doc.doc.find_all("table"):
                    if not any("chart" in (getattr(paragraph.provenance, "path", "") or "").lower()
                               for paragraph in table.caption):
                        continue
                    chart_rows.append([[cell.text for cell in row] for row in table.rows])
                data = json.dumps(chart_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
                records[str(path.relative_to(corpus))] = {
                    "charts": len(chart_rows), "sha256": hashlib.sha256(data).hexdigest(),
                    "characters": len(data), "errors": list(doc.errors),
                }
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                records[str(path.relative_to(corpus))] = {"exception": type(error).__name__}
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = snapshot(args.corpus, args.tree)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    print("files=%d charts=%d exceptions=%d" % (
        len(result), sum(row.get("charts", 0) for row in result.values()),
        sum("exception" in row for row in result.values())))


if __name__ == "__main__":
    main()
