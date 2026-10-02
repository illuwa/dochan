"""표 데이터의 바이트와 공개 PDF 출력을 변경 전 데이터에 대조한다.

baseline_json은 변경 전에 core14_metrics의 _DATA를 복원한 JSON이다.
PDF 코퍼스는 읽기만 하며 원본 문서 내용은 결과에 기록하지 않는다.
"""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import zlib

from dochan import Dochan
from dochan.pdf import core14_metrics


def probe(baseline_json, pdf_corpus):
    baseline = baseline_json.read_bytes()
    tree = ast.parse(Path(core14_metrics.__file__).read_text(encoding="utf-8"))
    payload = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "_DATA"
                           for target in node.targets))
    current = zlib.decompress(base64.b85decode(payload))
    old = json.loads(baseline)
    previous = [old["widths"], old["unicode"],
                {key: {int(code): glyph for code, glyph in table.items()}
                 for key, table in old["encodings"].items()}]
    tables = [core14_metrics.GLYPH_WIDTHS, core14_metrics.GLYPH_UNICODE,
              core14_metrics.ENCODINGS]
    saved = [dict(table) for table in tables]
    rows = []
    for name in ("standard_fonts.pdf", "ZapfDingbats.pdf", "basicapi.pdf"):
        path = pdf_corpus / name
        actual = Dochan(str(path))
        try:
            for table, contents in zip(tables, previous):
                table.clear()
                table.update(contents)
            expected = Dochan(str(path))
        finally:
            for table, contents in zip(tables, saved):
                table.clear()
                table.update(contents)
        actual_json, expected_json = actual.to_json(), expected.to_json()
        rows.append({"file": name, "json_equal": actual_json == expected_json,
                     "markdown_equal": actual.to_markdown() == expected.to_markdown(),
                     "text_characters": len(actual.to_plain_text()),
                     "errors": len(actual.errors),
                     "json_sha256": hashlib.sha256(actual_json.encode()).hexdigest()})
    return {"table_bytes_equal": baseline == current,
            "compressed_bytes_equal": base64.b85encode(zlib.compress(baseline, 9)).decode() == payload,
            "payload_sha256": hashlib.sha256(current).hexdigest(),
            "fonts": len(tables[0]), "widths": sum(map(len, tables[0].values())),
            "unicode_glyphs": len(tables[1]), "encodings": len(tables[2]), "pdfs": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_json", type=Path)
    parser.add_argument("pdf_corpus", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe(args.baseline_json, args.pdf_corpus)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if (result["table_bytes_equal"] and result["compressed_bytes_equal"]
                 and all(row["json_equal"] and row["markdown_equal"]
                         and row["text_characters"] > 0 and row["errors"] == 0
                         for row in result["pdfs"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
