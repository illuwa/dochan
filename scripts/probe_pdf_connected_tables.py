"""연결형 후보 발화와 출력 회귀를 익명 수치로 측정한다.

코퍼스 경로는 인자로 받는다. 내부 쌍은 파일명·본문·예외 문자열을 저장하지
않는다. --apply는 측정 프로세스에서만 후보 분리를 시험하는 옵션이다.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys


def nested_identities(document):
    """서명과 셀 위치별 텍스트를 함께 비교한다. 반환값은 파일에 기록하지 않는다."""
    from dochan.model.table import Table
    from scripts.compare_pdf_pairs import normalize_text, table_signature, MAX_NESTING_DEPTH

    result = Counter()

    def walk(blocks, depth):
        if depth > MAX_NESTING_DEPTH:
            return
        for block in blocks:
            if not isinstance(block, Table):
                continue
            if depth:
                key = (table_signature(block), tuple(
                    (r, c, cell.row_span, cell.col_span, normalize_text(cell.text))
                    for r, row in enumerate(block.rows) for c, cell in enumerate(row)
                    if not cell.is_merged_away))
                result[key] += 1
            for row in block.rows:
                for cell in row:
                    walk(cell.paragraphs, depth + 1)

    for section in document.sections:
        walk(section.elements, 0)
    return result


def measure(repo, path, mode, apply=False):
    sys.path.insert(0, str(repo))
    from dochan.pdf import tables, reader
    from dochan.pdf.connected_tables import split_connected
    from scripts.compare_pdf_fix2 import worker

    original = tables.split_connected
    original_build = reader.build_tables
    counts = {"connected_candidates": 0, "connected_pages": 0}

    def observe(hs, vs, tolerance, index, **kwargs):
        result = split_connected(hs, vs, tolerance, index, **kwargs)
        counts["connected_candidates"] += len(result) - 1
        return result if apply else [(hs, vs)]

    def build(segments, fragments, *args, **kwargs):
        before = counts["connected_candidates"]
        result = original_build(segments, fragments, *args, **kwargs)
        counts["connected_pages"] += counts["connected_candidates"] > before
        return result

    tables.split_connected = observe
    reader.build_tables = build
    try:
        row = worker(repo, path, mode)
    finally:
        tables.split_connected = original
        reader.build_tables = original_build
    if mode == 'pairs' and counts['connected_candidates']:
        from dochan import Dochan

        answer = nested_identities(Dochan(str(path.with_suffix('.hwpx'))).doc)
        after = nested_identities(Dochan(str(path)).doc)
        tables.split_connected = lambda h, v, *_args, **_kwargs: [(h, v)]
        try:
            before = nested_identities(Dochan(str(path)).doc)
        finally:
            tables.split_connected = original
        counts['new_nested_tables'] = sum((after - before).values())
        counts['new_nested_exact_text_and_structure'] = sum(((after - before) & answer).values())
        counts['lost_nested_tables'] = sum((before - after).values())
    return dict(row, **counts)


def summarize(rows, mode):
    good = [row for row in rows.values() if "connected_candidates" in row]
    negatives = [row for row in good if row.get("hwpx_nested") == 0]
    result = {"files": len(rows), "completed": len(good), "failed": len(rows) - len(good),
              "candidate_documents": sum(row["connected_candidates"] > 0 for row in good),
              "candidates": sum(row["connected_candidates"] for row in good)}
    if mode == "pairs":
        from scripts.compare_pdf_pairs import summarize as pair_summary

        result.update(pair_summary(rows))
        result.update(negative_documents=len(negatives),
                      negative_fired_documents=sum(row["connected_candidates"] > 0 for row in negatives),
                      negative_candidates=sum(row["connected_candidates"] for row in negatives))
        for key in ('new_nested_tables', 'new_nested_exact_text_and_structure', 'lost_nested_tables'):
            result[key] = sum(row.get(key, 0) for row in good)
    else:
        result["documents_with_tables"] = sum(row.get("tables", 0) > 0 for row in good)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("corpus", "pairs"), default="corpus")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.worker:
        try:
            result = measure(repo, args.corpus, args.mode, args.apply)
        except BaseException as exc:
            result = {"exception_type": type(exc).__name__}
        print(json.dumps(result))
        return
    if not 1 <= args.jobs <= 16 or args.timeout <= 0:
        parser.error("jobs must be 1..16; timeout must be positive")
    paths = sorted(args.corpus.glob("*.pdf"))
    if args.mode == "pairs":
        paths = [p for p in paths if p.with_suffix(".hwpx").exists()]
    if not paths:
        parser.error("no PDF inputs")

    def run(item):
        index, path = item
        command = [sys.executable, str(Path(__file__).resolve()), str(path.resolve()),
                   str(args.output.resolve()), "--mode", args.mode, "--worker"]
        if args.apply:
            command.append("--apply")
        try:
            process = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
                command, capture_output=True, timeout=args.timeout, check=False)
            row = (json.loads(process.stdout) if process.returncode == 0
                   else {"returncode": process.returncode})
        except subprocess.TimeoutExpired:
            row = {"timeout": args.timeout}
        except (ValueError, OSError) as exc:
            row = {"exception_type": type(exc).__name__}
        return (str(index) if args.mode == "pairs" else path.name), row

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for key, row in pool.map(run, enumerate(paths)):
            rows[key] = row
            if len(rows) % 100 == 0:
                print("completed {} / {}".format(len(rows), len(paths)), file=sys.stderr, flush=True)
    result = {"summary": summarize(rows, args.mode), "apply": args.apply, "rows": rows}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return int(result["summary"]["failed"] > 0)


if __name__ == "__main__":
    sys.exit(main())
