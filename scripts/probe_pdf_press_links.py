"""보도자료 PDF 링크를 독립 중앙점 판정 및 같은 URL의 HWPX 글자와 대조한다.

예: python -m scripts.probe_pdf_press_links corpus/press-pairs --output links.json
제품의 적중·경계 함수는 정답 계산에 사용하지 않는다. PDFium은 검증 전용이다.
"""
import argparse
import collections
import json
import math
import signal
import unicodedata
from pathlib import Path

from dochan.hwpx.parser import HWPXParser
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text
from dochan.pdf.annotations import DestinationResolver, attach_links, link_regions
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from scripts.probe_pdf_link_boundaries import ProbeDeadline, _compact, _inside, _runs

NORMALIZATION = ("NFKC로 호환 문자를 통일하고 모든 Unicode 공백을 제거한다. "
                 "문자열 양 끝의 괄호 ()만 제거하며 내부 괄호와 나머지 구두점은 보존한다. "
                 "URL은 정규화하지 않고 정확히 같은 URL의 HWPX 링크 후보 중 하나와 비교한다.")


def normalize(text):
    return "".join(unicodedata.normalize("NFKC", text).split()).strip("()")


def hwpx_links(path):
    """같은 URL의 독립적인 링크 발생을 합치지 않고 문단별로 보존한다."""
    if not path.is_file():
        return {}, ["missing_hwpx"]
    document = HWPXParser().parse(path, include_assets=False)
    links = collections.defaultdict(list)
    for paragraph in document.find_all("paragraph"):
        target, text = "", ""
        for run in paragraph.runs:
            if run.link != target:
                if target and text:
                    links[target].append(text)
                target, text = run.link, ""
            text += run.text
        if target and text:
            links[target].append(text)
    return dict(links), document.errors


def _glyphs(fragments):
    """제품 판정을 호출하지 않고 진행 폭과 두 축에서 중앙과 끝점을 다시 계산한다."""
    for fragment in fragments:
        xs = math.hypot(fragment.dir_x, fragment.dir_y)
        ys = math.hypot(fragment.up_x, fragment.up_y)
        if not xs or not ys or len(fragment.char_offsets) != len(fragment.text) + 1:
            continue
        ux, uy = fragment.dir_x / xs, fragment.dir_y / xs
        vx, vy = fragment.up_x / ys, fragment.up_y / ys
        for index, char in enumerate(fragment.text):
            first, last = fragment.char_offsets[index:index + 2]
            points = [(fragment.x + ux * d + vx * fragment.size / 2,
                       fragment.y + uy * d + vy * fragment.size / 2)
                      for d in (first, (first + last) / 2, last)]
            yield fragment, index, char, points, abs(last - first), abs(xs / ys - 1)


def _cut_depth(polygon, start, end):
    """진행선과 변의 교점까지 거리를 재며, 이 측정만으로 연결 여부를 정하지 않는다."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    width = math.hypot(dx, dy)
    cuts = []
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[(i + 1) % len(polygon)]
        ex, ey = bx - ax, by - ay
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-12:
            continue
        t = ((ax - start[0]) * ey - (ay - start[1]) * ex) / denominator
        s = ((ax - start[0]) * dy - (ay - start[1]) * dx) / denominator
        if 0 <= t <= 1 and 0 <= s <= 1:
            cuts.append(min(t, 1 - t) * width)
    return min(cuts) if cuts else None


def _diagnostics(fragments, polygons):
    centers, cuts, unreliable = [], [], 0
    if not polygons:
        return {"native_center_text": "", "cuts": [], "unreliable_fragments": 0}
    low = min(y for polygon in polygons for _, y in polygon)
    high = max(y for polygon in polygons for _, y in polygon)
    for fragment in fragments:
        if (not fragment.link_geometry_reliable or
                len(fragment.char_offsets) != len(fragment.text) + 1):
            if min(fragment.y, fragment.y + fragment.size) <= high and max(
                    fragment.y, fragment.y + fragment.size) >= low:
                unreliable += 1
    ratios = []
    for fragment, _index, char, points, width, ratio in _glyphs(fragments):
        start, center, end = points
        hit = any(_inside(polygon, *center) for polygon in polygons)
        if hit:
            centers.append(char)
            ratios.append(ratio)
        if char.isspace():
            continue
        for polygon in polygons:
            middle = _inside(polygon, *center)
            if any(_inside(polygon, *point) != middle for point in (start, end)):
                depth = _cut_depth(polygon, start, end)
                if depth is not None and depth > 1e-5:
                    cuts.append({"char": char, "center_inside": middle,
                                 "depth_pt": depth, "width_pt": width,
                                 "depth_ratio": depth / width if width else None,
                                 "reliable": fragment.link_geometry_reliable})
    return {"native_center_text": "".join(centers), "cuts": cuts,
            "unreliable_fragments": unreliable,
            "center_scale_ratio_max": max(ratios, default=0)}


def verify(path):
    import pypdfium2 as pdfium

    pdf = PDFFile(path.read_bytes())
    pages = pdf.pages()
    destinations = DestinationResolver(pdf, pages)
    areas = [link_regions(pdf, page, destinations) for page, _ in pages]
    raw = []
    for page, _ in pages:
        annots = pdf.resolve(page.get("Annots"))
        raw.append([pdf.resolve(ref) for ref in annots[:256]
                    if isinstance(pdf.resolve(ref), dict)
                    and str(pdf.resolve(ref).get("Subtype")) == "Link"]
                   if isinstance(annots, list) else [])
    if not any(raw):
        return {"records": [], "pdf_errors": pdf.warnings}
    paired, hwpx_errors = hwpx_links(path.with_suffix(".hwpx"))
    document = PDFReader().read(str(path))
    encoded = to_dict(document)
    body = collections.defaultdict(str)
    for run in _runs(encoded):
        provenance = run.get("provenance") or {}
        if provenance.get("path") != "annots":
            body[(provenance.get("page"), run["link"])] += run["text"]
    outputs = [to_markdown(document), to_plain_text(document),
               json.dumps(encoded, ensure_ascii=False)]
    reader, cache, records = PDFReader(), {}, []
    with pdfium.PdfDocument(str(path)) as independent:
        for page_index, annotations in enumerate(raw):
            if not annotations:
                continue
            page, resources = pages[page_index]
            extractor = ContentTextExtractor.from_fonts(
                reader._font_infos(pdf, resources, cache), track_char_positions=True)
            reader._configure_form_extractor(extractor, pdf, resources, cache)
            fragments = extractor.extract_fragments(b"\n".join(reader._page_content_parts(pdf, page)))
            regions = areas[page_index]
            warnings = []
            attach_links(fragments, regions, warnings, allow_clipped_edges=True)
            oracle_page = independent[page_index]
            textpage = oracle_page.get_textpage()
            try:
                glyphs = []
                for i in range(textpage.count_chars()):
                    char = textpage.get_text_range(i, 1)
                    if char.strip():
                        left, bottom, right, top = textpage.get_charbox(i)
                        glyphs.append((char, (left + right) / 2, (bottom + top) / 2))
            finally:
                textpage.close()
                oracle_page.close()
            resolved_index = 0
            for index, annot in enumerate(annotations):
                target = destinations.annotation_target(annot)
                region = regions[resolved_index] if target else None
                if target:
                    resolved_index += 1
                rect = pdf.resolve(annot.get("Rect"))
                valid_rect = (isinstance(rect, list) and len(rect) == 4 and
                              all(isinstance(v, (int, float)) and math.isfinite(v) for v in rect))
                if valid_rect:
                    x0, x1 = sorted((rect[0], rect[2]))
                    y0, y1 = sorted((rect[1], rect[3]))
                    # 보도자료 정답은 Rect에서 독립적으로 계산한다(제품 polygon 재사용 금지).
                    polygons = [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
                else:
                    polygons = []
                expected = "".join(c for c, x, y in glyphs if any(
                    _inside(polygon, x, y) for polygon in polygons))
                diag = _diagnostics(fragments, polygons)
                actual = "".join(char for frag, i, char, points, _width, _ratio in _glyphs(fragments)
                                 if any(_inside(p, *points[1]) for p in polygons)
                                 and any(first <= i < last and url == target
                                         for first, last, url in frag.link_spans))
                final = body[(page_index + 1, target)]
                if not actual or not _compact(final) or _compact(actual) not in _compact(final):
                    actual = ""
                candidates = paired.get(target, [])
                hwpx_unknown_reason = ("missing_hwpx" if hwpx_errors == ["missing_hwpx"] else
                                       "hwpx_errors" if hwpx_errors else
                                       "no_same_url" if not candidates else "")
                hwpx_status = ("unknown" if hwpx_errors or not candidates else
                               "match" if actual and any(normalize(actual) == normalize(c)
                                                         for c in candidates) else
                               "mismatch" if actual else "deferred")
                if actual:
                    reason = "attached"
                elif not target:
                    reason = "unresolved_target"
                elif not polygons:
                    reason = "invalid_rect"
                elif not expected:
                    reason = "no_drawn_text"
                elif diag["unreliable_fragments"]:
                    reason = "unreliable_text_geometry"
                elif diag["cuts"]:
                    reason = "glyph_boundary_cut"
                elif region and region.matched:
                    reason = "later_layout"
                else:
                    reason = "overlap_budget_or_other"
                records.append({"page": page_index + 1, "annotation_index": index,
                                "target": target, "rect": rect, "quad_points": annot.get("QuadPoints") is not None,
                                "drawn_text": bool(expected), "pdfium_center_text": expected,
                                "attached": bool(actual), "attached_text": actual,
                                "final_page_url_text": final, "hwpx_link_texts": candidates,
                                "hwpx_status": hwpx_status, "hwpx_unknown_reason": hwpx_unknown_reason,
                                "reason": reason,
                                "native_center_status": ("match" if normalize(actual) == normalize(
                                    diag["native_center_text"]) else "mismatch") if actual else "deferred",
                                "pdfium_status": ("match" if normalize(actual) == normalize(expected) else
                                                   "mismatch") if actual else "deferred",
                                "target_preserved": bool(target) and all(target in o for o in outputs),
                                "geometry": diag, "warnings": warnings})
    return {"records": records, "pdf_errors": document.errors, "hwpx_errors": hwpx_errors}


def summarize(results):
    records = [row for result in results.values() for row in result.get("records", [])]
    return {"documents": len(results), "link_documents": sum(bool(r.get("records")) for r in results.values()),
            "resolved_link_documents": sum(any(row["target"] for row in r.get("records", []))
                                           for r in results.values()),
            "annotations": len(records), "drawn_text": sum(r["drawn_text"] for r in records),
            "resolved_annotations": sum(bool(r["target"]) for r in records),
            "resolved_drawn_text": sum(bool(r["target"]) and r["drawn_text"] for r in records),
            "attached": sum(r["attached"] for r in records),
            "native_center_match": sum(r["native_center_status"] == "match" for r in records),
            "native_center_mismatch": sum(r["native_center_status"] == "mismatch" for r in records),
            "pdfium_match": sum(r["pdfium_status"] == "match" for r in records),
            "pdfium_mismatch": sum(r["pdfium_status"] == "mismatch" for r in records),
            "hwpx_match": sum(r["hwpx_status"] == "match" for r in records),
            "hwpx_mismatch": sum(r["hwpx_status"] == "mismatch" for r in records),
            "hwpx_unknown": sum(r["hwpx_status"] == "unknown" for r in records),
            "hwpx_unknown_reasons": dict(collections.Counter(r["hwpx_unknown_reason"] for r in records
                                                             if r["hwpx_status"] == "unknown")),
            "target_loss": sum(bool(r["target"]) and not r["target_preserved"] for r in records),
            "deferral_reasons": dict(collections.Counter(r["reason"] for r in records if not r["attached"])),
            "errors": {n: r["error"] for n, r in results.items() if "error" in r}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    def deadline(_signum, _frame):
        raise ProbeDeadline("document deadline")

    signal.signal(signal.SIGALRM, deadline)
    results = {}
    paths = [args.corpus / name for name in args.files] if args.files else sorted(args.corpus.glob("*.pdf"))
    for path in paths:
        try:
            signal.alarm(max(1, args.timeout))
            results[path.name] = verify(path)
        except (Exception, ProbeDeadline) as exc:
            results[path.name] = {"error": type(exc).__name__}
        finally:
            signal.alarm(0)
    summary = summarize(results)
    args.output.write_text(json.dumps({"normalization": NORMALIZATION, "summary": summary,
                                      "results": results}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
