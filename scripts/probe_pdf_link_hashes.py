"""공개 PDF의 Markdown·JSON 해시와 글자 수만 저장한다.

예: python -m scripts.probe_pdf_link_hashes corpus/pdfjs-src/test/pdfs --output hashes.json
"""
import argparse
import hashlib
import json
import signal
from pathlib import Path

from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.pdf.reader import PDFReader


class ProbeDeadline(BaseException):
    """문서별 처리 시간 상한."""


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text-tables", action="store_true")
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args()

    def deadline(_signum, _frame):
        raise ProbeDeadline("document deadline")

    signal.signal(signal.SIGALRM, deadline)
    rows = {}
    paths = args.corpus.rglob("*.pdf") if args.recursive else args.corpus.glob("*.pdf")
    for path in sorted(paths):
        key = path.relative_to(args.corpus).as_posix()
        try:
            signal.alarm(15)
            document = PDFReader(text_tables=args.text_tables).read(str(path))
            markdown = to_markdown(document)
            encoded = json.dumps(to_dict(document), ensure_ascii=False, sort_keys=True)
            rows[key] = {"markdown_sha256": _digest(markdown),
                               "markdown_chars": len(markdown),
                               "json_sha256": _digest(encoded),
                               "json_chars": len(encoded),
                               "errors": document.errors}
        except (Exception, ProbeDeadline) as exc:
            rows[key] = {"error": type(exc).__name__}
        finally:
            signal.alarm(0)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(json.dumps({"documents": len(rows),
                      "errors": sum("error" in row for row in rows.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
