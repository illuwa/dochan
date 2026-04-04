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

import zipfile
import os
from typing import Optional
from lxml import etree

from ..model.document import Document, Section, Paragraph, TextRun
from ..model.table import Table, Cell
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote

# Zip bomb protection constants
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_COMPRESSION_RATIO = 100

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
        self.errors = []
        self._bin_data_map = {}  # binItemId → filename

    def parse(self, file_path: str) -> Document:
        """HWPX 파일 파싱"""
        doc = Document()

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # 바이너리 데이터 목록 수집
                self._collect_bin_data(zf)

                # CharShape 목록 파싱
                self._parse_header_xml(zf)

                # 섹션 파일 목록 추출
                section_files = self._get_section_files(zf)

                # 각 섹션 파싱
                for sf in section_files:
                    try:
                        info = zf.getinfo(sf)
                        if info.file_size > MAX_FILE_SIZE:
                            self.errors.append(f"섹션 {sf} 크기 초과: {info.file_size} bytes")
                            continue
                        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                            self.errors.append(f"섹션 {sf} 압축률 초과")
                            continue
                        xml_data = zf.read(sf)
                        section = self._parse_section_xml(xml_data)
                        doc.sections.append(section)
                    except Exception as e:
                        self.errors.append(f"섹션 {sf} 파싱 실패: {e}")

                # 이미지 바이너리 데이터 로드
                self._load_image_data(zf, doc)

        except zipfile.BadZipFile:
            self.errors.append("ERR: 유효하지 않은 HWPX 파일")
        except Exception as e:
            self.errors.append(f"ERR: HWPX 파싱 실패: {e}")

        doc.errors = self.errors
        return doc

    def _parse_header_xml(self, zf: zipfile.ZipFile):
        """Contents/header.xml에서 CharShape 목록 파싱"""
        self._char_shapes = []  # list of dicts: {bold, italic, underline, strikeout, size_pt}

        for candidate in ['Contents/header.xml', 'header.xml']:
            if candidate not in zf.namelist():
                continue
            try:
                data = zf.read(candidate)
                root = etree.fromstring(data, parser=_safe_xml_parser)

                for elem in root.iter():
                    tag = _local_tag(elem.tag)
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
            except Exception:
                pass
            break

    def _collect_bin_data(self, zf: zipfile.ZipFile):
        """BinData 폴더의 파일 목록 수집"""
        for name in zf.namelist():
            if name.startswith('BinData/'):
                basename = os.path.basename(name)
                if basename:
                    # 파일명에서 ID 추출 시도
                    base = basename.split('.')[0]
                    self._bin_data_map[basename] = name

    def _get_section_files(self, zf: zipfile.ZipFile) -> list:
        """content.hpf에서 섹션 파일 목록 추출"""
        section_files = []

        # content.hpf 파싱 시도
        hpf_candidates = ['Contents/content.hpf', 'content.hpf']
        for hpf in hpf_candidates:
            if hpf in zf.namelist():
                try:
                    hpf_data = zf.read(hpf)
                    root = etree.fromstring(hpf_data, parser=_safe_xml_parser)
                    # rootfile 항목에서 섹션 찾기
                    for item in root.iter():
                        href = item.get('href', '')
                        if 'section' in href.lower() and href.endswith('.xml'):
                            full_path = f"Contents/{href}" if not href.startswith('Contents/') else href
                            if full_path in zf.namelist():
                                section_files.append(full_path)
                except Exception:
                    pass
                break

        # 폴백: 직접 section*.xml 찾기
        if not section_files:
            for name in sorted(zf.namelist()):
                if 'section' in name.lower() and name.endswith('.xml'):
                    section_files.append(name)

        return section_files

    def _parse_section_xml(self, xml_data: bytes) -> Section:
        """섹션 XML → Section 모델"""
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

        table.rows = rows
        return table

    def _parse_table_row(self, tr_elem) -> list:
        """<tr> → [Cell, ...]"""
        cells = []

        for child in tr_elem:
            tag = _local_tag(child.tag)
            if tag == 'tc':
                cell = self._parse_table_cell(child)
                cells.append(cell)

        return cells

    def _parse_table_cell(self, tc_elem) -> Cell:
        """<tc> → Cell"""
        cell = Cell()

        # 병합 속성 — tc 속성 또는 하위 cellSpan 태그
        col_span = tc_elem.get('colSpan')
        row_span = tc_elem.get('rowSpan')
        if col_span:
            try:
                cell.col_span = int(col_span)
            except ValueError:
                pass
        if row_span:
            try:
                cell.row_span = int(row_span)
            except ValueError:
                pass

        # <hp:cellSpan colSpan="1" rowSpan="1"/> 태그에서도 읽기
        for child in tc_elem:
            tag = _local_tag(child.tag)
            if tag == 'cellSpan':
                cs = child.get('colSpan')
                rs = child.get('rowSpan')
                if cs:
                    try:
                        cell.col_span = int(cs)
                    except ValueError:
                        pass
                if rs:
                    try:
                        cell.row_span = int(rs)
                    except ValueError:
                        pass

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
                    img.filename = bid
                    for key, path in self._bin_data_map.items():
                        if bid in key:
                            img.filename = key
                            break

        return img

    def _load_image_data(self, zf: zipfile.ZipFile, doc: Document):
        """Document 내 모든 Image 객체에 ZIP 바이너리 데이터 로드"""
        images = doc.find_all('image')
        for img in images:
            if img.filename and not img.has_data:
                for zip_name in zf.namelist():
                    if zip_name.startswith('BinData/') and img.filename in zip_name:
                        try:
                            info = zf.getinfo(zip_name)
                            if info.file_size > MAX_FILE_SIZE:
                                self.errors.append(f"이미지 {zip_name} 크기 초과: {info.file_size} bytes")
                                break
                            if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                                self.errors.append(f"이미지 {zip_name} 압축률 초과")
                                break
                            img.image_data = zf.read(zip_name)
                        except Exception:
                            pass
                        break


def _local_tag(tag: str) -> str:
    """'{namespace}localname' → 'localname'"""
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag
