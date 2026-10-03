"""공개 PDF 코퍼스의 ToUnicode 없는 Type0 인코딩을 전수 집계한다.

사용법: python -m scripts.probe_pdf_predefined_cmap <PDF 디렉터리> <JSON 출력>
PDF 본문이나 내부 문서 정보는 저장하지 않는다.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from dochan.pdf.objects import PDFName, PDFRef, PDFStream
from dochan.pdf.structure import PDFFile


def census(corpus):
    rows = defaultdict(lambda: {"fonts": 0, "files": []})
    failures = {}
    total = 0
    stream_fonts = 0
    stream_files = set()
    for path in sorted(corpus.glob("*.pdf")):
        try:
            pdf = PDFFile(path.read_bytes())
            names = set()
            for number in sorted(set(pdf.xref) | set(pdf._compressed)):
                obj = pdf.get_object(PDFRef(number, 0))
                if not isinstance(obj, dict) or str(obj.get("Subtype")) != "Type0":
                    continue
                encoding = pdf.resolve(obj.get("Encoding"))
                if isinstance(encoding, PDFStream):
                    stream_fonts += 1
                    stream_files.add(path.name)
                if pdf.resolve(obj.get("ToUnicode")) is not None:
                    continue
                key = str(encoding) if isinstance(encoding, PDFName) else (
                    "Encoding stream" if isinstance(encoding, PDFStream) else "other")
                rows[key]["fonts"] += 1
                names.add(key)
            for name in names:
                rows[name]["files"].append(path.name)
            total += 1
        except Exception as exc:
            failures[path.name] = type(exc).__name__
    return {"scanned": total, "encoding_stream_fonts": stream_fonts,
            "encoding_stream_files": sorted(stream_files),
            "groups": dict(sorted(rows.items())), "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = census(args.corpus)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PDF", result["scanned"], "groups", len(result["groups"]),
          "failures", len(result["failures"]))


if __name__ == "__main__":
    main()
