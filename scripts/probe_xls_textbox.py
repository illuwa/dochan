"""공개 XLS의 비메모 TxO 분포와 Markdown 해시만 기록한다."""
import argparse
from collections import Counter
import hashlib
from itertools import chain
import json
from pathlib import Path
import struct
import subprocess
import sys


def _source_root(path):
    sys.path.insert(0, str(path or Path(__file__).resolve().parents[1]))


def _raw_object_header(payload):
    if len(payload) < 10:
        return None
    marker, size, kind, object_id = struct.unpack_from("<HHHH", payload)
    if marker != 0x0015 or size < 6 or size + 4 > len(payload):
        return None
    return kind, object_id


def _raw_txo(payload, records, normalize_lines):
    """Decode the observed BIFF8 character segments without the product helper."""
    if len(payload) < 14:
        return "", None
    remaining = struct.unpack_from("<H", payload, 10)[0]
    if remaining > 32768:
        return "", None
    parts = []
    while remaining:
        item = next(records, None)
        if item is None:
            return "", None
        if item[1] != 0x003C:
            return "", item
        segment = item[2]
        if not segment or segment[0] not in (0, 1):
            return "", None
        width = 2 if segment[0] else 1
        count = min(remaining, (len(segment) - 1) // width)
        if count == 0:
            return "", None
        raw = segment[1:1 + count * width]
        parts.append(raw.decode("utf-16-le" if width == 2 else "latin1", errors="replace"))
        remaining -= count
    value = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    value = value.strip()
    if normalize_lines:
        value = "\n".join(line for line in (part.strip() for part in value.split("\n")) if line)
    return value, None


def scan(path):
    from dochan import cfb
    from dochan.office_binary.xls import _iter_records

    ole = cfb.OleFileIO(str(path))
    try:
        name = "Workbook" if ole.exists("Workbook") else "Book"
        stream = ole.openstream(name).read()
    finally:
        ole.close()
    records = iter(_iter_records(stream))
    pending = None
    objects = 0
    notes = 0
    text_count = 0
    text_hashes = []
    depth = 0
    chart_starts = []
    while True:
        item = next(records, None)
        if item is None:
            break
        kind, payload = item[1:]
        if kind in (0x0809, 0x0409, 0x0209, 0x0009):
            depth += 1
            if len(payload) >= 4 and struct.unpack_from("<H", payload, 2)[0] == 0x0020:
                chart_starts.append(depth)
            pending = None
        elif kind == 0x000A:
            if chart_starts and depth == chart_starts[-1]:
                chart_starts.pop()
            depth = max(0, depth - 1)
            pending = None
        if chart_starts:
            continue
        if kind == 0x005D:
            pending = _raw_object_header(payload)
            if pending is not None:
                if pending[0] == 0x0019:
                    notes += 1
                else:
                    objects += 1
        elif kind == 0x01B6 and pending is not None:
            object_type, _ = pending
            pending = None
            text, unconsumed = _raw_txo(payload, records, normalize_lines=object_type != 0x0019)
            if unconsumed is not None:
                # A malformed TxO cannot consume the next unrelated BIFF record.
                records = chain((unconsumed,), records)
            if (object_type not in (0x0019, 0x0007)
                    and not 0x000B <= object_type <= 0x0014 and text):
                text_count += 1
                text_hashes.append(hashlib.sha256(text.encode("utf-8")).hexdigest())
    return {"objects": objects, "notes": notes, "text_count": text_count,
            "text_hashes": text_hashes}


def markdown(path):
    from dochan import Dochan
    from dochan.output.markdown import to_markdown

    doc = Dochan(str(path)).doc
    rendered = to_markdown(doc)
    return {"sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "characters": len(rendered), "errors": doc.errors[:30]}


def verify(path):
    from dochan import Dochan
    from dochan.model.document import Paragraph

    observed = scan(path)
    doc = Dochan(str(path)).doc
    actual = Counter(
        hashlib.sha256(element.text.encode("utf-8")).hexdigest()
        for section in doc.sections for element in section.elements
        if isinstance(element, Paragraph)
    )
    expected = Counter(observed.pop("text_hashes"))
    missing = expected - actual
    return {**observed, "matched": sum(expected.values()) - sum(missing.values()),
            "missing": sum(missing.values()), "errors": doc.errors[:30]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--mode", choices=("scan", "markdown", "verify"), default="scan")
    parser.add_argument("--module-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--one", action="store_true")
    args = parser.parse_args()
    _source_root(args.module_root)
    if args.one:
        try:
            result = {"scan": scan, "markdown": markdown, "verify": verify}[args.mode](args.paths[0])
        except Exception as exc:
            result = {"exception": type(exc).__name__ + ": " + str(exc)}
        print(json.dumps(result, ensure_ascii=False))
        return
    rows = []
    for root_index, root in enumerate(args.paths):
        paths = sorted(root.rglob("*.xls")) if root.is_dir() else [root]
        for path in paths:
            command = [sys.executable, __file__, str(path), "--mode", args.mode, "--one"]
            if args.module_root:
                command += ["--module-root", str(args.module_root)]
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=60)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
                result = json.loads(completed.stdout) if completed.returncode == 0 else {
                    "exception": "exit %d" % completed.returncode}
            except (subprocess.TimeoutExpired, ValueError) as exc:
                result = {"exception": type(exc).__name__}
            rows.append({"root": root_index, "file": str(path.relative_to(root))
                         if root.is_dir() else path.name, **result})
            if len(rows) % 50 == 0:
                print("%d files" % len(rows), flush=True)
    if args.output:
        args.output.write_text(json.dumps(rows, ensure_ascii=False) + "\n")
    print(json.dumps({"files": len(rows), "failures": sum("exception" in row for row in rows),
                      "with_text": sum(row.get("text_count", 0) > 0 for row in rows)}))


if __name__ == "__main__":
    main()
