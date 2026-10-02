"""공개 pdf.js 코퍼스의 PDF 기능을 읽기 전용으로 검사한다."""
import argparse
import base64
import io
import json
import re
import struct
from pathlib import Path

from dochan.pdf.objects import PDFRef, PDFStream
from dochan.pdf.structure import PDFFile


def _tiff_decode(raw, width, height, colors, compression, predictor=1):
    """검증 전용 libtiff oracle. PDF 파서의 출력은 TIFF 입력으로 사용하지 않는다."""
    from PIL import Image
    count = 11
    extras = 8 + 2 + count * 12 + 4
    pixel_at = extras + colors * 2
    tags = [(256, 4, 1, width), (257, 4, 1, height),
            (258, 3, colors, 8 if colors == 1 else extras),
            (259, 3, 1, compression), (262, 3, 1, 5 if colors == 4 else 1),
            (273, 4, 1, pixel_at), (277, 3, 1, colors),
            (278, 4, 1, height), (279, 4, 1, len(raw)),
            (284, 3, 1, 1), (317, 3, 1, predictor)]
    head = b"II" + struct.pack("<HIH", 42, 8, count)
    for tag, kind, n, value in sorted(tags):
        head += struct.pack("<HHII", tag, kind, n, value)
    head += struct.pack("<I", 0) + struct.pack("<" + "H" * colors, *([8] * colors))
    with Image.open(io.BytesIO(head + raw)) as image:
        return image.tobytes()


def scan_filters(root):
    files = sorted(Path(root).glob("*.pdf"))
    results = []
    for path in files:
        data = path.read_bytes()
        if not re.search(rb"/LZW(?:Decode)?\b|/Predictor\s+2\b", data):
            continue
        pdf = PDFFile(data)
        for num in list(pdf.xref):
            stream = pdf.resolve(PDFRef(num, 0))
            if not isinstance(stream, PDFStream):
                continue
            d = stream.dictionary
            filters = d.get("Filter", [])
            filters = filters if isinstance(filters, list) else [filters]
            parms = d.get("DecodeParms", {})
            if not ("LZWDecode" in filters or "LZW" in filters or
                    isinstance(parms, dict) and parms.get("Predictor") == 2):
                continue
            decoded = pdf.decode_stream_bytes(stream)
            record = {"file": path.name, "object": num, "filters": filters,
                      "parms": parms, "decoded_bytes": len(decoded)}
            if d.get("BitsPerComponent") == 8 and d.get("Width") and d.get("Height"):
                raw = stream.raw
                if str(filters[0]) == "ASCII85Decode":
                    raw = base64.a85decode(raw.strip().removesuffix(b"~>"), adobe=False)
                colors = parms.get("Colors", 1) if isinstance(parms, dict) else 1
                oracle = _tiff_decode(raw, d["Width"], d["Height"], colors,
                                      5 if "LZWDecode" in filters else 8,
                                      parms.get("Predictor", 1) if isinstance(parms, dict) else 1)
                record["oracle_bytes"] = len(oracle)
                record["oracle_equal"] = decoded == oracle
            else:
                record["stream_prefix"] = decoded[:64].decode("ascii", errors="replace")
            results.append(record)
    return {"pdf_files": len(files), "filters": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = scan_filters(args.corpus)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
