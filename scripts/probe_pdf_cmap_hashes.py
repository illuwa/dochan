"""공개 PDF 코퍼스의 Markdown 해시와 길이만 기록한다.

사용법: python -m scripts.probe_pdf_cmap_hashes <PDF 디렉터리> <출력.json>
본문은 디스크에 저장하지 않는다.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

from dochan.output.markdown import to_markdown
from dochan.pdf.reader import PDFReader


def _one(path):
    try:
        doc = PDFReader().read(str(path))
        markdown = to_markdown(doc)
        return path.name, [hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                           len(markdown), len(doc.errors)]
    except Exception as exc:
        return path.name, ["EXC:" + type(exc).__name__, 0, 0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    files = sorted(args.corpus.glob("*.pdf"))
    if not 1 <= args.jobs <= 16:
        parser.error("jobs 범위는 1..16")
    with ProcessPoolExecutor(args.jobs) as executor:
        result = dict(executor.map(_one, files, chunksize=4))
    args.output.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False),
                           encoding="utf-8")
    print("PDF", len(result), "errors", sum(row[0].startswith("EXC:")
                                             for row in result.values()))


if __name__ == "__main__":
    main()
