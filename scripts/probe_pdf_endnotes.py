"""공개 교정 PDF의 미주를 Poppler 원시 글자 위치와 독립 대조한다.

freeculture.pdf의 검증 구역은 PDF 313–336쪽이며, 원시 지면에서 확인한
본문 열은 x=90–390pt, y=90–570pt다. 이 수치는 런타임 검출에 쓰지 않는다.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from unittest.mock import patch

from lxml import etree

from dochan.pdf.reader import PDFReader
from dochan.pdf.notes import detect_endnotes

NS = {"x": "http://www.w3.org/1999/xhtml"}


def normalize(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


def key(text):
    return normalize(text).casefold()


def probe(corpus):
    path = Path(corpus) / "freeculture.pdf"
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        ["pdftotext", "-bbox-layout", str(path), "-"],
        capture_output=True, check=True, timeout=60)
    root = etree.fromstring(result.stdout, etree.XMLParser(
        resolve_entities=False, load_dtd=False, no_network=True))
    pages = root.findall(".//x:page", NS)
    raw_lines = []
    for page_number, page in enumerate(pages, 1):
        for line in page.findall(".//x:line", NS):
            words = line.findall("x:word", NS)
            text = " ".join(w.text or "" for w in words)
            left, top, right, bottom = [float(line.get(k)) for k in ("xMin", "yMin", "xMax", "yMax")]
            if 85 <= left < 400 and 80 < top < 575:
                raw_lines.append((page_number, top, left, bottom - top, text, words))
    raw_lines.sort(key=lambda line: (line[0], line[1], line[2]))
    joined = []
    for line in raw_lines:
        if (joined and joined[-1][0] == line[0]
                and abs(joined[-1][1] - line[1]) < .01
                and abs(joined[-1][3] - line[3]) < .1):
            previous = joined.pop()
            joined.append(previous[:4] + (previous[4] + " " + line[4], previous[5] + line[5]))
        else:
            joined.append(line)
    raw_lines = joined
    chapter = None
    definitions = []
    chapters = []
    for page, top, left, height, text, words in raw_lines:
        if not 313 <= page <= 336:
            continue
        if text.isupper() and text != "NOTES":
            chapter = key(text)
            chapters.append(chapter)
        elif chapter:
            match = re.match(r"^(\d{1,3})\.\s+(.*)", text)
            if match:
                definitions.append({"chapter": chapter, "label": match.group(1),
                                    "page": page, "text": match.group(2)})
            else:
                definitions[-1]["text"] += "\n" + text
    references = []
    reference_bounds = {}
    chapter = None
    for page, top, left, height, text, words in raw_lines:
        if page >= 313:
            break
        if key(text) in chapters and height > 13:
            chapter = key(text)
        if chapter:
            for word in words:
                label = word.text or ""
                word_height = float(word.get("yMax")) - float(word.get("yMin"))
                # 수퍼스크립트 글리프는 실제 bbox 높이가 7.02 또는 7.20pt다.
                if re.fullmatch(r"\d{1,2}", label) and word_height < 8:
                    reference = (chapter, label, page)
                    references.append(reference)
                    reference_bounds[reference] = (float(word.get("xMin")), float(word.get("xMax")))
    native_bounds = {}

    def capture(drafts, dropped, first_number, warnings):
        for draft in drafts:
            markers = dict(draft.note_markers)
            for group in draft.groups:
                for line in group:
                    for order, segment in zip(line.fragment_orders, line.segments):
                        if order in markers:
                            native_bounds[(draft.page_number, markers[order])] = (segment.x0, segment.x1)
        return detect_endnotes(drafts, dropped, first_number, warnings)

    with patch("dochan.pdf.reader.detect_endnotes", capture):
        doc = PDFReader().read(str(path))
    actual = list(doc.find_all("endnote"))
    expected_by_number = {i + 1: definition for i, definition in enumerate(definitions)}
    actual_refs = []
    for section in doc.sections:
        for element in section.elements:
            for run in getattr(element, "runs", []):
                if run.note_reference_type == "endnote":
                    definition = expected_by_number.get(run.note_reference_number)
                    if definition:
                        actual_refs.append((definition["chapter"], run.text.strip(),
                                            run.provenance.page))
    exact = sum(normalize(note.text) == normalize(expected["text"])
                for note, expected in zip(actual, definitions))
    location_exact = sum(note.paragraphs[0].provenance.page == expected["page"]
                         for note, expected in zip(actual, definitions))
    ref_expected, ref_actual = Counter(references), Counter(actual_refs)
    exact_bounds = 0
    exact_starts = 0
    for reference in actual_refs:
        expected_bounds = reference_bounds.get(reference)
        actual_bounds = native_bounds.get((reference[2], reference[1]))
        if (expected_bounds is not None and actual_bounds is not None
                and abs(expected_bounds[0] - actual_bounds[0]) <= .01):
            exact_starts += 1
        if (expected_bounds is not None and actual_bounds is not None
                and all(abs(a - b) <= .01 for a, b in zip(expected_bounds, actual_bounds))):
            exact_bounds += 1
    retained_headings = Counter(key(line) for section in doc.sections
                                for element in section.elements
                                if getattr(element, "provenance", None)
                                and 313 <= (element.provenance.page or 0) <= 336
                                for line in getattr(element, "text", "").splitlines()
                                if key(line) in chapters)
    return {"sample": path.name, "chapters": len(chapters),
            "retained_chapter_headings": sum((Counter(chapters) & retained_headings).values()),
            "expected_definitions": len(definitions), "actual_definitions": len(actual),
            "exact_definition_texts": exact, "exact_definition_pages": location_exact,
            "expected_references": len(references), "actual_references": len(actual_refs),
            "exact_reference_chapter_label_pages": sum((ref_expected & ref_actual).values()),
            "exact_reference_start_x": exact_starts,
            "exact_reference_horizontal_bounds": exact_bounds,
            "reference_false_positives": sum((ref_actual - ref_expected).values()),
            "reference_misses": sum((ref_expected - ref_actual).values()),
            "definition_mismatches": [{"number": i + 1, "chapter": e["chapter"],
                                       "page": e["page"], "expected": e["text"], "actual": n.text}
                                      for i, (n, e) in enumerate(zip(actual, definitions))
                                      if normalize(n.text) != normalize(e["text"])]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus")
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
