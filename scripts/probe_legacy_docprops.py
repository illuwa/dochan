"""Hash public legacy Office Markdown without storing document output.

Usage: python -m scripts.probe_legacy_docprops ROOT [ROOT ...] --output FILE
"""
import argparse
import hashlib
import json
from pathlib import Path

from dochan import Dochan
from dochan.output.markdown import to_markdown


EXTENSIONS = {".doc", ".ppt", ".xls"}


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot(path, include_json=False):
    converted = Dochan(str(path))
    doc = converted.doc
    markdown = converted.to_markdown()
    json_digest = _digest(converted.to_json()) if include_json else None
    metadata = []
    metadata_positions = []
    header_positions = []
    if doc.sections:
        elements = doc.sections[0].elements
        for index, element in enumerate(elements):
            if getattr(getattr(element, "provenance", None), "path", "") == "\x05SummaryInformation":
                metadata.append(element.text)
                metadata_positions.append(index)
            elif type(element).__name__ == "HeaderFooter" and element.type == "header":
                header_positions.append(index)
        for index in reversed(metadata_positions):
            elements.pop(index)
    body = to_markdown(doc) if metadata else markdown
    result = {"markdown_sha256": _digest(markdown), "body_sha256": _digest(body),
              "characters": len(markdown), "metadata": metadata,
              "metadata_positions": metadata_positions, "header_positions": header_positions,
              "errors": doc.errors}
    if include_json:
        result["json_sha256"] = json_digest
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--extension", action="append", choices=("doc", "ppt", "xls"),
                        help="Limit the scan to one or more legacy extensions")
    parser.add_argument("--json", action="store_true", help="Also hash the complete JSON output")
    args = parser.parse_args()
    extensions = {"." + ext for ext in args.extension} if args.extension else EXTENSIONS
    results = {}
    for root in args.roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions:
                key = "%s/%s" % (root.name, path.relative_to(root))
                try:
                    results[key] = snapshot(path, args.json)
                except Exception as exc:
                    results[key] = {"exception": type(exc).__name__ + ": " + str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("files=%d exceptions=%d" % (
        len(results), sum("exception" in row for row in results.values())))


if __name__ == "__main__":
    main()
