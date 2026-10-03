"""공개 pdf.js PDF의 CID 경고와 PDFium 쪽별 문자 다중집합을 비교한다.

사용법: python -m scripts.probe_pdf_cid_unicode <코퍼스> <JSON 출력> [--repo 경로]
출력에는 텍스트 원문 대신 문자 수와 일치 수만 저장한다.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unicodedata


def _counts(text):
    return Counter(ch for ch in text if not ch.isspace()
                   and unicodedata.category(ch) not in ("Cc", "Co", "Cs", "Cn")
                   and ch != "\ufffd")


def _score(actual, expected):
    a, e = _counts(actual), _counts(expected)
    return {"actual": sum(a.values()), "expected": sum(e.values()),
            "matched": sum((a & e).values())}


def probe(path, include_all=False):
    import pypdfium2
    from dochan.model.document import Document
    from dochan.output.plain_text import to_plain_text
    from dochan.pdf.reader import PDFReader

    document = PDFReader().read(str(path))
    warnings = [e for e in document.errors if "ToUnicode 없는 CID" in e]
    if not warnings and not include_all:
        return None
    reference = pypdfium2.PdfDocument(str(path))
    pages = []
    for i, page in enumerate(reference):
        expected = page.get_textpage().get_text_range()
        actual = (to_plain_text(Document(sections=[document.sections[i]]))
                  if i < len(document.sections) else "")
        pages.append(_score(actual, expected))
    return {"pages": pages, "warnings": len(warnings),
            "errors": len([e for e in document.errors if e.startswith("ERR")]),
            "output_sha256": hashlib.sha256(to_plain_text(document).encode("utf-8")).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--only", type=Path, help="이전 실행 JSON에 기록된 파일만 측정")
    args = parser.parse_args()
    if args.repo:
        sys.path.insert(0, str(args.repo.resolve()))
    names = (json.loads(args.only.read_text())["rows"].keys() if args.only
             else (path.name for path in args.corpus.glob("*.pdf")))
    rows = {}
    for name in sorted(names):
        path = args.corpus / name
        try:
            row = probe(path, include_all=bool(args.only))
            if row is not None:
                rows[name] = row
        except Exception as exc:
            rows[name] = {"exception_type": type(exc).__name__}
    args.output.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2))
    print("CID 경고 문서:", len(rows), "쪽:", sum(len(r.get("pages", [])) for r in rows.values()))


if __name__ == "__main__":
    main()
