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
    if isinstance(parms, dict) and isinstance(parms.get("Predictor"), int) \
            and parms["Predictor"] > 1:
        # Predictor 미해제 데이터는 바이트 단위로 깨져 있다 — 조용히 깨진
        # 텍스트를 내보내느니 스트림을 건너뛴다
        warnings.append("WARN: PDF Predictor 인코딩은 아직 지원하지 않음 — 해당 스트림 건너뜀")
        return b""

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
    return data


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
