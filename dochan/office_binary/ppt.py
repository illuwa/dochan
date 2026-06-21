"""Native legacy PPT reader."""
import re
import struct
from typing import List

import olefile

from ..model.document import Document
from .structure import build_structured_section

SLIDE_CONTAINER = 1006
NOTES_CONTAINER = 1008
COMMENTS_CONTAINER = 1200
TEXT_HEADER_ATOM = 3999
TEXT_CHARS_ATOM = 4000
TEXT_BYTES_ATOM = 4008
CSTRING_ATOM = 4026


def _clean_line(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\u00ad", "")
    text = text.replace("\u2011", "-")
    text = _restore_field_results(text)
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    text = re.sub(r"[ \u3000]{2,}", "\t", text)
    return "\t".join(re.sub(r"[^\S\t]+", " ", part).strip() for part in text.split("\t")).strip()


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


def _append_clean_lines(lines: List[str], text: str, heading_level: int = 0):
    text = text.replace("\x0b", "\n").replace("\x0c", "\n")
    for line in re.split(r"[\r\n]+", text):
        cleaned = _clean_line(line)
        if heading_level and cleaned and not cleaned.startswith("#"):
            cleaned = f"{'#' * heading_level} {cleaned}"
        if cleaned:
            lines.append(cleaned)


def _looks_like_record_stream(data: bytes) -> bool:
    if len(data) < 8:
        return False
    _, _, size = struct.unpack_from("<HHI", data, 0)
    return size <= len(data) - 8


def _extract_ppt_text_records(data: bytes, depth: int = 0) -> List[str]:
    if depth > 20:
        return []

    lines: List[str] = []
    offset = 0
    pending_text_type = None
    while offset + 8 <= len(data):
        rec_options, record_type, size = struct.unpack_from("<HHI", data, offset)
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > len(data):
            break
        payload = data[payload_start:payload_end]

        if record_type == TEXT_HEADER_ATOM and len(payload) >= 4:
            pending_text_type = struct.unpack_from("<I", payload, 0)[0]
        elif record_type in (TEXT_CHARS_ATOM, CSTRING_ATOM):
            _append_clean_lines(lines, payload.decode("utf-16-le", errors="ignore"), _heading_level_for_text_type(pending_text_type))
            pending_text_type = None
        elif record_type == TEXT_BYTES_ATOM:
            _append_clean_lines(lines, payload.decode("cp1252", errors="replace"), _heading_level_for_text_type(pending_text_type))
            pending_text_type = None
        elif rec_options & 0x000F == 0x000F or _looks_like_record_stream(payload):
            lines.extend(_extract_ppt_text_records(payload, depth + 1))

        offset = payload_end

    return lines


def _heading_level_for_text_type(text_type) -> int:
    return 1 if text_type in {0, 6} else 0


def _extract_slide_text_records(data: bytes, depth: int = 0) -> List[List[str]]:
    if depth > 20:
        return []

    slides: List[List[str]] = []
    offset = 0
    while offset + 8 <= len(data):
        rec_options, record_type, size = struct.unpack_from("<HHI", data, offset)
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > len(data):
            break
        payload = data[payload_start:payload_end]

        if record_type == SLIDE_CONTAINER:
            lines = _extract_ppt_text_records(payload, depth + 1)
            if lines:
                slides.append(lines)
        elif rec_options & 0x000F == 0x000F or _looks_like_record_stream(payload):
            slides.extend(_extract_slide_text_records(payload, depth + 1))

        offset = payload_end

    return slides


def _extract_slide_and_notes_records(data: bytes, depth: int = 0) -> List[List[str]]:
    if depth > 20:
        return []

    slides: List[List[str]] = []
    offset = 0
    while offset + 8 <= len(data):
        rec_options, record_type, size = struct.unpack_from("<HHI", data, offset)
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > len(data):
            break
        payload = data[payload_start:payload_end]

        if record_type == SLIDE_CONTAINER:
            lines = _extract_ppt_text_records(payload, depth + 1)
            if lines:
                slides.append(lines)
        elif record_type == NOTES_CONTAINER:
            notes = _extract_ppt_text_records(payload, depth + 1)
            if notes:
                if not slides:
                    slides.append([])
                slides[-1].extend(["## Notes"] + notes)
        elif record_type == COMMENTS_CONTAINER:
            comments = _extract_ppt_text_records(payload, depth + 1)
            if comments:
                if not slides:
                    slides.append([])
                slides[-1].extend(["## Comments"] + comments)
        elif rec_options & 0x000F == 0x000F or _looks_like_record_stream(payload):
            nested = _extract_slide_and_notes_records(payload, depth + 1)
            if nested:
                for nested_lines in nested:
                    if slides and _is_supplemental_slide_block(nested_lines):
                        slides[-1].extend(nested_lines)
                    else:
                        slides.append(nested_lines)

        offset = payload_end

    return slides


def _is_supplemental_slide_block(lines: List[str]) -> bool:
    return bool(lines) and lines[0] in {"## Notes", "## Comments"}


def _fallback_text_lines(data: bytes) -> List[str]:
    lines: List[str] = []
    _append_clean_lines(lines, data[:len(data) - (len(data) % 2)].decode("utf-16-le", errors="ignore"))
    if not lines:
        _append_clean_lines(lines, data.decode("cp1252", errors="replace"))
    return lines


def parse_ppt_document_stream(data: bytes) -> Document:
    doc = Document(source_format="ppt")
    slide_lines = _extract_slide_and_notes_records(data)
    if not slide_lines:
        slide_lines = _extract_slide_text_records(data)
    if not slide_lines:
        slide_lines = [_extract_ppt_text_records(data) or _fallback_text_lines(data)]

    for slide_index, lines in enumerate(slide_lines, start=1):
        doc.sections.append(build_structured_section(lines, "ppt", section_index=slide_index - 1, slide=slide_index))
    return doc


class PPTReader:
    format_name = "ppt"
    extensions = (".ppt",)

    def read(self, file_path: str) -> Document:
        try:
            ole = olefile.OleFileIO(file_path)
        except Exception as exc:
            doc = Document(source_format="ppt")
            doc.errors.append(f"ERR: PPT OLE 파일 열기 실패: {exc}")
            return doc

        try:
            if not ole.exists("PowerPoint Document"):
                doc = Document(source_format="ppt")
                doc.errors.append("ERR: PPT PowerPoint Document stream not found")
                return doc
            ppt_data = ole.openstream("PowerPoint Document").read()
            return parse_ppt_document_stream(ppt_data)
        finally:
            ole.close()
