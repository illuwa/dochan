"""BIFF8 note and drawing text from Obj, TxO and Continue records."""
import struct


MAX_NOTE_CHARS = 32768
MAX_SHEET_NOTE_CHARS = 1000000
MAX_DRAWING_OBJECTS = 10000


def object_header(payload):
    """Return the ftCmo object type and id from a bounded Obj subrecord."""
    if len(payload) < 10:
        return None
    subrecord, length, object_type, object_id = struct.unpack_from("<HHHH", payload)
    if subrecord != 0x0015 or length < 6 or length + 4 > len(payload):
        return None
    return object_type, object_id


def read_txo_text(payload, records, normalize_lines=False):
    """Read cchText characters; the next Continue belongs to formatting after that.

    Notes retain line breaks; drawing text follows XLSX paragraph normalization.
    """
    if len(payload) < 14:
        return "", None, "truncated TxO header"
    char_count = struct.unpack_from("<H", payload, 10)[0]
    if char_count > MAX_NOTE_CHARS:
        return "", None, "TxO text length limit exceeded"
    if char_count == 0:
        return "", None, None
    # UTF-16LE 로 모아 한 번에 풀어야 Continue 경계에서 갈린 서로게이트 쌍이 깨지지 않는다.
    encoded = bytearray()
    remaining = char_count
    while remaining:
        item = next(records, None)
        if item is None:
            return "", None, "truncated TxO text"
        if item[1] != 0x003C:
            return "", item, "truncated TxO text"
        data = item[2]
        if not data or data[0] & ~1:
            return "", None, "invalid TxO Continue encoding"
        wide = bool(data[0] & 1)
        width = 2 if wide else 1
        available = (len(data) - 1) // width
        if not available:
            return "", None, "empty TxO Continue text"
        count = min(remaining, available)
        raw = data[1:1 + count * width]
        encoded += raw if wide else raw.decode("latin1").encode("utf-16-le")
        remaining -= count
    # 줄바꿈은 XLSX 메모·XLS 셀처럼 \n 으로 보존한다(Markdown 렌더러가 표 안에서 공백으로 바꾼다).
    text = bytes(encoded).decode("utf-16-le", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if normalize_lines:
        text = "\n".join(line for line in (part.strip() for part in text.split("\n")) if line)
    return text, None, None
