"""공개 PDF의 링크 글자를 독립 PDFium 글리프 좌표와 대조한다.

PDFium은 로컬 검증 도구로만 사용하며 dochan 런타임 의존성이 아니다.
--baseline은 수정 전 같은 프로브 결과를 받아 원래 양성 모집단도 유지한다.
"""
import argparse
import json
import math
import signal
import unicodedata
from pathlib import Path

from dochan.pdf.annotations import DestinationResolver, attach_links, link_regions
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text


class ProbeDeadline(BaseException):
    """제품의 경고 변환에 흡수되지 않는 검증 시간 제한."""


def _inside(points, x, y):
    # dochan의 적중 함수를 호출하지 않는 독립 ray-casting 판정이다.
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _runs(value):
    if isinstance(value, dict):
        if value.get("link") and "text" in value:
            yield value
        for child in value.values():
            yield from _runs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _runs(child)


def _compact(text):
    return "".join(unicodedata.normalize("NFKC", text).split()).replace("\u00ad", "")


def _miner_glyphs(path, page_index):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTContainer
    def walk(node):
        if isinstance(node, LTChar):
            left, bottom, right, top = node.bbox
            yield node.get_text(), (left + right) / 2, (bottom + top) / 2
        elif isinstance(node, LTContainer):
            for child in node:
                yield from walk(child)
    for page in extract_pages(str(path), page_numbers=[page_index]):
        return list(walk(page))
    return []


def verify(path, text_tables=False):
    import pypdfium2 as pdfium
    pdf = PDFFile(path.read_bytes())
    pages = pdf.pages()
    if not pages or (pdf.encrypted and not pdf.decrypt_ok):
        return {"excluded": True}
    destinations = DestinationResolver(pdf, pages)
    areas = [link_regions(pdf, page, destinations) for page, _ in pages]
    if not any(areas):
        has_link = False
        for page, _resources in pages:
            annots = pdf.resolve(page.get("Annots"))
            if isinstance(annots, list):
                for ref in annots[:65536]:
                    annot = pdf.resolve(ref)
                    if isinstance(annot, dict) and str(annot.get("Subtype")) == "Link":
                        has_link = True
                        break
        return {"linkless": not has_link, "unresolved_only": has_link}
    document = PDFReader(text_tables=text_tables).read(str(path))
    encoded = to_dict(document)
    body = {}
    for run in _runs(encoded):
        provenance = run.get("provenance") or {}
        if provenance.get("path") == "annots":
            continue
        key = (provenance.get("page"), run["link"])
        body[key] = body.get(key, "") + run["text"]
    outputs = [to_markdown(document), to_plain_text(document), json.dumps(encoded, ensure_ascii=False)]
    missing = sorted({area.target for page_areas in areas for area in page_areas
                      if any(area.target not in output for output in outputs)})
    records = []
    final_run_mismatches = []
    reader = PDFReader()
    cache = {}
    with pdfium.PdfDocument(str(path)) as independent:
        for page_index, regions in enumerate(areas):
            if not regions:
                continue
            page = independent[page_index]
            textpage = page.get_textpage()
            try:
                glyphs = []
                for i in range(textpage.count_chars()):
                    char = textpage.get_text_range(i, 1)
                    if not char.strip():
                        continue
                    left, bottom, right, top = textpage.get_charbox(i)
                    glyphs.append((char, (left + right) / 2, (bottom + top) / 2))
            finally:
                textpage.close()
                page.close()
            native_page, resources = pages[page_index]
            extractor = ContentTextExtractor.from_fonts(reader._font_infos(pdf, resources, cache),
                                                        track_char_positions=True)
            fragments = extractor.extract_fragments(b"\n".join(reader._page_content_parts(pdf, native_page)))
            attach_links(fragments, regions, [])
            selected = []
            selected_by_target = {}
            for fragment in fragments:
                for first, last, target in fragment.link_spans:
                    selected_by_target[target] = selected_by_target.get(target, "") + fragment.text[first:last]
                    direction = math.hypot(fragment.dir_x, fragment.dir_y)
                    up = math.hypot(fragment.up_x, fragment.up_y)
                    for i in range(first, last):
                        distance = (fragment.char_offsets[i] + fragment.char_offsets[i + 1]) / 2
                        x = fragment.x + fragment.dir_x / direction * distance + fragment.up_x / up * fragment.size * 0.5
                        y = fragment.y + fragment.dir_y / direction * distance + fragment.up_y / up * fragment.size * 0.5
                        selected.append((fragment.text[i], x, y, target))
            for target, text in selected_by_target.items():
                final = body.get((page_index + 1, target), "")
                if _compact(final) not in _compact(text):
                    final_run_mismatches.append({"page": page_index + 1, "target": target,
                                                "attached": text, "final": final})
            alternate_glyphs = None
            for index, region in enumerate(regions):
                polygons = region.polygons
                expected = "".join(char for char, x, y in glyphs
                                   if any(_inside(polygon, x, y) for polygon in polygons))
                oracle = "PDFium"
                if "\ufffe" in expected:
                    if alternate_glyphs is None:
                        alternate_glyphs = _miner_glyphs(path, page_index)
                    expected = "".join(char for char, x, y in alternate_glyphs
                                       if any(_inside(polygon, x, y) for polygon in polygons))
                    oracle = "pdfminer (PDFium non-Unicode glyph)"
                actual = "".join(char for char, x, y, target in selected if target == region.target
                                 and any(_inside(polygon, x, y) for polygon in polygons))
                # 반복 머리글 등 최종 본문에서 제거된 런은 연결 성공에 세지 않는다.
                if _compact(actual) not in _compact(body.get((page_index + 1, region.target), "")):
                    actual = ""
                records.append({"page": page_index + 1, "annotation_index": index,
                                "target": region.target, "oracle": oracle,
                                "expected": expected, "actual": actual,
                                "status": ("deferred" if not actual else "match"
                                           if _compact(expected) == _compact(actual) else "mismatch")})
    return {"records": records, "missing_output_targets": missing,
            "final_run_mismatches": final_run_mismatches,
            "body_positive": bool(body)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--text-tables", action="store_true")
    args = parser.parse_args()
    def timeout(_signum, _frame):
        raise ProbeDeadline("document deadline")
    signal.signal(signal.SIGALRM, timeout)
    results = {}
    paths = [args.corpus / name for name in args.files] if args.files else sorted(args.corpus.glob("*.pdf"))
    for path in paths:
        try:
            signal.alarm(15)
            results[path.name] = verify(path, text_tables=args.text_tables)
        except (Exception, ProbeDeadline) as exc:
            results[path.name] = {"error": type(exc).__name__}
        finally:
            signal.alarm(0)
    records = [row for result in results.values() for row in result.get("records", [])]
    summary = {"documents": len(results), "body_documents": sum(bool(r.get("body_positive")) for r in results.values()),
               "resolved_link_documents": sum("records" in r for r in results.values()),
               "linkless_documents": sum(bool(r.get("linkless")) for r in results.values()),
               "unresolved_only_documents": sum(bool(r.get("unresolved_only")) for r in results.values()),
               "excluded_documents": sum(bool(r.get("excluded")) for r in results.values()),
               "match": sum(r["status"] == "match" for r in records),
               "mismatch": sum(r["status"] == "mismatch" for r in records),
               "deferred": sum(r["status"] == "deferred" for r in records),
               "deferred_with_drawn_text": sum(r["status"] == "deferred" and bool(r["expected"]) for r in records),
               "output_loss_documents": sum(bool(r.get("missing_output_targets")) for r in results.values()),
               "final_run_mismatches": sum(len(r.get("final_run_mismatches", [])) for r in results.values()),
               "errors": {name: result["error"] for name, result in results.items() if "error" in result}}
    if args.baseline:
        baseline = json.loads(args.baseline.read_text())["results"]
        positives = [name for name, result in baseline.items() if result.get("body_positive")]
        summary["baseline_positive_documents"] = len(positives)
        summary["baseline_positive_rechecked"] = sum("records" in results.get(name, {}) for name in positives)
        summary["baseline_external_positive_documents"] = sum(
            any(row.get("actual") and not row["target"].startswith("#") for row in result.get("records", []))
            for result in baseline.values())
    args.output.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
