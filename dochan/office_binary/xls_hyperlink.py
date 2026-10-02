"""Bounded internal BIFF8 HLink decoding.

MS-XLS HLink wraps the MS-OSHARED Hyperlink structure after its eight-byte
Ref8U. Internal links carry a location string rather than a moniker. Keep its
spelling intact and prefix ``#``, matching the XLSX cell-text contract.
"""
import struct
from dataclasses import dataclass
from typing import List, Optional


_HLINK_GUID = bytes.fromhex('d0c9ea79f9bace118c8200aa004ba90b')
_MAX_STRING_UNITS = 32767


@dataclass(frozen=True)
class XlsHyperlink:
    target: str
    display: str = ''


def parse_hlink(record_data: bytes, errors: Optional[List[str]] = None) -> Optional[XlsHyperlink]:
    """Decode a location-only HLink, returning None for other link kinds.

    Unrecognized legacy/external payloads remain available to the caller's
    existing URL decoder. Recognized, damaged internal links produce a warning.
    String lengths are UTF-16 code units including the terminating NUL.
    """
    if len(record_data) < 32 or record_data[8:24] != _HLINK_GUID:
        return None
    version, flags = struct.unpack_from('<II', record_data, 24)
    if version != 2 or flags & 0x01 or not flags & 0x08:
        return None
    offset = 32

    def read_string() -> str:
        nonlocal offset
        if offset + 4 > len(record_data):
            raise ValueError('missing string length')
        count = struct.unpack_from('<I', record_data, offset)[0]
        offset += 4
        if not 1 <= count <= _MAX_STRING_UNITS or count > (len(record_data) - offset) // 2:
            raise ValueError('string length out of bounds')
        raw = record_data[offset:offset + 2 * count]
        offset += 2 * count
        if raw[-2:] != b'\0\0':
            raise ValueError('unterminated string')
        return raw[:-2].decode('utf-16le')

    try:
        display = read_string() if flags & 0x10 else ''
        if flags & 0x80:
            read_string()  # Target frame precedes location; it is not link text.
        location = read_string()
    except (ValueError, UnicodeError) as exc:
        if errors is not None:
            warning = 'WARN: XLS hyperlink malformed internal location: ' + str(exc)
            if warning not in errors:
                errors.append(warning)
        return None
    if not location:
        return None
    return XlsHyperlink(target='#' + location, display=display)
