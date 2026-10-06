"""Reproduce real-PDF line assembly parity, delegation, and alternating timings.

Run after the optional extensions have been built::

    /usr/bin/python3 -m scripts.probe_pdf_clines \
        --output .codex-work/pdf-clines-probe.json

The input corpus is read only. Results contain public filenames and hashes,
never extracted document text. Validation/capture overhead is excluded from
both parsing and replay timings. The scanner stays fixed for line-only timings;
an additional fresh process verifies DOCHAN_DISABLE_ACCEL=1 output hashes.
"""

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import statistics
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from dochan import Dochan
from dochan.pdf import content


LINE_FIELDS = (
    "fragment_orders", "order", "direction", "along_start", "along_end",
    "across", "left", "right", "y", "size", "first_size", "last_size",
    "segments", "runs", "trailing_space", "text",
)
SEGMENT_FIELDS = ("x0", "x1", "text", "space_width", "runs")
NUMERIC_FIELDS = ("x", "y", "width", "size", "space_width", "dir_x", "dir_y")
DEFAULT_CORPUS = Path("/Users/illuwa/dev/personal/dochan/corpus")


class LineMismatch(Exception):
    """The live fragment input produced different Python and C lines."""


def _shape(value):
    """Include types, signed zero/NaN bits, and nested run tuple shapes."""
    kind = type(value)
    name = kind.__module__ + "." + kind.__qualname__
    if kind is float:
        return (name, struct.pack(">d", value).hex())
    if kind in (list, tuple):
        return (name, tuple(_shape(item) for item in value))
    if isinstance(value, content._Segment):
        return (name, tuple((field, _shape(getattr(value, field)))
                            for field in SEGMENT_FIELDS))
    return (name, value)


def _compare_lines(expected, actual, location):
    if type(expected) is not type(actual) or len(expected) != len(actual):
        raise LineMismatch(location + ": line list type/length")
    for number, (left, right) in enumerate(zip(expected, actual)):
        if type(left) is not type(right):
            raise LineMismatch("%s: line %d type" % (location, number))
        for field in LINE_FIELDS:
            if _shape(getattr(left, field)) != _shape(getattr(right, field)):
                # Do not include field contents: diagnostics remain text-free.
                raise LineMismatch("%s: line %d field %s" % (location, number, field))


def _group_rows(frags):
    """Mirror the Python grouping loop only for delegation attribution."""
    rows, current = [], []
    current_across = current_direction = None
    current_size = 0.0
    for frag in frags:
        direction = content.writing_direction(frag)
        position = content.across(frag)
        tolerance = max(content._LINE_Y_TOLERANCE, 0.5 * current_size)
        if (current_across is None or
                (direction == current_direction and
                 abs(position - current_across) <= tolerance)):
            current.append(frag)
            if current_across is None:
                current_across, current_direction = position, direction
        else:
            rows.append(current)
            current = [frag]
            current_across, current_direction = position, direction
            current_size = 0.0
        current_size = max(current_size, frag.size)
    if current:
        rows.append(current)
    return rows


def _row_reasons(row):
    reasons = set()
    for frag in row:
        if type(frag) is not content.Fragment:
            reasons.add("fragment_subclass")
        for name in ("link_spans", "comment_markers"):
            value = getattr(frag, name)
            if type(value) is not list:
                reasons.add("non_list_" + name)
            if value:
                reasons.add(name)
        if frag.note_ref:
            reasons.add("note_ref")
        if type(frag.note_ref) is not int:
            reasons.add("non_int_note_ref")
        if type(frag.order) is not int:
            reasons.add("non_int_order")
        for name in ("bold", "italic", "invisible"):
            if getattr(frag, name) is not True and getattr(frag, name) is not False:
                reasons.add("non_bool_" + name)
        if type(frag.text) is not str:
            reasons.add("non_str_text")
        for name in NUMERIC_FIELDS:
            value = getattr(frag, name)
            if type(value) is not float:
                reasons.add("non_float_" + name)
            if isinstance(value, (float, int)) and not math.isfinite(value):
                reasons.add("nonfinite_" + name)
            if type(value) is int and abs(value) > 2 ** 53:
                reasons.add("large_int_" + name)
    if not reasons:
        ordered = content._in_writing_order(row)
        if ordered and content.writing_direction(ordered[0]) == "ltr":
            if any(not math.isfinite(content.along(right) - content.along(left) - left.width)
                   for left, right in zip(ordered, ordered[1:])
                   if content._Line._comparable_hangul(left, right)):
                reasons.add("nonfinite_tracking_gap")
            elif any(value is not None and not math.isfinite(value)
                     for value in content._Line._hangul_tracking_gaps(ordered)):
                reasons.add("nonfinite_tracking_median")
    return reasons


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse(paths, progress, before_document=None):
    records = {}
    parse_seconds = 0.0
    for number, path in enumerate(paths, 1):
        if before_document is not None:
            before_document(path)
        started = time.perf_counter()
        try:
            document = Dochan(str(path))
            parse_seconds += time.perf_counter() - started
        except LineMismatch:
            raise
        except Exception as exc:
            parse_seconds += time.perf_counter() - started
            records[str(path)] = {
                "exception_type": type(exc).__module__ + "." + type(exc).__name__,
                "exception_sha256": _digest(str(exc)),
            }
        else:
            records[str(path)] = {
                "markdown_sha256": _digest(document.to_markdown()),
                "json_sha256": _digest(document.to_json()),
                "errors_sha256": _digest(json.dumps(document.errors, ensure_ascii=False)),
                "errors_count": len(document.errors),
            }
        if number % 25 == 0 or number == len(paths):
            print("%s %d/%d" % (progress, number, len(paths)), flush=True)
    return records, parse_seconds


def _mismatches(expected, actual, mode):
    return [{"mode": mode, "path": path,
             "fields": [field for field in sorted(set(expected[path]) | set(actual.get(path, {})))
                        if expected[path].get(field) != actual.get(path, {}).get(field)]}
            for path in expected if expected[path] != actual.get(path)]


def _time_parsing(paths, baseline, accelerator, order):
    timings = {"c": [], "python": []}
    mismatches = []
    try:
        for mode in order:
            content._c_assemble_lines = accelerator if mode == "c" else None
            records, elapsed = _parse(paths, mode)
            timings[mode].append(elapsed)
            mismatches.extend(_mismatches(baseline, records, mode))
    finally:
        content._c_assemble_lines = accelerator
    return timings, mismatches


def _select(args):
    if args.count < 150:
        raise ValueError("--count must be at least 150 per corpus")
    selected = []
    groups = {}
    for name, root, recursive in (("pdfjs", args.pdfjs, True), ("press_pairs", args.press, False)):
        paths = sorted(root.rglob("*.pdf") if recursive else root.glob("*.pdf"))
        if len(paths) < args.count:
            raise ValueError("%s: only %d PDFs, need %d" % (root, len(paths), args.count))
        paths = paths[:args.count]
        groups[name] = {
            "root": str(root.resolve()),
            "files": [str(path.resolve()) for path in paths],
            "source_sha256": {str(path.resolve()): _file_digest(path) for path in paths},
        }
        selected.extend(path.resolve() for path in paths)
    return selected, groups


def _validate(paths, accelerator, original):
    captured = []
    reasons = Counter()
    stats = Counter()
    init = content._Line.__init__
    current_path = [""]

    def counted_init(self, fragments):
        stats["actual_python_rows"] += 1
        return init(self, fragments)

    def instrumented(self, fragments):
        content._c_assemble_lines = None
        try:
            expected = original(self, fragments)
        finally:
            content._c_assemble_lines = accelerator
        rows = _group_rows(fragments)
        stats["calls"] += 1
        stats["fragments"] += len(fragments)
        stats["rows"] += len(rows)
        location = "%s call %d" % (current_path[0], stats["calls"])
        content._Line.__init__ = counted_init
        before = stats["actual_python_rows"]
        try:
            actual = accelerator(fragments, content._Line, content._Segment,
                                 content.Fragment, content._LINE_Y_TOLERANCE)
            whole_fallback = actual is None
            if whole_fallback:
                content._c_assemble_lines = None
                actual = original(self, fragments)
        finally:
            content._Line.__init__ = init
            content._c_assemble_lines = accelerator
        _compare_lines(expected, actual, location)
        fallback_rows = stats["actual_python_rows"] - before
        stats["whole_call_fallbacks"] += int(whole_fallback)
        predicted = 0
        for row in rows:
            row_reasons = _row_reasons(row)
            if whole_fallback:
                row_reasons.add("whole_call_fallback")
            if row_reasons:
                predicted += 1
                reasons.update(row_reasons)
        if predicted != fallback_rows:
            raise LineMismatch("%s: predicted delegation %d, observed %d" % (
                location, predicted, fallback_rows))
        # Later parsing can attach annotation metadata to the same fragments.
        # Freeze their call-time state before replaying the measured workload.
        captured.append(copy.deepcopy(fragments))
        return actual

    def set_path(path):
        current_path[0] = str(path)

    content.ContentTextExtractor._assemble_lines = instrumented
    try:
        records, _ = _parse(paths, "validate", before_document=set_path)
    finally:
        content.ContentTextExtractor._assemble_lines = original
        content._Line.__init__ = init
        content._c_assemble_lines = accelerator
    stats["deep_comparison_mismatches"] = 0
    stats["python_row_fraction"] = stats["actual_python_rows"] / stats["rows"] if stats["rows"] else 0.0
    stats["c_rows"] = stats["rows"] - stats["actual_python_rows"]
    return records, captured, dict(stats), dict(sorted(reasons.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdfjs", type=Path, default=DEFAULT_CORPUS / "pdfjs-src")
    parser.add_argument("--press", type=Path, default=DEFAULT_CORPUS / "press-pairs")
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retime", action="store_true",
                        help="repeat parsing timings in a completed result after stopping other workloads")
    parser.add_argument("--worker-manifest", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_manifest:
        paths = [Path(path) for path in json.loads(args.worker_manifest.read_text())]
        records, elapsed = _parse(paths, "full-python")
        args.output.write_text(json.dumps({"records": records, "parse_seconds": elapsed,
                                          "scanner": content.CONTENT_SCANNER_BACKEND,
                                          "lines": content.LINE_ASSEMBLY_BACKEND}, indent=2))
        return 0
    accelerator = getattr(content, "_c_assemble_lines", None)
    if accelerator is None:
        raise RuntimeError("build _clines and run with acceleration enabled first")
    if args.retime:
        output = json.loads(args.output.read_text())
        if output["status"] != "passed":
            raise ValueError("--retime requires a completed passing result")
        if output["scanner_for_line_timings"] != content.CONTENT_SCANNER_BACKEND:
            raise ValueError("scanner changed since validation")
        paths = [Path(path) for group in output["selection"].values() for path in group["files"]]
        for group in output["selection"].values():
            for path, digest in group["source_sha256"].items():
                if _file_digest(Path(path)) != digest:
                    raise ValueError("source PDF changed: " + path)
        timings, mismatches = _time_parsing(paths, output["records"], accelerator, output["timing_order"])
        output.setdefault("superseded_parse_timings", []).append(output["parse_seconds"])
        output["parse_seconds"] = timings
        output["parse_seconds_median"] = {mode: statistics.median(values) for mode, values in timings.items()}
        output["hash_mismatches"].extend(mismatches)
        output["status"] = "failed" if output["hash_mismatches"] else "passed"
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": output["status"], "parse_medians": output["parse_seconds_median"],
                          "hash_mismatches": len(mismatches)}), flush=True)
        return 0 if output["status"] == "passed" else 1
    paths, groups = _select(args)
    original = content.ContentTextExtractor._assemble_lines
    output = {
        "python": sys.version, "platform": platform.platform(), "selection": groups,
        "implementation_sha256": {
            "content.py": _file_digest(Path(content.__file__)),
            "_clines.c": _file_digest(Path(content.__file__).with_name("_clines.c")),
            "extension": _file_digest(Path(sys.modules[accelerator.__module__].__file__)),
            "probe": _file_digest(Path(__file__)),
        },
        "selection_sha256": _digest(json.dumps([str(path) for path in paths])),
        "scanner_for_line_timings": content.CONTENT_SCANNER_BACKEND,
        "timing_order": ["c", "python", "c", "python", "c", "python"],
        "parse_seconds": {"c": [], "python": []},
        "replay_seconds": {"c": [], "python": []}, "hash_mismatches": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = args.output.with_suffix(".manifest.json")
    worker_output = args.output.with_suffix(".full-python.json")
    try:
        baseline, captured, stats, reasons = _validate(paths, accelerator, original)
        output["validation"] = stats
        output["delegation_reasons_nonexclusive"] = reasons
        output["records"] = baseline
        timings, mismatches = _time_parsing(paths, baseline, accelerator, output["timing_order"])
        output["parse_seconds"] = timings
        output["hash_mismatches"].extend(mismatches)
        extractor = content.ContentTextExtractor()
        for mode in output["timing_order"]:
            content._c_assemble_lines = accelerator if mode == "c" else None
            started = time.perf_counter()
            for fragments in captured:
                original(extractor, fragments)
            elapsed = time.perf_counter() - started
            output["replay_seconds"][mode].append(elapsed)
            print("replay %s %.6f" % (mode, elapsed), flush=True)
        manifest.write_text(json.dumps([str(path) for path in paths]))
        env = dict(os.environ, DOCHAN_DISABLE_ACCEL="1")
        command = [sys.executable, "-m", "scripts.probe_pdf_clines", "--worker-manifest", str(manifest.resolve()),
                   "--output", str(worker_output.resolve())]
        subprocess.run(command, check=True, env=env)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
        full_python = json.loads(worker_output.read_text())
        output["full_python"] = {key: value for key, value in full_python.items() if key != "records"}
        output["hash_mismatches"].extend(_mismatches(baseline, full_python["records"], "DOCHAN_DISABLE_ACCEL=1"))
        for stage in ("parse_seconds", "replay_seconds"):
            output[stage + "_median"] = {mode: statistics.median(values)
                                          for mode, values in output[stage].items()}
        output["successful_documents"] = sum("exception_type" not in row for row in baseline.values())
        output["exception_documents"] = len(paths) - output["successful_documents"]
        output["corpus_results"] = {
            name: {"selected": len(group["files"]),
                   "successful": sum("exception_type" not in baseline[path]
                                     for path in group["files"])}
            for name, group in groups.items()
        }
        output["status"] = "passed" if not output["hash_mismatches"] else "failed"
    except Exception as exc:
        output["status"] = "failed"
        output["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        content._c_assemble_lines = accelerator
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        manifest.unlink(missing_ok=True)
        worker_output.unlink(missing_ok=True)
    print(json.dumps({"status": output["status"], "validation": output["validation"],
                      "hash_mismatches": len(output["hash_mismatches"]),
                      "parse_medians": output["parse_seconds_median"],
                      "replay_medians": output["replay_seconds_median"]}), flush=True)
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
