"""PPT 리뷰 표본을 공개 기대값과 원시 바이트 근거로 반복 검사한다.

코퍼스는 읽기 전용이다. 사용 예:
/usr/bin/python3 -m scripts.probe_ppt_review --poi /path/to/slideshow
    --lo /path/to/sd/qa/unit/data/ppt --output .codex-work/ppt-review.json
"""
import argparse
import json
import re
from pathlib import Path

from dochan import cfb

from dochan import Dochan
from dochan.office_binary.officeart import parse_properties, parse_records, walk_records


def verify(poi, lo):
    checks = []
    cache = {}

    def load(root, name):
        path = root / name
        if path not in cache:
            parsed = Dochan(str(path))
            with cfb.OleFileIO(str(path)) as ole:
                raw = ole.openstream("PowerPoint Document").read()
            cache[path] = (parsed, parsed.doc.find_all("paragraph"), raw)
        return cache[path]

    def record(feature, name, source, expected, actual, evidence=None):
        row = {"feature": feature, "file": name, "source": source,
               "expected": expected, "actual": actual, "passed": expected == actual}
        if evidence is not None:
            row["raw_evidence"] = evidence
        checks.append(row)

    for root, name, values, source in [
        (poi, "WithComments.ppt", ["This is a test comment", "It is on the first, only slide"],
         "extractor/TestExtractor.java:254-263; CString instance 1 in raw stream"),
        (poi, "45543.ppt", ["testdoc", "test phrase"],
         "extractor/TestExtractor.java:267-274; CString instance 1 in raw stream"),
        (lo, "pass/hang-22.ppt", ["This is the second comment.Test to  check the number of comments which can be inserted."],
         "raw CString instance 1 at stream offset 6110"),
    ]:
        _parsed, paragraphs, raw = load(root, name)
        comments = [p for p in paragraphs if (p.provenance.path or "").endswith("#comments")]
        for value in values:
            offset = raw.find(value.encode("utf-16le"))
            record("comment:" + value, name, source, True,
                   any(value in p.text and p.text.startswith("[comment: ") for p in comments),
                   {"utf16_payload_offset": offset, "source_contains_expected": offset >= 0})
        if name == "WithComments.ppt":
            record("comment_author", name, "raw CString author; PPTXReader._read_slide_comments output contract",
                   True, any(p.text.startswith("[comment: Administrator: ") for p in comments))
        if name == "45543.ppt":
            record("comment_author", name, "raw CString author; PPTXReader._read_slide_comments output contract",
                   True, any(p.text.startswith("[comment: XPVMWARE01: ") for p in comments))

    for root, name, expected in [
        (poi, "41246-2.ppt", ["Fin"]),
        (poi, "bug60345_Jankovic_final_Retreat_2002.ppt", ["SEA", "SEA", "STAg", "STAg"]),
        (lo, "tdf143315-WordartWithoutBullet.ppt", ["בדיקה"]),
    ]:
        _parsed, paragraphs, raw = load(root, name)
        observed = []
        for atom in walk_records(parse_records(raw)):
            if atom.header.rec_type == 0xF00B:
                prop = parse_properties(atom).get(0xC0)
                if prop and prop.is_complex:
                    observed.append({"officeart_offset": atom.offset,
                                     "text": prop.data.decode("utf-16le", errors="replace").rstrip("\0\r")})
        actual = sorted(p.text.strip() for p in paragraphs if p.text.strip() in expected)
        record("wordart", name, "raw OfficeArt gtextUNICODE property 0x00C0", sorted(expected), actual, observed)

    for name, expected_literal_stars in (("datetime.ppt", 0), ("npe.ppt", 15)):
        _parsed, paragraphs, raw = load(poi, name)
        kinds = {}
        for atom in walk_records(parse_records(raw)):
            if atom.header.rec_type in (4056, 4087, 4088, 4089, 4090, 4117):
                kinds[str(atom.header.rec_type)] = kinds.get(str(atom.header.rec_type), 0) + 1
        source = "MC field records identify placeholder characters; synthetic field tests establish replacement behavior"
        if name == "npe.ppt":
            source += "; slide 14 Example: Star Reduction explicitly instructs replacing data values with *, so its 15 literal table cells must remain"
        record("unresolved_field_marker", name, source,
               [14] * expected_literal_stars,
               [p.provenance.slide for p in paragraphs if p.text.strip() == "*"], kinds)

    name = "bug60345_suba.ppt"
    parsed, paragraphs, _raw = load(poi, name)
    record("leading_markdown_code_indent", name, "raw paragraphs start with alignment whitespace; paragraph output must not create code blocks",
           [], [p.text for p in paragraphs if re.match(r"^(?: {4}|\t)", p.text)])
    name = "54111.ppt"
    _parsed, paragraphs, raw = load(poi, name)
    record("heading_soft_breaks", name, "raw title text begins with vertical tabs before Table sample", ["Table sample"],
           [p.text for p in paragraphs if p.heading_level and "Table sample" in p.text],
           {"title_utf16_offset": raw.find("Table sample".encode("utf-16le"))})
    name = "49541_symbol_map.ppt"
    _parsed, paragraphs, _raw = load(poi, name)
    record("symbol_font", name, "usermodel/TestBugs.java:508-516", True,
           any(p.text.strip() == "≥75 years" for p in paragraphs))
    for name, expected_count in (("with_textbox.ppt", 1), ("60003.ppt", 2)):
        _parsed, paragraphs, _raw = load(poi, name)
        record("wingdings_bullet", name, "raw StyleTextProp bullet character 0xD8 and Wingdings font; source text is retained",
               [expected_count, 0],
               [sum(p.text.startswith("➢ ") for p in paragraphs),
                sum(p.text.startswith("Ø ") for p in paragraphs)])
    name = "42474-2.ppt"
    parsed, paragraphs, raw = load(poi, name)
    record("adjacent_bold_runs", name, "raw text Given X = logb(x); size and baseline changes do not close identical Markdown bold spans",
           True, "**Given X = logb(x) and Y = logb(y):" in parsed.to_markdown(),
           {"source_contains_expected": b"Given X = logb(x)" in raw or "Given X = logb(x)".encode("utf-16le") in raw})
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poi", required=True, type=Path)
    parser.add_argument("--lo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    checks = verify(args.poi, args.lo)
    result = {"summary": {"checks": len(checks), "passed": sum(c["passed"] for c in checks)}, "checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
