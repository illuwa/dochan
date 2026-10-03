"""공개 PPTX 코퍼스의 셀 문단, OMML, 미디어 관계를 읽기 전용 검증한다."""
import argparse
import json
import posixpath
import zipfile
from collections import Counter
from pathlib import Path

from dochan.utils import safe_xml as etree

from dochan.ooxml.pptx import PPTXReader
from dochan.model.equation import Equation
from dochan.model.table import Table

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
      "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
A14 = "http://schemas.microsoft.com/office/drawing/2010/main"


def selected_children(container):
    """실물 수식 선택지는 OMML 존재로 식별하고 대체 그림을 중복 세지 않는다."""
    for node in container:
        if node.tag == "{%s}AlternateContent" % MC:
            choices = node.findall("{%s}Choice" % MC)
            branch = next((c for c in choices if c.findall(".//m:oMath", NS)), None)
            if branch is None:
                branch = node.find("{%s}Fallback" % MC)
            if branch is not None:
                yield from selected_children(branch)
        else:
            yield node


def raw_math_scripts(container):
    scripts = []
    for node in selected_children(container):
        if node.tag in {"{%s}m" % A14, "{%s}oMath" % NS["m"], "{%s}oMathPara" % NS["m"]}:
            scripts.append("".join(etree.itertext(node)))
        else:
            scripts.extend(raw_math_scripts(node))
    return scripts


def model_equations(blocks):
    for block in blocks:
        if isinstance(block, Equation):
            yield block
        elif isinstance(block, Table):
            for row in block.rows:
                for cell in row:
                    yield from model_equations(cell.paragraphs)


def model_cell_blocks(cell):
    return [("equation", block.script) if isinstance(block, Equation)
            else ("paragraph", block.text) for block in cell.paragraphs]


def cell_texts(tc, relationships=None):
    texts = []
    counts = {}
    for p in tc.findall("a:txBody/a:p", NS):
        pieces = []
        blocks = []
        for node in selected_children(p):
            if node.tag == "{%s}br" % NS["a"]:
                pieces.append("\n")
            elif node.tag in {"{%s}r" % NS["a"], "{%s}fld" % NS["a"]}:
                text = "".join(t.text or "" for t in node.findall("a:t", NS))
                link = node.find("a:rPr/a:hlinkClick", NS)
                if link is not None:
                    target = (relationships or {}).get(link.get("{%s}id" % NS["r"]), "")
                    if target:
                        text += " <" + target + ">"
                pieces.append(text)
            elif node.tag in {"{%s}m" % A14, "{%s}oMath" % NS["m"], "{%s}oMathPara" % NS["m"]}:
                if "".join(pieces).strip():
                    blocks.append(("paragraph", "".join(pieces)))
                pieces = []
                blocks.append(("equation", "".join(etree.itertext(node))))
        if "".join(pieces).strip():
            blocks.append(("paragraph", "".join(pieces)))
        props = p.find("a:pPr", NS)
        prefix = ""
        if props is not None and blocks:
            bullet = props.find("a:buChar", NS)
            numbering = props.find("a:buAutoNum", NS)
            if bullet is not None:
                prefix = bullet.get("char", "") or "•"
            elif numbering is not None:
                kind = numbering.get("type", "arabicPeriod")
                key = (props.get("lvl", "0"), kind)
                count = int(numbering.get("startAt", str(counts.get(key, 1))))
                counts[key] = count + 1
                if kind == "arabicPeriod":
                    prefix = str(count) + "."
                elif kind == "arabicParenR":
                    prefix = str(count) + ")"
                else:
                    # 미지원 규칙도 분모에서 빼지 않고 명시적인 불일치로 남긴다.
                    prefix = "[unsupported probe numbering: " + kind + "]"
        if prefix and blocks:
            if blocks[0][0] == "paragraph":
                blocks[0] = ("paragraph", prefix + " " + blocks[0][1])
            else:
                blocks.insert(0, ("paragraph", prefix))
        texts.extend(blocks)
    return texts


def probe(corpus, recursive=False):
    rows = []
    math_samples = []
    files = 0
    caption_tags = 0
    paths = Path(corpus).rglob("*.pptx") if recursive else Path(corpus).glob("*.pptx")
    for path in sorted(paths):
        try:
            with zipfile.ZipFile(path) as archive:
                slides = [n for n in archive.namelist()
                          if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
                roots = [(n, etree.fromstring(archive.read(n))) for n in slides]
                files += 1
                caption_tags += sum(1 for _, root in roots for n in root.iter()
                                    if isinstance(n.tag, str) and etree.QName(n).localname.lower() == "caption")
                maths = [(n, len(root.findall(".//m:oMath", NS))) for n, root in roots
                         if root.findall(".//m:oMath", NS)]
                if maths:
                    doc = PPTXReader().read(str(path))
                    expected_scripts = [script for _, root in roots for script in raw_math_scripts(root)]
                    equations = [e for s in doc.sections for e in model_equations(s.elements)]
                    actual_scripts = [e.script for e in equations]
                    math_samples.append({"file": path.name, "parts": maths,
                                         "expected_scripts": expected_scripts,
                                         "actual_scripts": actual_scripts,
                                         "latex": [e.latex for e in equations],
                                         "matched": Counter(expected_scripts) == Counter(actual_scripts)
                                         and all(e.latex.strip() for e in equations),
                                         "errors": doc.errors})
                tables = [(n, table) for n, root in roots for table in root.findall(".//a:tbl", NS)]
                if tables:
                    doc = PPTXReader().read(str(path))
                    compared = matched = 0
                    mismatches = []
                    used_tables = set()
                    for part, table in tables:
                        candidates = [t for section in doc.sections for t in section.elements
                                      if hasattr(t, "rows") and t.rows and t.rows[0]
                                      and id(t) not in used_tables
                                      and t.rows[0][0].provenance is not None
                                      and t.rows[0][0].provenance.path == part]
                        raw_rows = table.findall("a:tr", NS)
                        relationships = {}
                        rels_path = posixpath.dirname(part) + "/_rels/" + posixpath.basename(part) + ".rels"
                        if rels_path in archive.namelist():
                            for rel in etree.fromstring(archive.read(rels_path)):
                                target = rel.get("Target", "")
                                if rel.get("TargetMode") != "External":
                                    target = "#" + posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
                                relationships[rel.get("Id")] = target
                        matching = None
                        expected = [[cell_texts(tc, relationships) for tc in tr.findall("a:tc", NS)] for tr in raw_rows]
                        for candidate in candidates:
                            actual = [[model_cell_blocks(cell) for cell in r] for r in candidate.rows]
                            if actual == expected:
                                matching = candidate
                                break
                        count = sum(len(r) for r in expected)
                        compared += count
                        if matching is not None:
                            used_tables.add(id(matching))
                            matched += count
                        else:
                            mismatches.append(part)
                    rows.append({"file": path.name, "tables": len(tables), "cells": compared,
                                 "matched_cells": matched, "mismatches": mismatches})
                if path.name in {"EmbeddedAudio.pptx", "EmbeddedVideo.pptx"}:
                    doc = PPTXReader().read(str(path))
                    root = roots[0][1]
                    rels = etree.fromstring(archive.read("ppt/slides/_rels/slide1.xml.rels"))
                    relations = {r.get("Id"): r.get("Target") for r in rels}
                    tag = "audioFile" if "Audio" in path.name else "videoFile"
                    node = root.find(".//a:" + tag, NS)
                    rid = node.get("{%s}link" % NS["r"])
                    target = posixpath.normpath(posixpath.join("ppt/slides", relations[rid]))
                    assets = [a for a in doc.assets if a.metadata.get("kind") in {"audio", "video"}]
                    rows.append({"file": path.name, "media_relationship": rid,
                                 "expected": target,
                                 "actual": [{"path": a.source_path, "content_type": a.content_type,
                                             "filename": a.filename, "exists": archive.getinfo(a.source_path).file_size > 0}
                                            for a in assets],
                                 "reference_present": any(target in p.text for p in doc.find_all("paragraph"))})
        except (zipfile.BadZipFile, etree.XMLSyntaxError, KeyError, ValueError) as exc:
            rows.append({"file": path.name, "error": str(exc)})
    return {"files": files, "math_samples": math_samples, "caption_tags": caption_tags, "results": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", help="Apache POI test-data/slideshow 경로")
    parser.add_argument("--recursive", action="store_true", help="하위 폴더의 PPTX도 검사한다")
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus, args.recursive), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
