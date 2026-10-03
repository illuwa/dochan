"""익명 HWPX/PDF 쌍에서 PDF 표 미발견 사례의 테두리와 선분을 대조한다.

사용법: python -m scripts.probe_pdf_table_missing PAIRS_DIR --output JSON_PATH
결과에는 파일명, 문서 텍스트, 셀 텍스트, 예외 문자열을 기록하지 않는다.
"""
import argparse
from collections import Counter, defaultdict
import json
import re
import zipfile

from dochan import Dochan
from dochan.pdf import reader
from dochan.pdf.content import assemble_lines
from dochan.utils import safe_xml
from scripts.compare_pdf_pairs import find_pairs
from scripts.probe_pdf_table_mismatch import (_match_exact, _records,
                                               classify_documents, _compact)

MAX_XML_MEMBERS = 1000
MAX_XML_BYTES = 64 * 1024 * 1024
MAX_FRAGMENTS = 200000
MAX_ANCHORS = 2000
MAX_LINES = 20000
MAX_MATCH_LINES = 5000
MAX_MATCH_VALUES = 128
SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


def _tag(node):
    return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""


def _root(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise ValueError("XML size budget exceeded")
    return safe_xml.fromstring(archive.read(info))


def _border_styles(path):
    """원본 표 순서대로 각 셀의 실제 네 변 스타일을 집계한다."""
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist()
                 if info.filename == "Contents/header.xml"
                 or re.fullmatch(r"Contents/section\d+\.xml", info.filename)]
        if len(infos) > MAX_XML_MEMBERS or sum(i.file_size for i in infos) > MAX_XML_BYTES:
            raise ValueError("HWPX XML budget exceeded")
        header = _root(archive, "Contents/header.xml")
        fills = {}
        for fill in header.iter():
            if _tag(fill) != "borderFill":
                continue
            fills[fill.get("id")] = {
                _tag(side): (side.get("type", "NONE"), side.get("width", ""))
                for side in fill if _tag(side) in SIDES}
        tables = []
        sections = sorted((info for info in infos
                           if info.filename != "Contents/header.xml"),
                          key=lambda info: int(re.search(r"section(\d+)\.xml$",
                                                         info.filename).group(1)))
        for info in sections:
            root = _root(archive, info.filename)
            for table in root.iter():
                if _tag(table) != "tbl":
                    continue
                count = Counter()
                unknown = 0
                for row in table:
                    if _tag(row) != "tr":
                        continue
                    for cell in row:
                        if _tag(cell) != "tc":
                            continue
                        sides = fills.get(cell.get("borderFillIDRef"))
                        if sides is None or any(side not in sides for side in SIDES):
                            unknown += 1
                            continue
                        for side in SIDES:
                            kind, width = sides[side]
                            count[(side, kind, width)] += 1
                visible = sum(n for (side, kind, width), n in count.items()
                              if kind.upper() not in ("NONE", "") and width != "0")
                horizontal = sum(n for (side, kind, width), n in count.items()
                                 if side in ("topBorder", "bottomBorder")
                                 and kind.upper() not in ("NONE", "") and width != "0")
                vertical = visible - horizontal
                tables.append({"dims": (int(table.get("rowCnt", "0")),
                                        int(table.get("colCnt", "0"))),
                               "visible_sides": visible, "horizontal_sides": horizontal,
                               "vertical_sides": vertical, "unknown_cells": unknown,
                               "styles": [[side, kind, width, n]
                                          for (side, kind, width), n in sorted(count.items())]})
        return tables


def _anchors(cells, pages):
    """긴 셀 문자열과 PDF 글자 조각의 일치로 쪽과 대략적인 글자 영역을 찾는다."""
    matches = defaultdict(list)
    values = [value for value in cells if len(value) >= 2][:MAX_MATCH_VALUES]
    if not values:
        return None, [], "no_text", []
    for page, (segments, fragments, lines) in pages.items():
        if (len(segments) > MAX_LINES or len(fragments) > MAX_FRAGMENTS
                or len(lines) > MAX_MATCH_LINES):
            continue
        by_order = {fragment.order: fragment for fragment in fragments}
        for line in lines:
            text = _compact(line.text)
            hits = []
            for value in values:
                if value in text:
                    hits.append(min(len(value), 32))
                elif len(value) >= 8:
                    chunks = {value[:6], value[-6:], value[len(value) // 2 - 3:
                                                     len(value) // 2 + 3]}
                    matched = sum(chunk in text for chunk in chunks)
                    if matched:
                        hits.append(min(matched * 6, 18))
            score = sum(hits)
            if score < 3:
                continue
            if len(hits) == 1 and hits[0] < 4:
                continue
            matches[page].append((score, [by_order[order] for order in line.fragment_orders
                                          if order in by_order]))
            if len(matches[page]) >= MAX_ANCHORS:
                break
    if not matches:
        return None, [], "no_line_match", []
    page_scores = {page: sum(score for score, _ in rows) for page, rows in matches.items()}
    page = max(page_scores, key=lambda key: (page_scores[key], -key))
    best = max(page_scores.values())
    candidate_pages = [key for key, score in page_scores.items() if score * 2 >= best]
    locations = []
    if len(candidate_pages) <= 32:
        for key in candidate_pages:
            line_best = max(score for score, _ in matches[key])
            group = [fragment for score, frags in matches[key] if score * 2 >= line_best
                     for fragment in frags]
            locations.append((key, group[:MAX_ANCHORS]))
    if (len(page_scores) > 1 and
            page_scores[page] <= sum(page_scores.values()) - page_scores[page]):
        return None, [], "repeated_or_ambiguous", locations
    best = max(score for score, _ in matches[page])
    anchors = [fragment for score, group in matches[page] if score * 2 >= best
               for fragment in group]
    return page, anchors[:MAX_ANCHORS], "located", locations


def _covers(lines, coordinate, start, end, tolerance=1.5):
    runs = sorted((lo, hi) for fixed, lo, hi in lines
                  if abs(fixed - coordinate) <= tolerance)
    cursor = start
    for lo, hi in runs:
        if lo > cursor + tolerance:
            return False
        cursor = max(cursor, hi)
        if cursor >= end - tolerance:
            return True
    return False


def _axes(values, tolerance=1.5):
    clusters = []
    for value in sorted(values):
        if not clusters or value - clusters[-1][-1] > tolerance:
            clusters.append([])
        clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _geometry(segments, anchors, dims):
    """글자 부근의 PDF 선을 분류한다. 격자 확정은 닫힌 외곽·전폭 경계에 한한다."""
    if not anchors:
        return "other", 0, 0, False
    if len(segments) > MAX_LINES:
        return "other", 0, 0, False
    x0 = min(f.x for f in anchors)
    x1 = max(f.x + max(f.width, 1) for f in anchors)
    y0 = min(f.y for f in anchors)
    y1 = max(f.y + max(f.size, 1) for f in anchors)
    # 글자 여백은 코퍼스의 표 여백보다 넉넉히 잡는다. 선이 멀리 있으면
    # 인접 표의 선일 수도 있으므로 판정은 other로 남긴다.
    h, v = [], []
    for seg in segments[:MAX_LINES]:
        if abs(seg.y1 - seg.y0) <= 1.5 and y0 - 24 <= seg.y0 <= y1 + 24:
            if seg.x0 <= x1 + 24 and seg.x1 >= x0 - 24:
                h.append((0.5 * (seg.y0 + seg.y1), seg.x0, seg.x1))
    left_limit = min((line[1] for line in h), default=x0 - 24)
    right_limit = max((line[2] for line in h), default=x1 + 24)
    for seg in segments[:MAX_LINES]:
        if abs(seg.x1 - seg.x0) <= 1.5 and left_limit - 1.5 <= seg.x0 <= right_limit + 1.5:
            if seg.y0 <= y1 + 24 and seg.y1 >= y0 - 24:
                v.append((0.5 * (seg.x0 + seg.x1), seg.y0, seg.y1))
    if not h and not v:
        return "b", 0, 0, False
    if not h or not v:
        return "c", len(h), len(v), False
    if len(h) + len(v) > 2000:
        return "other", len(h), len(v), False
    xs = _axes({x for x, lo, hi in v if lo <= y0 + 1.5 and hi >= y1 - 1.5})
    ys = _axes({y for y, lo, hi in h if lo <= x0 + 1.5 and hi >= x1 - 1.5})
    if len(xs) > 64 or len(ys) > 64:
        return "other", len(h), len(v), False
    rows, cols = dims
    lefts = [x for x in xs if x < x0][-4:]
    rights = [x for x in xs if x > x1][:4]
    bottoms = [y for y in ys if y < y0 and y > y0 - 24][-4:]
    tops = [y for y in ys if y > y1 and y < y1 + 24][:4]
    for left in lefts:
        for right in rights:
            if left >= x0 or right <= x1 or right <= left:
                continue
            for bottom in bottoms:
                for top in tops:
                    full_x = [x for x in xs if left <= x <= right
                              and _covers(v, x, bottom, top)]
                    full_y = [y for y in ys if bottom <= y <= top
                              and _covers(h, y, left, right)]
                    if (len(full_x) == cols + 1 and len(full_y) == rows + 1
                            and full_x[0] == left and full_x[-1] == right
                            and full_y[0] == bottom and full_y[-1] == top):
                        return "a", len(h), len(v), True
    return "c", len(h), len(v), False


def inspect_pair(hwpx_path, pdf_path):
    raw = _border_styles(hwpx_path)
    answer = Dochan(hwpx_path).doc
    pages = {}
    build = reader.build_tables

    def capture(segments, fragments, **kwargs):
        pages[kwargs.get("page_number")] = (segments, fragments)
        return build(segments, fragments, **kwargs)

    reader.build_tables = capture
    try:
        candidate = Dochan(pdf_path).doc
    finally:
        reader.build_tables = build
    pages = {page: (segments, fragments, assemble_lines(fragments))
             for page, (segments, fragments) in pages.items()
             if len(fragments) <= MAX_FRAGMENTS}
    classified = classify_documents(answer, candidate)
    records = _records(answer)
    exact, _ = _match_exact(records, _records(candidate))
    unmatched = [i for i in range(len(records)) if i not in exact]
    if len(unmatched) != len(classified["cases"]):
        raise ValueError("mismatch index disagreement")
    rows = []
    for index, case in zip(unmatched, classified["cases"]):
        if case["category"] != "not_found":
            continue
        border = (raw[index] if len(raw) == len(records)
                  and raw[index]["dims"] == records[index]["signature"][:2] else None)
        page, anchors, location_reason, locations = _anchors(records[index]["cells"], pages)
        geometry = (_geometry(pages[page][0], anchors, records[index]["signature"][:2])
                    if page is not None else ("other", 0, 0, False))
        consensus = "unknown"
        if page is None and location_reason == "repeated_or_ambiguous" and locations:
            alternatives = [_geometry(pages[key][0], group,
                                      records[index]["signature"][:2])
                            for key, group in locations]
            labels = {item[0] for item in alternatives}
            consensus = labels.pop() if len(labels) == 1 else "mixed"
        rows.append({"source_index": index, "dims": list(records[index]["signature"][:2]),
                     "border": border, "page_found": page is not None,
                     "location_reason": location_reason,
                     "candidate_pages": len(locations),
                     "candidate_geometry_consensus": consensus,
                     "cell_text_count": sum(records[index]["cells"].values()),
                     "max_cell_chars": max((len(value) for value in records[index]["cells"]),
                                           default=0),
                     "anchor_count": len(anchors), "class": geometry[0],
                     "near_horizontal": geometry[1], "near_vertical": geometry[2],
                     "closed_grid": geometry[3]})
    return rows, {"raw_tables": len(raw), "model_tables": len(records),
                  "raw_model_order_equal": len(raw) == len(records),
                  "raw_model_dims_equal": (len(raw) == len(records) and all(
                      item["dims"] == record["signature"][:2]
                      for item, record in zip(raw, records))),
                  "baseline_exact": classified["baseline_exact"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    cases, pairs, failures = [], [], Counter()
    for _name, hwpx, pdf in find_pairs(args.pairs_dir):
        try:
            rows, summary = inspect_pair(hwpx, pdf)
            summary["pair_index"] = len(pairs) + 1
            pairs.append(summary)
            for row in rows:
                row["id"] = "M%04d" % (len(cases) + 1)
                row["pair_index"] = summary["pair_index"]
                cases.append(row)
        except Exception as exc:
            failures[type(exc).__name__] += 1
    result = {"pairs": len(pairs), "failures": dict(failures),
              "classes": dict(Counter(row["class"] for row in cases)),
              "cases": cases, "pair_summaries": pairs}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({key: result[key] for key in ("pairs", "failures", "classes")},
                     ensure_ascii=False))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
