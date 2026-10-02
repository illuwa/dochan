"""공개 PPT 코퍼스의 파싱 결과와 모델 기능 개수를 기록한다.

예: /usr/bin/python3 -m scripts.probe_ppt_corpus --corpus /path/to/slideshow
    --output .codex-work/ppt-corpus-after.json
기능 개수는 정답 일치 판정이 아니며 그룹은 공용 출력 모델에 없어 세지 않는다.
"""
import argparse
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

from dochan import Dochan
from dochan.model.document import Paragraph
from dochan.model.image import Image
from scripts.compare_office_pairs import _snapshot, _walk


def probe(path):
    result = {"file": path.name}
    started = time.perf_counter()
    try:
        parsed = Dochan(str(path))
        doc = parsed.doc
        features, text = _snapshot(doc)
        nodes = list(_walk(doc))
        paragraphs = [node for node in nodes if isinstance(node, Paragraph)]
        runs = [run for p in paragraphs for run in p.runs]
        counts = {name: len(values) for name, values in features.items()}
        counts.update({
            "paragraphs": len(paragraphs),
            "bold_runs": sum(bool(r.bold) for r in runs),
            "italic_runs": sum(bool(r.italic) for r in runs),
            "underline_runs": sum(bool(r.underline) for r in runs),
            "linked_runs": sum(bool(r.link) for r in runs),
            "internal_linked_runs": sum(r.link.startswith("#") for r in runs),
            "ocr_images": sum(bool(n.ocr_text) for n in nodes if isinstance(n, Image)),
        })
        result.update({"counts": counts, "errors": list(doc.errors),
                       "characters": len(text),
                       "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                       "texts": {key: features[key] for key in ("speaker_notes", "hyperlinks", "alt_text")}})
    except Exception as exc:
        result["exception"] = "%s: %s" % (type(exc).__name__, exc)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return result


def verify_features(corpus):
    """POI 테스트의 기대값만 재사용하며 파서 구현은 참조하지 않는다."""
    checks = []
    cache = {}

    def load(name):
        if name not in cache:
            cache[name] = Dochan(str(corpus / name)).doc
        return cache[name]

    def record(feature, name, source, expected, actual):
        checks.append({"feature": feature, "file": name, "source": source,
                       "expected": expected, "actual": actual, "passed": actual == expected})

    filename = "with_textbox.ppt"
    paragraphs = load(filename).find_all("paragraph")
    expected = ["Hello, World!!!", "I am just a poor boy", "This is Times New Roman", "Plain Text"]
    # PPTX와 같은 글머리 문자는 문장 내용/서식 기대값에 포함되지 않는다.
    actual = [value for p in paragraphs for value in expected if p.text.strip().endswith(value)]
    record("textbox_content", filename, "extractor/TestExtractor.java:97-105 (presence only; storage order is not the output contract)",
           sorted(expected), sorted(actual))
    record("textbox_position_order", filename,
           "PPTXReader._read_slide_elements sorts by (top, left, ordinal); PPT ClientAnchor top values: Plain 936, Hello 1754, poor boy 2352, Times 3359",
           [expected[3], expected[0], expected[1], expected[2]], actual)
    for text, flags in zip(expected[:3], [(True, True, False), (True, False, False), (True, True, True)]):
        matching = [p for p in paragraphs if p.text.strip().endswith(text)]
        actual = [[r.bold, r.italic, r.underline] for p in matching for r in p.runs if r.text.strip() == text]
        record("format:" + text, filename, "model/TestShapes.java:124-140", [list(flags)], actual)

    filename = "54880_chinese.ppt"
    text = "\n".join(p.text for p in load(filename).find_all("paragraph"))
    for value in ("Single byte", "Mix", "\u8868", "\uff8a\uff9d\uff76\uff78"):
        record("text:" + value, filename, "extractor/TestExtractor.java:380-393", True, value in text)

    for filename, rows, source in [
        ("54111.ppt", [["TH Cell %d" % c for c in range(1, 5)]] +
         [["Row %d, Cell %d" % (r, c) for c in range(1, 5)] for r in range(1, 6)],
         "extractor/TestExtractor.java:417-425"),
        ("54722.ppt", [["this", "Text", "is", "within", "a"], ["table", "1", "2", "3", "4"]],
         "extractor/TestExtractor.java:428-433"),
    ]:
        tables = [[[c.text.strip() for c in row] for row in table.rows] for table in load(filename).find_all("table")]
        record("table_cells", filename, source, True, rows in tables)
        checks[-1]["expected_cells"] = rows
        checks[-1]["actual_tables"] = tables

    for filename, expected, source in [
        ("basic_test_ppt_file.ppt", ["These are the notes for page 1", "These are the notes on page two, again lacking formatting"],
         "extractor/TestExtractor.java:72-76,112-117"),
        ("42474-1.ppt", ["Notes-1", "Notes-2"], "usermodel/TestBugs.java:129-146"),
    ]:
        actual = []
        for p in load(filename).find_all("paragraph"):
            path = getattr(p.provenance, "path", "") or ""
            if path.endswith("#notes") and p.text.strip() in expected:
                actual.append([getattr(p.provenance, "slide", None), p.text.strip()])
        record("notes_slide_attachment", filename, source, [[i + 1, value] for i, value in enumerate(expected)], actual)

    filename = "bug62092.ppt"
    text = "\n".join(p.text for p in load(filename).find_all("paragraph"))
    for value in ["Text box%d" % i for i in range(1, 6)] + ["WordArt1", "WordArt2", "Ungrouped text box"]:
        record("group_text:" + value, filename, "extractor/TestExtractor.java:450-469", 1, text.count(value))

    filename = "WithLinks.ppt"
    links = []
    for p in load(filename).find_all("paragraph"):
        path = getattr(p.provenance, "path", "") or ""
        if not path.endswith("#notes"):
            links.extend((getattr(p.provenance, "slide", None), r.text.strip(), r.link) for r in p.runs if r.link)
            # PPTX 리더와 legacy 구조화 출력은 링크를 display <target>으로 쓴다.
            for match in re.finditer(r"(.+?) <([^<>]+)>", p.text):
                links.append((getattr(p.provenance, "slide", None), match.group(1).strip(), match.group(2)))
    for value in [(1, "http://jakarta.apache.org/poi/", "http://jakarta.apache.org/poi/"),
                  (1, "http://slashdot.org/", "http://slashdot.org/"),
                  (2, "Jakarta HSSF", "http://jakarta.apache.org/poi/hssf/")]:
        record("hyperlink:" + value[1], filename, "model/TestHyperlink.java:50-92", True, value in links)
        checks[-1]["expected_link"] = list(value)
        checks[-1]["actual_links"] = links

    filename = "pictures.ppt"
    images = load(filename).find_all("image")
    record("image_placements", filename, "usermodel/TestPictures.java:179-227", 5, len(images))
    for slide, name in [(1, "clock.jpg"), (2, "tomcat.png"), (5, "wrench.emf")]:
        expected_bytes = (corpus / name).read_bytes()
        candidates = [im for im in images if getattr(im.provenance, "slide", None) == slide]
        record("image_bytes:" + name, filename, "usermodel/TestPictures.java:185-230", True,
               any(im.image_data == expected_bytes for im in candidates))

    filename = "bug60993.ppt"
    merged = [(ri, ci, cell.row_span, cell.col_span)
              for table in load(filename).find_all("table")
              for ri, row in enumerate(table.rows) for ci, cell in enumerate(row)
              if cell.row_span > 1 or cell.col_span > 1]
    record("merged_cells", filename,
           "bug60993.pptx output; PPT PPDrawing offset 35134, spid 2058/2063 child anchors",
           [(2, 1, 1, 2), (4, 1, 2, 1)], merged)

    filename = "customGeo.ppt"
    alts = [im.alt_text for im in load(filename).find_all("image")]
    for value in ["ODE_195bktxt.jpg", "http://www.ode.state.oh.us/gd/templates/images/ODE/ohio_logo.gif"]:
        record("alt_text:" + value, filename,
               "customGeo.pptx cNvPr descr; PPT OfficeArt property 0x381 at stream offsets 151022/587052",
               True, value in alts)

    filename = "WithMaster.ppt"
    text = "\n".join(p.text for p in load(filename).find_all("paragraph"))
    # POI는 일반 마스터 문구의 존재만 단언한다. footer만 정확히 한 번이다.
    value = "This text comes from the Master Slide"
    record("master_text:" + value, filename, "extractor/TestExtractor.java:318-326", True, value in text)
    for value, count in [("This is the Master Title", 0), ("Footer from the master slide", 1)]:
        record("master_text:" + value, filename, "extractor/TestExtractor.java:318-338", count, text.count(value))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-features", action="store_true", help="POI 공개 표본의 기대값도 검증한다")
    parser.add_argument("--recursive", action="store_true", help="하위 폴더의 공개 손상 표본도 검사한다")
    args = parser.parse_args(argv)
    if not args.corpus.is_dir():
        parser.error("--corpus must be an existing directory")
    candidates = args.corpus.rglob("*") if args.recursive else args.corpus.iterdir()
    paths = sorted(p for p in candidates if p.is_file() and p.suffix.lower() == ".ppt")
    rows = []
    for path in paths:
        row = probe(path)
        row["file"] = str(path.relative_to(args.corpus))
        rows.append(row)
    totals = Counter()
    for row in rows:
        totals.update(row.get("counts", {}))
    summary = {"files": len(rows), "exceptions": sum("exception" in row for row in rows),
               "documents_with_errors": sum(any(e.startswith("ERR") for e in row.get("errors", [])) for row in rows),
               "documents_with_warnings": sum(any(e.startswith("WARN") for e in row.get("errors", [])) for row in rows),
               "totals": dict(totals),
               "groups": None,
               "max_elapsed_seconds": max((r["elapsed_seconds"] for r in rows), default=0),
               "limitations": "그룹 자체는 공용 모델에 없으므로 그룹 개수는 미측정이다. OCR은 실행하지 않고 기존 결과만 센다. 기능 개수는 정답 일치율이 아니다."}
    output = {"summary": summary, "files": rows}
    if args.verify_features:
        output["feature_checks"] = verify_features(args.corpus)
        summary["feature_checks"] = len(output["feature_checks"])
        summary["feature_checks_passed"] = sum(c["passed"] for c in output["feature_checks"])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
