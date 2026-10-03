"""PDF 각주 변경 전후의 Markdown 해시와 각주 수를 작은 JSON으로 측정한다.

입력 코퍼스는 읽기만 한다. --private는 내부 표본 이름을 결과에 남기지 않는다.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def measure(path):
    from dochan import Dochan

    converted = Dochan(str(path))
    markdown = converted.to_markdown()
    notes = converted.doc.find_all("footnote")
    return {"sha256": hashlib.sha256(markdown.encode("utf-8", "surrogatepass")).hexdigest(),
            "characters": len(markdown), "footnotes": len(notes),
            "note_pages": [note.paragraphs[0].provenance.page for note in notes],
            "errors": sum(error.startswith("ERR") for error in converted.errors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(measure(args.corpus), ensure_ascii=False))
        except BaseException as exc:
            # 예외 문자열에는 내부 문서 이름이나 내용이 있을 수 있다.
            print(json.dumps({"failure": type(exc).__name__}))
        return

    files = sorted(args.corpus.glob("*.pdf"))
    rows = {}
    if args.output.exists():
        rows = json.loads(args.output.read_text(encoding="utf-8"))["rows"]

    def worker(index_path):
        index, path = index_path
        key = str(index) if args.private else path.name
        if key in rows:
            return key, rows[key]
        try:
            # nosemgrep: dangerous-subprocess-use-audit
            result = subprocess.run([sys.executable, "-m", "scripts.probe_pdf_note_body",
                                     str(path), str(args.output), "--worker"],
                                    capture_output=True, timeout=180, check=False)
            if result.returncode:
                return key, {"failure": "exit_%d" % result.returncode}
            return key, json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            return key, {"failure": "timeout"}
        except (OSError, ValueError):
            return key, {"failure": "probe_error"}

    with ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 8))) as pool:
        for key, row in pool.map(worker, enumerate(files)):
            rows[key] = row
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    summary = {"documents": len(files),
               "measured": sum("failure" not in row for row in rows.values()),
               "footnotes": sum(row.get("footnotes", 0) for row in rows.values())}
    args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False),
                           encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
