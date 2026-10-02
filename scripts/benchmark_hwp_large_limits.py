"""합성 HWP 경계 입력의 파싱 시간과 프로세스 최대 RSS를 측정한다.

각 사례는 새 프로세스에서 실행한다. RSS에는 인터프리터와 입력 생성이 포함된다.
실행: /usr/bin/python3 -m scripts.benchmark_hwp_large_limits --output result.json
"""
import argparse
import json
import multiprocessing
import resource
import struct
import sys
import time
import zlib


def _record(tag, level, data):
    return struct.pack("<I", tag | level << 10 | len(data) << 20) + data


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
    from dochan.hwp.doc_info import DocInfoParser
    from dochan.hwp.section import MAX_HWP_RECORDS, SectionParser
    from dochan.utils.safe_decompress import MAX_DECOMPRESSED_SIZE

    parser = SectionParser()
    compressed = False
    repeats = 1
    if case == "empty_records_at_limit":
        data = struct.pack("<I", 1023) * MAX_HWP_RECORDS
    elif case == "empty_list_header_siblings":
        data = struct.pack("<I", 72 | (1 << 10))
        data += struct.pack("<I", 66) * (MAX_HWP_RECORDS - 1)
    elif case == "empty_records_over_limit":
        data = struct.pack("<I", 1023) * (MAX_HWP_RECORDS + 1)
    elif case in ("paragraphs_at_limit", "document_records_over_limit"):
        unit = _record(66, 0, bytes(22)) + _record(67, 1, "x\r".encode("utf-16-le"))
        data = unit * (MAX_HWP_RECORDS // 2)
        repeats = 3 if case == "document_records_over_limit" else 1
    elif case in ("decompressed_bytes_at_limit", "decompressed_bytes_over_limit"):
        compressed = True
        data = _compressed_bytes(MAX_DECOMPRESSED_SIZE + (case.endswith("over_limit")))
    elif case == "docinfo_records_over_limit":
        parser = DocInfoParser()
        data = struct.pack("<I", 1023) * (MAX_HWP_RECORDS + 1)
    elif case == "cells_at_limit":
        # One valid table allocates exactly the document cell budget.
        from dochan.hwp.section import MAX_HWP_DOCUMENT_CELLS
        columns = 100
        table = struct.pack("<IHH", 0, MAX_HWP_DOCUMENT_CELLS // columns, columns)
        data = (_record(66, 0, bytes(22)) + _record(71, 1, b" lbt")
                + _record(77, 2, table))
    else:
        raise ValueError(case)
    start = time.perf_counter()
    results = [parser.parse_stream(data, compressed) for _ in range(repeats)]
    elapsed = time.perf_counter() - start
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    elements = sum(len(getattr(item, "elements", [])) for item in results)
    errors = parser.errors
    return dict(case=case, seconds=round(elapsed, 6), input_bytes=len(data),
                retained_sections=repeats, elements=elements, errors=errors,
                peak_rss_bytes=rss if sys.platform == "darwin" else rss * 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    cases = ["empty_records_at_limit", "empty_records_over_limit", "empty_list_header_siblings",
             "paragraphs_at_limit", "document_records_over_limit",
             "decompressed_bytes_at_limit", "decompressed_bytes_over_limit",
             "docinfo_records_over_limit", "cells_at_limit"]
    with multiprocessing.get_context("spawn").Pool(1, maxtasksperchild=1) as pool:
        rows = []
        for result in pool.imap(measure, cases):
            rows.append(result)
            print(json.dumps(result), flush=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
