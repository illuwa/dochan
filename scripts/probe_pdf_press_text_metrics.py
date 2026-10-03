"""공개 보도자료 PDF의 각주·링크 요소 수만 기록하는 회귀 프로브."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys


EXCLUDED = {"156783589", "156784075", "156783622"}


def worker(repo, pdf_path):
    sys.path.insert(0, str(repo))
    from dochan import Dochan

    result = Dochan(str(pdf_path))
    return {
        "footnotes": len(result.doc.find_all("footnote")),
        "endnotes": len(result.doc.find_all("endnote")),
        "linked_runs": sum(bool(run.link) for paragraph in result.doc.find_all("paragraph")
                           for run in paragraph.runs),
        "errors": sum(message.startswith("ERR") for message in result.errors),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        try:
            row = worker(args.repo.resolve(), args.corpus.resolve())
        except Exception as exc:
            row = {"error_type": type(exc).__name__}
        print(json.dumps(row))
        return
    files = sorted(path for path in args.corpus.glob("*.pdf")
                   if path.stem not in EXCLUDED and
                   path.with_suffix(".hwpx").is_file())
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def measure(item):
        index, path = item
        command = [sys.executable, str(Path(__file__).resolve()), str(args.repo.resolve()),
                   str(path.resolve()), str(args.output.resolve()), "--worker"]
        try:
            # nosemgrep: dangerous-subprocess-use-audit
            completed = subprocess.run(command, capture_output=True, check=False, timeout=180)
            row = json.loads(completed.stdout) if completed.returncode == 0 else {
                "returncode": completed.returncode}
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            row = {"error_type": type(exc).__name__}
        return path.stem, row

    with ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 8))) as pool:
        rows = dict(pool.map(measure, enumerate(files)))
    summary = {"files": len(files), "failed": sum("error_type" in row or "returncode" in row
                                                    for row in rows.values())}
    for key in ("footnotes", "endnotes", "linked_runs", "errors"):
        summary[key] = sum(row.get(key, 0) for row in rows.values())
    args.output.write_text(json.dumps({"summary": summary, "rows": rows},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
