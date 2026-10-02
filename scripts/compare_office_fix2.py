"""공개 Office 목록을 지정한 소스 트리로 변환하여 회귀 지표를 기록한다.

목록에는 읽기 전용 공개 코퍼스 경로를 한 줄에 하나씩 넣는다. 원본 파일은
복사하지 않으며, 파일별 시간 제한과 독립 프로세스로 손상 입력을 격리한다.
"""
import argparse
from collections import Counter
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import signal
import sys
import time


def _timeout(signum, frame):
    raise TimeoutError("document time limit exceeded")


def _probe(task):
    path, source_root, output, timeout = task
    sys.path.insert(0, source_root)
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(timeout)
    started = time.monotonic()
    row = {"path": path, "format": Path(path).suffix.lower()[1:]}
    try:
        from dochan import Dochan
        from dochan.model.document import Paragraph
        from dochan.model.image import Image
        from scripts.compare_office_pairs import _walk

        parsed = Dochan(path)
        markdown = parsed.to_markdown()
        nodes = list(_walk(parsed.doc))
        paragraphs = [node for node in nodes if isinstance(node, Paragraph)]
        images = [node for node in nodes if isinstance(node, Image)]
        text = "\n".join(p.text for p in paragraphs)
        runs = [run for p in paragraphs for run in p.runs]
        links = []
        for paragraph in paragraphs:
            explicit = [run.link for run in paragraph.runs if run.link]
            # Legacy PPT's established contract appends display <target>.
            suffixes = re.findall(r" <([^<>\n]+)>", paragraph.text)
            links.extend(explicit)
            links.extend(target for target in suffixes if target not in explicit)
        row.update({
            "errors": list(parsed.errors),
            "fatal": any(str(error).startswith("ERR:") for error in parsed.errors),
            "characters": len(text), "paragraphs": len(paragraphs),
            "images": len(images), "linked_runs": sum(bool(r.link) for r in runs),
            "hyperlink_references": len(links),
            "internal_links": sum(target.startswith("#") or target.startswith("PowerPoint Document#slide")
                                  for target in links),
            "image_references": len(re.findall(r"!\[[^\]]*\]\(", markdown)),
            "markdown_characters": len(markdown),
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "words": dict(Counter(re.findall(r"\w+", text))),
        })
    except Exception as exc:
        row.update({"fatal": True, "exception": "%s: %s" % (type(exc).__name__, exc)})
    finally:
        signal.alarm(0)
    row["seconds"] = round(time.monotonic() - started, 3)
    key = hashlib.sha256(path.encode("utf-8")).hexdigest()[:24]
    (Path(output) / (key + ".json")).write_text(json.dumps(row, ensure_ascii=True), encoding="utf-8")
    return row


def compare(before, after):
    """동일 목록의 전후 결과를 비교한다. 텍스트 감소는 판정 대신 후보로 남긴다."""
    old = {row["path"]: row for row in before["documents"]}
    new = {row["path"]: row for row in after["documents"]}
    if old.keys() != new.keys():
        raise ValueError("baseline and current document sets differ")
    changes = []
    for path in sorted(old):
        a, b = old[path], new[path]
        lost = Counter(a.get("words", {})) - Counter(b.get("words", {}))
        row = {"path": path, "format": b["format"],
               "new_fatal": b["fatal"] and not a["fatal"],
               "fixed_fatal": a["fatal"] and not b["fatal"],
               "markdown_changed": a.get("markdown_sha256") != b.get("markdown_sha256"),
               "text_changed": a.get("text_sha256") != b.get("text_sha256"),
               "lost_words": dict(lost), "lost_word_count": sum(lost.values()),
               "deltas": {key: b.get(key, 0) - a.get(key, 0) for key in
                          ("characters", "images", "image_references", "linked_runs", "internal_links")}}
        if any(row[key] for key in ("new_fatal", "fixed_fatal", "markdown_changed", "text_changed")):
            changes.append(row)
    summary = {}
    for fmt in sorted({row["format"] for row in new.values()}):
        selected = [row for row in changes if row["format"] == fmt]
        summary[fmt] = {
            "documents": sum(row["format"] == fmt for row in new.values()),
            "baseline_fatal": sum(row["fatal"] for row in old.values() if row["format"] == fmt),
            "current_fatal": sum(row["fatal"] for row in new.values() if row["format"] == fmt),
            "new_fatal": sum(row["new_fatal"] for row in selected),
            "fixed_fatal": sum(row["fixed_fatal"] for row in selected),
            "markdown_changed": sum(row["markdown_changed"] for row in selected),
            "word_loss_candidates": sum(bool(row["lost_words"]) for row in selected),
        }
    return {"summary": summary, "changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--lists", required=True, type=Path, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--baseline", type=Path, help="비교할 이전 results.json 경로")
    args = parser.parse_args()
    paths = sorted({line.strip() for listing in args.lists
                    for line in listing.read_text().splitlines() if line.strip()})
    args.output.mkdir(parents=True, exist_ok=True)
    tasks = [(path, str(args.source_root.resolve()), str(args.output.resolve()), args.timeout)
             for path in paths]
    rows = []
    # Spawn gives each worker a clean module cache for the selected source tree.
    with multiprocessing.get_context("spawn").Pool(args.workers, maxtasksperchild=1) as pool:
        for row in pool.imap_unordered(_probe, tasks, chunksize=1):
            rows.append(row)
    rows.sort(key=lambda row: row["path"])
    summary = {"documents": len(rows), "formats": dict(Counter(r["format"] for r in rows)),
               "fatal": sum(r["fatal"] for r in rows),
               "exceptions": sum("exception" in r for r in rows)}
    result = {"source_root": str(args.source_root.resolve()), "summary": summary, "documents": rows}
    (args.output / "results.json").write_text(json.dumps(result, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(summary))
    if args.baseline:
        comparison = compare(json.loads(args.baseline.read_text()), result)
        (args.output / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(comparison["summary"]))


if __name__ == "__main__":
    main()
