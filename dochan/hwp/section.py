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
import unicodedata
import zlib
from bisect import bisect_right
from dataclasses import dataclass, replace as _dc_replace
from itertools import chain
from typing import List

from ..utils.safe_decompress import MAX_DECOMPRESSED_SIZE, safe_zlib_decompress

from ..constants import (
    HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_PARA_CHAR_SHAPE,
    HWPTAG_CTRL_HEADER, HWPTAG_LIST_HEADER, HWPTAG_TABLE,
    HWPTAG_EQEDIT, HWPTAG_SHAPE_COMP_PICTURE, HWPTAG_SHAPE_COMP_OLE,
    HWPTAG_SHAPE_COMPONENT,
    HWPTAG_CTRL_DATA, MAX_OUTLINE_HEADING_LEVEL,
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
from .forms import form_text
from .charts import ChartReference, MAX_CHARTS
from .revisions import project_text_result


def _apply_link_ranges(runs, ranges, *, max_runs=None, on_limit=None):
    """텍스트 오프셋 범위 [(start, end, url)] 를 런 목록에 적용한다.

    정렬한 경계를 한 번 순회하며 마지막 범위가 우선하는 링크를 적용한다.
    기존 런과 모든 범위 경계를 보존하므로 서식과 JSON의 런 분할도 유지한다.
    런 수 R, 범위 수 L에 대해 O(R + L log L) 작업으로 끝난다.
    """
    from heapq import heappop, heappush

    events = []
    for index, (start, end, url) in enumerate(ranges):
        # _hyperlink_ranges emits only nonempty forward intervals.
        if end <= start:
            continue
        events.append((start, (-index, end, url)))
        events.append((end, None))
    if not events:
        return runs
    events.sort(key=lambda event: event[0])
    active = []
    event_index = 0
    pos = 0
    result = []
    for run_index, run in enumerate(runs):
        run_start = pos
        run_end = pos + len(run.text)
        if run_end == pos:
            result.append(run)
            continue
        while pos < run_end:
            if max_runs is not None and len(result) >= max_runs:
                # Preserve all remaining characters without allocating a run
                # per boundary. This fallback also covers link-only fanout.
                tail = [run.text[pos - run_start:]]
                tail.extend(item.text for item in runs[run_index + 1:])
                result.append(TextRun(text=''.join(tail)))
                if on_limit is not None:
                    on_limit()
                return result
            while event_index < len(events) and events[event_index][0] <= pos:
                entry = events[event_index][1]
                if entry is not None:
                    heappush(active, entry)
                event_index += 1
            while active and active[0][1] <= pos:
                heappop(active)
            stop = min(run_end, events[event_index][0]) if event_index < len(events) else run_end
            if not active and pos == run_start and stop == run_end:
                result.append(run)
            else:
                result.append(_dc_replace(
                    run, text=run.text[pos - run_start:stop - run_start],
                    link=active[0][2] if active else run.link,
                ))
            pos = stop
    return result


# Public corpus maximum: 638,984 records in one section. A byte-only
# bound would admit 52,428,800 empty records in 200 MiB and amplify them
# into Python tree nodes. Keep an independent object/work bound as well.
MAX_HWP_RECORDS = 1_000_000
MAX_HWP_DOCUMENT_RECORDS = 1_300_000
MAX_HWP_DOCUMENT_BYTES = MAX_DECOMPRESSED_SIZE
MAX_HWP_STRUCTURE_DEPTH = 64
MAX_HWP_TABLE_DEPTH = 32
MAX_HWP_TABLE_CELLS = 200_000
MAX_HWP_SECTION_CELLS = 200_000
MAX_HWP_DOCUMENT_CELLS = 200_000
# Four times the public corpus maximum (131,072 model runs per document).
# See docs/benchmarks/2026-10-03-hwp-runs-real-docs.md. Plain fallback runs
# preserve paragraph boundaries and are not charged to this formatting budget.
MAX_HWP_DOCUMENT_TEXT_RUNS = 524_288


class HWPRecordLimitError(ValueError):
    """A section exceeded its record budget before building model objects."""


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
    MAX_DOCUMENT_TEXT_RUNS = MAX_HWP_DOCUMENT_TEXT_RUNS

    def __init__(self, doc_info=None, *, revision_mode="preserve", project_revisions=True):
        if revision_mode not in ("preserve", "final", "original"):
            raise ValueError("unsupported HWP revision mode")
        self.doc_info = doc_info  # DocInfo 참조 (서식 해석용)
        self.revision_mode = revision_mode
        self.project_revisions = project_revisions
        self.errors = []
        self._section_cells = 0
        self._document_cells = 0
        self._document_records = 0
        self._document_bytes = 0
        self._document_text_runs = 0
        self._structure_depth = 0
        self._table_depth = 0
        self._in_table_cell = False
        self._fatal_error_keys = set()
        self._document_error_keys = set()
        self._table_failure_serial = 0
        self._chart_count = 0

    def _document_limit_once(self, key, message):
        if key not in self._document_error_keys:
            self._document_error_keys.add(key)
            self.errors.append(message)

    def parse_stream(self, stream_data: bytes, is_compressed: bool,
                     *, reject_record_limit: bool = False,
                     distribution_decoder=None) -> Section:
        self._reset_section_limits()
        # A prior section may have consumed the whole document budget. Do
        # not inflate or reject ViewText again: that would trigger a futile
        # BodyText fallback and one warning per remaining section.
        if self._document_records >= MAX_HWP_DOCUMENT_RECORDS and stream_data:
            self._document_limit_once(
                "records", "ERR: HWP document record count exceeds limit: "
                f"more than {MAX_HWP_DOCUMENT_RECORDS}")
            return Section()
        remaining = max(0, MAX_HWP_DOCUMENT_BYTES - self._document_bytes)
        byte_limit = min(MAX_DECOMPRESSED_SIZE, remaining)
        if not remaining and stream_data:
            self._document_limit_once(
                "bytes", "ERR: HWP document size limit exhausted: "
                f"{MAX_HWP_DOCUMENT_BYTES} bytes")
            return Section()
        try:
            if distribution_decoder is not None:
                # Validate CRC/alignment and inflate exactly once, under the
                # same budget as ordinary BodyText (including failed work).
                stream_data = distribution_decoder(
                    stream_data, is_compressed=is_compressed,
                    max_size=byte_limit, decompress=True,
                )
            elif is_compressed:
                stream_data = safe_zlib_decompress(stream_data, max_size=byte_limit)
        except (ValueError, zlib.error) as exc:
            self._document_bytes += min(getattr(exc, "inflated", 0), byte_limit)
            if "decompressed size exceeds limit" not in str(exc).lower():
                raise
            # Both byte caps currently equal 200 MiB, so the document cap
            # wins ties (including a single oversized section). Keep the
            # section branch for independently configured per-stream caps.
            if byte_limit == remaining:
                self._document_limit_once(
                    "bytes", "ERR: HWP document size limit exhausted: "
                    f"{MAX_HWP_DOCUMENT_BYTES} bytes")
            else:
                self.errors.append(f"ERR: HWP section size limit: {exc}")
            return Section()
        if len(stream_data) > byte_limit:
            message = ("ERR: HWP section/document size exceeds limit: "
                       f"{len(stream_data)} > {byte_limit} bytes")
            if byte_limit == remaining:
                self._document_limit_once("bytes", message)
            else:
                self.errors.append(message)
            return Section()
        self._document_bytes += len(stream_data)

        records = self._read_all_records(stream_data, reject_record_limit=reject_record_limit)
        tree = self._build_tree(records)
        return self._tree_to_section(tree, reset_limits=False)

    # ── 레코드 읽기 ──

    def _read_all_records(self, data: bytes, *, reject_record_limit: bool = False) -> List[RawRecord]:
        records = []
        # parse_stream already bounds this input; retain the guard for
        # direct record-reader callers, which bypass decompression checks.
        if len(data) > MAX_DECOMPRESSED_SIZE:
            self.errors.append("ERR: HWP section size exceeds limit")
            return records
        i = 0
        while i < len(data) - 3:
            if self._document_records >= MAX_HWP_DOCUMENT_RECORDS:
                message = ("ERR: HWP document record count exceeds limit: "
                           f"more than {MAX_HWP_DOCUMENT_RECORDS}")
                if reject_record_limit:
                    raise HWPRecordLimitError(message)
                self._document_limit_once("records", message)
                break
            if len(records) >= MAX_HWP_RECORDS:
                message = (
                    "ERR: HWP section record count exceeds limit: "
                    f"more than {MAX_HWP_RECORDS}"
                )
                if reject_record_limit:
                    raise HWPRecordLimitError(message)
                self.errors.append(message)
                break
            try:
                rec, new_i = self._read_one_record(data, i)
                if rec:
                    records.append(rec)
                    # Includes a rejected ViewText attempt before a BodyText
                    # fallback, so repeated attempts cannot evade this budget.
                    self._document_records += 1
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
        # At most five linear passes; n is bounded before allocating the tree.
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
        retained = []
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
                end = i + 1
                while (end < len(nodes) and
                       nodes[end]['record'].tag_id != HWPTAG_LIST_HEADER):
                    end += 1
                node['children'].extend(nodes[i + 1:end])
                self._fix_empty_list_headers(node['children'], depth=depth + 1)
                i = end
            else:
                i += 1
            retained.append(node)
        # Repeated pop(i + 1) shifts the remaining sibling list O(n²).
        # Compact once, retaining the same node identities and visit order.
        nodes[:] = retained

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
        bookmark_markers = []
        range_records = []

        for child in para_node['children']:
            crec = child['record']
            if crec.tag_id == HWPTAG_PARA_TEXT:
                text_result = parse_para_text(crec.data)
            elif crec.tag_id == HWPTAG_PARA_CHAR_SHAPE:
                char_shape_data = crec.data
            elif crec.tag_id == 70:  # HWPTAG_PARA_RANGE_TAG (공개 명세 표 64)
                range_records.append(crec.data)
            elif crec.tag_id == HWPTAG_CTRL_HEADER:
                # 책갈피(bokm)는 필드가 아니라 별도 컨트롤 — 이름을 마커로 뽑고
                # 컨트롤 목록에서는 제외한다 (뒤 루프에서 요소로 만들지 않음).
                if parse_ctrl_id(crec.data) == CTRL_BOOKMARK:
                    name = self._bookmark_name(child)
                    if name and not name.startswith('_'):
                        bookmark_markers.append(TextRun(text=f"[bookmark: {name}] "))
                else:
                    ctrl_nodes.append(child)

        if text_result:
            text_result, ctrl_nodes = self._form_text_result(text_result, ctrl_nodes)
            if self.project_revisions:
                self._warn_revision_controls(text_result, range_records)
                text_result = project_text_result(
                    text_result, range_records, getattr(self.doc_info, 'track_changes', {}),
                    self.revision_mode, self.errors,
                )

        # 텍스트 문단 생성
        if text_result and text_result['text'].strip():
            para = Paragraph()
            para_rec = para_node['record']
            if len(para_rec.data) >= 10:
                para.para_shape_id = struct.unpack_from("<H", para_rec.data, 8)[0]
            if len(para_rec.data) >= 11:
                para.style_id = para_rec.data[10]
            # CharShape 기반 TextRun 분할
            remaining = max(0, self.MAX_DOCUMENT_TEXT_RUNS - self._document_text_runs)
            para.runs, plain_tail = self._text_runs(text_result, char_shape_data, remaining)

            # 하이퍼링크 필드(%hlk) 범위에 링크 부여
            link_ranges = self._hyperlink_ranges(text_result, ctrl_nodes)
            if link_ranges:
                if plain_tail:
                    text_end = len(text_result['text'])
                    tail_start = text_end - len(para.runs[-1].text)
                    if any(url and max(start, tail_start) < min(end, text_end)
                           for start, end, url in link_ranges):
                        self._text_run_limit()
                # Never apply links to the unformatted suffix. If links exhaust
                # the budget earlier, join the two plain suffixes only once.
                tail = para.runs.pop() if plain_tail else None
                para.runs = _apply_link_ranges(
                    para.runs, link_ranges, max_runs=remaining,
                    on_limit=self._text_run_limit,
                )
                link_tail = len(para.runs) > remaining
                if tail is not None:
                    if link_tail:
                        para.runs[-1].text += tail.text
                    else:
                        para.runs.append(tail)
                plain_tail = plain_tail or link_tail
            self._document_text_runs += len(para.runs) - int(plain_tail)

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
            failure_serial = self._table_failure_serial
            starting_cells = self._section_cells
            starting_document_cells = self._document_cells
            starting_text_runs = self._document_text_runs
            try:
                ctrl_elem = self._parse_control(ctrl_node)
            except (_HWPStructureError, RecursionError) as exc:
                # 실패한 컨트롤의 예약만 되돌린다. 같은 문단의 텍스트와
                # 이미 성공한 형제 컨트롤은 그 예약과 함께 보존한다.
                self._section_cells = starting_cells
                self._document_cells = starting_document_cells
                self._document_text_runs = starting_text_runs
                if isinstance(exc, _HWPStructureError):
                    self._append_fatal_once(exc.key, exc.message)
                else:
                    self._append_fatal_once(
                        "structure-recursion",
                        "ERR: HWP structure recursion limit exceeded",
                    )
                continue
            if self._table_failure_serial != failure_serial:
                self._document_text_runs = starting_text_runs
                continue
            if isinstance(ctrl_elem, list):
                elements.extend(ctrl_elem)
            elif ctrl_elem:
                elements.append(ctrl_elem)

        return elements

    def _text_run_limit(self):
        self._document_limit_once(
            "text-runs",
            "WARN: HWP document text run budget exceeded; remaining text is preserved "
            "without formatting or hyperlinks",
        )

    def _text_runs(self, text_result, char_shape_data, remaining):
        """Stream shape boundaries; retain at most remaining formatted runs.

        Duplicate boundaries at the same mapped position never create a run.
        Different positions retain their historical JSON split, even when the
        styles match: merging those would change public serialized output.
        """
        text = text_result['text']
        shapes = getattr(self.doc_info, 'char_shapes', None)
        if not char_shape_data or len(char_shape_data) < 8 or not shapes:
            return [TextRun(text=text)], remaining == 0
        # A memoryview and iter_unpack avoid an input-sized list of tuples.
        pairs = struct.iter_unpack(
            '<II', memoryview(char_shape_data)[:len(char_shape_data) // 8 * 8])
        first = next(pairs)
        current_id = first[1]
        raw_to_text = text_result['raw_to_text']
        start = 0
        runs = []

        def suffix_changes(end, next_id):
            """무서식 단일 구간은 경고하지 않되, 뒤쪽 서식/분할 소실은 확인한다."""
            cursor = start
            shape_id = current_id
            segments = 0
            boundaries = chain(((end, next_id),),
                               ((min(raw_to_text[min(pos, len(raw_to_text) - 1)], len(text)), sid)
                                for pos, sid in pairs),
                               ((len(text), None),))
            for boundary, following_id in boundaries:
                if boundary < cursor:
                    continue
                if boundary > cursor:
                    segments += 1
                    if segments > 1:
                        return True
                    if shape_id is not None and 0 <= shape_id < len(shapes):
                        cs = shapes[shape_id]
                        if (cs.bold or cs.italic or cs.size_pt != 10.0 or cs.has_underline
                                or cs.has_strikeout or cs.superscript or cs.subscript):
                            return True
                cursor = boundary
                shape_id = following_id
            return False

        def append_run(end, next_id=None):
            if end == start:
                return True
            if len(runs) >= remaining:
                if suffix_changes(end, next_id):
                    self._text_run_limit()
                runs.append(TextRun(text=text[start:]))
                return False
            run = TextRun(text=text[start:end])
            if 0 <= current_id < len(shapes):
                cs = shapes[current_id]
                run.bold = cs.bold
                run.italic = cs.italic
                run.font_size_pt = cs.size_pt
                run.underline = cs.has_underline
                run.strikeout = cs.has_strikeout
                run.superscript = cs.superscript
                run.subscript = cs.subscript
            runs.append(run)
            return True

        for pos, cs_id in chain((first,), pairs):
            end = min(raw_to_text[min(pos, len(raw_to_text) - 1)], len(text))
            if end < start:
                continue
            if not append_run(end, cs_id):
                return runs, True
            start = end
            current_id = cs_id
        if not append_run(len(text)):
            return runs, True
        return runs, False

    def _warn_revision_controls(self, text_result, range_records):
        """개체 변경은 텍스트 투영만으로 확정하지 않고 부분지원으로 알린다."""
        if self.revision_mode == 'preserve':
            return
        controls = sorted((start, end) for start, end, _ in text_result.get('inline_controls', []))
        if not controls:
            return
        ends = [end for _, end in controls]
        target = 0x11 if self.revision_mode == 'final' else 0x10
        count = 0
        for data in range_records:
            if len(data) % 12:
                continue
            for start, end, tag in struct.iter_unpack('<III', data):
                count += 1
                if count > 100_000:
                    return  # project_text_result reports the range limit.
                if tag >> 24 != target:
                    continue
                index = bisect_right(ends, start)
                if index < len(controls) and controls[index][0] < end:
                    self._append_fatal_once(
                        'revision-control',
                        'ERR: HWP revision partial [control]; unresolved object preserved',
                    )
                    return

    def _form_text_result(self, text_result, ctrl_nodes):
        """인라인 양식·겹침·덧말을 원시 WCHAR 경계에 삽입한다."""
        queues = {}
        for node in ctrl_nodes:
            cid = parse_ctrl_id(node['record'].data)
            queues.setdefault(cid, []).append(node)
        next_index = {}
        insertions = []
        consumed = set()
        raw_map = text_result['raw_to_text']
        for _start, end, cid in text_result.get('inline_controls', []):
            if cid not in (b'mrof', b'spct', b'tudt'):
                continue
            index = next_index.get(cid, 0)
            next_index[cid] = index + 1
            nodes = queues.get(cid, [])
            if index >= len(nodes):
                self._document_limit_once('inline-' + repr(cid),
                                          'WARN: HWP inline control record missing')
                continue
            node = nodes[index]
            if cid == b'mrof':
                value = self._form_node_text(node)
            else:
                value = self._compose_dutmal_text(node['record'].data, cid)
            consumed.add(id(node))
            if value and end < len(raw_map):
                insertions.append((end, raw_map[end], value))

        if not insertions:
            return text_result, [node for node in ctrl_nodes if id(node) not in consumed]
        insertions.sort(key=lambda item: item[0])
        prefix = [0]
        for _, _, value in insertions:
            prefix.append(prefix[-1] + len(value))
        if len(text_result['text']) + prefix[-1] > 100 * 1024 * 1024:
            self._document_limit_once('inline-size', 'WARN: HWP inline output exceeds size limit')
            return text_result, [node for node in ctrl_nodes if id(node) not in consumed]
        parts = []
        offset = 0
        for _, position, value in insertions:
            parts.extend((text_result['text'][offset:position], value))
            offset = position
        parts.append(text_result['text'][offset:])
        result = dict(text_result)
        result['text'] = ''.join(parts)
        ends = [item[0] for item in insertions]
        result['raw_to_text'] = [value + prefix[bisect_right(ends, index)]
                                 for index, value in enumerate(raw_map)]
        result['field_marks'] = [(result['raw_to_text'][pos], kind, cid)
                                 for pos, kind, cid in text_result.get('field_raw_marks', [])
                                 if pos < len(raw_map)]
        return result, [node for node in ctrl_nodes if id(node) not in consumed]

    def _compose_dutmal_text(self, data, cid):
        """한컴 HWP 5.0 4.3.10.12/13의 가변 길이 CTRL_HEADER 본문."""
        try:
            if len(data) < 6 or data[:4] != cid:
                raise ValueError
            first_len = struct.unpack_from('<H', data, 4)[0]
            if first_len > 4096:
                raise ValueError
            first_end = 6 + first_len * 2
            if cid == b'spct':
                if first_end + 4 > len(data):
                    raise ValueError
                count = data[first_end + 3]
                if first_end + 4 + count * 4 > len(data):
                    raise ValueError
                value = data[6:first_end].decode('utf-16-le')
                # 공개 sample-compose-all-shapes 짝: 테두리 타입별 첫 문자는
                # HWP에만 저장된 도형 글리프이며 HWPX composeText에는 없다.
                borders = '\u3000◯●□■△▲☼◇◆▢♲♺♻'
                border_type = data[first_end]
                if border_type < len(borders) and value.startswith(borders[border_type]):
                    value = value[1:]
                # 원형 테두리 안의 숫자만 HWPX의 표시 숫자로 분해한다.
                # 테두리 없는 원문자 숫자는 HWPX에서도 원문자 그대로다.
                if (border_type == 1 and len(value) == 1
                        and '\u2460' <= value <= '\u2473'):
                    value = unicodedata.normalize('NFKC', value)
                if (border_type == 2 and len(value) == 1
                        and '\u2776' <= value <= '\u277f'):
                    value = str(ord(value) - ord('\u2776') + 1)
                # 공개 HWP/HWPX 짝에서 관측한 한컴 PUA 숫자 글리프만 복원한다.
                if len(value) == 1:
                    code = ord(value)
                    if 0xf02b1 <= code <= 0xf02b4:
                        return str(code - 0xf02b0)
                    if 0xf02ce <= code <= 0xf02d0:
                        return str(code - 0xf02cd)
                if (len(value) == 2 and ord(value[0]) == 0xf02ba
                        and 0xf02c3 <= ord(value[1]) <= 0xf02c8):
                    return str(ord(value[1]) - 0xf02c3 + 10)
                if value == '\U000f0289\U000f0293':
                    return '11'
                return value
            if first_end + 2 > len(data):
                raise ValueError
            second_len = struct.unpack_from('<H', data, first_end)[0]
            if second_len > 4096:
                raise ValueError
            second_end = first_end + 2 + second_len * 2
            if second_end + 20 > len(data):
                raise ValueError
            main = data[6:first_end].decode('utf-16-le')
            sub = data[first_end + 2:second_end].decode('utf-16-le')
            return main + ('(' + sub + ')' if sub else '')
        except (ValueError, UnicodeError, struct.error):
            self._document_limit_once('inline-malformed-' + repr(cid),
                                      'WARN: HWP inline control truncated or invalid')
            return ''

    def _form_node_text(self, node):
        for child in node['children']:
            if child['record'].tag_id == 91:  # HWPTAG_FORM_OBJECT
                try:
                    return form_text(child['record'].data)
                except ValueError as exc:
                    self._append_fatal_once('form-data', 'WARN: ' + str(exc))
        return ''

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
        # 유효한 직접 문단 모양은 스타일의 개요 기본값보다 우선한다.
        shapes = getattr(self.doc_info, 'para_shapes', [])
        direct = 0 <= para.para_shape_id < len(shapes)
        if direct and shapes[para.para_shape_id].heading_type == 1:
            # 깊은 개요는 본문 열거 항목이다. 글꼴 크기로 다시 승격하지 않는다.
            return self._outline_level(para.para_shape_id)
        # 1. Style 이름 기반
        if self.doc_info and hasattr(self.doc_info, 'styles') and 0 <= para.style_id < len(self.doc_info.styles):
            style = self.doc_info.styles[para.style_id]
            name = style.name.lower()
            # "개요 1" → level 1, "개요 2" → level 2, etc.
            if '개요' in name or 'outline' in name or 'heading' in name:
                for i in range(1, 7):
                    if str(i) in name:
                        return i if i <= MAX_OUTLINE_HEADING_LEVEL else 0
                return 1  # default heading level
            if name.startswith(('부제목', 'subtitle')):
                return 2
            if '제목' in name or 'title' in name:
                return 1
            if (not direct and 0 <= style.para_shape_id < len(shapes)
                    and shapes[style.para_shape_id].heading_type == 1):
                return self._outline_level(style.para_shape_id)

        level = self._outline_level(para.para_shape_id)
        if level:
            return level

        return 0 if self._in_table_cell else self._heading_level_by_font(para)

    @staticmethod
    def _heading_level_by_font(para) -> int:
        # 개요 정보가 없는 셀 밖 문단만 글꼴 크기로 판단한다.
        if para.runs:
            size = para.runs[0].font_size_pt
            if size >= 20:
                return 1
            elif size >= 16:
                return 2
            elif size >= 13:
                return 3

        return 0

    def _outline_level(self, shape_id):
        shapes = getattr(self.doc_info, 'para_shapes', [])
        if 0 <= shape_id < len(shapes):
            shape = shapes[shape_id]
            level = getattr(shape, 'heading_level', 0) + 1
            if shape.heading_type == 1 and 1 <= level <= MAX_OUTLINE_HEADING_LEVEL:
                return level
        return 0

    def _parse_control(self, ctrl_node):
        """★ ctrlId 바이트로 컨트롤 유형 식별 (v4.1 스펙 확정)"""
        ctrl_rec = ctrl_node['record']
        ctrl_id = parse_ctrl_id(ctrl_rec.data)
        if ctrl_id == b'mrof':
            value = self._form_node_text(ctrl_node)
            return Paragraph(runs=[TextRun(value)]) if value else None
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
        """표 하나를 all-or-nothing 자원 트랜잭션으로 파싱한다.

        중첩 깊이나 셀 예산을 넘기면 그 표만 통째로 되돌리고, 최상위에서는
        오류로 강등해 문서 전체 파싱이 죽지 않게 한다.
        """
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
        """표 파싱 (셀 병합 대응, LIST_HEADER(72)+TABLE(77) 수집)

        ★ 캡션 처리: 표 캡션은 TABLE 레코드보다 먼저 오는 LIST_HEADER 다
          (실측: 내부 실물 문서 2건의 hexdump). _build_tree 의 LIST_HEADER
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

        # 앞서 분리해 둔 캡션을 잃지 않도록 새 Table 을 만들지 않고 격자만 채운다.
        table.rows = grid

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
                        if hasattr(e, 'runs') or isinstance(e, ChartReference))
        if not cap_paras:
            return None
        return cap_paras, side

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
        saved_cell = self._in_table_cell
        self._in_table_cell = True
        try:
            return self._parse_cell_info_impl(lh_node)
        finally:
            self._in_table_cell = saved_cell

    def _parse_cell_info_impl(self, lh_node) -> dict:
        info = self._parse_cell_geometry(lh_node)
        info['paragraphs'] = []

        # 셀 내부 재귀 파싱 — 문단 + 중첩 컨트롤 모두
        for child in lh_node['children']:
            if child['record'].tag_id == HWPTAG_PARA_HEADER:
                starting_cells = self._section_cells
                starting_document_cells = self._document_cells
                try:
                    elems = self._parse_paragraph_group(child)
                except _HWPStructureError as exc:
                    # 실패한 문단 그룹만 버리고 바깥 표와 다른 셀은 살린다. 실패한 표는
                    # 자기 예산을 되돌렸지만, 같은 그룹에서 먼저 성공한 중첩 표의 예약은
                    # 내용과 함께 버려지므로 그룹 시작 시점으로 되돌린다.
                    self._section_cells = starting_cells
                    self._document_cells = starting_document_cells
                    self._append_fatal_once(exc.key, exc.message)
                    continue
                for e in elems:
                    if hasattr(e, 'runs'):  # Paragraph (도형 내부 텍스트 포함)
                        info['paragraphs'].append(e)
                    elif hasattr(e, 'rows'):  # 중첩 Table
                        if e.rows:  # 실패 폴백 Table() 은 내용이 없다.
                            info['paragraphs'].append(e)
                    elif isinstance(e, Image):
                        # 셀 안 이미지도 유지 (HWPX 와 동일 — BinData 연결 대상)
                        info['paragraphs'].append(e)
                    elif isinstance(e, ChartReference):
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
            elif tag == HWPTAG_SHAPE_COMP_OLE:
                ref = self._ole_to_chart_reference(child['record'].data)
                if ref is not None:
                    flow.append(ref)

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
            elif tag == HWPTAG_SHAPE_COMP_OLE:
                ref = self._ole_to_chart_reference(child['record'].data)
                if ref is not None:
                    out.append(ref)
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

    def _ole_to_chart_reference(self, data):
        # HWPTAG_SHAPE_COMP_OLE: properties(4), extent(8), BinData slot(2).
        self._chart_count += 1
        if self._chart_count > MAX_CHARTS:
            if self._chart_count == MAX_CHARTS + 1:
                self.errors.append('WARN: HWP chart/OLE control count limit exceeded')
            return None
        if len(data) < 14:
            self.errors.append('WARN: HWP chart OLE control truncated')
            return None
        return ChartReference(struct.unpack_from('<H', data, 12)[0])

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
