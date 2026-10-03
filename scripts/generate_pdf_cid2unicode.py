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
    lines = ['"""Adobe CID to Unicode fact tables. Generated; do not edit."""',
             "# Source: https://github.com/adobe-type-tools/mapping-resources-pdf/tree/master/pdf2unicode",
             "# License: BSD-3-Clause; see NOTICE and docs/THIRD_PARTY.md.",
             "TABLES = {"]
    for ordering in ORDERINGS:
        path = source_dir / ("Adobe-" + ordering + "-UCS2")
        source = path.read_bytes()
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.source_dir, args.output)


if __name__ == "__main__":
    main()
