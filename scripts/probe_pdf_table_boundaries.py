"""HWPX/PDF 쌍의 페이지 경계 셀과 무테두리 1×1 표를 집계한다.

파일명·셀 내용·예외 메시지는 출력하지 않는다. 공백을 제외한 텍스트의 완전 일치만
근거로 삼으며, 페이지 경계 양성이 없다는 결과는 코퍼스 전체의 부재 증명이 아니다.
사용법: python -m scripts.probe_pdf_table_boundaries <쌍 디렉터리>
"""
import argparse
from collections import Counter
import json
import re
from unittest.mock import patch
import unicodedata
import zipfile

from lxml import etree

from dochan import Dochan
from dochan.model.document import Paragraph
from dochan.pdf import reader
from dochan.pdf.pagination import repeated_header_rows, same_columns
from scripts.compare_pdf_pairs import find_pairs

MAX_XML_BYTES = 64 * 1024 * 1024
MAX_XML_MEMBERS = 1000


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def boundary_matches(previous, following, answer_cells):
    """같은 열의 두 경계 조각이 유일한 정답 셀 하나를 완성하는 경우만 센다."""
    return len(_matching_cells(previous, following, answer_cells))


def _matching_cells(previous, following, answer_cells):
    if not previous.rows or not following.rows:
        return []
    drop = repeated_header_rows(previous, following)
    if drop >= len(following.rows):
        return []
    answer = Counter(answer_cells)
    matches = []
    for left, right in zip(previous.rows[-1], following.rows[drop]):
        if (left.is_merged_away or right.is_merged_away
                or left.col != right.col or left.col_span != right.col_span):
            continue
        a, b = compact(left.text), compact(right.text)
        if a and b and a != b and not answer[a] and not answer[b] and answer[a + b] == 1:
            matches.append((left, right))
    return matches


def _closed_edge(segments, left, right, y, tolerance):
    intervals = sorted((segment.x0, segment.x1) for segment in segments
                       if abs(segment.y0 - segment.y1) <= 0.6
                       and abs(segment.y0 - y) <= tolerance
                       and segment.x1 >= left - tolerance
                       and segment.x0 <= right + tolerance)
    cursor = left
    for start, end in intervals:
        if start > cursor + tolerance:
            return False
        cursor = max(cursor, end)
        if cursor >= right - tolerance:
            return True
    return False


def borderless_texts(hwpx_path):
    """HWPX 원시 셀 borderFill의 네 방향 모두 NONE인 1×1 표만 반환한다."""
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    with zipfile.ZipFile(hwpx_path) as archive:
        members = [info for info in archive.infolist()
                   if info.filename == "Contents/header.xml"
                   or re.fullmatch(r"Contents/section\d+\.xml", info.filename)]
        if len(members) > MAX_XML_MEMBERS or sum(info.file_size for info in members) > MAX_XML_BYTES:
            raise ValueError("HWPX XML inspection budget exceeded")
        roots = [etree.fromstring(archive.read(info), parser) for info in members]
    borderless = set()
    sides = {"leftBorder", "rightBorder", "topBorder", "bottomBorder"}
    for root in roots:
        for fill in root.xpath('//*[local-name()="borderFill"]'):
            borders = {etree.QName(child).localname: child.get("type")
                       for child in fill if isinstance(child.tag, str)
                       and etree.QName(child).localname in sides}
            if len(borders) == 4 and all(value == "NONE" for value in borders.values()):
                borderless.add(fill.get("id"))
    found = []
    for root in roots:
        for table in root.xpath('//*[local-name()="tbl"]'):
            if table.get("rowCnt") != "1" or table.get("colCnt") != "1":
                continue
            cells = table.xpath('./*[local-name()="tr"]/*[local-name()="tc"]')
            if len(cells) != 1 or cells[0].get("borderFillIDRef") not in borderless:
                continue
            # 중첩 표를 품은 셀은 글상자 후보가 아니다.
            if cells[0].xpath('.//*[local-name()="tbl"]'):
                continue
            text = compact("".join(cells[0].xpath('.//*[local-name()="t"]/text()')))
            if text:
                found.append(text)
    return found


def inspect_pair(hwpx_path, pdf_path):
    answer = Dochan(hwpx_path).doc
    answer_tables = answer.find_all("table")
    answer_cells = [compact(cell.text) for table in answer_tables for row in table.rows
                    for cell in row if not cell.is_merged_away and compact(cell.text)]
    counts = Counter()
    original = reader.continues
    original_build = reader.build_tables
    recent_segments = {}

    def capture(segments, fragments, **kwargs):
        page = kwargs.get("page_number")
        recent_segments[page] = segments
        for old in sorted(recent_segments)[:-2]:
            del recent_segments[old]
        return original_build(segments, fragments, **kwargs)

    def observe(previous, following, tolerance=1.5):
        accepted = original(previous, following, tolerance)
        counts["boundary_calls"] += 1
        if same_columns(previous.candidate.xs, following.candidate.xs, tolerance):
            counts["boundary_same_columns"] += 1
            cells = _matching_cells(previous.candidate.table, following.candidate.table,
                                    answer_cells)
            counts["boundary_exact_cell_positives"] += len(cells)
            for left, right in cells:
                edges = []
                for cell, candidate, y in ((left, previous.candidate, previous.candidate.bbox[1]),
                                           (right, following.candidate, following.candidate.bbox[3])):
                    page = getattr(cell.provenance, "page", None)
                    edges.append(_closed_edge(recent_segments.get(page, []), candidate.xs[cell.col],
                                              candidate.xs[cell.col + cell.col_span], y, tolerance))
                counts["boundary_positive_closed_both_edges"] += int(all(edges))
                counts["boundary_positive_head_blocked"] += int(not following.starts_top)
            if accepted:
                counts["accepted_boundary_exact_cell_positives"] += len(cells)
        if accepted:
            counts["accepted_boundary_pairs"] += 1
        return accepted

    with patch.object(reader, "continues", observe), patch.object(reader, "build_tables", capture):
        parsed_pdf = Dochan(pdf_path)
        candidate = parsed_pdf.doc
    pdf_tables = candidate.find_all("table")
    pdf_cells = {compact(cell.text) for table in pdf_tables for row in table.rows for cell in row
                 if not cell.is_merged_away}
    paragraphs = [compact(element.text) for section in candidate.sections
                  for element in section.elements if isinstance(element, Paragraph)]
    paragraph_pool = set(paragraphs)
    page_texts = [compact("".join(element.text for element in section.elements
                                if isinstance(element, Paragraph))) for section in candidate.sections]
    all_paragraph_text = "".join(page_texts)
    full_text = compact(parsed_pdf.to_plain_text())
    counts["one_by_one_total"] = sum(table.row_count == table.col_count == 1 for table in answer_tables)
    unruled = borderless_texts(hwpx_path)
    counts["borderless_one_by_one_nonempty"] = len(unruled)
    for text in unruled:
        if text in pdf_cells:
            counts["borderless_exact_pdf_cell"] += 1
        elif text in paragraph_pool:
            counts["borderless_exact_pdf_paragraph"] += 1
        elif any(text in page for page in page_texts):
            counts["borderless_contiguous_pdf_paragraph_text"] += 1
        elif text in all_paragraph_text:
            counts["borderless_cross_page_paragraph_text"] += 1
        elif text in full_text:
            counts["borderless_other_output_text"] += 1
        else:
            counts["borderless_text_unmatched"] += 1
    counts["pdf_warning_documents"] = int(bool(candidate.errors))
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs_dir")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    totals = Counter()
    for _key, hwpx_path, pdf_path in find_pairs(args.pairs_dir):
        totals["pairs"] += 1
        try:
            result = inspect_pair(hwpx_path, pdf_path)
        except Exception:
            totals["failed_pairs"] += 1
            continue
        totals.update(result)
        totals["successful_pairs"] += 1
    # 0인 판정도 명시한다. 내부 표본 이름이나 내용은 저장하지 않는다.
    for key in ("failed_pairs", "boundary_exact_cell_positives",
                "accepted_boundary_exact_cell_positives", "borderless_exact_pdf_cell",
                "borderless_exact_pdf_paragraph", "borderless_contiguous_pdf_paragraph_text",
                "borderless_cross_page_paragraph_text", "borderless_other_output_text",
                "borderless_text_unmatched"):
        totals.setdefault(key, 0)
    output = json.dumps(dict(totals), ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    print(output)
    return int(not totals["pairs"] or totals["failed_pairs"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
