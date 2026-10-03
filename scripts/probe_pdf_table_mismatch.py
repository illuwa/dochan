"""HWPX/PDF 표 서명 미일치를 익명으로 분류한다.

사용법: python -m scripts.probe_pdf_table_mismatch PAIRS_DIR [--output JSON_PATH]
출력에는 문서명·본문·셀 텍스트·예외 메시지를 넣지 않는다. 분류는 대응 후보
진단이며, PDF만으로 구조를 확정할 수 있는지와는 별개의 문제다.
"""
import argparse
from collections import Counter, defaultdict
import json
import re
import unicodedata

from dochan import Dochan
from dochan.model.table import Table
from dochan.pdf.pagination import repeated_header_rows
from scripts.compare_pdf_pairs import find_pairs, table_signature

MAX_TABLES = 2000
MAX_CELLS = 200000
MAX_TEXT = 4096
MAX_TOTAL_TEXT = 8 * 1024 * 1024
MAX_MATCH_PAIRS = 250000
MAX_DEPTH = 32
_SPACE = re.compile(r"\s+")


def _compact(value):
    return _SPACE.sub("", unicodedata.normalize("NFC", value))[:MAX_TEXT]


def _nested_ids(doc):
    found = set()
    seen = set()

    def walk(blocks, depth):
        if depth > MAX_DEPTH:
            return
        for block in blocks:
            if not isinstance(block, Table) or id(block) in seen:
                continue
            seen.add(id(block))
            if depth:
                found.add(id(block))
            for row in block.rows:
                for cell in row:
                    walk(cell.paragraphs, depth + 1)

    for section in doc.sections:
        walk(section.elements, 0)
    return found


def _records(doc):
    tables = doc.find_all("table")
    if len(tables) > MAX_TABLES:
        raise ValueError("table budget exceeded")
    nested = _nested_ids(doc)
    records = []
    cells_seen = 0
    text_seen = 0
    for index, table in enumerate(tables):
        texts = []
        pages = set()
        for row in table.rows:
            cells_seen += len(row)
            if cells_seen > MAX_CELLS:
                raise ValueError("cell budget exceeded")
            for cell in row:
                if cell.is_merged_away:
                    continue
                value = _compact(cell.text)
                text_seen += len(value)
                if text_seen > MAX_TOTAL_TEXT:
                    raise ValueError("table text budget exceeded")
                if value:
                    texts.append(value)
                page = getattr(cell.provenance, "page", None)
                if isinstance(page, int):
                    pages.add(page)
        grams = set()
        for value in texts:
            if len(value) >= 4:
                grams.update(value[i:i + 4] for i in range(min(len(value) - 3, 512)))
        records.append({"index": index, "signature": table_signature(table),
                        "cells": Counter(texts), "grams": grams,
                        "nested": id(table) in nested, "pages": sorted(pages),
                        "table": table})
    return records


def _overlap(answer, candidate):
    a, b = answer["cells"], candidate["cells"]
    count = sum(min(n, b[value]) for value, n in a.items() if len(value) >= 3)
    exact = count / max(1, sum(n for value, n in a.items() if len(value) >= 3))
    common = len(answer["grams"] & candidate["grams"])
    grams = common / max(1, len(answer["grams"]))
    return exact, grams, 0.75 * exact + 0.25 * grams


def _strong(score):
    exact, grams, _combined = score
    return exact >= 0.2 or grams >= 0.55


def _same_text_coverage(answer, candidates):
    covered = Counter()
    for candidate in candidates:
        covered.update(candidate["cells"])
    target = answer["cells"]
    total = sum(target.values())
    return (sum(min(count, covered[value]) for value, count in target.items())
            / total if total else 0.0)


def _empty_rows(table):
    return sum(not any(_compact(cell.text) for cell in row
                       if not cell.is_merged_away) for row in table.rows)


def _match_exact(answer, candidate):
    """기존 서명 Counter와 같은 일치 수를 유지하며 텍스트로 대응을 고른다."""
    groups = defaultdict(lambda: ([], []))
    for i, item in enumerate(answer):
        groups[item["signature"]][0].append(i)
    for j, item in enumerate(candidate):
        groups[item["signature"]][1].append(j)
    matched_a, matched_b = {}, set()
    for left, right in groups.values():
        if len(left) * len(right) > MAX_MATCH_PAIRS:
            for i, j in zip(left, right):
                matched_a[i] = j
                matched_b.add(j)
            continue
        scored = [(_overlap(answer[i], candidate[j])[2], -abs(i - j), i, j)
                  for i in left for j in right]
        for _score, _distance, i, j in sorted(scored, reverse=True):
            if i not in matched_a and j not in matched_b:
                matched_a[i] = j
                matched_b.add(j)
    return matched_a, matched_b


def classify_documents(answer_doc, candidate_doc):
    """문서 쌍을 분류한다. 반환값에는 원문·파일명을 포함하지 않는다."""
    answer = _records(answer_doc)
    candidate = _records(candidate_doc)
    exact, used_pdf = _match_exact(answer, candidate)
    residual = [j for j in range(len(candidate)) if j not in used_pdf]
    unmatched = [i for i in range(len(answer)) if i not in exact]
    links = {}
    for i in unmatched:
        choices = []
        for j, other in enumerate(candidate):
            score = _overlap(answer[i], other)
            if _strong(score):
                choices.append((j, score))
        choices.sort(key=lambda pair: (-pair[1][2], abs(i - pair[0])))
        links[i] = choices[:8]
    pdf_link_count = Counter(j for choices in links.values() for j, _ in choices[:1])
    body_parts = [_compact(element.text) for section in candidate_doc.sections
                  for element in section.elements if hasattr(element, "runs")]
    cases = []
    for i in unmatched:
        item = answer[i]
        options = links[i]
        available = [(j, score) for j, score in options if j in residual]
        first = available[0] if available else (options[0] if options else None)
        category = "ambiguous"
        chosen = []
        repeated = 0
        if item["nested"]:
            category = "nested"
        elif not first:
            category = "not_found"
        else:
            j, score = first
            chosen = [j]
            # 조각들은 순서가 연속이고, 독립 셀들이 합쳐져 정답 대부분을 덮어야 한다.
            fragments = [(k, s) for k, s in available if k != j
                         and abs(k - j) <= 2 and candidate[k]["cells"] != candidate[j]["cells"]]
            if fragments:
                k = fragments[0][0]
                pair = sorted((j, k))
                left, right = (candidate[index] for index in pair)
                a_rows, a_cols = item["signature"][:2]
                l_rows, l_cols = left["signature"][:2]
                r_rows, r_cols = right["signature"][:2]
                repeated = repeated_header_rows(left["table"], right["table"])
                vertical = (l_cols == r_cols == a_cols
                            and abs(l_rows + r_rows - repeated - a_rows) <= 1)
                horizontal = (l_rows == r_rows == a_rows
                              and abs(l_cols + r_cols - a_cols) <= 1)
                pages = [left["pages"], right["pages"]]
                adjacent_pages = (len(pages[0]) == len(pages[1]) == 1
                                  and pages[1][0] == pages[0][0] + 1)
                same_page = (len(pages[0]) == len(pages[1]) == 1
                             and pages[0] == pages[1])
                if (_same_text_coverage(item, [left, right]) >= 0.8
                        and _same_text_coverage(item, [candidate[j]]) < 0.8
                        and ((vertical and (adjacent_pages or same_page))
                             or (horizontal and same_page))):
                    chosen = pair
                    category = "page_split" if adjacent_pages else "split"
            if category == "ambiguous":
                coverage = _same_text_coverage(item, [candidate[j]])
                if coverage >= 0.65 and (pdf_link_count[j] > 1 or j in used_pdf):
                    category = "merged"
                elif coverage >= 0.65:
                    a_rows, a_cols, a_spans = item["signature"]
                    p_rows, p_cols, p_spans = candidate[j]["signature"]
                    if a_rows != p_rows and a_cols == p_cols:
                        category = "row_count"
                    elif a_rows == p_rows and a_cols != p_cols:
                        category = "col_count"
                    elif a_rows != p_rows and a_cols != p_cols:
                        category = "row_col_count"
                    elif a_spans != p_spans:
                        category = "span_only"
                else:
                    category = "other"
        pdf_dims = [list(candidate[j]["signature"][:2]) for j in chosen]
        pages = [candidate[j]["pages"] for j in chosen]
        cases.append({"category": category,
                      "answer_dims": list(item["signature"][:2]),
                      "pdf_dims": pdf_dims, "pdf_pages": pages,
                      "answer_empty_rows": _empty_rows(item["table"]),
                      "pdf_empty_rows": [_empty_rows(candidate[j]["table"])
                                         for j in chosen],
                      "candidate_count": len(options),
                      "repeated_header_rows": repeated if category == "page_split" else 0,
                      "body_cell_coverage": round(_same_text_coverage(
                          item, [{"cells": Counter({value: 1 for value in item["cells"]
                                                   if any(value in part for part in body_parts)})}]), 3)
                          if category == "not_found" else None,
                      "text_coverage": round(_same_text_coverage(
                          item, [candidate[j] for j in chosen]), 3) if chosen else 0})
    referenced = {j for j in residual if any(
        _strong(_overlap(item, candidate[j])) for item in answer)}
    return {"hwpx_tables": len(answer), "pdf_tables": len(candidate),
            "baseline_exact": len(exact), "mismatch": len(unmatched),
            "pdf_only": len(set(residual) - referenced),
            "categories": dict(Counter(case["category"] for case in cases)),
            "cases": cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs_dir")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    totals = Counter()
    categories = Counter()
    cases = []
    failures = Counter()
    pairs = find_pairs(args.pairs_dir)
    for _name, hwpx_path, pdf_path in pairs:
        try:
            result = classify_documents(Dochan(hwpx_path).doc, Dochan(pdf_path).doc)
        except Exception as exc:
            failures[type(exc).__name__] += 1
            continue
        totals.update({key: result[key] for key in
                       ("hwpx_tables", "pdf_tables", "baseline_exact", "mismatch", "pdf_only")})
        categories.update(result["categories"])
        for case in result["cases"]:
            case["id"] = "T%04d" % (len(cases) + 1)
            cases.append(case)
    report = {"pairs": len(pairs), "completed": len(pairs) - sum(failures.values()),
              "failed_by_type": dict(failures), "totals": dict(totals),
              "categories": dict(categories), "cases": cases}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    print(output if not args.output else json.dumps({k: report[k] for k in
                                                    ("pairs", "completed", "failed_by_type",
                                                     "totals", "categories")}, ensure_ascii=False))
    return int(not pairs or bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
