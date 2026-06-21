"""Native legacy DOC reader."""
import re
import struct
from typing import List, Optional

import olefile

from ..model.document import Document
from .structure import build_structured_section

SECTION_BREAK = "\u241c"
FC_CLX_OFFSET = 0x01A2
LCB_CLX_OFFSET = 0x01A6


def _clean_text_lines(text: str) -> List[str]:
    text = text.replace("\x00", "")
    text = text.replace("\u00ad", "")
    text = text.replace("\u2011", "-")
    text = _restore_field_results(text)
    text = text.replace("\x0b", "\n")
    text = text.replace("\x0c", f"\n{SECTION_BREAK}\n")
    text = text.replace("\x07", "\t")
    text = re.sub(r"[\x01-\x06\x08\x0e-\x1f]+", " ", text)
    lines = []
    for line in re.split(r"[\r\n]+", text):
        line = re.sub(r"[ \u3000]{2,}", "\t", line)
        cleaned = "\t".join(re.sub(r"[^\S\t]+", " ", part).strip() for part in line.split("\t")).strip()
        cleaned = cleaned.rstrip("\t")
        if cleaned:
            lines.append(cleaned)
    return lines


def _restore_hyperlink_fields(text: str) -> str:
    def replace(match):
        anchor = (match.group("quoted_anchor") or match.group("bare_anchor") or "").strip()
        url = f"#{anchor}" if anchor else (match.group("quoted_url") or match.group("bare_url") or "").strip()
        display = re.sub(r"\s+", " ", match.group("display")).strip()
        return f"{display} <{url}>" if display else url

    pattern = re.compile(
        r'\x13\s*HYPERLINK\s+(?:\\l\s+(?:"(?P<quoted_anchor>[^"]+)"|(?P<bare_anchor>\S+))|(?:"(?P<quoted_url>[^"]+)"|(?P<bare_url>\S+)))[^\x14]*\x14(?P<display>.*?)\x15',
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(replace, text)


def _restore_field_results(text: str) -> str:
    text = _restore_hyperlink_fields(text)
    return re.sub(
        r"\x13[^\x14\x15]*\x14(.*?)\x15",
        lambda match: re.sub(r"\s+", " ", match.group(1)).strip(),
        text,
        flags=re.DOTALL,
    )


def _should_keep_line(line: str) -> bool:
    return len(line) > 1 or line == SECTION_BREAK or line.isdigit()


def _split_sections(lines: List[str]) -> List[List[str]]:
    sections: List[List[str]] = [[]]
    for line in lines:
        if line == SECTION_BREAK:
            if sections[-1]:
                sections.append([])
            continue
        sections[-1].append(line)
    return [section for section in sections if section]


def _extract_utf16_lines(data: bytes) -> List[str]:
    data = _fib_text_range(data)
    even_data = data[:len(data) - (len(data) % 2)]
    if not even_data:
        return []
    decoded = even_data.decode("utf-16-le", errors="ignore")
    lines = _clean_text_lines(decoded)
    return [line for line in lines if _should_keep_line(line)]


def _extract_latin_lines(data: bytes) -> List[str]:
    data = _fib_text_range(data)
    decoded = data.decode("cp1252", errors="replace")
    lines = _clean_text_lines(decoded)
    return [line for line in lines if _should_keep_line(line)]


def _line_quality(lines: List[str]) -> int:
    if not lines:
        return 0
    text = "\n".join(line for line in lines if line != SECTION_BREAK)
    ascii_visible = sum(1 for char in text if char.isascii() and (char.isalnum() or char in " \t.,:;!?-_/()[]"))
    unicode_visible = sum(1 for char in text if not char.isascii() and (char.isalpha() or char.isdigit()))
    replacement_penalty = text.count("\ufffd") * 10
    return ascii_visible * 2 + unicode_visible * 3 + len(lines) * 12 - replacement_penalty


def _likely_utf16(data: bytes) -> bool:
    sample = _fib_text_range(data)[: min(len(_fib_text_range(data)), 512)]
    if len(sample) < 4:
        return False
    even_nulls = sample[1::2].count(0)
    odd_nulls = sample[::2].count(0)
    pairs = max(1, len(sample) // 2)
    return even_nulls / pairs > 0.25 or odd_nulls / pairs > 0.25


def _fib_text_range(data: bytes) -> bytes:
    if len(data) < 0x20:
        return data
    fc_min = struct.unpack_from("<I", data, 0x18)[0]
    fc_mac = struct.unpack_from("<I", data, 0x1C)[0]
    if 0 < fc_min < fc_mac <= len(data):
        candidate = data[fc_min:fc_mac]
        if _looks_like_text(candidate):
            return candidate
    return data


def _extract_piece_table_lines(word_data: bytes, table_data: Optional[bytes]) -> List[str]:
    if not table_data or len(word_data) < LCB_CLX_OFFSET + 4:
        return []
    fc_clx = struct.unpack_from("<I", word_data, FC_CLX_OFFSET)[0]
    lcb_clx = struct.unpack_from("<I", word_data, LCB_CLX_OFFSET)[0]
    if lcb_clx <= 0 or fc_clx + lcb_clx > len(table_data):
        return []
    text = _extract_clx_text(word_data, table_data[fc_clx:fc_clx + lcb_clx])
    lines = _clean_text_lines(text)
    return [line for line in lines if _should_keep_line(line)]


def _extract_clx_text(word_data: bytes, clx: bytes) -> str:
    offset = 0
    pcdt_segments: List[bytes] = []
    while offset < len(clx):
        marker = clx[offset]
        offset += 1
        if marker == 0x01:
            if offset + 2 > len(clx):
                return ""
            size = struct.unpack_from("<H", clx, offset)[0]
            offset += 2 + size
            continue
        if marker != 0x02 or offset + 4 > len(clx):
            return ""
        size = struct.unpack_from("<I", clx, offset)[0]
        offset += 4
        segment = clx[offset:offset + size]
        if len(segment) < size:
            return ""
        pcdt_segments.append(segment)
        offset += size

    return "".join(_extract_piece_table_text(word_data, segment) for segment in pcdt_segments)


def _extract_piece_table_text(word_data: bytes, pcdt: bytes) -> str:
    if len(pcdt) < 16 or (len(pcdt) - 4) % 12:
        return ""
    piece_count = (len(pcdt) - 4) // 12
    cp_count = piece_count + 1
    cp_end = cp_count * 4
    if cp_end + piece_count * 8 > len(pcdt):
        return ""
    cps = [struct.unpack_from("<I", pcdt, index * 4)[0] for index in range(cp_count)]
    text_parts = []
    for index in range(piece_count):
        char_count = cps[index + 1] - cps[index]
        if char_count <= 0:
            continue
        pcd_offset = cp_end + index * 8
        fc_encoded = struct.unpack_from("<I", pcdt, pcd_offset + 2)[0]
        if fc_encoded & 0x40000000:
            file_offset = (fc_encoded & 0x3FFFFFFF) >> 1
            raw = word_data[file_offset:file_offset + char_count]
            text_parts.append(raw.decode("cp1252", errors="replace"))
        elif fc_encoded & 0x01:
            file_offset = fc_encoded >> 1
            raw = word_data[file_offset:file_offset + char_count]
            text_parts.append(raw.decode("cp1252", errors="replace"))
        else:
            file_offset = fc_encoded
            raw = word_data[file_offset:file_offset + char_count * 2]
            text_parts.append(raw.decode("utf-16-le", errors="replace"))
    return "".join(text_parts)


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[: min(len(data), 256)]
    decoded = sample[:len(sample) - (len(sample) % 2)].decode("utf-16-le", errors="ignore")
    visible = sum(1 for char in decoded if char.isprintable() or char in "\r\n\t")
    return visible >= max(1, len(decoded) // 2)


def parse_doc_word_stream(data: bytes, table_data: Optional[bytes] = None) -> Document:
    doc = Document(source_format="doc")
    lines = _extract_piece_table_lines(data, table_data)
    if not lines:
        utf16_lines = _extract_utf16_lines(data)
        latin_lines = _extract_latin_lines(data)
        if _likely_utf16(data):
            lines = utf16_lines
        else:
            lines = utf16_lines if _line_quality(utf16_lines) >= _line_quality(latin_lines) else latin_lines

    for section_index, section_lines in enumerate(_split_sections(lines)):
        section_path = f"WordDocument#section{section_index + 1}"
        doc.sections.append(
            build_structured_section(
                section_lines,
                "doc",
                section_index=section_index,
                path=section_path,
            )
        )
    return doc


class DOCReader:
    format_name = "doc"
    extensions = (".doc",)

    def _table_stream_names(self, ole, word_data: bytes) -> List[str]:
        preferred = "0Table"
        if len(word_data) > 0x0B:
            flags = struct.unpack_from("<H", word_data, 0x0A)[0]
            if flags & 0x0200:
                preferred = "1Table"
        names = [preferred, "1Table" if preferred == "0Table" else "0Table"]
        return [name for name in names if ole.exists(name)]

    def read(self, file_path: str) -> Document:
        try:
            ole = olefile.OleFileIO(file_path)
        except Exception as exc:
            doc = Document(source_format="doc")
            doc.errors.append(f"ERR: DOC OLE 파일 열기 실패: {exc}")
            return doc

        try:
            if not ole.exists("WordDocument"):
                doc = Document(source_format="doc")
                doc.errors.append("ERR: DOC WordDocument stream not found")
                return doc
            word_data = ole.openstream("WordDocument").read()
            table_data = None
            for table_name in self._table_stream_names(ole, word_data):
                table_data = ole.openstream(table_name).read()
                break
            return parse_doc_word_stream(word_data, table_data)
        finally:
            ole.close()
