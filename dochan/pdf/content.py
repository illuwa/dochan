"""페이지 콘텐츠 스트림 해석 — 텍스트 배치를 좌표까지 재구성한다.

텍스트 행렬(Tm/Td/TD/T*)과 글리프 폭(WidthMap)으로 각 텍스트 조각의
실제 x/y 를 누적한다. 이 좌표가 있어야 단어 간격, 열 경계(표), 읽기
순서를 복원한다. CTM과 괘선 경로를 같은 패스에서 해석한다.
"""
from dataclasses import dataclass, field, replace
import math
from typing import Callable, Dict, List, Optional, Tuple

from .objects import DELIMITERS, WHITESPACE, PDFLexer, PDFName, PDFSyntaxError
from .widths import WidthMap
from .paths import PathCollector, Segment

_OPERAND_START = b"(</[0123456789+-."
MAX_FORM_DEPTH = 16
MAX_FORM_CACHE_BYTES = 16 * 1024 * 1024
MAX_FORM_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_FORM_OPERATORS = 32768

# 같은 기준선으로 볼 y 허용오차 (device 단위)
_LINE_Y_TOLERANCE = 3.0


def default_byte_decoder(raw: bytes) -> str:
    """ToUnicode 가 없는 단순 폰트의 기본 바이트 해석."""
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


class VerticalMetrics:
    """CIDFont /W2·/DW2 (w1y, v1x, v1y), ISO 32000-1 §9.7.4.3.

    기본 세로 원점 x는 가로 폭의 절반이다. DW2는 [v1y, w1y] 순서다.
    CID 범위 및 전체 매핑을 65,536개로 제한한다.
    """

    def __init__(self, w_array, default_array, widths: WidthMap):
        self._widths = widths
        self._table: Dict[int, Tuple[float, float, float]] = {}
        self.warnings: List[str] = []
        self._v1y, self._w1y = 880.0, -1000.0
        if isinstance(default_array, list) and len(default_array) >= 2:
            if self._numbers(default_array[:2]):
                self._v1y, self._w1y = map(float, default_array[:2])
            else:
                self._warn()
        if not isinstance(w_array, list):
            return
        i = 0
        remaining = 65536
        while i < min(len(w_array), 65536 * 5):
            if remaining <= 0:
                self._warn()
                break
            start = w_array[i]
            if not isinstance(start, int) or not 0 <= start <= 65535:
                self._warn()
                i += 1
                continue
            if i + 1 < len(w_array) and isinstance(w_array[i + 1], list):
                entries = w_array[i + 1]
                limit = min(len(entries) // 3, 65536 - start, remaining)
                for offset in range(limit):
                    triple = entries[offset * 3:offset * 3 + 3]
                    if self._numbers(triple):
                        self._table[start + offset] = tuple(map(float, triple))
                    else:
                        self._warn()
                remaining -= limit
                if len(entries) % 3 or len(entries) // 3 > limit:
                    self._warn()
                i += 2
            elif i + 4 < len(w_array):
                end = w_array[i + 1]
                triple = w_array[i + 2:i + 5]
                if isinstance(end, int) and start <= end <= 65535 and self._numbers(triple):
                    metrics = tuple(map(float, triple))
                    count = min(end - start + 1, remaining)
                    for cid in range(start, start + count):
                        self._table[cid] = metrics
                    remaining -= count
                    if count < end - start + 1:
                        self._warn()
                else:
                    self._warn()
                i += 5
            else:
                self._warn()
                break
        if i < len(w_array):
            self._warn()

    @staticmethod
    def _numbers(values):
        try:
            return all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in values)
        except OverflowError:
            return False

    def _warn(self):
        if not self.warnings:
            self.warnings.append("WARN: 세로 CID 글리프 메트릭이 손상되거나 한도를 초과 — 기본값 사용")

    def metrics(self, cid: int) -> Tuple[float, float, float]:
        return self._table.get(cid, (self._w1y, self._widths.advance(cid) / 2.0, self._v1y))


@dataclass
class FontInfo:
    """폰트별 텍스트 해석 정보."""
    decode: Callable[[bytes], str]
    widths: WidthMap
    code_bytes: int = 1  # 1=단순 폰트, 2=Type0/Identity-H CID
    bold: bool = False
    italic: bool = False
    wmode: int = 0
    vertical_metrics: Optional[VerticalMetrics] = None
    link_metrics_reliable: bool = True
    space_code: int = 32  # ToUnicode may assign a CID other than 32 to U+0020.
    encoding_cmap: object = None


@dataclass
class Fragment:
    """한 번의 Tj/TJ 로 그려진 텍스트 조각과 그 시작 위치."""
    x: float
    y: float
    width: float   # device 폭
    size: float    # 유효 폰트 크기
    text: str
    space_width: float  # 이 조각 폰트의 공백 1칸 device 폭 (간격 판정용)
    bold: bool = False
    italic: bool = False
    order: int = 0
    dir_x: float = 1.0  # 장치 공간에서 텍스트 x축의 x 성분 — 음수면 오른쪽→왼쪽으로 진행
    dir_y: float = 0.0  # 장치 공간에서 텍스트 x축의 y 성분
    up_x: float = 0.0   # 장치 공간에서 텍스트 y축(글자의 위쪽) — 반사 행렬에서는 쓰기 축을 돌린 것과 다르다
    up_y: float = 1.0
    char_offsets: tuple = ()  # 장치 좌표의 누적 글리프 폭
    link_spans: list = field(default_factory=list)
    note_ref: int = 0
    link_geometry_reliable: bool = True
    comment_spans: list = field(default_factory=list)
    comment_markers: list = field(default_factory=list)
    mcids: tuple = ()
    artifact: bool = False
    # 렌더 모드 3·7(보이지 않는 글자)로 그린 조각. 줄 끝 공백 신호에만 쓴다.
    invisible: bool = False


def writing_direction(frag: Fragment) -> str:
    """장치 공간의 텍스트 x축을 네 가지 쓰기 방향으로 분류한다."""
    if abs(frag.dir_x) >= abs(frag.dir_y):
        return "ltr" if frag.dir_x >= 0 else "rtl"
    return "down" if frag.dir_y < 0 else "up"


def along(frag: Fragment) -> float:
    """조각 시작점을 읽기 방향이 양수인 축에 투영한다."""
    direction = writing_direction(frag)
    if direction == "ltr":
        return frag.x
    if direction == "rtl":
        return -frag.x
    if direction == "down":
        return -frag.y
    return frag.y


def across(frag: Fragment) -> float:
    """다음 줄에서 값이 작아지는 줄 간 좌표를 돌려준다 (180° 텍스트는 다음 줄이 위에 있다)."""
    direction = writing_direction(frag)
    if direction == "ltr":
        return frag.y
    if direction == "rtl":
        return -frag.y
    return frag.x if direction == "down" else -frag.x


@dataclass
class PageContent:
    """페이지 텍스트·괘선과 한도 경고."""
    fragments: List[Fragment]
    segments: List[Segment]
    warnings: List[str] = field(default_factory=list)
    marked_ids: set = field(default_factory=set)
    duplicate_marked_ids: set = field(default_factory=set)
    short_segments: List[Segment] = field(default_factory=list)


def _matmul(m1, m2):
    """2x3 아핀 행렬 곱 (m1 × m2). 각 행렬은 (a,b,c,d,e,f)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _clip_form_fragments(fragments, bbox, ctm):
    """Keep glyphs overlapping a Form's transformed BBox, including rotations."""
    x0, y0, x1, y1 = bbox
    a, b, c, d, e, f = ctm
    polygon = [(a * x + c * y + e, b * x + d * y + f)
               for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    if not all(math.isfinite(value) for point in polygon for value in point):
        return []
    signed_area = sum(polygon[i][0] * polygon[(i + 1) % 4][1] -
                      polygon[(i + 1) % 4][0] * polygon[i][1] for i in range(4))
    sign = 1 if signed_area >= 0 else -1

    def inside(x, y):
        for index, (px, py) in enumerate(polygon):
            qx, qy = polygon[(index + 1) % 4]
            if sign * ((qx - px) * (y - py) - (qy - py) * (x - px)) < -1e-7:
                return False
        return True

    def overlaps(quad):
        if not all(math.isfinite(value) for point in quad for value in point):
            return False
        for shape in (polygon, quad):
            for edge, (px, py) in enumerate(shape):
                qx, qy = shape[(edge + 1) % 4]
                axis_length = math.hypot(qy - py, qx - px)
                if not axis_length:
                    continue
                nx, ny = -(qy - py) / axis_length, (qx - px) / axis_length
                clip_projection = [nx * x + ny * y for x, y in polygon]
                glyph_projection = [nx * x + ny * y for x, y in quad]
                if (max(clip_projection) < min(glyph_projection) - 1e-7 or
                        max(glyph_projection) < min(clip_projection) - 1e-7):
                    return False
        return True

    kept = []
    for frag in fragments:
        count = len(frag.text)
        if not count:
            continue
        direction = math.hypot(frag.dir_x, frag.dir_y)
        upward = math.hypot(frag.up_x, frag.up_y)
        if not direction or not upward:
            continue
        ux, uy = frag.dir_x / direction, frag.dir_y / direction
        vx, vy = frag.up_x / upward, frag.up_y / upward
        if len(frag.char_offsets) != count + 1:
            # Without individual positions, preserve an overlapping run as a
            # whole. This also handles vertical runs whose origin is shifted
            # by v1y and whose rectangle can cross the Form boundary.
            quad = [(frag.x + ux * distance + vx * height,
                     frag.y + uy * distance + vy * height)
                    for distance, height in ((0, 0), (frag.width, 0),
                                             (frag.width, frag.size), (0, frag.size))]
            if overlaps(quad):
                kept.append(frag)
            continue
        offsets = frag.char_offsets
        accepted = []
        for index in range(count):
            first, last = offsets[index:index + 2]
            middle = (first + last) / 2
            if inside(frag.x + ux * middle + vx * frag.size / 2,
                      frag.y + uy * middle + vy * frag.size / 2):
                accepted.append(True)
                continue
            # A partly visible glyph still belongs to the page. Test its
            # rectangle against the transformed clip polygon (SAT) before
            # dropping it as entirely outside.
            quad = [(frag.x + ux * distance + vx * height,
                     frag.y + uy * distance + vy * height)
                    for distance, height in ((first, 0), (last, 0),
                                             (last, frag.size), (first, frag.size))]
            accepted.append(overlaps(quad))
        start = 0
        while start < count:
            if not accepted[start]:
                start += 1
                continue
            end = start + 1
            while end < count and accepted[end]:
                end += 1
            shift = offsets[start]
            kept.append(replace(
                frag, text=frag.text[start:end], x=frag.x + ux * shift,
                y=frag.y + uy * shift, width=offsets[end] - shift,
                char_offsets=tuple(value - shift for value in offsets[start:end + 1])
                if frag.char_offsets else ()))
            start = end
    return kept


class ContentTextExtractor:
    """콘텐츠 스트림에서 위치 인식 텍스트를 추출한다."""

    def __init__(self, font_decoders: Optional[Dict[str, Callable[[bytes], str]]] = None,
                 fonts: Optional[Dict[str, FontInfo]] = None, track_char_positions: bool = False):
        self.track_char_positions = track_char_positions
        # 하위 호환: 디코더 dict 만 주어지면 폭 정보 없는 FontInfo 로 감싼다
        if fonts is not None:
            self._fonts = fonts
        else:
            decoders = font_decoders or {}
            self._fonts = {
                name: FontInfo(decode=dec, widths=WidthMap({}, 500.0), code_bytes=1)
                for name, dec in decoders.items()
            }

    @classmethod
    def from_fonts(cls, fonts: Dict[str, FontInfo], track_char_positions: bool = False) -> "ContentTextExtractor":
        return cls(fonts=fonts, track_char_positions=track_char_positions)

    # ── 공개 API ──

    def extract(self, content: bytes) -> List[str]:
        return [text for text, _size in self.extract_sized(content)]

    def extract_sized(self, content: bytes) -> List[Tuple[str, float]]:
        """읽기 순서로 정렬된 (줄 텍스트, 최대 폰트 크기) 목록."""
        frags = self.extract_fragments(content)
        return [(line.text, line.size) for line in self._assemble_lines(frags)]

    def extract_lines(self, content: bytes) -> List["_Line"]:
        """열 경계 재구성을 위한 라인 객체(세그먼트 좌표 포함) 목록."""
        return self._assemble_lines(self.extract_fragments(content))

    # ── 좌표 기반 조각 추출 ──

    def extract_fragments(self, content: bytes) -> List[Fragment]:
        return self.extract_page(content).fragments

    def extract_page(self, content: bytes, _initial_ctm=(1, 0, 0, 1, 0, 0),
                     _form_context=None, _initial_text_state=None) -> PageContent:
        """그래픽 상태를 유지하며 텍스트와 괘선을 함께 해석한다."""
        if _form_context is None:
            _form_context = {"active": set(), "cache": {}, "cache_bytes": 0,
                             "expanded": 0, "operators": 0, "warned": set(),
                             "char_positions": 200000}
        self._form_context = _form_context
        self._link_position_reliable = True
        self._marked_stack = []
        self._marked_overflow = 0
        marked_ids = set()
        duplicate_marked_ids = set()
        lexer = PDFLexer(content)
        lexer.skip_array_operators = True
        ctm = _initial_ctm
        stack = []
        overflow = 0
        paths = PathCollector()
        frags: List[Fragment] = []
        operands: List[object] = []
        # 텍스트 상태
        tm = (1, 0, 0, 1, 0, 0)   # 텍스트 행렬
        tlm = (1, 0, 0, 1, 0, 0)  # 텍스트 라인 행렬
        font, fs, tc, tw, th, tl = (_initial_text_state if _initial_text_state is not None
                                    else (None, 0.0, 0.0, 0.0, 1.0, 0.0))
        # 텍스트 렌더 모드(ISO 32000-1 9.3.6). 3·7 은 보이지 않는 글자(OCR 텍스트층 등)다.
        tr = 0
        n = len(content)
        while True:
            lexer.skip_whitespace()
            if lexer.pos >= n:
                break
            ch = content[lexer.pos]
            if ch in _OPERAND_START:
                try:
                    operands.append(lexer.parse_object())
                except PDFSyntaxError:
                    lexer.pos += 1
                if len(operands) > 64:
                    del operands[:-8]
                continue
            op = lexer.read_token()
            if not op:
                lexer.pos += 1
                continue

            if op in (b"BT", b"Tm", b"Td", b"TD", b"T*", b"'", b'"'):
                # 이 연산은 글리프 전진이 아닌 텍스트 줄 행렬에서 다시 시작한다.
                self._link_position_reliable = True

            if op in (b"BDC", b"BMC"):
                props = operands[-1] if op == b"BDC" and operands else None
                if isinstance(props, PDFName):
                    props = getattr(self, "properties", {}).get(str(props))
                mcid = props.get("MCID") if isinstance(props, dict) else None
                if type(mcid) is not int or mcid < 0:
                    mcid = None
                if len(self._marked_stack) < 64 and not self._marked_overflow:
                    self._marked_stack.append((mcid, bool(operands and str(operands[0]) == "Artifact")))
                    if mcid is not None:
                        if mcid in marked_ids:
                            duplicate_marked_ids.add(mcid)
                        marked_ids.add(mcid)
                else:
                    self._marked_overflow += 1
                    if self._marked_overflow == 1:
                        paths.warnings.append("WARN: PDF marked-content 깊이 한도 초과")
            elif op == b"EMC":
                if self._marked_overflow:
                    self._marked_overflow -= 1
                elif self._marked_stack:
                    self._marked_stack.pop()
            elif op == b"q":
                if len(stack) < 256:
                    stack.append((ctm, font, fs, tc, tw, th, tl, tr))
                else:
                    overflow += 1
            elif op == b"Q":
                if overflow:
                    overflow -= 1
                elif stack:
                    ctm, font, fs, tc, tw, th, tl, tr = stack.pop()
            elif op == b"cm" and len(operands) >= 6:
                ctm = _matmul(tuple(_num(o) for o in operands[-6:]), ctm)
            elif op == b"Do" and operands and isinstance(operands[-1], PDFName):
                loader = getattr(self, "form_loader", None)
                if loader is not None:
                    loaded = None
                    try:
                        if (_form_context["expanded"] >= MAX_FORM_EXPANDED_BYTES or
                                _form_context["operators"] >= MAX_FORM_OPERATORS):
                            reason = "확장 한도"
                            if reason not in _form_context["warned"]:
                                paths.warnings.append("WARN: PDF Form " + reason + " — 해당 Form 건너뜀")
                                _form_context["warned"].add(reason)
                        else:
                            loaded = loader(str(operands[-1]), getattr(self, "resources", {}))
                    except Exception:
                        if "해석 실패" not in _form_context["warned"]:
                            paths.warnings.append("WARN: PDF Form 해석 실패 — 해당 Form 건너뜀")
                            _form_context["warned"].add("해석 실패")
                    if loaded is not None:
                        key, data, matrix, resources, fonts, properties, op_count, bbox, separate_mcids = loaded
                        reason = None
                        try:
                            form_ctm = _matmul(matrix, ctm)
                        except OverflowError:
                            form_ctm = (float("inf"),) * 6
                        if key in _form_context["active"]:
                            reason = "순환 참조"
                        elif len(_form_context["active"]) >= MAX_FORM_DEPTH:
                            reason = "깊이 한도"
                        elif (len(data) > MAX_FORM_CACHE_BYTES or
                              key not in _form_context["cache"] and
                              _form_context["cache_bytes"] + len(data) > MAX_FORM_CACHE_BYTES):
                            reason = "디코드 캐시 한도"
                        elif (not all(math.isfinite(v) and abs(v) <= 1e150 for v in form_ctm) or
                              not all(math.isfinite(v) for v in matrix)):
                            reason = "행렬 크기 한도"
                        elif matrix[0] * matrix[3] - matrix[1] * matrix[2] == 0:
                            reason = "특이 행렬"
                        else:
                            cached = _form_context["cache"].get(key)
                            if cached is None:
                                cached = (data, op_count)
                                _form_context["cache"][key] = cached
                                _form_context["cache_bytes"] += len(data)
                            op_count = cached[1]
                            if (_form_context["expanded"] + len(data) > MAX_FORM_EXPANDED_BYTES or
                                    _form_context["operators"] + op_count > MAX_FORM_OPERATORS):
                                reason = "확장 한도"
                        if reason is not None:
                            if reason not in _form_context["warned"]:
                                paths.warnings.append("WARN: PDF Form " + reason + " — 해당 Form 건너뜀")
                                _form_context["warned"].add(reason)
                        else:
                            _form_context["expanded"] += len(data)
                            _form_context["operators"] += op_count
                            _form_context["active"].add(key)
                            try:
                                child = ContentTextExtractor.from_fonts(
                                    fonts() if callable(fonts) else fonts,
                                    track_char_positions=self.track_char_positions or bbox is not None)
                                child.form_loader = loader
                                child.resources = resources
                                child.properties = properties
                                result = child.extract_page(
                                    data, form_ctm, _form_context, (font, fs, tc, tw, th, tl))
                                child_frags = (_clip_form_fragments(result.fragments, bbox, form_ctm)
                                               if bbox is not None else result.fragments)
                                offset = len(frags)
                                page_mcids = (tuple(item[0] for item in self._marked_stack
                                                    if item[0] is not None)
                                              if not self._marked_overflow and not separate_mcids else ())
                                parent_artifact = any(item[1] for item in self._marked_stack)
                                for index, frag in enumerate(child_frags):
                                    frag.order = offset + index
                                    frag.mcids = page_mcids  # Form MCIDs have their own space.
                                    frag.artifact = frag.artifact or parent_artifact
                                frags.extend(child_frags)
                                # Form vector art is outside this text pass. Adding
                                # its rules creates empty grids in unrelated artwork.
                                paths.warnings.extend(result.warnings)
                            except Exception:
                                if "해석 실패" not in _form_context["warned"]:
                                    paths.warnings.append("WARN: PDF Form 해석 실패 — 해당 Form 건너뜀")
                                    _form_context["warned"].add("해석 실패")
                            finally:
                                _form_context["active"].discard(key)
            elif op == b"BT":
                tm = (1, 0, 0, 1, 0, 0)
                tlm = (1, 0, 0, 1, 0, 0)
            elif op == b"Tf":
                if len(operands) >= 2 and isinstance(operands[-2], PDFName):
                    font = self._fonts.get(str(operands[-2]))
                if operands and isinstance(operands[-1], (int, float)):
                    fs = float(operands[-1])
            elif op == b"Tc" and operands and isinstance(operands[-1], (int, float)):
                tc = float(operands[-1])
            elif op == b"Tw" and operands and isinstance(operands[-1], (int, float)):
                tw = float(operands[-1])
            elif op == b"Tz" and operands and isinstance(operands[-1], (int, float)):
                th = float(operands[-1]) / 100.0
            elif op == b"TL" and operands and isinstance(operands[-1], (int, float)):
                tl = float(operands[-1])
            elif op == b"Tr" and operands and isinstance(operands[-1], int):
                tr = operands[-1]
            elif op == b"Td" and len(operands) >= 2:
                tx = _num(operands[-2])
                ty = _num(operands[-1])
                tlm = _matmul((1, 0, 0, 1, tx, ty), tlm)
                tm = tlm
            elif op == b"TD" and len(operands) >= 2:
                tx = _num(operands[-2])
                ty = _num(operands[-1])
                tl = -ty
                tlm = _matmul((1, 0, 0, 1, tx, ty), tlm)
                tm = tlm
            elif op == b"Tm" and len(operands) >= 6:
                tm = tuple(_num(o) for o in operands[-6:])
                tlm = tm
            elif op == b"T*":
                tlm = _matmul((1, 0, 0, 1, 0, -tl), tlm)
                tm = tlm
            elif op == b"Tj":
                if operands and isinstance(operands[-1], bytes):
                    shown = len(frags)
                    tm = self._show(operands[-1], tm, font, fs, tc, tw, th, frags, ctm)
                    if tr in (3, 7):
                        _mark_invisible(frags, shown)
            elif op in (b"'", b'"'):
                tlm = _matmul((1, 0, 0, 1, 0, -tl), tlm)
                tm = tlm
                if op == b'"' and len(operands) >= 3:
                    tw = _num(operands[-3])
                    tc = _num(operands[-2])
                if operands and isinstance(operands[-1], bytes):
                    shown = len(frags)
                    tm = self._show(operands[-1], tm, font, fs, tc, tw, th, frags, ctm)
                    if tr in (3, 7):
                        _mark_invisible(frags, shown)
            elif op == b"TJ":
                if operands and isinstance(operands[-1], list):
                    shown = len(frags)
                    for item in operands[-1]:
                        if isinstance(item, bytes):
                            tm = self._show(item, tm, font, fs, tc, tw, th, frags, ctm)
                        elif isinstance(item, (int, float)):
                            vertical = font is not None and font.wmode == 1
                            adj = -item / 1000.0 * fs * (1.0 if vertical else th)
                            tm = _matmul((1, 0, 0, 1, 0 if vertical else adj,
                                          adj if vertical else 0), tm)
                    if tr in (3, 7):
                        _mark_invisible(frags, shown)
            elif op == b"BI":
                lexer.pos = self._skip_inline_image(content, lexer.pos)
            else:
                paths.operate(op, [_num(o) for o in operands], ctm)
            operands = []
        safe = [frag for frag in frags if all(math.isfinite(v) for v in
                (frag.x, frag.y, frag.width, frag.size, frag.dir_x, frag.dir_y, frag.up_x, frag.up_y))]
        if len(safe) != len(frags):
            paths.warnings.append("WARN: PDF 비유한 텍스트 좌표 — 해당 조각 건너뜀")
        return PageContent(safe, paths.segments, paths.warnings, marked_ids,
                           duplicate_marked_ids, paths.short_segments)

    @classmethod
    def _count_operators(cls, data: bytes) -> Tuple[int, bool]:
        """Count a Form once, then charge every invocation against the page budget."""
        lexer = PDFLexer(data)
        lexer.skip_array_operators = True
        count = 0
        has_text_or_form = False
        while lexer.pos < len(data):
            lexer.skip_whitespace()
            if lexer.pos >= len(data):
                break
            if data[lexer.pos] in _OPERAND_START:
                try:
                    lexer.parse_object()
                except PDFSyntaxError:
                    lexer.pos += 1
                continue
            op = lexer.read_token()
            if not op:
                lexer.pos += 1
                continue
            count += 1
            if op in (b"Tj", b"TJ", b"'", b'"', b"Do"):
                has_text_or_form = True
            if op == b"BI":
                lexer.pos = cls._skip_inline_image(data, lexer.pos)
        return count, has_text_or_form

    def _show(self, raw, tm, font, fs, tc, tw, th, frags, ctm):
        if not raw:
            return tm
        if font is None:
            # Tf 미지정/미해석 폰트 — 텍스트 유실 방지용 기본 폰트
            font = FontInfo(decode=default_byte_decoder, widths=WidthMap({}, 500.0), code_bytes=1)
        text = font.decode(raw)
        if font.wmode == 1:
            return self._show_vertical(raw, text, tm, font, fs, tc, tw, th, frags, ctm)
        track_positions = (self.track_char_positions and len(text) <= 50000
                           and len(text) <= self._form_context["char_positions"])
        if track_positions:
            self._form_context["char_positions"] -= len(text)
        start_tm = _matmul(tm, ctm)
        # 조각 전체 device 폭을 계산하며 tm 을 전진
        total_adv = 0.0
        offsets = [0.0]
        decoded_parts = []
        chunks = self._iter_code_chunks(raw, font.code_bytes, font.encoding_cmap)
        codes = [cid for _chunk, cid in chunks]
        geometry_reliable = (self._link_position_reliable and font.link_metrics_reliable
                             and all(font.widths.explicit(code) for code in codes))
        self._link_position_reliable = geometry_reliable
        xscale, yscale = math.hypot(*start_tm[:2]), math.hypot(*start_tm[2:4])
        geometry_reliable = (geometry_reliable and xscale > 0 and yscale > 0
                             and math.isclose(xscale, yscale, rel_tol=1e-6)
                             and abs(start_tm[0] * start_tm[2] + start_tm[1] * start_tm[3])
                             <= 1e-6 * xscale * yscale)
        for chunk, code in chunks:
            w0 = font.widths.advance(code) / 1000.0
            valid_space = (chunk == b" " and
                           (font.encoding_cmap is None or font.encoding_cmap._space(1, 32)))
            disp = (w0 * fs + tc + (tw if valid_space else 0.0)) * th
            if track_positions:
                piece = font.decode(chunk)
                decoded_parts.append(piece)
                for index in range(len(piece)):
                    offsets.append(total_adv + disp * (index + 1) / len(piece))
            total_adv += disp
        scale = math.hypot(start_tm[0], start_tm[1]) or 1.0
        space_w = font.widths.advance(font.space_code) / 1000.0 * fs * th * scale
        if space_w <= 0:
            space_w = 0.25 * fs * scale
        eff_size = fs * ((abs(start_tm[0] * start_tm[3] - start_tm[1] * start_tm[2])) ** 0.5 or 1.0)
        if text.strip():
            frags.append(Fragment(
                x=start_tm[4], y=start_tm[5],
                width=abs(total_adv) * scale, size=eff_size,
                text=text, space_width=space_w,
                bold=font.bold, italic=font.italic, order=len(frags),
                mcids=tuple(item[0] for item in self._marked_stack if item[0] is not None)
                    if not self._marked_overflow else (),
                artifact=any(item[1] for item in self._marked_stack),
                dir_x=start_tm[0], dir_y=start_tm[1],
                up_x=start_tm[2], up_y=start_tm[3],
                char_offsets=tuple(abs(v) * scale for v in offsets)
                    if track_positions and "".join(decoded_parts) == text else (),
                link_geometry_reliable=geometry_reliable,
            ))
        return _matmul((1, 0, 0, 1, total_adv, 0), tm)

    def _show_vertical(self, raw, text, tm, font, fs, tc, tw, th, frags, ctm):
        """세로 폰트는 y축으로 전진하며 가로 스케일은 원점 x에만 적용한다."""
        metrics = font.vertical_metrics or VerticalMetrics(None, None, font.widths)
        chunks = self._iter_code_chunks(raw, font.code_bytes, font.encoding_cmap)
        if not chunks:
            return tm
        total_adv = sum(metrics.metrics(cid)[0] / 1000.0 * fs + tc
                        + (tw if chunk == b" " and
                           (font.encoding_cmap is None or font.encoding_cmap._space(1, 32))
                           else 0.0)
                        for chunk, cid in chunks)
        _w1y, v1x, v1y = metrics.metrics(chunks[0][1])
        origin = _matmul((1, 0, 0, 1, -v1x / 1000.0 * fs * th,
                          -v1y / 1000.0 * fs), tm)
        start_tm = _matmul(origin, ctm)
        scale = math.hypot(start_tm[2], start_tm[3]) or 1.0
        eff_size = fs * (abs(start_tm[0] * start_tm[3] - start_tm[1] * start_tm[2]) ** 0.5 or 1.0)
        if text.strip():
            frags.append(Fragment(
                x=start_tm[4], y=start_tm[5], width=abs(total_adv) * scale,
                size=eff_size, text=text,
                space_width=abs(metrics.metrics(32)[0]) / 1000.0 * fs * scale,
                bold=font.bold, italic=font.italic, order=len(frags),
                mcids=tuple(item[0] for item in self._marked_stack if item[0] is not None)
                    if not self._marked_overflow else (),
                artifact=any(item[1] for item in self._marked_stack),
                dir_x=-start_tm[2], dir_y=-start_tm[3],
                up_x=start_tm[0], up_y=start_tm[1],
            ))
        return _matmul((1, 0, 0, 1, 0, total_adv), tm)

    @staticmethod
    def _iter_code_chunks(raw: bytes, code_bytes: int, encoding_cmap=None):
        if encoding_cmap is not None:
            return list(encoding_cmap.iter_codes(raw, encoding_cmap.warnings))
        if code_bytes == 2:
            return [(raw[i:i + 2], (raw[i] << 8) | raw[i + 1])
                    for i in range(0, len(raw) - 1, 2)]
        return [(bytes((byte,)), byte) for byte in raw]

    @staticmethod
    def _iter_codes(raw: bytes, code_bytes: int, encoding_cmap=None):
        if encoding_cmap is not None:
            return [cid for _chunk, cid in encoding_cmap.iter_codes(raw)]
        if code_bytes == 2:
            return [(raw[i] << 8) | raw[i + 1] for i in range(0, len(raw) - 1, 2)]
        return list(raw)

    @staticmethod
    def _skip_inline_image(data: bytes, pos: int) -> int:
        """이진 데이터 속 우연한 'EI' 를 피해 공백 구분된 종결자를 찾는다."""
        n = len(data)
        while True:
            end = data.find(b"EI", pos)
            if end < 0:
                return n
            before_ok = end == 0 or data[end - 1] in WHITESPACE
            after = data[end + 2:end + 3]
            after_ok = not after or after[0] in WHITESPACE or after[0] in DELIMITERS
            if before_ok and after_ok:
                return end + 2
            pos = end + 1

    # ── 조각 → 줄 조립 (읽기 순서) ──

    def _assemble_lines(self, frags: List[Fragment]) -> List["_Line"]:
        """콘텐츠 스트림 순서를 보존하며 같은 기준선 조각을 한 줄로 묶는다.

        전역 y 정렬은 각주/머리말을 본문 사이에 끼워 넣을 수 있다.
        생성기가 의도한 그리기 순서를 유지하고, 쓰기 방향이나 줄 간 좌표가
        크게 바뀔 때만 줄을 나눈다. 줄 안에서는 쓰기 축을 따라 정렬한다.
        """
        if not frags:
            return []
        rows: List[List[Fragment]] = []
        current: List[Fragment] = []
        current_across: Optional[float] = None
        current_direction: Optional[str] = None
        current_size = 0.0
        for frag in frags:
            direction = writing_direction(frag)
            position = across(frag)
            tolerance = max(_LINE_Y_TOLERANCE, 0.5 * current_size)
            if (current_across is None or
                    (direction == current_direction and
                     abs(position - current_across) <= tolerance)):
                current.append(frag)
                if current_across is None:
                    current_across = position
                    current_direction = direction
            else:
                rows.append(current)
                current = [frag]
                current_across = position
                current_direction = direction
                current_size = 0.0
            current_size = max(current_size, frag.size)
        if current:
            rows.append(current)
        return [_Line(_in_writing_order(row)) for row in rows]


def _mark_invisible(frags, start):
    for fragment in frags[start:]:
        fragment.invisible = True


def assemble_lines(fragments: List[Fragment]) -> List["_Line"]:
    """조각 목록을 같은 기준선끼리 묶어 줄로 만든다 (표 셀·본문 공통 공개 진입점)."""
    return ContentTextExtractor()._assemble_lines(fragments)


def _in_writing_order(row: List[Fragment]) -> List[Fragment]:
    """같은 줄의 조각을 읽기 방향으로 정렬한다."""
    return sorted(row, key=along)


@dataclass
class _Segment:
    x0: float
    x1: float
    text: str
    space_width: float = 0.0  # 이 조각 폰트의 공백 1칸 폭 (텍스트 표 옵션의 칸 병합용)
    runs: tuple = ()


class _Line:
    """한 기준선의 텍스트 — 세그먼트 좌표와 조립된 문자열."""

    def __init__(self, frags: List[Fragment]):
        self.fragment_orders = tuple(f.order for f in frags)
        self.order = min(f.order for f in frags)
        self.direction = writing_direction(frags[0])
        self.along_start = min(along(f) for f in frags)
        self.along_end = max(along(f) + f.width for f in frags)
        self.across = across(frags[0])
        self.left = self.along_start
        self.right = self.along_end
        self.y = self.across
        self.size = max((f.size for f in frags), default=0.0)
        # 줄 병합의 크기 비교는 인접한 조각끼리 한다 (본문 끝의 작은 주석 ↔ 다음 줄)
        self.first_size = frags[0].size
        self.last_size = frags[-1].size
        self.segments: List[_Segment] = []
        parts: List[str] = []
        # 서식이 같은 인접 조각은 하나의 run 으로 묶는다 (부분 굵게 보존)
        self.runs: List[Tuple[str, bool, bool]] = []
        prev_end: Optional[float] = None
        prev_space: float = 0.0
        for f in frags:
            start = along(f)
            gap = (start - prev_end) if prev_end is not None else 0.0
            threshold = max(prev_space, f.space_width) * 0.5
            sep = ""
            if prev_end is not None and gap > threshold and parts and not parts[-1].endswith(" "):
                sep = " "
            if sep:
                parts.append(sep)
                previous_link = self.runs[-1][3] if self.runs and len(self.runs[-1]) > 3 else ""
                next_link = f.link_spans[0][2] if f.link_spans and f.link_spans[0][0] == 0 else ""
                self._append_run(sep, f.bold, f.italic,
                                 previous_link if previous_link == next_link else "")
            parts.append(f.text)
            fragment_runs = []
            if f.note_ref:
                link = (f.link_spans[0][2] if len(f.link_spans) == 1
                        and f.link_spans[0][:2] == (0, len(f.text)) else "")
                fragment_runs.append((f.text, f.bold, f.italic, link, f.note_ref))
            elif f.link_spans:
                at = 0
                for first, last, target in f.link_spans:
                    fragment_runs.extend([(f.text[at:first], f.bold, f.italic),
                                          (f.text[first:last], f.bold, f.italic, target)])
                    at = last
                fragment_runs.append((f.text[at:], f.bold, f.italic))
            else:
                fragment_runs.append((f.text, f.bold, f.italic))
            if f.comment_markers:
                marked_runs = []
                offset = 0
                markers = sorted(f.comment_markers)
                for run in fragment_runs:
                    end = offset + len(run[0])
                    at = offset
                    while markers and markers[0][0] <= end:
                        position, number = markers.pop(0)
                        if position > at:
                            marked_runs.append((run[0][at - offset:position - offset],) + run[1:])
                        marked_runs.append(("[comment %d]" % number, False, False, "", number, "comment"))
                        at = position
                    if at < end:
                        marked_runs.append((run[0][at - offset:],) + run[1:])
                    offset = end
                fragment_runs = marked_runs
            fragment_runs = [run for run in fragment_runs if run[0]]
            for run in fragment_runs:
                if len(run) > 4:
                    self.runs.append(run)
                else:
                    self._append_run(*run)
            self.segments.append(_Segment(start, start + f.width, f.text, f.space_width,
                                          tuple(fragment_runs)))
            prev_end = start + f.width
            prev_space = f.space_width
        joined = "".join(parts)
        # 앞 단어와 같은 텍스트 그리기 명령 안에서 줄 끝에 그려진 공백 글리프(줄 병합이 쓴다).
        # 한컴 PDF 에서는 원문의 띄어쓰기였다(공개·내부 짝 측정). 공백만 따로 그린 조각은 앞에서 버려진다.
        # 보이지 않는 글자(OCR 텍스트층)는 단어마다 공백을 붙여 그리므로 신호로 쓰지 않는다.
        self.trailing_space = (bool(joined.strip()) and joined[-1:].isspace()
                               and not frags[-1].invisible)
        self.text = joined.strip()

    def _append_run(self, text: str, bold: bool, italic: bool, link: str = "") -> None:
        if not text:
            return
        style = (bold, italic, link) if link else (bold, italic)
        if self.runs and self.runs[-1][1:] == style:
            prev = self.runs[-1]
            self.runs[-1] = (prev[0] + text,) + style
        else:
            self.runs.append((text,) + style)


def _num(value) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
