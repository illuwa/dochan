"""내부 PDF/HWPX 쌍의 각주를 읽기 전용으로 비교하고 익명 집계만 출력한다."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
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
            actual = [_normalize(note.text) for note in candidate.find_all("footnote")]
            expected = {kind: [_normalize(note.text) for note in answer.find_all(kind)]
                        for kind in ("footnote", "endnote")}
            if any(raw[kind] != len(expected[kind]) for kind in expected):
                result["raw_model_count_mismatches"] += 1
            if not any(raw.values()) and not any(expected.values()):
                result["negative_documents"] += 1
                result["negative_false_positives"] += len(actual)
                continue
            for kind, texts in expected.items():
                if not texts:
                    continue
                stats = result[kind]
                stats["documents"] += 1
                stats["expected"] += len(texts)
                stats["expected_characters"] += sum(map(len, texts))
                # PDF 휴리스틱은 미주도 footnote로 정규화한다. 두 종류가 함께
                # 있는 문서는 종류별 후보 수를 정할 수 없으므로 일치 수만 센다.
                pool = Counter(actual)
                for text in texts:
                    if pool[text]:
                        stats["exact"] += 1
                        pool[text] -= 1
                if sum(bool(items) for items in expected.values()) == 1:
                    stats["actual"] += len(actual)
                    stats["actual_characters"] += sum(map(len, actual))
        except Exception:
            # 경로/내용이 들어 있는 예외 문자열도 외부로 출력하지 않는다.
            result["errors"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
