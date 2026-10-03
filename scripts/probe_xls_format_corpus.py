"""공개 XLS의 Markdown 해시만 기록한다. 코퍼스 경로는 인자로 받는다."""
import argparse
import hashlib
import json
from pathlib import Path

from dochan import Dochan


def scan(roots, suffix="xls"):
    rows = {}
    for root in roots:
        root = Path(root)
        for path in sorted(root.rglob("*." + suffix)):
            key = root.name + "/" + str(path.relative_to(root))
            try:
                document = Dochan(str(path))
                markdown = document.to_markdown()
                rows[key] = {
                    "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    "characters": len(markdown),
                    "errors": [str(error)[:160] for error in document.doc.errors[:8]],
                }
            except Exception as error:
                rows[key] = {"failure": type(error).__name__}
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--suffix", choices=("xls", "xlsx"), default="xls")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = scan(args.roots, args.suffix)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print("files=%d failures=%d" % (len(rows), sum("failure" in row for row in rows.values())))


if __name__ == "__main__":
    main()
