"""공개 XLS의 Markdown 해시와 메모를 파일별 격리해 요약한다."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def inspect(path):
    from dochan import Dochan
    from dochan.output.markdown import to_markdown

    doc = Dochan(str(path)).doc
    markdown = to_markdown(doc)
    comments = re.findall(r"\[comment: (.*?)\]", markdown, re.DOTALL)
    return {
        "file": path.name,
        "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "characters": len(markdown),
        "comment_count": len(comments),
        "comments": comments[:100],
        "errors": doc.errors[:100],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--one", action="store_true")
    args = parser.parse_args()
    if args.one:
        try:
            result = inspect(args.corpus)
        except Exception as exc:
            result = {"file": args.corpus.name, "exception": type(exc).__name__ + ": " + str(exc)}
        print(json.dumps(result, ensure_ascii=False))
        return
    rows = []
    for index, path in enumerate(sorted(args.corpus.rglob("*.xls")), 1):
        command = [sys.executable, "-m", "scripts.probe_xls_notes", str(path), "--one"]
        try:
            run = subprocess.run(command, capture_output=True, text=True, timeout=60)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
            row = json.loads(run.stdout) if run.returncode == 0 else {
                "file": path.name, "process_exit": run.returncode, "stderr": run.stderr[-300:]}
        except (subprocess.TimeoutExpired, ValueError) as exc:
            row = {"file": path.name, "exception": type(exc).__name__}
        row["relative"] = str(path.relative_to(args.corpus))
        rows.append(row)
        if index % 50 == 0:
            print("%d files" % index, flush=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"files": len(rows), "comments": sum(r.get("comment_count", 0) for r in rows),
                      "failures": sum("sha256" not in r for r in rows)}))


if __name__ == "__main__":
    main()
