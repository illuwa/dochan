"""읽기 전용 POI OfficeArt 프로브. 코퍼스 파일은 복사하지 않는다.

사용법: /usr/bin/python3 -m scripts.probe_officeart POI_TEST_DATA --output 결과.json
DOC 스캐닝은 공용 파서의 검증용이며 FIB/PICF 기반 리더 통합을 대신하지 않는다.
"""
import argparse
import hashlib
import io
import json
import struct
from collections import Counter
from pathlib import Path

import olefile
from PIL import Image as PILImage

from dochan.office_binary.officeart import (
    Limits, Record, RecordHeader, decode_blip, parse_header, parse_records,
    read_bstore, read_shapes,
)

SAMPLES = {
    "document": ("testPictures.doc", "Picture_Alternative_Text.doc", "pictures_escher.doc", "vector_image.doc", "two_images.doc"),
    "slideshow": ("pictures.ppt", "23884_defense_FINAL_OOimport_edit.ppt"),
    "spreadsheet": ("SimpleWithImages.xls", "53446.xls"),
}
LIMITS = Limits()


def _read(ole, name):
    if not ole.exists(name):
        return b""
    if ole.get_type(name) != olefile.STGTY_STREAM:
        return b""
    if ole.get_size(name) > LIMITS.max_stream_bytes:
        raise ValueError("probe stream byte limit exceeded")
    return ole.openstream(name).read()


def _scan_doc(data, errors):
    """Observe fully bounded OfficeArt containers/FBSEs amid DOC host structures.

    No BLIP magic scanning: only full container/FBSE record headers are selected,
    with required recVer and range checks. Skip an accepted record's full extent
    so an embedded record is not counted a second time.
    """
    roots = []
    offset = 0
    allowed = {0xF000: 15, 0xF001: 15, 0xF002: 15, 0xF004: 15, 0xF007: 2}
    while offset + 8 <= len(data) and len(roots) < LIMITS.max_records:
        header = parse_header(data, offset)
        if (header.rec_type in allowed and header.rec_ver == allowed[header.rec_type]
                and 8 <= header.rec_len <= min(LIMITS.max_record_bytes, len(data) - offset - 8)):
            roots.extend(parse_records(data, offset, header.rec_len + 8, errors=errors))
            offset += header.rec_len + 8
        else:
            offset += 1
    return roots


def _biff_drawing(data, wanted):
    chunks = []
    offset = 0
    active = False
    while offset + 4 <= len(data):
        kind, size = struct.unpack_from("<HH", data, offset)
        offset += 4
        if size > len(data) - offset:
            break
        if kind == wanted or (kind == 0x003C and active):
            chunks.append(data[offset:offset + size])
            active = True
        else:
            active = False
        offset += size
    return b"".join(chunks)


def _image_info(image, offset=None, header=None):
    fmt, data = image
    info = {"format": fmt, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if offset is not None:
        info["offset"] = offset
    if header is not None:
        info.update({"type": "0x%x" % header.rec_type, "instance": "0x%x" % header.rec_instance,
                     "record_length": header.rec_len})
    if fmt in ("jpg", "png", "bmp", "tiff"):
        with PILImage.open(io.BytesIO(data)) as decoded:
            info["pixel_size"] = list(decoded.size)
    return info


def _flatten_shapes(shapes):
    for shape in shapes:
        yield shape
        yield from _flatten_shapes(shape.children)


def probe_file(path):
    errors = []
    pictures = []
    stores = []
    shapes = []
    with olefile.OleFileIO(str(path)) as ole:
        if path.suffix == ".ppt":
            raw = _read(ole, "Pictures")
            roots = parse_records(raw, errors=errors)
            for r in roots:
                image = decode_blip(r, errors=errors)
                if image:
                    pictures.append(_image_info(image, r.offset, r.header))
            drawing = parse_records(_read(ole, "PowerPoint Document"), errors=errors)
            stores = read_bstore(drawing, delayed_stream=raw, errors=errors)
            shapes = read_shapes(drawing, errors=errors)
        elif path.suffix == ".xls":
            workbook = _read(ole, "Workbook") or _read(ole, "Book")
            drawing = parse_records(_biff_drawing(workbook, 0x00EB), errors=errors)
            stores = read_bstore(drawing, errors=errors)
            shapes = read_shapes(parse_records(_biff_drawing(workbook, 0x00EC), errors=errors), errors=errors)
            pictures = [_image_info(e.image) for e in stores if e.image]
        else:
            word = _read(ole, "WordDocument")
            for stream in ("0Table", "1Table", "Data", "WordDocument"):
                data = _read(ole, stream)
                roots = _scan_doc(data, errors)
                entries = read_bstore(roots, delayed_stream=word, errors=errors)
                # Inline PICF OfficeArt stores FBSE without a surrounding BStore.
                loose = [r for r in roots if r.header.rec_type == 0xF007]
                if loose:
                    store = Record(RecordHeader(15, len(loose), 0xF001, 0), 0, memoryview(b""), loose)
                    entries.extend(read_bstore([store], errors=errors))
                stores.extend(entries)
                shapes.extend(read_shapes(roots, errors=errors))
                for entry in entries:
                    if entry.image:
                        info = _image_info(entry.image)
                        info["stream"] = stream
                        pictures.append(info)
    flat = list(_flatten_shapes(shapes))
    return {"file": path.name, "formats": dict(Counter(p["format"] for p in pictures)),
            "decoded": len(pictures), "bstore_entries": len(stores),
            "bstore_decoded": sum(e.image is not None for e in stores),
            "bstore_matches_picture_payloads": (Counter(hashlib.sha256(e.image[1]).hexdigest() for e in stores if e.image)
                                                == Counter(p["sha256"] for p in pictures)),
            "pictures": pictures, "shape_count": len(flat),
            "shapes": [{"spid": s.spid, "flags": s.flags, "pib": s.pib,
                        "name": s.name, "description": s.description,
                        "textbox_id": s.textbox_id} for s in flat], "warnings": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="POI test-data 경로")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    rows = {}
    for group, names in SAMPLES.items():
        for name in names:
            path = args.corpus / group / name
            try:
                rows[group + "/" + name] = probe_file(path)
            except (OSError, ValueError, TypeError, struct.error, PILImage.DecompressionBombError) as exc:
                rows[group + "/" + name] = {"error": str(exc)}
    # Independent picture fixtures named by HSLF TestPictures expectations.
    ppt = rows.get("slideshow/pictures.ppt", {})
    for image, (filename, skip) in zip(ppt.get("pictures", []),
                                     (("clock.jpg", 0), ("tomcat.png", 0), ("santa.wmf", 22),
                                      ("cow.pict", 512), ("wrench.emf", 0))):
        with open(args.corpus / "slideshow" / filename, "rb") as handle:
            reference = handle.read(LIMITS.max_image_bytes + 513)[skip:]
        image["reference"] = filename
        image["reference_payload_equal"] = image["sha256"] == hashlib.sha256(reference).hexdigest()
    vector = rows.get("document/vector_image.doc", {}).get("pictures", [])
    if vector:
        with open(args.corpus / "document" / "vector_image.emf", "rb") as handle:
            reference = handle.read(LIMITS.max_image_bytes + 1)
        vector[0]["reference_payload_equal"] = vector[0]["sha256"] == hashlib.sha256(reference).hexdigest()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
    for key, row in rows.items():
        print(key, row.get("decoded"), row.get("formats"), "warnings", len(row.get("warnings", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
