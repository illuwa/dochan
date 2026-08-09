"""PDF 이미지 XObject → OCR 가능한 이미지 바이트 추출.

DCTDecode/JPXDecode 스트림은 그 자체가 JPEG/JP2 파일이라 그대로 반환한다.
그 외(무압축·FlateDecode)의 raw 샘플은 Pillow 로 재구성해 PNG 로 만든다.
Pillow(선택 의존성)가 없거나 지원 못 하는 컬러스페이스면 빈 값을 반환한다.
"""
import io
from typing import List, Tuple

from .filters import decode_stream
from .objects import PDFStream

MAX_IMAGE_PIXELS = 40_000_000  # 픽셀 폭탄 방어 (~40MP)


def extract_image_bytes(stream: PDFStream, warnings: List[str]) -> Tuple[bytes, str]:
    """이미지 스트림 → (바이트, 확장자). 실패 시 (b"", "")."""
    d = stream.dictionary
    filters = d.get("Filter")
    filter_list = filters if isinstance(filters, list) else ([filters] if filters else [])
    filter_names = [str(f) for f in filter_list]

    if any(f in ("DCTDecode", "DCT") for f in filter_names):
        return stream.raw, "jpg"
    if any(f in ("JPXDecode",) for f in filter_names):
        return stream.raw, "jp2"
    if any(f in ("CCITTFaxDecode", "CCF", "JBIG2Decode") for f in filter_names):
        return b"", ""  # 팩스/이진 압축 — Pillow 재구성 대상 아님

    try:
        from PIL import Image as PILImage
    except ImportError:
        return b"", ""

    width = _int(d.get("Width"))
    height = _int(d.get("Height"))
    bpc = _int(d.get("BitsPerComponent")) or 8
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS or bpc != 8:
        return b"", ""

    colorspace = _colorspace_name(d.get("ColorSpace"))
    mode, channels = {
        "DeviceRGB": ("RGB", 3), "RGB": ("RGB", 3), "CalRGB": ("RGB", 3),
        "DeviceGray": ("L", 1), "Gray": ("L", 1), "CalGray": ("L", 1),
        "DeviceCMYK": ("CMYK", 4),
    }.get(colorspace, (None, 0))
    if mode is None:
        return b"", ""

    samples = decode_stream(d, stream.raw, warnings)
    expected = width * height * channels
    if len(samples) < expected:
        return b"", ""
    try:
        img = PILImage.frombytes(mode, (width, height), samples[:expected])
        if mode == "CMYK":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "png"
    except Exception:
        return b"", ""


def _colorspace_name(cs) -> str:
    if isinstance(cs, str):
        return str(cs)
    if isinstance(cs, list) and cs:
        return str(cs[0])
    return ""


def _int(value) -> int:
    return value if isinstance(value, int) else 0
