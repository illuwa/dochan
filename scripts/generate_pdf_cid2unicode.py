"""Adobe mapping-resources-pdf/pdf2unicode 표에서 CID 사실 데이터를 생성한다.

사용법: python -m scripts.generate_pdf_cid2unicode <원본 디렉터리> <출력 모듈>
원본은 저장소에 포함하지 않는다. 라이선스: BSD-3-Clause.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

from dochan.pdf.cmap import parse_tounicode


ORDERINGS = ("CNS1", "GB1", "Japan1", "KR", "Korea1")
SOURCE_SHA256 = {
    "Adobe-CNS1-UCS2": "8375afd535e153a7e3bcf448be93e5012b26229547a20d52520e46e3c386351f",
    "Adobe-GB1-UCS2": "368b40ec05568faf323cfbbddf23c60d566bbc88e366981eb6541b026381a3b8",
    "Adobe-Japan1-UCS2": "6a9693361647a37996312cc57071bb79f8c06411207be7c730a83fda1254cd82",
    "Adobe-KR-UCS2": "6861a3208f331ecd73369c5d51eacf3b72c820fe3c87524f79c9ac1bb16830ec",
    "Adobe-Korea1-UCS2": "45bcf869acdcec2507f75836919e589e7137b9f9dbaa8e4975747035024248ef",
    "LICENSE.txt": "feb8b068a417681821823ef2e8995072aa111121fa11f8664038f78717f4497c",
}


def _encode(source):
    mapping = parse_tounicode(source).mapping
    values = {cid: value for (_length, cid), value in mapping.items()
              if value and "\ufffd" not in value}
    dense = bytearray((max(values) + 1) * 4)
    extra = {}
    for cid, value in values.items():
        if len(value) == 1:
            dense[cid * 4:cid * 4 + 4] = ord(value).to_bytes(4, "big")
        else:
            extra[cid] = value
    return (base64.b85encode(zlib.compress(dense, 9)).decode("ascii"),
            base64.b85encode(zlib.compress(json.dumps(extra, ensure_ascii=False,
                                                   separators=(",", ":")).encode("utf-8"), 9)).decode("ascii"))


def generate(source_dir, output):
    for name, expected in SOURCE_SHA256.items():
        actual = hashlib.sha256((source_dir / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("원본 SHA-256 불일치: %s" % name)
    license_text = (source_dir / "LICENSE.txt").read_text(encoding="utf-8")
    lines = ['"""Adobe CID to Unicode fact tables. Generated; do not edit.',
             "Source: https://github.com/adobe-type-tools/mapping-resources-pdf/tree/master/pdf2unicode",
             "Modified: CID mappings are parsed and compressed into this module.",
             "The original CMap files are not distributed with dochan.",
             "", license_text.rstrip(), '"""', "TABLES = {"]
    hashes = {}
    for ordering in ORDERINGS:
        path = source_dir / ("Adobe-" + ordering + "-UCS2")
        source = path.read_bytes()
        hashes[path.name] = hashlib.sha256(source).hexdigest()
        dense, extra = _encode(source)
        lines.append("    %r: (" % ordering)
        for payload in (dense, extra):
            lines.append("        (")
            lines.extend("            %r" % payload[i:i + 100]
                         for i in range(0, len(payload), 100))
            lines.append("        ),")
        lines.append("    ),")
        lines.append("    # SHA-256 %s %s" % (path.name, hashlib.sha256(source).hexdigest()))
    lines.append("}")
    output.write_text("\n".join(lines) + "\n", encoding="ascii")
    for name, digest in hashes.items():
        print("SHA-256 %s: %s" % (name, digest))
    print("SHA-256 LICENSE.txt: %s" % hashlib.sha256(
        (source_dir / "LICENSE.txt").read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.source_dir, args.output)


if __name__ == "__main__":
    main()
