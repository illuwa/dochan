"""
hwpx/parser.py — HWPX (OWPML) 전체 파서
HWPX는 ZIP 아카이브 내부에 XML 파일들로 구성.
KS X 6101:2011 / OWPML 표준 기반.

구조:
  META-INF/manifest.xml — 파일 목록
  Contents/header.xml — 문서 헤더
  Contents/content.hpf — 섹션 목록
  Contents/section0.xml, section1.xml, ... — 본문
  BinData/ — 바이너리 데이터 (이미지 등)
"""

import posixpath
import zipfile

from lxml import etree

from ..model.document import Document, Section, Paragraph, TextRun
from ..model.table import Table, Cell
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote

# Zip bomb protection constants
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_XML_FILE_SIZE = 32 * 1024 * 1024
MAX_XML_ELEMENTS = 1000000
MAX_COMPRESSION_RATIO = 2000
MAX_META_FILE_SIZE = 32 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10000
MAX_SECTION_COUNT = 1000
MAX_TABLE_CELLS = 200000
MAX_TABLE_SPAN = 200000


class _SectionCountExceeded(ValueError):
    pass

# Safe XML parser (XXE protection)
_safe_xml_parser = etree.XMLParser(resolve_entities=False, no_network=True)

# OWPML 네임스페이스
NS = {
    'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hs': 'http://www.hancom.co.kr/hwpml/2011/section',
    'hc': 'http://www.hancom.co.kr/hwpml/2011/core',
    'hpf': 'urn:oasis:names:tc:opendocument:xmlns:container',
}


class HWPXParser:

    def __init__(self):
        self._reset()

    def _reset(self):
        self.errors = []
        self._part_name_map = {}  # normalized package path -> ZIP entry name
        self._bin_data_map = {}  # exact binary reference -> ZIP entry name
        self._ambiguous_bin_ids = set()
        self._explicit_bin_ids = set()
        self._reported_ambiguous_bin_ids = set()
        self._char_shapes = []
        self._table_cells_remaining = MAX_TABLE_CELLS
        self._table_cell_budget_exhausted = False

    def parse(self, file_path: str) -> Document:
        """HWPX 파일 파싱"""
        self._reset()
        doc = Document(source_format="hwpx")

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ARCHIVE_ENTRIES:
                    raise ValueError(
                        f"HWPX entry count exceeds limit: {len(infos)} > {MAX_ARCHIVE_ENTRIES}"
                    )
                total_size = sum(info.file_size for info in infos)
                if total_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                    raise ValueError(
                        "HWPX total uncompressed size exceeds limit: "
                        f"{total_size} > {MAX_ARCHIVE_UNCOMPRESSED_SIZE}"
                    )
                for info in infos:
                    normalized = _normalize_part_name(info.filename)
                    if normalized in self._part_name_map:
                        raise ValueError(f"duplicate HWPX part name: {normalized}")
                    self._part_name_map[normalized] = info.filename

                mimetype_part = self._part_name_map.get("mimetype")
                if mimetype_part is None:
                    raise ValueError("HWPX mimetype marker is missing")
                mimetype = self._read_zip_part(zf, mimetype_part, 128).decode(
                    "ascii", errors="strict"
                ).strip()
                if mimetype != "application/hwp+zip":
                    raise ValueError(f"invalid HWPX mimetype marker: {mimetype!r}")

                # 바이너리 데이터 목록 수집
                self._collect_bin_data()

                # CharShape 목록 파싱
                self._parse_header_xml(zf)

                # 섹션 파일 목록 추출
                section_files = self._get_section_files(zf)
                if not section_files:
                    self.errors.append("ERR: HWPX section parts not found")

                # 각 섹션 파싱
                for sf in section_files:
                    try:
                        info = zf.getinfo(sf)
                        if info.file_size > MAX_XML_FILE_SIZE:
                            self.errors.append(f"ERR: 섹션 {sf} 크기 초과: {info.file_size} bytes")
                            continue
                        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                            self.errors.append(f"ERR: 섹션 {sf} 압축률 초과")
                            continue
                        xml_data = self._read_zip_part(zf, sf, MAX_XML_FILE_SIZE)
                        section = self._parse_section_xml(xml_data)
                        doc.sections.append(section)
                    except Exception as e:
                        self.errors.append(f"ERR: 섹션 {sf} 파싱 실패: {e}")

                # 이미지 바이너리 데이터 로드
                self._load_image_data(zf, doc)

        except zipfile.BadZipFile:
            self.errors.append("ERR: 유효하지 않은 HWPX 파일")
        except Exception as e:
            self.errors.append(f"ERR: HWPX 파싱 실패: {e}")

        doc.errors = self.errors
        return doc

    def _read_zip_part(self, zf: zipfile.ZipFile, name: str, max_size: int) -> bytes:
        info = zf.getinfo(name)
        if info.file_size > max_size:
            raise ValueError(
                f"{name} size exceeds limit: {info.file_size} > {max_size}"
            )
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError(f"{name} compression ratio exceeds limit")
        return zf.read(name)

    def _parse_header_xml(self, zf: zipfile.ZipFile):
        """Contents/header.xml에서 CharShape 목록 파싱"""
        self._char_shapes = []  # list of dicts: {bold, italic, underline, strikeout, size_pt}

        for candidate in ['Contents/header.xml', 'header.xml']:
            part_name = self._part_name_map.get(candidate)
            if part_name is None:
                continue
            try:
                data = self._read_zip_part(zf, part_name, MAX_META_FILE_SIZE)
                if data.count(b"<") > MAX_XML_ELEMENTS:
                    raise ValueError("HWPX header XML element limit exceeded")
                root = etree.fromstring(data, parser=_safe_xml_parser)

                for elem in root.iter():
                    tag = _local_tag(elem.tag)
                    if tag == 'binItem':
                        self._index_binary_item(elem, candidate)
                    # HWPX: <charPr> (charShape가 아님)
                    if tag == 'charPr' and elem.get('id') is not None:
                        cs = {
                            'bold': False,
                            'italic': False,
                            'underline': False,
                            'strikeout': False,
                            'size_pt': 10.0,
                        }
                        # height 속성 → font size (hundredths of pt)
                        height = elem.get('height')
                        if height:
                            try:
                                cs['size_pt'] = int(height) / 100.0
                            except ValueError:
                                pass
                        # bold/italic/underline/strikeout는 자식 태그로 존재
                        for child in elem:
                            ctag = _local_tag(child.tag)
                            if ctag == 'bold':
                                # <bold/> 빈 태그 존재 = bold
                                cs['bold'] = True
                            elif ctag == 'italic':
                                cs['italic'] = True
                            elif ctag == 'underline':
                                utype = child.get('type', 'NONE')
                                cs['underline'] = utype != 'NONE'
                            elif ctag == 'strikeout':
                                sshape = child.get('shape', 'NONE')
                                cs['strikeout'] = sshape != 'NONE'
                        self._char_shapes.append(cs)
            except Exception as e:
                self.errors.append(f"ERR: HWPX metadata {candidate} parse failed: {e}")
            break

    def _collect_bin_data(self):
        """BinData 폴더의 파일 목록 수집"""
        for normalized, part_name in self._part_name_map.items():
            if not normalized.startswith('BinData/'):
                continue
            basename = posixpath.basename(normalized)
            if not basename:
                continue
            self._register_bin_data_alias(normalized, part_name)
            self._register_bin_data_alias(basename, part_name)
            stem, _ = posixpath.splitext(basename)
            if stem:
                self._register_bin_data_alias(stem, part_name)

    def _register_bin_data_alias(
        self,
        alias: str,
        part_name: str,
        *,
        explicit: bool = False,
    ):
        """Register an exact binary reference, retaining ambiguity instead of guessing."""
        alias = alias.strip().replace('\\', '/')
        if not alias:
            return

        if explicit:
            if alias not in self._explicit_bin_ids:
                self._bin_data_map[alias] = part_name
                self._ambiguous_bin_ids.discard(alias)
                self._explicit_bin_ids.add(alias)
                return
        elif alias in self._explicit_bin_ids or alias in self._ambiguous_bin_ids:
            return

        existing = self._bin_data_map.get(alias)
        if existing is None:
            self._bin_data_map[alias] = part_name
        elif existing != part_name:
            self._bin_data_map.pop(alias, None)
            self._ambiguous_bin_ids.add(alias)

    def _index_binary_item(self, item, owner_part: str):
        """Index an explicit package binary ID without fuzzy filename matching."""
        href = item.get('href', '')
        resolved = self._resolve_manifest_part(owner_part, href)
        if resolved is None or not resolved.startswith('BinData/'):
            return
        part_name = self._part_name_map[resolved]
        for attribute in ('id', 'itemID', 'itemId'):
            item_id = item.get(attribute, '')
            if item_id:
                self._register_bin_data_alias(
                    item_id,
                    part_name,
                    explicit=True,
                )

    def _resolve_bin_data_reference(self, reference: str):
        """Resolve an image reference through the precomputed exact index."""
        reference = reference.strip().replace('\\', '/')
        if not reference:
            return None
        candidates = [reference]
        try:
            normalized = _normalize_part_name(reference)
        except ValueError:
            normalized = reference
        if normalized != reference:
            candidates.append(normalized)

        for candidate in candidates:
            if candidate in self._ambiguous_bin_ids:
                if candidate not in self._reported_ambiguous_bin_ids:
                    self.errors.append(
                        f"WARN: HWPX image reference is ambiguous: {candidate}"
                    )
                    self._reported_ambiguous_bin_ids.add(candidate)
                return None
            part_name = self._bin_data_map.get(candidate)
            if part_name is not None:
                return part_name
        return None

    def _get_section_files(self, zf: zipfile.ZipFile) -> list:
        """content.hpf에서 섹션 파일 목록 추출"""
        section_files = []
        seen_sections = set()

        def add_section(normalized_name):
            if normalized_name in seen_sections:
                return
            part_name = self._part_name_map.get(normalized_name)
            if part_name is None:
                return
            if len(section_files) >= MAX_SECTION_COUNT:
                raise _SectionCountExceeded(
                    "HWPX section count exceeds limit: "
                    f"{len(section_files) + 1} > {MAX_SECTION_COUNT}"
                )
            seen_sections.add(normalized_name)
            section_files.append(part_name)

        # content.hpf 파싱 시도
        hpf_candidates = ['Contents/content.hpf', 'content.hpf']
        for hpf in hpf_candidates:
            hpf_part = self._part_name_map.get(hpf)
            if hpf_part is not None:
                try:
                    hpf_data = self._read_zip_part(zf, hpf_part, MAX_META_FILE_SIZE)
                    if hpf_data.count(b"<") > MAX_XML_ELEMENTS:
                        raise ValueError("HWPX content manifest XML element limit exceeded")
                    root = etree.fromstring(hpf_data, parser=_safe_xml_parser)
                    # rootfile 항목에서 섹션 찾기
                    for item in root.iter():
                        href = item.get('href', '')
                        resolved = self._resolve_manifest_part(hpf, href)
                        if resolved is None:
                            continue

                        if resolved.startswith('BinData/'):
                            self._index_binary_item(item, hpf)

                        if 'section' in href.lower() and href.lower().endswith('.xml'):
                            add_section(resolved)
                except _SectionCountExceeded:
                    raise
                except Exception as e:
                    self.errors.append(f"ERR: HWPX metadata {hpf} parse failed: {e}")
                break

        # 폴백: 직접 section*.xml 찾기
        if not section_files:
            for normalized in sorted(self._part_name_map):
                if 'section' in normalized.lower() and normalized.lower().endswith('.xml'):
                    add_section(normalized)

        return section_files

    def _resolve_manifest_part(self, manifest_name: str, href: str):
        """Resolve a manifest href to one normalized archive part name."""
        href = href.strip()
        if not href or href.replace('\\', '/').startswith('/'):
            return None

        candidates = []
        try:
            candidates.append(_normalize_part_name(href))
        except ValueError:
            pass
        manifest_dir = posixpath.dirname(manifest_name)
        if manifest_dir:
            try:
                candidates.append(
                    _normalize_part_name(posixpath.join(manifest_dir, href))
                )
            except ValueError:
                pass
        if not href.replace('\\', '/').startswith('Contents/'):
            try:
                candidates.append(
                    _normalize_part_name(posixpath.join('Contents', href))
                )
            except ValueError:
                pass

        for candidate in dict.fromkeys(candidates):
            if candidate in self._part_name_map:
                return candidate
        return None

    def _parse_section_xml(self, xml_data: bytes) -> Section:
        """섹션 XML → Section 모델"""
        if xml_data.count(b"<") > MAX_XML_ELEMENTS:
            raise ValueError("HWPX section XML element limit exceeded")
        section = Section()
        root = etree.fromstring(xml_data, parser=_safe_xml_parser)

        # ★ 최상위 <p>만 처리 (직접 자식)
        #   표 셀 안의 <p>는 _parse_table_cell에서 재귀 처리되므로
        #   root.iter()를 쓰면 중복됨
        for child in root:
            tag = _local_tag(child.tag)
            if tag == 'p':
                elements = self._parse_paragraph_elem(child)
                section.elements.extend(elements)

        return section

    @staticmethod
    def _detect_heading_level_by_font(runs) -> int:
        """Font size 기반 제목 레벨 감지"""
        if runs:
            size = runs[0].font_size_pt
            if size >= 20:
                return 1
            elif size >= 16:
                return 2
            elif size >= 13:
                return 3
        return 0

    def _parse_paragraph_elem(self, p_elem) -> list:
        """<p> 요소 → Paragraph/Table/등"""
        elements = []

        # 텍스트 수집
        runs = []
        for child in p_elem:
            tag = _local_tag(child.tag)

            if tag == 'run':
                # run 안에 tbl/pic이 있을 수 있음 (실제 HWPX 구조)
                inline_elems = self._parse_run_with_objects(child)
                for item in inline_elems:
                    if isinstance(item, TextRun):
                        runs.append(item)
                    else:
                        # 표/이미지 등 → 앞 텍스트 먼저 플러시
                        if runs:
                            para = Paragraph(runs=runs)
                            para.heading_level = self._detect_heading_level_by_font(runs)
                            if para.text.strip():
                                elements.append(para)
                            runs = []
                        elements.append(item)
            elif tag == 'ctrl':
                ctrl_elem = self._parse_ctrl(child)
                if ctrl_elem:
                    if runs:
                        para = Paragraph(runs=runs)
                        para.heading_level = self._detect_heading_level_by_font(runs)
                        if para.text.strip():
                            elements.append(para)
                        runs = []
                    elements.append(ctrl_elem)

        # 남은 텍스트
        if runs:
            para = Paragraph(runs=runs)
            para.heading_level = self._detect_heading_level_by_font(runs)
            if para.text.strip():
                elements.append(para)

        return elements

    def _parse_run_with_objects(self, run_elem) -> list:
        """<run> 내부의 텍스트 + 인라인 개체(표, 이미지) 파싱"""
        results = []
        text_parts = []
        font_size_pt = 10.0
        bold = False
        italic = False
        underline = False
        strikeout = False

        # CharShape lookup from charPrIDRef
        cs_id_str = run_elem.get('charPrIDRef', '')
        if cs_id_str and hasattr(self, '_char_shapes'):
            try:
                cs_id = int(cs_id_str)
                if 0 <= cs_id < len(self._char_shapes):
                    cs = self._char_shapes[cs_id]
                    bold = cs['bold']
                    italic = cs['italic']
                    font_size_pt = cs['size_pt']
                    underline = cs['underline']
                    strikeout = cs['strikeout']
            except (ValueError, IndexError):
                pass

        for child in run_elem:
            tag = _local_tag(child.tag)

            if tag == 'charPrIDRef' or tag == 'charPr':
                # charPr 속성은 별도 처리하지 않고 charPrIDRef 기반
                pass
            elif tag == 't':
                if child.text:
                    text_parts.append(child.text)
            elif tag == 'tab':
                text_parts.append('\t')
            elif tag == 'lineBreak':
                text_parts.append('\n')
            elif tag == 'tbl':
                # 앞 텍스트 먼저 TextRun으로
                if text_parts:
                    results.append(TextRun(
                        text=''.join(text_parts),
                        bold=bold, italic=italic,
                        font_size_pt=font_size_pt,
                        underline=underline, strikeout=strikeout,
                    ))
                    text_parts = []
                results.append(self._parse_table_elem(child))
            elif tag == 'pic':
                if text_parts:
                    results.append(TextRun(
                        text=''.join(text_parts),
                        bold=bold, italic=italic,
                        font_size_pt=font_size_pt,
                        underline=underline, strikeout=strikeout,
                    ))
                    text_parts = []
                results.append(self._parse_picture_elem(child))
            elif tag == 'ctrl':
                # <run> 안의 <ctrl> — 머리글/바닥글/각주 등
                ctrl_result = self._parse_ctrl(child)
                if ctrl_result:
                    if text_parts:
                        results.append(TextRun(
                            text=''.join(text_parts),
                            bold=bold, italic=italic,
                            font_size_pt=font_size_pt,
                            underline=underline, strikeout=strikeout,
                        ))
                        text_parts = []
                    results.append(ctrl_result)

        # 남은 텍스트
        if text_parts:
            text = ''.join(text_parts)
            if text:
                results.append(TextRun(
                    text=text,
                    bold=bold, italic=italic,
                    font_size_pt=font_size_pt,
                    underline=underline, strikeout=strikeout,
                ))

        return results

    def _parse_ctrl(self, ctrl_elem):
        """<ctrl> 요소 → Table/Equation/Image 등"""
        # 표
        for child in ctrl_elem.iter():
            tag = _local_tag(child.tag)

            if tag == 'tbl':
                return self._parse_table_elem(child)
            elif tag == 'equation':
                script = child.text or child.get('script', '')
                return Equation(script=script)
            elif tag == 'pic':
                return self._parse_picture_elem(child)
            elif tag == 'header':
                return self._parse_header_footer_elem(child, 'header')
            elif tag == 'footer':
                return self._parse_header_footer_elem(child, 'footer')
            elif tag == 'footNote':
                return self._parse_footnote_elem(child, 'footnote')
            elif tag == 'endNote':
                return self._parse_footnote_elem(child, 'endnote')

        return None

    def _parse_header_footer_elem(self, elem, hf_type: str):
        """<header>/<footer> → HeaderFooter"""
        hf = HeaderFooter(type=hf_type)

        for child in elem:
            tag = _local_tag(child.tag)
            if tag == 'subList':
                for sub in child:
                    if _local_tag(sub.tag) == 'p':
                        elems = self._parse_paragraph_elem(sub)
                        for e in elems:
                            if hasattr(e, 'runs'):
                                hf.paragraphs.append(e)
        return hf

    def _parse_footnote_elem(self, elem, fn_type: str):
        """<footNote>/<endNote> → Footnote"""
        fn = Footnote(type=fn_type)

        for child in elem:
            tag = _local_tag(child.tag)
            if tag == 'subList':
                for sub in child:
                    if _local_tag(sub.tag) == 'p':
                        elems = self._parse_paragraph_elem(sub)
                        for e in elems:
                            if hasattr(e, 'runs'):
                                fn.paragraphs.append(e)
        return fn

    def _parse_table_elem(self, tbl_elem) -> Table:
        """<tbl> → Table"""
        table = Table()
        rows = []

        for child in tbl_elem:
            tag = _local_tag(child.tag)
            if tag == 'tr':
                row = self._parse_table_row(child)
                rows.append(row)
                if self._table_cell_budget_exhausted:
                    break

        table.rows = rows
        return table

    def _parse_table_row(self, tr_elem) -> list:
        """<tr> → [Cell, ...]"""
        cells = []

        for child in tr_elem:
            tag = _local_tag(child.tag)
            if tag == 'tc':
                if not self._reserve_table_cell():
                    break
                cell = self._parse_table_cell(child)
                cells.append(cell)
                if self._table_cell_budget_exhausted:
                    break

        return cells

    def _reserve_table_cell(self) -> bool:
        if self._table_cell_budget_exhausted:
            return False
        if self._table_cells_remaining <= 0:
            error = (
                "ERR: HWPX table cell limit exceeded: "
                f"more than {MAX_TABLE_CELLS} cells"
            )
            if error not in self.errors:
                self.errors.append(error)
            self._table_cell_budget_exhausted = True
            return False
        self._table_cells_remaining -= 1
        return True

    def _parse_table_cell(self, tc_elem) -> Cell:
        """<tc> → Cell"""
        cell = Cell()

        # 병합 속성 — tc 속성 또는 하위 cellSpan 태그
        col_span = self._validated_table_span(tc_elem.get('colSpan'))
        row_span = self._validated_table_span(tc_elem.get('rowSpan'))
        if col_span is not None:
            cell.col_span = col_span
        if row_span is not None:
            cell.row_span = row_span

        # <hp:cellSpan colSpan="1" rowSpan="1"/> 태그에서도 읽기
        for child in tc_elem:
            tag = _local_tag(child.tag)
            if tag == 'cellSpan':
                cs = child.get('colSpan')
                rs = child.get('rowSpan')
                child_col_span = self._validated_table_span(cs)
                child_row_span = self._validated_table_span(rs)
                if child_col_span is not None:
                    cell.col_span = child_col_span
                if child_row_span is not None:
                    cell.row_span = child_row_span

        if cell.col_span * cell.row_span > MAX_TABLE_CELLS:
            self._record_invalid_table_span()
            cell.col_span = 1
            cell.row_span = 1

        # 셀 내 문단+이미지 — 직접 자식 <subList> 또는 <p>에서
        for child in tc_elem:
            tag = _local_tag(child.tag)
            if tag == 'subList':
                for sub_child in child:
                    if _local_tag(sub_child.tag) == 'p':
                        elems = self._parse_paragraph_elem(sub_child)
                        for e in elems:
                            cell.paragraphs.append(e)  # Paragraph + Image 모두
            elif tag == 'p':
                elems = self._parse_paragraph_elem(child)
                for e in elems:
                    cell.paragraphs.append(e)

        return cell

    def _validated_table_span(self, raw_value):
        if raw_value is None:
            return None
        value = raw_value.strip()
        digits = value.lstrip('0') or '0'
        max_digits = str(MAX_TABLE_SPAN)
        if (
            not value
            or not value.isascii()
            or not value.isdigit()
            or len(digits) > len(max_digits)
        ):
            self._record_invalid_table_span()
            return 1
        span = int(digits)
        if span <= 0 or span > MAX_TABLE_SPAN:
            self._record_invalid_table_span()
            return 1
        return span

    def _record_invalid_table_span(self):
        error = "ERR: HWPX invalid table span value"
        if error not in self.errors:
            self.errors.append(error)

    def _parse_picture_elem(self, pic_elem) -> Image:
        """<pic> → Image"""
        img = Image()

        for child in pic_elem.iter():
            tag = _local_tag(child.tag)
            if tag == 'img':
                # 속성명: binaryItemIDRef 또는 binaryItemId
                bid = (child.get('binaryItemIDRef', '') or
                       child.get('binaryItemId', '') or
                       child.get('binaryItemIdRef', ''))
                if bid:
                    part_name = self._resolve_bin_data_reference(bid)
                    if part_name is not None:
                        img.filename = posixpath.basename(
                            part_name.replace('\\', '/')
                        )
                        img._hwpx_part_name = part_name
                    else:
                        img.filename = bid

        return img

    def _load_image_data(self, zf: zipfile.ZipFile, doc: Document):
        """Document 내 모든 Image 객체에 ZIP 바이너리 데이터 로드"""
        images = doc.find_all('image')
        for img in images:
            if img.filename and not img.has_data:
                zip_name = getattr(img, '_hwpx_part_name', None)
                if zip_name is None:
                    zip_name = self._resolve_bin_data_reference(img.filename)
                if zip_name is None:
                    continue
                try:
                    info = zf.getinfo(zip_name)
                    if info.file_size > MAX_FILE_SIZE:
                        self.errors.append(f"WARN: 이미지 {zip_name} 크기 초과: {info.file_size} bytes")
                        continue
                    if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                        self.errors.append(f"WARN: 이미지 {zip_name} 압축률 초과")
                        continue
                    img.image_data = self._read_zip_part(
                        zf,
                        zip_name,
                        MAX_FILE_SIZE,
                    )
                except Exception as e:
                    self.errors.append(f"ERR: HWPX image {zip_name} read failed: {e}")


def _local_tag(tag: str) -> str:
    """'{namespace}localname' → 'localname'"""
    if not isinstance(tag, str):
        return ""
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def _normalize_part_name(name: str) -> str:
    """Return a canonical, relative POSIX path for one ZIP package part."""
    normalized = posixpath.normpath(name.replace('\\', '/'))
    if (
        not normalized
        or normalized == '.'
        or normalized == '..'
        or normalized.startswith('../')
        or normalized.startswith('/')
    ):
        raise ValueError(f"invalid HWPX part name: {name!r}")
    return normalized
