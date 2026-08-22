"""
hwp/section.py — 섹션 파서 (트리 구축 + 컨트롤 식별)

레코드 트리를 구축한 뒤 Document Model로 변환.

★ CTRL_HEADER 뒤에 개체 공통 속성 레코드가 올 수 있음 (스펙 4.3.9).
  실제 레코드 순서는 Level 기반으로 자동 처리되므로,
  트리 구축 시 Level만 정확하면 공통 속성이 children으로 포함됨.

★ TABLE(77) 레코드와 LIST_HEADER(72) 레코드의 순서가 유동적일 수 있음
  (hwplib Issue #201). children 전체를 순회하며 수집.
"""

import struct
from dataclasses import dataclass
from typing import List

from ..utils.safe_decompress import safe_zlib_decompress

from ..constants import (
    HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_PARA_CHAR_SHAPE,
    HWPTAG_CTRL_HEADER, HWPTAG_LIST_HEADER, HWPTAG_TABLE,
    HWPTAG_EQEDIT, HWPTAG_SHAPE_COMP_PICTURE,
)
from ..model.document import Section, Paragraph, TextRun
from ..model.table import Table, Cell
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote
from .records.ctrl_header import parse_ctrl_id, identify_control
from .records.para_text import parse_para_text
from .records.para_char_shape import parse_para_char_shape


MAX_HWP_RECORDS = 200_000
MAX_HWP_STRUCTURE_DEPTH = 64
MAX_HWP_TABLE_DEPTH = 32
MAX_HWP_TABLE_CELLS = 200_000
MAX_HWP_SECTION_CELLS = 200_000
MAX_HWP_DOCUMENT_CELLS = 200_000


class _HWPStructureError(ValueError):
    """Internal signal used to reject one unsafe structure transaction."""

    def __init__(self, key: str, message: str):
        super().__init__(message)
        self.key = key
        self.message = message


@dataclass
class RawRecord:
    tag_id: int
    level: int
    size: int
    data: bytes
    offset: int = 0


class SectionParser:

    MAX_STRUCTURE_DEPTH = MAX_HWP_STRUCTURE_DEPTH
    MAX_TABLE_DEPTH = MAX_HWP_TABLE_DEPTH
    MAX_TABLE_CELLS = MAX_HWP_TABLE_CELLS
    MAX_SECTION_CELLS = MAX_HWP_SECTION_CELLS
    MAX_DOCUMENT_CELLS = MAX_HWP_DOCUMENT_CELLS

    def __init__(self, doc_info=None):
        self.doc_info = doc_info  # DocInfo 참조 (서식 해석용)
        self.errors = []
        self._section_cells = 0
        self._document_cells = 0
        self._structure_depth = 0
        self._table_depth = 0
        self._fatal_error_keys = set()
        self._table_failure_serial = 0

    def parse_stream(self, stream_data: bytes, is_compressed: bool) -> Section:
        self._reset_section_limits()
        if is_compressed:
            stream_data = safe_zlib_decompress(stream_data)

        records = self._read_all_records(stream_data)
        tree = self._build_tree(records)
        return self._tree_to_section(tree, reset_limits=False)

    # ── 레코드 읽기 ──

    def _read_all_records(self, data: bytes) -> List[RawRecord]:
        records = []
        i = 0
        while i < len(data) - 3:
            if len(records) >= MAX_HWP_RECORDS:
                self.errors.append(
                    "ERR: HWP section record count exceeds limit: "
                    f"more than {MAX_HWP_RECORDS}"
                )
                break
            try:
                rec, new_i = self._read_one_record(data, i)
                if rec:
                    records.append(rec)
                i = new_i
            except ValueError as e:
                self.errors.append(f"ERR: 레코드 읽기 실패 offset={i}: {e}")
                break
            except Exception as e:
                self.errors.append(f"ERR: 레코드 읽기 실패 offset={i}: {e}")
                i += 4  # 에러 복구: 4바이트 전진
        return records

    def _read_one_record(self, data, offset):
        header = struct.unpack_from("<I", data, offset)[0]
        tag_id = header & 0x3FF
        level  = (header >> 10) & 0x3FF
        size   = (header >> 20) & 0xFFF

        if size == 0xFFF:
            # 확장 크기
            if offset + 8 > len(data):
                raise ValueError("truncated extended record header")
            size = struct.unpack_from("<I", data, offset + 4)[0]
            payload_start = offset + 8
        else:
            payload_start = offset + 4

        payload_end = payload_start + size
        if payload_end > len(data):
            raise ValueError(
                f"truncated record payload: declared={size}, "
                f"available={max(len(data) - payload_start, 0)}"
            )
        rec_data = data[payload_start:payload_end]
        return RawRecord(tag_id, level, size, rec_data, offset), payload_end

    # ── 트리 구축 ──

    def _build_tree(self, records):
        """레벨 기반 트리 구축.
        ★ HWP 실제 파일에서 LIST_HEADER 다음의 PARA_HEADER 및 그 하위 레코드가
          모두 같은 레벨로 나옴. LIST_HEADER의 paraCount를 읽어서
          해당 개수만큼의 PARA_HEADER(+하위)를 자식으로 강제 편입.
        """
        # 1단계: LIST_HEADER 뒤의 동일 레벨 레코드를 자식으로 level+1 보정
        # ★ 반복 적용으로 중첩 LH까지 처리
        adjusted = list(records)
        # NOTE: 5-pass fixpoint loop is O(5*n) where n=records.
        # Acceptable for documents up to ~100K records.
        # For larger documents, consider single-pass state machine.
        for _pass in range(5):
            new_adjusted = []
            changed = False
            i = 0
            while i < len(adjusted):
                rec = adjusted[i]
                if rec.tag_id == HWPTAG_LIST_HEADER:
                    new_adjusted.append(rec)
                    i += 1
                    while i < len(adjusted):
                        next_rec = adjusted[i]
                        if next_rec.level < rec.level:
                            break
                        if next_rec.level == rec.level and next_rec.tag_id == HWPTAG_LIST_HEADER:
                            break
                        # 같은 레벨 → +1, 더 깊은 레벨 → 역시 +1
                        new_adjusted.append(RawRecord(
                            next_rec.tag_id, next_rec.level + 1,
                            next_rec.size, next_rec.data, next_rec.offset
                        ))
                        if next_rec.level == rec.level:
                            changed = True
                        i += 1
                else:
                    new_adjusted.append(rec)
                    i += 1
            adjusted = new_adjusted
            if not changed:
                break

        # 2단계: 보정된 레코드로 트리 구축
        root = {'record': None, 'children': []}
        stack = [(-1, root)]

        for rec in adjusted:
            node = {'record': rec, 'children': []}
            while stack and stack[-1][0] >= rec.level:
                stack.pop()
            if stack:
                stack[-1][1]['children'].append(node)
            stack.append((rec.level, node))

        # 3단계: 후처리 — 자식 없는 LH 뒤의 형제 PH를 자식으로 재배치
        self._fix_empty_list_headers(root['children'], depth=0)

        return root['children']

    def _fix_empty_list_headers(self, nodes, depth=0):
        """자식 없는 LIST_HEADER 뒤의 형제 PARA_HEADER를 자식으로 이동 (재귀)"""
        if depth > self.MAX_STRUCTURE_DEPTH:
            self._append_fatal_once(
                "structure-depth",
                "ERR: HWP structure depth exceeds limit: "
                f"{depth} > {self.MAX_STRUCTURE_DEPTH}",
            )
            return
        i = 0
        while i < len(nodes):
            node = nodes[i]
            rec = node['record']

            # 먼저 자식 재귀
            if node['children']:
                self._fix_empty_list_headers(node['children'], depth=depth + 1)

            # LH에 자식이 없고, 다음 형제가 PH이면 자식으로 이동
            if (rec.tag_id == HWPTAG_LIST_HEADER and
                not node['children'] and
                i + 1 < len(nodes) and
                nodes[i + 1]['record'].tag_id == HWPTAG_PARA_HEADER):
                # PH (+ 그 이후 non-LH 형제들)를 LH 자식으로 이동
                moved = 0
                while (i + 1 < len(nodes) and
                       nodes[i + 1]['record'].tag_id != HWPTAG_LIST_HEADER):
                    sibling = nodes.pop(i + 1)
                    node['children'].append(sibling)
                    moved += 1
                # 이동하지 않았으면 다음으로
                if moved == 0:
                    i += 1
                # 이동했으면 같은 i에서 재확인 (LH가 연속일 수 있음)
            else:
                i += 1

    def _append_fatal_once(self, key: str, message: str) -> None:
        if key in self._fatal_error_keys:
            return
        self._fatal_error_keys.add(key)
        self.errors.append(message)

    def _reset_section_limits(self) -> None:
        self._section_cells = 0
        self._structure_depth = 0
        self._table_depth = 0
        self._fatal_error_keys.clear()
        self._table_failure_serial = 0

    def _reserve_table_cells(self, count: int) -> None:
        if count < 0:
            raise _HWPStructureError(
                "table-dimensions",
                "ERR: HWP table has invalid negative cell allocation",
            )
        if count > self.MAX_TABLE_CELLS:
            raise _HWPStructureError(
                "table-cells",
                "ERR: HWP table cell allocation exceeds limit: "
                f"{count} > {self.MAX_TABLE_CELLS}",
            )
        if self._section_cells + count > self.MAX_SECTION_CELLS:
            raise _HWPStructureError(
                "section-cells",
                "ERR: HWP section cell allocation exceeds limit: "
                f"{self._section_cells} + {count} > {self.MAX_SECTION_CELLS}",
            )
        if self._document_cells + count > self.MAX_DOCUMENT_CELLS:
            raise _HWPStructureError(
                "document-cells",
                "ERR: HWP document cell allocation exceeds limit: "
                f"{self._document_cells} + {count} > {self.MAX_DOCUMENT_CELLS}",
            )
        self._section_cells += count
        self._document_cells += count

    # ── 트리 → 모델 변환 ──

    def _tree_to_section(self, tree, *, reset_limits=True) -> Section:
        if reset_limits:
            self._reset_section_limits()
        section = Section()

        for node in tree:
            rec = node['record']
            if rec.tag_id == HWPTAG_PARA_HEADER:
                try:
                    elements = self._parse_paragraph_group(node)
                    section.elements.extend(elements)
                except _HWPStructureError as exc:
                    self._append_fatal_once(exc.key, exc.message)
                except RecursionError:
                    self._append_fatal_once(
                        "structure-recursion",
                        "ERR: HWP structure recursion limit exceeded",
                    )

        return section

    def _parse_paragraph_group(self, para_node):
        self._structure_depth += 1
        try:
            if self._structure_depth > self.MAX_STRUCTURE_DEPTH:
                raise _HWPStructureError(
                    "structure-depth",
                    "ERR: HWP structure depth exceeds limit: "
                    f"{self._structure_depth} > {self.MAX_STRUCTURE_DEPTH}",
                )
            return self._parse_paragraph_group_impl(para_node)
        finally:
            self._structure_depth -= 1

    def _parse_paragraph_group_impl(self, para_node):
        """PARA_HEADER 하위의 TEXT, CTRL_HEADER 등 파싱"""
        elements = []
        text_result = None
        char_shape_data = None
        ctrl_nodes = []

        for child in para_node['children']:
            crec = child['record']
            if crec.tag_id == HWPTAG_PARA_TEXT:
                text_result = parse_para_text(crec.data)
            elif crec.tag_id == HWPTAG_PARA_CHAR_SHAPE:
                char_shape_data = crec.data
            elif crec.tag_id == HWPTAG_CTRL_HEADER:
                ctrl_nodes.append(child)

        # 텍스트 문단 생성
        if text_result and text_result['text'].strip():
            para = Paragraph()
            # CharShape 기반 TextRun 분할
            text = text_result['text']
            cs_pairs = parse_para_char_shape(char_shape_data) if char_shape_data else []

            if cs_pairs and self.doc_info and hasattr(self.doc_info, 'char_shapes'):
                runs = []
                for idx, (pos, cs_id) in enumerate(cs_pairs):
                    end_pos = cs_pairs[idx + 1][0] if idx + 1 < len(cs_pairs) else len(text)
                    run_text = text[pos:end_pos]
                    if not run_text:
                        continue
                    run = TextRun(text=run_text)
                    if 0 <= cs_id < len(self.doc_info.char_shapes):
                        cs = self.doc_info.char_shapes[cs_id]
                        run.bold = cs.bold
                        run.italic = cs.italic
                        run.font_size_pt = cs.size_pt
                        run.underline = cs.underline_type > 0
                        run.strikeout = cs.strikeout > 0
                        run.superscript = cs.superscript
                        run.subscript = cs.subscript
                    runs.append(run)
                para.runs = runs if runs else [TextRun(text=text)]
            else:
                para.runs = [TextRun(text=text)]

            # 스타일 정보 연결 (PARA_HEADER에서)
            para_rec = para_node['record']
            if len(para_rec.data) >= 10:
                para.para_shape_id = struct.unpack_from("<H", para_rec.data, 8)[0]
            if len(para_rec.data) >= 11:
                para.style_id = para_rec.data[10]

            # 제목 감지
            para.heading_level = self._detect_heading_level(para)

            elements.append(para)

        # 컨트롤 파싱
        for ctrl_node in ctrl_nodes:
            failure_serial = self._table_failure_serial
            try:
                ctrl_elem = self._parse_control(ctrl_node)
            except _HWPStructureError as exc:
                if self._structure_depth > 1 or self._table_depth > 0:
                    raise
                self._append_fatal_once(exc.key, exc.message)
                continue
            except RecursionError as exc:
                if self._structure_depth > 1 or self._table_depth > 0:
                    raise _HWPStructureError(
                        "structure-recursion",
                        "ERR: HWP structure recursion limit exceeded",
                    ) from exc
                self._append_fatal_once(
                    "structure-recursion",
                    "ERR: HWP structure recursion limit exceeded",
                )
                continue
            if self._table_failure_serial != failure_serial:
                continue
            if ctrl_elem:
                elements.append(ctrl_elem)

        return elements

    def _detect_heading_level(self, para) -> int:
        """Style/CharShape 기반 제목 레벨 감지"""
        # 1. Style 이름 기반
        if self.doc_info and hasattr(self.doc_info, 'styles') and 0 <= para.style_id < len(self.doc_info.styles):
            style = self.doc_info.styles[para.style_id]
            name = style.name.lower()
            # "개요 1" → level 1, "개요 2" → level 2, etc.
            if '개요' in name or 'outline' in name or 'heading' in name:
                for i in range(1, 7):
                    if str(i) in name:
                        return i
                return 1  # default heading level
            if '제목' in name or 'title' in name:
                return 1
            if '부제목' in name or 'subtitle' in name:
                return 2

        # 2. Font size 기반 (CharShape 연결 후 작동)
        if para.runs:
            size = para.runs[0].font_size_pt
            if size >= 20:
                return 1
            elif size >= 16:
                return 2
            elif size >= 13:
                return 3

        return 0

    def _parse_control(self, ctrl_node):
        """★ ctrlId 바이트로 컨트롤 유형 식별 (v4.1 스펙 확정)"""
        ctrl_rec = ctrl_node['record']
        ctrl_id = parse_ctrl_id(ctrl_rec.data)
        ctrl_type = identify_control(ctrl_id)

        if ctrl_type == 'table':
            return self._parse_table(ctrl_node)
        elif ctrl_type == 'equation':
            return self._parse_equation(ctrl_node)
        elif ctrl_type == 'image':
            return self._parse_image(ctrl_node)
        elif ctrl_type in ('header', 'footer'):
            return self._parse_header_footer(ctrl_node, ctrl_type)
        elif ctrl_type in ('footnote', 'endnote'):
            return self._parse_footnote(ctrl_node, ctrl_type)
        else:
            return None

    def _parse_table(self, ctrl_node):
        """Parse one table as an all-or-nothing resource transaction."""
        parent_depth = self._table_depth
        starting_cells = self._section_cells
        starting_document_cells = self._document_cells
        self._table_depth += 1
        try:
            if self._table_depth > self.MAX_TABLE_DEPTH:
                raise _HWPStructureError(
                    "table-depth",
                    "ERR: HWP table nesting exceeds depth limit: "
                    f"{self._table_depth} > {self.MAX_TABLE_DEPTH}",
                )
            return self._parse_table_impl(ctrl_node)
        except RecursionError as exc:
            self._section_cells = starting_cells
            self._document_cells = starting_document_cells
            error = _HWPStructureError(
                "structure-recursion",
                "ERR: HWP structure recursion limit exceeded",
            )
            if parent_depth > 0:
                raise error from exc
            self._append_fatal_once(error.key, error.message)
            self._table_failure_serial += 1
            return Table()
        except _HWPStructureError as exc:
            self._section_cells = starting_cells
            self._document_cells = starting_document_cells
            if parent_depth > 0:
                raise
            self._append_fatal_once(exc.key, exc.message)
            self._table_failure_serial += 1
            return Table()
        finally:
            self._table_depth -= 1

    def _parse_table_impl(self, ctrl_node):
        """Collect, validate, reserve, then allocate a table exactly once."""
        table_rec = None
        list_header_nodes = []

        for child in ctrl_node['children']:
            crec = child['record']
            if crec.tag_id == HWPTAG_TABLE:
                table_rec = crec
            elif crec.tag_id == HWPTAG_LIST_HEADER:
                list_header_nodes.append(child)

        # TABLE 레코드에서 행/열 수 파싱
        row_count = 0
        col_count = 0
        if table_rec and len(table_rec.data) >= 8:
            row_count = struct.unpack_from("<H", table_rec.data, 4)[0]
            col_count = struct.unpack_from("<H", table_rec.data, 6)[0]

        geometries = [self._parse_cell_geometry(node) for node in list_header_nodes]
        if row_count > 0 and col_count > 0:
            allocation_rows = row_count
            allocation_cols = col_count
            use_coordinates = True
        else:
            use_coordinates = False
            if col_count > 0 and geometries:
                allocation_rows = (
                    len(geometries) + col_count - 1
                ) // col_count
                allocation_cols = col_count
            elif geometries:
                allocation_rows = 1
                allocation_cols = len(geometries)
            else:
                allocation_rows = 0
                allocation_cols = 0

        self._validate_cell_geometries(
            geometries,
            allocation_rows,
            allocation_cols,
            use_coordinates=use_coordinates,
        )
        allocation_count = allocation_rows * allocation_cols
        self._reserve_table_cells(allocation_count)

        cells_info = [self._parse_cell_info(node) for node in list_header_nodes]
        grid = [
            [Cell() for _ in range(allocation_cols)]
            for _ in range(allocation_rows)
        ]
        if use_coordinates:
            for info in cells_info:
                row = info.get('row', 0)
                col = info.get('col', 0)
                cell = grid[row][col]
                cell.paragraphs = info.get('paragraphs', [])
                cell.row_span = info.get('row_span', 1)
                cell.col_span = info.get('col_span', 1)
        else:
            for index, info in enumerate(cells_info):
                row, col = divmod(index, allocation_cols)
                grid[row][col].paragraphs = info.get('paragraphs', [])

        table = Table(rows=grid)

        return table

    def _parse_cell_geometry(self, lh_node) -> dict:
        """Read cell coordinates/spans without descending into its contents."""
        if "cell_info" in lh_node:
            info = lh_node["cell_info"]
            return {
                "row": info.get("row", 0),
                "col": info.get("col", 0),
                "row_span": info.get("row_span", 1),
                "col_span": info.get("col_span", 1),
            }

        geometry = {'row': 0, 'col': 0, 'row_span': 1, 'col_span': 1}
        data = lh_node['record'].data
        if len(data) >= 16:
            geometry['col'] = struct.unpack_from("<H", data, 8)[0]
            geometry['row'] = struct.unpack_from("<H", data, 10)[0]
            geometry['col_span'] = struct.unpack_from("<H", data, 12)[0]
            geometry['row_span'] = struct.unpack_from("<H", data, 14)[0]
        return geometry

    def _validate_cell_geometries(
        self,
        geometries,
        row_count: int,
        col_count: int,
        *,
        use_coordinates: bool,
    ) -> None:
        for index, geometry in enumerate(geometries):
            row_span = geometry.get('row_span', 1)
            col_span = geometry.get('col_span', 1)
            if row_span < 1 or col_span < 1:
                raise _HWPStructureError(
                    "table-span",
                    "ERR: HWP table invalid cell span",
                )
            if use_coordinates:
                row = geometry.get('row', 0)
                col = geometry.get('col', 0)
            else:
                row, col = divmod(index, col_count)
            if not (0 <= row < row_count and 0 <= col < col_count):
                raise _HWPStructureError(
                    "table-position",
                    "ERR: HWP table cell position out of bounds",
                )
            if row + row_span > row_count or col + col_span > col_count:
                raise _HWPStructureError(
                    "table-span-bounds",
                    "ERR: HWP table cell span out of bounds",
                )

    def _parse_cell_info(self, lh_node) -> dict:
        """LIST_HEADER 노드에서 셀 위치/병합/내용 파싱"""
        info = self._parse_cell_geometry(lh_node)
        info['paragraphs'] = []

        # 셀 내부 재귀 파싱 — 문단 + 중첩 컨트롤 모두
        for child in lh_node['children']:
            if child['record'].tag_id == HWPTAG_PARA_HEADER:
                elems = self._parse_paragraph_group(child)
                for e in elems:
                    if hasattr(e, 'runs'):  # Paragraph
                        info['paragraphs'].append(e)
                    elif hasattr(e, 'rows'):  # 중첩 Table
                        # 중첩 표의 셀 텍스트를 문단으로 풀어서 추가
                        for row in e.rows:
                            for cell in row:
                                info['paragraphs'].extend(cell.paragraphs)

        return info

    def _parse_equation(self, ctrl_node):
        """수식 파싱 — 스펙 표 105 확인 완료"""
        for child in ctrl_node['children']:
            if child['record'].tag_id == HWPTAG_EQEDIT:
                data = child['record'].data
                try:
                    if len(data) < 6:
                        return Equation(script="[데이터 부족]")
                    script_len = struct.unpack_from("<H", data, 4)[0]
                    if script_len * 2 + 6 > len(data):
                        return Equation(script="[데이터 부족]")
                    script_bytes = data[6 : 6 + script_len * 2]
                    script = script_bytes.decode('utf-16-le', errors='replace')
                    return Equation(script=script.strip('\x00'))
                except Exception:
                    return Equation(script="[수식 파싱 실패]")
        return None

    def _parse_image(self, ctrl_node):
        """이미지 파싱 — 스펙 표 32,107 확인 완료"""
        for child in ctrl_node['children']:
            if child['record'].tag_id == HWPTAG_SHAPE_COMP_PICTURE:
                data = child['record'].data
                bin_data_id = -1
                # Bounds check: need at least 73 bytes to read UINT16 at offset 71
                if len(data) >= 73:
                    bin_data_id = struct.unpack_from("<H", data, 71)[0]
                return Image(bin_id=bin_data_id,
                           filename=f"image_{bin_data_id}.bin")
        return None

    def _parse_header_footer(self, ctrl_node, hf_type):
        hf = HeaderFooter(type=hf_type)
        for child in ctrl_node['children']:
            if child['record'].tag_id == HWPTAG_LIST_HEADER:
                for sub in child['children']:
                    if sub['record'].tag_id == HWPTAG_PARA_HEADER:
                        elems = self._parse_paragraph_group(sub)
                        for e in elems:
                            if hasattr(e, 'runs'):
                                hf.paragraphs.append(e)
        return hf

    def _parse_footnote(self, ctrl_node, fn_type):
        fn = Footnote(type=fn_type)
        for child in ctrl_node['children']:
            if child['record'].tag_id == HWPTAG_LIST_HEADER:
                for sub in child['children']:
                    if sub['record'].tag_id == HWPTAG_PARA_HEADER:
                        elems = self._parse_paragraph_group(sub)
                        for e in elems:
                            if hasattr(e, 'runs'):
                                fn.paragraphs.append(e)
        return fn
