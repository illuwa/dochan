"""Record compact Markdown hashes for public XLS corpora without saving output."""
import argparse
import hashlib
import json
from pathlib import Path

from dochan import Dochan
from dochan.model.table import Table


def _features(doc):
    grids = []
    content = hashlib.sha256()
    properties = []
    names = []
    for section in doc.sections:
        sheet_name = getattr(section.provenance, "sheet", "")
        for element in section.elements:
            if isinstance(element, Table):
                grids.append((sheet_name, element.row_count, element.col_count))
                for row in element.rows:
                    for cell in row:
                        if cell.text:
                            content.update(repr((sheet_name, cell.row, cell.col, cell.text)).encode("utf-8"))
            elif getattr(element, "text", ""):
                source = getattr(getattr(element, "provenance", None), "path", "")
                if source == "\x05SummaryInformation":
                    properties.append(element.text)
                elif element.text.startswith("Defined name: "):
                    names.append(element.text)
    return {"grids": grids, "content_sha256": content.hexdigest(),
            "properties": properties, "names": names}


def scan(directories):
    results = {}
    for directory in directories:
        root = Path(directory)
        for path in sorted(root.rglob("*.xls")):
            key = "%s/%s" % (root.name, path.relative_to(root))
            try:
                reader = Dochan(str(path))
                markdown = reader.to_markdown()
                results[key] = {
                    "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    "chars": len(markdown),
                    "errors": list(reader.doc.errors),
                    "features": _features(reader.doc),
                }
            except Exception as exc:
                results[key] = {"exception": "%s: %s" % (type(exc).__name__, exc)}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results = scan(args.directories)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
    print("XLS files: %d" % len(results))


if __name__ == "__main__":
    main()
