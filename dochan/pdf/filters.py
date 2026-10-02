"""PDF 스트림 필터 해제 — 표준 라이브러리만 사용."""
import base64
import binascii
import zlib
from typing import List, Optional

MAX_DECODED_SIZE = 50 * 1024 * 1024
# Packed samples take up to eight Python decode steps per byte. Bound work
# separately from byte size; return only completed rows on exhaustion.
MAX_PACKED_PREDICTOR_SAMPLES = 1024 * 1024

# 이미지 압축 계열 — 텍스트 추출 대상이 아니므로 조용히 빈 값 처리
_IMAGE_FILTERS = {"DCTDecode", "DCT", "JPXDecode", "CCITTFaxDecode", "CCF", "JBIG2Decode"}

_WHITESPACE = b"\x00\t\n\x0c\r "


class PredictorBudget:
    """문서의 모든 packed TIFF 스트림이 공유하는 샘플 연산 예산."""

    def __init__(self):
        self.remaining_samples = MAX_PACKED_PREDICTOR_SAMPLES


def decode_stream(stream_dict: dict, raw: bytes, warnings: List[str],
                  predictor_budget: Optional[PredictorBudget] = None) -> bytes:
    """스트림 사전의 /Filter 체인을 적용해 원본 바이트를 해제한다."""
    filters = stream_dict.get("Filter")
    if filters is None:
        return raw
    if not isinstance(filters, list):
        filters = [filters]

    parms = stream_dict.get("DecodeParms", stream_dict.get("DP"))
    parameters = parms if isinstance(parms, list) else [parms]
    if predictor_budget is None:
        predictor_budget = PredictorBudget()
    data = raw
    for index, filt in enumerate(filters):
        name = str(filt)
        param = parameters[index] if index < len(parameters) else None
        param = param if isinstance(param, dict) else {}
        if name in ("FlateDecode", "Fl"):
            data = _flate(data, warnings)
        elif name in ("LZWDecode", "LZW"):
            early = param.get("EarlyChange", 1)
            if early not in (0, 1):
                warnings.append("WARN: LZWDecode EarlyChange 값이 잘못됨")
                return b""
            data = _lzw(data, early, warnings)
        elif name in ("ASCIIHexDecode", "AHx"):
            data = _ascii_hex(data, warnings)
        elif name in ("ASCII85Decode", "A85"):
            data = _ascii85(data, warnings)
        elif name in _IMAGE_FILTERS:
            return b""
        else:
            warnings.append(f"WARN: 지원하지 않는 PDF 필터: {name}")
            return b""
        if len(data) > MAX_DECODED_SIZE:
            warnings.append("WARN: PDF 스트림이 해제 한도를 초과하여 잘림")
            return data[:MAX_DECODED_SIZE]
        if name in ("FlateDecode", "Fl", "LZWDecode", "LZW"):
            data = _predictor(data, param, warnings, predictor_budget)
    return data


def _lzw(data: bytes, early: int, warnings: List[str]) -> bytes:
    """ISO 32000-1 §7.4.4: MSB 코드, 9–12비트, Clear/EOD."""
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    width, bitpos, previous = 9, 0, b""
    out = bytearray()
    while bitpos + width <= len(data) * 8:
        bytepos, shift = divmod(bitpos, 8)
        count = (shift + width + 7) // 8
        word = int.from_bytes(data[bytepos:bytepos + count], "big")
        code = (word >> (count * 8 - shift - width)) & ((1 << width) - 1)
        if bitpos == 0 and code != 256:
            warnings.append("WARN: LZWDecode 시작 Clear 코드가 없음")
            return b""
        bitpos += width
        if code == 256:
            table = table[:258]
            width, previous = 9, b""
            continue
        if code == 257:
            return bytes(out)
        if code < len(table):
            entry = table[code]
        elif code == len(table) and previous:
            entry = previous + previous[:1]
        else:
            warnings.append("WARN: LZWDecode 사전 코드가 잘못됨")
            return bytes(out)
        if len(out) + len(entry) > MAX_DECODED_SIZE:
            warnings.append("WARN: LZWDecode 해제 한도를 초과하여 잘림")
            out.extend(entry[:MAX_DECODED_SIZE - len(out)])
            return bytes(out)
        out.extend(entry)
        if previous and len(table) < 4096:
            table.append(previous + entry[:1])
            if width < 12 and len(table) + early == 1 << width:
                width += 1
        previous = entry
    warnings.append("WARN: LZWDecode 코드열이 잘림 (EOD 없음)")
    return bytes(out)


def _predictor(data: bytes, parms: dict, warnings: List[str],
               predictor_budget: PredictorBudget) -> bytes:
    predictor = parms.get("Predictor", 1)
    if predictor == 1:
        return data
    columns, colors, bits = (parms.get("Columns", 1), parms.get("Colors", 1),
                              parms.get("BitsPerComponent", 8))
    if (not isinstance(predictor, int) or predictor not in (2, 10, 11, 12, 13, 14, 15)
            or not isinstance(columns, int) or not isinstance(colors, int)
            or columns <= 0 or colors <= 0 or not isinstance(bits, int)
            or bits not in (1, 2, 4, 8, 16)
            or columns * colors * bits > MAX_DECODED_SIZE * 8):
        warnings.append("WARN: PDF Predictor 매개변수가 잘못되거나 한도를 초과함")
        return b""
    if predictor == 2:
        return _apply_tiff_predictor(data, columns, colors, bits, warnings, predictor_budget)
    return _apply_png_predictor(data, columns, colors, bits, warnings)


def _apply_tiff_predictor(data: bytes, columns: int, colors: int, bits: int,
                          warnings: List[str], predictor_budget: PredictorBudget) -> bytes:
    """행별로 같은 색의 이전 픽셀을 더한다. 패딩은 샘플이 아니다."""
    samples = columns * colors
    row_width = (samples * bits + 7) // 8
    out = bytearray()
    mask = (1 << bits) - 1
    for pos in range(0, len(data), row_width):
        if len(data) - pos < row_width:
            warnings.append("WARN: TIFF Predictor 행이 잘림 — 잔여 데이터 무시")
            break
        if bits < 8:
            if samples > predictor_budget.remaining_samples:
                message = "WARN: TIFF Predictor 연산 한도 초과 — 완성된 행만 반환"
                if message not in warnings:
                    warnings.append(message)
                break
            predictor_budget.remaining_samples -= samples
        row = bytearray(data[pos:pos + row_width])
        if bits == 8:
            for i in range(colors, row_width):
                row[i] = (row[i] + row[i - colors]) & 255
        else:
            # 최대 한 행만 보관한다. 큰 Python 정수로 행 전체를 펼치지 않는다.
            for i in range(colors, samples):
                offset, left_offset = i * bits, (i - colors) * bits
                if bits == 16:
                    at, left = offset // 8, left_offset // 8
                    value = (int.from_bytes(row[at:at + 2], "big") +
                             int.from_bytes(row[left:left + 2], "big")) & mask
                    row[at:at + 2] = value.to_bytes(2, "big")
                else:
                    at, left = offset // 8, left_offset // 8
                    shift, left_shift = 8 - bits - offset % 8, 8 - bits - left_offset % 8
                    value = ((row[at] >> shift) + (row[left] >> left_shift)) & mask
                    row[at] = (row[at] & ~(mask << shift)) | (value << shift)
        out.extend(row)
    return bytes(out)


def _apply_png_predictor(data: bytes, columns: int, colors: int, bits: int,
                         warnings: List[str]) -> bytes:
    bpp = max(1, (colors * bits + 7) // 8)
    row_width = (columns * colors * bits + 7) // 8
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
