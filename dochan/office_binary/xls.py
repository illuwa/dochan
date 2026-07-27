"""Native XLS BIFF reader."""
from datetime import date, timedelta
import re
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import olefile

from .structure import is_encrypted_container
from ..conversion import Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.table import Cell, Table

# BIFF 의 DIMENSION/ROW 레코드는 생성기가 주장하는 값이라 신뢰할 수 없다.
# 그대로 믿으면 1KB 파일로 수천만 셀을 만들게 된다. 다만 실제 셀이 뒷받침하는 격자는
# 정당한 데이터이므로(실측: 27만 셀이 빽빽이 찬 시트가 존재한다) 두 기준을 나눠 쓴다.
# 상한은 파싱 속도가 아니라 출력 직렬화 비용이 결정한다. 실측상 셀 45만 개면
# to_json 하나에 26초가 걸린다(셀마다 dict 를 만들기 때문). 30만을 절대 상한으로 둔다.
MAX_SHEET_CELLS = 300_000
SPARSE_GRID_FACTOR = 4           # 격자가 내용 있는 셀 수의 이 배를 넘으면 대부분이 빈 칸이다
MAX_SPARSE_GRID_CELLS = 30_000   # 내용이 넓게 흩어진 격자는 더 공격적으로 자른다
MAX_WORKBOOK_CELLS = 600_000     # 워크북 전체 총량. 시트를 여럿 두는 우회를 막는다
MAX_SHEET_COLS = 256          # BIFF8 의 열 상한
MAX_RANGE_FILL_CELLS = 100_000  # MERGEDCELLS/HLINK 가 선언한 범위로 채울 수 있는 총 셀 수
MAX_EMPTY_GRID_CELLS = 1_000     # 내용 없는 격자를 표로 만들 최대 크기


@dataclass
class _SheetInfo:
    name: str
    offset: int
    visibility: int = 0
    cells: Dict[Tuple[int, int], str] = field(default_factory=dict)
    hyperlinks: Dict[Tuple[int, int], str] = field(default_factory=dict)
    comments: Dict[Tuple[int, int], str] = field(default_factory=dict)
    header: str = ""
    footer: str = ""
    merged_ranges: List[Tuple[int, int, int, int]] = field(default_factory=list)
    row_indices: Set[int] = field(default_factory=set)
    col_indices: Set[int] = field(default_factory=set)
    dimension: Optional[Tuple[int, int, int, int]] = None


@dataclass
class _DefinedName:
    name: str
    tokens: bytes = b""


def _cell_ref(row: int, col: int) -> str:
    letters = ""
    value = col + 1
    while value:
        value, rem = divmod(value - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return f"{letters}{row + 1}"


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


_BIFF_ERROR_NAMES = {
    0x00: "#NULL!",
    0x07: "#DIV/0!",
    0x0F: "#VALUE!",
    0x17: "#REF!",
    0x1D: "#NAME?",
    0x24: "#NUM!",
    0x2A: "#N/A",
}


def _format_biff_error(value: int) -> str:
    return _BIFF_ERROR_NAMES.get(value, f"#ERR{value}")


def _format_number_with_format(value: float, format_string: str = "", date_1904: bool = False) -> str:
    normalized = format_string.lower()
    if _is_date_format(normalized):
        return _excel_serial_to_date(value, date_1904=date_1904)
    if "%" in normalized:
        formatted = _format_number(value * 100)
        return f"{formatted}%"
    if "$" in normalized:
        return f"${value:,.2f}"
    if "," in normalized and "0" in normalized:
        if "." in normalized:
            decimals = len(normalized.rsplit(".", 1)[1].replace("0", "").replace("#", ""))
            return f"{value:,.{decimals}f}"
        return f"{value:,.0f}"
    return _format_number(value)


def _decode_rk(raw: int) -> float:
    value = raw >> 2
    if raw & 0x02:
        if value & 0x20000000:
            value -= 0x40000000
        decoded = float(value)
    else:
        packed = (raw & 0xFFFFFFFC).to_bytes(4, "little") + b"\x00\x00\x00\x00"
        decoded = struct.unpack("<d", packed)[0]
    if raw & 0x01:
        decoded /= 100
    return decoded


def _is_date_format(normalized: str) -> bool:
    return any(marker in normalized for marker in ("m/d", "d/m", "yyyy", "yy")) and not any(token in normalized for token in ("h", "s"))


def _excel_serial_to_date(value: float, date_1904: bool = False) -> str:
    # NaN/inf 는 int() 에서 ValueError/OverflowError 가 나고, 지나치게 큰 값은
    # timedelta 에서 OverflowError 가 난다. 어느 쪽이든 원본 숫자를 그대로 돌려준다.
    if value != value or value in (float("inf"), float("-inf")):
        return _format_number(value)
    try:
        serial = int(value)
    except (ValueError, OverflowError):
        return _format_number(value)
    if serial >= 60:
        serial -= 1
    # date + timedelta 의 실제 한계는 상수로 가늠하지 말고 예외로 잡는다.
    # 셀 하나가 워크북 전체를 날리면 안 된다.
    try:
        if date_1904:
            return (date(1904, 1, 1) + timedelta(days=serial)).isoformat()
        return (date(1899, 12, 31) + timedelta(days=serial)).isoformat()
    except (OverflowError, ValueError):
        return _format_number(value)


def _read_short_string(data: bytes, offset: int = 0) -> Tuple[str, int]:
    if offset + 3 > len(data):
        return "", len(data)
    char_count = struct.unpack_from("<H", data, offset)[0]
    flags = data[offset + 2]
    offset += 3
    rich_text_runs = 0
    extension_size = 0
    if flags & 0x08:
        if offset + 2 > len(data):
            return "", len(data)
        rich_text_runs = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    if flags & 0x04:
        if offset + 4 > len(data):
            return "", len(data)
        extension_size = struct.unpack_from("<I", data, offset)[0]
        offset += 4
    is_utf16 = flags & 0x01
    byte_count = char_count * (2 if is_utf16 else 1)
    raw = data[offset:offset + byte_count]
    offset += byte_count
    if is_utf16:
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("cp1252", errors="replace")
    offset += rich_text_runs * 4 + extension_size
    return text, min(offset, len(data))


def _read_biff8_label_text(data: bytes, offset: int = 0) -> str:
    if offset + 3 > len(data):
        return ""
    char_count = struct.unpack_from("<H", data, offset)[0]
    flags = data[offset + 2]
    byte_count = char_count * (2 if flags & 0x01 else 1)
    if offset + 3 + byte_count > len(data):
        raw = data[offset + 2:offset + 2 + char_count]
        return raw.decode("cp1252", errors="replace")
    text, _ = _read_short_string(data, offset)
    return text


def _read_biff_label_text(data: bytes, offset: int = 0) -> str:
    if offset >= len(data):
        return ""
    char_count = data[offset]
    raw = data[offset + 1:offset + 1 + char_count]
    return raw.decode("cp1252", errors="replace")


def _read_formula_string_result_text(record_type: int, data: bytes) -> str:
    if record_type == 0x0007 and data and data[0] == len(data) - 1:
        return _read_biff_label_text(data)
    return _read_biff8_label_text(data)


def _read_boundsheet_name(data: bytes) -> str:
    if len(data) < 8:
        return "Sheet"
    name_len = data[6]
    flags = data[7]
    raw = data[8:]
    if flags & 0x01:
        return raw[:name_len * 2].decode("utf-16-le", errors="replace")
    return raw[:name_len].decode("cp1252", errors="replace")


def _read_boundsheet_visibility(data: bytes) -> int:
    if len(data) < 6:
        return 0
    return struct.unpack_from("<H", data, 4)[0] & 0x0003


def _iter_records(data: bytes):
    offset = 0
    while offset + 4 <= len(data):
        record_type, size = struct.unpack_from("<HH", data, offset)
        payload_start = offset + 4
        payload_end = payload_start + size
        if payload_end > len(data):
            payload_end = len(data)
            next_offset = _recover_next_record_offset(data, payload_start + 1)
            if next_offset is not None and next_offset <= payload_end:
                yield offset, record_type, data[payload_start:next_offset]
                offset = next_offset
                continue
            yield offset, record_type, data[payload_start:payload_end]
            break
        yield offset, record_type, data[payload_start:payload_end]
        offset = payload_end


def _recover_next_record_offset(data: bytes, start: int) -> Optional[int]:
    if start >= len(data) - 3:
        return None

    for candidate in range(start, len(data) - 3):
        if candidate + 4 > len(data):
            return None
        next_record_type, next_size = struct.unpack_from("<HH", data, candidate)
        if next_record_type == 0:
            continue
        if candidate + 4 + next_size <= len(data):
            return candidate
    return None


def parse_biff_workbook(data: bytes, workbook_stream: str = "Workbook") -> Document:
    doc = Document(source_format="xls")
    normalized_stream = workbook_stream or "Workbook"
    sheets: List[_SheetInfo] = []
    shared_strings: List[str] = []
    formats: Dict[int, str] = {}
    xf_formats: List[int] = []
    external_sheets: List[Tuple[int, int]] = []
    defined_name_records: List[_DefinedName] = []
    date_1904 = False

    records = list(_iter_records(data))
    index = 0
    while index < len(records):
        offset, record_type, record_data = records[index]
        if record_type == 0x0085 and len(record_data) >= 8:  # BOUNDSHEET
            sheet_offset = struct.unpack_from("<I", record_data, 0)[0]
            sheets.append(
                _SheetInfo(
                    name=_read_boundsheet_name(record_data),
                    offset=sheet_offset,
                    visibility=_read_boundsheet_visibility(record_data),
                )
            )
        elif record_type == 0x00FC and len(record_data) >= 8:  # SST
            sst_segments = [record_data]
            while index + 1 < len(records) and records[index + 1][1] == 0x003C:  # CONTINUE
                index += 1
                sst_segments.append(records[index][2])
            shared_strings = _parse_sst_segments(sst_segments)
        elif record_type == 0x0017 and len(record_data) >= 2:  # EXTERNSHEET
            external_sheets = _parse_externsheet(record_data)
        elif record_type == 0x0018 and len(record_data) >= 15:  # NAME
            defined_name = _read_name_record(record_data)
            if defined_name.name:
                defined_name_records.append(defined_name)
        elif record_type == 0x0022 and len(record_data) >= 2:  # DATEMODE
            date_1904 = bool(struct.unpack_from("<H", record_data, 0)[0])
        elif record_type == 0x041E and len(record_data) >= 5:  # FORMAT
            format_index = struct.unpack_from("<H", record_data, 0)[0]
            formats[format_index] = _read_biff8_label_text(record_data, 2)
        elif record_type == 0x00E0 and len(record_data) >= 4:  # XF
            xf_formats.append(struct.unpack_from("<H", record_data, 2)[0])
        index += 1

    if not sheets:
        sheets.append(_SheetInfo(name="Sheet1", offset=0))

    sheets = [sheet for sheet in sheets if 0 <= sheet.offset < len(data)]
    if not sheets:
        sheets.append(_SheetInfo(name="Sheet1", offset=0))

    unique_sheets = []
    seen_offsets = set()
    for sheet in sheets:
        if sheet.offset not in seen_offsets:
            seen_offsets.add(sheet.offset)
            unique_sheets.append(sheet)

    sorted_sheets = sorted(unique_sheets, key=lambda sheet: sheet.offset)
    sheet_names = [sheet.name for sheet in sorted_sheets]
    defined_names = [defined_name.name for defined_name in defined_name_records]
    defined_name_elements = _defined_name_elements(
        defined_name_records,
        external_sheets,
        sheet_names,
        defined_names,
        path=normalized_stream,
    )
    for index, sheet in enumerate(sorted_sheets):
        start = sheet.offset
        end = len(data)
        for next_sheet in sorted_sheets[index + 1 :]:
            if next_sheet.offset > start:
                end = next_sheet.offset
                break
        _parse_sheet_records(
            data[start:end],
            sheet,
            shared_strings,
            formats,
            xf_formats,
            external_sheets,
            sheet_names,
            defined_names,
            date_1904,
        )

    # 워크북 전체가 실체화할 수 있는 셀 총량. 시트별 상한만으로는 시트를 여럿 두는
    # 우회를 막을 수 없다(실측: 10.7KB 스트림으로 1,920만 셀을 만들 수 있었다).
    workbook_budget = [MAX_WORKBOOK_CELLS]

    for sheet_index, sheet in enumerate(sorted_sheets):
        sheet_path = f"{normalized_stream}#{sheet.name}"
        section = Section(
            provenance=Provenance(
                source_format="xls",
                sheet=sheet.name,
                path=sheet_path,
                visibility=sheet.visibility,
                hidden=sheet.visibility in {1, 2},
            )
        )
        if sheet_index == 0:
            section.elements.extend(defined_name_elements)
        for paragraph in _sheet_header_footer_elements(sheet, path=sheet_path):
            section.elements.append(paragraph)
        table = _sheet_to_table(sheet, path=sheet_path, errors=doc.errors, budget=workbook_budget)
        if table.rows:
            section.elements.append(table)
        doc.sections.append(section)

    return doc


def _parse_externsheet(record_data: bytes) -> List[Tuple[int, int]]:
    count = struct.unpack_from("<H", record_data, 0)[0]
    refs: List[Tuple[int, int]] = []
    offset = 2
    for _ in range(count):
        if offset + 6 > len(record_data):
            break
        _, first_sheet, last_sheet = struct.unpack_from("<HHH", record_data, offset)
        refs.append((first_sheet, last_sheet))
        offset += 6
    return refs


def _read_name_record(record_data: bytes) -> _DefinedName:
    name_length = record_data[3]
    formula_length = struct.unpack_from("<H", record_data, 4)[0]
    menu_length = record_data[10]
    description_length = record_data[11]
    help_length = record_data[12]
    status_length = record_data[13]
    offset = 14
    if offset >= len(record_data):
        return _DefinedName("")
    flags = record_data[offset]
    offset += 1
    byte_count = name_length * (2 if flags & 0x01 else 1)
    if offset + byte_count > len(record_data):
        return _DefinedName("")
    raw = record_data[offset:offset + byte_count]
    name = raw.decode("utf-16-le" if flags & 0x01 else "cp1252", errors="replace")
    offset += byte_count
    tokens = record_data[offset:offset + formula_length]
    offset += formula_length + menu_length + description_length + help_length + status_length
    return _DefinedName(name, tokens) if offset <= len(record_data) else _DefinedName("")


def _defined_name_elements(
    defined_names: List[_DefinedName],
    external_sheets: List[Tuple[int, int]],
    sheet_names: List[str],
    name_labels: List[str],
    path: str,
) -> List[Paragraph]:
    elements = []
    for defined_name in defined_names:
        if not defined_name.tokens:
            continue
        target = _decode_formula_token_stream(
            defined_name.tokens,
            external_sheets=external_sheets,
            sheet_names=sheet_names,
            defined_names=name_labels,
        )
        if not target:
            continue
        provenance = Provenance(source_format="xls", path=path)
        elements.append(
            Paragraph(
                runs=[TextRun(text=f"Defined name: {_defined_name_label(defined_name.name)} = {target}", provenance=provenance)],
                provenance=provenance,
            )
        )
    return elements


def _defined_name_label(name: str) -> str:
    if name.startswith("_xlnm."):
        return name.split(".", 1)[1]
    return name


def _sheet_header_footer_elements(sheet: _SheetInfo, path: str) -> List[Paragraph]:
    elements = []
    provenance = Provenance(source_format="xls", sheet=sheet.name, path=path)
    header = _decode_header_footer_text(sheet.header)
    footer = _decode_header_footer_text(sheet.footer)
    if header:
        elements.append(Paragraph(runs=[TextRun(text=f"Header: {header}", provenance=provenance)], provenance=provenance))
    if footer:
        elements.append(Paragraph(runs=[TextRun(text=f"Footer: {footer}", provenance=provenance)], provenance=provenance))
    return elements


def _decode_header_footer_text(text: str) -> str:
    if not text:
        return ""
    decoded = text.replace("&&", "\u0000")
    replacements = {
        "&L": " ",
        "&C": " ",
        "&R": " ",
        "&P": "#",
        "&N": "#",
        "&D": "date",
        "&T": "time",
        "&F": "file",
        "&A": "sheet",
    }
    for marker, value in replacements.items():
        decoded = decoded.replace(marker, value)
    decoded = re.sub(r"&\"[^\"]*\"", " ", decoded)
    decoded = re.sub(r"&[0-9]{1,3}", " ", decoded)
    decoded = re.sub(r"&[A-Z]", " ", decoded)
    decoded = decoded.replace("\u0000", "&")
    return re.sub(r"\s+", " ", decoded).strip()


def _parse_sst(data: bytes) -> List[str]:
    return _parse_sst_segments([data])


class _SegmentReader:
    def __init__(self, segments: List[bytes]):
        self.segments = segments
        self.segment_index = 0
        self.offset = 0

    def read(self, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining > 0 and self.segment_index < len(self.segments):
            segment = self.segments[self.segment_index]
            available = len(segment) - self.offset
            if available <= 0:
                self._next_segment()
                continue
            take = min(available, remaining)
            chunks.append(segment[self.offset:self.offset + take])
            self.offset += take
            remaining -= take
        return b"".join(chunks)

    def read_byte(self) -> Optional[int]:
        raw = self.read(1)
        return raw[0] if raw else None

    def available_in_current_segment(self) -> int:
        if self.segment_index >= len(self.segments):
            return 0
        return max(0, len(self.segments[self.segment_index]) - self.offset)

    def _next_segment(self):
        self.segment_index += 1
        self.offset = 0


def _parse_sst_segments(segments: List[bytes]) -> List[str]:
    strings = []
    reader = _SegmentReader(segments)
    header = reader.read(8)
    if len(header) < 8:
        return strings
    unique_count = struct.unpack_from("<I", header, 4)[0]
    for _ in range(unique_count):
        text = _read_sst_string(reader)
        strings.append(text)
        if reader.segment_index >= len(reader.segments):
            break
    return strings


def _read_sst_string(reader: _SegmentReader) -> str:
    header = reader.read(3)
    if len(header) < 3:
        return ""
    char_count = struct.unpack_from("<H", header, 0)[0]
    flags = header[2]
    rich_text_runs = 0
    extension_size = 0
    if flags & 0x08:
        raw = reader.read(2)
        if len(raw) < 2:
            return ""
        rich_text_runs = struct.unpack_from("<H", raw, 0)[0]
    if flags & 0x04:
        raw = reader.read(4)
        if len(raw) < 4:
            return ""
        extension_size = struct.unpack_from("<I", raw, 0)[0]

    text_parts: List[str] = []
    remaining_chars = char_count
    current_flags = flags
    while remaining_chars > 0:
        bytes_per_char = 2 if current_flags & 0x01 else 1
        available_chars = reader.available_in_current_segment() // bytes_per_char
        if available_chars <= 0:
            next_flags = reader.read_byte()
            if next_flags is None:
                break
            current_flags = next_flags
            continue
        take_chars = min(remaining_chars, available_chars)
        raw = reader.read(take_chars * bytes_per_char)
        text_parts.append(raw.decode("utf-16-le" if current_flags & 0x01 else "cp1252", errors="replace"))
        remaining_chars -= take_chars

    reader.read(rich_text_runs * 4 + extension_size)
    return "".join(text_parts)


def _parse_sheet_records(
    data: bytes,
    sheet: _SheetInfo,
    shared_strings: List[str],
    formats: Dict[int, str],
    xf_formats: List[int],
    external_sheets: List[Tuple[int, int]],
    sheet_names: List[str],
    defined_names: List[str],
    date_1904: bool = False,
):
    pending_formula_cell: Optional[Tuple[int, int]] = None
    pending_formula_text = ""
    pending_shared_formula_anchor: Optional[Tuple[int, int]] = None
    shared_formula_cells: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    # MERGEDCELLS/HLINK 는 좌표 범위를 선언할 뿐인데 그 범위를 전부 채우면
    # 기형 파일 하나가 65536x256 번 반복하게 만든다. 채울 수 있는 총량을 제한한다.
    range_fill_budget = MAX_RANGE_FILL_CELLS
    shared_formula_templates: Dict[Tuple[int, int], bytes] = {}
    for _, record_type, record_data in _iter_records(data):
        if record_type == 0x00FD and len(record_data) >= 10:  # LABELSST
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, _, sst_index = struct.unpack_from("<HHHI", record_data, 0)
            try:
                sheet.cells[(row, col)] = shared_strings[sst_index]
            except IndexError:
                sheet.cells[(row, col)] = ""
        elif record_type == 0x0204 and len(record_data) >= 8:  # LABEL
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, _ = struct.unpack_from("<HHH", record_data, 0)
            sheet.cells[(row, col)] = _read_biff8_label_text(record_data, 6)
        elif record_type == 0x0004 and len(record_data) >= 7:  # BIFF2/3/4 LABEL
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, _ = struct.unpack_from("<HHH", record_data, 0)
            sheet.cells[(row, col)] = _read_biff_label_text(record_data, 6)
        elif record_type == 0x00D6 and len(record_data) >= 9:  # RSTRING
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, _ = struct.unpack_from("<HHH", record_data, 0)
            sheet.cells[(row, col)] = _read_biff8_label_text(record_data, 6)
        elif record_type in (0x0201, 0x0001) and len(record_data) >= 6:  # BLANK
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, _ = struct.unpack_from("<HHH", record_data, 0)
            sheet.cells.setdefault((row, col), "")
        elif record_type == 0x00BE and len(record_data) >= 8:  # MULBLANK
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, first_col = struct.unpack_from("<HH", record_data, 0)
            last_col = struct.unpack_from("<H", record_data, len(record_data) - 2)[0]
            for col in range(first_col, last_col + 1):
                sheet.cells.setdefault((row, col), "")
        elif record_type == 0x0208 and len(record_data) >= 2:  # ROW
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row = struct.unpack_from("<H", record_data, 0)[0]
            sheet.row_indices.add(row)
        elif record_type == 0x007D and len(record_data) >= 4:  # COLINFO
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            first_col, last_col = struct.unpack_from("<HH", record_data, 0)
            for col in range(first_col, last_col + 1):
                sheet.col_indices.add(col)
        elif record_type == 0x0200 and len(record_data) >= 8:  # DIMENSION
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            # BIFF5+ 는 행을 UINT32 로 쓰고(12바이트), BIFF2/3/4 는 UINT16 이다(8바이트).
            if len(record_data) >= 12:
                first_row, last_row, first_col, last_col = struct.unpack_from("<IIHH", record_data, 0)
            else:
                first_row, last_row, first_col, last_col = struct.unpack_from("<HHHH", record_data, 0)
            if first_row < last_row and first_col < last_col:
                sheet.dimension = (first_row, last_row, first_col, last_col)
        elif record_type == 0x0014:  # HEADER
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            sheet.header = _read_biff8_label_text(record_data)
        elif record_type == 0x0015:  # FOOTER
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            sheet.footer = _read_biff8_label_text(record_data)
        elif record_type in (0x0203, 0x0003) and len(record_data) >= 14:  # NUMBER
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, xf_index = struct.unpack_from("<HHH", record_data, 0)
            value = struct.unpack_from("<d", record_data, 6)[0]
            sheet.cells[(row, col)] = _format_number_with_format(
                value,
                _format_for_xf(xf_index, formats, xf_formats),
                date_1904=date_1904,
            )
        elif record_type == 0x0002 and len(record_data) >= 8:  # INTEGER
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, xf_index, value = struct.unpack_from("<HHHH", record_data, 0)
            sheet.cells[(row, col)] = _format_number_with_format(
                float(value),
                _format_for_xf(xf_index, formats, xf_formats),
                date_1904=date_1904,
            )
        elif record_type == 0x027E and len(record_data) >= 10:  # RK
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, xf_index, raw = struct.unpack_from("<HHHI", record_data, 0)
            value = _decode_rk(raw)
            sheet.cells[(row, col)] = _format_number_with_format(
                value,
                _format_for_xf(xf_index, formats, xf_formats),
                date_1904=date_1904,
            )
        elif record_type == 0x00BD and len(record_data) >= 10:  # MULRK
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, first_col = struct.unpack_from("<HH", record_data, 0)
            last_col = struct.unpack_from("<H", record_data, len(record_data) - 2)[0]
            offset = 4
            for col in range(first_col, last_col + 1):
                if offset + 6 > len(record_data) - 2:
                    break
                xf_index, raw = struct.unpack_from("<HI", record_data, offset)
                value = _decode_rk(raw)
                sheet.cells[(row, col)] = _format_number_with_format(
                    value,
                    _format_for_xf(xf_index, formats, xf_formats),
                    date_1904=date_1904,
                )
                offset += 6
        elif record_type in (0x0205, 0x0005) and len(record_data) >= 8:  # BOOLERR
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col, _, value, is_error = struct.unpack_from("<HHHBB", record_data, 0)
            if is_error:
                sheet.cells[(row, col)] = _format_biff_error(value)
            else:
                sheet.cells[(row, col)] = "TRUE" if value else "FALSE"
        elif record_type == 0x0006 and len(record_data) >= 14:  # FORMULA cached number
            row, col, xf_index = struct.unpack_from("<HHH", record_data, 0)
            formatted = _decode_formula_cached_result(record_data, _format_for_xf(xf_index, formats, xf_formats))
            formula = _decode_formula_tokens(record_data, external_sheets, sheet_names, defined_names)
            sheet.cells[(row, col)] = _with_formula_text(formatted, formula) if formula else formatted
            formula_anchor = _formula_exp_anchor(record_data)
            if formula_anchor:
                shared_formula_cells.setdefault(formula_anchor, []).append((row, col))
                pending_shared_formula_anchor = formula_anchor
                if formula_anchor in shared_formula_templates:
                    sheet.cells[(row, col)] = _with_formula_text(
                        formatted,
                        _decode_shared_formula_for_cell(
                            shared_formula_templates[formula_anchor],
                            formula_anchor,
                            (row, col),
                            external_sheets,
                            sheet_names,
                            defined_names,
                        ),
                    )
            else:
                pending_shared_formula_anchor = None
            pending_formula_cell = (row, col)
            pending_formula_text = formula
        elif record_type in (0x0207, 0x0007) and pending_formula_cell is not None:  # STRING formula result
            value = _read_formula_string_result_text(record_type, record_data)
            sheet.cells[pending_formula_cell] = f"{value} (={pending_formula_text})" if pending_formula_text else value
            pending_formula_cell = None
        elif record_type == 0x04BC and pending_shared_formula_anchor is not None:  # SHRFMLA
            tokens = _shared_formula_tokens(record_data)
            if tokens:
                shared_formula_templates[pending_shared_formula_anchor] = tokens
                for cell in shared_formula_cells.get(pending_shared_formula_anchor, []):
                    sheet.cells[cell] = _with_formula_text(
                        sheet.cells.get(cell, ""),
                        _decode_shared_formula_for_cell(
                            tokens,
                            pending_shared_formula_anchor,
                            cell,
                            external_sheets,
                            sheet_names,
                            defined_names,
                        ),
                    )
            pending_formula_cell = None
            pending_shared_formula_anchor = None
        elif record_type == 0x00E5 and len(record_data) >= 2:  # MERGEDCELLS
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            count = struct.unpack_from("<H", record_data, 0)[0]
            offset = 2
            for _ in range(count):
                if offset + 8 > len(record_data):
                    break
                first_row, last_row, first_col, last_col = struct.unpack_from("<HHHH", record_data, offset)
                sheet.merged_ranges.append((first_row, last_row, first_col, last_col))
                range_fill_budget = _fill_cell_range(
                    sheet, first_row, last_row, first_col, last_col, range_fill_budget
                )
                offset += 8
        elif record_type == 0x01B8 and len(record_data) >= 8:  # HLINK
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            first_row, last_row, first_col, last_col = struct.unpack_from("<HHHH", record_data, 0)
            url = _extract_hlink_url(record_data)
            if url:
                span = _range_span(first_row, last_row, first_col, last_col)
                if 0 < span <= range_fill_budget:
                    range_fill_budget -= span
                    for row_idx in range(first_row, last_row + 1):
                        for col_idx in range(first_col, last_col + 1):
                            sheet.hyperlinks[(row_idx, col_idx)] = url
                            sheet.cells.setdefault((row_idx, col_idx), "")
                elif span > 0:
                    # 범위가 예산을 넘으면 앵커 한 칸에만 링크를 붙인다
                    sheet.hyperlinks[(first_row, first_col)] = url
                    sheet.cells.setdefault((first_row, first_col), "")
        elif record_type == 0x001C and len(record_data) >= 11:  # NOTE
            pending_formula_cell = None
            pending_shared_formula_anchor = None
            row, col = struct.unpack_from("<HH", record_data, 0)
            author = _extract_note_author(record_data)
            if author:
                sheet.comments[(row, col)] = author
                sheet.cells.setdefault((row, col), "")


def has_filepass_record(data: bytes, scan_limit: int = 4096) -> bool:
    """BIFF FILEPASS(0x002F) 레코드 유무 — 암호로 보호된 워크북인지 판별한다.

    FILEPASS 이후의 레코드는 암호화되어 있어 그대로 해석하면 쓰레기 좌표가 나오고,
    그 좌표로 격자를 만들려다 시간과 메모리가 폭주한다.
    """
    offset = 0
    seen = 0
    while offset + 4 <= len(data) and seen < scan_limit:
        record_type, size = struct.unpack_from("<HH", data, offset)
        if record_type == 0x002F:
            return True
        offset += 4 + size
        seen += 1
    return False


def _warn_truncated(errors: Optional[List[str]], sheet: _SheetInfo, max_row: int, max_col: int) -> None:
    """격자를 잘랐다는 사실을 남긴다. 조용히 데이터를 버리면 안 된다."""
    if errors is None:
        return
    message = (
        f"WARN: XLS 시트 '{sheet.name}' 격자가 상한을 넘어 "
        f"{max_row + 1}행 x {max_col + 1}열로 잘렸습니다"
    )
    if message not in errors:
        errors.append(message)


def _range_span(first_row: int, last_row: int, first_col: int, last_col: int) -> int:
    if last_row < first_row or last_col < first_col:
        return 0
    return (last_row - first_row + 1) * (last_col - first_col + 1)


def _fill_cell_range(
    sheet: _SheetInfo,
    first_row: int,
    last_row: int,
    first_col: int,
    last_col: int,
    budget: int,
) -> int:
    """선언된 좌표 범위를 빈 셀로 채운다. 남은 예산을 돌려준다.

    예산을 넘는 범위는 앵커 한 칸만 남긴다 — 병합 정보 자체는
    sheet.merged_ranges 에 이미 있으므로 격자 복원에 필요한 정보는 잃지 않는다.
    """
    span = _range_span(first_row, last_row, first_col, last_col)
    if span <= 0:
        return budget
    if span > budget:
        sheet.cells.setdefault((first_row, first_col), "")
        return budget
    for row_idx in range(first_row, last_row + 1):
        for col_idx in range(first_col, last_col + 1):
            sheet.cells.setdefault((row_idx, col_idx), "")
    return budget - span


def _format_for_xf(xf_index: int, formats: Dict[int, str], xf_formats: List[int]) -> str:
    if xf_index < 0 or xf_index >= len(xf_formats):
        return ""
    return formats.get(xf_formats[xf_index], "")


def _extract_hlink_url(record_data: bytes) -> str:
    payload = record_data[8:]
    decoded_payloads = {
        payload.decode("utf-16-le", errors="ignore"),
        payload.decode("cp1252", errors="replace"),
    }

    url_patterns = [
        re.compile(r"(?:https?|ftp)://[^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"mailto:[^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"file://[^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"[A-Za-z]:[\\/][^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"\\\\[^\s\"'<>]+\\\\[^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"www\.[^\s\"'<>]+", re.IGNORECASE),
    ]

    best_match = ""
    for decoded in decoded_payloads:
        for pattern in url_patterns:
            match = pattern.search(decoded)
            if not match:
                continue
            candidate = re.sub(r"[\x00\n\r]+", "", match.group(0)).strip()
            if len(candidate) <= 0:
                continue
            if len(candidate) > len(best_match):
                best_match = candidate

    return best_match


def _extract_note_author(record_data: bytes) -> str:
    author_length = struct.unpack_from("<H", record_data, 8)[0]
    if len(record_data) < 11:
        return ""
    flags = record_data[10]
    offset = 11
    byte_count = author_length * (2 if flags & 0x01 else 1)
    if offset + byte_count > len(record_data):
        return ""
    raw = record_data[offset:offset + byte_count]
    return raw.decode("utf-16-le" if flags & 0x01 else "cp1252", errors="replace").strip()


def _decode_formula_cached_result(record_data: bytes, format_string: str = "") -> str:
    if len(record_data) < 14:
        return ""
    result = record_data[6:14]
    if result[6:8] == b"\xff\xff":
        result_type = result[0]
        if result_type == 0x01:
            return "TRUE" if result[2] else "FALSE"
        if result_type == 0x02:
            return _format_biff_error(result[2])
        if result_type == 0x03:
            return ""
    value = struct.unpack_from("<d", record_data, 6)[0]
    return _format_number_with_format(value, format_string)


def _decode_formula_tokens(
    record_data: bytes,
    external_sheets: Optional[List[Tuple[int, int]]] = None,
    sheet_names: Optional[List[str]] = None,
    defined_names: Optional[List[str]] = None,
) -> str:
    if len(record_data) < 22:
        return ""
    token_size = struct.unpack_from("<H", record_data, 20)[0]
    tokens = record_data[22:22 + token_size]
    return _decode_formula_token_stream(
        tokens,
        external_sheets=external_sheets,
        sheet_names=sheet_names,
        defined_names=defined_names,
    )


def _formula_exp_anchor(record_data: bytes) -> Optional[Tuple[int, int]]:
    if len(record_data) < 27:
        return None
    token_size = struct.unpack_from("<H", record_data, 20)[0]
    tokens = record_data[22:22 + token_size]
    if len(tokens) >= 5 and tokens[0] == 0x01:  # ptgExp
        return struct.unpack_from("<HH", tokens, 1)
    return None


def _decode_shared_formula(record_data: bytes) -> str:
    return _decode_formula_token_stream(_shared_formula_tokens(record_data))


def _shared_formula_tokens(record_data: bytes) -> bytes:
    if len(record_data) >= 10:
        token_size = struct.unpack_from("<H", record_data, 8)[0]
        tokens = record_data[10:10 + token_size]
        if tokens:
            return tokens
    if len(record_data) >= 11:
        token_size = struct.unpack_from("<H", record_data, 9)[0]
        return record_data[11:11 + token_size]
    return b""


def _decode_shared_formula_for_cell(
    tokens: bytes,
    anchor: Tuple[int, int],
    cell: Tuple[int, int],
    external_sheets: Optional[List[Tuple[int, int]]] = None,
    sheet_names: Optional[List[str]] = None,
    defined_names: Optional[List[str]] = None,
) -> str:
    return _decode_formula_token_stream(
        tokens,
        row_delta=cell[0] - anchor[0],
        col_delta=cell[1] - anchor[1],
        external_sheets=external_sheets,
        sheet_names=sheet_names,
        defined_names=defined_names,
    )


def _decode_formula_token_stream(
    tokens: bytes,
    row_delta: int = 0,
    col_delta: int = 0,
    external_sheets: Optional[List[Tuple[int, int]]] = None,
    sheet_names: Optional[List[str]] = None,
    defined_names: Optional[List[str]] = None,
) -> str:
    stack: List[str] = []
    offset = 0
    while offset < len(tokens):
        token = tokens[offset]
        offset += 1
        token = _base_formula_token(token)
        if token == 0x24 and offset + 4 <= len(tokens):  # ptgRef
            row, col = struct.unpack_from("<HH", tokens, offset)
            stack.append(_formula_cell_ref(row, col, row_delta=row_delta, col_delta=col_delta))
            offset += 4
        elif token == 0x25 and offset + 8 <= len(tokens):  # ptgArea
            first_row, last_row, first_col, last_col = struct.unpack_from("<HHHH", tokens, offset)
            stack.append(
                f"{_formula_cell_ref(first_row, first_col, row_delta=row_delta, col_delta=col_delta)}:"
                f"{_formula_cell_ref(last_row, last_col, row_delta=row_delta, col_delta=col_delta)}"
            )
            offset += 8
        elif token == 0x3A and offset + 6 <= len(tokens):  # ptgRef3d
            xti_index, row, col = struct.unpack_from("<HHH", tokens, offset)
            stack.append(
                f"{_formula_3d_prefix(xti_index, external_sheets, sheet_names)}"
                f"{_formula_cell_ref(row, col, row_delta=row_delta, col_delta=col_delta)}"
            )
            offset += 6
        elif token == 0x3B and offset + 10 <= len(tokens):  # ptgArea3d
            xti_index, first_row, last_row, first_col, last_col = struct.unpack_from("<HHHHH", tokens, offset)
            prefix = _formula_3d_prefix(xti_index, external_sheets, sheet_names)
            stack.append(
                f"{prefix}{_formula_cell_ref(first_row, first_col, row_delta=row_delta, col_delta=col_delta)}:"
                f"{_formula_cell_ref(last_row, last_col, row_delta=row_delta, col_delta=col_delta)}"
            )
            offset += 10
        elif token == 0x23 and offset + 4 <= len(tokens):  # ptgName
            name_index, _ = struct.unpack_from("<HH", tokens, offset)
            stack.append(_formula_name(name_index, defined_names))
            offset += 4
        elif token in {0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E} and len(stack) >= 2:
            right = stack.pop()
            left = stack.pop()
            stack.append(f"{left}{_formula_operator(token)}{right}")
        elif token in {0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E}:
            break
        elif token == 0x22 and offset + 3 <= len(tokens):  # ptgFuncVar
            argument_count = tokens[offset]
            function_index = struct.unpack_from("<H", tokens, offset + 1)[0]
            function_name, _ = _formula_function_name(function_index)
            available_args = min(len(stack), argument_count)
            if available_args == 0:
                break
            args = stack[-available_args:]
            del stack[-available_args:]
            stack.append(f"{function_name}({','.join(args)})")
            offset += 3
        elif token == 0x21 and offset + 2 <= len(tokens):  # ptgFunc
            function_index = struct.unpack_from("<H", tokens, offset)[0]
            argument_count = _fixed_function_arg_count(function_index)
            function_name, is_known = _formula_function_name(function_index)
            if not is_known and len(stack) > 0:
                argument_count = len(stack)
            if len(stack) < argument_count:
                break
            args = stack[-argument_count:]
            del stack[-argument_count:]
            stack.append(f"{function_name}({','.join(args)})")
            offset += 2
        elif token == 0x1E and offset + 2 <= len(tokens):  # ptgInt
            stack.append(str(struct.unpack_from("<h", tokens, offset)[0]))
            offset += 2
        elif token == 0x1F and offset + 8 <= len(tokens):  # ptgNum
            stack.append(_format_number(struct.unpack_from("<d", tokens, offset)[0]))
            offset += 8
        elif token == 0x17 and offset + 2 <= len(tokens):  # ptgStr
            char_count = tokens[offset]
            flags = tokens[offset + 1]
            offset += 2
            byte_count = char_count * (2 if flags & 0x01 else 1)
            if offset + byte_count > len(tokens):
                break
            raw = tokens[offset:offset + byte_count]
            text = raw.decode("utf-16-le" if flags & 0x01 else "cp1252", errors="replace")
            stack.append(_quote_formula_string(text))
            offset += byte_count
        elif token == 0x1D and offset + 1 <= len(tokens):  # ptgBool
            stack.append("TRUE" if tokens[offset] else "FALSE")
            offset += 1
        elif token == 0x1C and offset + 1 <= len(tokens):  # ptgErr
            stack.append(_format_biff_error(tokens[offset]))
            offset += 1
        elif token == 0x19:  # ptgAttr: skip attribute metadata
            if offset >= len(tokens):
                break
            if offset + 1 < len(tokens):
                offset += 2
            else:
                break
        elif token == 0x12 and stack:  # ptgUplus
            stack[-1] = f"+{stack[-1]}"
        elif token == 0x13 and stack:  # ptgUminus
            stack[-1] = f"-{stack[-1]}"
        elif token == 0x14 and stack:  # ptgPercent
            stack[-1] = f"{stack[-1]}%"
        elif token == 0x15 and stack:  # ptgParen
            stack[-1] = f"({stack[-1]})"
        else:
            break
    return stack[-1] if stack else ""


def _formula_3d_prefix(
    xti_index: int,
    external_sheets: Optional[List[Tuple[int, int]]],
    sheet_names: Optional[List[str]],
) -> str:
    if not external_sheets or not sheet_names or xti_index >= len(external_sheets):
        return ""
    first_sheet, last_sheet = external_sheets[xti_index]
    if first_sheet >= len(sheet_names):
        return ""
    first_name = _quote_sheet_name(sheet_names[first_sheet])
    if last_sheet != first_sheet and last_sheet < len(sheet_names):
        return f"{first_name}:{_quote_sheet_name(sheet_names[last_sheet])}!"
    return f"{first_name}!"


def _quote_sheet_name(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return f"'{name.replace(chr(39), chr(39) + chr(39))}'"


def _formula_name(name_index: int, defined_names: Optional[List[str]]) -> str:
    if not defined_names or name_index <= 0 or name_index > len(defined_names):
        return f"Name{name_index}"
    return defined_names[name_index - 1]


def _formula_cell_ref(row: int, col_flags: int, row_delta: int = 0, col_delta: int = 0) -> str:
    col = col_flags & 0x00FF
    col_relative = bool(col_flags & 0x4000)
    row_relative = bool(col_flags & 0x8000)
    if row_relative:
        row += row_delta
    if col_relative:
        col += col_delta
    if row < 0 or col < 0:
        return "#REF!"
    ref = _cell_ref(row, col)
    letters = "".join(char for char in ref if char.isalpha())
    row_number = ref[len(letters):]
    col_prefix = "" if col_relative else "$"
    row_prefix = "" if row_relative else "$"
    return f"{col_prefix}{letters}{row_prefix}{row_number}"


def _base_formula_token(token: int) -> int:
    return {
        0x41: 0x21,
        0x42: 0x22,
        0x44: 0x24,
        0x45: 0x25,
        0x5A: 0x3A,
        0x5B: 0x3B,
        0x61: 0x21,
        0x62: 0x22,
        0x64: 0x24,
        0x65: 0x25,
        0x7A: 0x3A,
        0x7B: 0x3B,
    }.get(token, token)


def _quote_formula_string(text: str) -> str:
    return f'"{text.replace(chr(34), chr(34) + chr(34))}"'


def _with_formula_text(value: str, formula: str) -> str:
    if not formula or "(=" in value:
        return value
    if not value:
        return f"(={formula})"
    return f"{value} (={formula})"


def _formula_operator(token: int) -> str:
    return {
        0x03: "+",
        0x04: "-",
        0x05: "*",
        0x06: "/",
        0x07: "^",
        0x08: "&",
        0x09: "<",
        0x0A: "<=",
        0x0B: "=",
        0x0C: ">=",
        0x0D: ">",
        0x0E: "<>",
    }.get(token, "")


def _formula_function_name(function_index: int) -> tuple[str, bool]:
    known_functions = {
        0: "COUNT",
        1: "IF",
        4: "SUM",
        5: "AVERAGE",
        6: "MIN",
        7: "MAX",
        8: "ROW",
        9: "COLUMN",
        27: "ROUND",
        34: "TRUE",
        35: "FALSE",
        36: "AND",
        37: "OR",
        38: "NOT",
        39: "MOD",
    }
    if function_index in known_functions:
        return known_functions[function_index], True
    return f"F{function_index}", False


def _fixed_function_arg_count(function_index: int) -> int:
    return {
        27: 2,
        34: 0,
        35: 0,
        39: 2,
    }.get(function_index, 1)


def _sheet_to_table(
    sheet: _SheetInfo,
    path: str,
    errors: Optional[List[str]] = None,
    budget: Optional[List[int]] = None,
) -> Table:
    if not sheet.cells and not sheet.row_indices and not sheet.col_indices:
        return Table()

    # 경계는 '내용이 있는 좌표' 로 잡아야 한다. MULBLANK/BLANK 가 만든 빈 자리표시자까지
    # 세면 실제로는 30열짜리 표가 108열로 잡혀 상한에 걸리고 본문이 잘린다.
    content_keys = [key for key, value in sheet.cells.items() if value]
    content_keys.extend(sheet.hyperlinks.keys())
    content_keys.extend(sheet.comments.keys())
    content_rows = {row for row, _ in content_keys}
    content_cols = {col for _, col in content_keys}

    cell_rows = {row for row, _ in sheet.cells.keys()}
    cell_cols = {col for _, col in sheet.cells.keys()}

    max_row = max(cell_rows | sheet.row_indices, default=-1)
    max_col = max(cell_cols | sheet.col_indices, default=-1)

    # DIMENSION 은 생성기가 주장하는 값이라 실제 데이터 범위보다 훨씬 클 수 있다.
    # 경계값만 반영한다. range() 로 집합에 풀면 65536개 정수를 채우게 된다.
    if sheet.dimension:
        first_row, last_row, first_col, last_col = sheet.dimension
        if last_row > first_row:
            max_row = max(max_row, last_row - 1)
        if last_col > first_col:
            max_col = max(max_col, last_col - 1)

    if max_row < 0 or max_col < 0:
        return Table()

    # 내용이 하나도 없는 큰 격자는 탭만 수십만 개인 표가 되어 출력 가치가 없다.
    # 작은 격자는 빈 좌표 보존을 위해 그대로 둔다.
    has_content = any(sheet.cells.values()) or sheet.hyperlinks or sheet.comments
    if not has_content and (max_row + 1) * (max_col + 1) > MAX_EMPTY_GRID_CELLS:
        return Table()

    # 선언된 격자를 그대로 실체화하면 셀마다 Provenance/Paragraph/TextRun/Cell 네 객체가
    # 생겨 시간과 메모리가 폭주한다(XLS 최대 65536x256 = 1677만 셀).
    # 실제 셀 수에 비해 격자가 지나치게 큰 경우만 선언값으로 부풀려진 것으로 보고 되돌린다.
    def _is_sparse(size: int) -> bool:
        return size > MAX_SHEET_CELLS and size > len(content_keys) * SPARSE_GRID_FACTOR

    grid_size = (max_row + 1) * (max_col + 1)
    if _is_sparse(grid_size):
        # 선언값과 빈 자리표시자로 부풀려진 격자를 내용이 있는 범위로 되돌린다.
        max_row = max(content_rows, default=-1)
        max_col = max(content_cols, default=-1)
        if max_row < 0 or max_col < 0:
            return Table()
        grid_size = (max_row + 1) * (max_col + 1)
        if _is_sparse(grid_size):
            # 되돌려도 희소하면 내용이 넓게 흩어진 것이다. 대부분 빈 칸이므로 잘라낸다.
            max_col = min(max_col, MAX_SHEET_COLS - 1)
            max_row = min(max_row, max(0, MAX_SPARSE_GRID_CELLS // (max_col + 1) - 1))
            grid_size = (max_row + 1) * (max_col + 1)
            _warn_truncated(errors, sheet, max_row, max_col)

    # 내용이 빽빽이 뒷받침하더라도 절대 상한은 넘지 않는다.
    # 워크북 전체 예산도 함께 본다 — 시트별 상한만으로는 시트를 여럿 두는 우회를 못 막는다.
    cap = MAX_SHEET_CELLS if budget is None else min(MAX_SHEET_CELLS, max(0, budget[0]))
    if grid_size > cap:
        max_col = min(max_col, MAX_SHEET_COLS - 1)
        max_row = min(max_row, max(0, cap // (max_col + 1) - 1))
        grid_size = (max_row + 1) * (max_col + 1)
        _warn_truncated(errors, sheet, max_row, max_col)
    if max_row < 0 or max_col < 0:
        return Table()
    if budget is not None:
        budget[0] -= grid_size

    rows = []
    for row_idx in range(max_row + 1):
        row = []
        for col_idx in range(max_col + 1):
            text = sheet.cells.get((row_idx, col_idx), "")
            hyperlink = sheet.hyperlinks.get((row_idx, col_idx), "")
            if hyperlink:
                text = f"{text} <{hyperlink}>" if text else hyperlink
            comment = sheet.comments.get((row_idx, col_idx), "")
            if comment:
                text = f"{text} [comment: {comment}]" if text else f"[comment: {comment}]"
            cell_ref = _cell_ref(row_idx, col_idx)
            provenance = Provenance(
                source_format="xls",
                sheet=sheet.name,
                cell=cell_ref,
                path=path,
            )
            paragraph = Paragraph(
                runs=[TextRun(text=text, provenance=provenance)],
                provenance=provenance,
            )
            row.append(Cell(paragraphs=[paragraph], row=row_idx, col=col_idx, provenance=provenance))
        rows.append(row)
    _apply_merged_ranges(rows, sheet.merged_ranges)
    return Table(rows=rows)


def _apply_merged_ranges(rows: List[List[Cell]], merged_ranges: List[Tuple[int, int, int, int]]) -> None:
    for first_row, last_row, first_col, last_col in merged_ranges:
        if first_row >= len(rows) or first_col >= len(rows[first_row]):
            continue
        anchor = rows[first_row][first_col]
        # 격자가 잘렸을 수 있으므로 span 이 표 밖을 가리키지 않게 한다.
        anchor.row_span = max(1, min(last_row, len(rows) - 1) - first_row + 1)
        anchor.col_span = max(1, min(last_col, len(rows[first_row]) - 1) - first_col + 1)
        for row_idx in range(first_row, min(last_row + 1, len(rows))):
            for col_idx in range(first_col, min(last_col + 1, len(rows[row_idx]))):
                if row_idx == first_row and col_idx == first_col:
                    continue
                rows[row_idx][col_idx].row_span = 0
                rows[row_idx][col_idx].col_span = 0


def _score_biff_document(document: Document) -> tuple[int, int, int]:
    section_count = len(document.sections)
    table_cells = 0
    text_elements = 0
    for section in document.sections:
        for element in section.elements:
            if hasattr(element, "rows"):
                for row in element.rows:
                    table_cells += len(row)
            elif hasattr(element, "runs"):
                text_elements += 1
    return (section_count, table_cells, text_elements)


class XLSReader:
    format_name = "xls"
    extensions = (".xls",)

    def read(self, file_path: str) -> Document:
        try:
            ole = olefile.OleFileIO(file_path)
        except Exception as exc:
            doc = Document(source_format="xls")
            doc.errors.append(f"ERR: XLS OLE 파일 열기 실패: {exc}")
            return doc

        doc = Document(source_format="xls")
        try:
            if is_encrypted_container(ole):
                doc.errors.append("ERR: XLS 암호로 보호된 문서입니다")
                return doc
            stream_names = [name for name in ("Workbook", "Book") if ole.exists(name)]
            if not stream_names:
                doc.errors.append("ERR: XLS Workbook stream not found")
                return doc

            best_document = None
            best_score = None
            for stream_name in stream_names:
                try:
                    workbook_data = ole.openstream(stream_name).read()
                    if has_filepass_record(workbook_data):
                        doc.errors.append(
                            f"ERR: XLS {stream_name} 은 암호로 보호되어 있습니다 (FILEPASS)"
                        )
                        continue
                    candidate = parse_biff_workbook(workbook_data, workbook_stream=stream_name)
                    score = _score_biff_document(candidate)
                    if best_document is None or score > best_score:
                        best_document = candidate
                        best_score = score
                except Exception as exc:
                    doc.errors.append(f"ERR: XLS {stream_name} stream 처리 실패: {exc}")
                    continue
            if best_document is not None:
                if doc.errors:
                    best_document.errors.extend(doc.errors)
                return best_document
            return doc
        except Exception as exc:
            doc.errors.append(f"ERR: XLS 파싱 중 오류: {exc}")
            return doc
        finally:
            ole.close()
