"""공개 OOXML 코퍼스의 출력 지문을 저장하고 이전 지문과 비교한다.

코퍼스는 읽기만 하며 각 문서의 Markdown, JSON, 경고를 함께 비교한다.
사용 예: python -m scripts.probe_ooxml_strict CORPUS ... --output before.json
이후 같은 명령에 --baseline before.json을 추가한다.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import signal
import zipfile

from dochan.utils import safe_xml as etree

from dochan.ooxml.docx import DOCXReader
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.xlsx import XLSXReader
from dochan.ooxml.package import MAX_XML_PART_SIZE
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown


READERS = {".docx": DOCXReader, ".pptx": PPTXReader, ".xlsx": XLSXReader}
PAIRS = {"SampleSS.strict.xlsx": "SampleSS.xlsx", "sample.strict.xlsx": "sample.xlsx",
         "SimpleStrict.xlsx": "SimpleNormal.xlsx"}


def strict_evidence(path, doc):
    """패키지 정규화와 독립적으로 원시 QName의 문단 문자열을 확인한다.

    이 비교는 텍스트 보존 검사이며 전체 읽기 순서나 렌더링 적합성 판정이 아니다.
    XML 문단이 없는 SmartArt 전용 문서는 성공 분모에 포함하지 않는다.
    """
    evidence = {}
    if path.suffix in {".docx", ".pptx"}:
        namespace = "http://purl.oclc.org/ooxml/" + (
            "wordprocessingml/main" if path.suffix == ".docx" else "drawingml/main")
        texts = []
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = info.filename
                selected = (name == "word/document.xml" or
                            (name.startswith(("word/header", "word/footer", "ppt/slides/slide"))
                             and name.endswith(".xml")))
                if not selected or info.file_size > MAX_XML_PART_SIZE:
                    continue
                root = etree.fromstring(archive.read(info),
                    etree.XMLParser(resolve_entities=False, no_network=True))
                for paragraph in root.iter("{" + namespace + "}p"):
                    value = "".join(node.text or "" for node in paragraph.iter("{" + namespace + "}t"))
                    if value.strip():
                        texts.append((name, value))
        compact_markdown = re.sub(r"\s", "", to_markdown(doc))
        checks = [{"part": name, "expected": value,
                   "matched": re.sub(r"\s", "", value) in compact_markdown}
                  for name, value in texts]
        evidence.update(text_checks=checks, checked=len(checks),
                        matched=sum(check["matched"] for check in checks),
                        status="checked" if checks else "no paragraph text sample")
    if path.name in PAIRS:
        pair = path.with_name(PAIRS[path.name])
        if pair.exists():
            other = READERS[path.suffix]().read(str(pair))
            evidence["transitional_pair"] = {"file": pair.name,
                "json_equal": to_dict(doc) == to_dict(other),
                "markdown_equal": to_markdown(doc) == to_markdown(other),
                "errors_equal": doc.errors == other.errors}
    return evidence


def _timeout(signum, frame):
    raise TimeoutError("문서당 30초 상한을 넘었다.")


def fingerprint(item):
    label, filename = item
    path = Path(filename)
    row = {"file": label, "format": path.suffix[1:], "strict": False}
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(30)
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.filename.endswith((".xml", ".rels")) and info.file_size <= MAX_XML_PART_SIZE:
                    if b"http://purl.oclc.org/ooxml/" in archive.read(info):
                        row["strict"] = True
                        break
        doc = READERS[path.suffix]().read(str(path))
        markdown = to_markdown(doc)
        payload = {"json": to_dict(doc), "markdown": markdown, "errors": doc.errors}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        row.update(sha256=hashlib.sha256(encoded).hexdigest(),
                   characters=len(markdown), sections=len(doc.sections), errors=doc.errors)
        if row["strict"]:
            row["markdown"] = markdown
            row["json"] = payload["json"]
            row["verification"] = strict_evidence(path, doc)
    except Exception as exc:
        row["exception"] = type(exc).__name__ + ": " + str(exc)
    finally:
        signal.alarm(0)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    paths = [(str(index) + ":" + str(path.relative_to(root)), str(path))
             for index, root in enumerate(args.corpus)
             for path in sorted(root.rglob("*")) if path.suffix in READERS and path.is_file()]
    # fork 전 리더를 import해 실행 중 워크트리가 바뀌어도 기준 구현을 유지한다.
    with ProcessPoolExecutor(max_workers=args.workers,
                             mp_context=multiprocessing.get_context("fork")) as pool:
        rows = list(pool.map(fingerprint, paths, chunksize=1))
    result = {"roots": [str(root) for root in args.corpus], "rows": rows}
    if args.baseline:
        old = {row["file"]: row for row in json.loads(args.baseline.read_text())["rows"]}
        for row in rows:
            before = old.get(row["file"], {})
            row["unchanged"] = (row.get("sha256"), row.get("exception")) == (
                before.get("sha256"), before.get("exception"))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(Counter((row["format"] + ":" +
        ("strict" if row["strict"] else "transitional") + ":" +
        ("exception" if "exception" in row else "parsed") +
        (":" + str(row["unchanged"]) if "unchanged" in row else ""))
        for row in rows)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
