"""Bounded [MS-OLEPS] SummaryInformation title and author reader."""
import struct
from typing import Dict, List

from ..conversion import Provenance
from ..model.document import Paragraph, Section, TextRun
from ..model.header_footer import HeaderFooter
from ..utils.bounded_io import read_ole_stream


SUMMARY_STREAM = "\x05SummaryInformation"
# FMTID_SummaryInformation, GUID F29F85E0-4FF9-1068-AB91-08002B27B3D9
# stored with little-endian Data1, Data2 and Data3 fields.
FMTID_SUMMARY = bytes.fromhex("e0859ff2f94f6810ab9108002b27b3d9")
MAX_SUMMARY_BYTES = 1024 * 1024
MAX_SECTIONS = 16
MAX_PROPERTIES = 1024
MAX_STRING_CHARS = 4096
# [MS-UCODEREF] code pages whose Python codec is not named cp<id>.
CODEPAGE_CODECS = {
    10000: "mac_roman", 10006: "mac_greek", 10007: "mac_cyrillic",
    10029: "mac_latin2", 10079: "mac_iceland", 10081: "mac_turkish",
    1200: "utf-16-le", 20127: "ascii", 32768: "mac_roman",
    32769: "cp1252", 51949: "euc_kr", 54936: "gb18030",
    65001: "utf-8",
}


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
    # [MS-OLEPS] 2.21 defines one or two sections. Keep the older bounded
    # tolerance for extra sections because only the first summary FMTID is read.
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
    if codepage in CODEPAGE_CODECS:
        encoding = CODEPAGE_CODECS[codepage]
    elif 28591 <= codepage <= 28599:
        encoding = "iso8859_%d" % (codepage - 28590)
    else:
        encoding = "cp%d" % codepage
    try:
        "".encode(encoding)
    except LookupError:
        if warn_partial and errors is not None:
            errors.append("WARN: %s unknown SummaryInformation code page %d; using cp1252" % (
                source_format, codepage))
        encoding = "cp1252"
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
        value = raw.decode("utf-16-le" if value_type == 31 else encoding, errors="replace")
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


def read_summary_elements(ole, source_format: str, errors, budget,
                          warn_partial: bool = True) -> List[Paragraph]:
    """Read optional metadata after the caller has accepted or decrypted the body."""
    if not ole.exists(SUMMARY_STREAM):
        return []
    try:
        data = read_ole_stream(ole, SUMMARY_STREAM, max_bytes=MAX_SUMMARY_BYTES,
                               budget=budget)
        if not data:
            return []
        properties = parse_summary_information(data, source_format, errors,
                                               warn_partial=warn_partial)
        return summary_elements(properties, source_format)
    except Exception as exc:
        errors.append("WARN: %s SummaryInformation unavailable: %s" % (source_format, exc))
        return []


def prepend_summary(ole, doc, source_format: str, budget,
                    warn_partial: bool = True) -> None:
    elements = read_summary_elements(ole, source_format, doc.errors, budget,
                                     warn_partial=warn_partial)
    if elements:
        if not doc.sections:
            doc.sections.append(Section())
        existing = doc.sections[0].elements
        index = 0
        if source_format.upper() == "DOC":
            while index < len(existing) and isinstance(existing[index], HeaderFooter) and existing[index].type == "header":
                index += 1
        existing[index:index] = elements
