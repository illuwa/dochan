"""공개 PDF 코퍼스의 세로 인코딩과 세로 텍스트 좌표를 검증한다.

실행: /usr/bin/python3 -m scripts.probe_pdf_vertical <pdfjs/test/pdfs>
코퍼스 파일을 저장소에 복사하지 않으며 파일명만 결과에 사용한다.
"""
import argparse
import json
import signal
import sys
from pathlib import Path

from dochan.pdf.cmap import encoding_wmode
from dochan.pdf.content import ContentTextExtractor, writing_direction
from dochan.pdf.objects import PDFName, PDFStream
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile


class ProbeDeadline(BaseException):
    """리더의 Exception 경고 강등에 삼켜지지 않는 측정 전용 시간 제한이다."""


def _font_mode(pdf, font):
    encoding = pdf.resolve(font.get("Encoding"))
    if isinstance(encoding, PDFName):
        return encoding_wmode(str(encoding))
    if isinstance(encoding, PDFStream):
        return encoding_wmode(data=pdf.decode_stream_bytes(encoding),
                              dictionary_mode=pdf.resolve(encoding.dictionary.get("WMode")))
    return 0


def _scan_resources(pdf, resources, seen, depth=0):
    if depth > 32:
        return []
    resources = pdf.resolve(resources)
    if not isinstance(resources, dict) or id(resources) in seen:
        return []
    seen.add(id(resources))
    result = []
    fonts = pdf.resolve(resources.get("Font"))
    if isinstance(fonts, dict):
        for name, ref in fonts.items():
            font = pdf.resolve(ref)
            if isinstance(font, dict) and _font_mode(pdf, font):
                result.append({"name": str(name), "encoding": str(font.get("Encoding")),
                               "to_unicode": font.get("ToUnicode") is not None})
    xobjects = pdf.resolve(resources.get("XObject"))
    if isinstance(xobjects, dict):
        for ref in xobjects.values():
            obj = pdf.resolve(ref)
            if isinstance(obj, PDFStream) and str(obj.dictionary.get("Subtype")) == "Form":
                result.extend(_scan_resources(pdf, obj.dictionary.get("Resources"), seen, depth + 1))
    return result


def _extract(pdf):
    reader = PDFReader()
    result = []
    for page, resources in pdf.pages():
        fonts = reader._font_infos(pdf, resources, {})
        extractor = ContentTextExtractor.from_fonts(fonts)
        content = b"\n".join(reader._page_content_parts(pdf, page))
        fragments = extractor.extract_fragments(content)
        result.append({"lines": extractor.extract(content),
                       "fragments": [{"text": f.text, "x": round(f.x, 4), "y": round(f.y, 4),
                                      "width": round(f.width, 4), "direction": writing_direction(f)}
                                     for f in fragments]})
    return result


def probe(corpus):
    paths = sorted(corpus.glob("*.pdf"))
    result = {"scanned": len(paths), "failures": [], "vertical_documents": [],
              "negative_documents": 0, "uninspectable_documents": 0, "verified": []}
    def deadline(_signum, _frame):
        raise ProbeDeadline("PDF 리소스 스캔이 5초 한도를 초과했다")

    old_handler = signal.signal(signal.SIGALRM, deadline)
    for index, path in enumerate(paths):
        try:
            signal.alarm(5)
            pdf = PDFFile(path.read_bytes())
            pages = pdf.pages()
            if not pages or (pdf.encrypted and not pdf.decrypt_ok):
                result["uninspectable_documents"] += 1
                continue
            found = []
            for page, resources in pages:
                found.extend(_scan_resources(pdf, resources, set()))
            if found:
                result["vertical_documents"].append({"file": path.name, "fonts": found})
            else:
                result["negative_documents"] += 1
        except (Exception, ProbeDeadline) as exc:
            result["failures"].append({"file": path.name, "error": type(exc).__name__})
        finally:
            signal.alarm(0)
        if (index + 1) % 100 == 0:
            print("PDF 리소스 스캔: {}/{}".format(index + 1, len(paths)), file=sys.stderr, flush=True)
    signal.signal(signal.SIGALRM, old_handler)
    # 기대 문자열은 각 표본의 공개 ToUnicode bfchar 및 콘텐츠 코드에서 직접 읽었다.
    for name, expected, width, x, y in [
            ("issue20930.pdf", "ABCDE", 320, 91.996, 318.88),
            ("issue6387.pdf", "あのイーハトーヴォのすきとおった風", 510, 132, 583.6)]:
        path = corpus / name
        if not path.exists():
            continue
        pages = _extract(PDFFile(path.read_bytes()))
        first = pages[0]["fragments"][0] if pages and pages[0]["fragments"] else {}
        expected_columns = 9 if name == "issue6387.pdf" else 1
        columns_match = (pages and len(pages[0]["lines"]) >= expected_columns
                         and pages[0]["lines"][:expected_columns] == [expected] * expected_columns)
        passed = (first.get("text") == expected and first.get("direction") == "down"
                  and first.get("width") == width
                  and abs(first.get("x", 0) - x) < 0.0001
                  and abs(first.get("y", 0) - y) < 0.0001 and bool(columns_match))
        result["verified"].append({"file": name, "expected": {"text": expected,
                                  "x": x, "y": y, "width": width, "direction": "down"},
                                  "actual": first, "passed": passed,
                                  "verified_columns": expected_columns if columns_match else 0,
                                  "line_count": len(pages[0]["lines"]) if pages else 0})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
