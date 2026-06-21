"""Structure helpers for legacy Office text streams."""
import re
from typing import Iterable, List

from ..conversion import Provenance
from ..model.document import Paragraph, Section, TextRun
from ..model.table import Cell, Table


def build_structured_section(lines: Iterable[str], source_format: str, section_index: int = 0, slide: int = 0) -> Section:
    provenance = Provenance(source_format=source_format, section=section_index, slide=slide or None)
    section = Section(provenance=provenance)
    normalized = [line.strip() for line in lines if line and line.strip()]
    index = 0
    paragraph_index = 0
    while index < len(normalized):
        line = normalized[index]
        if index + 1 < len(normalized) and _is_heading_underline(normalized[index + 1]):
            heading_level = 1 if normalized[index + 1].startswith("=") else 2
            section.elements.append(
                _paragraph_from_line(
                    f"{'#' * heading_level} {line}",
                    source_format,
                    section_index,
                    slide,
                    paragraph_index,
                )
            )
            paragraph_index += 1
            index += 2
            continue
        if _is_table_line(line):
            table_lines = []
            while index < len(normalized) and _is_table_line(normalized[index]):
                table_lines.append(normalized[index])
                index += 1
            section.elements.append(_table_from_lines(table_lines, source_format, section_index, slide))
            continue
        if _is_key_value_line(line):
            key_value_lines = []
            while index < len(normalized) and _is_key_value_line(normalized[index]):
                key_value_lines.append(normalized[index])
                index += 1
            if len(key_value_lines) > 1:
                section.elements.append(_table_from_key_value_lines(key_value_lines, source_format, section_index, slide))
                continue
            index -= len(key_value_lines)

        paragraph = _paragraph_from_line(line, source_format, section_index, slide, paragraph_index)
        section.elements.append(paragraph)
        paragraph_index += 1
        index += 1
    return section


def _is_table_line(line: str) -> bool:
    return len(_table_parts(line)) > 1


def _table_parts(line: str) -> List[str]:
    if "\t" in line:
        return line.split("\t")
    if "|" in line:
        stripped = line.strip().strip("|")
        parts = [part.strip() for part in stripped.split("|")]
        if len(parts) > 1:
            return parts
    return [line]


def _is_table_separator(parts: List[str]) -> bool:
    return len(parts) > 1 and all(re.fullmatch(r":?-{3,}:?", part or "") for part in parts)


def _is_heading_underline(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 3 and (set(stripped) == {"="} or set(stripped) == {"-"})


def _is_key_value_line(line: str) -> bool:
    return _key_value_parts(line) is not None


def _key_value_parts(line: str):
    if _heading_label_match(line):
        return None
    match = re.match(r"^\s*([^:：\t|]{1,40})\s*[:：]\s*(\S.*)$", line)
    if not match:
        return None
    key = match.group(1).strip()
    value = match.group(2).strip()
    if not key or not value:
        return None
    return [key, value]


def _paragraph_from_line(line: str, source_format: str, section_index: int, slide: int, paragraph_index: int) -> Paragraph:
    heading_level = 0
    text = _normalize_list_marker(line)
    if line.startswith("#"):
        marker = line.split(" ", 1)[0]
        if marker and set(marker) == {"#"} and 1 <= len(marker) <= 6 and len(line) > len(marker):
            heading_level = len(marker)
            text = line[len(marker):].strip()
    else:
        heading_match = _heading_label_match(line)
        if heading_match:
            heading_level, text = heading_match
    provenance = Provenance(
        source_format=source_format,
        section=section_index,
        slide=slide or None,
        paragraph=paragraph_index,
    )
    return Paragraph(
        runs=[TextRun(text=text, provenance=provenance)],
        heading_level=heading_level,
        provenance=provenance,
    )


def _heading_label_match(line: str):
    heading_match = re.match(r"(?i)^(title|heading\s*([1-6]))\s*:\s*(.+)$", line)
    if heading_match:
        return int(heading_match.group(2) or "1"), heading_match.group(3).strip()
    korean_match = re.match(r"^(제목|소제목)\s*:\s*(.+)$", line)
    if korean_match:
        return (2 if korean_match.group(1) == "소제목" else 1), korean_match.group(2).strip()
    return None


def _normalize_list_marker(line: str) -> str:
    match = re.match(r"^\s*[□☐]\s*(.+)$", line)
    if match:
        return f"- [ ] {match.group(1).strip()}"
    match = re.match(r"^\s*[☑☒]\s*(.+)$", line)
    if match:
        return f"- [x] {match.group(1).strip()}"
    match = re.match(r"^\s*\[\s*([xX✓✔])\s*\]\s*(.+)$", line)
    if match:
        return f"- [x] {match.group(2).strip()}"
    match = re.match(r"^\s*\[\s*\]\s*(.+)$", line)
    if match:
        return f"- [ ] {match.group(1).strip()}"
    match = re.match(r"^\s*[•◦‣]\s*(.+)$", line)
    if match:
        return f"- {match.group(1).strip()}"
    match = re.match(r"^\s*(\d{1,3})\)\s*(.+)$", line)
    if match:
        return f"{match.group(1)}. {match.group(2).strip()}"
    match = re.match(r"^\s*\((\d{1,3})\)\s*(.+)$", line)
    if match:
        return f"{match.group(1)}. {match.group(2).strip()}"
    match = re.match(r"^\s*(?:[A-Za-z]|[ivxlcdmIVXLCDM]{2,8})[\.)]\s+(.+)$", line)
    if match:
        return f"- {match.group(1).strip()}"
    return line


def _table_from_lines(lines: List[str], source_format: str, section_index: int, slide: int) -> Table:
    rows_parts = [parts for parts in (_table_parts(line) for line in lines) if not _is_table_separator(parts)]
    if not rows_parts:
        return Table()
    return _table_from_rows(rows_parts, source_format, section_index, slide)


def _table_from_key_value_lines(lines: List[str], source_format: str, section_index: int, slide: int) -> Table:
    rows_parts = [parts for parts in (_key_value_parts(line) for line in lines) if parts]
    return _table_from_rows(rows_parts, source_format, section_index, slide)


def _table_from_rows(rows_parts: List[List[str]], source_format: str, section_index: int, slide: int) -> Table:
    width = max(len(parts) for parts in rows_parts)
    rows = []
    for row_idx, parts in enumerate(rows_parts):
        row = []
        for col_idx in range(width):
            text = parts[col_idx].strip() if col_idx < len(parts) else ""
            provenance = Provenance(
                source_format=source_format,
                section=section_index,
                slide=slide or None,
            )
            paragraph = Paragraph(runs=[TextRun(text=text, provenance=provenance)], provenance=provenance)
            row.append(Cell(paragraphs=[paragraph], provenance=provenance))
        rows.append(row)
    return Table(rows=rows)
