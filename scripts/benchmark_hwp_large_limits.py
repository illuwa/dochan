"""합성 HWP 경계 입력의 공개 API 시간과 프로세스 최대 RSS를 측정한다.

각 사례는 새 프로세스에서 실행한다. RSS에는 인터프리터와 입력 생성이 포함되며,
Dochan 모델과 to_markdown·to_json 문자열을 동시에 보관한 상태에서 측정한다.
실행: /usr/bin/python3 -m scripts.benchmark_hwp_large_limits --output result.json
"""
import argparse
import json
import multiprocessing
import struct
import zlib

from scripts.probe_hwp_corrupt_sections import (
    deflate, distribution_stream, fingerprint, parse_public, probe, record, streams,
)


def _record(tag, level, data):
    return record(tag, level, data)


def _compressed_bytes(size):
    compressor = zlib.compressobj(wbits=-15)
    # Unknown records with a 1 MiB payload avoid making millions of objects.
    block = struct.pack("<II", 1023 | (0xFFF << 20), 1024 * 1024 - 8)
    block += bytes(1024 * 1024 - 8)
    chunks = []
    while size:
        count = min(size, len(block))
        chunks.append(compressor.compress(block[:count]))
        size -= count
    chunks.append(compressor.flush())
    return b"".join(chunks)


def measure(case):
    from dochan.hwp.doc_info import MAX_HWP_RECORDS as DOCINFO_RECORDS
    from dochan.hwp.section import MAX_HWP_RECORDS
    from dochan.utils.safe_decompress import MAX_DECOMPRESSED_SIZE

    compressed = False
    repeats = 1
    docinfo = b""
    distribution = False
    if case.startswith("corrupt_multisection_"):
        return probe(case.removeprefix("corrupt_multisection_"))
    if case == "empty_records_at_limit":
        data = struct.pack("<I", 1023) * MAX_HWP_RECORDS
    elif case == "empty_list_header_siblings":
        data = struct.pack("<I", 72 | (1 << 10))
        data += struct.pack("<I", 66) * (MAX_HWP_RECORDS - 1)
    elif case == "empty_records_over_limit":
        data = struct.pack("<I", 1023) * (MAX_HWP_RECORDS + 1)
    elif case in ("paragraphs_at_limit", "document_records_over_limit",
                  "docinfo_and_document_records_over_limit"):
        unit = _record(66, 0, bytes(22)) + _record(67, 1, "x\r".encode("utf-16-le"))
        data = unit * (MAX_HWP_RECORDS // 2)
        repeats = 1 if case == "paragraphs_at_limit" else 3
        if case == "docinfo_and_document_records_over_limit":
            docinfo = _record(21, 0, bytes(72)) * DOCINFO_RECORDS
    elif case in ("decompressed_bytes_at_limit", "decompressed_bytes_over_limit"):
        compressed = True
        data = _compressed_bytes(MAX_DECOMPRESSED_SIZE + (case.endswith("over_limit")))
    elif case == "docinfo_records_over_limit":
        data = b""
        docinfo = _record(21, 0, bytes(72)) * (DOCINFO_RECORDS + 1)
    elif case == "docinfo_char_shapes_at_limit":
        data = b""
        docinfo = _record(21, 0, bytes(72)) * DOCINFO_RECORDS
    elif case in ("repeated_checksum_failures", "distribution_repeated_checksum_failures"):
        # Eighty 4 MiB expansions exceed the 200 MiB document work budget.
        body = _record(1023, 0, bytes(4 * 1024 * 1024 - 8))
        distribution = case.startswith("distribution_")
        data = (distribution_stream(body) if distribution else
                deflate(body) + struct.pack("<II", zlib.crc32(body) ^ 1, len(body)))
        compressed = True
        repeats = 80
    elif case == "cells_at_limit":
        # One valid table allocates exactly the document cell budget.
        from dochan.hwp.section import MAX_HWP_DOCUMENT_CELLS
        columns = 100
        table = struct.pack("<IHH", 0, MAX_HWP_DOCUMENT_CELLS // columns, columns)
        data = (_record(66, 0, bytes(22)) + _record(71, 1, b" lbt")
                + _record(77, 2, table))
    else:
        raise ValueError(case)
    # All fixtures use compressed OLE streams, as real compressed HWP files do.
    if not compressed:
        data = deflate(data)
    contents = streams([data] * repeats, deflate(docinfo), distribution=distribution)
    reader, markdown, serialized, stats = parse_public(contents)
    stats.update(case=case, input_bytes=sum(map(len, contents.values())),
                 input_sections=repeats, retained_sections=len(reader.doc.sections),
                 char_shapes=len(reader.doc.char_shapes),
                 elements=sum(len(item.elements) for item in reader.doc.sections),
                 errors=reader.errors, markdown=fingerprint(markdown), json=fingerprint(serialized))
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", action="append", dest="cases",
                        help="한 사례만 실행하며 여러 번 지정할 수 있다.")
    args = parser.parse_args()
    cases = ["empty_records_at_limit", "empty_records_over_limit", "empty_list_header_siblings",
             "paragraphs_at_limit", "document_records_over_limit",
             "decompressed_bytes_at_limit", "decompressed_bytes_over_limit",
             "docinfo_records_over_limit", "docinfo_char_shapes_at_limit",
             "docinfo_and_document_records_over_limit", "cells_at_limit",
             "corrupt_multisection_invalid", "corrupt_multisection_truncated",
             "corrupt_multisection_checksum", "repeated_checksum_failures",
             "distribution_repeated_checksum_failures"]
    with multiprocessing.get_context("spawn").Pool(1, maxtasksperchild=1) as pool:
        rows = []
        for result in pool.imap(measure, args.cases or cases):
            rows.append(result)
            print(json.dumps(result), flush=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
