"""동일 문서 HWPX(정답지) ↔ HWP 쌍의 구조 및 서식 동등성을 측정한다.

사용법: python -m scripts.compare_hwp_pairs DIR [DIR ...] [--output out.json]
"""

import argparse
import json
import os
import sys
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

from scripts.compare_pdf_pairs import (
    cell_hit_rate,
    multiset_matches,
    nested_signatures,
    normalize_text,
    structure_matches,
    table_stats,
    token_ratio,
)


def find_pairs(directories: List[str]) -> List[Tuple[str, str, str]]:
    """NFC 로 같은 이름인 HWPX/HWP 파일 쌍을 경로 순서대로 찾는다 (확장자 대소문자 무시)."""
    pairs: List[Tuple[str, str, str]] = []
    for directory in directories:
        names = sorted(os.listdir(directory))
        hwp_by_stem = {}
        for name in names:
            if name.lower().endswith(".hwp"):
                stem = unicodedata.normalize("NFC", name[:-4])
                hwp_by_stem.setdefault(stem, os.path.join(directory, name))
        for name in names:
            if not name.lower().endswith(".hwpx"):
                continue
            stem = unicodedata.normalize("NFC", name[:-5])
            hwp_path = hwp_by_stem.get(stem)
            if hwp_path:
                pairs.append((stem, os.path.join(directory, name), hwp_path))
    return pairs


def formatting_signature(paragraph) -> tuple:
    """연속한 같은 굵기/기울기 런을 합친 후 텍스트를 정규화한다."""
    merged = []
    for run in paragraph.runs:
        if not run.text:
            continue
        style = (bool(run.bold), bool(run.italic))
        if merged and merged[-1][1:] == style:
            merged[-1] = (merged[-1][0] + run.text,) + style
        else:
            merged.append((run.text,) + style)
    signature = []
    for text, bold, italic in merged:
        normalized = normalize_text(text)
        if normalized:
            signature.append((normalized, bold, italic))
    return tuple(signature)


def _body_paragraphs(doc) -> list:
    return [element for section in doc.sections for element in section.elements
            if hasattr(element, "runs")]


def format_match_stats(answer, candidate) -> Tuple[int, int, int, int]:
    """(서식 일치, 텍스트 일치, HWPX 문단 수, HWP 문단 수)."""
    answer_paras = _body_paragraphs(answer)
    candidate_paras = _body_paragraphs(candidate)
    answer_by_text = {}
    candidate_by_text = {}
    for para in answer_paras:
        answer_by_text.setdefault(normalize_text(para.text), Counter())[formatting_signature(para)] += 1
    for para in candidate_paras:
        candidate_by_text.setdefault(normalize_text(para.text), Counter())[formatting_signature(para)] += 1

    matched_text = 0
    matched_format = 0
    for text, answer_styles in answer_by_text.items():
        candidate_styles = candidate_by_text.get(text, Counter())
        matched_text += min(sum(answer_styles.values()), sum(candidate_styles.values()))
        matched_format += sum((answer_styles & candidate_styles).values())
    return matched_format, matched_text, len(answer_paras), len(candidate_paras)


def compare_pair(hwpx_path: str, hwp_path: str) -> Dict[str, object]:
    from dochan import Dochan

    answer = Dochan(hwpx_path)
    candidate = Dochan(hwp_path)
    answer_sigs, answer_cells = table_stats(answer.doc)
    candidate_sigs, candidate_cells = table_stats(candidate.doc)
    exact = structure_matches(answer_sigs, candidate_sigs)[0]
    answer_nested = nested_signatures(answer.doc)
    candidate_nested = nested_signatures(candidate.doc)
    matched_format, matched_text, paragraphs_hwpx, paragraphs_hwp = format_match_stats(
        answer.doc, candidate.doc
    )
    return {
        "tok_ratio": round(token_ratio(answer.to_plain_text(), candidate.to_plain_text()), 4),
        "hwpx_tables": len(answer_sigs),
        "hwp_tables": len(candidate_sigs),
        "signature_exact": exact,
        "cell_hit": cell_hit_rate(answer_cells, candidate_cells),
        "hwpx_nested": len(answer_nested),
        "hwp_nested": len(candidate_nested),
        "nested_exact": multiset_matches(answer_nested, candidate_nested),
        "format_match": matched_format / matched_text if matched_text else None,
        "paragraphs_hwpx": paragraphs_hwpx,
        "paragraphs_hwp": paragraphs_hwp,
        "hwp_errors": [error for error in candidate.errors if error.startswith("ERR")][:3],
        "hwp_warnings": sum(error.startswith("WARN") for error in candidate.errors),
    }


def summarize(rows: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    valid = [row for row in rows.values() if "tok_ratio" in row]
    ratios = [row["tok_ratio"] for row in valid]
    hits = [row["cell_hit"] for row in valid if row.get("cell_hit") is not None]
    formats = [row["format_match"] for row in valid if row.get("format_match") is not None]
    answer_tables = sum(row["hwpx_tables"] for row in valid)
    answer_nested = sum(row["hwpx_nested"] for row in valid)
    return {
        "pairs": len(rows),
        "mean_tok_ratio": round(sum(ratios) / len(ratios), 4) if ratios else None,
        "min_tok_ratio": round(min(ratios), 4) if ratios else None,
        "hwpx_tables": answer_tables,
        "hwp_tables": sum(row["hwp_tables"] for row in valid),
        "signature_match": round(sum(row["signature_exact"] for row in valid) / answer_tables, 4)
        if answer_tables else None,
        "mean_cell_hit": round(sum(hits) / len(hits), 4) if hits else None,
        "hwpx_nested": answer_nested,
        "hwp_nested": sum(row["hwp_nested"] for row in valid),
        "nested_match": round(sum(row["nested_exact"] for row in valid) / answer_nested, 4)
        if answer_nested else None,
        "mean_format_match": round(sum(formats) / len(formats), 4) if formats else None,
        "pairs_with_errors": sum(bool(row.get("hwp_errors") or row.get("error"))
                                 for row in rows.values()),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", help="같은 이름의 HWPX/HWP 쌍이 든 디렉터리")
    parser.add_argument("--output", help="쌍별 결과 JSON 경로")
    args = parser.parse_args(argv)

    rows: Dict[str, Dict[str, object]] = {}
    for stem, hwpx_path, hwp_path in find_pairs(args.directories):
        key = stem
        suffix = 2
        while key in rows:
            key = f"{stem} ({suffix})"
            suffix += 1
        try:
            rows[key] = compare_pair(hwpx_path, hwp_path)
        except Exception as exc:
            rows[key] = {"error": repr(exc)}
    summary = summarize(rows)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump({"summary": summary, "pairs": rows}, handle, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
