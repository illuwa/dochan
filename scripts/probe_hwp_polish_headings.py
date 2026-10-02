"""공개 코퍼스의 직접 문단 개요 우선순위와 깊은 개요 짝을 검증한다."""

import argparse
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from dochan.hwpx.parser import (
    HWPXParser, MAX_XML_FILE_SIZE, NS, _heading_level_from_style_name,
    _parse_xml_tolerant,
)


XML_NS = dict(NS, hh="http://www.hancom.co.kr/hwpml/2011/head")


def _font_heading(size):
    return 1 if size >= 20 else 2 if size >= 16 else 3 if size >= 13 else 0


class _HeadingProbe(HWPXParser):
    def __init__(self):
        super().__init__()
        self.heading_checks = []

    def _heading_level_for(self, paragraph, runs):
        actual = super()._heading_level_for(paragraph, runs)
        direct_id = int(paragraph.get("paraPrIDRef", "-1"))
        style_id = int(paragraph.get("styleIDRef", "-1"))
        direct = self._para_prs.get(direct_id)
        style = self._styles.get(style_id)
        if not direct or not style:
            return actual
        named_level = (_heading_level_from_style_name(style["name"])
                       or _heading_level_from_style_name(style["eng_name"]))
        inherited = self._outline_level(style["para_pr_id"])
        if (direct["heading_type"] != "OUTLINE" and inherited
                and not (named_level and named_level <= 3)):
            expected = _font_heading(runs[0].font_size_pt) if runs else 0
            self.heading_checks.append({
                "para_pr_id": direct_id, "style_id": style_id,
                "old_heading": inherited, "expected": expected,
                "actual": actual, "matches": actual == expected,
                "nonempty": bool("".join(run.text for run in runs).strip()),
            })
        return actual


def probe(corpus):
    result = {"scanned_hwpx": 0, "xml_conflict_documents": [],
              "scan_errors": [], "paired_hwpx": 0,
              "deep_outline_large_font_pairs": []}
    for path in sorted(corpus.rglob("*.hwpx")):
        result["scanned_hwpx"] += 1
        pair = corpus / "hwp" / (path.stem + ".hwp")
        paired = pair.is_file()
        result["paired_hwpx"] += int(paired)
        conflicts = []
        deep_sizes = Counter()
        try:
            with ZipFile(path) as package:
                header_info = package.getinfo("Contents/header.xml")
                if header_info.file_size > MAX_XML_FILE_SIZE:
                    raise ValueError("header XML size limit")
                header = _parse_xml_tolerant(package.read(header_info))
                shapes = {p.get("id"): p.find("hh:heading", XML_NS)
                          for p in header.findall(".//hh:paraPr", XML_NS)}
                styles = {s.get("id"): s for s in header.findall(".//hh:style", XML_NS)}
                char_sizes = {c.get("id"): int(c.get("height", "1000")) / 100.0
                              for c in header.findall(".//hh:charPr", XML_NS)}
                for part in package.infolist():
                    if not (part.filename.startswith("Contents/section")
                            and part.filename.endswith(".xml")):
                        continue
                    if part.file_size > MAX_XML_FILE_SIZE:
                        raise ValueError("section XML size limit")
                    section = _parse_xml_tolerant(package.read(part))
                    for index, p in enumerate(section.findall(".//hp:p", XML_NS)):
                        direct = shapes.get(p.get("paraPrIDRef"))
                        if direct is None:
                            continue
                        if (paired and direct.get("type") == "OUTLINE"
                                and 3 <= int(direct.get("level", "0")) <= 5):
                            for run in p.findall("hp:run", XML_NS):
                                if "".join(run.itertext()).strip():
                                    size = char_sizes.get(run.get("charPrIDRef"), 10.0)
                                    if size >= 13:
                                        deep_sizes[str(size)] += 1
                                    break
                        style = styles.get(p.get("styleIDRef"))
                        if style is None:
                            continue
                        inherited = shapes.get(style.get("paraPrIDRef"))
                        if inherited is None:
                            continue
                        named = (_heading_level_from_style_name(style.get("name", ""))
                                 or _heading_level_from_style_name(style.get("engName", "")))
                        if named and named <= 3:
                            continue
                        if (inherited.get("type") == "OUTLINE"
                                and int(inherited.get("level", "0")) < 3
                                and (direct.get("type"), direct.get("level"))
                                != (inherited.get("type"), inherited.get("level"))):
                            conflicts.append({
                                "part": part.filename, "paragraph_index": index,
                                "para_pr_id": p.get("paraPrIDRef"),
                                "style_id": p.get("styleIDRef"),
                                "direct_type": direct.get("type"),
                                "direct_level": direct.get("level"),
                                "style_para_pr_id": style.get("paraPrIDRef"),
                                "style_level": inherited.get("level"),
                            })
            if conflicts:
                parser = _HeadingProbe()
                document = parser.parse(str(path))
                checks = parser.heading_checks
                result["xml_conflict_documents"].append({
                    "file": str(path.relative_to(corpus)), "xml_conflicts": conflicts,
                    "parsed_heading_checks": checks,
                    "matched": sum(check["matches"] for check in checks),
                    "changed_nonempty": sum(check["nonempty"]
                                            and check["old_heading"] != check["actual"]
                                            for check in checks),
                    "parser_warning_count": len(document.errors),
                })
            if deep_sizes:
                result["deep_outline_large_font_pairs"].append({
                    "file": str(path.relative_to(corpus)), "font_size_counts": dict(deep_sizes),
                })
        except Exception as exc:
            result["scan_errors"].append({"file": str(path.relative_to(corpus)),
                                          "error_type": type(exc).__name__})
    records = result["xml_conflict_documents"]
    result["summary"] = {
        "conflict_documents": len(records),
        "xml_conflicts": sum(len(row["xml_conflicts"]) for row in records),
        "parsed_heading_checks": sum(len(row["parsed_heading_checks"]) for row in records),
        "matched": sum(row["matched"] for row in records),
        "changed_nonempty": sum(row["changed_nonempty"] for row in records),
    }
    result["multi_002"] = {
        "hwp_present": (corpus / "hwp/hwp-multi-002.hwp").is_file(),
        "same_name_hwpx": [str(p.relative_to(corpus))
                           for p in corpus.rglob("hwp-multi-002.hwpx")],
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
