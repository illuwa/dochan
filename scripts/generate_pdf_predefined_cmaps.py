"""Adobe cmap-resources 사실 표에서 압축된 PDF Encoding CMap을 생성한다.

사용법: python -m scripts.generate_pdf_predefined_cmaps <원본 디렉터리> <출력 모듈>
원본은 저장소에 포함하지 않는다. 모든 입력은 고정 SHA-256으로 검증한다.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import zlib

from dochan.pdf.cmap import parse_encoding_cmap


MANIFEST = Path(__file__).with_name("pdf_predefined_cmap_hashes.json")
NAMES = set("""
GB-EUC-H GB-EUC-V GBpc-EUC-H GBpc-EUC-V GBK-EUC-H GBK-EUC-V
GBKp-EUC-H GBKp-EUC-V GBK2K-H GBK2K-V UniGB-UCS2-H UniGB-UCS2-V
UniGB-UTF16-H UniGB-UTF16-V
B5pc-H B5pc-V HKscs-B5-H HKscs-B5-V ETen-B5-H ETen-B5-V
ETenms-B5-H ETenms-B5-V CNS-EUC-H CNS-EUC-V UniCNS-UCS2-H
UniCNS-UCS2-V UniCNS-UTF16-H UniCNS-UTF16-V
83pv-RKSJ-H 90ms-RKSJ-H 90ms-RKSJ-V 90msp-RKSJ-H 90msp-RKSJ-V
90pv-RKSJ-H 90pv-RKSJ-V Add-RKSJ-H Add-RKSJ-V EUC-H EUC-V
Ext-RKSJ-H Ext-RKSJ-V H V UniJIS-UCS2-H UniJIS-UCS2-V
UniJIS-UCS2-HW-H UniJIS-UCS2-HW-V UniJIS-UTF16-H UniJIS-UTF16-V
KSC-EUC-H KSC-EUC-V KSCms-UHC-H KSCms-UHC-V KSCms-UHC-HW-H
KSCms-UHC-HW-V KSCpc-EUC-H KSCpc-EUC-V UniKS-UCS2-H UniKS-UCS2-V
UniKS-UTF16-H UniKS-UTF16-V
""".split())


def _copyright(source, name):
    for raw in source.splitlines():
        if raw.startswith(b"%%Copyright: Copyright"):
            return raw[len(b"%%Copyright: "):].decode("ascii").strip()
    raise ValueError("저작권 줄 없음: %s" % name)


def _integer(number):
    number = number * 2 if number >= 0 else -number * 2 - 1
    result = bytearray()
    while number >= 128:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return result


def _ranges(rows):
    result = bytearray()
    for size in (1, 2, 3, 4):
        selected = sorted((lo, hi, cid) for length, lo, hi, cid in rows
                          if length == size)
        result.extend(_integer(len(selected)))
        previous_hi, next_cid = -1, 0
        for lo, hi, cid in selected:
            result.extend(_integer(lo - previous_hi - 1))
            result.extend(_integer(hi - lo))
            result.extend(_integer(cid - next_cid))
            previous_hi, next_cid = hi, cid + hi - lo + 1
    return result


def generate(source_dir, output):
    expected = json.loads(MANIFEST.read_text(encoding="ascii"))
    sources = {}
    for relative, digest in expected.items():
        source = (source_dir / relative).read_bytes()
        if hashlib.sha256(source).hexdigest() != digest:
            raise ValueError("원본 SHA-256 불일치: %s" % relative)
        if relative != "LICENSE.md":
            sources[Path(relative).name] = source
    if set(sources) != NAMES:
        raise ValueError("원본 CMap 목록이 해시 목록과 다름")
    license_text = (source_dir / "LICENSE.md").read_text(encoding="utf-8").rstrip()
    lines = ['"""Adobe predefined Encoding CMaps; generated factual ranges.',
             "Source: https://github.com/adobe-type-tools/cmap-resources",
             "Modified: CMap ranges are parsed and compressed into this module.",
             "The original CMap files are not distributed with dochan.", ""]
    for name, source in sorted(sources.items()):
        lines.append("%s: %s" % (name, _copyright(source, name)))
    lines += ["", license_text, '"""', "TABLES = {"]
    for name, source in sorted(sources.items()):
        clean = re.sub(rb"%[^\r\n]*", b"", source)
        parents = re.findall(rb"/([A-Za-z0-9-]+)\s+usecmap\b", clean)
        parent = parents[-1].decode("ascii") if parents else ""
        if parent and parent not in sources and parent not in ("Identity-H", "Identity-V"):
            raise ValueError("선택 목록에 없는 부모 CMap: %s" % parent)
        warnings = []
        cmap = parse_encoding_cmap(source, warnings=warnings, parents=sources)
        if warnings:
            raise ValueError("CMap 파싱 경고: %s: %s" % (name, warnings[0]))
        meta = (cmap.codespaces, cmap.registry, cmap.ordering, parent,
                cmap.supplement, cmap.wmode)
        binary = _ranges(cmap.cidranges) + _ranges(cmap.notdefranges)
        packed = base64.b85encode(zlib.compress(binary, 9)).decode("ascii")
        lines.append("    %r: (%r, (" % (name, meta))
        lines.extend("        %r" % packed[i:i + 100] for i in range(0, len(packed), 100))
        lines.append("    )),")
    lines.append("}")
    output.write_text("\n".join(lines) + "\n", encoding="ascii")
    print("CMaps:", len(sources), "module bytes:", output.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.source_dir, args.output)


if __name__ == "__main__":
    main()
