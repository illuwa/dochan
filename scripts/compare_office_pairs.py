"""Legacy Office ↔ OOXML 짝을 현재 Dochan 출력 계약으로 비교한다.

사용법: /usr/bin/python3 -m scripts.compare_office_pairs DIR [DIR ...]
         --output result.json [--min-token-ratio 0.8]
기준선은 기본적으로 필터 없이 기록한다. 임계값은 코퍼스 실측 후 명시한다.
"""
import argparse
import difflib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from dochan.model.document import Paragraph
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Table
from scripts.compare_hwp_pairs import formatting_signature
from scripts.compare_pdf_pairs import normalize_text, table_signature

MAX_NODES = 1000000
MAX_TOKENS = 20000
EXTENSIONS = {"doc": "docx", "ppt": "pptx", "xls": "xlsx"}


def find_pairs(directories: List[str]) -> List[Tuple[str, str, str]]:
    """디렉터리별 NFC 이름과 대소문자 무시 확장자로 (키, OOXML, legacy)를 찾는다.

    줄기 이름 자체는 대소문자를 구분한다. 중복 디렉터리·정규화 중복은 한 번만
    측정하고, 다른 디렉터리/형식의 같은 이름에는 고유한 키를 붙인다.
    """
    pairs = []
    seen_dirs = set()
    keys = set()
    for directory in directories:
        directory = os.path.realpath(directory)
        if directory in seen_dirs:
            continue
        seen_dirs.add(directory)
        files = {}
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            stem, ext = os.path.splitext(name)
            ext = ext[1:].lower()
            if ext in EXTENSIONS or ext in EXTENSIONS.values():
                files.setdefault((unicodedata.normalize("NFC", stem), ext), path)
        for (stem, ext), legacy in sorted(files.items()):
            if ext not in EXTENSIONS or (stem, EXTENSIONS[ext]) not in files:
                continue
            base = stem + "." + ext
            key = base
            suffix = 2
            while key in keys:
                key = "%s (%d)" % (base, suffix)
                suffix += 1
            keys.add(key)
            pairs.append((key, files[(stem, EXTENSIONS[ext])], legacy))
    return pairs


def _walk(doc):
    stack = [(e, 0) for s in reversed(doc.sections) for e in reversed(s.elements)]
    seen = set()
    while stack:
        node, depth = stack.pop()
        if id(node) in seen or depth > 32:
            continue
        seen.add(id(node))
        if len(seen) > MAX_NODES:
            raise ValueError("comparison model node limit exceeded")
        yield node
        children = list(getattr(node, "caption", []))
        if isinstance(node, Table):
            children += [p for row in node.rows for cell in row for p in cell.paragraphs]
        elif isinstance(node, (Footnote, HeaderFooter)):
            children += node.paragraphs
        stack.extend((child, depth + 1) for child in reversed(children))


def _token_ratio(answer, candidate):
    a = normalize_text(answer).split()
    b = normalize_text(candidate).split()
    if not a:
        return None
    if len(a) > MAX_TOKENS or len(b) > MAX_TOKENS:
        return None
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a != b else 1.0


def _snapshot(doc):
    nodes = list(_walk(doc))
    paragraphs = [n for n in nodes if isinstance(n, Paragraph)]
    tables = [n for n in nodes if isinstance(n, Table)]
    images = [n for n in nodes if isinstance(n, Image)]
    features = {}
    features["tables"] = [table_signature(t) for t in tables]
    features["cells"] = [normalize_text(c.text) for t in tables for row in t.rows
                         for c in row if not c.is_merged_away]
    features["merged_cells"] = [(ri, ci, c.row_span, c.col_span) for t in tables
                                for ri, row in enumerate(t.rows) for ci, c in enumerate(row)
                                if c.row_span > 1 or c.col_span > 1]
    features["format_runs"] = [run for p in paragraphs for run in formatting_signature(p)]
    # Distinguish placements (Image nodes) from unique resource references.
    asset_paths = {a.source_path for a in doc.assets
                   if getattr(a, "metadata", {}).get("kind") == "image"
                   or getattr(a, "content_type", "").startswith("image/")}
    unmatched = set()
    represented = set()
    for image in images:
        path = getattr(getattr(image, "provenance", None), "path", "") or image.filename
        matches = {a for a in asset_paths if path == a or
                   (image.filename and os.path.basename(a) == image.filename)}
        represented.update(matches)
        if not matches:
            unmatched.add(path or (("bin", image.bin_id) if image.bin_id >= 0 else id(image)))
    features["images"] = [1] * (len(images) + len(asset_paths - represented))
    features["image_references"] = [1] * (len(asset_paths) + len(unmatched))
    features["image_bytes"] = [1 for image in images if image.has_data]
    features["alt_text"] = [normalize_text(i.alt_text) for i in images if normalize_text(i.alt_text)]
    for kind in ("footnote", "endnote", "comment", "header", "footer"):
        features[kind + "s"] = [normalize_text(n.text) for n in nodes
                                 if isinstance(n, (Footnote, HeaderFooter)) and n.type == kind]
    features["comments"] = features.pop("comments", [])
    urls = {r.link for p in paragraphs for r in p.runs if r.link}
    bookmarks = []
    notes = defaultdict(list)
    chart_paths = set()
    for p in paragraphs:
        text = p.text
        path = getattr(p.provenance, "path", "") or ""
        # XLS(X)/PPT(X) currently carry these concepts as textual markers.
        inline_comments = re.findall(r"\[comment: (.*?)\]", text, flags=re.DOTALL)
        features["comments"].extend(normalize_text(t) for t in inline_comments)
        if path.endswith("#comments") and not inline_comments:
            if not (p.heading_level == 2 and text.strip() == "Comments") and text.strip():
                features["comments"].append(normalize_text(text))
        bookmarks.extend(normalize_text(t) for t in re.findall(r"\[bookmark: (.*?)\]", text))
        urls.update(re.findall(r"<((?:https?://|mailto:|#)[^<>\s]+)>", text))
        if "notesSlides/" in path or path.endswith("#notes"):
            if not (p.heading_level == 2 and text.strip() == "Notes"):
                notes[getattr(p.provenance, "slide", None)].append(normalize_text(text))
        if re.search(r"(?:^|/)charts/[^/]+\.xml$", path) or "#chart" in path:
            chart_paths.add(path)
    features["hyperlinks"] = sorted(urls)
    features["bookmarks"] = bookmarks
    features["speaker_notes"] = [" ".join(parts).strip() for _, parts in sorted(notes.items(), key=lambda x: str(x[0]))
                                 if any(parts)]
    features["slides"] = [1] * len({s.provenance.slide for s in doc.sections
                                    if s.provenance and s.provenance.slide is not None})
    features["sheets"] = [1] * len({s.provenance.sheet for s in doc.sections
                                    if s.provenance and s.provenance.sheet is not None})
    features["charts"] = [1] * len(chart_paths)
    return features, "\n".join(p.text for p in paragraphs)


def _metric(answer, candidate):
    matched = sum((Counter(answer) & Counter(candidate)).values())
    return {"answer": len(answer), "candidate": len(candidate), "matched": matched,
            "ratio": matched / len(answer) if answer else None}


def compare_documents(answer, candidate, answer_text=None, candidate_text=None) -> Dict[str, object]:
    a, a_text = _snapshot(answer)
    b, b_text = _snapshot(candidate)
    a_text = a_text if answer_text is None else answer_text
    b_text = b_text if candidate_text is None else candidate_text
    metrics = {key: _metric(value, b[key]) for key, value in a.items()}
    urls_a, urls_b = set(a["hyperlinks"]), set(b["hyperlinks"])
    metrics["hyperlinks"]["set_equal"] = urls_a == urls_b
    metrics["hyperlinks"]["jaccard"] = len(urls_a & urls_b) / len(urls_a | urls_b) if urls_a else None
    text_keys = ("footnotes", "endnotes", "comments", "headers", "footers", "speaker_notes", "bookmarks", "alt_text", "hyperlinks")
    texts = {key: {"answer": a[key], "candidate": b[key],
                   "tok_ratio": _token_ratio(" ".join(a[key]), " ".join(b[key]))} for key in text_keys}
    tok_ratio = _token_ratio(a_text, b_text)
    return {
        "tok_ratio": tok_ratio, "metrics": metrics, "texts": texts,
        "token_limit_exceeded": max(len(normalize_text(a_text).split()), len(normalize_text(b_text).split())) > MAX_TOKENS,
        "answer_errors": list(answer.errors), "candidate_errors": list(candidate.errors),
    }


def compare_pair(ooxml_path: str, legacy_path: str) -> Dict[str, object]:
    from dochan import Dochan
    answer = Dochan(ooxml_path)
    candidate = Dochan(legacy_path)
    row = compare_documents(answer.doc, candidate.doc, answer.to_plain_text(), candidate.to_plain_text())
    row["files"] = {"answer": os.path.basename(ooxml_path), "candidate": os.path.basename(legacy_path)}
    row["format"] = os.path.splitext(legacy_path)[1][1:].lower()
    return row


def _failed(row):
    return bool(row.get("error") or any(e.startswith("ERR") for e in
                row.get("answer_errors", []) + row.get("candidate_errors", [])))


def summarize(rows, min_token_ratio: Optional[float] = None, exclude_pairs=()):
    excluded = sorted(set(exclude_pairs) & set(rows))
    valid = [r for key, r in rows.items() if key not in excluded and not _failed(r)]
    eligible = [r for r in valid if min_token_ratio is None or
                (r.get("tok_ratio") is not None and r["tok_ratio"] >= min_token_ratio)]
    ratios = [r["tok_ratio"] for r in eligible if r.get("tok_ratio") is not None]
    names = sorted({key for r in eligible for key in r.get("metrics", {})})
    metrics = {}
    for key in names:
        stats = [r["metrics"][key] for r in eligible if key in r.get("metrics", {})]
        denominator = sum(s["answer"] for s in stats)
        metrics[key] = {"answer": denominator, "candidate": sum(s["candidate"] for s in stats),
                        "matched": sum(s["matched"] for s in stats),
                        "ratio": sum(s["matched"] for s in stats) / denominator if denominator else None,
                        "measured_pairs": sum(s["ratio"] is not None for s in stats)}
    return {"pairs": len(rows), "eligible_pairs": len(eligible),
            "excluded_pairs": len(excluded), "excluded_pair_keys": excluded,
            "parse_failures": sum(_failed(r) for r in rows.values()),
            "below_threshold": sum(r.get("tok_ratio") is not None and r["tok_ratio"] < min_token_ratio
                                   for r in valid) if min_token_ratio is not None else 0,
            "unmeasured_tokens": sum(r.get("tok_ratio") is None for r in valid),
            "min_token_ratio": min_token_ratio,
            "mean_tok_ratio": sum(ratios) / len(ratios) if ratios else None,
            "metrics": metrics}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+")
    parser.add_argument("--output", help="JSON 출력 경로")
    parser.add_argument("--min-token-ratio", type=float, default=None)
    parser.add_argument("--exclude-pair", action="append", default=[],
                        help="내용 차이를 확인한 짝의 키를 집계에서 제외한다. 원시 결과는 보존한다.")
    args = parser.parse_args(argv)
    if args.min_token_ratio is not None and not 0 <= args.min_token_ratio <= 1:
        parser.error("--min-token-ratio must be between 0 and 1")
    rows = {}
    for key, answer, candidate in find_pairs(args.directories):
        try:
            rows[key] = compare_pair(answer, candidate)
        except Exception as exc:
            rows[key] = {"error": repr(exc), "files": {"answer": os.path.basename(answer), "candidate": os.path.basename(candidate)}}
    summary = summarize(rows, args.min_token_ratio, args.exclude_pair)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump({"summary": summary, "pairs": rows}, handle, ensure_ascii=False, indent=2)
    print("짝 %d개, 측정 대상 %d개, 파싱 실패 %d개, 임계값 미달 %d개, 명시적 제외 %d개" %
          (summary["pairs"], summary["eligible_pairs"], summary["parse_failures"],
           summary["below_threshold"], summary["excluded_pairs"]))
    print("평균 토큰 유사도: %s" % ("미측정" if summary["mean_tok_ratio"] is None else "%.4f" % summary["mean_tok_ratio"]))
    for key, metric in summary["metrics"].items():
        print("%s: 정답 %d / legacy %d / 일치 %d / 비율 %s" %
              (key, metric["answer"], metric["candidate"], metric["matched"],
               "null" if metric["ratio"] is None else "%.4f" % metric["ratio"]))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
