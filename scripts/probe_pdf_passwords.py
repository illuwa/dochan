"""pdf.js 매니페스트의 암호 PDF를 제공 암호와 틀린 암호로 검증한다.

실행: /usr/bin/python3 -m scripts.probe_pdf_passwords <pdfs 경로> --output <JSON>
코퍼스는 읽기 전용이며 매니페스트와 PDF 바이트를 저장소로 복사하지 않는다.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from dochan.pdf.objects import PDFLexer, parse_indirect_object
from dochan.pdf.reader import PDFReader


def _revision(data):
    """암호 객체를 원시 바이트에서 읽어 인증을 반복하지 않고 R값을 기록한다."""
    refs = list(re.finditer(rb"/Encrypt\s+(\d+)\s+(\d+)\s+R", data))
    if not refs:
        # 구형 작성기는 암호 사전을 트레일러에 직접 넣기도 한다.
        inline = list(re.finditer(rb"/Encrypt\s*(?=<<)", data))
        if not inline:
            return None
        try:
            dictionary = PDFLexer(data, inline[-1].end()).parse_object()
            return dictionary.get("R") if isinstance(dictionary, dict) else None
        except Exception:
            return None
    number, generation = refs[-1].groups()
    pattern = rb"(?<!\d)" + number + rb"\s+" + generation + rb"\s+obj\b"
    match = re.search(pattern, data)
    if match is None:
        return None
    try:
        _number, _generation, dictionary = parse_indirect_object(data, match.start())
        return dictionary.get("R") if isinstance(dictionary, dict) else None
    except Exception:
        return None


def _read(path, password):
    document = PDFReader(password=password).read(str(path))
    text = "\n".join(p.text for section in document.sections for p in section.elements
                     if hasattr(p, "text"))
    return {"sections": len(document.sections), "text_chars": len(text),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "preview": text[:120], "warnings": document.errors}


def probe(corpus, manifest):
    corpus = corpus.resolve()
    manifest_text = manifest.read_text(encoding="utf-8")
    rows = []
    for entry in json.loads(manifest_text):
        if "password" not in entry:
            continue
        name = Path(entry["file"]).name
        path = corpus / name
        if not path.is_file():
            rows.append({"file": name, "status": "missing"})
            continue
        if path.resolve().parent != corpus:
            rows.append({"file": name, "status": "outside-corpus"})
            continue
        data = path.read_bytes()
        correct = _read(path, entry["password"])
        wrong_password = "dochan-probe-incorrect-password"
        if wrong_password == entry["password"]:
            wrong_password += "!"
        wrong = _read(path, wrong_password)
        marker = '"id": "' + entry["id"] + '"'
        position = manifest_text.find(marker)
        rows.append({"file": name, "revision": _revision(data),
                     "manifest_line": manifest_text[:position].count("\n") + 1,
                     "md5_matches_manifest": hashlib.md5(data).hexdigest() == entry.get("md5"),
                     "correct_password": correct, "wrong_password": wrong,
                     "accepted": correct["sections"] > 0,
                     "wrong_rejected": wrong["sections"] == 0 and
                     any("암호" in message for message in wrong["warnings"])})
    checked = [row for row in rows if "accepted" in row]
    return {"samples": len(checked), "accepted": sum(row["accepted"] for row in checked),
            "wrong_rejected": sum(row["wrong_rejected"] for row in checked), "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = args.manifest or args.corpus.parent / "test_manifest.json"
    result = probe(args.corpus, manifest)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
