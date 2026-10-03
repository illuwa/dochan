"""BIFF8 cell note text from Obj, TxO and Continue records."""
import struct


MAX_NOTE_CHARS = 32768
MAX_SHEET_NOTE_CHARS = 1000000
MAX_NOTE_OBJECTS = 10000


def comment_object_id(payload):
    """Return ftCmo.id when the Obj is a cell note (object type 0x19)."""
    if len(payload) < 10:
        return None
    subrecord, length, object_type, object_id = struct.unpack_from("<HHHH", payload)
    if subrecord != 0x0015 or length < 6 or length + 4 > len(payload) or object_type != 0x0019:
        return None
    return object_id


def read_txo_text(payload, records):
    """Read cchText characters; the next Continue belongs to formatting after that."""
    if len(payload) < 14:
        return "", None, "truncated TxO header"
    char_count = struct.unpack_from("<H", payload, 10)[0]
    if char_count > MAX_NOTE_CHARS:
        return "", None, "TxO text length limit exceeded"
    if char_count == 0:
        return "", None, None
    parts = []
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
        parts.append(raw.decode("utf-16-le" if wide else "latin1", errors="replace"))
        remaining -= count
    text = "".join(parts).replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
    return text, None, None
