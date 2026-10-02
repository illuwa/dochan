"""내부 PDF/HWPX 주석을 익명 집계하거나 공개 PDF 미주 양성을 독립 탐색한다."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import unicodedata
import zipfile

from dochan import Dochan
from dochan.pdf.reader import PDFReader


def _normalize(text):
    # PDF 줄 조립과 HWPX의 공백 분절 차이를 빼고 정의 글자열을 비교한다.
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def _raw_counts(path):
    counts = Counter()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if re.fullmatch(r"Contents/section\d+\.xml", name):
                xml = archive.read(name)
                counts["footnote"] += len(re.findall(rb"<(?:\w+:)?footNote\b", xml))
                counts["endnote"] += len(re.findall(rb"<(?:\w+:)?endNote\b", xml))
    return counts


def probe(corpus):
    result = {"pairs": 0, "errors": 0, "negative_documents": 0,
              "negative_false_positives": 0, "raw_model_count_mismatches": 0,
              "footnote": {"documents": 0, "expected": 0, "actual": 0,
                           "exact": 0, "expected_characters": 0, "actual_characters": 0},
              "endnote": {"documents": 0, "expected": 0, "actual": 0,
                          "exact": 0, "expected_characters": 0, "actual_characters": 0}}
    for path in sorted(Path(corpus).glob("*.pdf")):
        answer_path = path.with_suffix(".hwpx")
        if not answer_path.is_file():
            continue
        result["pairs"] += 1
        try:
            raw = _raw_counts(answer_path)
            answer = Dochan(str(answer_path)).doc
            candidate = PDFReader().read(str(path))
            actual = {kind: [_normalize(note.text) for note in candidate.find_all(kind)]
                      for kind in ("footnote", "endnote")}
            expected = {kind: [_normalize(note.text) for note in answer.find_all(kind)]
                        for kind in ("footnote", "endnote")}
            if any(raw[kind] != len(expected[kind]) for kind in expected):
                result["raw_model_count_mismatches"] += 1
            if not any(raw.values()) and not any(expected.values()):
                result["negative_documents"] += 1
                result["negative_false_positives"] += sum(map(len, actual.values()))
                continue
            for kind, texts in expected.items():
                if not texts:
                    continue
                stats = result[kind]
                stats["documents"] += 1
                stats["expected"] += len(texts)
                stats["expected_characters"] += sum(map(len, texts))
                # 정의 내용뿐 아니라 공통 모델의 각주/미주 유형도 일치해야 한다.
                pool = Counter(actual[kind])
                for text in texts:
                    if pool[text]:
                        stats["exact"] += 1
                        pool[text] -= 1
                stats["actual"] += len(actual[kind])
                stats["actual_characters"] += sum(map(len, actual[kind]))
        except Exception:
            # 경로/내용이 들어 있는 예외 문자열도 외부로 출력하지 않는다.
            result["errors"] += 1
    return result


def probe_public(corpus):
    """Poppler는 검증에만 쓰며 파서 런타임에는 필요하지 않다."""
    result = {"documents": 0, "conversion_errors": 0, "candidates": []}
    heading = re.compile(r"^\s*(?:end\s*notes|notes|미\s*주)\s*$", re.I)
    for path in sorted(Path(corpus).glob("*.pdf")):
        result["documents"] += 1
        try:
            converted = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                       capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            result["conversion_errors"] += 1
            continue
        if converted.returncode:
            result["conversion_errors"] += 1
        pages = converted.stdout.decode("utf-8", "replace").split("\f")
        matches = [index for index, page in enumerate(pages, 1)
                   if any(heading.fullmatch(line) for line in page.splitlines())]
        if matches:
            doc = PDFReader().read(str(path))
            result["candidates"].append({"file": path.name, "heading_pages": matches,
                                         "actual_endnotes": len(doc.find_all("endnote")),
                                         "actual_footnotes": len(doc.find_all("footnote"))})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--public", action="store_true",
                        help="공개 코퍼스에서 pdftotext로 미주 제목을 독립 검색한다")
    args = parser.parse_args()
    result = probe_public(args.corpus) if args.public else probe(args.corpus)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
