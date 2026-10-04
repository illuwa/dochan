"""공개 ZIP 문서의 정상 출력 회귀와 메모리 절단 복구를 검증한다.

python -m scripts.probe_zip_salvage CORPUS --baseline baseline.jsonl
python -m scripts.probe_zip_salvage CORPUS --compare baseline.jsonl --output result.json

출력 전문과 잘라낸 파일은 저장하지 않는다. baseline은 변경 전 소스 트리를
--repo로 지정할 수 있으며, 정상 원본의 Markdown SHA-256을 독립 정답으로 쓴다.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import posixpath
import random
import re
import signal
import struct
import sys
import time
import zipfile
import zlib
from urllib.parse import unquote, urlsplit


PUBLIC_ROOTS = (
    "poi-src/test-data", "lo-src", "hwp-public/hwp", "hwp-public/hwpx",
    "poi-src/test-data/document", "poi-src/test-data/slideshow",
    "poi-src/test-data/spreadsheet", "press-pairs", "press-pairs-holdout",
    "press-pairs-holdout2", "press-pairs-holdout3", "press-pairs-holdout4",
)
DEFAULT_ROOTS = PUBLIC_ROOTS[:4]
EXTENSIONS = frozenset((".hwp", ".hwpx", ".pdf", ".doc", ".docx",
                        ".ppt", ".pptx", ".xls", ".xlsx"))
KINDS = ("docx", "pptx", "xlsx", "hwpx")
# Inventory reads document signatures only, never third-party source code.
SOURCE_SUFFIXES = frozenset((
    '.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx', '.java',
    '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.py', '.swift', '.rs',
    '.go', '.rb', '.php', '.cs', '.scala', '.kt', '.m', '.mm', '.sh', '.bash', '.zsh',
))
MAX_INPUT = 512 * 1024 * 1024
EMPTY_HASH = hashlib.sha256(b"").hexdigest()
_REL_NAMESPACES = frozenset((
    "http://schemas.openxmlformats.org/package/2006/relationships",
    "http://purl.oclc.org/ooxml/package/relationships",
))


class ProbeDeadline(BaseException):
    """파서의 문서 예외 처리보다 바깥에서 시간 제한을 보고한다."""


@contextmanager
def deadline(seconds):
    def expire(_signum, _frame):
        raise ProbeDeadline()

    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def discover_public(corpus, roots=DEFAULT_ROOTS, all_extensions=True):
    """명시적으로 허용한 공개 자원만 찾고 외부 심볼릭 링크는 제외한다."""
    corpus = Path(corpus).resolve()
    found = set()
    for name in roots:
        if name not in PUBLIC_ROOTS:
            raise ValueError("공개 root가 아님: " + name)
        root = corpus / name
        for path in root.rglob("*"):
            if path.suffix.lower() in SOURCE_SUFFIXES:
                continue
            if not path.is_file() or (not all_extensions and
                                      path.suffix.lower() not in EXTENSIONS):
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
                with resolved.open("rb") as source:
                    if source.read(4) == b"PK\x03\x04":
                        found.add(resolved.relative_to(corpus).as_posix())
            except (OSError, ValueError):
                continue
    return sorted(found)


def summarize_document(doc):
    from dochan.output.markdown import to_markdown

    body = to_markdown(doc)
    return {
        "format": doc.source_format,
        "markdown_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "markdown_chars": len(body),
        "errors": list(doc.errors),
        "fatal": any(str(message).startswith("ERR:") for message in doc.errors),
    }


def parse_path(path, timeout):
    from dochan.reader import Dochan

    with deadline(timeout):
        return summarize_document(Dochan(str(path)).doc)


def parse_bytes(data, kind, timeout):
    """원본과 절단본을 같은 기존 형식 리더에 메모리 스트림으로 전달한다."""
    from dochan.hwpx.parser import HWPXParser
    from dochan.ooxml.docx import DOCXReader
    from dochan.ooxml.pptx import PPTXReader
    from dochan.ooxml.xlsx import XLSXReader

    readers = {"docx": DOCXReader, "pptx": PPTXReader, "xlsx": XLSXReader}
    with deadline(timeout), io.BytesIO(data) as source:
        doc = (HWPXParser().parse(source) if kind == "hwpx"
               else readers[kind]().read(source))
        return summarize_document(doc)


def safe_measure(operation):
    started = time.monotonic()
    try:
        result = operation()
        result["exception"] = None
        result["timeout"] = False
    except ProbeDeadline:
        result = {"exception": "시간 제한 초과", "timeout": True}
    except Exception as exc:
        result = {"exception": type(exc).__name__ + ": " + str(exc)[:1000],
                  "timeout": False}
    result["seconds"] = round(time.monotonic() - started, 6)
    return result


def measure_file(corpus, relative, timeout):
    path = corpus / relative
    result = {"file": relative, "bytes": path.stat().st_size}
    try:
        with zipfile.ZipFile(path):
            result["bad_zip"] = False
    except zipfile.BadZipFile:
        result["bad_zip"] = True
    if result["bytes"] > MAX_INPUT:
        result.update(exception="입력 크기 상한 초과", timeout=False)
    else:
        result.update(safe_measure(lambda: parse_path(path, timeout)))
    return result


def cut_offsets(data):
    """중앙 디렉터리의 원본 오프셋으로 절단점을 독립 계산한다."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        central = archive.start_dir
        if not infos:
            raise ValueError("로컬 항목 없음")
        last = max(infos, key=lambda info: info.header_offset)
        start = last.header_offset
        if data[start:start + 4] != b"PK\x03\x04":
            raise ValueError("마지막 로컬 헤더 없음")
        name_len, extra_len = struct.unpack_from("<HH", data, start + 26)
        payload_start = start + 30 + name_len + extra_len
        last_mid = payload_start + last.compress_size // 2
        # 빈 마지막 항목도 그 로컬 헤더 중간에서 자른다.
        if last.compress_size == 0:
            last_mid = start + 15
        eocd = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
        central_end = eocd if eocd >= central else len(data)
        return {
            "central_start": central,
            "central_middle": central + (central_end - central) // 2,
            "last_local_middle": last_mid,
            "length_30": len(data) * 30 // 100,
            "length_60": len(data) * 60 // 100,
            "length_90": len(data) * 90 // 100,
        }


class _IneligibleOriginal(ValueError):
    pass


def original_admissibility(data, kind):
    """원본 ZIP만 검사한다. 복구 구현이나 절단 결과를 정답지로 쓰지 않는다.

    로컬/중앙 메타데이터 일치, 연속성, CRC, 크기 한도와 원본 관계 대상의
    존재를 확인한다. 관계가 없는 최소 주문서는 .rels가 없어도 제외하지
    않고 별도로 표시한다. .rels XML에는 기존 safe_xml의 DTD/상한 방어를 쓴다.
    """
    from dochan.utils import safe_xml as etree

    result = {"eligible": False, "reasons": [], "missing_main_relationships": False}

    def require(condition, reason):
        if not condition:
            raise _IneligibleOriginal(reason)

    def safe_name(name):
        name = name.replace("\\", "/")
        require(not name.startswith("/") and ".." not in name.split("/")
                and "\0" not in name, "unsafe_original_part_name")
        return posixpath.normpath(name)

    def parse_xml(payload, reason):
        try:
            require(payload.count(b"<") <= 1000000, "original_xml_element_limit")
            return etree.fromstring(payload, max_bytes=32 * 1024 * 1024,
                                    max_depth=2048)
        except Exception:
            raise _IneligibleOriginal(reason) from None

    try:
        require(kind in KINDS and len(data) <= MAX_INPUT, "input_limit")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = sorted(archive.infolist(), key=lambda item: item.header_offset)
            require(0 < len(infos) <= 10000, "archive_entry_limit")
            require(sum(item.file_size for item in infos) <= MAX_INPUT, "archive_size_limit")
            names = {}
            xml = {}
            next_offset = 0
            for item in infos:
                name = safe_name(item.filename)
                require(name not in names, "duplicate_original_part_name")
                names[name] = item.filename
                require(item.file_size <= 100 * 1024 * 1024 and
                        (item.file_size == 0 or item.compress_size > 0) and
                        (not item.compress_size or item.file_size / item.compress_size <= 2000),
                        "original_part_size_ratio_limit")
                offset = item.header_offset
                require(offset == next_offset and offset + 30 <= len(data),
                        "noncontiguous_original_locals")
                fields = struct.unpack_from("<IHHHHHIIIHH", data, offset)
                signature, version, flags, method = fields[:4]
                crc, compressed, size, name_length, extra_length = fields[6:]
                require(signature == 0x04034B50, "noncontiguous_original_locals")
                require(version < 45, "unsupported_local_version")
                require(not flags & (1 | 0x40 | 0x2000), "encrypted_original_member")
                require(method in (0, 8), "unsupported_original_method")
                payload_offset = offset + 30 + name_length + extra_length
                require(payload_offset + item.compress_size <= archive.start_dir,
                        "truncated_original_local")
                raw_name = data[offset + 30:offset + 30 + name_length]
                try:
                    decoded = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
                except UnicodeError:
                    raise _IneligibleOriginal("invalid_original_name_encoding") from None
                require(decoded == item.orig_filename and flags == item.flag_bits and
                        method == item.compress_type, "local_metadata_mismatch")
                extra = data[offset + 30 + name_length:payload_offset]
                cursor = 0
                while cursor < len(extra):
                    require(cursor + 4 <= len(extra), "invalid_original_extra")
                    tag, length = struct.unpack_from("<HH", extra, cursor)
                    require(tag != 1, "zip64_original_member")
                    cursor += 4 + length
                    require(cursor <= len(extra), "invalid_original_extra")
                require(compressed != 0xffffffff and size != 0xffffffff, "zip64_original_member")
                end = payload_offset + item.compress_size
                if flags & 8:
                    require((not crc or crc == item.CRC) and
                            (not compressed or compressed == item.compress_size) and
                            (not size or size == item.file_size), "local_metadata_mismatch")
                    descriptor = end + 4 if data[end:end + 4] == b"PK\x07\x08" else end
                    require(descriptor + 12 <= archive.start_dir, "invalid_original_descriptor")
                    require(struct.unpack_from("<III", data, descriptor) ==
                            (item.CRC, item.compress_size, item.file_size),
                            "invalid_original_descriptor")
                    next_offset = descriptor + 12
                else:
                    require((crc, compressed, size) ==
                            (item.CRC, item.compress_size, item.file_size),
                            "local_metadata_mismatch")
                    next_offset = end
                keep_xml = (name.endswith(".rels") or name in
                            ("Contents/header.xml", "Contents/content.hpf", "content.hpf"))
                chunks = []
                actual_size = 0
                with archive.open(item) as stream:
                    while True:
                        chunk = stream.read(min(1024 * 1024, item.file_size - actual_size + 1))
                        if not chunk:
                            break
                        actual_size += len(chunk)
                        require(actual_size <= item.file_size, "original_crc_size_mismatch")
                        if keep_xml:
                            require(actual_size <= 32 * 1024 * 1024, "original_xml_size_limit")
                            chunks.append(chunk)
                require(actual_size == item.file_size, "original_crc_size_mismatch")
                if keep_xml:
                    xml[name] = b"".join(chunks)
            require(next_offset == archive.start_dir, "noncontiguous_original_locals")
            if kind == "hwpx":
                require("Contents/header.xml" in xml, "hwpx_header_missing")
                header = parse_xml(xml["Contents/header.xml"], "invalid_hwpx_header_xml")
                count = header.get("secCnt", "")
                require(bool(re.fullmatch(r"[0-9]{1,4}", count)), "invalid_hwpx_section_count")
                count = int(count)
                sections = {name for name in names if re.fullmatch(r"Contents/section[0-9]+\.xml", name)}
                require(1 <= count <= 1000 and sections ==
                        {"Contents/section%d.xml" % number for number in range(count)},
                        "hwpx_section_count_mismatch")
                for name in ("Contents/content.hpf", "content.hpf"):
                    if name in xml:
                        parse_xml(xml[name], "invalid_hwpx_manifest_xml")
                main_part = None
            else:
                require("_rels/.rels" in xml, "original_root_relationships_missing")
                main_part = None
            for name, payload in xml.items():
                if not name.endswith(".rels"):
                    continue
                relationships = parse_xml(payload, "invalid_relationship_xml")
                require(relationships.tag in {"{%s}Relationships" % uri for uri in _REL_NAMESPACES},
                        "invalid_relationship_xml")
                part = ("" if name == "_rels/.rels" else posixpath.join(
                    posixpath.dirname(posixpath.dirname(name)), posixpath.basename(name)[:-5]))
                for relation in relationships:
                    if relation.tag not in {"{%s}Relationship" % uri for uri in _REL_NAMESPACES}:
                        continue
                    if relation.get("TargetMode") == "External":
                        continue
                    target = unquote(relation.get("Target", "").replace("\\", "/"))
                    parsed = urlsplit(target)
                    require(bool(parsed.path) and not parsed.scheme and not parsed.netloc
                            and not any(ord(character) < 32 for character in target),
                            "unsafe_original_relationship_target")
                    resolved = posixpath.normpath(parsed.path.lstrip("/") if parsed.path.startswith("/")
                                                else posixpath.join(posixpath.dirname(part), parsed.path))
                    require(not resolved.startswith("../") and resolved != "..",
                            "unsafe_original_relationship_target")
                    require(resolved in names, "missing_internal_target")
                    if (kind != "hwpx" and name == "_rels/.rels" and
                            relation.get("Type", "").rsplit("/", 1)[-1] == "officeDocument"):
                        require(main_part is None, "ambiguous_original_main_relationship")
                        main_part = resolved
            if kind != "hwpx":
                require(main_part is not None, "original_main_relationship_missing")
                main_rels = posixpath.join(posixpath.dirname(main_part), "_rels",
                                           posixpath.basename(main_part) + ".rels")
                result["missing_main_relationships"] = main_rels not in names
        result["eligible"] = True
    except _IneligibleOriginal as exc:
        result["reasons"] = [str(exc)]
    except (zipfile.BadZipFile, zlib.error):
        result["reasons"] = ["original_crc_size_mismatch"]
    except Exception:
        result["reasons"] = ["original_validation_exception"]
    return result


def probe_cuts(corpus, original_records, count, seed, timeout, intact_samples=False):
    def check_original(row, kind):
        with deadline(timeout):
            return original_admissibility((corpus / row["file"]).read_bytes(), kind)

    rng = random.Random(seed)
    samples = {kind: [] for kind in KINDS}
    exclusions = []
    exclusions_count = Counter()
    missing_main_rels = []
    for row in original_records:
        kind = row.get("format")
        if (kind in samples and not row.get("bad_zip") and
                not row.get("fatal") and not row.get("exception") and
                row.get("markdown_chars", 0) > 0):
            if intact_samples:
                suffix = Path(row["file"]).suffix.lower()
                allowed = (suffix in (".hwp", ".hwpx") if kind == "hwpx"
                           else suffix == "." + kind)
                eligibility = (safe_measure(lambda: check_original(row, kind)) if allowed else
                    {"eligible": False, "reasons": ["nonstandard_document_extension"]})
                if eligibility.get("missing_main_relationships"):
                    missing_main_rels.append(row["file"])
                if not eligibility.get("eligible"):
                    reasons = eligibility.get("reasons", ["original_validation_timeout_or_exception"])
                    exclusions_count.update(reasons)
                    exclusions.append({"file": row["file"], "format": kind, "reasons": reasons})
                    continue
            samples[kind].append(row)
    selected = {}
    records = []
    counters = Counter()
    for kind in KINDS:
        candidates = sorted(samples[kind], key=lambda row: row["file"])
        selected[kind] = rng.sample(candidates, min(count, len(candidates)))
        for row in selected[kind]:
            path = corpus / row["file"]
            data = path.read_bytes()
            original = safe_measure(lambda: parse_bytes(data, kind, timeout))
            if (original.get("exception") or original.get("fatal") or
                    original.get("markdown_sha256") != row["markdown_sha256"]):
                records.append({"file": row["file"], "format": kind,
                                "cut": "original_stream", "status": "failure",
                                "original": original})
                counters["original_stream_failure"] += 1
                continue
            offsets = cut_offsets(data)
            for label, offset in offsets.items():
                result = safe_measure(lambda: parse_bytes(data[:offset], kind, timeout))
                equal = result.get("markdown_sha256") == original["markdown_sha256"]
                fatal = result.get("fatal", False)
                empty = result.get("markdown_sha256") == EMPTY_HASH
                recovered_warning = any(str(message).startswith(
                    "WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 ")
                    for message in result.get("errors", []))
                if result.get("exception"):
                    status = "exception"
                elif label in ("central_start", "central_middle"):
                    status = ("pass" if equal and not fatal and recovered_warning
                              else "failure")
                elif fatal:
                    status = "pass" if empty else "fatal_nonempty"
                else:
                    status = "pass" if equal else "silent_difference"
                counters[status] += 1
                counters[kind + ":" + label + ":" + status] += 1
                if fatal:
                    counters["fatal_empty" if empty else "fatal_nonempty_count"] += 1
                elif equal:
                    counters["complete_equal"] += 1
                if result.get("timeout"):
                    counters["timeout"] += 1
                records.append({"file": row["file"], "format": kind,
                                "cut": label, "offset": offset,
                                "original_sha256": original["markdown_sha256"],
                                "status": status, "result": result})
            if len(records) % 120 == 0:
                print(json.dumps({"cut_progress": len(records), "format": kind},
                                 ensure_ascii=False), file=sys.stderr, flush=True)
    return {"seed": seed, "requested_per_format": count,
            "intact_samples": intact_samples, "exclusions": exclusions,
            "exclusion_counts": dict(exclusions_count),
            "originals_without_main_relationships": missing_main_rels,
            "selected": {kind: len(rows) for kind, rows in selected.items()},
            "candidate_counts": {kind: len(rows) for kind, rows in samples.items()},
            "counts": dict(counters), "records": records}


def run(args):
    if args.repo:
        sys.path.insert(0, str(Path(args.repo).resolve()))
    corpus = Path(args.corpus).resolve()
    roots = tuple(args.roots.split(",")) if args.roots else DEFAULT_ROOTS
    discovered = discover_public(corpus, roots, args.all_extensions)
    if args.baseline:
        output = Path(args.baseline)
        output.parent.mkdir(parents=True, exist_ok=True)
        counts = Counter()
        with output.open("w", encoding="utf-8") as stream:
            for number, relative in enumerate(discovered, 1):
                result = measure_file(corpus, relative, args.timeout)
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                stream.flush()
                counts["files"] += 1
                counts["bad_zip"] += bool(result.get("bad_zip"))
                counts["exceptions"] += bool(result.get("exception"))
                counts["timeouts"] += bool(result.get("timeout"))
                if number % 100 == 0:
                    print(json.dumps({"progress": number, "total": len(discovered)},
                                     ensure_ascii=False), file=sys.stderr, flush=True)
        print(json.dumps(dict(counts), ensure_ascii=False))
        return 0
    with Path(args.compare).open(encoding="utf-8") as source:
        before = [json.loads(line) for line in source if line.strip()]
    expected = {row["file"]: row for row in before}
    if set(expected) != set(discovered):
        raise ValueError("baseline과 현재 공개 인벤토리가 다름")
    after = []
    broken = []
    changed = []
    counts = Counter()
    for number, relative in enumerate(discovered, 1):
        old = expected[relative]
        new = measure_file(corpus, relative, args.timeout)
        after.append(new)
        counts["files"] += 1
        counts["exceptions"] += bool(new.get("exception"))
        counts["timeouts"] += bool(new.get("timeout"))
        if old.get("bad_zip"):
            broken.append({"file": relative, "before": old, "after": new})
            counts["bad_zip"] += 1
            counts["recovered"] += (not new.get("fatal", True) and
                                     not new.get("exception"))
        else:
            counts["normal"] += 1
            equal = (old.get("markdown_sha256") == new.get("markdown_sha256") and
                     old.get("exception") == new.get("exception"))
            counts["normal_equal"] += equal
            if not equal:
                changed.append({"file": relative, "before": old, "after": new})
        if number % 100 == 0:
            print(json.dumps({"progress": number, "total": len(discovered)},
                             ensure_ascii=False), file=sys.stderr, flush=True)
    cuts = (probe_cuts(corpus, before, args.samples, args.seed, args.timeout, args.intact_samples)
            if args.samples else None)
    result = {"roots": roots, "all_extensions": args.all_extensions,
              "counts": dict(counts), "broken_zip": broken,
              "normal_changes": changed, "cuts": cuts}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"counts": dict(counts),
                      "cuts": cuts["counts"] if cuts else None}, ensure_ascii=False))
    return int(bool(changed or counts["exceptions"] or counts["timeouts"] or
                    (cuts and any(number != args.samples for number in cuts["selected"].values())) or
                    (cuts and any(cuts["counts"].get(key, 0) for key in
                                  ("failure", "silent_difference", "fatal_nonempty",
                                   "exception", "original_stream_failure")))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--baseline")
    modes.add_argument("--compare")
    parser.add_argument("--output", default=".codex-work/zip-salvage-results.json")
    parser.add_argument("--repo", "--source-root", help="원본 baseline용 소스 트리")
    parser.add_argument("--roots", help="허용된 공개 하위 root의 쉼표 구분 목록")
    parser.add_argument("--all-extensions", action="store_true", default=True)
    parser.add_argument("--document-extensions", dest="all_extensions", action="store_false")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--samples", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--intact-samples", action="store_true",
                        help="원본 로컬/CRC/관계/섹션 일치를 독립 확인한 후보만 무작위 선택")
    args = parser.parse_args()
    if args.timeout <= 0 or args.samples < 0:
        parser.error("timeout은 양수, samples는 음이 아닌 정수여야 함")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
