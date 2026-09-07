"""동일 문서 HWPX(정답지) ↔ PDF 쌍으로 PDF 리더 품질을 측정한다.

사용법:
    python -m scripts.compare_pdf_pairs <쌍 디렉터리> [--output 결과.json]

<쌍 디렉터리> 안의 `이름.pdf` 마다 같은 이름의 `.hwpx` 가 있으면 한 쌍으로 본다.
지표:
- tok_ratio: 공백 토큰 시퀀스의 difflib 유사도 (문단·읽기 순서·공백 복원 품질)
- cell_hit: HWPX 셀 텍스트 중 PDF 표 셀에 그대로 존재하는 비율 (표 텍스트 배치 품질)
- signature_match: (행 수, 열 수, 병합 셀 span 다중집합)이 완전히 같은 HWPX 표 비율
- merge_match: 같은 행·열 수의 PDF 표가 있는 병합 셀 표 중 span 다중집합까지 같은 비율
"""
import argparse
import difflib
import glob
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """NFC 정규화 + 공백 정리. macOS 파일명/한글 조합 차이를 지운다."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text)).strip()


def token_ratio(left: str, right: str) -> float:
    a = normalize_text(left).split(" ")
    b = normalize_text(right).split(" ")
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def table_signature(table) -> Tuple[int, int, Tuple[Tuple[int, int], ...]]:
    spans = sorted(
        (cell.row_span, cell.col_span)
        for row in table.rows for cell in row
        if cell.row_span > 1 or cell.col_span > 1
    )
    return (table.row_count, table.col_count, tuple(spans))


def table_stats(doc) -> Tuple[List[tuple], List[str]]:
    tables = doc.find_all("table")
    signatures = [table_signature(t) for t in tables]
    cells = [
        normalize_text(cell.text)
        for t in tables for row in t.rows for cell in row
        if not cell.is_merged_away and normalize_text(cell.text)
    ]
    return signatures, cells


def cell_hit_rate(answer_cells: List[str], candidate_cells: List[str]) -> Optional[float]:
    if not answer_cells:
        return None
    available = set(candidate_cells)
    return sum(1 for c in answer_cells if c in available) / len(answer_cells)


def structure_matches(answer: List[tuple], candidate: List[tuple]) -> Tuple[int, int, int, int]:
    """(완전 일치 수, 병합 표 수, 병합 표 중 행·열 일치 수, 그중 span 까지 일치 수)."""
    pool = Counter(candidate)
    dims_pool = Counter((s[0], s[1]) for s in candidate)
    exact = merged_total = merged_dims = merged_exact = 0
    for sig in answer:
        has_merge = bool(sig[2])
        if pool[sig] > 0:
            pool[sig] -= 1
            exact += 1
            if has_merge:
                merged_exact += 1
        if has_merge:
            merged_total += 1
            if dims_pool[(sig[0], sig[1])] > 0:
                dims_pool[(sig[0], sig[1])] -= 1
                merged_dims += 1
    return exact, merged_total, merged_dims, merged_exact


def compare_pair(hwpx_path: str, pdf_path: str) -> Dict[str, object]:
    from dochan import Dochan

    answer = Dochan(hwpx_path)
    candidate = Dochan(pdf_path)
    answer_sigs, answer_cells = table_stats(answer.doc)
    candidate_sigs, candidate_cells = table_stats(candidate.doc)
    exact, merged_total, merged_dims, merged_exact = structure_matches(answer_sigs, candidate_sigs)
    return {
        "tok_ratio": round(token_ratio(answer.to_plain_text(), candidate.to_plain_text()), 4),
        "hwpx_tables": len(answer_sigs),
        "pdf_tables": len(candidate_sigs),
        "cell_hit": cell_hit_rate(answer_cells, candidate_cells),
        "signature_exact": exact,
        "merged_tables": merged_total,
        "merged_dims_matched": merged_dims,
        "merged_exact": merged_exact,
        "pdf_errors": [e for e in candidate.errors if e.startswith("ERR")][:3],
    }


def find_pairs(pairs_dir: str) -> List[Tuple[str, str, str]]:
    pairs = []
    for pdf_path in sorted(glob.glob(os.path.join(pairs_dir, "*.pdf"))):
        hwpx_path = pdf_path[:-4] + ".hwpx"
        if os.path.exists(hwpx_path):
            key = normalize_text(os.path.basename(pdf_path)[:-4])
            pairs.append((key, hwpx_path, pdf_path))
    return pairs


def summarize(rows: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    ratios = [r["tok_ratio"] for r in rows.values() if "tok_ratio" in r]
    hits = [r["cell_hit"] for r in rows.values() if r.get("cell_hit") is not None]
    hwpx_tables = sum(r.get("hwpx_tables", 0) for r in rows.values())
    merged_total = sum(r.get("merged_tables", 0) for r in rows.values())
    merged_dims = sum(r.get("merged_dims_matched", 0) for r in rows.values())
    return {
        "pairs": len(rows),
        "mean_tok_ratio": round(sum(ratios) / len(ratios), 4) if ratios else None,
        "min_tok_ratio": round(min(ratios), 4) if ratios else None,
        "hwpx_tables": hwpx_tables,
        "pdf_tables": sum(r.get("pdf_tables", 0) for r in rows.values()),
        "mean_cell_hit": round(sum(hits) / len(hits), 4) if hits else None,
        "signature_match": round(sum(r.get("signature_exact", 0) for r in rows.values()) / hwpx_tables, 4)
        if hwpx_tables else None,
        "merge_match": round(sum(r.get("merged_exact", 0) for r in rows.values()) / merged_dims, 4)
        if merged_dims else None,
        "merged_tables": merged_total,
        "merged_dims_matched": merged_dims,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pairs_dir", help="HWPX/PDF 쌍이 든 디렉터리")
    parser.add_argument("--output", help="쌍별 결과 JSON 경로")
    args = parser.parse_args(argv)

    started = time.time()
    rows: Dict[str, Dict[str, object]] = {}
    for key, hwpx_path, pdf_path in find_pairs(args.pairs_dir):
        try:
            rows[key] = compare_pair(hwpx_path, pdf_path)
        except Exception as exc:  # 측정 도구는 한 문서 실패로 전체를 멈추지 않는다
            rows[key] = {"error": repr(exc)}
    summary = summarize(rows)
    summary["elapsed_seconds"] = round(time.time() - started, 1)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump({"summary": summary, "pairs": rows}, handle, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
