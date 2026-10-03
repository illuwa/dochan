"""공개 보도자료 HWPX/PDF 쌍의 토큰 불일치를 분류한다.

원문은 저장하지 않는다. 결과에는 공개 newsId, PDF 쪽, 원인별 토큰 수만 남긴다.
"""
import argparse
from collections import Counter, defaultdict
import difflib
import json
from pathlib import Path
import re

from dochan import Dochan
from dochan.model.document import Document
from dochan.output.plain_text import to_plain_text
from scripts.compare_pdf_pairs import find_pairs, normalize_text


EXCLUDED = {"156783589", "156784075", "156783622"}
IMAGE = re.compile(r"^\[이미지(?::.*)?\]$")
PAGE = re.compile(r"^(?:[-–—]|\d{1,4}|쪽|페이지|page|p\.)$", re.I)
SYMBOL = re.compile(r"^[\u2460-\u24ff\ue000-\uf8ff•▪◦※○●■□◇◆]+$")


def _tokens(text):
    normalized = normalize_text(text)
    return normalized.split(" ") if normalized else []


def _classify(left, right, left_all, right_all):
    if not left or not right:
        extra = right if right else left
        if extra and all(IMAGE.fullmatch(token) for token in extra):
            return "image_placeholder"
        if extra and all(PAGE.fullmatch(token) for token in extra) and len(extra) <= 4:
            return "page_number_or_list_number"
        if extra and all(SYMBOL.fullmatch(token) for token in extra):
            return "bullet_or_pua"
        pool = Counter(left_all if right else right_all)
        common = sum(min(count, pool[token]) for token, count in Counter(extra).items())
        if common * 2 >= len(extra):
            return "moved_text_or_reading_order"
        return "pdf_extra" if right else "pdf_missing"
    if "".join(left) == "".join(right):
        return "space_segmentation"
    if any(IMAGE.fullmatch(token) for token in right):
        return "image_mixed"
    if Counter(left) == Counter(right):
        return "reading_order"
    if any(SYMBOL.fullmatch(token) for token in left + right):
        return "bullet_or_pua_mixed"
    left_chars = Counter("".join(left))
    right_chars = Counter("".join(right))
    overlap = sum((left_chars & right_chars).values())
    total = max(sum(left_chars.values()), sum(right_chars.values()), 1)
    if overlap / total >= 0.85:
        return "space_and_order_mixed"
    return "content_or_order_unresolved"


def inspect_pair(hwpx_path, pdf_path):
    answer = Dochan(hwpx_path)
    candidate = Dochan(pdf_path)
    left = _tokens(answer.to_plain_text())
    right = _tokens(candidate.to_plain_text())
    page_ends = []
    running = 0
    for section in candidate.doc.sections:
        running += len(_tokens(to_plain_text(Document(sections=[section]))))
        page_ends.append((running, getattr(section.provenance, "page", None)))
    counts = Counter()
    pages = defaultdict(Counter)
    for operation, i, j, k, m in difflib.SequenceMatcher(
            None, left, right, autojunk=False).get_opcodes():
        if operation == "equal":
            continue
        category = _classify(left[i:j], right[k:m], left, right)
        mass = max(j - i, m - k)
        counts[category] += mass
        position = k + (m - k) // 2
        page = next((page for end, page in page_ends if position < end), None)
        pages[category][page or 0] += mass
    return {
        "tokens_hwpx": len(left), "tokens_pdf": len(right),
        "ratio": round(difflib.SequenceMatcher(None, left, right, autojunk=False).ratio(), 4),
        "causes": dict(counts),
        "pages": {key: dict(value) for key, value in pages.items()},
        "hwpx_errors": len(answer.errors), "pdf_errors": len(candidate.errors),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--parity", choices=("even", "odd", "all"), default="all")
    args = parser.parse_args(argv)
    if not (args.pairs_dir / "manifest.json").is_file():
        parser.error("공개 보도자료 manifest.json이 필요합니다")
    rows = {}
    if args.output.exists():
        rows = json.loads(args.output.read_text(encoding="utf-8")).get("rows", {})
    for key, hwpx_path, pdf_path in find_pairs(str(args.pairs_dir)):
        if key in EXCLUDED or (args.parity != "all" and
                               (int(key) % 2 == 0) != (args.parity == "even")):
            continue
        if key not in rows:
            try:
                rows[key] = inspect_pair(hwpx_path, pdf_path)
            except Exception as exc:
                rows[key] = {"error_type": type(exc).__name__}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    totals = Counter()
    documents = Counter()
    examples = defaultdict(list)
    for key, row in rows.items():
        for category, mass in row.get("causes", {}).items():
            totals[category] += mass
            documents[category] += 1
            if len(examples[category]) < 3:
                page = max(row["pages"].get(category, {0: 0}),
                           key=row["pages"].get(category, {0: 0}).get)
                examples[category].append([key, page])
    summary = {"pairs": len(rows), "mass": dict(totals),
               "documents": dict(documents), "examples": dict(examples)}
    args.output.write_text(json.dumps({"summary": summary, "rows": rows},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
