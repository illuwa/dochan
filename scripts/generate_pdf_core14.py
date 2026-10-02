"""로컬 Adobe AFM에서 폭·내장 인코딩 데이터를 재현 가능하게 생성한다.

실행: python -m scripts.generate_pdf_core14 AFM_DIR --output MODULE --notice NOTICE
fontTools는 로컬 생성 시에만 Adobe Glyph List를 읽는 데 사용한다.
생성된 모듈과 dochan의 런타임에는 fontTools 의존성이 없다.

입력 출처: Adobe 가 배포한 Core14_AFMs.zip(원 URL 은 현재 404, Wayback Machine 2017 스냅샷에서 확인;
SHA-256 8c892c3c49553cfd2d2a27c4495b4bb12e2875115be7fd127ed3876df19d8654). 같은 14개 AFM 과 MustRead.html 이
Apache PDFBox 저장소 `pdfbox/src/main/resources/org/apache/pdfbox/resources/afm/` 에도 그대로 실려 있다.
공식 zip 은 CRLF 줄바꿈이라 파싱 전에 LF 로 정규화한다. SOURCE_SHA256 은 정규화한 내용의 해시다.
"""
import argparse
import base64
import hashlib
import importlib.metadata
import json
import re
import textwrap
import zlib
from pathlib import Path


NOTICE_MARKER = "Adobe Core 14 AFM metrics and Adobe Glyph List"


def generate(directory):
    from fontTools import agl

    metrics, encodings, unicode_map, notices, hashes = {}, {}, {}, set(), {}
    files = sorted(directory.glob("*.afm"))
    if len(files) != 14:
        raise ValueError("Core 14 AFM 파일 14개가 필요합니다")
    for path in files:
        raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        source = raw.decode("latin-1")
        font = re.search(r"^FontName (.+)$", source, re.M).group(1)
        widths, encoding = {}, {}
        for line in source.splitlines():
            if line.startswith("Notice ") or (line.startswith("Comment ") and "Copyright" in line):
                notices.add(line.split(" ", 1)[1])
            if not line.startswith("C "):
                continue
            fields = dict(part.strip().split(" ", 1) for part in line.split(";") if part.strip())
            glyph, code = fields["N"], int(fields["C"])
            widths[glyph] = int(fields["WX"])
            if 0 <= code <= 255:
                encoding[code] = glyph
            value = agl.toUnicode(glyph, isZapfDingbats=(font == "ZapfDingbats"))
            if value:
                unicode_map[glyph] = value
        metrics[font] = widths
        if font in ("Symbol", "ZapfDingbats"):
            encodings[font + "Encoding"] = encoding
        elif font == "Times-Roman":
            encodings["StandardEncoding"] = encoding
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    # ISO 32000-1 Annex D: these byte encodings use the same Unicode repertoire
    # as Python's codecs, with the PDF-specific space/hyphen/bullet exceptions.
    reverse = {value: glyph for glyph, value in sorted(unicode_map.items())}
    for name, codec in (("WinAnsiEncoding", "cp1252"), ("MacRomanEncoding", "mac_roman")):
        encoding = {}
        for code in range(32, 256):
            value = bytes([code]).decode(codec, errors="replace")
            glyph = reverse.get(value)
            if glyph:
                encoding[code] = glyph
        if name == "WinAnsiEncoding":
            encoding.update({160: "space", 173: "hyphen"})
            for code in (127, 129, 141, 143, 144, 157):
                encoding[code] = "bullet"
        else:
            encoding.update({202: "space", 219: "currency"})
            # Annex D's PDF MacRoman is not the modern Macintosh codec:
            # the Apple logo and these mathematical symbols are undefined.
            for code in (173, 176, 178, 179, 182, 183, 184, 185, 186, 195,
                         197, 198, 215, 240):
                encoding.pop(code, None)
        encodings[name] = encoding
    html = (directory / "MustRead.html").read_text(encoding="latin-1")
    paragraph = re.search(r"This file and the 14 PostScript.*?AFM files\.", html, re.S).group(0)
    # Retain the source AGL redistribution notice, including its disclaimer.
    agl_notice = agl._aglText.split("# Name:", 1)[0]
    agl_notice = "\n".join(line.removeprefix("# ").removeprefix("#") for line in agl_notice.splitlines()
                            if not line.startswith("# ---")).strip()
    fonttools_license = importlib.metadata.distribution("fonttools").read_text("licenses/LICENSE")
    if not fonttools_license:
        raise ValueError("FontTools ZapfDingbats 대응표의 MIT 고지를 찾지 못했습니다")
    notice = (NOTICE_MARKER + "\n\n" + "\n".join(sorted(notices)) + "\n\n" + paragraph
              + "\n\nModified: dochan extracts only glyph names, advance widths (WX) and built-in encoding codes "
              "from the AFM files, adds a Unicode mapping using the Adobe Glyph List, and rebuilds the WinAnsi and "
              "MacRoman tables from Python codecs. The original AFM files are not distributed with dochan.\n"
              "(AFM 에서 글리프 이름·폭·내장 인코딩 코드만 추출하고 Adobe Glyph List 로 유니코드 대응표를 더한 수정본이며, "
              "원본 AFM 은 배포하지 않습니다.)\n\n"
              + agl_notice + "\n\nFontTools ZapfDingbats Unicode mapping "
              "(Adobe ITC Zapf Dingbats Glyph List, BSD-3, via fontTools):\n\n" + fonttools_license)
    payload = json.dumps({"widths": metrics, "encodings": encodings, "unicode": unicode_map},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    compressed = base64.b85encode(zlib.compress(payload, 9)).decode()
    header = "\n".join("# " + line if line else "#" for line in notice.splitlines())
    module = (header + '\n\n"""Generated by scripts/generate_pdf_core14.py; do not edit by hand."""\n'
              + "import base64\nimport json\nimport zlib\n\n"
              + "SOURCE_SHA256 = " + repr(hashes) + "\n\n_DATA = (\n"
              + "\n".join("    " + repr(line) for line in textwrap.wrap(compressed, 100, break_on_hyphens=False))
              + "\n)\n_TABLES = json.loads(zlib.decompress(base64.b85decode(_DATA)))\n"
              + 'GLYPH_WIDTHS = _TABLES["widths"]\nGLYPH_UNICODE = _TABLES["unicode"]\n'
              + 'ENCODINGS = {name: {int(code): glyph for code, glyph in table.items()}\n'
              + '             for name, table in _TABLES["encodings"].items()}\n'
              + "del _TABLES, _DATA\n")
    return module, notice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("afm_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notice", type=Path)
    args = parser.parse_args()
    module, notice = generate(args.afm_dir)
    args.output.write_text(module, encoding="utf-8")
    if args.notice:
        existing = args.notice.read_text(encoding="utf-8") if args.notice.exists() else ""
        # 생성 고지는 NOTICE 끝에 둔다 — 다시 생성하면 표지부터 끝까지를 바꾼다
        if NOTICE_MARKER in existing:
            existing = existing[:existing.index(NOTICE_MARKER)]
        args.notice.write_text(existing.rstrip() + "\n\n" + notice.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
