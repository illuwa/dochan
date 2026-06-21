"""Benchmark dochan against optional local competitor installations."""
import argparse
import json
import posixpath
import re
import signal
import sys
import zipfile
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Callable, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OFFICE_FORMATS = ("docx", "pptx", "xlsx")
CONVERTER_NAMES = ("dochan", "markitdown", "docling")
DEFAULT_CONVERSION_TIMEOUT_SECONDS = 120.0
JSON_PROFILE_KEYS = (
    "json_asset_count",
    "json_section_provenance_count",
    "json_table_count",
    "json_table_cell_count",
    "json_cell_provenance_count",
    "json_cell_paragraph_count",
    "json_run_provenance_count",
    "json_rich_run_count",
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[(.*?)\]\(([^)]+)\)")


def iter_input_files(root: Path, formats: Iterable[str] = OFFICE_FORMATS) -> List[Path]:
    suffixes = {f".{fmt.lower().lstrip('.')}" for fmt in formats}
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def load_expectations(root: Path) -> Dict[str, dict]:
    manifest = root / "expected.json"
    if not manifest.exists():
        return {}
    return json.loads(manifest.read_text(encoding="utf-8"))


def output_capture_path(output_root: Path, converter: str, relative_input: Path, run_index: int) -> Path:
    return output_root / converter / relative_input.parent / f"{relative_input.name}.run{run_index}.md"


def score_output(output: str, expectation: dict, structured_profile: dict = None) -> dict:
    structured_profile = structured_profile or {}
    expected_text = expectation.get("expected_text", [])
    expected_markdown = expectation.get("expected_markdown", [])
    expected_tables = expectation.get("expected_tables", [])
    expected_table_rows = expectation.get("expected_table_rows", [])
    expected_assets = expectation.get("expected_assets", [])
    expected_empty_total = 1 if expectation.get("expected_empty") is True else 0
    expected_empty_found = 1 if expected_empty_total and not output.strip() else 0
    table_cells = [
        str(cell)
        for table in expected_tables
        for row in table
        for cell in row
        if str(cell).strip()
    ]

    text_found = sum(1 for text in expected_text if str(text) in output)
    markdown_found = sum(1 for snippet in expected_markdown if str(snippet) in output)
    cells_found = sum(1 for cell in table_cells if _contains_table_cell(output, cell))
    table_rows_found = sum(1 for row in expected_table_rows if _contains_table_row(output, row))
    asset_paths = set(structured_profile.get("json_asset_paths", []))
    assets_found = sum(1 for asset in expected_assets if str(asset) in asset_paths)
    total = (
        len(expected_text)
        + len(expected_markdown)
        + len(table_cells)
        + len(expected_table_rows)
        + len(expected_assets)
        + expected_empty_total
    )
    found = text_found + markdown_found + cells_found + table_rows_found + assets_found + expected_empty_found
    return {
        "expected_text_total": len(expected_text),
        "expected_text_found": text_found,
        "expected_markdown_total": len(expected_markdown),
        "expected_markdown_found": markdown_found,
        "expected_table_cells_total": len(table_cells),
        "expected_table_cells_found": cells_found,
        "expected_table_rows_total": len(expected_table_rows),
        "expected_table_rows_found": table_rows_found,
        "expected_assets_total": len(expected_assets),
        "expected_assets_found": assets_found,
        "expected_empty_total": expected_empty_total,
        "expected_empty_found": expected_empty_found,
        "accuracy": found / total if total else None,
    }


def profile_output(output: str) -> dict:
    lines = output.splitlines()
    return {
        "line_count": len(lines),
        "word_count": len(re.findall(r"\S+", output)),
        "unique_text_token_count": len(_unique_text_tokens(output)),
        "heading_count": len(_meaningful_markdown_headings(lines)),
        "markdown_table_row_count": len(_markdown_table_rows(output, include_empty=False)),
        "link_count": len(re.findall(r"<(?:https?://|mailto:|#)[^>]+>", output)),
        "image_reference_count": len(_meaningful_markdown_image_refs(output)),
        "comment_marker_count": output.count("[comment"),
        "bookmark_marker_count": output.count("[bookmark:"),
        "formula_marker_count": output.count("(="),
    }


def profile_structured_json(payload: dict) -> dict:
    sections = payload.get("sections", []) if isinstance(payload, dict) else []
    assets = payload.get("assets", []) if isinstance(payload, dict) else []
    profile = {
        "json_asset_count": len(assets),
        "json_asset_paths": [
            asset.get("source_path", "")
            for asset in assets
            if isinstance(asset, dict) and asset.get("source_path")
        ],
        "json_section_provenance_count": 0,
        "json_table_count": 0,
        "json_table_cell_count": 0,
        "json_cell_provenance_count": 0,
        "json_cell_paragraph_count": 0,
        "json_run_provenance_count": 0,
        "json_rich_run_count": 0,
    }

    for section in sections:
        if section.get("provenance"):
            profile["json_section_provenance_count"] += 1
        for element in section.get("elements", []):
            _profile_json_element(element, profile)
    return profile


def _profile_json_element(element: dict, profile: dict) -> None:
    if not isinstance(element, dict):
        return
    if element.get("type") == "paragraph":
        for run in element.get("runs", []):
            _profile_json_run(run, profile)
        return
    if element.get("type") in {"footnote", "endnote", "comment"}:
        for child in element.get("elements", []):
            _profile_json_element(child, profile)
        return
    if element.get("type") != "table":
        return

    profile["json_table_count"] += 1
    for row in element.get("rows", []):
        for cell in row:
            if not isinstance(cell, dict):
                continue
            profile["json_table_cell_count"] += 1
            if cell.get("provenance"):
                profile["json_cell_provenance_count"] += 1
            paragraphs = cell.get("paragraphs", [])
            profile["json_cell_paragraph_count"] += len(paragraphs)
            for paragraph in paragraphs:
                _profile_json_element(paragraph, profile)


def _profile_json_run(run: dict, profile: dict) -> None:
    if not isinstance(run, dict):
        return
    if run.get("provenance"):
        profile["json_run_provenance_count"] += 1
    if any(run.get(key) for key in ("bold", "italic", "underline", "strikeout", "superscript", "subscript")):
        profile["json_rich_run_count"] += 1


def _unique_text_tokens(output: str) -> set:
    stripped = re.sub(r"https?://\S+", " ", output)
    stripped = re.sub(r"mailto:\S+", " ", stripped)
    stripped = MARKDOWN_IMAGE_RE.sub(" ", stripped)
    stripped = re.sub(r"\[[^\]]+\]", " ", stripped)
    stripped = re.sub(r"\bUnnamed:\s*\d+\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bNaN\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bNaT\b", " ", stripped, flags=re.IGNORECASE)
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9가-힣]+", stripped)
        if not token.isdigit()
    }


def _meaningful_markdown_image_refs(output: str) -> List[Tuple[str, str]]:
    return [
        (alt, target)
        for alt, target in MARKDOWN_IMAGE_RE.findall(output)
        if not _is_generated_shape_placeholder_image(alt, target)
    ]


def _is_generated_shape_placeholder_image(alt: str, target: str) -> bool:
    if alt.strip():
        return False
    name = posixpath.basename(target.strip())
    return re.fullmatch(r"Shape\d+\.(?:png|jpe?g|gif|bmp|wmf|emf)", name, flags=re.IGNORECASE) is not None


def _meaningful_markdown_headings(lines: List[str]) -> List[str]:
    headings = []
    generic = {"sheet", "chart", "notes", "notes:"}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        text = stripped.lstrip("#").strip()
        normalized = text.lower().rstrip(":").strip()
        if (
            not text
            or normalized in generic
            or re.fullmatch(r"sheet\s*\d+", normalized)
            or re.fullmatch(r"hoja\s*\d+", normalized)
        ):
            continue
        headings.append(text)
    return headings


def _contains_table_cell(output: str, value: str) -> bool:
    escaped = re.escape(str(value))
    return re.search(rf"(^|\||\s){escaped}($|\||\s)", output) is not None


def _contains_table_row(output: str, expected_row: List[object]) -> bool:
    expected = [str(cell).strip() for cell in expected_row]
    return any(row == expected for row in _markdown_table_rows(output))


def _row_success(row: dict) -> bool:
    if row.get("error"):
        return False
    if row.get("expected_empty_total"):
        return row.get("expected_empty_found", 0) == row.get("expected_empty_total", 0)
    if row.get("input_semantic_empty"):
        return True
    return bool(row.get("nonempty"))


def input_has_ooxml_semantic_signal(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in {".docx", ".pptx", ".xlsx"}:
        return True
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if _has_media_asset(names, suffix):
                return True
            if suffix == ".docx" and _docx_archive_has_alt_chunk_signal(archive):
                return True
            for name in names:
                if not name.endswith(".xml") or not _is_semantic_xml_part(name, suffix):
                    continue
                try:
                    xml = archive.read(name).decode("utf-8", "ignore")
                except Exception:
                    return True
                if _xml_has_visible_text(xml):
                    return True
                if suffix == ".xlsx" and _worksheet_has_value(xml):
                    return True
                if suffix == ".xlsx" and name == "xl/workbook.xml" and _workbook_has_meaningful_sheet_name(xml):
                    return True
                if suffix == ".docx" and _docx_has_visible_object(xml):
                    return True
                if suffix in {".pptx", ".xlsx"} and _drawingml_has_visible_object(xml):
                    return True
    except Exception:
        return True
    return False


def _docx_archive_has_alt_chunk_signal(archive: zipfile.ZipFile) -> bool:
    try:
        rels = archive.read("word/_rels/document.xml.rels").decode("utf-8", "ignore")
    except Exception:
        return False
    for relationship in re.findall(r"<(?:[A-Za-z0-9_]+:)?Relationship\b[^>]*>", rels):
        if "/aFChunk" not in relationship:
            continue
        target_match = re.search(r'\bTarget="([^"]+)"', relationship)
        if not target_match:
            continue
        target = target_match.group(1)
        part = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("word", target))
        if part not in archive.namelist():
            continue
        try:
            data = archive.read(part)
        except Exception:
            continue
        if _html_like_bytes_have_text(data):
            return True
    return False


def _html_like_bytes_have_text(data: bytes) -> bool:
    text = data.decode("utf-8", "ignore")
    text = re.sub(r"<(?:script|style)\b[\s\S]*?</(?:script|style)>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return bool(_normalize_semantic_text(text))


def _normalize_semantic_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_media_asset(names: List[str], suffix: str) -> bool:
    media_prefixes = {
        ".docx": ("word/media/",),
        ".pptx": ("ppt/media/",),
        ".xlsx": ("xl/media/",),
    }
    return any(name.startswith(media_prefixes[suffix]) for name in names)


def _is_semantic_xml_part(name: str, suffix: str) -> bool:
    if name.startswith("docProps/"):
        return name.endswith("core.xml")
    if suffix == ".docx":
        return name.startswith("word/") and not any(
            name.endswith(part)
            for part in (
                "settings.xml",
                "styles.xml",
                "numbering.xml",
                "fontTable.xml",
                "webSettings.xml",
            )
        ) and not name.startswith("word/theme/")
    if suffix == ".pptx":
        return name.startswith(("ppt/slides/", "ppt/notesSlides/", "ppt/slideMasters/", "ppt/slideLayouts/", "ppt/charts/", "ppt/comments", "ppt/commentAuthors"))
    if suffix == ".xlsx":
        return name.startswith(("xl/workbook.xml", "xl/sharedStrings.xml", "xl/worksheets/", "xl/comments", "xl/drawings/", "xl/charts/"))
    return False


def _xml_has_visible_text(xml: str) -> bool:
    return any(
        _strip_xml_text(text)
        for text in re.findall(r"<(?:[A-Za-z0-9_]+:)?(?:t|instrText)[^>]*>(.*?)</(?:[A-Za-z0-9_]+:)?(?:t|instrText)>", xml)
    )


def _worksheet_has_value(xml: str) -> bool:
    return any(
        _strip_xml_text(value)
        for value in re.findall(r"<(?:[A-Za-z0-9_]+:)?v[^>]*>(.*?)</(?:[A-Za-z0-9_]+:)?v>", xml)
    )


def _workbook_has_meaningful_sheet_name(xml: str) -> bool:
    for name in re.findall(r'<(?:[A-Za-z0-9_]+:)?sheet\b[^>]*\bname="([^"]+)"', xml):
        normalized = name.strip().lower()
        if not re.fullmatch(r"(?:sheet|hoja)\d+", normalized):
            return True
    return False


def _docx_has_visible_object(xml: str) -> bool:
    return "<w:drawing" in xml or "<v:imagedata" in xml


def _drawingml_has_visible_object(xml: str) -> bool:
    return "<a:blip" in xml or "<c:chart" in xml


def _strip_xml_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _markdown_table_rows(output: str, include_empty: bool = True) -> List[List[str]]:
    rows = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if not include_empty and not any(_profile_cell_has_signal(cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _profile_cell_has_signal(cell: str) -> bool:
    stripped = cell.strip()
    if not stripped:
        return False
    if re.fullmatch(r"nan", stripped, flags=re.IGNORECASE):
        return False
    if re.fullmatch(r"nat", stripped, flags=re.IGNORECASE):
        return False
    if re.fullmatch(r"Unnamed:\s*\d+", stripped, flags=re.IGNORECASE):
        return False
    return True


def _convert_dochan(path: Path) -> str:
    from dochan import Dochan

    return Dochan(str(path)).to_markdown()


def _convert_dochan_profiled(path: Path) -> Tuple[str, dict]:
    from dochan import Dochan

    converter = Dochan(str(path))
    return converter.to_markdown(), profile_structured_json(converter.to_dict())


def _convert_markitdown(path: Path) -> str:
    from markitdown import MarkItDown

    result = MarkItDown().convert(str(path))
    return getattr(result, "text_content", "") or getattr(result, "markdown", "")


def _convert_docling(path: Path) -> str:
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(path))
    document = result.document
    if hasattr(document, "export_to_markdown"):
        return document.export_to_markdown()
    return str(document)


def _run_with_timeout(callback: Callable[[], Tuple[str, dict]], timeout_seconds: float) -> Tuple[str, dict]:
    if not timeout_seconds or timeout_seconds <= 0:
        return callback()

    def raise_timeout(_signum, _frame):
        raise TimeoutError(f"conversion timed out after {timeout_seconds:g}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    signal.signal(signal.SIGALRM, raise_timeout)
    try:
        return callback()
    finally:
        signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])
        signal.signal(signal.SIGALRM, previous_handler)


def inspect_converter_availability(converter_names: Iterable[str] = CONVERTER_NAMES) -> Dict[str, dict]:
    status = {}
    for name in converter_names:
        normalized = name.strip().lower()
        if normalized == "dochan":
            status[normalized] = {"available": True, "error": ""}
        elif normalized == "markitdown":
            try:
                import markitdown  # noqa: F401
            except Exception as exc:
                status[normalized] = {"available": False, "error": repr(exc)}
            else:
                status[normalized] = {"available": True, "error": ""}
        elif normalized == "docling":
            try:
                import docling  # noqa: F401
            except Exception as exc:
                status[normalized] = {"available": False, "error": repr(exc)}
            else:
                status[normalized] = {"available": True, "error": ""}
        else:
            status[normalized] = {"available": False, "error": f"Unknown converter: {name}"}
    return status


def discover_converters(converter_names: Iterable[str] = CONVERTER_NAMES) -> Dict[str, Callable[[Path], str]]:
    status = inspect_converter_availability(converter_names)
    converters = {}
    registry = {
        "dochan": _convert_dochan,
        "markitdown": _convert_markitdown,
        "docling": _convert_docling,
    }
    for name in converter_names:
        normalized = name.strip().lower()
        if status.get(normalized, {}).get("available") and normalized in registry:
            converters[normalized] = registry[normalized]
    return converters


def summarize_results(results: List[dict]) -> List[dict]:
    grouped: Dict[Tuple[str, str, str], List[dict]] = {}
    for row in results:
        key = (row["converter"], row["file"], row["format"])
        grouped.setdefault(key, []).append(row)

    summary = []
    for (converter, file_path, file_format), rows in sorted(grouped.items()):
        seconds = [row["seconds"] for row in rows]
        accuracies = [row["accuracy"] for row in rows if row.get("accuracy") is not None]
        success_count = sum(1 for row in rows if _row_success(row))
        item = {
            "converter": converter,
            "file": file_path,
            "format": file_format,
            "runs": len(rows),
            "best_seconds": min(seconds),
            "median_seconds": median(seconds),
            "mean_accuracy": mean(accuracies) if accuracies else None,
            "success_rate": success_count / len(rows) if rows else 0.0,
            "median_chars": median(row.get("chars", 0) for row in rows),
            "median_table_rows": median(row.get("markdown_table_row_count", 0) for row in rows),
            "median_headings": median(row.get("heading_count", 0) for row in rows),
            "median_links": median(row.get("link_count", 0) for row in rows),
            "median_image_references": median(row.get("image_reference_count", 0) for row in rows),
            "median_comments": median(row.get("comment_marker_count", 0) for row in rows),
            "median_bookmarks": median(row.get("bookmark_marker_count", 0) for row in rows),
            "median_formula_markers": median(row.get("formula_marker_count", 0) for row in rows),
            "median_unique_text_tokens": median(row.get("unique_text_token_count", 0) for row in rows),
            "representative_output_path": _representative_output_path(rows),
        }
        item.update(_json_profile_medians(rows))
        summary.append(item)
    return summary


def summarize_by_format(results: List[dict]) -> List[dict]:
    grouped: Dict[Tuple[str, str], List[dict]] = {}
    for row in results:
        key = (row["converter"], row["format"])
        grouped.setdefault(key, []).append(row)

    summary = []
    for (converter, file_format), rows in sorted(grouped.items()):
        seconds = [row["seconds"] for row in rows]
        accuracies = [row["accuracy"] for row in rows if row.get("accuracy") is not None]
        success_count = sum(1 for row in rows if _row_success(row))
        item = {
            "converter": converter,
            "format": file_format,
            "files": len({row["file"] for row in rows}),
            "runs": len(rows),
            "success_rate": success_count / len(rows) if rows else 0.0,
            "best_seconds": min(seconds),
            "median_seconds": median(seconds),
            "mean_accuracy": mean(accuracies) if accuracies else None,
            "median_chars": median(row.get("chars", 0) for row in rows),
            "median_table_rows": median(row.get("markdown_table_row_count", 0) for row in rows),
            "median_headings": median(row.get("heading_count", 0) for row in rows),
            "median_links": median(row.get("link_count", 0) for row in rows),
            "median_image_references": median(row.get("image_reference_count", 0) for row in rows),
            "median_comments": median(row.get("comment_marker_count", 0) for row in rows),
            "median_bookmarks": median(row.get("bookmark_marker_count", 0) for row in rows),
            "median_formula_markers": median(row.get("formula_marker_count", 0) for row in rows),
            "median_unique_text_tokens": median(row.get("unique_text_token_count", 0) for row in rows),
            "representative_output_path": _representative_output_path(rows),
        }
        item.update(_json_profile_medians(rows))
        summary.append(item)
    return summary


def _json_profile_medians(rows: List[dict]) -> dict:
    return {
        f"median_{key}": median(row.get(key, 0) for row in rows)
        for key in JSON_PROFILE_KEYS
    }


def _representative_output_path(rows: List[dict]) -> str:
    for row in sorted(rows, key=lambda item: item.get("run", 0)):
        output_path = row.get("output_path", "")
        if output_path:
            return output_path
    return ""


def compare_against_dochan(format_summary: List[dict]) -> List[dict]:
    by_format_converter = {
        (row["format"], row["converter"]): row
        for row in format_summary
    }
    comparisons = []
    for row in sorted(format_summary, key=lambda item: (item["format"], item["converter"])):
        competitor = row["converter"]
        if competitor == "dochan":
            continue

        file_format = row["format"]
        dochan = by_format_converter.get((file_format, "dochan"))
        comparison = {
            "format": file_format,
            "competitor": competitor,
            "dochan_available": dochan is not None,
            "competitor_available": True,
            "dochan_median_seconds": _metric(dochan, "median_seconds"),
            "competitor_median_seconds": row.get("median_seconds"),
            "speedup_vs_competitor": _ratio(row.get("median_seconds"), _metric(dochan, "median_seconds")),
            "dochan_mean_accuracy": _metric(dochan, "mean_accuracy"),
            "competitor_mean_accuracy": row.get("mean_accuracy"),
            "accuracy_delta": _delta(_metric(dochan, "mean_accuracy"), row.get("mean_accuracy")),
            "dochan_success_rate": _metric(dochan, "success_rate"),
            "competitor_success_rate": row.get("success_rate"),
            "success_rate_delta": _delta(_metric(dochan, "success_rate"), row.get("success_rate")),
            "median_chars_delta": _delta(_metric(dochan, "median_chars"), row.get("median_chars")),
            "median_table_rows_delta": _delta(_metric(dochan, "median_table_rows"), row.get("median_table_rows")),
            "median_headings_delta": _delta(_metric(dochan, "median_headings"), row.get("median_headings")),
            "median_links_delta": _delta(_metric(dochan, "median_links"), row.get("median_links")),
            "median_image_references_delta": _delta(
                _metric(dochan, "median_image_references"),
                row.get("median_image_references"),
            ),
            "median_comments_delta": _delta(_metric(dochan, "median_comments"), row.get("median_comments")),
            "median_bookmarks_delta": _delta(_metric(dochan, "median_bookmarks"), row.get("median_bookmarks")),
            "median_formula_markers_delta": _delta(
                _metric(dochan, "median_formula_markers"),
                row.get("median_formula_markers"),
            ),
            "median_unique_text_tokens_delta": _delta(
                _metric(dochan, "median_unique_text_tokens"),
                row.get("median_unique_text_tokens"),
            ),
        }
        comparison.update(_json_profile_deltas(dochan, row))
        comparisons.append(comparison)
    return comparisons


def compare_files_against_dochan(summary: List[dict]) -> List[dict]:
    by_file_converter = {
        (row["file"], row["converter"]): row
        for row in summary
    }
    comparisons = []
    for row in sorted(summary, key=lambda item: (item["format"], item["file"], item["converter"])):
        competitor = row["converter"]
        if competitor == "dochan":
            continue

        file_path = row["file"]
        dochan = by_file_converter.get((file_path, "dochan"))
        comparisons.append(_comparison_row(row, dochan, competitor, {"file": file_path, "format": row["format"]}))
    return comparisons


def _comparison_row(row: dict, dochan: dict, competitor: str, base: dict) -> dict:
    comparison = dict(base)
    comparison.update({
        "competitor": competitor,
        "dochan_available": dochan is not None,
        "competitor_available": True,
        "dochan_median_seconds": _metric(dochan, "median_seconds"),
        "competitor_median_seconds": row.get("median_seconds"),
        "speedup_vs_competitor": _ratio(row.get("median_seconds"), _metric(dochan, "median_seconds")),
        "dochan_mean_accuracy": _metric(dochan, "mean_accuracy"),
        "competitor_mean_accuracy": row.get("mean_accuracy"),
        "accuracy_delta": _delta(_metric(dochan, "mean_accuracy"), row.get("mean_accuracy")),
        "dochan_success_rate": _metric(dochan, "success_rate"),
        "competitor_success_rate": row.get("success_rate"),
        "success_rate_delta": _delta(_metric(dochan, "success_rate"), row.get("success_rate")),
        "median_chars_delta": _delta(_metric(dochan, "median_chars"), row.get("median_chars")),
        "median_table_rows_delta": _delta(_metric(dochan, "median_table_rows"), row.get("median_table_rows")),
        "median_headings_delta": _delta(_metric(dochan, "median_headings"), row.get("median_headings")),
        "median_links_delta": _delta(_metric(dochan, "median_links"), row.get("median_links")),
        "median_image_references_delta": _delta(
            _metric(dochan, "median_image_references"),
            row.get("median_image_references"),
        ),
        "median_comments_delta": _delta(_metric(dochan, "median_comments"), row.get("median_comments")),
        "median_bookmarks_delta": _delta(_metric(dochan, "median_bookmarks"), row.get("median_bookmarks")),
        "median_formula_markers_delta": _delta(
            _metric(dochan, "median_formula_markers"),
            row.get("median_formula_markers"),
        ),
        "median_unique_text_tokens_delta": _delta(
            _metric(dochan, "median_unique_text_tokens"),
            row.get("median_unique_text_tokens"),
        ),
    })
    if "file" in base:
        comparison["dochan_output_path"] = _metric(dochan, "representative_output_path") or ""
        comparison["competitor_output_path"] = row.get("representative_output_path", "")
    comparison.update(_json_profile_deltas(dochan, row))
    return comparison


def _json_profile_deltas(dochan: dict, competitor: dict) -> dict:
    deltas = {}
    for key in JSON_PROFILE_KEYS:
        median_key = f"median_{key}"
        if (
            (dochan is None or median_key not in dochan)
            and median_key not in competitor
        ):
            continue
        deltas[f"{median_key}_delta"] = _delta(
            _metric(dochan, median_key),
            competitor.get(median_key),
        )
    return deltas


def find_improvement_candidates(competitive_summary: List[dict]) -> List[dict]:
    return _find_improvement_candidates(competitive_summary, include_file=False)


def find_file_improvement_candidates(file_competitive_summary: List[dict]) -> List[dict]:
    return _find_improvement_candidates(file_competitive_summary, include_file=True)


def _find_improvement_candidates(competitive_summary: List[dict], include_file: bool) -> List[dict]:
    candidates = []
    for row in competitive_summary:
        score = 0.0
        reasons = []

        accuracy_delta = row.get("accuracy_delta")
        if accuracy_delta is not None and accuracy_delta <= -0.25:
            deficit = abs(accuracy_delta)
            score += deficit
            reasons.append(f"dochan_accuracy_trails_by={deficit:.3f}")

        success_rate_delta = row.get("success_rate_delta")
        if success_rate_delta is not None and success_rate_delta < 0:
            deficit = abs(success_rate_delta)
            score += deficit
            reasons.append(f"dochan_success_rate_trails_by={deficit:.3f}")

        table_delta = row.get("median_table_rows_delta")
        token_delta = row.get("median_unique_text_tokens_delta")
        table_delta_is_signal = token_delta is None or token_delta <= -1
        if table_delta is not None and table_delta <= -1 and table_delta_is_signal:
            deficit = abs(table_delta)
            score += 0.05
            reasons.append(f"dochan_table_rows_trail_by={deficit:g}")

        headings_delta = row.get("median_headings_delta")
        headings_delta_is_signal = token_delta is None or token_delta <= -1
        if headings_delta is not None and headings_delta <= -1 and headings_delta_is_signal:
            deficit = abs(headings_delta)
            score += 0.05
            reasons.append(f"dochan_headings_trail_by={deficit:g}")

        links_delta = row.get("median_links_delta")
        if links_delta is not None and links_delta <= -1:
            deficit = abs(links_delta)
            score += 0.05
            reasons.append(f"dochan_links_trail_by={deficit:g}")

        for key, label in [
            ("median_image_references_delta", "image_references"),
            ("median_comments_delta", "comments"),
            ("median_bookmarks_delta", "bookmarks"),
            ("median_formula_markers_delta", "formula_markers"),
        ]:
            delta = row.get(key)
            if delta is not None and delta <= -1:
                deficit = abs(delta)
                score += 0.05
                reasons.append(f"dochan_{label}_trail_by={deficit:g}")

        if not reasons:
            continue

        candidate = {
            "format": row["format"],
            "competitor": row["competitor"],
            "worst_gap_score": round(score, 3),
            "reasons": reasons,
        }
        if include_file:
            candidate["file"] = row["file"]
            candidate["dochan_output_path"] = row.get("dochan_output_path", "")
            candidate["competitor_output_path"] = row.get("competitor_output_path", "")
        candidates.append(candidate)
    return sorted(candidates, key=lambda item: (-item["worst_gap_score"], item["format"], item["competitor"], item.get("file", "")))


def _metric(row: dict, key: str):
    if row is None:
        return None
    return row.get(key)


def _delta(left, right):
    if left is None or right is None:
        return None
    return left - right


def _ratio(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def run_benchmark(
    root: Path,
    formats: Iterable[str] = OFFICE_FORMATS,
    runs: int = 1,
    converter_names: Iterable[str] = CONVERTER_NAMES,
    output_root: Path = None,
    timeout_seconds: float = DEFAULT_CONVERSION_TIMEOUT_SECONDS,
) -> dict:
    files = iter_input_files(root, formats)
    requested_converters = [name.strip().lower() for name in converter_names if name.strip()]
    converter_status = inspect_converter_availability(requested_converters)
    converters = discover_converters(requested_converters)
    expectations = load_expectations(root)
    input_semantic_empty = {
        file_path: not input_has_ooxml_semantic_signal(file_path)
        for file_path in files
    }
    results = []

    for file_path in files:
        for name, convert in converters.items():
            for run_index in range(1, max(runs, 1) + 1):
                started = perf_counter()
                json_profile = {}
                try:
                    output, json_profile = _run_with_timeout(
                        lambda: _convert_dochan_profiled(file_path)
                        if name == "dochan"
                        else (convert(file_path), {}),
                        timeout_seconds,
                    )
                    error = ""
                except Exception as exc:
                    output = ""
                    error = repr(exc)
                elapsed = perf_counter() - started
                relative_path = file_path.relative_to(root).as_posix()
                output_path = None
                if output_root is not None:
                    output_path = output_capture_path(output_root, name, Path(relative_path), run_index)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(output, encoding="utf-8")
                expectation = expectations.get(relative_path, {})
                row = {
                    "converter": name,
                    "file": str(file_path),
                    "format": file_path.suffix.lower().lstrip("."),
                    "run": run_index,
                    "seconds": elapsed,
                    "chars": len(output),
                    "nonempty": bool(output.strip()),
                    "error": error,
                    "input_semantic_empty": input_semantic_empty.get(file_path, False),
                }
                row.update(json_profile)
                if output_path is not None:
                    row["output_path"] = str(output_path)
                row.update(profile_output(output))
                if expectation:
                    row.update(score_output(output, expectation, json_profile))
                results.append(row)

    summary = summarize_results(results)
    format_summary = summarize_by_format(results)
    competitive_summary = compare_against_dochan(format_summary)
    file_competitive_summary = compare_files_against_dochan(summary)
    return {
        "root": str(root),
        "formats": list(formats),
        "runs": max(runs, 1),
        "timeout_seconds": timeout_seconds,
        "output_root": str(output_root) if output_root is not None else "",
        "file_count": len(files),
        "requested_converters": requested_converters,
        "converter_status": converter_status,
        "converters": sorted(converters),
        "results": results,
        "summary": summary,
        "format_summary": format_summary,
        "competitive_summary": competitive_summary,
        "improvement_candidates": find_improvement_candidates(competitive_summary),
        "file_competitive_summary": file_competitive_summary,
        "file_improvement_candidates": find_file_improvement_candidates(file_competitive_summary),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark dochan against local MarkItDown/Docling installations.")
    parser.add_argument("root", type=Path, help="Directory containing benchmark documents")
    parser.add_argument("--formats", default=",".join(OFFICE_FORMATS), help="Comma-separated extensions")
    parser.add_argument("--converters", default=",".join(CONVERTER_NAMES), help="Comma-separated converter names")
    parser.add_argument("--runs", type=int, default=1, help="Repeated runs per converter/file")
    parser.add_argument("--timeout", type=float, default=DEFAULT_CONVERSION_TIMEOUT_SECONDS, help="Seconds before a single conversion is recorded as timed out")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    parser.add_argument("--save-outputs", type=Path, default=None, help="Optional directory for converter Markdown outputs")
    args = parser.parse_args()

    formats = [item.strip().lstrip(".") for item in args.formats.split(",") if item.strip()]
    converter_names = [item.strip().lower() for item in args.converters.split(",") if item.strip()]
    report = run_benchmark(
        args.root,
        formats=formats,
        runs=args.runs,
        converter_names=converter_names,
        output_root=args.save_outputs,
        timeout_seconds=args.timeout,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
