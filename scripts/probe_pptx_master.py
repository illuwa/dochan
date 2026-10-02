"""공개 PPTX XML 상속과 리더 회귀를 독립적으로 측정한다.

실행: python -m scripts.probe_pptx_master CORPUS... --output DIR
--snapshot NAME 으로 리더 스냅샷을 남기고 --baseline FILE 로 비교한다.
XML 해석은 표준 라이브러리만 사용하며 PPTX 리더의 상속 함수를 호출하지 않는다.
XML 대조는 구현 해석과의 일치이며, 표시 정답의 주 근거는 PowerPoint 실측이다.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import posixpath
import re
from decimal import Decimal
import subprocess
import sys
import xml.etree.ElementTree as ET  # nosemgrep: use-defused-xml (독립 정답지용, DTD·엔티티는 파싱 전에 거부)
import zipfile


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
FIELDS = ("b", "i", "u", "sz", "baseline")
MODEL_FIELDS = ("bold", "italic", "underline", "font_size_pt", "superscript", "subscript")
PROPERTY_XML = {"bold": "b", "italic": "i", "underline": "u", "font_size_pt": "sz",
                "superscript": "baseline", "subscript": "baseline"}
LIMIT = 32 * 1024 * 1024


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_xml(archive, name):
    if not name or name not in archive.namelist():
        return None
    if archive.getinfo(name).file_size > LIMIT:
        raise ValueError("XML part exceeds probe limit")
    raw = archive.read(name)
    markers = [token.encode(codec) for token in ("<!DOCTYPE", "<!ENTITY")
               for codec in ("ascii", "utf-16-le", "utf-16-be")]
    if any(marker in raw for marker in markers):
        raise ValueError("DTD not accepted by independent probe")
    return ET.fromstring(raw)


def relations(archive, part):
    folder, name = posixpath.split(part)
    root = read_xml(archive, folder + "/_rels/" + name + ".rels")
    if root is None:
        return []
    return [(r.get("Id"), r.get("Type", "").rsplit("/", 1)[-1],
             posixpath.normpath(posixpath.join(folder, r.get("Target", "")))
             if not r.get("Target", "").startswith("/") else r.get("Target").lstrip("/"))
            for r in root if r.get("TargetMode") != "External"]


def related(archive, part, kind):
    return next((target for _, typ, target in relations(archive, part) if typ == kind), "")


def placeholder(shape):
    return shape.find("p:nvSpPr/p:nvPr/p:ph", NS)


def family(kind):
    if kind in (None, "dt", "ftr", "sldNum"):
        return kind
    return "title" if kind in ("title", "ctrTitle") else "body"


def ph_index(ph):
    value = ph.get("idx", "0").strip()
    if len(value) > 32 or not re.fullmatch(r"[+-]?[0-9]+", value):
        return None
    result = int(value)
    return result if 0 <= result <= 4294967295 else None


def ph_kind(ph):
    return ph.get("type") or ("title" if ph_index(ph) == 0 else "body")


def match(shape, root, master=False):
    ph = placeholder(shape)
    if ph is None or root is None or ph_index(ph) is None:
        return None
    candidates = [(sp, placeholder(sp)) for sp in root.findall(".//p:sp", NS)]
    candidates = [(sp, p) for sp, p in candidates if p is not None and ph_index(p) is not None]
    kind, idx = ph_kind(ph), ph_index(ph)
    if not master:
        candidates = [(sp, p) for sp, p in candidates if ph_index(p) == idx]
    target = family(kind) if master else kind
    for condition in (lambda p: ph_kind(p) == target,
                      lambda p: family(ph_kind(p)) == family(kind)):
        matching = [(sp, p) for sp, p in candidates if condition(p)]
        if matching:
            if master:
                same_idx = [sp for sp, p in matching if ph_index(p) == idx]
                if same_idx:
                    return same_idx[0]
            return matching[0][0]
    return candidates[0][0] if candidates and not master and "type" not in ph.attrib else None


def level(paragraph):
    ppr = paragraph.find("a:pPr", NS)
    try:
        value = int(ppr.get("lvl", "0")) if ppr is not None else 0
        return value if 0 <= value <= 8 else 0
    except ValueError:
        return 0


def attrs(node):
    return {key: node.get(key) for key in FIELDS if node is not None and node.get(key) is not None}


def normalized(values):
    result = {"bold": values.get("b") in ("1", "true"),
              "italic": values.get("i") in ("1", "true"),
              "underline": bool(values.get("u") and values["u"] != "none"),
              "font_size_pt": 10.0, "superscript": False, "subscript": False}
    try:
        size = int(values.get("sz", "1000"))
        if 100 <= size <= 400000:
            result["font_size_pt"] = size / 100.0
    except ValueError:
        pass
    try:
        value = values.get("baseline", "0")
        baseline = Decimal(value[:-1]) * 1000 if value.endswith("%") else Decimal(value)
        result["superscript"] = baseline > 0
        result["subscript"] = baseline < 0
    except ArithmeticError:
        pass
    return result


def raw_probe(path):
    records, inventory = [], defaultdict(set)
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(".xml"):
                continue
            if not (name.startswith("ppt/slideMasters/") or name.startswith("ppt/slideLayouts/")
                    or name.startswith("ppt/slides/") or name == "ppt/presentation.xml"):
                continue
            root = read_xml(archive, name)
            stage = ("master" if "/slideMasters/" in name else "layout" if "/slideLayouts/" in name
                     else "default" if name == "ppt/presentation.xml" else "slide")
            for node in root.findall(".//a:defRPr", NS):
                inventory[stage].update(attrs(node))
            for node in root.findall(".//a:lstStyle//a:defRPr", NS):
                inventory["lstStyle"].update(attrs(node))
        presentation = read_xml(archive, "ppt/presentation.xml")
        if presentation is None:
            return records, inventory
        rels = {key: target for key, _, target in relations(archive, "ppt/presentation.xml")}
        for slide_no, slide in enumerate(presentation.findall("p:sldIdLst/p:sldId", NS), 1):
            slide_path = rels.get(slide.get("{%s}id" % NS["r"]), "")
            slide_root = read_xml(archive, slide_path)
            layout_path = related(archive, slide_path, "slideLayout")
            layout_root = read_xml(archive, layout_path)
            master_path = related(archive, layout_path, "slideMaster")
            master_root = read_xml(archive, master_path)
            sources = [(slide_path, slide_root, False), (layout_path, layout_root, True)]
            for part, root, is_layout in sources:
                if root is None:
                    continue
                for shape_no, shape in enumerate(root.findall(".//p:sp", NS)):
                    ph = placeholder(shape)
                    if is_layout and ph is not None:
                        continue
                    layout_shape = None if is_layout else match(shape, layout_root)
                    master_shape = match(layout_shape if layout_shape is not None else shape,
                                         master_root, master=True)
                    effective_ph = placeholder(layout_shape) if layout_shape is not None else ph
                    kind = (ph.get("type") if ph is not None else None)
                    if not kind and effective_ph is not None:
                        kind = ph_kind(effective_ph)
                    style_name = family(kind)
                    tx_style = (master_root.find("p:txStyles/p:%sStyle" % style_name, NS)
                                if master_root is not None and style_name in ("title", "body") else None)
                    for para_no, paragraph in enumerate(shape.findall("p:txBody/a:p", NS)):
                        lvl = level(paragraph)
                        own_stage = "layout" if is_layout else "slide"
                        layers = [(own_stage, paragraph.find("a:pPr/a:defRPr", NS))]
                        styles = [(own_stage, shape.find("p:txBody/a:lstStyle", NS)),
                                  ("layout", layout_shape.find("p:txBody/a:lstStyle", NS) if layout_shape is not None else None),
                                  ("master", master_shape.find("p:txBody/a:lstStyle", NS) if master_shape is not None else None),
                                  ("txStyles", tx_style),
                                  ("default", presentation.find("p:defaultTextStyle", NS))]
                        # All level-specific values outrank all defPPr values.
                        for tag in ("a:lvl%dpPr/a:defRPr" % (lvl + 1), "a:defPPr/a:defRPr"):
                            layers.extend((stage, style.find(tag, NS)) for stage, style in styles if style is not None)
                        for run_no, run in enumerate(list(paragraph)):
                            if run.tag not in ("{%s}r" % NS["a"], "{%s}fld" % NS["a"], "{%s}br" % NS["a"]):
                                continue
                            text = "\n" if run.tag.endswith("}br") else "".join(t.text or "" for t in run.findall("a:t", NS))
                            if not text:
                                continue
                            direct = attrs(run.find("a:rPr", NS))
                            chosen, evidence, evidence_nodes = {}, {}, {}
                            for stage, node in [("layout" if is_layout else "slide", run.find("a:rPr", NS))] + layers:
                                for key, value in attrs(node).items():
                                    if key not in chosen:
                                        chosen[key], evidence[key] = value, stage
                                        evidence_nodes[key] = {"node": node.tag.rsplit("}", 1)[-1],
                                                               "part": {"slide": slide_path, "layout": layout_path,
                                                                        "master": master_path, "txStyles": master_path,
                                                                        "default": "ppt/presentation.xml"}[stage]}
                            old = normalized({key: value for key, value in direct.items() if key in ("b", "i", "u")})
                            if run.tag.endswith(("}fld", "}br")):
                                old = normalized({})
                            expected = normalized(chosen)
                            changes = {key: {"before": old[key], "after": expected[key]} for key in MODEL_FIELDS if old[key] != expected[key]}
                            records.append({"file": str(path), "slide": slide_no, "part": part,
                                            "shape": shape_no, "paragraph": para_no, "run": run_no,
                                            "text": text, "level": lvl, "expected": expected,
                                            "xml_values": chosen, "evidence": evidence,
                                            "evidence_nodes": evidence_nodes, "changes": changes})
    return records, inventory


def snapshot(paths):
    from dochan.ooxml.pptx import PPTXReader
    from dochan.output.json_out import to_json
    from dochan.output.markdown import to_markdown
    from dochan.output.plain_text import to_plain_text
    results = {}
    for path in paths:
        try:
            doc = PPTXReader().read(str(path))
            runs = []
            for paragraph in doc.find_all("paragraph"):
                for run in paragraph.runs:
                    row = {key: getattr(run, key) for key in MODEL_FIELDS}
                    row.update(text=run.text, strikeout=run.strikeout,
                               path=getattr(run.provenance, "path", ""),
                               slide=getattr(run.provenance, "slide", None), heading=paragraph.heading_level)
                    runs.append(row)
            markdown = to_markdown(doc)
            results[str(path)] = {"markdown": digest(markdown),
                                  "bold_heading_lines": sum(line.startswith("#") and "**" in line for line in markdown.splitlines()),
                                  "adjacent_bold_markers": markdown.count("****"), "json": digest(to_json(doc)),
                                  "text": digest(to_plain_text(doc)), "runs": runs, "errors": doc.errors,
                                  "newline_heading_bold": sum(r["heading"] > 0 and "\n" in r["text"] and r["bold"] for r in runs),
                                  "multiline_heading_bold_runs": sum(r["heading"] > 0 and "\n" in r["text"].strip() and r["bold"] for r in runs),
                                  "multiline_heading_bold_lines": sum(len(r["text"].strip().splitlines()) for r in runs
                                                                     if r["heading"] > 0 and "\n" in r["text"].strip() and r["bold"])}
        except Exception as exc:
            results[str(path)] = {"exception": repr(exc)}
    return {"files": results}


def compare(before, after):
    rows = []
    for path, new in after["files"].items():
        old = before["files"][path]
        changes = Counter()
        old_runs, new_runs = old.get("runs", []), new.get("runs", [])
        changed_runs = 0
        for left, right in zip(old_runs, new_runs):
            fields = [k for k in MODEL_FIELDS if left[k] != right[k]]
            if fields:
                changed_runs += 1
                changes.update(fields)
        rows.append({"file": path, "markdown_changed": old.get("markdown") != new.get("markdown"),
                     "json_changed": old.get("json") != new.get("json"),
                     "text_changed": old.get("text") != new.get("text"),
                     "run_count_delta": len(new_runs) - len(old_runs),
                     "run_text_changes": sum(left["text"] != right["text"] for left, right in zip(old_runs, new_runs)), "changed_runs": changed_runs,
                     "properties": dict(changes), "newline_heading_bold": new.get("newline_heading_bold", 0),
                     "multiline_heading_bold_runs": new.get("multiline_heading_bold_runs", 0),
                     "multiline_heading_bold_lines": new.get("multiline_heading_bold_lines", 0),
                     "errors_changed": old.get("errors") != new.get("errors")})
    return rows


def validate(records, current):
    buckets = defaultdict(list)
    for path, document in current["files"].items():
        for run in document.get("runs", []):
            buckets[(path, run["slide"], run["path"], run["text"])].append(run)
    raw_signatures = defaultdict(set)
    for record in records:
        key = (record["file"], record["slide"], record["part"], record["text"])
        raw_signatures[key].add(tuple(record["expected"][k] for k in MODEL_FIELDS))
    ambiguous_keys = {key for key, values in raw_signatures.items() if len(values) > 1}
    ambiguous_keys.update(key for key, values in buckets.items()
                          if len({tuple(r[k] for k in MODEL_FIELDS) for r in values}) > 1)
    results = Counter()
    mismatches, unmatched, ambiguous = [], [], []
    for record in records:
        key = (record["file"], record["slide"], record["part"], record["text"])
        if key in ambiguous_keys:
            results["ambiguous"] += 1
            ambiguous.append(record)
            continue
        candidates = buckets[key]
        actual_key = key
        if not candidates:
            # Hyperlink serialization appends the target after the original text.
            for candidate_key, values in buckets.items():
                suffix = candidate_key[3][len(key[3]) + 2:]
                plausible_link = bool(key[3].strip()) or suffix.startswith(("http:", "https:", "mailto:", "#ppt/", "ftp:"))
                if (values and plausible_link and candidate_key[:3] == key[:3]
                        and candidate_key[3].startswith(key[3] + " <")):
                    candidates = values
                    actual_key = candidate_key
                    break
        if actual_key in ambiguous_keys:
            results["ambiguous"] += 1
            ambiguous.append(record)
            continue
        if not candidates:
            results["unmatched"] += 1
            unmatched.append(record)
            continue
        actual = candidates.pop(0)
        if all(actual[k] == record["expected"][k] for k in MODEL_FIELDS):
            results["matched"] += 1
        else:
            results["mismatched"] += 1
            mismatches.append(dict(record, actual=actual))
    return {"counts": dict(results), "mismatches": mismatches, "unmatched": unmatched,
            "ambiguous": ambiguous, "ambiguous_buckets": len(ambiguous_keys),
            "raw_ambiguous_buckets": sum(len(v) > 1 for v in raw_signatures.values())}


def legacy_pairs(roots, paths, worktree):
    """별도 워크트리의 레거시 리더 출력은 참고값으로만 저장한다."""
    ppt = {p.stem: p for root in roots for p in root.rglob("*.ppt")}
    pairs = {p.stem: {"ppt": str(ppt[p.stem]), "pptx": str(p)}
             for p in paths if p.stem in ppt}
    code = (
        "import json,sys\nfrom dochan.office_binary.ppt import PPTReader\n"
        "result={}\nfor name,path in json.loads(sys.stdin.read()).items():\n"
        " d=PPTReader().read(path)\n"
        " result[name]={'errors':d.errors,'runs':[dict(text=r.text,bold=r.bold,italic=r.italic,"
        "underline=r.underline,font_size_pt=r.font_size_pt,superscript=r.superscript,"
        "subscript=r.subscript) for p in d.find_all('paragraph') for r in p.runs]}\n"
        "print(json.dumps(result,ensure_ascii=False))"
    )
    for phase, directory in (("head_before_inheritance", Path(__file__).resolve().parents[1]),
                             ("legacy_branch_worktree", worktree)):
        # nosemgrep: dangerous-subprocess-use-audit
        result = subprocess.run([sys.executable, "-c", code], cwd=str(directory),
                                input=json.dumps({k: v["ppt"] for k, v in pairs.items()}),
                                capture_output=True, text=True, check=True, timeout=120)
        for name, row in json.loads(result.stdout).items():
            pairs[name][phase] = row
    return pairs


def compare_legacy(pairs, raw_records):
    def unique_styles(rows):
        groups = defaultdict(list)
        for row in rows:
            if row["text"].strip():
                groups[row["text"]].append(row)
        return {text: values[0] for text, values in groups.items()
                if len({tuple(r[k] for k in MODEL_FIELDS) for r in values}) == 1}

    results = []
    for name, pair in pairs.items():
        expected = unique_styles([dict(r["expected"], text=r["text"]) for r in raw_records
                                  if r["file"] == pair["pptx"]])
        before = unique_styles(pair["head_before_inheritance"]["runs"])
        after = unique_styles(pair["legacy_branch_worktree"]["runs"])
        common = sorted(set(expected) & set(before) & set(after))
        row = {"name": name, "common_unambiguous_texts": len(common)}
        for phase, actual in (("before", before), ("after", after)):
            differences = [{"text": text, "properties": {
                key: {"expected": expected[text][key], "actual": actual[text][key]}
                for key in MODEL_FIELDS if expected[text][key] != actual[text][key]}}
                for text in common if any(expected[text][key] != actual[text][key] for key in MODEL_FIELDS)]
            row[phase + "_matched"] = len(common) - len(differences)
            row[phase + "_differences"] = differences
            row[phase + "_different_properties"] = dict(Counter(key for diff in differences for key in diff["properties"]))
        results.append(row)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot", default="current")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--legacy-worktree", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = sorted({path for root in args.roots for path in root.rglob("*") if path.suffix.lower() in {".pptx", ".pptm", ".potx", ".ppsx"}})
    current = snapshot(paths)
    (args.output / (args.snapshot + ".json")).write_text(json.dumps(current, ensure_ascii=False))
    all_records, errors = [], []
    counts, field_counts = Counter(), defaultdict(Counter)
    for path in paths:
        try:
            records, inventory = raw_probe(path)
            all_records.extend(records)
            for stage, fields in inventory.items():
                if fields:
                    counts[stage] += 1
                    field_counts[stage].update(fields)
        except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
            errors.append({"file": str(path), "error": str(exc)})
    changed = [r for r in all_records if r["changes"]]
    with (args.output / "changed-runs.jsonl").open("w") as stream:
        for row in changed:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    validation = validate(all_records, current)
    summary = {"files": len(paths), "decks_with_defaults": dict(counts),
               "decks_per_field": {k: dict(v) for k, v in field_counts.items()},
               "raw_runs": len(all_records), "predicted_changed_runs": len(changed),
               "changed_by_field": dict(Counter(k for r in changed for k in r["changes"])),
               "raw_errors": errors, "validation": validation["counts"]}
    summary["ambiguous_buckets"] = validation["ambiguous_buckets"]
    summary["raw_ambiguous_buckets"] = validation["raw_ambiguous_buckets"]
    summary["direct_changed_runs"] = sum(any(r["evidence_nodes"][PROPERTY_XML[k]]["node"] == "rPr"
                                             for k in r["changes"]) for r in changed)
    summary["inherited_changed_runs"] = sum(any(r["evidence_nodes"][PROPERTY_XML[k]]["node"] == "defRPr"
                                                for k in r["changes"]) for r in changed)
    summary["changed_by_stage"] = dict(Counter(stage for r in changed
                                               for stage in {r["evidence"][PROPERTY_XML[k]] for k in r["changes"]}))
    summary["inherited_changed_by_field"] = dict(Counter(k for r in changed for k in r["changes"]
                                                         if r["evidence_nodes"][PROPERTY_XML[k]]["node"] == "defRPr"))
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (args.output / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2))
    if args.baseline:
        before = json.loads(args.baseline.read_text())
        rows = compare(before, current)
        by_file = defaultdict(list)
        for record in changed:
            by_file[record["file"]].append(record)
        for row in rows:
            raw_changes = by_file[row["file"]]
            row["xml_stages"] = dict(Counter(stage for r in raw_changes
                                               for stage in {r["evidence"][PROPERTY_XML[k]] for k in r["changes"]}))
        (args.output / "regression.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    if args.legacy_worktree:
        pairs = legacy_pairs(args.roots, paths, args.legacy_worktree)
        (args.output / "legacy-pairs.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=2))
        comparisons = compare_legacy(pairs, all_records)
        (args.output / "legacy-comparison.json").write_text(json.dumps(comparisons, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
