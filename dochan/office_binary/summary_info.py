"""Bounded [MS-OLEPS] SummaryInformation title and author reader."""
import struct
from typing import Dict, List

from ..conversion import Provenance
from ..model.document import Paragraph, Section, TextRun
from ..utils.bounded_io import read_ole_stream


SUMMARY_STREAM = "\x05SummaryInformation"
# FMTID_SummaryInformation, GUID F29F85E0-4FF9-1068-AB91-08002B27B3D9
# stored with little-endian Data1, Data2 and Data3 fields.
FMTID_SUMMARY = bytes.fromhex("e0859ff2f94f6810ab9108002b27b3d9")
MAX_SUMMARY_BYTES = 1024 * 1024
MAX_SECTIONS = 16
MAX_PROPERTIES = 1024
MAX_STRING_CHARS = 4096


def parse_summary_information(data: bytes, source_format: str, errors=None,
                              warn_partial: bool = True) -> Dict[str, str]:
    """Return the section-zero title/creator; reject a non-summary property set."""
    def invalid():
        if errors is not None:
            errors.append("WARN: %s malformed SummaryInformation ignored" % source_format)
        return {}

    if (len(data) < 48 or len(data) > MAX_SUMMARY_BYTES
            or data[:2] != b"\xfe\xff"):
        return invalid()
    section_count = struct.unpack_from("<I", data, 24)[0]
    if (not 1 <= section_count <= MAX_SECTIONS
            or 28 + 20 * section_count > len(data)
            or data[28:44] != FMTID_SUMMARY):
        return invalid()
    section_offset = struct.unpack_from("<I", data, 44)[0]
    if section_offset < 28 + 20 * section_count or section_offset + 8 > len(data):
        return invalid()
    section_size, property_count = struct.unpack_from("<II", data, section_offset)
    if (section_size < 8 or section_offset + section_size > len(data)
            or property_count > MAX_PROPERTIES or 8 + property_count * 8 > section_size):
        return invalid()
    end = section_offset + section_size
    table_end = 8 + property_count * 8
    offsets = {}
    malformed = False
    for index in range(property_count):
        identifier, relative = struct.unpack_from("<II", data, section_offset + 8 + index * 8)
        if identifier in (1, 2, 4):
            if table_end <= relative <= section_size - 4:
                offsets[identifier] = section_offset + relative
            else:
                malformed = True
    codepage = 1252
    if 1 in offsets:
        offset = offsets[1]
        if offset + 6 <= end and struct.unpack_from("<H", data, offset)[0] == 2:
            codepage = struct.unpack_from("<H", data, offset + 4)[0]
        else:
            malformed = True
    result = {}
    for identifier, key in ((2, "title"), (4, "creator")):
        offset = offsets.get(identifier)
        if offset is None:
            continue
        if offset + 8 > end:
            malformed = True
            continue
        value_type = struct.unpack_from("<H", data, offset)[0]
        count = struct.unpack_from("<I", data, offset + 4)[0]
        if value_type not in (30, 31) or count > MAX_STRING_CHARS:
            malformed = True
            continue
        byte_count = count * (2 if value_type == 31 else 1)
        if offset + 8 + byte_count > end:
            malformed = True
            continue
        raw = data[offset + 8:offset + 8 + byte_count]
        if value_type == 31 or codepage == 1200:
            encoding = "utf-16-le"
        else:
            encoding = ("mac_roman" if codepage in (10000, 32768)
                        else "cp1252" if codepage == 32769 else "cp%d" % codepage)
        try:
            value = raw.decode(encoding, errors="replace")
        except LookupError:
            value = raw.decode("cp1252", errors="replace")
        value = value.split("\x00", 1)[0].strip()
        if value:
            result[key] = value
    if malformed and warn_partial and errors is not None:
        errors.append("WARN: %s malformed SummaryInformation property ignored" % source_format)
    return result


def summary_elements(properties: Dict[str, str], source_format: str) -> List[Paragraph]:
    provenance = Provenance(source_format=source_format.lower(), path=SUMMARY_STREAM)
    elements = []
    if properties.get("title"):
        elements.append(Paragraph(runs=[TextRun(properties["title"])], heading_level=1,
                                  provenance=provenance))
    if properties.get("creator"):
        elements.append(Paragraph(runs=[TextRun("Author: " + properties["creator"])],
                                  provenance=provenance))
    return elements


def read_summary_elements(ole, source_format: str, errors, budget) -> List[Paragraph]:
    """Read optional metadata after the caller has accepted or decrypted the body."""
    if not ole.exists(SUMMARY_STREAM):
        return []
    try:
        data = read_ole_stream(ole, SUMMARY_STREAM, max_bytes=MAX_SUMMARY_BYTES,
                               budget=budget)
        properties = parse_summary_information(data, source_format, errors)
        return summary_elements(properties, source_format)
    except Exception as exc:
        errors.append("WARN: %s SummaryInformation unavailable: %s" % (source_format, exc))
        return []


def prepend_summary(ole, doc, source_format: str, budget) -> None:
    elements = read_summary_elements(ole, source_format, doc.errors, budget)
    if elements:
        if not doc.sections:
            doc.sections.append(Section())
        doc.sections[0].elements[:0] = elements
