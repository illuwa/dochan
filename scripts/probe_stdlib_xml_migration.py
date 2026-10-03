"""공개 코퍼스의 Markdown·JSON·errors 해시와 변환 시간을 기록한다.

사용 예: python scripts/probe_stdlib_xml_migration.py corpus --source . --output result.jsonl
비교 예: python scripts/probe_stdlib_xml_migration.py --compare before.jsonl after.jsonl
내부 문서는 이 도구에 넣지 않는다. 파일명은 코퍼스 루트 상대 경로만 기록한다.
"""

import argparse
import contextlib
from dataclasses import fields, is_dataclass, replace
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import signal
import resource
import sys
import time
from collections import Counter, defaultdict


EXTENSIONS = {
    ".docx": "docx", ".docm": "docx", ".pptx": "pptx", ".pptm": "pptx",
    ".xlsx": "xlsx", ".xlsm": "xlsx", ".hwpx": "hwpx", ".pdf": "pdf",
}
CORPORA = ("poi-src", "lo-src", "tika-test-docs", "pdfjs-src", "hwp-public")


class ProbeTimeout(BaseException):
    """문서 파서의 일반 예외 복구로 시간 제한이 삼켜지지 않게 한다."""


def _alarm(signum, frame):
    raise ProbeTimeout()


def _initialize(source):
    sys.path.insert(0, source)
    # 모든 자식에서 같은 해시 순서를 쓰도록 실행 명령에도 PYTHONHASHSEED=0을 준다.
    from dochan import Dochan
    global _reader
    _reader = Dochan
    signal.signal(signal.SIGALRM, _alarm)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def selftest_streaming():
    """작은 합성 반복 문자열 문서로 기존 출력과 순차 출력이 같은지 확인한다."""
    from dochan.model.document import Document, Paragraph, Section, TextRun
    from dochan.model.table import Cell, Table
    from dochan.output.json_out import to_json
    from dochan.output.markdown import to_markdown

    cases = 0
    for text in ("repeat", '한글 😀 | \\ "\n\t', ""):
        for count in (1, 4):
            table = Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun(text)])])
                                 for _ in range(3)] for _ in range(count)])
            table.rows[-1][-1].row_span = 0
            if count > 1:
                table.rows[-1].pop()
            doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun("before")]),
                                                       table,
                                                       Paragraph(runs=[TextRun("after")])])])
            for name, chunks, expected in (("markdown", stream_markdown(doc), to_markdown(doc)),
                                           ("json", stream_json(doc), to_json(doc))):
                actual = hash_chunks(chunks)
                assert actual["sha256"] == digest(expected), (name, count)
                assert actual["bytes"] == len(expected.encode("utf-8")), (name, count)
            cases += 1
    return cases


def hash_chunks(chunks):
    """실제 UTF-8 출력 바이트를 연결 순서 그대로 빠짐없이 해시한다."""
    hashed = hashlib.sha256()
    size = 0
    for chunk in chunks:
        encoded = chunk.encode("utf-8")
        hashed.update(encoded)
        size += len(encoded)
    return {"sha256": hashed.hexdigest(), "bytes": size}


def stream_json(doc):
    """기존 JSON 변환 사전과 같은 직렬화 옵션을 쓰며 문자열만 순차 출력한다."""
    from dochan.output.json_out import to_dict
    return json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(to_dict(doc))


def stream_markdown(doc):
    """단일 평문 표를 가진 표본만 기존 렌더러로 감싸서 순차 출력한다.

    바깥 문서와 각 고유 셀은 기존 렌더러를 재사용한다. 표의 행 구분자만
    순차로 보낸다. 캡션·중첩 표·각주·링크는 지원하지 않고 즉시 거부한다.
    """
    from dochan.model.document import Paragraph, TextRun
    from dochan.model.table import Table
    from dochan.output.markdown import _cell_text, to_markdown

    tables = [elem for section in doc.sections for elem in section.elements
              if isinstance(elem, Table)]
    if len(tables) != 1 or len(doc.find_all("table")) != 1:
        raise ValueError("streaming probe requires exactly one top-level table")
    table = tables[0]
    if table.caption or not table.rows or table.col_count == 0:
        raise ValueError("streaming probe requires a nonempty table without caption")
    marker = "DOCHANSTREAMTABLEBOUNDARY8C516947"
    cells = {}
    cell_keys = {}
    for row in table.rows:
        for cell in row:
            key_parts = []
            for block in cell.paragraphs:
                if not isinstance(block, Paragraph):
                    raise ValueError("streaming probe requires plain paragraph cells")
                for run in block.runs:
                    if run.link or run.note_ref or getattr(run.provenance, "source_format", "") == "ppt":
                        raise ValueError("streaming probe does not support contextual runs")
                key_parts.append(tuple(run.text for run in block.runs))
            key = tuple(key_parts)
            if key not in cells:
                rendered = _cell_text(cell)
                if marker in rendered:
                    raise ValueError("streaming marker occurs in cell content")
                cells[key] = rendered
            cell_keys[id(cell)] = key
    skeleton = replace(doc, sections=[replace(section, elements=[
        Paragraph(runs=[TextRun(marker)]) if elem is table else elem
        for elem in section.elements]) for section in doc.sections])
    rendered = to_markdown(skeleton)
    if rendered.count(marker) != 1:
        raise ValueError("streaming marker is ambiguous in rendered document")
    prefix, suffix = rendered.split(marker)
    yield prefix
    for row_idx, row in enumerate(table.rows):
        if row_idx:
            yield "\n"
        yield "| "
        for index in range(max(len(row), table.col_count)):
            if index:
                yield " | "
            if index < len(row) and not row[index].is_merged_away:
                yield cells[cell_keys[id(row[index])]]
        yield " |"
        if row_idx == 0:
            yield "\n| " + " | ".join(["---"] * table.col_count) + " |"
    yield suffix


def streaming_probe(path, source, output):
    """대형 반복 표본의 실제 출력 해시를 별도 측정한다. 코퍼스 시간에 합치지 않는다."""
    _initialize(str(Path(source).resolve()))
    result = {"method": "exact UTF-8 output chunks", "synthetic_cases": selftest_streaming()}
    started = time.perf_counter()
    total_started = started
    reader = _reader(str(Path(path).resolve()))
    result["parse_seconds"] = time.perf_counter() - started
    for name, chunks in (("markdown", stream_markdown(reader.doc)),
                         ("json", stream_json(reader.doc))):
        started = time.perf_counter()
        result[name] = hash_chunks(chunks)
        result[name]["seconds"] = time.perf_counter() - started
        print(json.dumps({"finished": name, **result[name]}), flush=True)
    result["errors"] = digest(json.dumps(reader.errors, ensure_ascii=False, sort_keys=True))
    result["error_count"] = len(reader.errors)
    result["total_seconds"] = time.perf_counter() - total_started
    result["peak_rss_platform_units"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def model_digest(value):
    """문자열 반복을 확장하지 않고 모델 전체 필드와 순서를 비교한다.

    출력 바이트의 검증을 대신하지 않는다. 큰 반복 문자열 문서의 구조를
    보조 검증할 때만 쓰며, 동일한 문자열의 해시는 한 번만 계산한다.
    """
    strings = {}

    def visit(item):
        if isinstance(item, str):
            if item not in strings:
                strings[item] = {"string_sha256": digest(item), "characters": len(item)}
            return strings[item]
        if isinstance(item, bytes):
            return {"bytes_sha256": hashlib.sha256(item).hexdigest(), "bytes": len(item)}
        if is_dataclass(item):
            return {"type": type(item).__name__,
                    "fields": {field.name: visit(getattr(item, field.name)) for field in fields(item)}}
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [visit(child) for child in item]
        return item

    normalized = visit(value)
    return {"sha256": digest(json.dumps(normalized, ensure_ascii=False, sort_keys=True)),
            "unique_strings": len(strings)}


def _convert(task):
    root, relative, timeout = task
    path = Path(root) / relative
    result = {"path": relative, "format": EXTENSIONS[path.suffix.lower()]}
    started = time.perf_counter()
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            reader = _reader(str(path))
            markdown = reader.to_markdown()
            serialized = reader.to_json()
            errors = json.dumps(reader.errors, ensure_ascii=False, sort_keys=True)
        result.update(status="ok", markdown=digest(markdown), json=digest(serialized),
                      errors=digest(errors), error_count=len(reader.errors),
                      markdown_bytes=len(markdown.encode("utf-8")),
                      json_bytes=len(serialized.encode("utf-8")))
    except ProbeTimeout:
        result.update(status="timeout", timeout_seconds=timeout)
    except Exception as exc:
        result.update(status="exception", exception=repr(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    result["seconds"] = round(time.perf_counter() - started, 6)
    return result


def summarize(rows):
    formats = defaultdict(lambda: {"count": 0, "seconds": 0.0,
                                   "successful_seconds": 0.0, "statuses": Counter()})
    for row in rows:
        entry = formats[row["format"]]
        entry["count"] += 1
        entry["seconds"] += row["seconds"]
        if row["status"] == "ok":
            entry["successful_seconds"] += row["seconds"]
        entry["statuses"][row["status"]] += 1
    return dict(formats)


def compare(before_path, after_path, formats=None):
    def read(path):
        return {row["path"]: row for row in
                (json.loads(line) for line in Path(path).read_text().splitlines())
                if not formats or row["format"] in formats}
    before, after = read(before_path), read(after_path)
    changes = []
    keys = ("status", "markdown", "json", "errors", "exception")
    for path in sorted(set(before) | set(after)):
        left, right = before.get(path, {}), after.get(path, {})
        fields = [key for key in keys if left.get(key) != right.get(key)]
        if not left or not right:
            fields.append("missing")
        if fields:
            changes.append({"path": path, "fields": fields,
                            "before": {key: left.get(key) for key in fields},
                            "after": {key: right.get(key) for key in fields}})
    result = {"before_count": len(before), "after_count": len(after),
              "changed_count": len(changes), "changes": changes,
              "fully_compared_count": sum(before[path]["status"] == "ok"
                                          and after[path]["status"] == "ok"
                                          for path in set(before) & set(after)),
              "unverified": [path for path in sorted(set(before) | set(after))
                             if before.get(path, {}).get("status") != "ok"
                             or after.get(path, {}).get("status") != "ok"],
              "before": summarize(before.values()), "after": summarize(after.values())}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(changes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="?")
    parser.add_argument("--source", default=".")
    parser.add_argument("--output")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--formats", nargs="+", choices=sorted(set(EXTENSIONS.values())))
    parser.add_argument("--exclude", action="append", default=[],
                        help="별도 검증하는 공개 상대 경로를 제외하고 요약에 명시한다")
    parser.add_argument("--compare", nargs=2)
    parser.add_argument("--stream-file", help="대형 단일 평문 표의 실제 출력 바이트를 순차 해싱한다")
    parser.add_argument("--selftest-streaming", action="store_true")
    args = parser.parse_args()
    if args.compare:
        return compare(*args.compare, formats=args.formats)
    if args.selftest_streaming:
        _initialize(str(Path(args.source).resolve()))
        print(json.dumps({"synthetic_cases": selftest_streaming()}))
        return 0
    if args.stream_file:
        if not args.output:
            parser.error("--stream-file requires --output")
        return streaming_probe(args.stream_file, args.source, args.output)
    if not args.corpus or not args.output:
        parser.error("corpus and --output are required")
    root = Path(args.corpus).resolve()
    paths = sorted(str(path.relative_to(root)) for corpus in CORPORA
                   for path in (root / corpus).rglob("*")
                   if path.is_file() and path.suffix.lower() in EXTENSIONS
                   and (not args.formats or EXTENSIONS[path.suffix.lower()] in args.formats))
    discovered = len(paths)
    excluded = sorted(set(args.exclude))
    if any(path not in paths for path in excluded):
        parser.error("--exclude must identify a discovered corpus-relative path")
    paths = [path for path in paths if path not in excluded]
    rows = []
    started = time.perf_counter()
    print(json.dumps({"discovered": discovered, "selected": len(paths),
                      "excluded": excluded, "workers": args.workers,
                      "timeout": args.timeout}), flush=True)
    with open(args.output, "w", encoding="utf-8") as output:
        with multiprocessing.Pool(args.workers, initializer=_initialize,
                                  initargs=(str(Path(args.source).resolve()),),
                                  maxtasksperchild=25) as pool:
            tasks = ((str(root), path, args.timeout) for path in paths)
            for row in pool.imap_unordered(_convert, tasks, chunksize=1):
                rows.append(row)
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                output.flush()
                if len(rows) % 100 == 0 or row["status"] != "ok":
                    print(json.dumps({"completed": len(rows), "total": len(paths),
                                      "elapsed": round(time.perf_counter() - started, 1),
                                      "last_status": row["status"]}), flush=True)
    summary = {"count": len(rows), "wall_seconds": time.perf_counter() - started,
               "discovered": discovered, "excluded": excluded,
               "python": sys.version, "hash_seed": os.environ.get("PYTHONHASHSEED"),
               "workers": args.workers, "timeout": args.timeout, "formats": summarize(rows)}
    Path(args.output + ".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
