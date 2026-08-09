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
from dataclasses import dataclass, replace as _dc_replace
from typing import List, Optional

from ..utils.safe_decompress import safe_zlib_decompress

from ..constants import (
    HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_PARA_CHAR_SHAPE,
    HWPTAG_CTRL_HEADER, HWPTAG_LIST_HEADER, HWPTAG_TABLE,
    HWPTAG_EQEDIT, HWPTAG_SHAPE_COMP_PICTURE, HWPTAG_SHAPE_COMPONENT,
    HWPTAG_CTRL_DATA,
)
from ..model.document import Section, Paragraph, TextRun
from ..model.table import Table, Cell
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote
from .records.ctrl_header import (
    parse_ctrl_id, identify_control,
    is_field_ctrl_id, parse_field_command_url, CTRL_FIELD_HYPERLINK,
    CTRL_BOOKMARK,
)
from .records.para_text import parse_para_text
from .records.para_char_shape import parse_para_char_shape


def _apply_link_ranges(runs, ranges):
    """텍스트 오프셋 범위 [(start, end, url)] 를 런 목록에 적용한다.

    범위 경계에 걸친 런은 최대 3조각으로 나누고 가운데 조각에만 링크를 건다.
    런 서식(굵게 등)은 dataclasses.replace 로 그대로 복제된다.
    """
    for start, end, url in ranges:
        new_runs = []
        pos = 0
        for run in runs:
            run_len = len(run.text)
            run_start, run_end = pos, pos + run_len
            pos = run_end
            if run_len == 0 or run_end <= start or run_start >= end:
                new_runs.append(run)
                continue
            cut_a = max(start - run_start, 0)
            cut_b = min(end - run_start, run_len)
            if cut_a > 0:
                new_runs.append(_dc_replace(run, text=run.text[:cut_a]))
            new_runs.append(_dc_replace(run, text=run.text[cut_a:cut_b], link=url))
            if cut_b < run_len:
                new_runs.append(_dc_replace(run, text=run.text[cut_b:]))
        runs = new_runs
    return runs


@dataclass
class RawRecord:
    tag_id: int
    level: int
    size: int
    data: bytes
    offset: int = 0


class SectionParser:

    def __init__(self, doc_info=None):
        self.doc_info = doc_info  # DocInfo 참조 (서식 해석용)
        self.errors = []

    def parse_stream(self, stream_data: bytes, is_compressed: bool) -> Section:
        if is_compressed:
            stream_data = safe_zlib_decompress(stream_data)

        records = self._read_all_records(stream_data)
        tree = self._build_tree(records)
        return self._tree_to_section(tree)

    # ── 레코드 읽기 ──

    def _read_all_records(self, data: bytes) -> List[RawRecord]:
        records = []
        i = 0
        while i < len(data) - 3:
            try:
                rec, new_i = self._read_one_record(data, i)
                if rec:
                    records.append(rec)
                i = new_i
            except Exception as e:
                self.errors.append(f"레코드 읽기 실패 offset={i}: {e}")
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
                return None, len(data)
            size = struct.unpack_from("<I", data, offset + 4)[0]
            rec_data = data[offset + 8 : offset + 8 + size]
            return RawRecord(tag_id, level, size, rec_data, offset), offset + 8 + size
        else:
            rec_data = data[offset + 4 : offset + 4 + size]
            return RawRecord(tag_id, level, size, rec_data, offset), offset + 4 + size

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
        if depth > 100:
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

    # ── 트리 → 모델 변환 ──

    def _tree_to_section(self, tree) -> Section:
        section = Section()

        for node in tree:
            rec = node['record']
            if rec.tag_id == HWPTAG_PARA_HEADER:
                elements = self._parse_paragraph_group(node)
                section.elements.extend(elements)

        return section

    def _parse_paragraph_group(self, para_node):
        """PARA_HEADER 하위의 TEXT, CTRL_HEADER 등 파싱"""
        elements = []
        text_result = None
        char_shape_data = None
        ctrl_nodes = []
        bookmark_markers = []

        for child in para_node['children']:
            crec = child['record']
            if crec.tag_id == HWPTAG_PARA_TEXT:
                text_result = parse_para_text(crec.data)
            elif crec.tag_id == HWPTAG_PARA_CHAR_SHAPE:
                char_shape_data = crec.data
            elif crec.tag_id == HWPTAG_CTRL_HEADER:
                # 책갈피(bokm)는 필드가 아니라 별도 컨트롤 — 이름을 마커로 뽑고
                # 컨트롤 목록에서는 제외한다 (뒤 루프에서 요소로 만들지 않음).
                if parse_ctrl_id(crec.data) == CTRL_BOOKMARK:
                    name = self._bookmark_name(child)
                    if name and not name.startswith('_'):
                        bookmark_markers.append(TextRun(text=f"[bookmark: {name}] "))
                else:
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

            # 하이퍼링크 필드(%hlk) 범위에 링크 부여
            link_ranges = self._hyperlink_ranges(text_result, ctrl_nodes)
            if link_ranges:
                para.runs = _apply_link_ranges(para.runs, link_ranges)

            # 스타일 정보 연결 (PARA_HEADER에서)
            para_rec = para_node['record']
            if len(para_rec.data) >= 10:
                para.para_shape_id = struct.unpack_from("<H", para_rec.data, 8)[0]
            if len(para_rec.data) >= 11:
                para.style_id = para_rec.data[10]

            # 책갈피 마커는 문단 앞에 붙인다 (문서 내 앵커 — DOCX 규약과 동일)
            if bookmark_markers:
                para.runs = bookmark_markers + para.runs

            # 제목 감지
            para.heading_level = self._detect_heading_level(para)

            elements.append(para)
        elif bookmark_markers:
            # 텍스트 없는 책갈피(영역 앵커 등)도 마커로 남긴다
            elements.append(Paragraph(runs=list(bookmark_markers)))

        # 컨트롤 파싱 (GSO 는 이미지+도형 텍스트 등 여러 요소를 낼 수 있어 리스트 허용)
        for ctrl_node in ctrl_nodes:
            ctrl_elem = self._parse_control(ctrl_node)
            if isinstance(ctrl_elem, list):
                elements.extend(ctrl_elem)
            elif ctrl_elem:
                elements.append(ctrl_elem)

        return elements

    @staticmethod
    def _bookmark_name(ctrl_node) -> str:
        """책갈피(bokm) 컨트롤의 CTRL_DATA(파라미터셋)에서 이름을 읽는다.

        실측(143E '참조' / 전략물자 'wrapper' hexdump): CTRL_DATA 레이아웃은
        sig(2) + cnt(4) + item(4) + 이름 길이(UINT16, offset 10) + UTF-16LE(offset 12).
        """
        for child in ctrl_node['children']:
            if child['record'].tag_id != HWPTAG_CTRL_DATA:
                continue
            data = child['record'].data
            if len(data) < 12:
                continue
            length = struct.unpack_from("<H", data, 10)[0]
            end = 12 + length * 2
            if length == 0 or end > len(data):
                continue
            return data[12:end].decode('utf-16-le', errors='replace').strip('\x00').strip()
        return ""

    def _hyperlink_ranges(self, text_result, ctrl_nodes) -> list:
        """필드 마크(텍스트 스트림의 컨트롤 3/4)와 %hlk CTRL_HEADER 를 짝지어
        (start, end, url) 링크 범위 목록을 만든다.

        텍스트 스트림의 필드 시작 블록에는 ctrlId 가 내장되어 있으므로(실측),
        같은 ctrlId 의 N번째 등장 ↔ N번째 CTRL_HEADER 로 짝을 맺는다.
        필드가 닫히지 않으면 문단 끝까지 링크가 이어진다.
        """
        marks = text_result.get('field_marks') or []
        if not any(kind == 'start' for _, kind, _ in marks):
            return []

        # ctrlId 별 필드 CTRL_HEADER 대기열 (레코드 순서 = 텍스트 등장 순서)
        queues = {}
        for node in ctrl_nodes:
            data = node['record'].data
            cid = parse_ctrl_id(data)
            if is_field_ctrl_id(cid):
                queues.setdefault(cid, []).append(data)
        if not queues:
            return []
        next_index = {cid: 0 for cid in queues}

        text_len = len(text_result['text'])
        ranges = []
        stack = []
        for offset, kind, cid in marks:
            if kind == 'start':
                url = ''
                queue = queues.get(cid)
                if queue is not None and next_index[cid] < len(queue):
                    data = queue[next_index[cid]]
                    next_index[cid] += 1
                    if cid == CTRL_FIELD_HYPERLINK:
                        url = parse_field_command_url(data)
                stack.append((offset, url))
            else:
                if stack:
                    start, url = stack.pop()
                    end = min(offset, text_len)
                    if url and end > start:
                        ranges.append((start, end, url))
        # 닫히지 않은 필드는 문단 끝까지
        for start, url in stack:
            if url and text_len > start:
                ranges.append((start, text_len, url))

        # 바깥 범위 먼저 적용 → 중첩된 안쪽 범위가 나중에 덮어쓴다
        ranges.sort(key=lambda r: (r[0], -r[1]))
        return ranges

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
        elif ctrl_type == 'memo':
            # 숨은 설명/메모(tcmt) — DOCX 주석과 같은 Footnote(type='comment') 규약.
            # 실측 구조(han_grammar.hwp): CTRL_HEADER → LIST_HEADER → PARA_HEADER들
            return self._parse_footnote(ctrl_node, 'comment')
        else:
            return None

    MAX_TABLE_CELLS = 1_000_000  # 1M cells max

    # 표 캡션 위치 코드(개체 공통 속성 표 76) → caption_side 문자열
    _CAPTION_SIDE = {0: 'LEFT', 1: 'RIGHT', 2: 'TOP', 3: 'BOTTOM'}

    def _parse_table(self, ctrl_node):
        """표 파싱 (셀 병합 대응, LIST_HEADER(72)+TABLE(77) 수집)

        ★ 캡션 처리: 표 캡션은 TABLE 레코드보다 먼저 오는 LIST_HEADER 다
          (실측: Trade and Security / 정보보안 hexdump). _build_tree 의 LIST_HEADER
          자식 흡수 규칙 때문에 이 캡션 LH 가 뒤따르는 TABLE 레코드를 자식으로
          삼킨다. 그래서 TABLE 을 못 찾으면 표 차원이 0이 되고 캡션 LH 가 셀로
          오인돼 표가 통째로 무너진다. TABLE 을 만나기 전의 LIST_HEADER(및 그 안에
          흡수된 TABLE)를 캡션으로 분리한다.
        """
        table = Table()
        table_rec = None
        caption_nodes = []
        list_header_nodes = []

        for child in ctrl_node['children']:
            crec = child['record']
            if crec.tag_id == HWPTAG_TABLE:
                if table_rec is None:
                    table_rec = crec
            elif crec.tag_id == HWPTAG_LIST_HEADER:
                if table_rec is None:
                    # TABLE 을 아직 못 만났다 → 이 LH 는 캡션 영역이다.
                    # 트리 보정으로 TABLE 이 이 LH 자식으로 흡수됐을 수 있다.
                    nested_table = next(
                        (g['record'] for g in child['children']
                         if g['record'].tag_id == HWPTAG_TABLE), None)
                    if nested_table is not None:
                        table_rec = nested_table
                    caption_nodes.append(child)
                else:
                    list_header_nodes.append(child)

        caption = self._parse_table_caption(caption_nodes)
        if caption is not None:
            table.caption, table.caption_side = caption

        # TABLE 레코드에서 행/열 수 파싱
        row_count = 0
        col_count = 0
        if table_rec and len(table_rec.data) >= 8:
            row_count = struct.unpack_from("<H", table_rec.data, 4)[0]
            col_count = struct.unpack_from("<H", table_rec.data, 6)[0]

        # 각 LIST_HEADER에서 셀 정보 파싱
        cells_info = []
        for lh_node in list_header_nodes:
            ci = self._parse_cell_info(lh_node)
            cells_info.append(ci)

        # 좌표 기반 격자 배치 (셀 병합 대응)
        if row_count > 0 and col_count > 0:
            if row_count * col_count > self.MAX_TABLE_CELLS:
                self.errors.append(f"표 크기 초과: {row_count}x{col_count}")
                return table
            grid = [[Cell() for _ in range(col_count)] for _ in range(row_count)]
            placed = 0
            for ci in cells_info:
                r, c = ci.get('row', 0), ci.get('col', 0)
                if 0 <= r < row_count and 0 <= c < col_count:
                    grid[r][c] = Cell(
                        paragraphs=ci.get('paragraphs', []),
                        row_span=ci.get('row_span', 1),
                        col_span=ci.get('col_span', 1),
                    )
                    placed += 1

            # ★ 좌표 배치 실패율이 높으면 순서대로 재배치
            if placed < len(cells_info) * 0.5 and cells_info:
                if row_count * col_count > self.MAX_TABLE_CELLS:
                    self.errors.append(f"표 크기 초과: {row_count}x{col_count}")
                    return table
                grid = [[Cell() for _ in range(col_count)] for _ in range(row_count)]
                idx = 0
                for r in range(row_count):
                    for c in range(col_count):
                        if idx < len(cells_info):
                            ci = cells_info[idx]
                            grid[r][c] = Cell(
                                paragraphs=ci.get('paragraphs', []),
                                row_span=ci.get('row_span', 1),
                                col_span=ci.get('col_span', 1),
                            )
                            idx += 1
            table.rows = grid
        else:
            # 폴백: 단순 순서 배치
            if col_count > 0 and cells_info:
                rows = []
                for i in range(0, len(cells_info), col_count):
                    row = [Cell(paragraphs=ci.get('paragraphs', []))
                           for ci in cells_info[i:i+col_count]]
                    while len(row) < col_count:
                        row.append(Cell())
                    rows.append(row)
                table.rows = rows
            else:
                row = [Cell(paragraphs=ci.get('paragraphs', [])) for ci in cells_info]
                table.rows = [row] if row else []

        return table

    def _parse_table_caption(self, caption_nodes):
        """캡션 LIST_HEADER 노드들에서 (문단 목록, side) 를 만든다.

        캡션 LH 는 PARA_HEADER(캡션 문단)와 (흡수된) TABLE 을 자식으로 가진다.
        문단만 캡션으로 취하고 TABLE 은 건드리지 않는다. side 는 캡션 LH offset 8
        의 위치 코드(0=L,1=R,2=T,3=B)에서 읽는다 (실측 direction=2=TOP)."""
        if not caption_nodes:
            return None
        cap_paras = []
        side = 'BOTTOM'
        for cnode in caption_nodes:
            data = cnode['record'].data
            if len(data) >= 12:
                direction = struct.unpack_from("<I", data, 8)[0]
                side = self._CAPTION_SIDE.get(direction, side)
            for sub in cnode['children']:
                if sub['record'].tag_id == HWPTAG_PARA_HEADER:
                    cap_paras.extend(
                        e for e in self._parse_paragraph_group(sub)
                        if hasattr(e, 'runs'))
        if not cap_paras:
            return None
        return cap_paras, side

    def _parse_cell_info(self, lh_node) -> dict:
        """LIST_HEADER 노드에서 셀 위치/병합/내용 파싱"""
        lh_rec = lh_node['record']
        info = {'row': 0, 'col': 0, 'row_span': 1, 'col_span': 1, 'paragraphs': []}

        # ★ 실제 LIST_HEADER = UINT32(paraCount) + UINT32(props) = 8바이트
        # 셀 속성(26바이트)은 offset 8부터:
        #   offset 8=Col, 10=Row, 12=ColSpan, 14=RowSpan
        if len(lh_rec.data) >= 16:
            info['col'] = struct.unpack_from("<H", lh_rec.data, 8)[0]
            info['row'] = struct.unpack_from("<H", lh_rec.data, 10)[0]
            info['col_span'] = struct.unpack_from("<H", lh_rec.data, 12)[0]
            info['row_span'] = struct.unpack_from("<H", lh_rec.data, 14)[0]

        # 셀 내부 재귀 파싱 — 문단 + 중첩 컨트롤 모두
        for child in lh_node['children']:
            if child['record'].tag_id == HWPTAG_PARA_HEADER:
                elems = self._parse_paragraph_group(child)
                for e in elems:
                    if hasattr(e, 'runs'):  # Paragraph (도형 내부 텍스트 포함)
                        info['paragraphs'].append(e)
                    elif hasattr(e, 'rows'):  # 중첩 Table
                        # 중첩 표의 셀 텍스트를 문단으로 풀어서 추가
                        for row in e.rows:
                            for cell in row:
                                info['paragraphs'].extend(cell.paragraphs)
                    elif isinstance(e, Image):
                        # 셀 안 이미지도 유지 (HWPX 와 동일 — BinData 연결 대상)
                        info['paragraphs'].append(e)

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

    MAX_SHAPE_DEPTH = 32  # 묶음 개체(SC_CONTAINER) 중첩 상한

    def _parse_image(self, ctrl_node):
        """GSO/그림 개체 파싱 → 요소 리스트.

        실측 구조 (회계규칙/정보보안 등 test_pairs):
          CTRL_HEADER('gso ') ─ [LIST_HEADER(캡션)] ─ SHAPE_COMPONENT
                                  └ SC_PICTURE(이미지) 또는
                                    LIST_HEADER → PARA_HEADER(도형 내부 텍스트)
        SHAPE_COMPONENT 는 묶음 개체에서 중첩된다. SC_PICTURE 가
        CTRL_HEADER 직속인 구버전 구조도 그대로 지원한다.
        도형 내부 문단은 HWPX(drawText)와 동일하게 문서 흐름으로 내보낸다.
        """
        flow = []
        caption_paras = []
        alt_text = self._parse_object_description(ctrl_node['record'].data)

        for child in ctrl_node['children']:
            tag = child['record'].tag_id
            if tag == HWPTAG_LIST_HEADER:
                # GSO 직속 LIST_HEADER = 캡션 리스트.
                # 트리 보정으로 SHAPE_COMPONENT 가 이 밑에 들어올 수 있다 (실측).
                for sub in child['children']:
                    stag = sub['record'].tag_id
                    if stag == HWPTAG_PARA_HEADER:
                        caption_paras.extend(
                            e for e in self._parse_paragraph_group(sub)
                            if hasattr(e, 'runs'))
                    elif stag == HWPTAG_SHAPE_COMPONENT:
                        flow.extend(self._parse_shape_component(sub))
            elif tag == HWPTAG_SHAPE_COMPONENT:
                flow.extend(self._parse_shape_component(child))
            elif tag == HWPTAG_SHAPE_COMP_PICTURE:
                flow.append(self._picture_to_image(child['record'].data))

        images = [e for e in flow if isinstance(e, Image)]
        if images:
            if caption_paras:
                images[0].caption = caption_paras
            if alt_text:
                # 개체 설명문은 GSO 단위 속성 — HWPX shapeComment 처럼 이미지의
                # 대체 텍스트로 쓴다 (본문 텍스트로는 흘리지 않는다)
                images[0].alt_text = alt_text
        elif caption_paras:
            # 이미지 없는 도형의 캡션은 잃지 않도록 흐름에 남긴다
            flow.extend(caption_paras)
        return flow

    @staticmethod
    def _parse_object_description(data: bytes) -> str:
        """개체 공통 속성(표 70) 끝의 설명문 문자열.

        실측(회계규칙 GSO hexdump — HWPX shapeComment 와 대조 일치):
        offset 44 = UINT16 길이, offset 46 부터 UTF-16LE.
        고정 44바이트 = ctrlId(4)+속성(4)+오프셋(8)+크기(8)+z(4)+여백(8)
        +인스턴스ID(4)+쪽나눔방지(4). HWPX 는 XML 개행 정규화로 \\r\\n 이
        \\n 이 되므로 같은 값이 나오도록 정규화한다.
        """
        if len(data) < 46:
            return ""
        length = struct.unpack_from("<H", data, 44)[0]
        end = 46 + length * 2
        if length == 0 or end > len(data):
            return ""
        text = data[46:end].decode('utf-16-le', errors='replace')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        return text.strip('\x00').strip()

    def _parse_shape_component(self, node, depth: int = 0):
        """SHAPE_COMPONENT 하위에서 이미지/도형 텍스트를 문서 순서대로 수집"""
        if depth > self.MAX_SHAPE_DEPTH:
            return []
        out = []
        for child in node['children']:
            tag = child['record'].tag_id
            if tag == HWPTAG_SHAPE_COMP_PICTURE:
                out.append(self._picture_to_image(child['record'].data))
            elif tag == HWPTAG_SHAPE_COMPONENT:
                out.extend(self._parse_shape_component(child, depth + 1))
            elif tag == HWPTAG_LIST_HEADER:
                # 텍스트박스 리스트 — 트리 보정으로 PARA_HEADER 가 자식으로 온다
                for sub in child['children']:
                    stag = sub['record'].tag_id
                    if stag == HWPTAG_PARA_HEADER:
                        out.extend(self._parse_paragraph_group(sub))
                    elif stag == HWPTAG_SHAPE_COMPONENT:
                        out.extend(self._parse_shape_component(sub, depth + 1))
            elif tag == HWPTAG_PARA_HEADER:
                out.extend(self._parse_paragraph_group(child))
        return out

    @staticmethod
    def _picture_to_image(data: bytes) -> Image:
        """SC_PICTURE 레코드 → Image (스펙 표 32,107 확인 완료)"""
        bin_data_id = -1
        # Bounds check: need at least 73 bytes to read UINT16 at offset 71
        if len(data) >= 73:
            bin_data_id = struct.unpack_from("<H", data, 71)[0]
        return Image(bin_id=bin_data_id,
                     filename=f"image_{bin_data_id}.bin")

    def _list_blocks(self, ctrl_node) -> list:
        """CTRL_HEADER 하위 LIST_HEADER 들의 문단/표/이미지 블록 수집.

        문단만 남기면 안 된다 — 머리말 안에 표가 들고 그 표 셀에 그림이 있는
        실문서(회계규칙)가 있고, HWPX(_sublist_paragraphs)는 전부 유지한다.
        """
        blocks = []
        for child in ctrl_node['children']:
            if child['record'].tag_id == HWPTAG_LIST_HEADER:
                for sub in child['children']:
                    if sub['record'].tag_id == HWPTAG_PARA_HEADER:
                        blocks.extend(self._parse_paragraph_group(sub))
        return blocks

    def _parse_header_footer(self, ctrl_node, hf_type):
        return HeaderFooter(type=hf_type, paragraphs=self._list_blocks(ctrl_node))

    def _parse_footnote(self, ctrl_node, fn_type):
        return Footnote(type=fn_type, paragraphs=self._list_blocks(ctrl_node))
