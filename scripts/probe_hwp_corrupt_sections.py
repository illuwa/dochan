"""합성 손상 다중 섹션을 공개 Dochan API로 비교한다.

OLE 컨테이너만 메모리 대역으로 바꾸며 파서·AES·압축·출력기는 그대로 쓴다.
--source-root로 HEAD~1 추출본과 작업 소스를 각각 실행할 수 있다.
"""
import argparse
import hashlib
import io
import json
import resource
import struct
import sys
import tempfile
import time
import zlib
from pathlib import Path
from unittest.mock import patch


def record(tag, level, data):
    if len(data) >= 4095:
        return struct.pack("<II", tag | level << 10 | 4095 << 20, len(data)) + data
    return struct.pack("<I", tag | level << 10 | len(data) << 20) + data


def section(text):
    return record(66, 0, bytes(22)) + record(67, 1, (text + "\r").encode("utf-16-le"))


def deflate(data):
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


def distribution_stream(body, bad_checksum=True):
    """직접 조립한 DISTRIBUTE_DOC_DATA와 AES-ECB 암호문을 반환한다."""
    from dochan.hwp.distdoc import _descramble
    from dochan.utils.aes import _encrypt_block, _key_expansion

    seed = bytes(256)
    key_data = bytearray(seed)
    _descramble(key_data)
    key = bytes(key_data[4:20])
    checksum = zlib.crc32(body) ^ int(bad_checksum)
    payload = deflate(body) + struct.pack("<II", checksum, len(body))
    payload += bytes(-len(payload) % 16)
    expanded = _key_expansion(key)
    encrypted = b"".join(_encrypt_block(payload[i:i + 16], expanded, 10)
                         for i in range(0, len(payload), 16))
    return record(28, 0, seed) + encrypted


def streams(sections, docinfo=None, compressed=True, distribution=False):
    header = bytearray(256)
    header[:32] = b"HWP Document File".ljust(32, b"\x00")
    struct.pack_into("<BBBBI", header, 32, 0, 0, 0, 5,
                     int(compressed) | (4 if distribution else 0))
    if docinfo is None:
        docinfo = deflate(b"") if compressed else b""
    result = {"FileHeader": bytes(header), "DocInfo": docinfo}
    storage = "ViewText" if distribution else "BodyText"
    result.update(("%s/Section%d" % (storage, index), data)
                  for index, data in enumerate(sections))
    return result


class MemoryOle:
    def __init__(self, contents):
        self.contents = contents

    def exists(self, name):
        return name in self.contents

    def openstream(self, name):
        return io.BytesIO(self.contents[name])

    def get_size(self, name):
        return len(self.contents[name])

    def listdir(self, **kwargs):
        return [name.split("/") for name in self.contents]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def parse_public(contents):
    """입력과 DocInfo·문단 모델·두 직렬화 결과를 모두 유지한 채 측정한다."""
    from dochan import Dochan

    with tempfile.TemporaryDirectory(prefix="dochan-synthetic-") as directory:
        filename = Path(directory) / "synthetic.hwp"
        filename.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        with patch("dochan.reader.olefile.OleFileIO", side_effect=lambda *_: MemoryOle(contents)):
            start = time.perf_counter()
            reader = Dochan(str(filename))
            parse_time = time.perf_counter() - start
            markdown = reader.to_markdown()
            markdown_time = time.perf_counter() - start - parse_time
            serialized = reader.to_json()
            elapsed = time.perf_counter() - start
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    stats = {"api": "Dochan -> to_markdown -> to_json", "seconds": round(elapsed, 6),
             "parse_seconds": round(parse_time, 6), "markdown_seconds": round(markdown_time, 6),
             "json_seconds": round(elapsed - parse_time - markdown_time, 6),
             "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024}
    return reader, markdown, serialized, stats


def fingerprint(text):
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "characters": len(text)}


def probe(damage, count=1000):
    body = section("S0-text")
    broken = deflate(body)
    if damage == "checksum":
        broken += struct.pack("<II", zlib.crc32(body) ^ 1, len(body))
    elif damage == "truncated":
        broken = broken[:-1]
    elif damage == "invalid":
        broken = b"\xff"
    else:
        raise ValueError(damage)
    data = [broken] + [deflate(section("S%d-text" % i)) for i in range(1, count)]
    reader, markdown, serialized, stats = parse_public(streams(data))
    expected = ["S%d-text" % i for i in range(1, count)]
    actual = [element.text for item in reader.doc.sections for element in item.elements]
    actual_set = set(actual)
    stats.update(case="corrupt_multisection_" + damage, expected_valid_sections=count - 1,
                 retained_valid_sections=sum(text in actual_set for text in expected),
                 valid_texts_match=actual == expected, markdown=fingerprint(markdown),
                 json=fingerprint(serialized), errors=reader.errors)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sections", type=int, default=1000)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.source_root).resolve()))
    rows = [probe(damage, args.sections) for damage in ("invalid", "truncated", "checksum")]
    Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
