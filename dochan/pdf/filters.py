"""PDF 스트림 필터 해제 — 표준 라이브러리만 사용."""
import base64
import binascii
import zlib
from typing import List

MAX_DECODED_SIZE = 50 * 1024 * 1024

# 이미지 압축 계열 — 텍스트 추출 대상이 아니므로 조용히 빈 값 처리
_IMAGE_FILTERS = {"DCTDecode", "DCT", "JPXDecode", "CCITTFaxDecode", "CCF", "JBIG2Decode"}

_WHITESPACE = b"\x00\t\n\x0c\r "


def decode_stream(stream_dict: dict, raw: bytes, warnings: List[str]) -> bytes:
    """스트림 사전의 /Filter 체인을 적용해 원본 바이트를 해제한다."""
    filters = stream_dict.get("Filter")
    if filters is None:
        return raw
    if not isinstance(filters, list):
        filters = [filters]

    parms = stream_dict.get("DecodeParms") or stream_dict.get("DP")
    predictor = 1
    columns = 1
    colors = 1
    bits = 8
    if isinstance(parms, dict):
        if isinstance(parms.get("Predictor"), int):
            predictor = parms["Predictor"]
        if isinstance(parms.get("Columns"), int) and parms["Columns"] > 0:
            columns = parms["Columns"]
        if isinstance(parms.get("Colors"), int) and parms["Colors"] > 0:
            colors = parms["Colors"]
        if isinstance(parms.get("BitsPerComponent"), int) and parms["BitsPerComponent"] > 0:
            bits = parms["BitsPerComponent"]

    data = raw
    for filt in filters:
        name = str(filt)
        if name in ("FlateDecode", "Fl"):
            data = _flate(data, warnings)
        elif name in ("ASCIIHexDecode", "AHx"):
            data = _ascii_hex(data, warnings)
        elif name in ("ASCII85Decode", "A85"):
            data = _ascii85(data, warnings)
        elif name in _IMAGE_FILTERS:
            return b""
        else:
            warnings.append(f"WARN: 지원하지 않는 PDF 필터: {name}")
            return b""

    if predictor >= 10:  # PNG predictor 계열 — xref 스트림의 사실상 표준
        return _apply_png_predictor(data, columns, colors, bits, warnings)
    if predictor > 1:  # TIFF predictor 2 — 드물고 미지원
        warnings.append("WARN: TIFF Predictor 인코딩은 지원하지 않음 — 해당 스트림 건너뜀")
        return b""
    return data


def _apply_png_predictor(data: bytes, columns: int, colors: int, bits: int,
                         warnings: List[str]) -> bytes:
    bpp = max(1, (colors * bits + 7) // 8)
    row_width = bpp * columns
    stride = row_width + 1  # 행마다 필터 타입 1바이트 선행
    out = bytearray()
    prev = bytearray(row_width)
    pos = 0
    n = len(data)
    while pos < n:
        if n - pos < stride:
            warnings.append("WARN: PNG Predictor 행이 잘림 — 잔여 데이터 무시")
            break
        filter_type = data[pos]
        row = bytearray(data[pos + 1:pos + stride])
        pos += stride
        if filter_type == 0:
            pass
        elif filter_type == 1:  # Sub
            for i in range(bpp, row_width):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(row_width):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(row_width):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(row_width):
                left = row[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                if pa <= pb and pa <= pc:
                    pred = left
                elif pb <= pc:
                    pred = up
                else:
                    pred = up_left
                row[i] = (row[i] + pred) & 0xFF
        else:
            warnings.append(f"WARN: 알 수 없는 PNG Predictor 필터 타입: {filter_type}")
            return b""
        out += row
        prev = row
    return bytes(out)


def _flate(data: bytes, warnings: List[str]) -> bytes:
    try:
        decomp = zlib.decompressobj()
        out = decomp.decompress(data, MAX_DECODED_SIZE)
        if decomp.unconsumed_tail:
            warnings.append("WARN: PDF 스트림이 해제 한도를 초과하여 잘림")
        return out
    except zlib.error as e:
        warnings.append(f"WARN: FlateDecode 실패: {e}")
        return b""


def _ascii_hex(data: bytes, warnings: List[str]) -> bytes:
    text = data.split(b">")[0]
    text = bytes(c for c in text if c not in _WHITESPACE)
    if len(text) % 2:
        text += b"0"
    try:
        return binascii.unhexlify(text)
    except (binascii.Error, ValueError):
        warnings.append("WARN: ASCIIHexDecode 실패")
        return b""


def _ascii85(data: bytes, warnings: List[str]) -> bytes:
    text = bytes(c for c in data if c not in _WHITESPACE)
    if text.startswith(b"<~"):
        text = text[2:]
    if text.endswith(b"~>"):
        text = text[:-2]
    try:
        return base64.a85decode(text)
    except ValueError:
        warnings.append("WARN: ASCII85Decode 실패")
        return b""
