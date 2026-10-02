"""PDF 수정 전후의 공개 코퍼스와 비공개 문서 쌍을 비교하는 측정 도구다.

공개 코퍼스는 Markdown 지표를 저장한다. 비공개 쌍은 이름과 본문을
저장하지 않으며 compare_pdf_pairs의 수치 지표와 경고 개수만 저장한다.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys


def worker(repo, path, mode, text_tables=False):
    sys.path.insert(0, str(repo))
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        if mode == "pairs":
            from scripts.compare_pdf_pairs import compare_pair
            from dochan.pdf import reader

            detected = [0]
            original = getattr(reader, "detect_endnotes", None)
            if original is not None:
                def observe(drafts, dropped, first_number=1, warnings=None):
                    result = original(drafts, dropped, first_number, warnings)
                    detected[0] += result - first_number
                    return result

                reader.detect_endnotes = observe

            row = compare_pair(str(path.with_suffix(".hwpx")), str(path))
            numeric = {key: value for key, value in row.items()
                       if value is None or isinstance(value, (int, float, bool))}
            numeric["detected_endnotes"] = detected[0]
            return numeric
        from dochan import Dochan

        document = Dochan(str(path), pdf_text_tables=text_tables)
        markdown = document.to_markdown()
        plain = document.to_plain_text()
        json_output = document.to_json()
        return {
            "markdown_length": len(markdown),
            "plain_length": len(plain),
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8", "surrogatepass")).hexdigest(),
            "json_sha256": hashlib.sha256(json_output.encode("utf-8", "surrogatepass")).hexdigest(),
            "replacement_characters": markdown.count("\ufffd"),
            "plain_replacement_characters": plain.count("\ufffd"),
            "errors": sum(message.startswith("ERR") for message in document.errors),
            "warnings": sum(message.startswith("WARN") for message in document.errors),
            "sections": len(document.doc.sections),
            "tables": len(document.doc.find_all("table")),
            "detected_endnotes": len(document.doc.find_all("endnote")),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("corpus", "pairs"), default="corpus")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--text-tables", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            row = worker(args.repo, args.corpus, args.mode, args.text_tables)
        except BaseException as exc:
            # 예외 문자열에는 비공개 파일명이나 본문이 있을 수 있다.
            row = {"exception_type": type(exc).__name__}
        print(json.dumps(row, ensure_ascii=False))
        return
    files = sorted(args.corpus.glob("*.pdf"))
    if args.mode == "pairs":
        files = [path for path in files if path.with_suffix(".hwpx").exists()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if args.output.exists():
        rows = json.loads(args.output.read_text())["rows"]

    def measure(item):
        index, path = item
        key = path.name if args.mode == "corpus" else str(index)
        if key in rows and "detected_endnotes" in rows[key]:
            return key, rows[key]
        command = [sys.executable, str(Path(__file__).resolve()),
                   str(args.repo.resolve()), str(path.resolve()), str(args.output.resolve()),
                   "--mode", args.mode, "--worker"]
        if args.text_tables:
            command.append("--text-tables")
        try:
            # nosemgrep: dangerous-subprocess-use-audit
            result = subprocess.run(command, capture_output=True, timeout=args.timeout, check=False)
            if result.returncode:
                return key, {"returncode": result.returncode}
            return key, json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            return key, {"timeout": args.timeout}
        except (ValueError, OSError) as exc:
            return key, {"exception_type": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 16))) as pool:
        for key, row in pool.map(measure, enumerate(files)):
            rows[key] = row
            args.output.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2))
    completed = [row for row in rows.values() if "exception_type" not in row
                 and "timeout" not in row and "returncode" not in row]
    summary = {"files": len(files), "completed": len(completed), "failed": len(rows) - len(completed)}
    summary["detected_endnotes"] = sum(row.get("detected_endnotes", 0) for row in completed)
    if args.mode == "pairs":
        sys.path.insert(0, str(args.repo.resolve()))
        from scripts.compare_pdf_pairs import summarize

        summary.update(summarize(rows))
    else:
        for key in ("markdown_length", "plain_length", "replacement_characters",
                    "plain_replacement_characters", "errors", "warnings", "sections", "tables"):
            summary[key] = sum(row.get(key, 0) for row in completed)
        for key in ("errors", "warnings", "replacement_characters"):
            summary["files_with_" + key] = sum(row.get(key, 0) > 0 for row in completed)
        summary["empty_markdown"] = sum(row["markdown_length"] == 0 for row in completed)
    args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
