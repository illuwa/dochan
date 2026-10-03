"""공개 PDF 코퍼스의 Form 텍스트와 출력 회귀를 PDFium으로 측정한다.

실행 예: python -m scripts.probe_pdf_forms corpus/pdfjs-src --output result.json
변경 전 비교는 --source-root 에 git archive로 만든 소스 스냅숏을 지정한다.
문서 출력 본문은 보존하지 않고 해시, 글자 수, n-gram 빈도만 기록한다.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import signal
import sys
import unicodedata


class Deadline(BaseException):
    pass


def _timeout(_signum, _frame):
    raise Deadline()


def _normalized(value):
    return "".join(unicodedata.normalize("NFKC", value).split()).replace("\u00ad", "")


def _grams(value):
    value = _normalized(value)
    return dict(Counter(value[i:i + 2] for i in range(max(0, len(value) - 1))))


def _has_form_text(pdf):
    from dochan.pdf.objects import PDFStream
    for _page, resources in pdf.pages():
        if not isinstance(resources, dict):
            continue
        xobjects = pdf.resolve(resources.get("XObject"))
        if not isinstance(xobjects, dict):
            continue
        for ref in xobjects.values():
            stream = pdf.resolve(ref)
            if isinstance(stream, PDFStream) and str(stream.dictionary.get("Subtype")) == "Form":
                body = pdf.decode_stream_bytes(stream)
                if b"BT" in body and (b"Tj" in body or b"TJ" in body):
                    return True
    return False


def _pdfium_text(path):
    import pypdfium2 as pdfium
    parts = []
    with pdfium.PdfDocument(str(path)) as document:
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            try:
                parts.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    sys.path.insert(0, str((args.source_root or Path(__file__).resolve().parents[1]).resolve()))
    from dochan.output.json_out import to_dict
    from dochan.output.markdown import to_markdown
    from dochan.output.plain_text import to_plain_text
    from dochan.pdf.reader import PDFReader
    from dochan.pdf.structure import PDFFile

    signal.signal(signal.SIGALRM, _timeout)
    results = {}
    paths = ([args.corpus / name for name in args.files] if args.files else
             sorted(p for p in args.corpus.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"))
    for index, path in enumerate(paths, 1):
        name = str(path.relative_to(args.corpus))
        try:
            signal.alarm(args.timeout)
            document = PDFReader().read(str(path))
            markdown = to_markdown(document)
            json_data = json.dumps(to_dict(document), ensure_ascii=False, sort_keys=True)
            plain = to_plain_text(document)
            pdf = PDFFile(path.read_bytes())
            form_text = _has_form_text(pdf)
            row = {
                "form_text": form_text,
                "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
                "json_sha256": hashlib.sha256(json_data.encode()).hexdigest(),
                "text_chars": len(_normalized(plain)),
                "tables": len(document.find_all("table")),
                "headers_footers": len(document.find_all("header_footer")),
                "errors": document.errors,
            }
            if form_text:
                row["bigrams"] = _grams(plain)
                oracle = _pdfium_text(path)
                row["pdfium_chars"] = len(_normalized(oracle))
                row["pdfium_bigrams"] = _grams(oracle)
                row["chars"] = dict(Counter(_normalized(plain)))
                row["pdfium_char_counts"] = dict(Counter(_normalized(oracle)))
            results[name] = row
        except (Exception, Deadline) as exc:
            results[name] = {"probe_error": type(exc).__name__, "message": str(exc)[:200]}
        finally:
            signal.alarm(0)
        if index % 100 == 0:
            print("processed %d/%d" % (index, len(paths)), file=sys.stderr, flush=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"documents": len(paths),
                      "form_text": sum(bool(v.get("form_text")) for v in results.values()),
                      "probe_errors": sum("probe_error" in v for v in results.values())}))


if __name__ == "__main__":
    main()
