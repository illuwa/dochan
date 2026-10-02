"""Inventory a local HWPX corpus without parsing or expanding document payloads.

Container signatures are independent of extensions; ZIP metadata does not prove
that a file is HWPX or that its payload CRC/XML is valid. Only version.xml may be
inflated, with a fixed budget, to obtain generator application/version metadata.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import struct
import zlib
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import olefile
from lxml import etree


HASH_CHUNK_BYTES = 1024 * 1024
MAX_ZIP_DIRECTORY_BYTES = 16 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_GENERATOR_BYTES = 64 * 1024
MAX_SOURCE_INDEX_BYTES = 16 * 1024 * 1024
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x06\x06", b"PK\x07\x08")


def _unsafe_part_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return (normalized.startswith("/") or ".." in normalized.split("/")
            or re.match(r"^[A-Za-z]:", normalized) is not None or "\0" in name)


def _generator_metadata(archive, infos):
    versions = [info for info in infos if info.filename == "version.xml"]
    if not versions:
        return None, []
    if len(versions) != 1:
        return None, ["ambiguous_generator_metadata"]
    info = versions[0]
    if info.flag_bits & 1:
        return None, ["encrypted_generator_metadata"]
    if max(info.file_size, info.compress_size) > MAX_GENERATOR_BYTES:
        return None, ["generator_size_limit"]
    try:
        with archive.open(info) as stream:
            data = stream.read(MAX_GENERATOR_BYTES + 1)
        if len(data) > MAX_GENERATOR_BYTES:
            return None, ["generator_size_limit"]
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False,
                                 no_network=True, huge_tree=False)
        root = etree.fromstring(data, parser=parser)
        if root.getroottree().docinfo.doctype:
            return None, ["invalid_generator_xml"]
        generator = {
            key: root.get(attribute)
            for key, attribute in (("application", "application"), ("app_version", "appVersion"))
            if root.get(attribute) is not None
        }
        return generator or None, []
    except etree.XMLSyntaxError:
        return None, ["invalid_generator_xml"]
    except (OSError, EOFError, ValueError, RuntimeError, zipfile.BadZipFile, zlib.error):
        return None, ["unreadable_generator_metadata"]


def _zip_metadata(stream):
    # The public ZipFile constructor allocates the entire central directory.
    # CPython's bounded EOCD reader also handles ZIP64; inspect its declarations
    # before constructing ZipFile. No local file data is read by this preflight.
    end = zipfile._EndRecData(stream)
    if end is None:
        raise zipfile.BadZipFile("missing central directory")
    if (end[zipfile._ECD_SIZE] > MAX_ZIP_DIRECTORY_BYTES
            or end[zipfile._ECD_ENTRIES_TOTAL] > MAX_ZIP_ENTRIES):
        return None, ["zip_metadata_limit"]
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            return None, ["zip_metadata_limit"]
        if len(infos) != end[zipfile._ECD_ENTRIES_TOTAL]:
            raise zipfile.BadZipFile("inconsistent entry count")
        parts = []
        for index, info in enumerate(infos):
            parts.append({
                "name": info.filename,
                "index": index,
                "bytes": info.file_size,
                "compressed_bytes": info.compress_size,
                "compression_method": info.compress_type,
                "compression_ratio": (round(info.file_size / info.compress_size, 6)
                                      if info.compress_size else None),
                "crc32": f"{info.CRC:08x}",
                "encrypted": bool(info.flag_bits & 1),
                "is_directory": info.is_dir(),
            })
        names = Counter(info.filename for info in infos)
        generator, errors = _generator_metadata(archive, infos)
        return {
            "entry_count": len(infos),
            "compressed_bytes": sum(info.compress_size for info in infos),
            "uncompressed_bytes": sum(info.file_size for info in infos),
            "encrypted_entries": sum(bool(info.flag_bits & 1) for info in infos),
            "duplicate_names": sorted(name for name, count in names.items() if count > 1),
            "unsafe_names": sorted(name for name in names if _unsafe_part_name(name)),
            "parts": sorted(parts, key=lambda part: (part["name"], part["index"])),
            "generator": generator,
        }, errors


def inspect_file(path: Path, relative_path: str) -> dict:
    record = {
        "path": relative_path,
        "extension": path.suffix.lower(),
        "bytes": None,
        "sha256": None,
        "container": "unknown",
        "extension_mismatch": False,
        "zip": None,
        "sources": [],
        "errors": [],
    }
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            record["errors"] = ["not_regular_file"]
            return record
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            magic = stream.read(8)
            digest.update(magic)
            size = len(magic)
            for chunk in iter(lambda: stream.read(HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
                size += len(chunk)
            record["bytes"] = size
            record["sha256"] = digest.hexdigest()
            stream.seek(0)
            if magic.startswith(ZIP_MAGICS):
                record["container"] = "zip"
                try:
                    record["zip"], record["errors"] = _zip_metadata(stream)
                except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError,
                        ValueError, OSError, struct.error, NotImplementedError):
                    record["errors"] = ["invalid_zip"]
            elif magic == OLE_MAGIC:
                record["container"] = "ole"
                try:
                    # Directory/FAT validation only: do not open any OLE stream.
                    with olefile.OleFileIO(stream, raise_defects=olefile.DEFECT_INCORRECT):
                        pass
                except (OSError, ValueError, EOFError, struct.error):
                    record["errors"] = ["invalid_ole"]
            else:
                record["errors"] = ["empty_file" if size == 0 else "unrecognized_magic"]
    except OSError:
        record["errors"] = ["unreadable_file"]
    expected = {".hwpx": "zip", ".hwp": "ole", ".zip": "zip"}.get(record["extension"])
    record["extension_mismatch"] = expected is not None and expected != record["container"]
    return record


def _load_sources(index_path: Path) -> dict:
    try:
        with index_path.open("rb") as stream:
            data = stream.read(MAX_SOURCE_INDEX_BYTES + 1)
        if len(data) > MAX_SOURCE_INDEX_BYTES:
            raise ValueError("source index exceeds size limit")
        payload = json.loads(data)
        entries = payload.get("fixtures") if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ValueError("source index must contain a list")
        sources = defaultdict(list)
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError("source index entries require a path")
            if any(key in entry and entry[key] is not None and not isinstance(entry[key], str)
                   for key in ("source", "license")):
                raise ValueError("source and license must be strings or null")
            # SOURCES.json paths are relative to the index, never basename joins.
            source_path = (index_path.parent / entry["path"]).resolve()
            label = {field: entry.get(field) for field in ("source", "license")}
            if label not in sources[source_path]:
                sources[source_path].append(label)
        return {key: sorted(value, key=to_json) for key, value in sources.items()}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read source index JSON") from exc


def build_inventory(input_dir: Path, source_index: Optional[Path] = None) -> dict:
    input_dir = Path(input_dir)
    if input_dir.is_symlink() or not input_dir.is_dir():
        raise ValueError("input must be an existing non-symlink directory")
    sources = _load_sources(Path(source_index)) if source_index is not None else {}
    paths = []

    def walk_error(error):
        raise ValueError("cannot enumerate input directory") from error

    for directory, dirnames, filenames in os.walk(input_dir, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        paths.extend(parent / name for name in filenames)
        paths.extend(parent / name for name in dirnames if (parent / name).is_symlink())
    files = []
    hashes = defaultdict(list)
    for path in sorted(paths, key=lambda path: path.relative_to(input_dir).as_posix()):
        record = inspect_file(path, path.relative_to(input_dir).as_posix())
        if sources and record["sha256"] is not None:
            record["sources"] = sources.get(path.resolve(), [])
        files.append(record)
        if record["sha256"] is not None:
            hashes[record["sha256"]].append(record["path"])
    duplicate_groups = [
        {"sha256": digest, "paths": sorted(paths)}
        for digest, paths in sorted(hashes.items()) if len(paths) > 1
    ]
    return {
        "schema_version": 1,
        "files": files,
        "duplicate_groups": duplicate_groups,
        "summary": {
            "total_files": len(files),
            "total_bytes": sum(record["bytes"] or 0 for record in files),
            "containers": dict(sorted(Counter(record["container"] for record in files).items())),
            "extensions": dict(sorted(Counter(record["extension"] for record in files).items())),
            "extension_mismatches": sum(record["extension_mismatch"] for record in files),
            "files_with_errors": sum(bool(record["errors"]) for record in files),
            "errors": dict(sorted(Counter(error for record in files for error in record["errors"]).items())),
            "hashed_files": sum(record["sha256"] is not None for record in files),
            "unique_sha256": len(hashes),
            "duplicate_groups": len(duplicate_groups),
            "duplicate_files": sum(len(group["paths"]) - 1 for group in duplicate_groups),
            "files_in_duplicate_groups": sum(len(group["paths"]) for group in duplicate_groups),
            "files_with_source": sum(bool(record["sources"]) for record in files),
        },
    }


def to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="Scan all files recursively, irrespective of extension")
    parser.add_argument("--output", type=Path, help="JSON output outside the input directory; default: stdout")
    parser.add_argument("--source-index", type=Path, help="Optional SOURCES.json with paths relative to its parent")
    args = parser.parse_args()
    try:
        if args.output is not None:
            output = args.output.resolve()
            root = args.input_dir.resolve()
            if output == root or root in output.parents:
                raise ValueError("output must be outside the input directory")
            if args.source_index is not None and output == args.source_index.resolve():
                raise ValueError("output must not overwrite the source index")
        report = build_inventory(args.input_dir, source_index=args.source_index)
        payload = to_json(report)
        if args.output is None:
            print(payload, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
            print(to_json(report["summary"]), end="")
    except ValueError as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("cannot write inventory output")
    return 1 if report["summary"]["files_with_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
