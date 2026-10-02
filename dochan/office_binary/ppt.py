"""Native legacy PPT reader."""
import re
import struct
from dataclasses import replace
from typing import List, Optional

import olefile

from ..model.document import Document
from ..utils.bounded_io import (
    BoundedIOError,
    ByteBudget,
    MAX_OLE_DOCUMENT_SIZE,
    MAX_OLE_STREAM_SIZE,
    ResourceLimitError,
    read_ole_stream,
    validate_file_size,
)
from .structure import build_structured_section, is_encrypted_container

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


def _find_next_record_offset(data: bytes, start: int) -> Optional[int]:
    if start >= len(data) - 7:
        return None

    for candidate in range(start, len(data) - 7):
        _, _, size = struct.unpack_from("<HHI", data, candidate)
        if candidate + 8 + size <= len(data):
            return candidate
    return None


def _extract_ppt_text_records(data: bytes, depth: int = 0, recovery_budget=None,
                              recovery_master_ids=()) -> List[str]:
    if depth > 20:
        return []

    lines: List[str] = []
    offset = 0
    pending_text_type = None
    while offset + 8 <= len(data):
        if recovery_budget is not None:
            if recovery_budget[0] <= 0 or recovery_budget[1] <= 0:
                break
            recovery_budget[0] -= 1
        rec_options, record_type, size = struct.unpack_from("<HHI", data, offset)
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > len(data):
            next_offset = _find_next_record_offset(data, payload_start + 1)
            payload_end = next_offset if next_offset is not None else len(data)
        payload = data[payload_start:payload_end]

        if recovery_budget is not None:
            # MainMaster and its outline list contain editing prompts. A notes
            # master is a NotesContainer whose NotesAtom refers to a master ID,
            # rather than an actual slide; do not promote those prompts either.
            master_notes = (record_type == NOTES_CONTAINER and len(payload) >= 12
                            and struct.unpack_from("<H", payload, 2)[0] == 1009
                            and struct.unpack_from("<I", payload, 8)[0] in recovery_master_ids)
            if (record_type == 1016 or master_notes
                    or (record_type == 4080 and rec_options >> 4 == 1)):
                offset = payload_end
                continue

        if record_type == TEXT_HEADER_ATOM and len(payload) >= 4:
            pending_text_type = struct.unpack_from("<I", payload, 0)[0]
        elif record_type in (TEXT_CHARS_ATOM, CSTRING_ATOM) and (recovery_budget is None or record_type != CSTRING_ATOM):
            if recovery_budget is not None:
                payload = payload[:recovery_budget[1] * 2]
                recovery_budget[1] -= len(payload) // 2
            _append_clean_lines(lines, payload.decode("utf-16-le", errors="ignore"), _heading_level_for_text_type(pending_text_type))
            pending_text_type = None
        elif record_type in (SLIDE_CONTAINER, NOTES_CONTAINER, COMMENTS_CONTAINER):
            lines.extend(_extract_ppt_text_records(payload, depth + 1, recovery_budget, recovery_master_ids))
            pending_text_type = None
        elif record_type == TEXT_BYTES_ATOM:
            if recovery_budget is not None:
                payload = payload[:recovery_budget[1]]
                recovery_budget[1] -= len(payload)
            _append_clean_lines(lines, payload.decode("cp1252", errors="replace"), _heading_level_for_text_type(pending_text_type))
            pending_text_type = None
        elif rec_options & 0x000F == 0x000F or _looks_like_record_stream(payload):
            lines.extend(_extract_ppt_text_records(payload, depth + 1, recovery_budget, recovery_master_ids))
            pending_text_type = None
        else:
            pending_text_type = None

        offset = payload_end

    return lines


def _supplement_legacy_text(doc, data, stream_name, max_chars, max_paragraphs, master_ids=()):
    """Keep salvage text separate from slides whose identity cannot be proved.

    Use the legacy scan for unresolved references or an empty damaged tree.
    CString is metadata (font names, tags, etc.), not slide display text. The
    scan has shared record/character bounds and never decodes arbitrary bytes.
    """
    from .ppt_structure import warn

    def key(text):
        text = re.sub(r"^#{1,6}\s+", "", text)
        text = re.sub(r"^[•◦▪▫●○■□☑☐➢]\s+", "", text)
        text = re.sub(r" <[^<>\r\n]+>", "", text)
        return re.sub(r"\s+", " ", text).strip()

    if max_chars <= 0 or max_paragraphs <= 0:
        warn(doc.errors, "legacy text recovery skipped: document output budget exceeded")
        return
    seen = set()
    for paragraph in doc.find_all("paragraph"):
        seen.add(key(paragraph.text))
        seen.update(key(line) for line in paragraph.text.splitlines())
        # Generated numbering is not part of the TextAtom. Strip only runs
        # marked by this renderer, never genuine leading numbers in the text.
        body = ''.join(run.text for run in paragraph.runs
                       if not getattr(run, '_ppt_generated_list_prefix', False))
        seen.add(key(body))
        seen.update(key(line) for line in body.splitlines())
    budget = [100000, min(max_chars, 8 * 1024 * 1024)]
    lines = []
    used = 0
    for line in _extract_ppt_text_records(data[:64 * 1024 * 1024], recovery_budget=budget,
                                          recovery_master_ids=master_ids):
        normalized = key(line)
        if not normalized or normalized in seen:
            continue
        if len(lines) >= max_paragraphs or used + len(line) > max_chars:
            warn(doc.errors, "legacy text recovery output budget exceeded")
            break
        seen.add(normalized)
        lines.append(line)
        used += len(line)
    if min(budget) <= 0 or len(data) > 64 * 1024 * 1024:
        warn(doc.errors, "legacy text recovery scan budget exceeded")
    if lines:
        path = stream_name + "#legacy-recovery"
        doc.sections.append(build_structured_section(lines, "ppt", len(doc.sections), path=path))
        warn(doc.errors, "incomplete structure supplemented with legacy text; slide association unverified")


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
            next_offset = _find_next_record_offset(data, payload_start + 1)
            payload_end = next_offset if next_offset is not None else len(data)
        payload = data[payload_start:payload_end]

        if record_type == SLIDE_CONTAINER:
            lines = _extract_ppt_text_records(payload, depth + 1)
            if lines:
                slides.append(lines)
        elif record_type in {NOTES_CONTAINER, COMMENTS_CONTAINER}:
            nested = _extract_slide_text_records(payload, depth + 1)
            if nested:
                slides.extend(nested)
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
            next_offset = _find_next_record_offset(data, payload_start + 1)
            payload_end = next_offset if next_offset is not None else len(data)
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


def parse_ppt_document_stream(data: bytes, stream_name: str = "PowerPoint Document",
                              current_user: bytes = b"", pictures: bytes = b"") -> Document:
    doc = Document(source_format="ppt")
    if current_user:
        from .ppt_render import read_structured_ppt
        try:
            structured = read_structured_ppt(data, current_user, pictures, stream_name, doc.errors)
            if structured is not None:
                return structured
        except Exception as exc:
            doc.errors.append("WARN: PPT structure recovery failed; using legacy text: %s" % exc)
    slide_lines = _extract_slide_and_notes_records(data)
    if not slide_lines:
        slide_lines = _extract_slide_text_records(data)
    if not slide_lines:
        slide_lines = [_extract_ppt_text_records(data) or _fallback_text_lines(data)]

    for slide_index, lines in enumerate(slide_lines, start=1):
        slide_path = f"{stream_name}#slide{slide_index}"
        doc.sections.append(
            build_structured_section(
                lines,
                "ppt",
                section_index=slide_index - 1,
                slide=slide_index,
                path=slide_path,
            )
        )
        _apply_supplemental_block_paths(doc.sections[-1], slide_path)
    return doc


def _score_ppt_document(document: Document) -> tuple[int, int]:
    return (
        len(document.sections),
        sum(len(section.elements) for section in document.sections),
    )


def _ppt_stream_names(ole) -> list[str]:
    return [name for name in ("PowerPoint Document", "Contents") if ole.exists(name)]


def _apply_supplemental_block_paths(section, base_path: str) -> None:
    current_path = base_path
    supplemental_marker = {2: f"{base_path}#notes", 3: f"{base_path}#comments"}

    for element in section.elements:
        if getattr(element, "heading_level", 0) == 2:
            heading = element.text.strip()
            if heading == "Notes":
                current_path = supplemental_marker[2]
            elif heading == "Comments":
                current_path = supplemental_marker[3]
        _set_element_path(element, current_path)


def _set_element_path(element, path: str) -> None:
    if getattr(element, "provenance", None) is not None:
        element.provenance = replace(element.provenance, path=path)
    if hasattr(element, "runs"):
        for run in getattr(element, "runs"):
            if getattr(run, "provenance", None) is not None:
                run.provenance = replace(run.provenance, path=path)
    if hasattr(element, "paragraphs"):
        for child in getattr(element, "paragraphs"):
            _set_element_path(child, path)
    if hasattr(element, "rows"):
        for row in getattr(element, "rows"):
            for cell in row:
                if hasattr(cell, "provenance") and getattr(cell, "provenance", None) is not None:
                    cell.provenance = replace(cell.provenance, path=path)
                if hasattr(cell, "paragraphs"):
                    for child in getattr(cell, "paragraphs"):
                        _set_element_path(child, path)


class PPTReader:
    format_name = "ppt"
    extensions = (".ppt",)

    def __init__(self, password=None):
        self.password = password

    def read(self, file_path: str) -> Document:
        doc = Document(source_format="ppt")
        try:
            validate_file_size(file_path, MAX_OLE_DOCUMENT_SIZE)
        except ResourceLimitError as exc:
            doc.errors.append(f"ERR: PPT stream validation failed: {exc}")
            return doc

        try:
            ole = olefile.OleFileIO(file_path)
        except Exception as exc:
            doc.errors.append(f"ERR: PPT OLE 파일 열기 실패: {exc}")
            return doc

        stream_budget = ByteBudget(MAX_OLE_DOCUMENT_SIZE)
        try:
            if is_encrypted_container(ole):
                doc.errors.append("ERR: PPT 암호로 보호된 문서입니다")
                return doc
            stream_names = _ppt_stream_names(ole)
            if not stream_names:
                doc.errors.append("ERR: PPT PowerPoint Document stream not found")
                return doc

            best_document = None
            best_score = None
            for stream_name in stream_names:
                try:
                    ppt_data = read_ole_stream(
                        ole,
                        stream_name,
                        max_bytes=MAX_OLE_STREAM_SIZE,
                        budget=stream_budget,
                    )
                except BoundedIOError as exc:
                    fatal_doc = Document(source_format="ppt")
                    fatal_doc.errors.append(
                        f"ERR: PPT stream validation failed: {exc}"
                    )
                    return fatal_doc
                except Exception as exc:
                    doc.errors.append(f"ERR: PPT {stream_name} stream read 실패: {exc}")
                    continue

                try:
                    auxiliary = {}
                    if stream_name == "PowerPoint Document" and ole.exists("Current User"):
                        for name in ("Current User", "Pictures"):
                            if ole.exists(name):
                                try:
                                    auxiliary[name] = read_ole_stream(
                                        ole, name, max_bytes=MAX_OLE_STREAM_SIZE, budget=stream_budget,
                                    )
                                except Exception as exc:
                                    doc.errors.append("WARN: PPT %s stream unavailable: %s" % (name, exc))
                    from ..crypto.ppt import decrypt_presentation
                    try:
                        ppt_data, pictures = decrypt_presentation(
                            ppt_data, auxiliary.get("Current User", b""),
                            auxiliary.get("Pictures", b""), self.password,
                        )
                    except ValueError as exc:
                        doc.errors.append("ERR: %s" % exc)
                        return doc
                    candidate = parse_ppt_document_stream(
                        ppt_data, stream_name, auxiliary.get("Current User", b""), pictures,
                    )
                except Exception as exc:
                    doc.errors.append(f"ERR: PPT {stream_name} stream 파싱 실패: {exc}")
                    continue

                score = _score_ppt_document(candidate)
                if best_document is None or score > best_score:
                    best_document = candidate
                    best_score = score

            if best_document is not None:
                if doc.errors:
                    best_document.errors.extend(doc.errors)
                return best_document

            if not doc.errors:
                doc.errors.append("ERR: PPT 파서를 사용할 수 있는 유효한 스트림이 없습니다")

            return doc
        except Exception as exc:
            doc.errors.append(f"ERR: PPT 파싱 중 오류: {exc}")
            return doc
        finally:
            ole.close()
