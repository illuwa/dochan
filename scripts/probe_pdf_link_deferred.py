"""Classify deferred public PDF link annotations against independent glyphs."""
import argparse
import collections
import json
import math
from pathlib import Path

from dochan.pdf.annotations import DestinationResolver, _contains, _on_boundary, link_regions
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from scripts.probe_pdf_link_boundaries import _compact


def classify(path, deferred):
    pdf = PDFFile(path.read_bytes())
    pages = pdf.pages()
    areas = [link_regions(pdf, page, DestinationResolver(pdf, pages)) for page, _ in pages]
    reader = PDFReader()
    cache = {}
    by_page = collections.defaultdict(list)
    for record in deferred:
        by_page[record["page"] - 1].append(record)
    result = []
    for page_index, records in by_page.items():
        page, resources = pages[page_index]
        extractor = ContentTextExtractor.from_fonts(
            reader._font_infos(pdf, resources, cache), track_char_positions=True)
        if hasattr(reader, "_configure_form_extractor"):
            reader._configure_form_extractor(extractor, pdf, resources, cache)
        fragments = extractor.extract_fragments(
            b"\n".join(reader._page_content_parts(pdf, page)))
        regions = areas[page_index]
        for record in records:
            index = record["annotation_index"]
            region = regions[index]
            centers = []
            cuts = []
            inward_cuts = []
            outward_cuts = []
            shared = []
            unreliable = 0
            for frag in fragments:
                for polygon in region.polygons:
                    low = min(y for _, y in polygon)
                    high = max(y for _, y in polygon)
                    if (not frag.link_geometry_reliable or
                            len(frag.char_offsets) != len(frag.text) + 1):
                        if min(frag.y, frag.y + frag.size) <= high and max(frag.y, frag.y + frag.size) >= low:
                            unreliable += 1
                if not frag.link_geometry_reliable or len(frag.char_offsets) != len(frag.text) + 1:
                    continue
                direction = math.hypot(frag.dir_x, frag.dir_y)
                up = math.hypot(frag.up_x, frag.up_y)
                if not direction or not up or not frag.size:
                    continue
                ux, uy = frag.dir_x / direction, frag.dir_y / direction
                vx, vy = frag.up_x / up, frag.up_y / up
                for char_index, char in enumerate(frag.text):
                    if char.isspace():
                        continue
                    first, last = frag.char_offsets[char_index:char_index + 2]
                    middle = (first + last) / 2
                    x = frag.x + ux * middle + vx * frag.size * 0.5
                    y = frag.y + uy * middle + vy * frag.size * 0.5
                    hit = any(_contains(polygon, x, y) for polygon in region.polygons)
                    if hit:
                        centers.append(char)
                        for other_index, other in enumerate(regions):
                            if other_index != index and other.target != region.target and any(
                                    _contains(polygon, x, y) for polygon in other.polygons):
                                shared.append(char)
                                break
                    for polygon in region.polygons:
                        for distance in (first, last):
                            ex = frag.x + ux * distance + vx * frag.size * 0.5
                            ey = frag.y + uy * distance + vy * frag.size * 0.5
                            if (_contains(polygon, ex, ey) != _contains(polygon, x, y)
                                    and not _on_boundary(polygon, ex, ey)):
                                cuts.append(char)
                                (inward_cuts if hit else outward_cuts).append(char)
                                break
            if not record["expected"]:
                cause = "no_pdfium_glyph"
            elif shared:
                cause = "different_destinations_overlap"
            elif unreliable:
                cause = "unreliable_text_geometry"
            elif cuts and centers:
                cause = "glyph_boundary_cut"
            elif not centers:
                cause = "no_native_center"
            else:
                cause = "later_layout_or_other"
            result.append({"file": path.name, "page": page_index + 1, "annotation_index": index,
                           "cause": cause, "oracle_chars": len(record["expected"]),
                           "native_center_chars": len(centers), "cut_chars": len(cuts),
                           "native_center_matches": _compact("".join(centers)) == _compact(record["expected"]),
                           "inward_cut_chars": len(inward_cuts),
                           "outward_cut_chars": len(outward_cuts),
                           "shared_chars": len(shared), "unreliable_fragments": unreliable,
                           "quads": len(region.polygons) > 1})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())["results"]
    rows = []
    for name, result in baseline.items():
        deferred = [record for record in result.get("records", []) if record["status"] == "deferred"]
        if deferred:
            rows.extend(classify(args.corpus / name, deferred))
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(json.dumps(collections.Counter(row["cause"] for row in rows), ensure_ascii=False))


if __name__ == "__main__":
    main()
