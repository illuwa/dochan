"""Measure public HWP/HWPX structural budgets without building document models.

Run with Python 3.9: python -m scripts.probe_hwp_large_inventory CORPUS
    --private-pairs PRIVATE_DIRECTORY --output .codex-work/inventory.json
Private paths, filenames, content, and exception messages are never serialized.
Counts cover physical records/elements, including unselected XML switch branches.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import time
import zipfile

from dochan import cfb
from dochan.utils import safe_xml as etree

from dochan.hwp.distdoc import decode_distribution_section
from dochan.hwp.header import FileHeader
from dochan.utils.bounded_io import read_ole_stream, validate_file_size
from dochan.utils.safe_decompress import safe_zlib_decompress

RECORD_LIMIT = 200_000
CELL_LIMIT = 200_000
XML_LIMIT = 32 * 1024 * 1024
CHART_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"


def scan_records(data):
    """Scan bounded stream once. Do not allocate records, trees, or model cells."""
    out = Counter(bytes=len(data))
    offset = 0
    controls = []
    while offset + 4 <= len(data):
        word = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        tag, level, size = word & 1023, (word >> 10) & 1023, word >> 20
        if size == 4095:
            if offset + 4 > len(data):
                out["truncated"] += 1
                break
            size = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        if offset + size > len(data):
            out["truncated"] += 1
            break
        out["records"] += 1
        out["max_level"] = max(out["max_level"], level)
        while controls and controls[-1][0] >= level:
            controls.pop()
        if tag == 71 and size >= 4:
            controls.append([level, data[offset:offset + 4] == b" lbt", False])
        if tag == 77 and size >= 8:
            rows, cols = struct.unpack_from("<HH", data, offset + 4)
            grid = rows * cols
            out["tables"] += 1
            out["grid_cells"] += grid
            out["max_table_grid_cells"] = max(out["max_table_grid_cells"], grid)
            if controls and controls[-1][1]:
                controls[-1][2] = True
        if tag == 72:
            out["list_headers"] += 1
            # This is a physical table-cell header count. Captions (before TABLE)
            # and non-table controls are excluded without allocating a parse tree.
            if controls and controls[-1][1] and controls[-1][2] and size >= 30:
                out["table_cell_headers"] += 1
        offset += size
    out["trailing_bytes"] = len(data) - offset
    return dict(out)


def scan_hwp(path):
    validate_file_size(str(path))
    out = {"sections": [], "errors": []}
    with cfb.OleFileIO(str(path)) as ole:
        header = FileHeader.parse(read_ole_stream(ole, "FileHeader"))
        out["distribution"] = header.is_distribution
        out["track_change"] = header.is_track_change
        if header.is_encrypted or header.is_drm:
            out["errors"].append("encrypted_or_drm")
            return out
        names = ["/".join(parts) for parts in ole.listdir()]
        names = [n for n in names if n == "DocInfo" or
                 re.fullmatch(r"(?:BodyText|ViewText)/Section[0-9]+", n)]
        for name in sorted(names):
            try:
                data = read_ole_stream(ole, name)
                if name.startswith("ViewText/") and header.is_distribution:
                    data = decode_distribution_section(data, is_compressed=header.is_compressed)
                if header.is_compressed:
                    data = safe_zlib_decompress(data)
                item = scan_records(data)
                item["stream"] = name
                out["sections"].append(item)
            except Exception as exc:
                out["errors"].append(name + ":" + type(exc).__name__)
    return out


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def scan_hwpx(path):
    out = {"sections": [], "charts": [], "errors": [], "chart_refs": []}
    with zipfile.ZipFile(str(path)) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 512 * 1024 * 1024:
            out["errors"].append("archive_limit")
            return out
        for info in infos:
            is_section = re.fullmatch(r"Contents/section[0-9]+\.xml", info.filename)
            is_chart = "chart" in info.filename.lower() and info.filename.lower().endswith(".xml")
            if not (is_section or is_chart):
                continue
            try:
                item = Counter(bytes=info.file_size)
                # Streaming inventory deliberately measures XML beyond the runtime
                # 32 MiB part limit; the 512 MiB archive cap still bounds input.
                with archive.open(info) as stream:
                    context = etree.iterparse(stream, events=("start", "end"),
                                              max_bytes=512 * 1024 * 1024, clear=True)
                    child_points = []
                    for event, elem in context:
                        if event == "start":
                            child_points.append(0)
                            continue
                        actual_points = child_points.pop()
                        item["elements"] += 1
                        tag = local(elem.tag)
                        if tag == "tc":
                            item["cells"] += 1
                        elif tag == "tbl":
                            grid = integer(elem.get("rowCnt")) * integer(elem.get("colCnt"))
                            item["tables"] += 1
                            item["grid_cells"] += grid
                            item["max_table_grid_cells"] = max(item["max_table_grid_cells"], grid)
                        elif tag == "chart" and is_section:
                            item["chart_placements"] += 1
                            out["chart_refs"].append(elem.get("chartIDRef", ""))
                        if elem.tag == CHART_NS + "pt":
                            item["chart_points"] += 1
                            item["chart_max_index_plus_one"] = max(item["chart_max_index_plus_one"], integer(elem.get("idx")) + 1)
                            if child_points:
                                child_points[-1] += 1
                        elif elem.tag == CHART_NS + "ser":
                            item["chart_series"] += 1
                        elif elem.tag == CHART_NS + "ptCount":
                            declared = integer(elem.get("val"))
                            item["chart_declared_points"] += declared
                            item["chart_max_cache_declared_points"] = max(item["chart_max_cache_declared_points"], declared)
                        if isinstance(elem.tag, str) and elem.tag.startswith(CHART_NS):
                            item["chart_max_cache_actual_points"] = max(item["chart_max_cache_actual_points"], actual_points)
                item = dict(item)
                item["stream"] = info.filename
                out["sections" if is_section else "charts"].append(item)
            except etree.ForbiddenDTD:
                out["errors"].append("doctype")
            except Exception as exc:
                out["errors"].append(type(exc).__name__)
    return out


def metrics(doc):
    values = {}
    for storage in ("BodyText", "ViewText", "DocInfo"):
        parts = [s for s in doc["sections"] if s["stream"].split("/")[0] == storage]
        if parts:
            for metric in ("records", "grid_cells", "table_cell_headers", "list_headers", "bytes"):
                values[storage + ".document_" + metric] = sum(s.get(metric, 0) for s in parts)
                values[storage + ".max_section_" + metric] = max(s.get(metric, 0) for s in parts)
            values[storage + ".max_table_grid_cells"] = max(s.get("max_table_grid_cells", 0) for s in parts)
    if "charts" in doc:
        for metric in ("cells", "grid_cells", "bytes", "elements", "chart_placements"):
            values["hwpx.document_" + metric] = sum(s.get(metric, 0) for s in doc["sections"])
            values["hwpx.max_section_" + metric] = max((s.get(metric, 0) for s in doc["sections"]), default=0)
        values["hwpx.max_table_grid_cells"] = max((s.get("max_table_grid_cells", 0) for s in doc["sections"]), default=0)
        values["hwpx.chart_parts"] = len(doc["charts"])
        chart_parts = {s["stream"]: s for s in doc["charts"]}
        values["hwpx.unresolved_chart_refs"] = sum(ref not in chart_parts for ref in doc["chart_refs"])
        values["hwpx.resolved_chart_refs"] = sum(ref in chart_parts for ref in doc["chart_refs"])
        for metric in ("chart_points", "chart_series", "bytes"):
            values["hwpx.placed_" + metric] = sum(chart_parts.get(ref, {}).get(metric, 0) for ref in doc["chart_refs"])
        values["hwpx.max_chart_part_bytes"] = max((s.get("bytes", 0) for s in doc["charts"]), default=0)
        for metric in ("chart_points", "chart_series", "chart_declared_points"):
            values["hwpx.document_" + metric] = sum(s.get(metric, 0) for s in doc["charts"])
        for metric in ("chart_max_index_plus_one", "chart_max_cache_declared_points", "chart_max_cache_actual_points", "chart_points", "chart_series"):
            values["hwpx.max_part_" + metric] = max((s.get(metric, 0) for s in doc["charts"]), default=0)
    return values


def summarize(documents, private=False):
    keys = sorted({k for d in documents for k in d["metrics"]})
    out = {}
    for key in keys:
        rows = sorted(((d["metrics"][key], d) for d in documents if key in d["metrics"]), key=lambda row: row[0], reverse=True)
        ascending = sorted(row[0] for row in rows)
        item = {"count": len(rows), "max": ascending[-1], "p50": ascending[(len(rows) - 1) // 2], "p95": ascending[int((len(rows) - 1) * .95)], "p99": ascending[int((len(rows) - 1) * .99)]}
        item["top20"] = [({"value": value} if private else {"file": doc["file"], "value": value}) for value, doc in rows[:20]]
        out[key] = item
    return out


def summarize_sections(documents, private=False):
    """Each physical section contributes one observation, not one document maximum."""
    grouped = {}
    for doc in documents:
        for section in doc["sections"]:
            stream = section["stream"]
            family = "hwpx" if "charts" in doc else stream.split("/")[0]
            if family in ("BodyText", "ViewText"):
                names = ("records", "grid_cells", "table_cell_headers", "bytes")
            elif family == "hwpx":
                names = ("cells", "grid_cells", "chart_placements", "bytes")
            else:
                continue
            for name in names:
                row = {"value": section.get(name, 0)}
                if not private:
                    row.update(file=doc["file"], stream=stream)
                grouped.setdefault(family + "." + name, []).append(row)
    result = {}
    for key, rows in grouped.items():
        ranked = sorted(rows, key=lambda row: row["value"], reverse=True)
        ordered = sorted(row["value"] for row in rows)
        n = len(ordered)
        result[key] = {
            "n": n, "count": n, "p50": ordered[(n - 1) // 2],
            "p95": ordered[int((n - 1) * .95)],
            "p99": ordered[int((n - 1) * .99)], "max": ordered[-1],
            "top20": ranked[:20],
        }
    return result


def inventory(paths, private=False):
    documents = []
    errors = Counter()
    for index, path in enumerate(paths):
        try:
            with path.open("rb") as source:
                magic = source.read(8)
            kind = "hwp" if magic == bytes.fromhex("d0cf11e0a1b11ae1") else "hwpx" if magic.startswith(b"PK") else path.suffix.lower()[1:]
            doc = scan_hwp(path) if kind == "hwp" else scan_hwpx(path)
            doc["detected_format"] = kind
        except Exception as exc:
            doc = {"sections": [], "errors": [type(exc).__name__]}
        doc["metrics"] = metrics(doc)
        if not private:
            doc["file"] = path.name
            doc["corpus_folder"] = path.parent.name
        documents.append(doc)
        errors.update(doc["errors"])
        if (index + 1) % 250 == 0:
            print("%s scanned %d/%d" % ("private" if private else "public", index + 1, len(paths)), flush=True)
    exceeded = []
    thresholds = {
        "BodyText.max_section_records": RECORD_LIMIT,
        "ViewText.max_section_records": RECORD_LIMIT,
        "DocInfo.max_section_records": RECORD_LIMIT,
        "BodyText.document_grid_cells": CELL_LIMIT,
        "ViewText.document_grid_cells": CELL_LIMIT,
        "hwpx.document_grid_cells": CELL_LIMIT,
        "hwpx.document_cells": CELL_LIMIT,
        "hwpx.max_section_bytes": XML_LIMIT,
        "hwpx.document_chart_placements": 256,
        "hwpx.document_chart_series": 1024,
        "hwpx.document_chart_points": CELL_LIMIT,
        "hwpx.placed_chart_points": CELL_LIMIT,
        "hwpx.placed_chart_series": 1024,
        "hwpx.placed_bytes": 32 * 1024 * 1024,
        "hwpx.max_chart_part_bytes": 4 * 1024 * 1024,
        "hwpx.max_part_chart_series": 128,
        "hwpx.max_part_chart_points": 50000,
        "hwpx.max_part_chart_max_cache_actual_points": 10000,
        "hwpx.max_part_chart_max_cache_declared_points": 10000,
        "hwpx.max_part_chart_max_index_plus_one": 10000,
    }
    for doc in documents:
        for metric, limit in thresholds.items():
            value = doc["metrics"].get(metric, 0)
            if value > limit:
                row = {"metric": metric, "value": value, "baseline_limit": limit}
                if not private:
                    row["file"] = doc["file"]
                exceeded.append(row)
    result = {"files": len(paths), "detected_formats": dict(Counter(d.get("detected_format", "unknown") for d in documents)), "errors": dict(errors), "summary": summarize(documents, private), "section_summary": summarize_sections(documents, private), "baseline_exceeded": exceeded}
    if not private:
        result["documents"] = documents
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--private-pairs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    result = {"baseline_limits": {"hwp_records_per_stream": RECORD_LIMIT, "hwp_document_cells": CELL_LIMIT, "hwpx_document_cells": CELL_LIMIT, "hwpx_chart_points": CELL_LIMIT}}
    for extension in ("hwp", "hwpx"):
        paths = sorted((args.corpus / extension).glob("*." + extension))
        result[extension] = inventory(paths)
    additional = sorted(p for folder in (args.corpus / "hwp", args.corpus / "hwpx")
                        for p in folder.iterdir()
                        if p.suffix.lower() in (".hwp", ".hwpx")
                        and p.suffix != "." + folder.name)
    result["additional_public"] = inventory(additional)
    if args.private_pairs:
        paths = sorted(p for p in args.private_pairs.rglob("*") if p.suffix.lower() in (".hwp", ".hwpx"))
        result["private_aggregate"] = inventory(paths, private=True)
    result["elapsed_seconds"] = time.perf_counter() - start
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Saved inventory; %.2f seconds" % result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main()
