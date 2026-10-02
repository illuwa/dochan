"""공개 HWP/HWPX 코퍼스의 재귀 제목 수와 기준 대비 변화를 측정한다.

실행 예:
  python scripts/probe_hwp_heading_changes.py scan CORPUS --output scan.json
  python scripts/probe_hwp_heading_changes.py scan CORPUS --source-root SNAPSHOT \
      --label 3bcfc21 --output baseline.json
  python scripts/probe_hwp_heading_changes.py diff baseline.json scan.json \
      --output changes.json

공개 코퍼스 전용이다. 파일명과 제목을 저장하므로 내부 문서에는 실행하지 않는다.
표 셀, 표/그림 캡션, 머리말/꼬리말, 각주/미주를 재귀 탐색한다.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def heading_inventory(doc):
    """객체 참조를 중복 집계하지 않고 모든 문단의 안정 경로를 조사한다."""
    headings = []
    paragraph_count = 0
    seen = set()
    stack = [(section, "sections[{}]".format(index))
             for index, section in reversed(list(enumerate(doc.sections)))]
    while stack:
        element, path = stack.pop()
        if id(element) in seen:
            continue
        seen.add(id(element))
        if hasattr(element, "heading_level"):
            paragraph_count += 1
            if element.heading_level:
                entry = {
                    "path": path,
                    "level": element.heading_level,
                    "text": element.text,
                    "inside_cell": ".rows[" in path,
                }
                headings.append(entry)
        children = []
        for index, row in enumerate(getattr(element, "rows", [])):
            for column, cell in enumerate(row):
                children.append((cell, "{}.rows[{}][{}]".format(path, index, column)))
        for field in ("elements", "paragraphs", "caption"):
            for index, child in enumerate(getattr(element, field, [])):
                children.append((child, "{}.{}[{}]".format(path, field, index)))
        stack.extend(reversed(children))
    return paragraph_count, headings


def summarize(files):
    groups = {}
    for row in files:
        for key in ("all", "extension:" + row["extension"],
                    "source_format:" + (row["source_format"] or "unknown")):
            group = groups.setdefault(key, Counter())
            group["files"] += 1
            group["headings"] += len(row["headings"])
            group["cell_headings"] += sum(h["inside_cell"] for h in row["headings"])
            group["paragraphs"] += row["paragraphs"]
            group["files_with_errors"] += bool(row["errors"])
            group["errors"] += len(row["errors"])
            group["fatal_errors"] += sum(e.startswith("ERR") for e in row["errors"])
            group["warnings"] += sum(e.startswith("WARN") for e in row["errors"])
            group["exceptions"] += bool(row.get("exception"))
            for heading in row["headings"]:
                group["h{}".format(heading["level"])] += 1
    return {key: dict(value) for key, value in sorted(groups.items())}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_document(args):
    """공개 HWP 표본의 제목 판정 입력을 문단/스타일 모양과 대조한다."""
    sys.path.insert(0, str(args.source_root.resolve()))
    from dochan import Dochan

    doc = Dochan(str(args.file)).doc
    if doc.source_format != "hwp":
        raise ValueError("inspect는 HWP 전용입니다. HWPX의 참조 ID는 원본 XML에서 확인하세요.")
    _, headings = heading_inventory(doc)
    import re

    for heading in headings:
        paragraph = doc
        for field, index, column in re.findall(r"(\w+)\[(\d+)\](?:\[(\d+)\])?", heading["path"]):
            paragraph = getattr(paragraph, field)[int(index)]
            if column:
                paragraph = paragraph[int(column)]
        basis = {"para_shape_id": paragraph.para_shape_id, "style_id": paragraph.style_id,
                 "font_sizes_pt": [run.font_size_pt for run in paragraph.runs]}
        shape_id = paragraph.para_shape_id
        if 0 <= shape_id < len(doc.para_shapes):
            shape = doc.para_shapes[shape_id]
            basis["direct_heading_type"] = shape.heading_type
            basis["direct_heading_level_zero_based"] = getattr(shape, "heading_level", None)
        if 0 <= paragraph.style_id < len(doc.styles):
            style = doc.styles[paragraph.style_id]
            basis["style_name"] = style.name
            basis["style_para_shape_id"] = style.para_shape_id
            if 0 <= style.para_shape_id < len(doc.para_shapes):
                shape = doc.para_shapes[style.para_shape_id]
                basis["style_heading_type"] = shape.heading_type
                basis["style_heading_level_zero_based"] = getattr(shape, "heading_level", None)
        heading["basis"] = basis
    return {"file": args.file.name, "source_format": doc.source_format,
            "summary": {"headings": len(headings), "errors": len(doc.errors)},
            "headings": headings, "errors": list(doc.errors)}


def scan(args):
    source_root = args.source_root.resolve()
    if not (source_root / "dochan" / "__init__.py").is_file():
        raise ValueError("--source-root에 dochan 패키지가 없습니다")
    sys.path.insert(0, str(source_root))
    from dochan import Dochan

    corpus = args.corpus.resolve()
    paths = sorted(path for path in corpus.rglob("*")
                   if path.is_file() and path.suffix.lower() in (".hwp", ".hwpx"))
    if not paths:
        raise ValueError("HWP/HWPX 표본이 없습니다")
    files = []
    for index, path in enumerate(paths, 1):
        row = {"file": str(path.relative_to(corpus)), "extension": path.suffix.lower(),
               "sha256": sha256_file(path), "source_format": "", "paragraphs": 0,
               "headings": [], "errors": []}
        try:
            doc = Dochan(str(path)).doc
            row["source_format"] = doc.source_format
            row["errors"] = list(doc.errors)
            row["paragraphs"], row["headings"] = heading_inventory(doc)
        except Exception as exc:
            row["exception"] = repr(exc)
        files.append(row)
        if index % 100 == 0:
            print("{}/{}".format(index, len(paths)), file=sys.stderr, flush=True)
    source_hashes = {str(path.relative_to(source_root)): sha256_file(path)
                     for path in sorted((source_root / "dochan").rglob("*.py"))}
    return {"label": args.label, "source_hashes": source_hashes,
            "summary": summarize(files), "files": files}


def compare(args):
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    old_files = {row["file"]: row for row in before["files"]}
    new_files = {row["file"]: row for row in after["files"]}
    if old_files.keys() != new_files.keys():
        raise ValueError("측정 대상 파일 목록이 다릅니다")
    changes = []
    totals = Counter()
    for filename, old in old_files.items():
        new = new_files[filename]
        if old["sha256"] != new["sha256"]:
            raise ValueError("측정 사이 표본 바이트가 바뀌었습니다: " + filename)
        old_heads = {heading["path"]: heading for heading in old["headings"]}
        new_heads = {heading["path"]: heading for heading in new["headings"]}
        removed = [old_heads[path] for path in sorted(old_heads.keys() - new_heads.keys())]
        added = [new_heads[path] for path in sorted(new_heads.keys() - old_heads.keys())]
        modified = [{"before": old_heads[path], "after": new_heads[path]}
                    for path in sorted(old_heads.keys() & new_heads.keys())
                    if old_heads[path] != new_heads[path]]
        errors_changed = old["errors"] != new["errors"]
        structure_changed = old["paragraphs"] != new["paragraphs"]
        format_changed = old["source_format"] != new["source_format"]
        exception_changed = old.get("exception") != new.get("exception")
        totals["files"] += 1
        totals["heading_changed_files"] += bool(removed or added or modified)
        totals["removed"] += len(removed)
        totals["added"] += len(added)
        totals["modified"] += len(modified)
        totals["errors_changed_files"] += errors_changed
        totals["paragraph_count_changed_files"] += structure_changed
        totals["format_changed_files"] += format_changed
        totals["exception_changed_files"] += exception_changed
        if removed or added or modified or errors_changed or structure_changed or format_changed or exception_changed:
            changes.append({
                "file": filename, "extension": new["extension"],
                "source_format": new["source_format"], "removed": removed,
                "added": added, "modified": modified,
                "before_headings": len(old_heads), "after_headings": len(new_heads),
                "before_paragraphs": old["paragraphs"], "after_paragraphs": new["paragraphs"],
                "before_errors": old["errors"], "after_errors": new["errors"],
                "before_exception": old.get("exception"), "after_exception": new.get("exception"),
            })
    return {"before_label": before["label"], "after_label": after["label"],
            "before_summary": before["summary"], "after_summary": after["summary"],
            "summary": dict(totals), "changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scanner = commands.add_parser("scan")
    scanner.add_argument("corpus", type=Path)
    scanner.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    scanner.add_argument("--label", default="working-tree")
    scanner.add_argument("--output", type=Path, required=True)
    differ = commands.add_parser("diff")
    differ.add_argument("before", type=Path)
    differ.add_argument("after", type=Path)
    differ.add_argument("--output", type=Path, required=True)
    inspector = commands.add_parser("inspect")
    inspector.add_argument("file", type=Path)
    inspector.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    inspector.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commands = {"scan": scan, "diff": compare, "inspect": inspect_document}
    result = commands[args.command](args)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
