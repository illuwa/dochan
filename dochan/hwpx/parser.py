"""
hwpx/parser.py — HWPX (OWPML) 전체 파서
HWPX는 ZIP 아카이브 내부에 XML 파일들로 구성.
KS X 6101:2011 / OWPML 표준 기반.

구조:
  META-INF/manifest.xml — 파일 목록
  Contents/header.xml — 문서 헤더 (글꼴/글자모양/문단모양/스타일)
  Contents/content.hpf — 섹션 목록 + 바이너리 항목 매핑
  Contents/section0.xml, section1.xml, ... — 본문
  BinData/ — 바이너리 데이터 (이미지 등)
"""

import re
import zipfile
import os
from typing import Optional
from lxml import etree

from ..model.document import Document, Section, Paragraph, TextRun
from ..model.table import Table, Cell
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote
from ..model.style import FaceName, ParaShape, StyleEntry
from ..hwp.records.char_shape import CharShape
from ..hwp.records.ctrl_header import field_command_to_url

# Zip bomb protection constants
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
# 단일 deflate 스트림의 압축률만으로는 zip bomb 여부를 판단하지 않는다.
# BMP 등 비압축 픽셀 포맷은 단색 영역이 넓은 실사용 이미지에서도 흔히 100배를
# 넘긴다 (실측: 기상청 보도자료의 7.85MB BMP 차트가 101.1배). 실질적 방어는
# 절대 해제 크기 상한(MAX_FILE_SIZE)이 담당하므로, 여기서는 그 상한 근처까지
# 도달하고도 원본이 비정상적으로 작은 명백한 이상치만 걸러낸다.
MAX_COMPRESSION_RATIO = 2000


def _compression_ratio_exceeded(file_size: int, compress_size: int) -> bool:
    """zip 항목의 압축 해제 비율이 이상치로 볼 만큼 큰지 판단."""
    return compress_size > 0 and file_size / compress_size > MAX_COMPRESSION_RATIO

# 표/도형 폭주 방어
MAX_TABLE_CELLS = 1_000_000          # 표 하나가 주장할 수 있는 최대 격자 크기
# 문서 전체에서 실체화할 셀 총량. 표를 여럿 두어 상한을 우회하는 메모리 폭탄을 막는다.
# 실측 기준 실문서 80개의 셀 총합이 31,399개이므로 20만이면 충분히 여유롭다.
MAX_DOCUMENT_CELLS = 200_000
MAX_DRAWING_DEPTH = 32
MAX_FIELD_DEPTH = 64                 # 짝이 안 맞는 fieldBegin 이 무한히 쌓이는 것을 막는다
MAX_FONT_SIZE_PT = 4096.0            # HWP 스펙상 글자 크기 상한

# header.xml / content.hpf 도 zip bomb 대상이다
MAX_META_FILE_SIZE = 32 * 1024 * 1024

# OUTLINE 레벨을 Markdown 헤딩으로 승격할 상한.
# 한글 규정문서는 '개요 5' 같은 깊은 레벨을 평범한 본문 열거 항목에 쓰는 일이 잦아서,
# 전 레벨을 승격하면 목록이 통째로 헤딩이 된다.
MAX_OUTLINE_HEADING_LEVEL = 3

# Safe XML parser (XXE protection)
_safe_xml_parser = etree.XMLParser(resolve_entities=False, no_network=True)

# XML 1.0 Char 생산 규칙에 없는 C0 제어문자 (탭/개행/캐리지리턴은 허용됨).
# UTF-8 에서는 0x00-0x1F 범위가 항상 단독 바이트로만 나타나므로(멀티바이트
# 시퀀스의 후행 바이트는 절대 0x80 미만일 수 없다) 디코딩 전에 바이트 단위로
# 제거해도 안전하다.
_INVALID_XML_CHAR_RE = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _parse_xml_tolerant(data: bytes):
    """일부 실제 문서에는 XML 1.0에서 금지된 제어문자가 하나씩 섞여 있어
    lxml이 전체를 못 읽는 경우가 있다. 그런 경우 무효 문자만 제거하고
    한 번 더 시도한다 — 그래도 안 되면(다른 종류의 오류) 원래 예외를
    그대로 올려 호출자의 기존 처리 로직을 그대로 탄다.
    """
    try:
        return etree.fromstring(data, parser=_safe_xml_parser)
    except etree.XMLSyntaxError:
        cleaned = _INVALID_XML_CHAR_RE.sub(b"", data)
        if cleaned == data:
            raise
        return etree.fromstring(cleaned, parser=_safe_xml_parser)

# OWPML 네임스페이스
NS = {
    'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hs': 'http://www.hancom.co.kr/hwpml/2011/section',
    'hc': 'http://www.hancom.co.kr/hwpml/2011/core',
    'hpf': 'urn:oasis:names:tc:opendocument:xmlns:container',
}

# <hp:switch>/<hp:case required-namespace="..."> 에서 우리가 해석할 수 있다고 선언하는 확장.
# 이 목록에 없는 case 는 건너뛰고 <hp:default> 를 쓴다.
#
# HwpUnitChar 는 일부러 제외한다. 그 분기의 값은 default 와 단위계가 달라 정확히 1/2 스케일이며
# (실측: 같은 문서의 .hwp/.hwpx 쌍 76개에서 여백 3468건이 예외 없이 2.0배 차이),
# 우리는 그 단위를 해석하지 않는다. default 를 써야 HWP 바이너리 경로와 값이 일치한다.
SUPPORTED_SWITCH_NAMESPACES = {
    'http://www.hancom.co.kr/hwpml/2016/paragraph',
}

# <hp:run> 아래에 올 수 있는 도형 컨테이너. 내부에 <hp:drawText> 로 텍스트를 품는다.
# compose(글자 겹치기)는 여기 넣지 않는다 — drawText 가 없고 composeText 속성이 본문이다.
DRAWING_TAGS = {
    'rect', 'ellipse', 'line', 'connectLine', 'curve', 'polygon',
    'arc', 'container', 'ole',
}

# 스타일 이름에서 개요 수준을 읽어내기 위한 패턴 ("개요 1", "Outline 2", "Heading 3")
_STYLE_HEADING_RE = re.compile(r'^\s*(?:개요|outline|heading)\s*(\d+)\s*$', re.IGNORECASE)

_ALIGN_MAP = {'JUSTIFY': 0, 'LEFT': 1, 'RIGHT': 2, 'CENTER': 3, 'DISTRIBUTE': 4}
_STYLE_TYPE_MAP = {'PARA': 0, 'CHAR': 1}


class HWPXParser:

    def __init__(self):
        self._reset()

    def _reset(self):
        """인스턴스 상태 초기화. 같은 파서로 두 번 parse 해도 값이 섞이지 않게 한다."""
        self.errors = []
        self._bin_path_by_id = {}     # content.hpf 의 item id → zip 내 전체 경로
        self._bin_path_by_stem = {}   # 파일명(확장자 제외) → zip 내 전체 경로 (폴백)
        self._section_files = []
        self._char_shapes = []        # 본문 서식 조회용 (dict 목록)
        self._para_prs = {}           # paraPr id → {'heading_type', 'heading_level'}
        self._styles = {}             # style id → {'name', 'eng_name', 'para_pr_id'}
        self._face_names = []
        self._para_shapes = []
        self._style_entries = []
        self._char_shape_entries = []
        self._link_stack = []         # 문단 스코프 하이퍼링크 스택 (top 이 현재 유효 URL)
        self._field_overflow = 0      # 상한을 넘겨 버려진 fieldBegin 수 (짝 맞추기용)
        self._note_seq = 0            # 각주/미주 참조 번호
        self._cell_budget = MAX_DOCUMENT_CELLS

    def parse(self, file_path: str) -> Document:
        """HWPX 파일 파싱"""
        self._reset()
        doc = Document()
        doc.source_format = "hwpx"

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # content.hpf 를 한 번만 읽어 섹션 목록과 바이너리 매핑을 함께 얻는다
                self._read_content_hpf(zf)

                # 바이너리 데이터 인덱스 (content.hpf 에 없는 항목 폴백)
                self._collect_bin_data(zf)

                # 글자모양/문단모양/스타일 파싱
                self._parse_header_xml(zf)

                # 각 섹션 파싱
                for sf in self._section_files:
                    try:
                        info = zf.getinfo(sf)
                        if info.file_size > MAX_FILE_SIZE:
                            self.errors.append(f"섹션 {sf} 크기 초과: {info.file_size} bytes")
                            continue
                        if _compression_ratio_exceeded(info.file_size, info.compress_size):
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

        # HWP 경로(reader.py)와 대칭이 되도록 서식 목록을 문서에 실어준다
        doc.char_shapes = self._char_shape_entries
        doc.para_shapes = self._para_shapes
        doc.styles = self._style_entries
        doc.face_names = self._face_names
        doc.errors = self.errors
        return doc

    # ── content.hpf / BinData ──

    def _read_content_hpf(self, zf: zipfile.ZipFile):
        """content.hpf 에서 섹션 목록과 바이너리 항목 매핑을 한 번에 읽는다."""
        self._section_files = []
        names = zf.namelist()

        for hpf in ('Contents/content.hpf', 'content.hpf'):
            if hpf not in names:
                continue
            data = self._read_meta(zf, hpf)
            if data is None:
                break
            try:
                root = _parse_xml_tolerant(data)
            except Exception as e:
                self.errors.append(f"content.hpf 파싱 실패: {e}")
                break

            for item in root.iter():
                href = item.get('href', '')
                if not href:
                    continue
                full_path = href if href.startswith('Contents/') else f"Contents/{href}"

                item_id = item.get('id', '')
                if item_id and href.startswith('BinData/'):
                    if href in names:
                        self._bin_path_by_id[item_id] = href
                    elif full_path in names:
                        self._bin_path_by_id[item_id] = full_path

                if 'section' in href.lower() and href.endswith('.xml'):
                    if full_path in names and full_path not in self._section_files:
                        self._section_files.append(full_path)
            break

        # 폴백: content.hpf 가 없거나 섹션을 못 찾은 경우 직접 탐색
        if not self._section_files:
            for name in sorted(names):
                if 'section' in name.lower() and name.endswith('.xml'):
                    self._section_files.append(name)

    def _read_meta(self, zf: zipfile.ZipFile, name: str):
        """메타 XML(content.hpf / header.xml)도 zip bomb 가드를 통과시킨다."""
        try:
            info = zf.getinfo(name)
        except KeyError:
            return None
        if info.file_size > MAX_META_FILE_SIZE:
            self.errors.append(f"{name} 크기 초과: {info.file_size} bytes")
            return None
        if _compression_ratio_exceeded(info.file_size, info.compress_size):
            self.errors.append(f"{name} 압축률 초과")
            return None
        try:
            return zf.read(name)
        except Exception as e:
            self.errors.append(f"{name} 읽기 실패: {e}")
            return None

    def _collect_bin_data(self, zf: zipfile.ZipFile):
        """BinData 폴더의 파일 목록을 stem 기준으로 색인 (content.hpf 매핑의 폴백)"""
        for name in zf.namelist():
            if not name.startswith('BinData/'):
                continue
            basename = os.path.basename(name)
            if not basename:
                continue
            stem = os.path.splitext(basename)[0]
            # 정확 일치를 우선하기 위해 먼저 들어온 항목을 유지한다
            self._bin_path_by_stem.setdefault(stem, name)
            self._bin_path_by_stem.setdefault(basename, name)

    def _resolve_bin_path(self, bin_id: str) -> str:
        """binaryItemIDRef → zip 내 전체 경로. 부분 문자열 매칭을 쓰지 않는다."""
        if not bin_id:
            return ""
        path = self._bin_path_by_id.get(bin_id)
        if path:
            return path
        return self._bin_path_by_stem.get(bin_id, "")

    # ── header.xml ──

    def _parse_header_xml(self, zf: zipfile.ZipFile):
        """Contents/header.xml에서 글자모양/문단모양/스타일/글꼴 파싱"""
        self._char_shapes = []

        names = zf.namelist()
        for candidate in ('Contents/header.xml', 'header.xml'):
            if candidate not in names:
                continue
            data = self._read_meta(zf, candidate)
            if data is None:
                break
            # 서식은 부가 정보다. 여기서 무슨 일이 나든 본문 파싱을 막아서는 안 된다.
            try:
                root = _parse_xml_tolerant(data)
                for elem in root.iter():
                    tag = _local_tag(elem.tag)
                    if tag == 'charPr' and elem.get('id') is not None:
                        self._collect_char_pr(elem)
                    elif tag == 'paraPr' and elem.get('id') is not None:
                        self._collect_para_pr(elem)
                    elif tag == 'style' and elem.get('id') is not None:
                        self._collect_style(elem)
                    elif tag == 'font':
                        # OWPML 은 <hh:font face="굴림체" type="TTF"/> 로 face 속성을 쓴다.
                        name = elem.get('face') or elem.get('name') or ''
                        if name:
                            face = FaceName()
                            face.name = name
                            self._face_names.append(face)
            except Exception as e:
                self.errors.append(f"header.xml 파싱 실패: {e}")
            break

        self._drop_blanket_strikeout()

    def _drop_blanket_strikeout(self):
        """모든 글자모양에 취소선이 걸려 있으면 문서 기본값으로 보고 해제한다.

        <hh:strikeout> 는 취소선 '모양'만 담고 적용 여부를 따로 두지 않는다.
        대부분의 생성기는 미적용을 shape="NONE" 으로 쓰지만(실측: HWP 바이너리의
        취소선 비트 개수와 정확히 일치), 일부 문서는 모양 기본값을 전 글자모양에
        박아둔다. 그 경우 본문 전체가 취소선으로 렌더되므로 걸러낸다.
        """
        if len(self._char_shapes) < 5:
            return
        if not all(cs['strikeout'] for cs in self._char_shapes):
            return
        for cs in self._char_shapes:
            cs['strikeout'] = False
        for entry in self._char_shape_entries:
            entry.strikeout = 0

    def _collect_char_pr(self, elem):
        """<hh:charPr> → 본문 조회용 dict + Document.char_shapes 용 CharShape"""
        cs = {
            'bold': False,
            'italic': False,
            'underline': False,
            'strikeout': False,
            'size_pt': 10.0,
        }
        height = elem.get('height')
        if height:
            try:
                size = int(height) / 100.0
            except (ValueError, TypeError, OverflowError):
                size = 0.0
            if 0.0 < size <= MAX_FONT_SIZE_PT:
                cs['size_pt'] = size

        for child in elem:
            ctag = _local_tag(child.tag)
            if ctag == 'bold':
                cs['bold'] = True
            elif ctag == 'italic':
                cs['italic'] = True
            elif ctag == 'underline':
                cs['underline'] = child.get('type', 'NONE') != 'NONE'
            elif ctag == 'strikeout':
                cs['strikeout'] = child.get('shape', 'NONE') != 'NONE'

        self._char_shapes.append(cs)

        entry = CharShape()
        entry.base_size = int(round(cs['size_pt'] * 100))  # size_pt 는 읽기 전용 프로퍼티
        entry.bold = cs['bold']
        entry.italic = cs['italic']
        entry.underline_type = 1 if cs['underline'] else 0
        entry.strikeout = 1 if cs['strikeout'] else 0
        self._char_shape_entries.append(entry)

    def _collect_para_pr(self, elem):
        """<hh:paraPr> → 개요 정보 + Document.para_shapes 용 ParaShape"""
        para_pr_id = _int_attr(elem, 'id', -1)
        heading = _find_child(elem, 'heading')
        info = {'heading_type': 'NONE', 'heading_level': 0}
        if heading is not None:
            info['heading_type'] = (heading.get('type') or 'NONE').upper()
            info['heading_level'] = _int_attr(heading, 'level', 0)
        if para_pr_id >= 0:
            self._para_prs[para_pr_id] = info

        shape = ParaShape()
        align = _find_child(elem, 'align')
        if align is not None:
            shape.align = _ALIGN_MAP.get((align.get('horizontal') or '').upper(), 0)
        margin = _find_child(elem, 'margin')
        if margin is not None:
            left = _find_child(margin, 'left')
            right = _find_child(margin, 'right')
            intent = _find_child(margin, 'intent')
            if left is not None:
                shape.left_margin = _int_attr(left, 'value', 0)
            if right is not None:
                shape.right_margin = _int_attr(right, 'value', 0)
            if intent is not None:
                shape.indent = _int_attr(intent, 'value', 0)
        spacing = _find_child(elem, 'lineSpacing')
        if spacing is not None:
            shape.line_spacing = _int_attr(spacing, 'value', 0)
        if info['heading_type'] == 'OUTLINE':
            shape.heading_type = 1
        self._para_shapes.append(shape)

    def _collect_style(self, elem):
        """<hh:style> → 이름 기반 개요 판별용 맵 + Document.styles 용 StyleEntry"""
        style_id = _int_attr(elem, 'id', -1)
        name = elem.get('name', '') or ''
        eng_name = elem.get('engName', '') or ''
        para_pr_id = _int_attr(elem, 'paraPrIDRef', -1)
        char_pr_id = _int_attr(elem, 'charPrIDRef', -1)
        if style_id >= 0:
            self._styles[style_id] = {
                'name': name,
                'eng_name': eng_name,
                'para_pr_id': para_pr_id,
            }
        self._style_entries.append(StyleEntry(
            name=name,
            type=_STYLE_TYPE_MAP.get((elem.get('type') or '').upper(), 0),
            char_shape_id=char_pr_id,
            para_shape_id=para_pr_id,
        ))

    # ── 섹션 ──

    def _parse_section_xml(self, xml_data: bytes) -> Section:
        """섹션 XML → Section 모델"""
        section = Section()
        root = _parse_xml_tolerant(xml_data)

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
        """Font size 기반 제목 레벨 감지 (개요 정보가 없을 때의 폴백)"""
        if runs:
            size = runs[0].font_size_pt
            if size >= 20:
                return 1
            elif size >= 16:
                return 2
            elif size >= 13:
                return 3
        return 0

    def _heading_level_for(self, p_elem, runs) -> int:
        """개요(OUTLINE) 정보 → 스타일 이름 → 폰트 크기 순으로 제목 수준을 정한다."""
        style_id = _int_attr(p_elem, 'styleIDRef', -1)
        style = self._styles.get(style_id)

        if style:
            # (a) 스타일 이름이 "개요 N" / "Outline N" / "Heading N"
            level = _heading_level_from_style_name(style['name']) or \
                _heading_level_from_style_name(style['eng_name'])
            if level and level <= MAX_OUTLINE_HEADING_LEVEL:
                return level

            # (b) 스타일이 가리키는 paraPr 의 개요 정보
            #     실측상 본문이 OUTLINE 에 닿는 경로는 거의 이것뿐이다.
            level = self._outline_level(style['para_pr_id'])
            if level:
                return level

        # (c) 문단 자신의 paraPr
        level = self._outline_level(_int_attr(p_elem, 'paraPrIDRef', -1))
        if level:
            return level

        # (d) 폰트 크기 휴리스틱
        return self._detect_heading_level_by_font(runs)

    def _outline_level(self, para_pr_id: int) -> int:
        info = self._para_prs.get(para_pr_id)
        if not info or info['heading_type'] != 'OUTLINE':
            return 0
        level = info['heading_level'] + 1  # OWPML level 은 0-based
        return level if level <= MAX_OUTLINE_HEADING_LEVEL else 0

    def _make_paragraph(self, runs, p_elem) -> Paragraph:
        para = Paragraph(runs=runs)
        para.style_id = _int_attr(p_elem, 'styleIDRef', -1)
        para.para_shape_id = _int_attr(p_elem, 'paraPrIDRef', -1)
        para.heading_level = self._heading_level_for(p_elem, runs)
        return para

    def _parse_paragraph_elem(self, p_elem) -> list:
        """<p> 요소 → Paragraph/Table/등"""
        elements = []

        # 하이퍼링크 상태는 문단 안에서만 유효하다. 중첩 호출(표 셀, 도형)을 위해 저장/복원.
        saved_links = self._link_stack
        saved_overflow = self._field_overflow
        self._link_stack = []
        self._field_overflow = 0
        try:
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
                                para = self._make_paragraph(runs, p_elem)
                                if para.text.strip():
                                    elements.append(para)
                                runs = []
                            elements.append(item)
                elif tag == 'ctrl':
                    ctrl_elem = self._parse_ctrl(child)
                    if ctrl_elem:
                        if runs:
                            para = self._make_paragraph(runs, p_elem)
                            if para.text.strip():
                                elements.append(para)
                            runs = []
                        elements.append(ctrl_elem)

            # 남은 텍스트
            if runs:
                para = self._make_paragraph(runs, p_elem)
                if para.text.strip():
                    elements.append(para)
        finally:
            self._link_stack = saved_links
            self._field_overflow = saved_overflow

        return elements

    # ── run ──

    def _current_link(self) -> str:
        # 비어있지 않은 URL 만 스택에 담으므로 O(1) 이다.
        # 전체를 역순 순회하면 짝이 안 맞는 fieldBegin 이 쌓일 때 O(n^2) 가 된다.
        return self._link_stack[-1] if self._link_stack else ""

    def _push_field(self, url: str):
        if len(self._link_stack) >= MAX_FIELD_DEPTH:
            # 짝이 안 맞는 fieldBegin 이 무한히 쌓이지 못하게 한다.
            self._field_overflow += 1
            return
        # 링크가 아닌 필드(CLICK_HERE, FORMULA)도 짝을 맞춰야 하므로 현재 링크를 이어 담는다.
        self._link_stack.append(url or self._current_link())

    def _pop_field(self):
        if self._field_overflow > 0:
            self._field_overflow -= 1
            return
        if self._link_stack:
            self._link_stack.pop()

    def _parse_run_with_objects(self, run_elem) -> list:
        """<run> 내부의 텍스트 + 인라인 개체(표, 이미지, 도형) 파싱"""
        results = []
        text_parts = []
        font_size_pt = 10.0
        bold = False
        italic = False
        underline = False
        strikeout = False

        # CharShape lookup from charPrIDRef
        cs_id_str = run_elem.get('charPrIDRef', '')
        if cs_id_str and self._char_shapes:
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

        def flush():
            """누적 텍스트를 TextRun 으로 확정한다. 링크 경계에서도 호출된다."""
            if not text_parts:
                return
            text = ''.join(text_parts)
            del text_parts[:]
            if text:
                results.append(TextRun(
                    text=text,
                    bold=bold, italic=italic,
                    font_size_pt=font_size_pt,
                    underline=underline, strikeout=strikeout,
                    link=self._current_link(),
                ))

        for child in run_elem:
            tag = _local_tag(child.tag)

            if tag in ('charPrIDRef', 'charPr'):
                # charPr 속성은 별도 처리하지 않고 charPrIDRef 기반
                pass
            elif tag == 't':
                text_parts.append(_text_of_t(child))
            elif tag == 'tab':
                text_parts.append('\t')
            elif tag == 'lineBreak':
                text_parts.append('\n')
            elif tag == 'tbl':
                flush()
                results.append(self._parse_table_elem(child))
            elif tag == 'pic':
                flush()
                results.append(self._parse_picture_elem(child))
            elif tag == 'equation':
                flush()
                results.append(_parse_equation_elem(child))
            elif tag == 'compose':
                # 글자 겹치기 — 표시 문자는 composeText 속성에 있다
                text_parts.append(child.get('composeText', '') or '')
            elif tag in DRAWING_TAGS:
                # 도형(사각형/타원/그룹 등) 내부의 <drawText> 텍스트
                drawn = self._parse_drawing_elem(child)
                if drawn:
                    flush()
                    results.extend(drawn)
            elif tag == 'ctrl':
                action = _field_action(child)
                if action is not None:
                    # 하이퍼링크 필드 경계 — 링크가 걸린 범위를 정확히 자른다
                    flush()
                    kind, url = action
                    if kind == 'begin':
                        self._push_field(url)
                    else:
                        self._pop_field()
                    continue

                ctrl_result = self._parse_ctrl(child)
                if ctrl_result is not None:
                    flush()
                    if isinstance(ctrl_result, Footnote):
                        # 각주/미주는 본문에 참조 마커를 남긴다. 마커 없는 정의만 남으면
                        # Markdown 렌더러가 각주를 통째로 버린다.
                        # 마커는 반드시 별도 런이어야 한다 — 앞 텍스트와 합쳐지면
                        # 그 텍스트 전체가 마커로 치환되어 사라진다.
                        self._note_seq += 1
                        ctrl_result.number = self._note_seq
                        results.append(TextRun(
                            text=f"[{self._note_seq}]",
                            note_ref=self._note_seq,
                            font_size_pt=font_size_pt,
                        ))
                    results.append(ctrl_result)

        flush()
        return results

    def _parse_ctrl(self, ctrl_elem):
        """<ctrl> 요소 → Table/Equation/Image 등"""
        for child in ctrl_elem.iter():
            tag = _local_tag(child.tag)

            if tag == 'tbl':
                return self._parse_table_elem(child)
            elif tag == 'equation':
                return _parse_equation_elem(child)
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

    # ── 도형 ──

    def _parse_drawing_elem(self, elem, depth: int = 0) -> list:
        """도형 컨테이너 내부의 텍스트/표/이미지를 문서 순서대로 뽑는다.

        <hp:container> 는 중첩되므로 재귀가 필요하다.
        run_elem.iter() 같은 통짜 순회를 쓰면 표 하위를 다시 훑어 텍스트가 중복된다.
        """
        results = []
        if depth > MAX_DRAWING_DEPTH:
            return results

        for child in elem:
            tag = _local_tag(child.tag)
            if tag == 'drawText':
                for sub in child:
                    if _local_tag(sub.tag) != 'subList':
                        continue
                    for p_elem in sub:
                        if _local_tag(p_elem.tag) == 'p':
                            results.extend(self._parse_paragraph_elem(p_elem))
            elif tag == 'tbl':
                results.append(self._parse_table_elem(child))
            elif tag == 'pic':
                results.append(self._parse_picture_elem(child))
            elif tag in DRAWING_TAGS:
                results.extend(self._parse_drawing_elem(child, depth + 1))

        return results

    # ── 머리글/바닥글/각주 ──

    def _sublist_paragraphs(self, elem) -> list:
        """<...><subList><p>... 구조의 내용을 뽑는다.

        문단만 걸러내면 안 된다 — 실제로 표가 든 미주가 존재하고(실측),
        그런 표는 통째로 사라진다. Table/Image 도 그대로 담고 출력 계층이 처리한다.
        """
        blocks = []
        for child in elem:
            if _local_tag(child.tag) != 'subList':
                continue
            for sub in child:
                if _local_tag(sub.tag) != 'p':
                    continue
                blocks.extend(self._parse_paragraph_elem(sub))
        return blocks

    def _parse_header_footer_elem(self, elem, hf_type: str):
        """<header>/<footer> → HeaderFooter"""
        return HeaderFooter(type=hf_type, paragraphs=self._sublist_paragraphs(elem))

    def _parse_footnote_elem(self, elem, fn_type: str):
        """<footNote>/<endNote> → Footnote"""
        return Footnote(type=fn_type, paragraphs=self._sublist_paragraphs(elem))

    # ── 표 ──

    def _parse_table_elem(self, tbl_elem) -> Table:
        """<tbl> → Table.

        <hp:cellAddr> 의 colAddr/rowAddr 가 절대 좌표를 주므로 그것으로 격자를 복원한다.
        병합에 가려진 셀은 XML 에 아예 존재하지 않기 때문에, <tr> 안의 <tc> 순서로만
        배치하면 병합이 있는 행부터 열이 통째로 밀린다.
        """
        table = Table()

        row_cnt = _int_attr(tbl_elem, 'rowCnt', 0)
        col_cnt = _int_attr(tbl_elem, 'colCnt', 0)

        anchors = []      # (row, col, row_span, col_span, Cell)
        ordered = []      # 좌표가 없을 때의 폴백용
        has_coords = True

        for child in tbl_elem:
            tag = _local_tag(child.tag)
            if tag == 'caption':
                table.caption = self._sublist_paragraphs(child)
                table.caption_side = (child.get('side') or 'TOP').upper()
                continue
            if tag != 'tr':
                continue

            for tc in child:
                if _local_tag(tc.tag) != 'tc':
                    continue
                cell = self._parse_table_cell(tc)
                ordered.append(cell)

                addr = _find_child(tc, 'cellAddr')
                if addr is None:
                    has_coords = False
                    continue
                row = _int_attr(addr, 'rowAddr', -1)
                col = _int_attr(addr, 'colAddr', -1)
                if row < 0 or col < 0:
                    has_coords = False
                    continue
                anchors.append((row, col, cell.row_span, cell.col_span, cell))

        declared = row_cnt * col_cnt
        if has_coords and anchors and row_cnt > 0 and col_cnt > 0:
            if declared > MAX_TABLE_CELLS:
                # 선언된 격자가 너무 크다 — 실제 셀만으로 폴백한다
                self.errors.append(f"표 크기 초과: {row_cnt}x{col_cnt}")
                table.rows = self._fallback_rows(tbl_elem)
                return table
            if declared > self._cell_budget:
                # 문서 전체 셀 예산 초과. 표를 여럿 두어 우회하는 메모리 폭탄을 막는다.
                self.errors.append(
                    f"문서 셀 예산 초과 — 표 {row_cnt}x{col_cnt} 를 좌표 배치하지 않음"
                )
                table.rows = self._fallback_rows(tbl_elem)
                return table
            self._cell_budget -= declared
            table.rows, dropped = _build_grid(anchors, row_cnt, col_cnt)
            if dropped:
                self.errors.append(
                    f"표 셀 {dropped}개가 격자({row_cnt}x{col_cnt}) 밖 좌표라 배치되지 못함"
                )
        else:
            table.rows = self._fallback_rows(tbl_elem)

        return table

    def _fallback_rows(self, tbl_elem) -> list:
        """cellAddr 가 없는 비표준 입력용 — <tr> 안 <tc> 등장 순서로 배치."""
        rows = []
        for child in tbl_elem:
            if _local_tag(child.tag) != 'tr':
                continue
            row = []
            for tc in child:
                if _local_tag(tc.tag) == 'tc':
                    row.append(self._parse_table_cell(tc))
            rows.append(row)
        return rows

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

        # <hp:cellSpan colSpan="1" rowSpan="1"/> 태그에서도 읽기 (실문서는 이쪽을 쓴다)
        span = _find_child(tc_elem, 'cellSpan')
        if span is not None:
            cell.col_span = max(_int_attr(span, 'colSpan', cell.col_span), 1)
            cell.row_span = max(_int_attr(span, 'rowSpan', cell.row_span), 1)

        # 셀 내 문단+이미지 — 직접 자식 <subList> 또는 <p>에서
        for child in tc_elem:
            tag = _local_tag(child.tag)
            if tag == 'subList':
                for sub_child in child:
                    if _local_tag(sub_child.tag) == 'p':
                        cell.paragraphs.extend(self._parse_paragraph_elem(sub_child))
            elif tag == 'p':
                cell.paragraphs.extend(self._parse_paragraph_elem(child))

        return cell

    # ── 이미지 ──

    def _parse_picture_elem(self, pic_elem) -> Image:
        """<pic> → Image"""
        img = Image()

        for child in pic_elem:
            tag = _local_tag(child.tag)
            if tag == 'img':
                # 속성명: binaryItemIDRef 또는 binaryItemId
                # 주의: <hc:img> 는 core 네임스페이스다. _local_tag 덕에 무관하게 잡힌다.
                bid = (child.get('binaryItemIDRef', '') or
                       child.get('binaryItemId', '') or
                       child.get('binaryItemIdRef', ''))
                if bid:
                    resolved = self._resolve_bin_path(bid)
                    img.filename = resolved or bid
            elif tag == 'shapeComment':
                # 한글이 자동 생성한 그림 설명. 본문이 아니라 대체 텍스트로 쓴다.
                img.alt_text = (child.text or '').strip()
            elif tag == 'caption':
                img.caption = self._sublist_paragraphs(child)
                img.caption_side = (child.get('side') or 'BOTTOM').upper()

        return img

    def _load_image_data(self, zf: zipfile.ZipFile, doc: Document):
        """Document 내 모든 Image 객체에 ZIP 바이너리 데이터 로드"""
        images = doc.find_all('image')
        if not images:
            return

        cache = {}
        names = set(zf.namelist())  # 이미지마다 재구축하면 O(이미지 수 x 엔트리 수)
        for img in images:
            if not img.filename or img.has_data:
                continue
            zip_name = img.filename
            if zip_name not in names:
                zip_name = self._resolve_bin_path(os.path.splitext(os.path.basename(zip_name))[0])
            # 이미지 데이터는 BinData/ 안에서만 읽는다.
            # 아카이브 내 임의 엔트리를 가리켜 그 바이트를 실어가지 못하게 한다.
            if not zip_name or not zip_name.startswith('BinData/'):
                continue

            if zip_name in cache:
                img.image_data = cache[zip_name]
                continue

            try:
                info = zf.getinfo(zip_name)
            except KeyError:
                continue
            if info.file_size > MAX_FILE_SIZE:
                self.errors.append(f"이미지 {zip_name} 크기 초과: {info.file_size} bytes")
                continue
            if _compression_ratio_exceeded(info.file_size, info.compress_size):
                self.errors.append(f"이미지 {zip_name} 압축률 초과")
                continue
            try:
                data = zf.read(zip_name)
            except Exception:
                continue
            cache[zip_name] = data
            img.image_data = data


# ── 모듈 헬퍼 ──


def _local_tag(tag: str) -> str:
    """'{namespace}localname' → 'localname'"""
    if isinstance(tag, str) and '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def _int_attr(elem, name: str, default: int) -> int:
    value = elem.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _choose_switch_branch(switch_elem):
    """<hp:switch> 에서 유효한 분기 하나만 고른다.

    case 와 default 가 서로 다른 값을 담고 있어서(실측: 좌여백 9000 vs 18000),
    양쪽을 다 읽으면 값이 두 번 반영되거나 마지막 것이 이겨 조용히 틀린다.
    """
    default_branch = None
    for branch in switch_elem:
        tag = _local_tag(branch.tag)
        if tag == 'case':
            required = None
            for key, value in branch.attrib.items():
                if _local_tag(key) == 'required-namespace':
                    required = value
                    break
            if required in SUPPORTED_SWITCH_NAMESPACES:
                return branch
        elif tag == 'default':
            default_branch = branch
    return default_branch


def _find_child(parent, name: str):
    """직계 자식에서 name 태그를 찾는다. <hp:switch> 안에 있으면 분기 하나만 본다."""
    for child in parent:
        tag = _local_tag(child.tag)
        if tag == name:
            return child
        if tag == 'switch':
            branch = _choose_switch_branch(child)
            if branch is None:
                continue
            for sub in branch:
                if _local_tag(sub.tag) == name:
                    return sub
    return None


def _text_of_t(t_elem) -> str:
    """<hp:t> 의 전체 텍스트.

    <hp:t> 는 tab/fwSpace/markpenBegin 같은 자식을 가질 수 있는데, 자식 뒤에 이어지는
    tail 텍스트를 놓치면 문장 나머지가 통째로 사라진다(실측 270건 3234자).
    """
    parts = []
    if t_elem.text:
        parts.append(t_elem.text)

    for sub in t_elem:
        # 주석/처리명령/엔티티 노드는 tag 가 문자열이 아니고 itertext() 도 못 쓴다.
        # 걸러내지 않으면 lxml 이 TypeError 를 던져 섹션 전체가 날아간다.
        if not isinstance(sub.tag, str):
            if sub.tail:
                parts.append(sub.tail)
            continue

        tag = _local_tag(sub.tag)
        if tag == 'tab':
            parts.append('\t')
        elif tag == 'lineBreak':
            parts.append('\n')
        elif tag in ('fwSpace', 'nbSpace'):
            parts.append(' ')
        else:
            inner = ''.join(sub.itertext())
            if inner:
                parts.append(inner)
        if sub.tail:
            parts.append(sub.tail)

    return ''.join(parts)


def _parse_equation_elem(eq_elem) -> Equation:
    """<hp:equation> → Equation.

    수식 원문은 <hp:script> 자식 요소에 들어 있다. 요소 자신의 text 는 공백뿐이다.
    """
    script = _find_child(eq_elem, 'script')
    if script is not None and script.text:
        return Equation(script=script.text.strip())
    return Equation(script=(eq_elem.text or eq_elem.get('script', '') or '').strip())


def _string_param(field_elem, name: str) -> str:
    """<hp:parameters> 안의 <hp:stringParam name="..."> 값"""
    for node in field_elem.iter():
        if _local_tag(node.tag) != 'stringParam':
            continue
        if node.get('name') == name:
            return (node.text or '').strip()
    return ""


def _field_action(ctrl_elem):
    """<hp:ctrl> 이 필드 경계면 ('begin'|'end', URL) 을, 아니면 None 을 돌려준다.

    HYPERLINK 가 아닌 필드(CLICK_HERE, FORMULA)도 begin/end 짝을 이루므로
    스택 균형을 위해 빈 URL 로 push 한다.
    """
    for child in ctrl_elem:
        tag = _local_tag(child.tag)
        if tag == 'fieldBegin':
            if (child.get('type') or '').upper() != 'HYPERLINK':
                return ('begin', '')
            # Command 는 'http\://host;1;0;0;' 처럼 이스케이프되어 있다. Path 가 깨끗하다.
            path = _string_param(child, 'Path')
            if path:
                return ('begin', path)
            # 일부 생성기는 Path 없이 Command 만 싣는다 (실측: corpus
            # 80168_regulatory_analysis.hwpx 의 law.go.kr 링크). HWP 바이너리와
            # 같은 규칙으로 Command 에서 URL 을 복원한다.
            return ('begin', field_command_to_url(_string_param(child, 'Command')))
        if tag == 'fieldEnd':
            return ('end', '')
    return None


def _heading_level_from_style_name(name: str) -> int:
    """'개요 1' / 'Outline 2' / 'Heading 3' → 정수 레벨. 아니면 0."""
    if not name:
        return 0
    match = _STYLE_HEADING_RE.match(name)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def _build_grid(anchors, row_cnt: int, col_cnt: int):
    """앵커 셀을 좌표에 배치하고, 병합에 가려진 자리를 placeholder 로 채운다.

    rowSpan 이 덮는 칸은 나중에 오는 <tr> 에 걸리므로 반드시 2패스여야 한다.
    앵커를 전부 놓기 전에 placeholder 를 채우면 뒤 행의 앵커를 덮어쓴다.

    반환: (rows, dropped) — dropped 는 격자 밖 좌표라 배치하지 못한 앵커 수.
    """
    grid = [[None] * col_cnt for _ in range(row_cnt)]
    dropped = 0

    # 1패스: 앵커 배치
    for row, col, _rs, _cs, cell in anchors:
        if not (0 <= row < row_cnt and 0 <= col < col_cnt):
            dropped += 1
            continue
        if grid[row][col] is not None:
            # 같은 좌표를 두 셀이 주장한다 — 먼저 온 것을 남기고 손실을 보고한다
            dropped += 1
            continue
        cell.row = row
        cell.col = col
        grid[row][col] = cell

    # 2패스: 병합에 먹힌 자리 채우기 (is_merged_away 가 True 가 되도록 span=0)
    for row, col, rs, cs, _cell in anchors:
        if not (0 <= row < row_cnt and 0 <= col < col_cnt):
            continue
        for rr in range(row, min(row + max(rs, 1), row_cnt)):
            for cc in range(col, min(col + max(cs, 1), col_cnt)):
                if rr == row and cc == col:
                    continue
                if grid[rr][cc] is None:
                    grid[rr][cc] = Cell(row=rr, col=cc, row_span=0, col_span=0)

    # 남은 빈 칸은 평범한 빈 셀
    for row in range(row_cnt):
        for col in range(col_cnt):
            if grid[row][col] is None:
                grid[row][col] = Cell(row=row, col=col)

    return grid, dropped
