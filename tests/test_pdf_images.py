"""PDF 이미지 XObject 추출 + OCR 테스트."""
import struct
import zlib

import pytest

from dochan.pdf.images import extract_image_bytes
from dochan.pdf.objects import PDFStream

PIL = pytest.importorskip("PIL")
from PIL import Image as _PILImage  # noqa: E402


def _rgb_stream(w, h, color=(200, 30, 30), flate=False):
    raw = bytes(color) * (w * h)
    d = {"Subtype": "Image", "Width": w, "Height": h,
         "ColorSpace": "DeviceRGB", "BitsPerComponent": 8}
    if flate:
        raw = zlib.compress(raw)
        d["Filter"] = "FlateDecode"
    return PDFStream(d, raw)


def test_extract_raw_rgb_image_as_png():
    stream = _rgb_stream(4, 3)
    data, ext = extract_image_bytes(stream, [])
    assert ext == "png"
    img = _PILImage.open(__import__("io").BytesIO(data))
    assert img.size == (4, 3)
    assert img.getpixel((0, 0)) == (200, 30, 30)


def test_extract_flate_rgb_image():
    stream = _rgb_stream(5, 5, color=(10, 20, 30), flate=True)
    data, ext = extract_image_bytes(stream, [])
    img = _PILImage.open(__import__("io").BytesIO(data))
    assert img.size == (5, 5)
    assert img.getpixel((2, 2)) == (10, 20, 30)


def test_dct_stream_returned_as_jpeg_bytes():
    # DCTDecode 는 스트림 원본이 곧 JPEG — 그대로 반환
    jpeg_magic = b"\xff\xd8\xff\xe0stub-jpeg-body"
    stream = PDFStream({"Subtype": "Image", "Filter": "DCTDecode",
                        "Width": 10, "Height": 10}, jpeg_magic)
    data, ext = extract_image_bytes(stream, [])
    assert ext == "jpg"
    assert data == jpeg_magic


def test_unsupported_colorspace_returns_none():
    stream = PDFStream({"Subtype": "Image", "Filter": "CCITTFaxDecode",
                        "Width": 8, "Height": 8}, b"\x00" * 8)
    assert extract_image_bytes(stream, []) == (b"", "")
