"""공개 HWP 코퍼스의 배포용 헤더·복호화·본문 추출을 검증한다.

사용법: /usr/bin/python3 -m scripts.probe_hwp_distribution CORPUS [--output JSON]
코퍼스를 복사하지 않고 공개 파일명과 집계만 출력한다.
"""

import argparse
import hashlib
import json
import re
import struct
import zlib
from collections import Counter
from pathlib import Path

from dochan import cfb

from dochan import Dochan
from dochan.constants import HWPTAG_DISTRIBUTE_DOC_DATA, HWPTAG_PARA_TEXT
from dochan.hwp.distdoc import _descramble
from dochan.hwp.header import FileHeader
from dochan.hwp.records.para_text import parse_para_text
from dochan.utils.aes import aes128_ecb_decrypt
from dochan.utils.bounded_io import MAX_OLE_DOCUMENT_SIZE, MAX_OLE_STREAM_SIZE
from dochan.utils.safe_decompress import MAX_DECOMPRESSED_SIZE


def _read_stream(ole, name):
    if ole.get_size(name) > MAX_OLE_STREAM_SIZE:
        raise ValueError("OLE stream size exceeds limit")
    return ole.openstream(name).read(MAX_OLE_STREAM_SIZE + 1)


def _raw_decrypt(raw):
    """생산 경로의 후처리에 영향받지 않고 AES 결과를 관찰한다."""
    if len(raw) < 260:
        raise ValueError("short distribution stream")
    header = struct.unpack_from("<I", raw)[0]
    if header & 1023 != HWPTAG_DISTRIBUTE_DOC_DATA or header >> 20 != 256:
        raise ValueError("unexpected distribution record header")
    block = bytearray(raw[4:260])
    offset = 4 + (block[0] & 15)
    _descramble(block)
    return aes128_ecb_decrypt(bytes(block[offset:offset + 16]), raw[260:])


def _paragraph_texts(data):
    texts = []
    offset = 0
    records = 0
    while offset < len(data):
        records += 1
        if records > 1000000 or offset + 4 > len(data):
            raise ValueError("record count limit or truncated record header")
        header = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        size = header >> 20
        if size == 4095:
            if offset + 4 > len(data):
                raise ValueError("truncated extended record size")
            size = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        if offset + size > len(data):
            raise ValueError("truncated record payload")
        if header & 1023 == HWPTAG_PARA_TEXT:
            text = parse_para_text(data[offset:offset + size])["text"]
            if text.strip():
                texts.append(text)
        offset += size
    return texts, records


def _normalize(text):
    return re.sub(r"\s+", "", text)


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_file(path, header):
    row = {"file": path.name, "compressed": header.is_compressed,
           "encrypted": header.is_encrypted, "sections": []}
    expected_texts = []
    with cfb.OleFileIO(str(path)) as ole:
        streams = [name for name in ole.listdir()
                   if len(name) == 2 and name[0] == "ViewText"
                   and re.fullmatch(r"Section\d+", name[1])]
        if len(streams) > 1000:
            raise ValueError("section count limit")
        for name in sorted(streams):
            result = {"stream": "/".join(name)}
            try:
                plaintext = _raw_decrypt(_read_stream(ole, name))
                result["decrypted_bytes"] = len(plaintext)
                if header.is_compressed:
                    inflater = zlib.decompressobj(-15)
                    data = inflater.decompress(plaintext, MAX_DECOMPRESSED_SIZE + 1)
                    if len(data) > MAX_DECOMPRESSED_SIZE:
                        raise ValueError("decompressed size limit")
                    if not inflater.eof:
                        raise ValueError("incomplete deflate stream")
                    trailing = inflater.unused_data
                    result["trailing_bytes"] = len(trailing)
                    result["trailing_hex"] = trailing[:64].hex()
                    result["crc_size_blocks_valid"] = (
                        32 <= len(trailing) <= 47
                        and not trailing[:-32].strip(b"\x00")
                        and not trailing[-28:-16].strip(b"\x00")
                        and not trailing[-12:].strip(b"\x00")
                        and struct.unpack_from("<I", trailing, len(trailing) - 32)[0]
                        == zlib.crc32(data) & 0xFFFFFFFF
                        and struct.unpack_from("<I", trailing, len(trailing) - 16)[0]
                        == len(data)
                    )
                    consumed = len(plaintext) - len(trailing)
                    result["crc_size_packed_valid"] = (
                        len(trailing) == 8 + (-(consumed + 8) % 16)
                        and not trailing[8:].strip(b"\x00")
                        and struct.unpack_from("<I", trailing, 0)[0]
                        == zlib.crc32(data) & 0xFFFFFFFF
                        and struct.unpack_from("<I", trailing, 4)[0] == len(data)
                    )
                else:
                    data = plaintext
                texts, record_count = _paragraph_texts(data)
                expected_texts.extend(texts)
                result["inflated_bytes"] = len(data)
                result["record_count"] = record_count
                result["text_paragraphs"] = len(texts)
            except Exception as exc:
                result["error"] = str(exc)
            row["sections"].append(result)
        preview = ""
        if ole.exists("PrvText"):
            preview = _read_stream(ole, "PrvText").decode("utf-16-le", errors="replace").strip("\x00")
    document = Dochan(str(path))
    plain_text = document.to_plain_text()
    actual = _normalize(plain_text)
    without_link_annotations = _normalize(re.sub(r" <https?://[^>]+>", "", plain_text))
    expected = [_normalize(text) for text in expected_texts if _normalize(text)]
    row["expected_text_paragraphs"] = len(expected)
    row["present_text_paragraphs"] = sum(text in actual for text in expected)
    row["raw_text_paragraph_presence"] = (
        row["present_text_paragraphs"] / len(expected) if expected else None
    )
    row["present_paragraphs_without_link_annotations"] = sum(
        text in without_link_annotations for text in expected
    )
    row["preview_characters"] = len(_normalize(preview))
    row["preview_present"] = bool(preview) and _normalize(preview) in actual
    row["body_characters"] = len(document.to_plain_text())
    row["errors"] = document.errors
    return row


def probe(corpus):
    root = Path(corpus)
    source = root / "hwp" if (root / "hwp").is_dir() else root
    files = sorted(source.glob("*.hwp"))
    rows = []
    scan_errors = []
    encrypted = 0
    distribution_digests = set()
    for path in files:
        try:
            if path.stat().st_size > MAX_OLE_DOCUMENT_SIZE:
                raise ValueError("OLE document size exceeds limit")
            with cfb.OleFileIO(str(path)) as ole:
                if not ole.exists("FileHeader"):
                    continue
                header = FileHeader.parse(_read_stream(ole, "FileHeader"))
                encrypted += int(header.is_encrypted)
            if header.is_distribution:
                rows.append(_probe_file(path, header))
                distribution_digests.add(_file_digest(path))
        except Exception as exc:
            scan_errors.append({"file": path.name, "error": str(exc)})
    sections = [section for row in rows for section in row["sections"]]
    expected = sum(row["expected_text_paragraphs"] for row in rows)
    matched = sum(row["present_text_paragraphs"] for row in rows)
    annotation_matched = sum(row["present_paragraphs_without_link_annotations"] for row in rows)
    return {
        "summary": {
            "hwp_scanned": len(files), "distribution_files": len(rows),
            "unique_distribution_files": len(distribution_digests),
            "password_encrypted_files": encrypted, "scan_errors": len(scan_errors),
            "distribution_sections": len(sections),
            "trailing_length_histogram": dict(sorted(Counter(
                section.get("trailing_bytes") for section in sections
                if "trailing_bytes" in section).items())),
            "valid_crc_size_blocks": sum(bool(section.get("crc_size_blocks_valid"))
                                         for section in sections),
            "valid_crc_size_packed": sum(bool(section.get("crc_size_packed_valid"))
                                         for section in sections),
            "valid_crc_size_trailers": sum(bool(section.get("crc_size_blocks_valid"))
                                           or bool(section.get("crc_size_packed_valid"))
                                           for section in sections),
            "nonempty_files": sum(row["body_characters"] > 0 for row in rows),
            "files_with_errors": sum(bool(row["errors"]) for row in rows),
            "expected_text_paragraphs": expected,
            "present_text_paragraphs": matched,
            "raw_text_paragraph_presence": matched / expected if expected else None,
            "present_paragraphs_without_link_annotations": annotation_matched,
            "raw_text_without_link_annotations_presence": (
                annotation_matched / expected if expected else None
            ),
        },
        "distribution": rows, "scan_errors": scan_errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = probe(args.corpus)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
