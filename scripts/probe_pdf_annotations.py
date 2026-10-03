"""공개 PDF 주석·목적지·텍스트 직사각형을 읽기 전용으로 조사한다.

실행: /usr/bin/python3 -m scripts.probe_pdf_annotations <pdfjs/test/pdfs>
Contents와 작성자의 기대값은 독립 PDF 문자열 디코딩으로 구한다.
RC는 표준 라이브러리 DOM으로 독립 파싱하고 원시 XML도 증거에 남긴다.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import signal
import sys
from xml.etree import ElementTree as etree  # nosemgrep: use-defused-xml -- independent gold, declarations rejected before parse

from dochan.model.header_footer import Comment
from dochan.pdf.annotations import CommentExtractor, DestinationResolver, MARKUP_SUBTYPES
from dochan.pdf.content import ContentTextExtractor, writing_direction
from dochan.pdf.objects import PDFName, PDFRef, PDFStream
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile


class ProbeDeadline(BaseException):
    """리더의 Exception 경고 강등에 삼켜지지 않는 측정 전용 시간 제한이다."""


def independent_string(value):
    if not isinstance(value, bytes):
        return ""
    if value[:2] == b"\xfe\xff":
        return value[2:].decode("utf-16-be", errors="replace")
    if value[:3] == b"\xef\xbb\xbf":
        return value[3:].decode("utf-8", errors="replace")
    # ISO 32000-1 Annex D PDFDocEncoding 문자 코드.
    table = {24: 0x2d8, 25: 0x2c7, 26: 0x2c6, 27: 0x2d9, 28: 0x2dd,
             29: 0x2db, 30: 0x2da, 31: 0x2dc, 127: 0xfffd, 159: 0xfffd,
             160: 0x20ac, 173: 0xfffd}
    special = (0x2022, 0x2020, 0x2021, 0x2026, 0x2014, 0x2013, 0x192,
               0x2044, 0x2039, 0x203a, 0x2212, 0x2030, 0x201e, 0x201c,
               0x201d, 0x2018, 0x2019, 0x201a, 0x2122, 0xfb01, 0xfb02,
               0x141, 0x152, 0x160, 0x178, 0x17d, 0x131, 0x142, 0x153,
               0x161, 0x17e)
    table.update((128 + index, point) for index, point in enumerate(special))
    return "".join(chr(table.get(byte, byte)) for byte in value)


def independent_rc(value):
    if not isinstance(value, bytes) or len(value) > 65536:
        return ""
    try:
        if value.startswith((b"\xff\xfe\0\0", b"\0\0\xfe\xff")):
            decoded = value.decode("utf-32")
        elif value.startswith((b"\xff\xfe", b"\xfe\xff")):
            decoded = value.decode("utf-16")
        else:
            decoded = value.decode("utf-8-sig")
        if "<!DOCTYPE" in decoded.upper() or "<!ENTITY" in decoded.upper():
            return ""
        root = etree.fromstring(decoded)  # nosemgrep: use-defused-xml -- bounded independent gold; decoded declarations rejected
    except (ValueError, etree.ParseError):
        return ""

    def local(node):
        return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""

    def text(node):
        # 감수 기준은 제품 코드와 독립적으로 itertext 로 모은다
        return "".join(node.itertext())

    blocks = []
    for node in root.iter():
        if local(node) in ("p", "div"):
            if not any(local(child) in ("p", "div") for child in node.iter() if child is not node):
                blocks.append(text(node).strip())
    result = "\n".join(blocks).strip() if blocks else text(root).strip()
    return result


def raw_value(value, depth=0):
    if depth > 8:
        return "<depth-limit>"
    if isinstance(value, PDFRef):
        return "{} {} R".format(value.num, value.gen)
    if isinstance(value, PDFName):
        return "/" + str(value)
    if isinstance(value, bytes):
        return independent_string(value)[:4000]
    if isinstance(value, list):
        return [raw_value(item, depth + 1) for item in value[:32]]
    if isinstance(value, dict):
        return {str(key): raw_value(item, depth + 1) for key, item in list(value.items())[:32]}
    return value


def independent_names(pdf):
    root = pdf.resolve(pdf.trailer.get("Root"))
    names = {}
    origins = {}
    if not isinstance(root, dict):
        return names, origins
    dictionary = pdf.resolve(root.get("Dests"))
    if isinstance(dictionary, dict):
        for name, dest in dictionary.items():
            names[str(name)] = dest
            origins[str(name)] = "catalog/Dests"
    catalog_names = pdf.resolve(root.get("Names"))
    pending = [catalog_names.get("Dests")] if isinstance(catalog_names, dict) else []
    seen = set()
    while pending and len(seen) < 4096:
        ref = pending.pop(0)
        key = (ref.num, ref.gen) if isinstance(ref, PDFRef) else id(ref)
        if key in seen:
            continue
        seen.add(key)
        node = pdf.resolve(ref)
        if not isinstance(node, dict):
            continue
        pairs = pdf.resolve(node.get("Names"))
        if isinstance(pairs, list):
            for index in range(0, min(len(pairs) - 1, 8192), 2):
                name = pdf.resolve(pairs[index])
                if isinstance(name, bytes):
                    name = independent_string(name)
                    names[name] = pairs[index + 1]
                    origins[name] = "catalog/Names/Dests/Names"
        kids = pdf.resolve(node.get("Kids"))
        if isinstance(kids, list):
            pending.extend(kids[:4096 - len(seen)])
    return names, origins


def independent_page(pdf, destination, names, page_refs, page_ids):
    seen = set()
    for _ in range(64):
        destination = pdf.resolve(destination)
        if isinstance(destination, list) and destination:
            ref = destination[0]
            if isinstance(ref, PDFRef):
                return page_refs.get(ref.num), raw_value(ref)
            return page_ids.get(id(pdf.resolve(ref))), raw_value(ref)
        if isinstance(destination, dict):
            destination = destination.get("D")
        elif isinstance(destination, (bytes, PDFName)):
            name = independent_string(destination) if isinstance(destination, bytes) else str(destination)
            if name in seen:
                return None, "cycle"
            seen.add(name)
            destination = names.get(name)
        else:
            return None, None
    return None, "depth-limit"


def _rectangle(pdf, annot):
    rect = pdf.resolve(annot.get("Rect"))
    if not isinstance(rect, list) or len(rect) != 4 or not all(isinstance(n, (int, float)) for n in rect):
        return None
    return (min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3]))


def probe(corpus):
    files = sorted(corpus.glob("*.pdf"))
    result = {"scanned": len(files), "uninspectable": 0, "failures": [], "linkless_documents": 0,
              "documents_with_links": 0, "documents_with_comments": 0, "subtypes": Counter(),
              "comment_expected": 0, "comment_actual": 0, "comment_mismatches": [],
              "popup_count": 0, "rich_text_annotations": 0, "rich_text_fallbacks": 0,
              "rich_text_stream_annotations": 0,
              "examples": {}, "internal_forms": Counter(), "internal_links": 0,
              "internal_resolved_forms": Counter(),
              "internal_resolved": 0, "internal_mismatches": [], "internal_examples": {},
              "geometry": {"links_measured": 0, "links_without_matches": 0,
                           "fragments_center_inside": Counter(), "first_examples": [],
                           "near_misses": [], "rotated_fragments_skipped": 0}}

    def deadline(_signal, _frame):
        raise ProbeDeadline()

    old_handler = signal.signal(signal.SIGALRM, deadline)
    reader = PDFReader()
    for file_index, path in enumerate(files):
        previous = deepcopy(result)
        try:
            signal.alarm(5)
            pdf = PDFFile(path.read_bytes())
            pages = pdf.pages()
            if not pages or (pdf.encrypted and not pdf.decrypt_ok):
                result["uninspectable"] += 1
                continue
            names, origins = independent_names(pdf)
            page_ids = {id(page): n for n, (page, _) in enumerate(pages, 1)}
            page_refs = {number: page_ids[id(obj)] for number, obj in pdf._cache.items() if id(obj) in page_ids}
            resolver = DestinationResolver(pdf, pages)
            extractor = CommentExtractor()
            seen = set()
            has_link = has_comment = False
            font_cache = {}
            for page_number, (page, resources) in enumerate(pages, 1):
                annots = pdf.resolve(page.get("Annots"))
                if not isinstance(annots, list):
                    continue
                expected = []
                source = []
                links = []
                for ref in annots[:256]:
                    annot = pdf.resolve(ref)
                    if not isinstance(annot, dict):
                        continue
                    subtype = str(annot.get("Subtype"))
                    result["subtypes"][subtype] += 1
                    key = (ref.num, ref.gen) if isinstance(ref, PDFRef) else id(ref)
                    if subtype == "Popup":
                        result["popup_count"] += 1
                    if subtype == "Link":
                        has_link = True
                        links.append((ref, annot))
                    if key in seen:
                        continue
                    seen.add(key)
                    if subtype not in MARKUP_SUBTYPES:
                        continue
                    contents = independent_string(pdf.resolve(annot.get("Contents"))).strip()
                    rich = pdf.resolve(annot.get("RC"))
                    if rich:
                        result["rich_text_annotations"] += 1
                    if isinstance(rich, PDFStream):
                        result["rich_text_stream_annotations"] += 1
                        rich = pdf.decode_stream_bytes(rich) if len(rich.raw) <= 65536 else b""
                    if not contents:
                        contents = independent_rc(rich)
                        if contents:
                            result["rich_text_fallbacks"] += 1
                    if not contents:
                        continue
                    has_comment = True
                    author = independent_string(pdf.resolve(annot.get("T"))).strip()
                    expected.append(("\n".join(line for line in contents.splitlines() if line.strip()), author))
                    source.append({"file": path.name, "page": page_number, "object": raw_value(ref),
                                   "subtype": subtype, "raw_Contents": raw_value(pdf.resolve(annot.get("Contents"))),
                                   "raw_T": raw_value(pdf.resolve(annot.get("T"))),
                                   "raw_RC": raw_value(rich), "expected_text": expected[-1][0], "expected_author": author})
                comments = [obj for obj in extractor.extract(pdf, page, page_number) if isinstance(obj, Comment)]
                actual = [(obj.text, obj.author) for obj in comments]
                result["comment_expected"] += len(expected)
                result["comment_actual"] += len(actual)
                if expected != actual:
                    result["comment_mismatches"].append({"file": path.name, "page": page_number,
                                                          "expected": expected[:10], "actual": actual[:10]})
                for index, sample in enumerate(source):
                    category = sample["subtype"]
                    if sample["raw_RC"] and not sample["raw_Contents"]:
                        category += "-RC-fallback"
                    examples = result["examples"].setdefault(category, [])
                    if len(examples) < 2:
                        sample["actual_text"] = actual[index][0] if index < len(actual) else None
                        sample["actual_author"] = actual[index][1] if index < len(actual) else None
                        sample["matched"] = index < len(actual) and actual[index] == expected[index]
                        examples.append(sample)
                for ref, annot in links:
                    action = pdf.resolve(annot.get("A"))
                    if isinstance(action, dict) and str(action.get("S")) == "GoTo":
                        dest = action.get("D")
                        form = "A/GoTo"
                    elif not isinstance(action, dict) and annot.get("Dest") is not None:
                        dest = annot.get("Dest")
                        form = "Dest"
                    else:
                        continue
                    result["internal_links"] += 1
                    resolved = pdf.resolve(dest)
                    name = independent_string(resolved) if isinstance(resolved, bytes) else str(resolved) if isinstance(resolved, PDFName) else ""
                    form += "/" + origins.get(name, "name-unresolved") if name else "/array"
                    result["internal_forms"][form] += 1
                    expected_page, expected_ref = independent_page(pdf, dest, names, page_refs, page_ids)
                    actual_page = resolver.page_number(dest)
                    if expected_page is not None:
                        result["internal_resolved"] += 1
                        result["internal_resolved_forms"][form] += 1
                    sample = {"file": path.name, "page": page_number, "object": raw_value(ref),
                              "form": form, "destination": raw_value(resolved), "page_ref": expected_ref,
                              "expected_page": expected_page, "actual_page": actual_page,
                              "matched": expected_page == actual_page}
                    if expected_page != actual_page:
                        result["internal_mismatches"].append(sample)
                    examples = result["internal_examples"].setdefault(form, [])
                    if len(examples) < 3:
                        examples.append(sample)
                if links:
                    fonts = reader._font_infos(pdf, resources, font_cache)
                    content = b"\n".join(reader._page_content_parts(pdf, page))
                    fragments = ContentTextExtractor.from_fonts(fonts).extract_fragments(content)
                    geo = result["geometry"]
                    for ref, annot in links:
                        rect = _rectangle(pdf, annot)
                        if rect is None:
                            continue
                        geo["links_measured"] += 1
                        matches = []
                        nearby = []
                        for frag in fragments[:20000]:
                            if writing_direction(frag) != "ltr":
                                geo["rotated_fragments_skipped"] += 1
                                continue
                            midpoint = frag.x + frag.width / 2
                            if not rect[0] <= midpoint <= rect[2] or frag.size <= 0:
                                continue
                            bottom = (rect[1] - frag.y) / frag.size
                            top = (rect[3] - frag.y) / frag.size
                            for ratio in (0.0, 0.35, 0.5, 0.7, 0.9):
                                if bottom <= ratio <= top:
                                    geo["fragments_center_inside"][str(ratio)] += 1
                            sample = {"text": frag.text[:200], "x": round(frag.x, 4), "y": round(frag.y, 4),
                                      "width": round(frag.width, 4), "size": round(frag.size, 4),
                                      "rect_bottom_over_size": round(bottom, 4), "rect_top_over_size": round(top, 4)}
                            if bottom <= 0.5 <= top:
                                matches.append(sample)
                            elif bottom < 2 and top > -2:
                                nearby.append(sample)
                        evidence = {"file": path.name, "page": page_number, "object": raw_value(ref),
                                    "rect": rect, "quad_points": raw_value(pdf.resolve(annot.get("QuadPoints"))),
                                    "action": raw_value(pdf.resolve(annot.get("A"))),
                                    "destination": raw_value(pdf.resolve(annot.get("Dest"))),
                                    "matches": matches[:4], "match_count": len(matches)}
                        if not matches:
                            geo["links_without_matches"] += 1
                            if nearby and len(geo["near_misses"]) < 15:
                                evidence["nearby"] = nearby[:4]
                                geo["near_misses"].append(evidence)
                        elif len(geo["first_examples"]) < 15:
                            geo["first_examples"].append(evidence)
            result["documents_with_links"] += int(has_link)
            result["linkless_documents"] += int(not has_link)
            result["documents_with_comments"] += int(has_comment)
        except (Exception, ProbeDeadline) as exc:
            result = previous  # 문서 중간 실패의 부분 집계를 검증 결과에 섞지 않는다.
            result["failures"].append({"file": path.name, "error": type(exc).__name__})
        finally:
            signal.alarm(0)
        if (file_index + 1) % 100 == 0:
            print("PDF 주석 스캔: {}/{}".format(file_index + 1, len(files)), file=sys.stderr, flush=True)
    signal.signal(signal.SIGALRM, old_handler)
    return result


def verify_body_links(corpus):
    """원시 Link 부재 문서의 실제 Document TextRun에 잘못된 링크가 생기는지 잰다."""
    result = {"scanned": 0, "parser_excluded": [], "parser_failures": [], "fullread_timeouts": [],
              "fullread_failures": [], "negative_documents": 0, "negative_completed": 0,
              "negative_completed_with_text": 0, "negative_completed_without_text": 0,
              "negative_body_link_runs": 0, "negative_fallback_link_runs": 0,
              "negative_positive_files": [], "positive_examples": []}

    def deadline(_signal, _frame):
        raise ProbeDeadline()

    old_handler = signal.signal(signal.SIGALRM, deadline)
    reader = PDFReader()
    for index, path in enumerate(sorted(corpus.glob("*.pdf"))):
        result["scanned"] += 1
        try:
            signal.alarm(5)
            pdf = PDFFile(path.read_bytes())
            pages = pdf.pages()
            if not pages or (pdf.encrypted and not pdf.decrypt_ok):
                result["parser_excluded"].append(path.name)
                continue
            has_link = False
            for page, _inherited in pages:
                annots = pdf.resolve(page.get("Annots"))
                if isinstance(annots, list):
                    for ref in annots[:65536]:
                        annot = pdf.resolve(ref)
                        if isinstance(annot, dict) and str(annot.get("Subtype")) == "Link":
                            has_link = True
                            break
                if has_link:
                    break
        except (Exception, ProbeDeadline) as exc:
            result["parser_failures"].append({"file": path.name, "error": type(exc).__name__})
            continue
        finally:
            signal.alarm(0)
        positive_sample = path.name in ("TAMReview.pdf", "basicapi.pdf", "annotation-link-text-popup.pdf")
        if has_link and not positive_sample:
            continue
        if not has_link:
            result["negative_documents"] += 1
        try:
            signal.alarm(5)
            document = reader.read(str(path))
            body_runs = []
            fallback_runs = []
            unlinked_text = []
            paragraphs = document.find_all("paragraph")
            for paragraph in paragraphs:
                for run in paragraph.runs:
                    if run.link:
                        target = fallback_runs if getattr(run.provenance, "path", "") == "annots" else body_runs
                        target.append({"text": run.text, "link": run.link,
                                       "page": getattr(run.provenance, "page", None)})
                    elif run.text.strip():
                        unlinked_text.append(run.text)
            if not has_link:
                result["negative_completed"] += 1
                text_key = "negative_completed_with_text" if any(p.text.strip() for p in paragraphs) else "negative_completed_without_text"
                result[text_key] += 1
                result["negative_body_link_runs"] += len(body_runs)
                result["negative_fallback_link_runs"] += len(fallback_runs)
                if body_runs or fallback_runs:
                    result["negative_positive_files"].append({"file": path.name, "body": body_runs,
                                                               "fallback": fallback_runs})
            else:
                # 기대값은 원시 Link 주석의 목적지와 위의 좌표 실측으로 독립 확인했다.
                expectations = {
                    "TAMReview.pdf": [("Creative Commons Attribution-Noncommercial-No Derivative Works License",
                                       "http://creativecommons.org/licenses/by-nc-nd/3.0/")],
                    "basicapi.pdf": [("Chapter 1 ", "#page-2"), ("Paragraph 1.1 ", "#page-3")],
                    "annotation-link-text-popup.pdf": [("mozilla.org", "http://www.mozilla.org/")],
                }
                expected = expectations[path.name]
                combined = []
                for run in body_runs:
                    if combined and combined[-1]["link"] == run["link"] and combined[-1]["page"] == run["page"]:
                        combined[-1]["text"] += run["text"]
                    else:
                        combined.append(dict(run))
                passed = all(any(text in run["text"] and run["link"] == link for run in combined)
                             for text, link in expected)
                if path.name == "TAMReview.pdf":
                    passed = passed and "Copyright:" in unlinked_text
                result["positive_examples"].append({"file": path.name, "expected": expected,
                                                    "actual_body_runs": combined, "passed": passed,
                                                    "unlinked_Copyright_confirmed": "Copyright:" in unlinked_text,
                                                    "fallback_link_runs": len(fallback_runs)})
        except ProbeDeadline:
            result["fullread_timeouts"].append(path.name)
        except Exception as exc:
            result["fullread_failures"].append({"file": path.name, "error": type(exc).__name__})
        finally:
            signal.alarm(0)
        if (index + 1) % 100 == 0:
            print("PDF 본문 링크 검증: {}/983".format(index + 1), file=sys.stderr, flush=True)
    signal.signal(signal.SIGALRM, old_handler)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--verify-body-links", action="store_true")
    args = parser.parse_args()
    result = verify_body_links(args.corpus) if args.verify_body_links else probe(args.corpus)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
