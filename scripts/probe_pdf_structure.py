"""PDF 각주·중첩표·페이지 경계·수식 전제조건을 집계한다.

내부 문서 이름과 본문은 결과에 기록하지 않는다. 각주 후보는 실측으로 정한
보수적 기하 조건의 조사 결과이며 라이브러리의 출력 동작을 바꾸지 않는다.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from dochan import Dochan
from dochan.pdf.content import ContentTextExtractor, assemble_lines
from dochan.pdf.objects import PDFRef
from dochan.pdf.notes import detect_notes
from dochan.pdf.pagination import (EDGE_FRACTION, HEADER_FOOTER_ZONE, HeadInfo,
                                  TailInfo, body_between, continues, page_bounds,
                                  page_rotation, repeated_header_rows, same_columns)
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from dochan.pdf.tables import TableBudget, build_tables
from scripts.compare_pdf_pairs import (find_pairs, multiset_matches, nested_signatures,
                                       normalize_text)

MAX_PROBE_FRAGMENTS = 50000
MAX_PROBE_FILES = 10000
_MARKER = re.compile(r"^\s*(\d{1,3})\)\s*$")
_DEFINITION = re.compile(r"^\s*(\d{1,3})\)\s*\S")


def footnote_candidates(fragments, bounds):
    """동일 번호의 하단 작은 글씨와 본문 위첨자가 유일하게 짝지어지는가."""
    if not fragments or len(fragments) > MAX_PROBE_FRAGMENTS:
        return []
    sizes = Counter(round(f.size, 3) for f in fragments if f.size > 0)
    if not sizes:
        return []
    body = sizes.most_common(1)[0][0]
    bottom, top = bounds
    lines = assemble_lines(fragments)
    definitions = [(i, line, _DEFINITION.match(line.text))
                   for i, line in enumerate(lines)
                   if bottom <= line.y <= bottom + (top - bottom) * 0.25
                   and 0 < line.size < body * 0.9]
    definitions = [(i, line, match) for i, line, match in definitions if match]
    if not definitions:
        return []
    references = {}
    for frag in fragments:
        marker = _MARKER.match(frag.text)
        if marker is None or not 0 < frag.size <= body * 0.8:
            continue
        # 실물 표지의 크기비는 0.75, 상승은 본문 크기의 0.207~0.217이다.
        nearby = [host for host in fragments
                  if host.size >= body * 0.95
                  and 0.15 * host.size <= frag.y - host.y <= 0.3 * host.size
                  and -0.1 * host.size <= frag.x - host.x - host.width <= 0.5 * host.size]
        if len(nearby) == 1:
            references.setdefault(marker.group(1), []).append(frag)
    result = []
    counts = Counter(match.group(1) for _i, _line, match in definitions)
    for index, line, match in definitions:
        marker = match.group(1)
        refs = references.get(marker, [])
        if len(refs) != 1 or counts[marker] != 1 or refs[0].y <= line.y + body:
            continue
        following = next((i for i, _ln, _m in definitions if i > index), len(lines))
        body_lines = []
        for continuation in lines[index:following]:
            if continuation.y > line.y or abs(continuation.size - line.size) > 0.1:
                break
            body_lines.append(continuation.text)
        text = re.sub(r"^\s*\d{1,3}\)\s*", "", " ".join(body_lines))
        result.append({"reference_order": refs[0].order,
                       "definition_order": line.order,
                       "text": text})
    return result


def _compact(text):
    return normalize_text(text).replace(" ", "")


def probe_pairs(pairs_dir):
    totals = Counter()
    for _key, hwpx_path, pdf_path in find_pairs(str(pairs_dir))[:MAX_PROBE_FILES]:
        totals["pairs"] += 1
        try:
            answer = Dochan(hwpx_path).doc
            # Supported Elements의 같은 행은 각주와 미주를 함께 평가한다.
            # 미주가 페이지 하단에 출력된 문서를 음성 모집단에 넣으면 안 된다.
            footnotes = answer.find_all("footnote")
            endnotes = answer.find_all("endnote")
            truth_notes = footnotes + endnotes
            truth_nested = nested_signatures(answer)
            totals["footnote_positive_documents"] += bool(footnotes)
            totals["endnote_positive_documents"] += bool(endnotes)
            totals["note_positive_documents"] += bool(truth_notes)
            totals["note_negative_documents"] += not bool(truth_notes)
            totals["footnotes_expected"] += len(footnotes)
            totals["endnotes_expected"] += len(endnotes)
            totals["nested_expected"] += len(truth_nested)
            totals["nested_one_by_one_expected"] += sum(s[:2] == (1, 1) for s in truth_nested)
            totals["nested_negative_documents"] += not bool(truth_nested)
            pdf_doc = PDFReader().read(pdf_path)
            pdf_nested = nested_signatures(pdf_doc)
            totals["nested_actual"] += len(pdf_nested)
            totals["nested_exact"] += multiset_matches(truth_nested, pdf_nested)
            totals["nested_false_in_negative_documents"] += len(pdf_nested) if not truth_nested else 0
            totals["nested_one_by_one_exact"] += multiset_matches(
                [s for s in truth_nested if s[:2] == (1, 1)],
                [s for s in pdf_nested if s[:2] == (1, 1)])
            pdf = PDFFile(Path(pdf_path).read_bytes())
            reader = PDFReader()
            cache = {}
            budget = TableBudget()
            previous = None
            candidate_texts = []
            next_note_number = 1
            truth_cells = {_compact(c.text) for table in answer.find_all("table")
                           for row in table.rows for c in row if c.text}
            for page_number, (page, resources) in enumerate(pdf.pages(), 1):
                totals["pages"] += 1
                content = ContentTextExtractor.from_fonts(
                    reader._font_infos(pdf, resources, cache)).extract_page(
                        b"\n".join(reader._page_content_parts(pdf, page)))
                candidates, _consumed, _refs, next_note_number = detect_notes(
                    content.fragments, content.segments, page_bounds(pdf, page),
                    page_number, next_note_number)
                candidate_texts.extend(_compact(candidate.text) for candidate in candidates)
                tables = build_tables(content.segments, content.fragments,
                                      page_number=page_number, budget=budget)
                if not tables or page_rotation(pdf, page) != 0:
                    previous = None
                    continue
                low, high = page_bounds(pdf, page)
                body_low, body_high = low + HEADER_FOOTER_ZONE, high - HEADER_FOOTER_ZONE
                first, last = max(tables, key=lambda t: t.bbox[3]), min(tables, key=lambda t: t.bbox[1])
                consumed = set().union(*(t.fragment_orders for t in tables))
                starts = (first.bbox[1] < body_high and first.bbox[3] > body_low
                          and max(0, body_high - first.bbox[3]) <= EDGE_FRACTION * (high - low)
                          and not body_between(content.fragments, consumed, first.bbox[3], body_high))
                reaches = (last.bbox[1] < body_high and last.bbox[3] > body_low
                           and not body_between(content.fragments, consumed, body_low, last.bbox[1]))
                head = HeadInfo(first, starts)
                if previous is not None and starts:
                    totals["boundary_candidates"] += 1
                    if same_columns(previous.candidate.xs, first.xs):
                        totals["boundary_same_columns"] += 1
                    if continues(previous, head):
                        totals["boundary_continuations"] += 1
                        drop = repeated_header_rows(previous.candidate.table, first.table)
                        prev_row = previous.candidate.table.rows[-1]
                        next_row = first.table.rows[drop]
                        pair_hits = 0
                        for left, right in zip(prev_row, next_row):
                            a, b = _compact(left.text), _compact(right.text)
                            if a and b and a + b in truth_cells:
                                pair_hits += 1
                        totals["boundary_split_cells_with_exact_truth"] += pair_hits
                previous = TailInfo(last, True, max(0, last.bbox[1] - body_low), high - low) if reaches else None
            totals["note_candidates"] += len(candidate_texts)
            expected = [_compact(n.text) for n in truth_notes]
            totals["note_exact"] += multiset_matches(expected, candidate_texts)
            totals["note_false_in_negative_documents"] += len(candidate_texts) if not truth_notes else 0
        except Exception:
            # 내부 파일명이나 예외에 포함된 본문을 출력하지 않는다.
            totals["failed_pairs"] += 1
    return dict(totals)


def probe_formulas(pdf_dir):
    result = {"files": 0, "raw_formula_files": [], "failed_files": 0}
    for path in sorted(Path(pdf_dir).glob("*.pdf"))[:MAX_PROBE_FILES]:
        result["files"] += 1
        data = path.read_bytes()
        if b"/Formula" not in data:
            continue
        try:
            pdf = PDFFile(data)
            formulas = []
            for num in pdf.xref:
                obj = pdf.resolve(PDFRef(num, 0))
                if isinstance(obj, dict) and str(obj.get("S", "")) == "Formula":
                    formulas.append(obj)
            result["raw_formula_files"].append({
                "public_file": path.name,
                "formula_elements": len(formulas),
                "associated_file_elements": sum(bool(obj.get("AF")) for obj in formulas),
                "alt_elements": sum(bool(obj.get("Alt")) for obj in formulas),
                "raw_mathml_present": b"/MathML" in data,
            })
        except Exception:
            result["failed_files"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-dir")
    parser.add_argument("--public-pdf-dir")
    args = parser.parse_args()
    result = {}
    if args.pairs_dir:
        result["private_pair_aggregates"] = probe_pairs(args.pairs_dir)
    if args.public_pdf_dir:
        result["public_formula_observations"] = probe_formulas(args.public_pdf_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
