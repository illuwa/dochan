"""PDF 주석과 목적지의 제한된 네이티브 해석."""
import math
from bisect import bisect_right
from dataclasses import dataclass, replace
from ..utils import safe_xml as etree

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from ..model.header_footer import Comment
from .objects import PDFName, PDFRef, PDFStream

MAX_ANNOTATIONS = 256
MAX_ANNOTATION_TEXT = 65536
MAX_COMMENT_TEXT_TOTAL = 8 * 1024 * 1024
MAX_COMMENTS = 4096
MARKUP_SUBTYPES = {"Text", "FreeText", "Highlight", "Underline", "Squiggly", "StrikeOut",
                   "Caret", "Stamp", "Ink", "Square", "Circle", "Line", "Polygon", "PolyLine",
                   "FileAttachment", "Sound", "Redact"}


def text_string(value):
    """ISO 32000 PDFDocEncoding과 BOM이 있는 유니코드 문자열."""
    if not isinstance(value, bytes):
        return ""
    value = value[:MAX_ANNOTATION_TEXT]
    if value.startswith(b"\xfe\xff"):
        return value[2:].decode("utf-16-be", errors="replace")
    if value.startswith(b"\xef\xbb\xbf"):
        return value[3:].decode("utf-8", errors="replace")
    special = "•†‡…—–ƒ⁄‹›−‰„“”‘’‚™ﬁﬂŁŒŠŸŽıłœšž"
    accents = "˘ˇˆ˙˝˛˚˜"
    chars = []
    for byte in value:
        if 0x18 <= byte <= 0x1f:
            chars.append(accents[byte - 0x18])
        elif 0x80 <= byte <= 0x9e:
            chars.append(special[byte - 0x80])
        elif byte == 0xa0:
            chars.append("€")
        elif byte in (0x7f, 0x9f, 0xad):
            chars.append("\ufffd")
        else:
            chars.append(chr(byte))
    return "".join(chars)


def page_annotations(pdf, page):
    annots = pdf.resolve(page.get("Annots"))
    if not isinstance(annots, list):
        return []
    if len(annots) > MAX_ANNOTATIONS:
        pdf.warnings.append("WARN: PDF 주석 개수 한도 초과 — 일부만 추출")
    return annots[:MAX_ANNOTATIONS]


def _rich_text(value, warnings):
    if not isinstance(value, bytes) or len(value) > MAX_ANNOTATION_TEXT:
        if value:
            warnings.append("WARN: PDF 주석 RC 크기 한도 초과 또는 잘못된 형식")
        return ""
    if value.startswith(b"\xfe\xff"):
        try:
            value = value[2:].decode("utf-16-be").encode("utf-8")
        except UnicodeError:
            warnings.append("WARN: PDF 주석 RC Unicode 해석 실패")
            return ""
    if b"<!DOCTYPE" in value.upper() or b"<!ENTITY" in value.upper():
        warnings.append("WARN: PDF 주석 RC의 DTD/엔티티는 허용하지 않음")
        return ""
    try:
        # RC는 XML rich-text 문자열이며 PDFDocEncoding 문자열과 인코딩이 다르다.
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
        root = etree.fromstring(value, parser)
        nodes = [node for node in root.iter() if isinstance(node.tag, str)]
        parents = etree.parent_map(root)
        if len(nodes) > 4096 or any(len(list(etree.ancestors(n, parents))) > 32 for n in nodes):
            warnings.append("WARN: PDF 주석 RC 구조 한도 초과")
            return ""
        paragraphs = [n for n in nodes if etree.QName(n).localname in ("p", "div")
                      and not any(etree.QName(c).localname in ("p", "div")
                                  for c in n.iter() if c is not n and isinstance(c.tag, str))]
        if paragraphs:
            return "\n".join("".join(etree.itertext(n)).strip() for n in paragraphs).strip()
        return "".join(etree.itertext(root)).strip()
    except etree.ForbiddenDTD:
        warnings.append("WARN: PDF 주석 RC의 DTD/엔티티는 허용하지 않음")
        return ""
    except (ValueError, UnicodeError, etree.XMLSyntaxError):
        warnings.append("WARN: PDF 주석 RC XML 해석 실패")
        return ""


class CommentExtractor:
    def __init__(self):
        self.number = 0
        self.total_text = 0
        self.exhausted = False
        self.seen = set()
        self.regions = []

    def extract(self, pdf, page, page_number):
        result = []
        self.regions = []
        if self.exhausted:
            return result
        for ref in page_annotations(pdf, page):
            key = (ref.num, ref.gen) if isinstance(ref, PDFRef) else id(ref)
            if key in self.seen:
                continue
            self.seen.add(key)
            annot = pdf.resolve(ref)
            if not isinstance(annot, dict) or str(annot.get("Subtype")) not in MARKUP_SUBTYPES:
                continue  # Popup은 부모의 표시창이지 별도 코멘트가 아니다.
            contents = text_string(pdf.resolve(annot.get("Contents"))).strip()
            if not contents:
                rich = pdf.resolve(annot.get("RC"))
                if isinstance(rich, PDFStream):
                    # ISO 32000-1 §12.5.6.3: RC는 text string 또는 text stream이다.
                    # 공통 해제기의 스트림/문서 예산과 캐시를 그대로 적용한다.
                    if len(rich.raw) > MAX_ANNOTATION_TEXT:
                        pdf.warnings.append("WARN: PDF 주석 RC 스트림 크기 한도 초과")
                        rich = b""
                    else:
                        rich = pdf.decode_stream_bytes(rich)
                contents = _rich_text(rich, pdf.warnings)
            if not contents:
                continue
            author = text_string(pdf.resolve(annot.get("T"))).strip()
            if self.number >= MAX_COMMENTS or self.total_text + len(contents) + len(author) > MAX_COMMENT_TEXT_TOTAL:
                self.exhausted = True
                pdf.warnings.append("WARN: PDF 문서 주석 개수/텍스트 한도 초과 — 이후 주석 생략")
                break
            self.total_text += len(contents) + len(author)
            self.number += 1
            self.regions.append(comment_region(pdf, annot, self.number))
            provenance = Provenance(source_format="pdf", page=page_number, path="annots")
            marker = TextRun(text="[comment %d]" % self.number,
                             note_reference_type="comment", note_reference_number=self.number,
                             provenance=provenance)
            paragraphs = [Paragraph(runs=[TextRun(text=line, provenance=provenance)], provenance=provenance)
                          for line in contents.splitlines() if line.strip()]
            result.extend([Paragraph(runs=[marker], provenance=provenance),
                           Comment(number=self.number, author=author,
                                   paragraphs=paragraphs)])
        return result


class DestinationResolver:
    """문서 로컬 목적지만 페이지로 푼다. 이름 트리와 별칭에는 순환/개수 상한이 있다."""
    def __init__(self, pdf, pages, load_names=True):
        self.pdf = pdf
        self.page_numbers = {id(page): number for number, (page, _resources) in enumerate(pages, 1)}
        self.targets = set()
        self.names = {}
        if not load_names:
            return
        root = pdf.resolve(pdf.trailer.get("Root"))
        if not isinstance(root, dict):
            return
        dests = pdf.resolve(root.get("Dests"))
        if isinstance(dests, dict):
            for key, value in list(dests.items())[:4096]:
                self.names[str(key)] = value
        names = pdf.resolve(root.get("Names"))
        if isinstance(names, dict):
            pending = [(names.get("Dests"), 0)]
            seen = set()
            while pending and len(seen) < 4096 and len(self.names) < 4096:
                ref, depth = pending.pop()
                if ref is None:
                    continue
                key = (ref.num, ref.gen) if isinstance(ref, PDFRef) else id(ref)
                if key in seen or depth > 32:
                    pdf.warnings.append("WARN: PDF 이름 있는 목적지 트리의 순환 또는 깊이 한도 초과")
                    continue
                seen.add(key)
                node = pdf.resolve(ref)
                if not isinstance(node, dict):
                    continue
                pairs = pdf.resolve(node.get("Names"))
                if isinstance(pairs, list):
                    for i in range(0, min(len(pairs) - 1, (4096 - len(self.names)) * 2), 2):
                        name = pdf.resolve(pairs[i])
                        if isinstance(name, bytes):
                            self.names[text_string(name)] = pairs[i + 1]
                kids = pdf.resolve(node.get("Kids"))
                if isinstance(kids, list):
                    pending.extend((kid, depth + 1) for kid in kids[:4096 - len(seen) - len(pending)])

    def page_number(self, destination):
        seen = set()
        for _ in range(32):
            destination = self.pdf.resolve(destination)
            if isinstance(destination, list) and destination:
                page = self.pdf.resolve(destination[0])
                return self.page_numbers.get(id(page)) if isinstance(page, dict) else None
            if isinstance(destination, dict):
                destination = destination.get("D")
                continue
            if isinstance(destination, (bytes, PDFName)):
                name = text_string(destination) if isinstance(destination, bytes) else str(destination)
                if name in seen:
                    self.pdf.warnings.append("WARN: PDF 이름 있는 목적지 별칭 순환")
                    return None
                seen.add(name)
                destination = self.names.get(name)
                continue
            return None
        self.pdf.warnings.append("WARN: PDF 목적지 깊이 한도 초과")
        return None

    def annotation_target(self, annot):
        action = self.pdf.resolve(annot.get("A"))
        if isinstance(action, dict):
            kind = str(action.get("S"))
            if kind == "URI":
                return text_string(self.pdf.resolve(action.get("URI"))).strip()
            if kind != "GoTo":
                return ""
            destination = action.get("D")
        else:
            destination = annot.get("Dest")
        page = self.page_number(destination)
        if page is None:
            if destination is not None:
                self.pdf.warnings.append("WARN: PDF 링크 목적지를 페이지로 풀지 못함")
            return ""
        self.targets.add(page)
        return "#page-%d" % page


@dataclass
class LinkRegion:
    target: str
    polygons: list
    matched: bool = False


def _polygon(values):
    if not isinstance(values, list) or len(values) not in (4, 8):
        return None
    try:
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            return None
        if len(values) == 4:
            left, right = sorted((values[0], values[2]))
            bottom, top = sorted((values[1], values[3]))
            if left >= right or bottom >= top:
                return None
            return [(left, bottom), (right, bottom), (right, top), (left, top)]
        points = list(zip(values[::2], values[1::2]))
        cx, cy = sum(x for x, _ in points) / 4, sum(y for _, y in points) / 4
        points.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        turns = [(points[(i + 1) % 4][0] - points[i][0]) *
                 (points[(i + 2) % 4][1] - points[(i + 1) % 4][1]) -
                 (points[(i + 1) % 4][1] - points[i][1]) *
                 (points[(i + 2) % 4][0] - points[(i + 1) % 4][0]) for i in range(4)]
        if all(turn > 0 and math.isfinite(turn) for turn in turns):
            return points
    except (OverflowError, ValueError):
        pass
    return None


def _contains(polygon, x, y):
    # 두 QuadPoints 순서를 모두 반시계방향으로 정규화한 뒤 볼록 사각형을 검사한다.
    return all((polygon[(i + 1) % 4][0] - a) * (y - b) -
               (polygon[(i + 1) % 4][1] - b) * (x - a) >= -1e-7
               for i, (a, b) in enumerate(polygon))


def _on_boundary(polygon, x, y):
    """An exact shared edge may select one glyph and exclude its neighbor."""
    # The former 1e-5pt allowance covers observed coordinate rounding; the
    # wider 1e-4pt inset also accepted actual inward cuts of a glyph.
    tolerance = 1e-5
    for index, (ax, ay) in enumerate(polygon):
        bx, by = polygon[(index + 1) % 4]
        length = math.hypot(bx - ax, by - ay)
        if not length:
            continue
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if (abs(cross) <= tolerance * length
                and min(ax, bx) - tolerance <= x <= max(ax, bx) + tolerance
                and min(ay, by) - tolerance <= y <= max(ay, by) + tolerance):
            return True
    return False


def link_regions(pdf, page, destinations):
    regions = []
    for ref in page_annotations(pdf, page):
        annot = pdf.resolve(ref)
        if not isinstance(annot, dict) or str(annot.get("Subtype")) != "Link":
            continue
        target = destinations.annotation_target(annot)
        if not target:
            continue
        quads = pdf.resolve(annot.get("QuadPoints"))
        polygons = []
        if isinstance(quads, list):
            for pos in range(0, min(len(quads), 8 * 256) - 7, 8):
                polygon = _polygon(quads[pos:pos + 8])
                if polygon:
                    polygons.append(polygon)
        if not polygons:
            rect = _polygon(pdf.resolve(annot.get("Rect")))
            if rect:
                polygons.append(rect)
        regions.append(LinkRegion(target, polygons))
    return regions



def comment_region(pdf, annot, number):
    """ISO 32000-1 §12.5.6.4/10: markup quads and text-note rectangles."""
    polygons = []
    subtype = str(annot.get("Subtype"))
    if subtype in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
        quads = pdf.resolve(annot.get("QuadPoints"))
        # The broad Rect includes neighboring lines: invalid/missing quads must
        # defer instead of anchoring against the entire annotation appearance.
        if isinstance(quads, list) and len(quads) % 8 == 0 and len(quads) <= 8 * 256:
            for pos in range(0, len(quads), 8):
                polygon = _polygon(quads[pos:pos + 8])
                if not polygon:
                    return LinkRegion(str(number), [])
                polygons.append(polygon)
    elif subtype == "Text":
        polygon = _polygon(pdf.resolve(annot.get("Rect")))
        if polygon:
            polygons.append(polygon)
    return LinkRegion(str(number), polygons)


def attach_comments(fragments, regions, warnings):
    """Select safely with link geometry, then place one reference per comment.

    Keep source text/widths unchanged so table and paragraph detection still use
    the original page. The final layout inserts markers between text runs.
    """
    if not regions:
        return
    copies = [replace(frag, link_spans=[]) for frag in fragments]
    geometry_warnings = []
    attach_links(copies, regions, geometry_warnings, allow_clipped_edges=False)
    warnings.extend(w.replace("링크", "주석") for w in geometry_warnings)
    endings = {}
    for original, selected in zip(fragments, copies):
        original.comment_spans = list(selected.link_spans)
        for first, last, target in selected.link_spans:
            last = first + len(original.text[first:last].rstrip())
            candidate = (original.order, last)
            if target not in endings or candidate > endings[target][0]:
                endings[target] = (candidate, original)
    for target, ((_order, last), frag) in endings.items():
        frag.comment_markers.append((last, int(target)))


def attach_links(fragments, regions, warnings, allow_clipped_edges=False):
    """글리프 중앙점이 주석 사각형에 있는 문자만 링크로 만든다."""
    # Identical annotations do not change geometry. Keep every annotation in
    # the input (and benchmark denominator), but spend the bounded work once.
    unique = {}
    groups = {}
    for region in regions:
        key = (region.target, tuple(tuple(polygon) for polygon in region.polygons))
        unique.setdefault(key, region)
        groups.setdefault(key, []).append(region)
    _attach_unique_links(fragments, list(unique.values()), warnings, allow_clipped_edges)
    for key, original in unique.items():
        if original.matched:
            for region in groups[key]:
                region.matched = True


# A clipped link edge may stop at these neighbours without splitting a word.
# Apostrophes, slashes, hyphens and similar joiners continue the word.
_OPENING_BOUNDARIES = "([{<\"\u201c\u00ab\u300c\u300e\uff08\u3010\u300a\u3008"
_CLOSING_BOUNDARIES = (")]}>\"\u201d\u00bb"
                       "\uff0c\u3002\uff1b\uff1a\uff01\uff1f\u3001"
                       "\u300d\u300f\uff09\u3011\u300b\u3009")
# ASCII sentence marks also occur inside tokens (www.example.com, 3.14, 1,000);
# they end a word only before whitespace, a closing boundary or line end.
_SENTENCE_MARKS = ",.;:!?"
# Neighbour lookups for clipped edges have their own budget. When it runs out
# only the clipped links still unchecked are deferred, as before clipped-edge
# support; links with exact glyph edges on the page keep their body text.
_NEIGHBOR_CHECK_LIMIT = 2000000


def _attach_unique_links(fragments, regions, warnings, allow_clipped_edges):
    checks = 0
    spans = []
    matched = set()
    blocked = set()
    ambiguous = set()
    # Atomicity belongs to an annotation, not to its URL. The same destination
    # can occur in separate, independently measurable areas of a page. Regions
    # sharing a selected glyph remain one conservative ambiguity component.
    parents = list(range(len(regions)))
    ranks = [0] * len(regions)

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def join(indices):
        if indices:
            first = root(indices[0])
            for index in indices[1:]:
                other = root(index)
                if first == other:
                    continue
                if ranks[first] < ranks[other]:
                    first, other = other, first
                parents[other] = first
                if ranks[first] == ranks[other]:
                    ranks[first] += 1

    bounds = []
    for index, region in enumerate(regions):
        points = [point for polygon in region.polygons for point in polygon]
        if points:
            bounds.append((min(y for _, y in points), index,
                           min(x for x, _ in points), max(x for x, _ in points),
                           max(y for _, y in points)))
    bounds.sort()
    lower_edges = [bound[0] for bound in bounds]
    # Runs whose end glyphs can continue a word across a Tj/TJ split.
    neighbor_checks = 0
    neighbor_warned = []
    runs = {}
    for frag in fragments:
        direction = math.hypot(frag.dir_x, frag.dir_y)
        up = math.hypot(frag.up_x, frag.up_y)
        if (frag.text and frag.size and direction and up and
                len(frag.char_offsets) == len(frag.text) + 1):
            runs[id(frag)] = (frag, frag.dir_x / direction, frag.dir_y / direction,
                              frag.up_x / up, frag.up_y / up)

    def touching(run, side):
        """Runs that line assembly joins to `run` before (0) or after (1) it.

        Line assembly joins runs whose gap is at most half a space, and any
        overlap. Order, not distance alone, picks the side, so the previous
        glyph of a one-glyph-per-Tj line is not taken as the next one.
        Returns None when the neighbour check budget is exhausted.
        """
        nonlocal neighbor_checks
        frag, ux, uy, vx, vy = run
        start, end = frag.char_offsets[0], frag.char_offsets[-1]
        found = []
        for other_run in runs.values():
            other, ox, oy = other_run[:3]
            neighbor_checks += 1
            if neighbor_checks > _NEIGHBOR_CHECK_LIMIT:
                if not neighbor_warned:
                    neighbor_warned.append(True)
                    warnings.append("WARN: PDF 링크 이웃 글자 검사 한도 초과 — 잘린 경계 링크는 본문 연결 보류")
                return None
            if other is frag or ux * ox + uy * oy < 0.999:
                continue
            ax, ay = other.x - frag.x, other.y - frag.y
            if abs(ax * vx + ay * vy) > 0.3 * min(frag.size, other.size):
                continue
            base = ax * ux + ay * uy
            other_start = base + other.char_offsets[0]
            other_end = base + other.char_offsets[-1]
            limit = (max(frag.space_width, other.space_width) * 0.5
                     or 0.125 * min(frag.size, other.size))
            if (side == 1 and start < other_start <= end + limit or
                    side == 0 and other_start < start and other_end >= start - limit):
                found.append(other_run)
        return found

    for frag in fragments:
        if frag.link_geometry_reliable and len(frag.char_offsets) == len(frag.text) + 1:
            continue
        # 폭이 불명확한 줄은 링크 일부만 살아남아 단어가 잘리는 것을 막는다.
        # x 전진 자체가 불확실하므로 가로 겹침을 추정해 후보를 좁히지 않는다.
        for index, region in enumerate(regions):
            for polygon in region.polygons:
                checks += 1
                if checks > 2000000:
                    warnings.append("WARN: PDF 링크 기하 검사 한도 초과 — 본문 연결 생략")
                    return
                low, high = min(y for _, y in polygon), max(y for _, y in polygon)
                if min(frag.y, frag.y + frag.size) <= high and max(frag.y, frag.y + frag.size) >= low:
                    blocked.add(index)
                    break
    for frag in fragments:
        if not frag.link_geometry_reliable:
            continue
        if len(frag.char_offsets) != len(frag.text) + 1 or not frag.size:
            continue
        direction = math.hypot(frag.dir_x, frag.dir_y)
        up = math.hypot(frag.up_x, frag.up_y)
        if not direction or not up:
            continue
        clipped_edges = []
        ux, uy = frag.dir_x / direction, frag.dir_y / direction
        vx, vy = frag.up_x / up, frag.up_y / up
        # Broad phase: all tested character points lie on this baseline-parallel
        # segment. Disjoint regions cannot select or cut any glyph in the run.
        ends = [(frag.x + ux * d + vx * frag.size * 0.5,
                 frag.y + uy * d + vy * frag.size * 0.5)
                for d in (min(frag.char_offsets), max(frag.char_offsets))]
        left, right = min(x for x, _ in ends), max(x for x, _ in ends)
        bottom, top = min(y for _, y in ends), max(y for _, y in ends)
        candidates = []
        for low, region_index, x0, x1, high in bounds[:bisect_right(lower_edges, top + 1e-7)]:
            checks += 1
            if checks > 2000000:
                warnings.append("WARN: PDF 링크 기하 검사 한도 초과 — 본문 연결 생략")
                return
            if high + 1e-7 >= bottom and x1 + 1e-7 >= left and x0 - 1e-7 <= right:
                candidates.append((region_index, regions[region_index]))
        targets = []
        for index, char in enumerate(frag.text):
            # 폰트 코드 폭으로 계산한 진행 중앙과 글자 높이 중앙이다.
            distance = (frag.char_offsets[index] + frag.char_offsets[index + 1]) / 2
            x, y = frag.x + ux * distance + vx * frag.size * 0.5, frag.y + uy * distance + vy * frag.size * 0.5
            hits = []
            for region_index, region in candidates:
                if region_index in blocked:
                    continue
                for polygon in region.polygons:
                    checks += 3
                    if checks > 2000000:
                        warnings.append("WARN: PDF 링크 기하 검사 한도 초과 — 본문 연결 생략")
                        return
                    middle = _contains(polygon, x, y)
                    if not char.isspace():
                        first, last = frag.char_offsets[index:index + 2]
                        # Test the exact glyph ends. A small difference at the
                        # boundary uses the measured 1e-5 allowance below;
                        # a deeper inward cut remains ambiguous.
                        edges = [(frag.x + ux * d + vx * frag.size * 0.5,
                                  frag.y + uy * d + vy * frag.size * 0.5)
                                 for d in (first, last)]
                        edge_inside = [_contains(polygon, px, py) for px, py in edges]
                        uncertain = [side for side, ((px, py), inside) in enumerate(
                            zip(edges, edge_inside)) if inside != middle and
                            not _on_boundary(polygon, px, py)]
                        if uncertain:
                            # A clipped outer edge can still select its whole
                            # glyph by center. Both edges outside, or an edge
                            # inside while its center is outside, is ambiguous.
                            if (allow_clipped_edges and middle and len(uncertain) == 1
                                    and sum(edge_inside) == 1):
                                clipped_edges.append((index, region_index, uncertain[0]))
                            else:
                                ambiguous.add(region_index)
                    if middle:
                        hits.append(region_index)
                        break
            unique = {regions[i].target for i in hits}
            if len(unique) > 1 and not char.isspace():
                ambiguous.update(hits)
            target = next(iter(unique)) if len(unique) == 1 else ""
            if not char.isspace():
                join(hits)
            targets.append((target, tuple(hits)))
            if target and not char.isspace():
                matched.update(hits)
        for char_index, region_index, side in clipped_edges:
            neighbor = char_index - 1 if side == 0 else char_index + 1
            if 0 <= neighbor < len(targets):
                neighbors = [(runs[id(frag)], neighbor, region_index in targets[neighbor][1])]
            else:
                # The word can continue in another run on this baseline (a TJ
                # split or a separate Tj); its touching glyph gets the same test.
                adjacent = touching(runs[id(frag)], side)
                if adjacent is None:
                    ambiguous.add(region_index)
                    continue
                neighbors = []
                for run in adjacent:
                    other, ox, oy, ovx, ovy = run
                    glyph = len(other.text) - 1 if side == 0 else 0
                    distance = (other.char_offsets[glyph] + other.char_offsets[glyph + 1]) / 2
                    cx = other.x + ox * distance + ovx * other.size * 0.5
                    cy = other.y + oy * distance + ovy * other.size * 0.5
                    neighbor_checks += len(regions[region_index].polygons)
                    neighbors.append((run, glyph, any(
                        _contains(polygon, cx, cy) for polygon in regions[region_index].polygons)))
            for run, glyph, inside in neighbors:
                char = run[0].text[glyph]
                if side == 0:
                    boundary = char.isspace() or char in _OPENING_BOUNDARIES
                elif char.isspace() or char in _CLOSING_BOUNDARIES:
                    boundary = True
                elif char in _SENTENCE_MARKS:
                    if glyph + 1 < len(run[0].text):
                        following = [run[0].text[glyph + 1]]
                    else:
                        after = touching(run, 1)
                        # An unchecked continuation cannot prove a word end.
                        following = None if after is None else [item[0].text[0] for item in after]
                    boundary = following is not None and all(
                        c.isspace() or c in _CLOSING_BOUNDARIES for c in following)
                else:
                    boundary = False
                if inside or not boundary:
                    ambiguous.add(region_index)
                    break
        start = 0
        while start < len(targets):
            end = start + 1
            while end < len(targets) and targets[end] == targets[start]:
                end += 1
            target, indices = targets[start]
            if target and frag.text[start:end].strip():
                spans.append((frag, start, end, target, indices))
            start = end
    # 한도 초과는 부분 연결을 남기지 않는다.
    blocked_roots = {root(index) for index in blocked | ambiguous}
    for frag, start, end, target, indices in spans:
        if not any(root(index) in blocked_roots for index in indices):
            if frag.link_spans and frag.link_spans[-1][1:] == (start, target):
                first, _last, _target = frag.link_spans[-1]
                frag.link_spans[-1] = (first, end, target)
            else:
                frag.link_spans.append((start, end, target))
    for index in matched:
        if root(index) not in blocked_roots:
            regions[index].matched = True
