"""Record HWPX Markdown hashes and paragraph counts without persisting document output.

Usage: python -m scripts.probe_hwpx_picture_flow --output result.json ROOT [ROOT ...]
       python -m scripts.probe_hwpx_picture_flow --output result.json --reference before.json ROOT [ROOT ...]
"""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from dochan import Dochan
from dochan.model.document import Paragraph
from dochan.utils import safe_xml


def _paths(roots):
    for index, root in enumerate(roots):
        root = Path(root)
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() == ".hwpx":
                yield "%d/%s" % (index, path.relative_to(root)), path


def _has_paragraph_picture(path):
    """Check section XML independently of Markdown output, within XML size limits."""
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("Contents/section") or not name.endswith(".xml"):
                continue
            info = archive.getinfo(name)
            if info.file_size > 64 * 1024 * 1024:
                continue
            root = safe_xml.fromstring(archive.read(name), max_bytes=64 * 1024 * 1024)
            paragraph = "{http://www.hancom.co.kr/hwpml/2011/paragraph}p"
            picture = "{http://www.hancom.co.kr/hwpml/2011/paragraph}pic"
            for para in root.iter(paragraph):
                if any(True for _ in para.iter(picture)):
                    return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference")
    parser.add_argument("roots", nargs="+")
    args = parser.parse_args()
    reference = None
    if args.reference:
        with open(args.reference, encoding="utf-8") as handle:
            reference = json.load(handle)["files"]

    rows = {}
    changed = []
    classified = []
    for key, path in _paths(args.roots):
        try:
            reader = Dochan(str(path), include_assets=False)
            markdown = reader.to_markdown()
            row = {
                "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                "characters": len(markdown),
                "paragraphs": sum(isinstance(item, Paragraph)
                                  for section in reader.doc.sections for item in section.elements),
                "errors": len(reader.errors),
            }
        except Exception as exc:
            row = {"error": type(exc).__name__}
        rows[key] = row
        if reference is not None and row != reference.get(key):
            changed.append(key)
            try:
                if _has_paragraph_picture(path):
                    classified.append(key)
            except (OSError, ValueError, zipfile.BadZipFile, safe_xml.XMLSyntaxError):
                pass

    result = {"files": rows, "summary": {"scanned": len(rows),
              "errors": sum("error" in row for row in rows.values()),
              "changed": changed, "changed_with_paragraph_picture": classified}}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"scanned": len(rows),
                      "errors": result["summary"]["errors"],
                      "changed": len(changed),
                      "changed_with_paragraph_picture": len(classified)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
