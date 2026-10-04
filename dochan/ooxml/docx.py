"""Native DOCX reader."""
from dataclasses import dataclass, replace
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import posixpath
import re
import zipfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

from ..utils import safe_xml as etree

from ..conversion import AssetRef, Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.equation import Equation
from ..model.header_footer import Comment, Footnote, HeaderFooter
from ..model.image import Image
from ..model.table import Cell, Table
from .package import OOXMLPackage
from .math import _omml_to_latex

# 문서당 이미지 바이너리 추출 총량 상한 (메모리 방어)
_MAX_IMAGE_BYTES_TOTAL = 100 * 1024 * 1024

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
DC_NS = "http://purl.org/dc/elements/1.1/"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
V_NS = "urn:schemas-microsoft-com:vml"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
DGM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
NS = {
    "w": W_NS,
    "r": R_NS,
    "rel": REL_NS,
    "wp": WP_NS,
    "a": A_NS,
    "mc": MC_NS,
    "dc": DC_NS,
    "w15": W15_NS,
    "v": V_NS,
    "m": M_NS,
    "dgm": DGM_NS,
}
MAX_NESTED_TABLE_DEPTH = 32
MAX_TABLE_CELLS = 200000
MAX_STRUCTURE_DEPTH = 64
MAX_NUMBERING_VALUE = 100000
MAX_NUMBERING_LEVEL = 8
MAX_NUMBERING_TEMPLATE_CHARS = 256
MAX_IMAGE_ASSET_REFS = 10000
MAX_DIAGNOSTIC_PATH_CHARS = 256
MAX_DOCUMENT_CHARTS = 128
MAX_SMARTART_PARTS = 128
MAX_SMARTART_BYTES = 16 * 1024 * 1024
MAX_SMARTART_OUTPUT_CHARS = 1000000
MAX_CHART_BYTES_TOTAL = 64 * 1024 * 1024
_STRUCTURE_DEPTH_ERROR = (
    f"ERR: DOCX structure depth limit exceeded ({MAX_STRUCTURE_DEPTH})"
)


class _HTMLAltChunkTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._parts = []
        self._skip_depth = 0
        self._row_cells = []
        self._cell_parts = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "head"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in {"p", "div", "li", "br"}:
            self._flush_text()
        elif tag == "tr":
            self._flush_text()
            self._row_cells = []
        elif tag in {"td", "th"}:
            self._cell_parts = []
        elif tag == "img":
            alt = dict(attrs).get("alt", "").strip()
            if alt:
                self._append_text(alt)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._skip_depth:
            if tag in {"script", "style", "head"}:
                self._skip_depth -= 1
            return
        if tag in {"p", "div", "li"}:
            self._flush_text()
        elif tag in {"td", "th"}:
            if self._cell_parts is not None:
                text = _normalize_space(" ".join(self._cell_parts))
                self._row_cells.append(text)
                self._cell_parts = None
        elif tag == "tr":
            if self._row_cells:
                self.blocks.append(" | ".join(self._row_cells))
                self._row_cells = []

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._append_text(data)

    def close(self):
        super().close()
        self._flush_text()

    def _append_text(self, text: str):
        if self._cell_parts is not None:
            self._cell_parts.append(text)
        else:
            self._parts.append(text)

    def _flush_text(self):
        text = _normalize_space(" ".join(self._parts))
        if text:
            self.blocks.append(text)
        self._parts = []


def _normalize_space(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def _bounded_diagnostic_path(path: str) -> str:
    value = str(path).replace("\r", "\\r").replace("\n", "\\n")
    if len(value) <= MAX_DIAGNOSTIC_PATH_CHARS:
        return value
    return value[:MAX_DIAGNOSTIC_PATH_CHARS - 3] + "..."


def _w_attr(elem, name: str) -> str:
    if elem is None:
        return ""
    return elem.get(f"{{{W_NS}}}{name}", "")


def _w_on_off_enabled(elem, *, false_values=None) -> bool:
    """Interpret one WordprocessingML on/off property, including explicit false."""
    if elem is None:
        return False
    disabled = {"0", "false", "off", "no"}
    if false_values:
        disabled.update(false_values)
    value = _w_attr(elem, "val").strip().lower()
    return not value or value not in disabled


def _r_attr(elem, name: str) -> str:
    if elem is None:
        return ""
    return elem.get(f"{{{R_NS}}}{name}", "")


def _w15_attr(elem, name: str) -> str:
    if elem is None:
        return ""
    return elem.get(f"{{{W15_NS}}}{name}", "")


def _resolve_internal_target(base_dir: str, target: str) -> str:
    slash_target = target.replace("\\", "/")
    decoded_target = unquote(slash_target)
    if (
        not slash_target
        or any(ord(char) < 32 for char in decoded_target)
        or decoded_target.startswith("//")
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", decoded_target)
    ):
        raise ValueError("invalid internal relationship target")

    def resolve(candidate: str) -> str:
        if candidate.startswith("/"):
            resolved = posixpath.normpath(candidate.lstrip("/"))
        else:
            resolved = posixpath.normpath(posixpath.join(base_dir, candidate))
        if (
            resolved in {"", ".", ".."}
            or resolved.startswith("../")
            or resolved.startswith("/")
            or ".." in resolved.split("/")
        ):
            raise ValueError("internal relationship target escapes package root")
        return resolved

    # Inspect the URI-decoded form as well as the literal ZIP member path so
    # percent-encoded traversal cannot be emitted into Markdown targets.
    resolve(decoded_target)
    return resolve(slash_target)


@dataclass
class _NumberingLevel:
    fmt: str = "decimal"
    text: str = "%1."
    start: int = 1


@dataclass
class _RunStyle:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikeout: bool = False
    superscript: bool = False
    subscript: bool = False


class DOCXReader:
    format_name = "docx"
    extensions = (".docx",)

    def read(self, file_path: str) -> Document:
        doc = Document(source_format="docx")
        self._parents = {}
        self._sibling_positions = {}
        self._numbering_counts = {}
        self._note_reference_numbers = {}
        self._note_reference_order = []
        self._comment_reference_numbers = {}
        self._comment_reference_order = []
        self._annotated_comments = set()
        self._image_asset_ids = set()
        self._image_asset_count = 0
        self._image_asset_limit_reported = False
        self._assets = []
        self._image_elements = []
        self._image_occurrences = 0
        self._caption_styles = set()
        self._smartart_targets = set()
        self._smartart_parts = {}
        self._smartart_bytes = 0
        self._smartart_output_chars = 0
        self._chart_parts = {}
        self._chart_cell_counts = {}
        self._chart_occurrences = 0
        from .xlsx import MAX_CHART_OUTPUT_CELLS
        self._chart_output_remaining = MAX_CHART_OUTPUT_CELLS
        self._image_bytes_total = 0
        self._table_cell_budget = MAX_TABLE_CELLS
        self._active_document_errors = doc.errors
        try:
            with OOXMLPackage(file_path) as package:
                self._package = package
                self._document_part = self._main_document_part(package)
                root = package.read_xml_part(self._document_part)
                self._register_tree(root)
                self._document_relationships = self._read_document_relationships(package)
                self._active_relationships = self._document_relationships
                self._preload_smartart(package, self._document_relationships)
                self._alt_chunk_data = self._read_alt_chunk_data(package, self._document_relationships)
                self._image_data_cache = self._preload_image_bytes(package)
                self._record_embedded_relationship_assets(package)
                self._paragraph_styles = self._read_paragraph_styles(package)
                self._chart_parts = self._read_chart_parts(package)
                self._run_styles = self._read_run_styles(package)
                numbering = self._read_numbering(package)
                self._numbering = numbering
                self._notes = {
                    "footnote": self._read_notes(package, "word/footnotes.xml", "footnote"),
                    "endnote": self._read_notes(package, "word/endnotes.xml", "endnote"),
                }
                self._comments = self._read_notes(package, "word/comments.xml", "comment")
                headers, footers = self._read_headers_footers(package, root)
                core_properties = self._read_core_properties(package)
        except (
            OSError,
            KeyError,
            ValueError,
            zipfile.BadZipFile,
            etree.XMLSyntaxError,
        ) as exc:
            self._parents.clear()
            self._sibling_positions.clear()
            doc.errors.append(f"ERR: DOCX package parse failed: {exc}")
            return doc

        section = Section(
            provenance=Provenance(source_format="docx", section=0, path=self._document_part)
        )
        body = root.find("w:body", namespaces=NS)
        if body is None:
            self._parents.clear()
            self._sibling_positions.clear()
            doc.errors.append("ERR: DOCX body not found")
            doc.sections.append(section)
            return doc

        section.elements.extend(headers)
        section.elements.extend(self._core_property_elements(core_properties))
        section.elements.extend(self._parse_block_elements(body, [0], numbering))

        section.elements.extend(footers)

        for note_type, note_id in self._note_reference_order:
            note = self._notes.get(note_type, {}).get(note_id)
            if note and note.text.strip():
                section.elements.append(note)

        for comment_id in self._comment_reference_order:
            comment = getattr(self, "_comments", {}).get(comment_id)
            if comment and comment.text.strip():
                section.elements.append(comment)

        section.elements.extend(image for image in getattr(self, "_image_elements", [])
                                if not getattr(image, "_anchored", False))
        doc.assets = getattr(self, "_assets", [])
        doc.sections.append(section)
        self._release_source_elements(doc)
        self._parents.clear()
        self._sibling_positions.clear()
        self._package = None
        self._active_relationships = {}
        self._alt_chunk_data = {}
        return doc

    def _register_tree(self, root):
        """Register each story once; direct subtree parsing uses the same context."""
        if not hasattr(self, "_parents"):
            self._parents = {}
        if not hasattr(self, "_sibling_positions"):
            self._sibling_positions = {}
        if root not in self._parents:
            for parent in root.iter():
                for position, child in enumerate(parent):
                    self._parents[child] = parent
                    self._sibling_positions[child] = position
            self._parents[root] = None

    def _release_source_elements(self, doc):
        """캡션 결합이 끝나면 모델에 임시로 붙인 XML 참조를 제거한다."""
        stack = [doc]
        seen = set()
        while stack:
            value = stack.pop()
            if id(value) in seen:
                continue
            seen.add(id(value))
            if isinstance(value, (list, tuple)):
                stack.extend(value)
            elif hasattr(value, "__dict__"):
                value.__dict__.pop("_source_element", None)
                value.__dict__.pop("_image_target", None)
                stack.extend(value.__dict__.values())

    def _parse_block_elements(
        self,
        container,
        paragraph_index_ref: List[int],
        numbering,
        depth: int = 0,
    ) -> List[object]:
        if not self._structure_depth_allowed(depth):
            return []
        self._register_tree(container)
        elements = []
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(
                    child,
                    paragraph_index_ref[0],
                    structure_depth=depth,
                    numbering=numbering,
                )
                paragraph_index_ref[0] += 1
                elements.extend(self._paragraph_flow(para))
            elif child.tag in (f"{{{M_NS}}}oMathPara", f"{{{M_NS}}}oMath"):
                elements.extend(self._equations_in(child, include_self=True))
            elif child.tag == f"{{{W_NS}}}commentRangeEnd":
                annotation = self._comment_annotation(_w_attr(child, "id"))
                if annotation:
                    elements.append(Paragraph(runs=[TextRun(text=annotation)]))
            elif child.tag == f"{{{W_NS}}}altChunk":
                alt_chunk_elements = self._parse_alt_chunk(child, paragraph_index_ref[0])
                paragraph_index_ref[0] += len(alt_chunk_elements)
                elements.extend(alt_chunk_elements)
            elif child.tag == f"{{{W_NS}}}tbl":
                table = self._parse_table(
                    child, paragraph_index_ref[0], structure_depth=depth)
                table._source_element = child
                elements.append(table)
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
                f"{{{W_NS}}}moveTo",
            ):
                elements.extend(
                    self._parse_block_elements(
                        child, paragraph_index_ref, numbering, depth + 1,
                    )
                )
            elif child.tag == f"{{{W_NS}}}moveFrom":
                continue
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(child)
                elements.extend(
                    self._parse_block_elements(
                        preferred, paragraph_index_ref, numbering, depth + 1,
                    )
                )
        return self._attach_captions(elements)

    def _paragraph_flow(self, para):
        """이미지 참조는 문단에 남기고 블록 차트만 앵커에서 펼친다."""
        elements = []
        runs = []
        images = []
        has_other_text = any(run.text.strip() and run.equation is None
                             and not run.note_ref and not run.note_reference_type
                             and not getattr(run, '_bookmark_annotation', False)
                             and not getattr(run, '_equation_annotation', False)
                             for run in para.runs)

        def flush():
            if any(r.text.strip() for r in runs):
                block = replace(para, runs=list(runs),
                                heading_level=para.heading_level if not elements else 0)
                block._source_element = getattr(para, "_source_element", None)
                if len(images) == 1:
                    block._image_target = images[0]
                elements.append(block)
            elements.extend(images)
            runs.clear()
            images.clear()

        for run in para.runs:
            if run.equation is not None:
                if has_other_text:
                    runs.append(run)
                else:
                    flush()
                    elements.append(run.equation)
                continue
            flow = getattr(run, "_flow_elements", None)
            if flow is None:
                runs.append(run)
                continue
            for item in flow:
                if isinstance(item, Image):
                    item._source_element = getattr(para, "_source_element", None)
                    item._anchored = True
                    images.append(item)
                else:
                    flush()
                    elements.append(item)
            if run.text:
                runs.append(replace(run))
        flush()
        kind = getattr(para, "_caption_kind", "")
        if kind and len(elements) == 1 and isinstance(elements[0], Paragraph):
            elements[0]._caption_kind = kind
        return elements

    def _caption_kind(self, elem):
        instructions = ["".join(n.text or "" for n in elem.findall(".//w:instrText", namespaces=NS))]
        instructions.extend(_w_attr(n, "instr") for n in elem.findall(".//w:fldSimple", namespaces=NS))
        for instruction in instructions:
            match = re.search(r"\bSEQ\s+(?:\"([^\"]+)\"|([^\s\\]+))", instruction, re.I)
            if match:
                name = (match.group(1) or match.group(2)).casefold()
                if name in {"table", "표"}:
                    return "table"
                if name in {"figure", "그림"}:
                    return "image"
                return "" if name in {"equation", "수식"} else "any"
        style = _w_attr(elem.find("w:pPr/w:pStyle", namespaces=NS), "val")
        visited = set()
        while style and style not in visited and len(visited) < MAX_STRUCTURE_DEPTH:
            visited.add(style)
            if style.casefold() == "caption" or style in getattr(self, "_caption_styles", set()):
                return "any"
            style = getattr(self, "_paragraph_styles", {}).get(style, "")
        return ""

    def _attach_captions(self, elements):
        remove = set()
        for index, elem in enumerate(elements):
            kind = getattr(elem, "_caption_kind", "")
            if not kind:
                continue
            candidates = []
            for offset, side in ((-1, "BOTTOM"), (1, "TOP")):
                position = index + offset
                if 0 <= position < len(elements):
                    target = elements[position]
                    target = getattr(target, "_image_target", target)
                    if isinstance(target, (Table, Image)) and not target.caption and (kind == "any" or
                            kind == "table" and isinstance(target, Table) or
                            kind == "image" and isinstance(target, Image)):
                        source = getattr(elem, "_source_element", None)
                        target_source = getattr(target, "_source_element", None)
                        if source is not None and target_source is not None:
                            if self._caption_neighbor(source, offset) is not target_source:
                                continue
                        candidates.append((target, side))
            # 두 대상 사이의 모호한 캡션은 추측해 옮기지 않는다.
            if len(candidates) == 1 and not candidates[0][0].caption:
                target, side = candidates[0]
                target.caption = [elem]
                target.caption_side = side
                remove.add(index)
        return [elem for index, elem in enumerate(elements) if index not in remove]

    def _caption_neighbor(self, source, direction):
        """투명 래퍼만 건너뛰고 빈 문단을 포함한 실제 다음 블록을 찾는다."""
        wrappers = {f"{{{W_NS}}}{name}" for name in
                    ("sdt", "sdtContent", "smartTag", "ins", "moveTo")}
        wrappers.update({f"{{{MC_NS}}}Choice", f"{{{MC_NS}}}Fallback"})

        def edge(node):
            if node.tag == f"{{{MC_NS}}}AlternateContent":
                return edge(self._alternate_content_preferred_child(node))
            if node.tag in wrappers:
                children = list(node)
                for child in children if direction > 0 else reversed(children):
                    candidate = edge(child)
                    if candidate is not None:
                        return candidate
                return None
            if node.tag in {f"{{{W_NS}}}sdtPr", f"{{{W_NS}}}sdtEndPr",
                            f"{{{W_NS}}}del", f"{{{W_NS}}}moveFrom"}:
                return None
            return node

        current = source
        while current is not None:
            parent = self._parents.get(current)
            if parent is None:
                return None
            position = self._sibling_positions[current]
            following = (range(position + 1, len(parent)) if direction > 0
                         else range(position - 1, -1, -1))
            for sibling_index in following:
                sibling = parent[sibling_index]
                candidate = edge(sibling)
                if candidate is not None:
                    return candidate
            current = parent
            if current is None or current.tag not in wrappers | {f"{{{MC_NS}}}AlternateContent"}:
                return None
        return None

    def _structure_depth_allowed(self, depth: int) -> bool:
        if depth <= MAX_STRUCTURE_DEPTH:
            return True
        errors = getattr(self, "_active_document_errors", None)
        if errors is not None and _STRUCTURE_DEPTH_ERROR not in errors:
            errors.append(_STRUCTURE_DEPTH_ERROR)
        return False

    def _read_core_properties(self, package: OOXMLPackage) -> Dict[str, str]:
        if not package.exists("docProps/core.xml"):
            return {}
        root = package.read_xml_part("docProps/core.xml")
        return {
            "title": self._child_text(root, "dc:title"),
            "creator": self._child_text(root, "dc:creator"),
        }

    def _child_text(self, elem, path: str) -> str:
        child = elem.find(path, namespaces=NS)
        return (child.text or "").strip() if child is not None else ""

    def _core_property_elements(self, core_properties: Dict[str, str]) -> List[Paragraph]:
        elements = []
        title = core_properties.get("title", "")
        if title:
            elements.append(
                Paragraph(
                    runs=[TextRun(text=title)],
                    heading_level=1,
                    provenance=Provenance(source_format="docx", path="docProps/core.xml"),
                )
            )
        creator = core_properties.get("creator", "")
        if creator:
            elements.append(
                Paragraph(
                    runs=[TextRun(text=f"Author: {creator}")],
                    provenance=Provenance(source_format="docx", path="docProps/core.xml"),
                )
            )
        return elements

    def _main_document_part(self, package: OOXMLPackage) -> str:
        if package.exists("_rels/.rels"):
            relationships = package.read_xml_part("_rels/.rels")
            for rel in relationships.findall("rel:Relationship", namespaces=NS):
                if (rel.get("Type", "").endswith("/officeDocument")
                        and rel.get("TargetMode", "").lower() != "external"):
                    target = self._validated_internal_relationship_target(
                        "", rel.get("Target", ""), "_rels/.rels", rel.get("Id", ""))
                    if target:
                        return target
        return "word/document.xml"

    def _parse_paragraph(
        self,
        p_elem,
        paragraph_index: int,
        path: str = None,
        structure_depth: int = 0,
        numbering=None,
    ) -> Paragraph:
        para = Paragraph(
            provenance=Provenance(
                source_format="docx",
                section=0,
                paragraph=paragraph_index,
                path=path or self._document_part,
            )
        )
        para._source_element = p_elem
        para.heading_level = self._heading_level(p_elem)
        para._caption_kind = self._caption_kind(p_elem)
        # 부모 목록 표지는 자식 텍스트박스가 카운터를 소비하기 전에 예약한다.
        if numbering is not None:
            self._apply_numbering(para, p_elem, numbering)
        para.runs.extend(self._parse_runs(p_elem, structure_depth))
        for run in para.runs:
            if run.provenance is None:
                run.provenance = para.provenance
        return para

    def _read_notes(self, package: OOXMLPackage, path: str, note_type: str) -> Dict[str, Footnote]:
        if not package.exists(path):
            return {}
        root = package.read_xml_part(path)
        self._register_tree(root)
        notes = {}
        for note_elem in root.findall(f"w:{note_type}", namespaces=NS):
            note_id = _w_attr(note_elem, "id")
            if not note_id or note_id.startswith("-"):
                continue
            if note_type == "comment":
                note = Comment(author=_w_attr(note_elem, "author"))
            else:
                note = Footnote(type=note_type)
            note_para_ids = []
            paragraph_index = 0
            for block in self._parse_note_blocks(note_elem, paragraph_index, path):
                if isinstance(block, Paragraph):
                    para_id = _w15_attr(getattr(block, "_source_element", None), "paraId")
                    if para_id:
                        note_para_ids.append(para_id)
                    if block.text.strip():
                        note.paragraphs.append(block)
                    paragraph_index += 1
                elif isinstance(block, Table) and block.rows:
                    note.paragraphs.append(block)
                elif isinstance(block, (Equation, Image)):
                    note.paragraphs.append(block)
            note.paragraph_ids = note_para_ids
            notes[note_id] = note
        if note_type == "comment":
            self._append_comment_replies(package, notes)
        return notes

    def _parse_note_blocks(
        self,
        container,
        paragraph_index: int,
        path: str,
        depth: int = 0,
    ) -> List[object]:
        if not self._structure_depth_allowed(depth):
            return []
        blocks = []
        paragraph_ref = [paragraph_index]
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(
                    child,
                    paragraph_ref[0],
                    path=path,
                    structure_depth=depth,
                )
                para._source_element = child
                blocks.extend(self._paragraph_flow(para))
                paragraph_ref[0] += 1
            elif child.tag == f"{{{W_NS}}}tbl":
                blocks.append(
                    self._parse_table(
                        child,
                        paragraph_ref[0],
                        structure_depth=depth,
                    )
                )
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
                f"{{{W_NS}}}moveTo",
            ):
                nested = self._parse_note_blocks(
                    child, paragraph_ref[0], path, depth + 1,
                )
                paragraph_ref[0] += sum(isinstance(item, Paragraph) for item in nested)
                blocks.extend(nested)
            elif child.tag == f"{{{W_NS}}}moveFrom":
                continue
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                nested = self._parse_note_blocks(
                    self._alternate_content_preferred_child(child),
                    paragraph_ref[0],
                    path,
                    depth + 1,
                )
                paragraph_ref[0] += sum(isinstance(item, Paragraph) for item in nested)
                blocks.extend(nested)
        return blocks

    def _append_comment_replies(self, package: OOXMLPackage, comments: Dict[str, Footnote]):
        if not package.exists("word/commentsExtended.xml"):
            return
        root = package.read_xml_part("word/commentsExtended.xml")
        paragraph_to_comment_id = {}
        for comment_id, comment in comments.items():
            for para_id in getattr(comment, "paragraph_ids", []):
                paragraph_to_comment_id[para_id] = comment_id

        for comment_ex in root.findall("w15:commentEx", namespaces=NS):
            para_id = _w15_attr(comment_ex, "paraId")
            parent_para_id = _w15_attr(comment_ex, "paraIdParent")
            if not para_id or not parent_para_id:
                continue
            child_id = paragraph_to_comment_id.get(para_id, "")
            parent_id = paragraph_to_comment_id.get(parent_para_id, "")
            if not child_id or not parent_id or child_id == parent_id:
                continue
            child = comments.get(child_id)
            parent = comments.get(parent_id)
            reply_text = (child.text or "").strip() if child else ""
            if not parent or not reply_text:
                continue
            author = getattr(child, "author", "")
            prefix = f"Reply from {author}: " if author else "Reply: "
            parent.paragraphs.append(Paragraph(runs=[TextRun(text=f"{prefix}{reply_text}")]))

    def _read_headers_footers(self, package: OOXMLPackage, document_root) -> Tuple[List[HeaderFooter], List[HeaderFooter]]:
        headers = []
        footers = []
        seen = set()
        for sect_pr in document_root.findall(".//w:sectPr", namespaces=NS):
            for ref_name, hf_type, target_list in (
                ("headerReference", "header", headers),
                ("footerReference", "footer", footers),
            ):
                for ref in sect_pr.findall(f"w:{ref_name}", namespaces=NS):
                    rel_id = _r_attr(ref, "id")
                    path = getattr(self, "_document_relationships", {}).get(rel_id, "")
                    key = (hf_type, path)
                    if not path or key in seen or not package.exists(path):
                        continue
                    seen.add(key)
                    target_list.append(self._read_header_footer(package, path, hf_type))
        return headers, footers

    def _read_header_footer(self, package: OOXMLPackage, path: str, hf_type: str) -> HeaderFooter:
        root = package.read_xml_part(path)
        self._register_tree(root)
        hf = HeaderFooter(type=hf_type)
        paragraph_index_ref = [0]
        previous_relationships = getattr(self, "_active_relationships", {})
        self._active_relationships = self._read_part_relationships(package, path)
        try:
            hf.paragraphs.extend(self._parse_header_footer_paragraphs(root, paragraph_index_ref, path))
        finally:
            self._active_relationships = previous_relationships
        return hf

    def _parse_header_footer_paragraphs(
        self,
        container,
        paragraph_index_ref: List[int],
        path: str,
        depth: int = 0,
    ) -> List[Paragraph]:
        if not self._structure_depth_allowed(depth):
            return []
        paragraphs = []
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(
                    child,
                    paragraph_index_ref[0],
                    path=path,
                    structure_depth=depth,
                )
                paragraph_index_ref[0] += 1
                paragraphs.extend(self._paragraph_flow(para))
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
                f"{{{W_NS}}}moveTo",
            ):
                paragraphs.extend(
                    self._parse_header_footer_paragraphs(
                        child, paragraph_index_ref, path, depth + 1,
                    )
                )
            elif child.tag == f"{{{W_NS}}}moveFrom":
                continue
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(child)
                paragraphs.extend(
                    self._parse_header_footer_paragraphs(
                        preferred, paragraph_index_ref, path, depth + 1,
                    )
                )
        return paragraphs

    def _read_numbering(self, package: OOXMLPackage) -> Dict[Tuple[str, str], _NumberingLevel]:
        if not package.exists("word/numbering.xml"):
            return {}
        root = package.read_xml_part("word/numbering.xml")
        abstract_levels: Dict[Tuple[str, str], _NumberingLevel] = {}
        for abstract in root.findall("w:abstractNum", namespaces=NS):
            abstract_id = _w_attr(abstract, "abstractNumId")
            for level in abstract.findall("w:lvl", namespaces=NS):
                ilvl = self._validated_numbering_level(
                    _w_attr(level, "ilvl") or "0",
                )
                if ilvl is None:
                    continue
                fmt = _w_attr(level.find("w:numFmt", namespaces=NS), "val") or "decimal"
                text = _w_attr(level.find("w:lvlText", namespaces=NS), "val") or "%1."
                if len(text) > MAX_NUMBERING_TEMPLATE_CHARS:
                    self._record_numbering_template_limit()
                    text = "%1."
                start_raw = _w_attr(level.find("w:start", namespaces=NS), "val") or "1"
                start = self._validated_numbering_value(
                    start_raw,
                    "start value",
                )
                abstract_levels[(abstract_id, ilvl)] = _NumberingLevel(fmt=fmt, text=text, start=start)

        levels: Dict[Tuple[str, str], _NumberingLevel] = {}
        for num in root.findall("w:num", namespaces=NS):
            num_id = _w_attr(num, "numId")
            abstract_id = _w_attr(num.find("w:abstractNumId", namespaces=NS), "val")
            for (candidate_id, ilvl), level in abstract_levels.items():
                if candidate_id == abstract_id:
                    levels[(num_id, ilvl)] = level
        return levels

    def _validated_numbering_level(self, raw_value: str) -> Optional[str]:
        value = str(raw_value).strip()
        digits = value.lstrip("0") or "0"
        limit = str(MAX_NUMBERING_LEVEL)
        if (
            not value
            or not value.isascii()
            or not value.isdigit()
            or len(digits) > len(limit)
            or (len(digits) == len(limit) and digits > limit)
        ):
            self._record_numbering_level_limit()
            return None
        return str(int(digits))

    def _validated_numbering_value(self, raw_value: str, context: str) -> int:
        value = str(raw_value).strip()
        digits = value.lstrip("0") or "0"
        limit = str(MAX_NUMBERING_VALUE)
        if (
            not value
            or not value.isascii()
            or not value.isdigit()
            or len(digits) > len(limit)
            or (len(digits) == len(limit) and digits > limit)
        ):
            self._record_numbering_limit(context)
            return 1
        return int(digits)

    def _record_numbering_limit(self, context: str) -> None:
        error = f"ERR: DOCX numbering value limit exceeded ({context})"
        errors = getattr(self, "_active_document_errors", None)
        if errors is not None and error not in errors:
            errors.append(error)

    def _record_numbering_level_limit(self) -> None:
        error = f"ERR: DOCX numbering level limit exceeded ({MAX_NUMBERING_LEVEL})"
        errors = getattr(self, "_active_document_errors", None)
        if errors is not None and error not in errors:
            errors.append(error)

    def _record_numbering_template_limit(self) -> None:
        error = (
            "ERR: DOCX numbering marker template limit exceeded "
            f"({MAX_NUMBERING_TEMPLATE_CHARS} characters)"
        )
        errors = getattr(self, "_active_document_errors", None)
        if errors is not None and error not in errors:
            errors.append(error)

    def _read_paragraph_styles(self, package: OOXMLPackage) -> Dict[str, str]:
        if not package.exists("word/styles.xml"):
            return {}
        root = package.read_xml_part("word/styles.xml")
        styles = {}
        self._caption_styles = set()
        for style in root.findall("w:style", namespaces=NS):
            if _w_attr(style, "type") != "paragraph":
                continue
            style_id = _w_attr(style, "styleId")
            if not style_id:
                continue
            name = _w_attr(style.find("w:name", namespaces=NS), "val")
            if name.casefold() == "caption":
                self._caption_styles.add(style_id)
            based_on = _w_attr(style.find("w:basedOn", namespaces=NS), "val")
            styles[style_id] = based_on
        return styles

    def _read_run_styles(self, package: OOXMLPackage) -> Dict[str, _RunStyle]:
        self._style_definitions = {}
        self._default_paragraph_style = ""
        self._default_run_style = _RunStyle()
        if not package.exists("word/styles.xml"):
            return {}
        root = package.read_xml_part("word/styles.xml")
        self._default_run_style = self._run_style_from_rpr(
            root.find("w:docDefaults/w:rPrDefault/w:rPr", namespaces=NS))
        styles = {}
        for style in root.findall("w:style", namespaces=NS):
            kind = _w_attr(style, "type")
            style_id = _w_attr(style, "styleId")
            if kind not in {"paragraph", "character"} or not style_id:
                continue
            r_pr = style.find("w:rPr", namespaces=NS)
            self._style_definitions[style_id] = (
                _w_attr(style.find("w:basedOn", namespaces=NS), "val"), r_pr)
            if kind == "paragraph" and _w_attr(style, "default") in {"1", "true", "on"}:
                self._default_paragraph_style = style_id
            if kind == "character":
                styles[style_id] = self._run_style_from_rpr(r_pr)
        return styles

    def _inherited_run_style(self, r_elem, r_pr):
        style = replace(getattr(self, "_default_run_style", _RunStyle()))
        paragraph = next((node for node in etree.ancestors(r_elem, self._parents)
                          if node.tag == f"{{{W_NS}}}p"), None)
        paragraph_style = ""
        if paragraph is not None:
            paragraph_style = _w_attr(paragraph.find("w:pPr/w:pStyle", namespaces=NS), "val")
        paragraph_style = paragraph_style or getattr(self, "_default_paragraph_style", "")
        character_style = _w_attr(r_pr.find("w:rStyle", namespaces=NS), "val") if r_pr is not None else ""
        definitions = getattr(self, "_style_definitions", {})
        for style_id in (paragraph_style, character_style):
            chain, visited = [], set()
            while style_id in definitions and style_id not in visited and len(chain) < MAX_STRUCTURE_DEPTH:
                visited.add(style_id)
                style_id, properties = definitions[style_id]
                if properties is not None:
                    chain.append(properties)
                else:
                    chain.append(None)
            if style_id in definitions:
                warning = "WARN: DOCX run style inheritance cycle or depth limit"
                if warning not in self._active_document_errors:
                    self._active_document_errors.append(warning)
            for properties in reversed(chain):
                if properties is None:
                    continue
                # ISO 29500 toggle properties invert at style levels, whereas
                # direct run properties below assign the final on/off value.
                for tag, attr in (("b", "bold"), ("i", "italic"), ("strike", "strikeout")):
                    if _w_on_off_enabled(properties.find("w:" + tag, namespaces=NS)):
                        setattr(style, attr, not getattr(style, attr))
                underline = properties.find("w:u", namespaces=NS)
                if underline is not None:
                    style.underline = _w_on_off_enabled(underline, false_values={"none"})
                align = properties.find("w:vertAlign", namespaces=NS)
                if align is not None:
                    value = _w_attr(align, "val")
                    style.superscript, style.subscript = value == "superscript", value == "subscript"
        return style

    def _run_style_from_rpr(self, r_pr) -> _RunStyle:
        style = _RunStyle()
        if r_pr is None:
            return style
        style.bold = _w_on_off_enabled(r_pr.find("w:b", namespaces=NS))
        style.italic = _w_on_off_enabled(r_pr.find("w:i", namespaces=NS))
        style.underline = _w_on_off_enabled(
            r_pr.find("w:u", namespaces=NS), false_values={"none"},
        )
        style.strikeout = _w_on_off_enabled(r_pr.find("w:strike", namespaces=NS))
        vert_align = r_pr.find("w:vertAlign", namespaces=NS)
        if vert_align is not None:
            value = _w_attr(vert_align, "val")
            style.superscript = value == "superscript"
            style.subscript = value == "subscript"
        return style

    def _read_document_relationships(self, package: OOXMLPackage) -> Dict[str, str]:
        rels_path = self._relationships_path(self._document_part)
        if not package.exists(rels_path):
            return {}
        root = package.read_xml_part(rels_path)
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            rel_type = rel.get("Type", "")
            target = rel.get("Target", "")
            if not rel_id or not target:
                continue
            if rel.get("TargetMode", "").lower() == "external":
                if rel_type.endswith("/hyperlink"):
                    relationships[rel_id] = target
                continue
            if rel_type.endswith("/header") or rel_type.endswith("/footer"):
                resolved = self._validated_internal_relationship_target(
                    posixpath.dirname(self._document_part), target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/image") or rel_type.endswith("/chart") or rel_type.endswith("/chartEx") or rel_type.endswith("/diagramData"):
                resolved = self._validated_internal_relationship_target(
                    posixpath.dirname(self._document_part), target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/aFChunk"):
                resolved = self._validated_internal_relationship_target(
                    posixpath.dirname(self._document_part), target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/hyperlink"):
                resolved = self._validated_internal_relationship_target(
                    posixpath.dirname(self._document_part), target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            if rel_type.endswith("/diagramData") and rel_id in relationships:
                self._smartart_targets.add(relationships[rel_id])
        return relationships

    def _smartart_warning(self, detail):
        warning = "WARN: DOCX SmartArt " + detail
        if warning not in self._active_document_errors:
            self._active_document_errors.append(warning)

    def _preload_smartart(self, package, relationships):
        for target in dict.fromkeys(relationships.values()):
            if target not in self._smartart_targets or target in self._smartart_parts:
                continue
            if len(self._smartart_parts) >= MAX_SMARTART_PARTS:
                self._smartart_warning("part count limit exceeded")
                break
            self._smartart_parts[target] = []
            try:
                size = package.part_size(target)
                if self._smartart_bytes + size > MAX_SMARTART_BYTES:
                    self._smartart_warning("byte limit exceeded")
                    break
                self._smartart_bytes += size
                root = package.read_xml_part(target)
                texts = []
                for container in root.iter(f"{{{DGM_NS}}}t"):
                    paragraphs = []
                    for para in container.findall("a:p", namespaces=NS):
                        text = "".join(node.text or "" for node in para.iter(f"{{{A_NS}}}t")).strip()
                        if text:
                            paragraphs.append(text)
                    if paragraphs:
                        texts.append("\n".join(paragraphs))
                self._smartart_parts[target] = texts
            except (OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
                self._smartart_warning("data could not be read: %s (%s)" %
                                       (_bounded_diagnostic_path(target), type(exc).__name__))

    def _smartart_blocks(self, node):
        target = getattr(self, "_active_relationships", {}).get(_r_attr(node, "dm"), "")
        texts = getattr(self, "_smartart_parts", {}).get(target, [])
        if not texts:
            self._smartart_warning("text unavailable: " + _bounded_diagnostic_path(target or "unresolved diagramData"))
            return []
        blocks = []
        for text in texts:
            if self._smartart_output_chars + len(text) > MAX_SMARTART_OUTPUT_CHARS:
                self._smartart_warning("output character limit exceeded")
                break
            self._smartart_output_chars += len(text)
            provenance = Provenance(source_format="docx", section=0, path=target)
            blocks.append(Paragraph(runs=[TextRun(text=text, provenance=provenance)], provenance=provenance))
        return blocks

    def _read_chart_parts(self, package):
        targets = [target for target in dict.fromkeys(self._document_relationships.values())
                   if target.startswith("word/charts/") and target.endswith(".xml")]
        if not targets:
            return {}
        from .charts import chart_elements, hydrate_chart_references, normalize_chart
        from .xlsx import XLSXReader
        result = {}
        total = 0
        reader = XLSXReader()
        reader._errors = self._active_document_errors
        for target in targets:
            if len(result) >= MAX_DOCUMENT_CHARTS:
                self._active_document_errors.append("WARN: DOCX chart count limit exceeded")
                break
            try:
                size = package.part_size(target)
                if total + size > MAX_CHART_BYTES_TOTAL:
                    self._active_document_errors.append("WARN: DOCX chart byte limit exceeded")
                    break
                total += size
                root = normalize_chart(package.read_xml_part(target), self._active_document_errors)
                hydrate_chart_references(root, package, target, self._active_document_errors)
                table = reader._chart_series_table(root)
                def paragraph(text):
                    return Paragraph(runs=[TextRun(text=text)], provenance=Provenance(
                        source_format="docx", section=0, path=target))
                result[target] = chart_elements(root, table, paragraph)
            except (OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
                self._active_document_errors.append("WARN: DOCX chart skipped: %s: %s" % (target, exc))
                result[target] = []
        return result

    def _chart_warning(self, warning):
        if warning not in self._active_document_errors:
            self._active_document_errors.append(warning)

    def _chart_blocks_in(self, elem):
        blocks = []
        stack = [elem]
        while stack:
            node = stack.pop()
            if node.tag == "{%s}AlternateContent" % MC_NS:
                preferred = self._alternate_content_preferred_child(node)
                if preferred is not node:
                    stack.append(preferred)
                    continue
            if (isinstance(node.tag, str) and etree.QName(node).localname == "chart" and
                    etree.QName(node).namespace in {
                        "http://schemas.openxmlformats.org/drawingml/2006/chart",
                        "http://schemas.microsoft.com/office/drawing/2014/chartex"}):
                target = getattr(self, "_active_relationships", {}).get(_r_attr(node, "id"), "")
                template = getattr(self, "_chart_parts", {}).get(target, [])
                if not template:
                    continue
                if self._chart_occurrences >= MAX_DOCUMENT_CHARTS:
                    self._chart_warning("WARN: DOCX chart count limit exceeded")
                    continue
                if target not in self._chart_cell_counts:
                    self._chart_cell_counts[target] = sum(
                        len(row) for block in template if isinstance(block, Table)
                        for row in block.rows)
                cells = self._chart_cell_counts[target]
                if cells > self._chart_output_remaining:
                    self._chart_warning("WARN: DOCX chart output cell budget exceeded")
                    continue
                self._chart_occurrences += 1
                self._chart_output_remaining -= cells
                blocks.extend(self._clone_chart_block(block) for block in template)
            else:
                stack.extend(reversed(list(node)))
        return blocks

    def _clone_chart_block(self, block):
        """정규화된 차트 모델만 경량 복제한다. 문자열은 불변 값으로 공유한다.

        deepcopy의 범용 객체 그래프·memo 비용을 피하면서도 셀/런/캡션을
        개별 수정하거나 find_all로 순회하는 기존 모델 계약을 유지한다.
        """
        if isinstance(block, Table):
            return replace(block, rows=[[
                replace(cell, paragraphs=[self._clone_chart_block(p) for p in cell.paragraphs],
                        provenance=replace(cell.provenance) if cell.provenance else None)
                for cell in row] for row in block.rows],
                caption=[self._clone_chart_block(p) for p in block.caption])
        return replace(block, runs=[
            replace(run, provenance=replace(run.provenance) if run.provenance else None)
            for run in block.runs],
            provenance=replace(block.provenance) if block.provenance else None)

    def _read_part_relationships(self, package: OOXMLPackage, part_path: str) -> Dict[str, str]:
        rels_path = self._relationships_path(part_path)
        if not package.exists(rels_path):
            return {}
        root = package.read_xml_part(rels_path)
        relationships = {}
        part_dir = posixpath.dirname(part_path)
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            rel_type = rel.get("Type", "")
            target = rel.get("Target", "")
            if not rel_id or not target:
                continue
            if rel.get("TargetMode", "").lower() == "external":
                if rel_type.endswith("/hyperlink"):
                    relationships[rel_id] = target
                continue
            if rel_type.endswith("/image") or rel_type.endswith("/diagramData"):
                resolved = self._validated_internal_relationship_target(
                    part_dir, target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/aFChunk"):
                resolved = self._validated_internal_relationship_target(
                    part_dir, target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/hyperlink"):
                resolved = self._validated_internal_relationship_target(
                    part_dir, target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            if rel_type.endswith("/diagramData") and rel_id in relationships:
                self._smartart_targets.add(relationships[rel_id])
        self._preload_smartart(package, relationships)
        return relationships

    def _validated_internal_relationship_target(
        self,
        base_dir: str,
        target: str,
        rels_path: str,
        rel_id: str,
    ) -> str:
        try:
            return _resolve_internal_target(base_dir, target)
        except ValueError:
            error = (
                "ERR: DOCX unsafe internal relationship target skipped: "
                f"{rels_path}#{rel_id}"
            )
            errors = getattr(self, "_active_document_errors", None)
            if errors is not None and error not in errors:
                errors.append(error)
            return ""

    def _parse_alt_chunk(self, alt_chunk_elem, paragraph_index: int) -> List[Paragraph]:
        rel_id = _r_attr(alt_chunk_elem, "id")
        target = getattr(self, "_active_relationships", {}).get(rel_id, "")
        if not target:
            target = getattr(self, "_document_relationships", {}).get(rel_id, "")
        data = getattr(self, "_alt_chunk_data", {}).get(target)
        if not target or data is None:
            return []
        blocks = self._alt_chunk_blocks(target, data)
        paragraphs = []
        for offset, text in enumerate(blocks):
            if not text.strip():
                continue
            provenance = Provenance(
                source_format="docx",
                section=0,
                paragraph=paragraph_index + offset,
                path=target,
            )
            paragraphs.append(Paragraph(runs=[TextRun(text=text)], provenance=provenance))
        return paragraphs

    def _read_alt_chunk_data(self, package: OOXMLPackage, relationships: Dict[str, str]) -> Dict[str, bytes]:
        data = {}
        for target in relationships.values():
            extension = posixpath.splitext(target.lower())[1]
            if extension not in {".html", ".htm", ".mht", ".mhtml"}:
                continue
            if package.exists(target):
                data[target] = package.read_part(target)
        return data

    def _alt_chunk_blocks(self, target: str, data: bytes) -> List[str]:
        extension = posixpath.splitext(target.lower())[1]
        if extension in {".mht", ".mhtml"}:
            html = self._html_from_mhtml(data)
        else:
            html = self._decode_html_bytes(data)
        return self._html_blocks(html)

    def _html_from_mhtml(self, data: bytes) -> str:
        message = BytesParser(policy=policy.default).parsebytes(data)
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                if content_type == "text/html":
                    return part.get_content()
        if message.get_content_type() == "text/html":
            return message.get_content()
        return self._decode_html_bytes(data)

    def _decode_html_bytes(self, data: bytes) -> str:
        for encoding in ("utf-8", "windows-1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _html_blocks(self, html: str) -> List[str]:
        parser = _HTMLAltChunkTextParser()
        parser.feed(html)
        parser.close()
        return parser.blocks

    def _relationships_path(self, part_path: str) -> str:
        part_dir = posixpath.dirname(part_path)
        name = posixpath.basename(part_path)
        return posixpath.join(part_dir, "_rels", f"{name}.rels")

    def _record_embedded_relationship_assets(self, package: OOXMLPackage):
        rels_path = self._relationships_path(self._document_part)
        if not package.exists(rels_path):
            return
        root = package.read_xml_part(rels_path)
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_type = rel.get("Type", "")
            if not (rel_type.endswith("/oleObject") or rel_type.endswith("/package")):
                continue
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if (
                not rel_id
                or not target
                or rel.get("TargetMode", "").lower() == "external"
            ):
                continue
            source_path = self._validated_internal_relationship_target(
                posixpath.dirname(self._document_part), target, rels_path, rel_id,
            )
            if source_path:
                self._record_embedded_asset(rel_id, source_path, rel_type)

    def _apply_numbering(self, para: Paragraph, p_elem, numbering: Dict[Tuple[str, str], _NumberingLevel]):
        num_pr = p_elem.find("w:pPr/w:numPr", namespaces=NS)
        if num_pr is None:
            return
        num_id = _w_attr(num_pr.find("w:numId", namespaces=NS), "val")
        # numId=0 cancels numbering; absent definitions do not consume levels.
        if not num_id or num_id == "0":
            return
        raw_level = _w_attr(num_pr.find("w:ilvl", namespaces=NS), "val") or "0"
        level_key = raw_level.strip().lstrip("0") or "0"
        level = numbering.get((num_id, level_key))
        if level is None:
            return
        ilvl = self._validated_numbering_level(raw_level)
        if ilvl is None:
            return
        count = getattr(self, "_numbering_counts", {}).get((num_id, ilvl))
        if count is None:
            count = level.start
        if not 0 <= count <= MAX_NUMBERING_VALUE:
            self._record_numbering_limit("list counter")
            return
        self._numbering_counts[(num_id, ilvl)] = min(
            count + 1,
            MAX_NUMBERING_VALUE + 1,
        )
        self._reset_deeper_numbering_counts(num_id, ilvl)
        prefix = self._numbering_prefix(level, count, num_id, ilvl, numbering)
        if prefix:
            para.runs.insert(0, TextRun(text=f"{prefix} "))

    def _reset_deeper_numbering_counts(self, num_id: str, ilvl: str):
        try:
            current_level = int(ilvl)
        except ValueError:
            return
        for key_num_id, key_ilvl in list(self._numbering_counts):
            if key_num_id != num_id:
                continue
            try:
                key_level = int(key_ilvl)
            except ValueError:
                continue
            if key_level > current_level:
                del self._numbering_counts[(key_num_id, key_ilvl)]

    def _numbering_prefix(
        self,
        level: _NumberingLevel,
        count: int,
        num_id: str = "",
        ilvl: str = "0",
        numbering: Dict[Tuple[str, str], _NumberingLevel] = None,
    ) -> str:
        if level.fmt == "bullet":
            return "•"
        markers = self._numbering_markers(level, count, num_id, ilvl, numbering or {})
        prefix = level.text
        for index, marker in markers.items():
            prefix = prefix.replace(f"%{index}", marker)
        return prefix

    def _numbering_markers(
        self,
        level: _NumberingLevel,
        count: int,
        num_id: str,
        ilvl: str,
        numbering: Dict[Tuple[str, str], _NumberingLevel],
    ) -> Dict[int, str]:
        try:
            current_level = int(ilvl)
        except ValueError:
            current_level = 0
        markers = {}
        for level_index in range(current_level + 1):
            level_key = str(level_index)
            marker_level = level if level_key == ilvl else numbering.get((num_id, level_key))
            if marker_level is None:
                continue
            marker_count = count if level_key == ilvl else self._current_numbering_count(num_id, level_key, marker_level)
            markers[level_index + 1] = self._numbering_marker(marker_level.fmt, marker_count)
        return markers

    def _current_numbering_count(self, num_id: str, ilvl: str, level: _NumberingLevel) -> int:
        next_count = self._numbering_counts.get((num_id, ilvl))
        if next_count is None:
            return level.start
        return max(level.start, next_count - 1)

    def _numbering_marker(self, fmt: str, count: int) -> str:
        if not 0 <= count <= MAX_NUMBERING_VALUE:
            self._record_numbering_limit("generated marker")
            return ""
        if fmt == "decimalZero":
            return str(count).zfill(2)
        if count == 0:
            return "0"
        if fmt == "lowerLetter":
            return self._letter_marker(count)
        if fmt == "upperLetter":
            return self._letter_marker(count).upper()
        if fmt == "lowerRoman":
            return self._roman_marker(count).lower()
        if fmt == "upperRoman":
            return self._roman_marker(count)
        return str(count)

    def _letter_marker(self, count: int) -> str:
        count = max(count, 1)
        marker = ""
        value = count
        while value:
            value, remainder = divmod(value - 1, 26)
            marker = chr(ord("a") + remainder) + marker
        return marker

    def _roman_marker(self, count: int) -> str:
        count = max(count, 1)
        numerals = (
            (1000, "M"),
            (900, "CM"),
            (500, "D"),
            (400, "CD"),
            (100, "C"),
            (90, "XC"),
            (50, "L"),
            (40, "XL"),
            (10, "X"),
            (9, "IX"),
            (5, "V"),
            (4, "IV"),
            (1, "I"),
        )
        result = []
        value = count
        for number, marker in numerals:
            repetitions, value = divmod(value, number)
            if repetitions:
                result.append(marker * repetitions)
        return "".join(result)

    def _heading_level(self, p_elem) -> int:
        p_style = p_elem.find("w:pPr/w:pStyle", namespaces=NS)
        style = _w_attr(p_style, "val")
        return self._style_heading_level(style)

    def _style_heading_level(self, style: str) -> int:
        visited = set()
        while style and style not in visited:
            visited.add(style)
            level = self._heading_level_from_style_id(style)
            if level:
                return level
            style = getattr(self, "_paragraph_styles", {}).get(style, "")
        return 0

    def _heading_level_from_style_id(self, style: str) -> int:
        lower = style.lower()
        if lower == "title":
            return 1
        if lower.startswith("heading"):
            suffix = lower.replace("heading", "", 1)
            if suffix.isdigit():
                return max(1, min(int(suffix), 6))
            return 1
        return 0

    def _parse_runs(self, p_elem, depth: int = 0) -> List[TextRun]:
        if not self._structure_depth_allowed(depth):
            return []
        self._register_tree(p_elem)
        runs = []
        direct_equations = set()
        for child in p_elem:
            if child.tag == f"{{{W_NS}}}r":
                runs.extend(self._parse_run(child, depth))
            elif child.tag == f"{{{W_NS}}}hyperlink":
                hyperlink_runs = self._parse_runs(child, depth + 1)
                target = self._hyperlink_target(child)
                if target and hyperlink_runs:
                    if hyperlink_runs[-1].equation is not None:
                        marker = TextRun(text=f" <{target}>")
                        marker._equation_annotation = True
                        hyperlink_runs.append(marker)
                    else:
                        hyperlink_runs[-1].text = f"{hyperlink_runs[-1].text} <{target}>"
                runs.extend(hyperlink_runs)
            elif child.tag == f"{{{W_NS}}}bookmarkStart":
                bookmark_marker = self._bookmark_marker(child)
                if bookmark_marker:
                    marker = TextRun(text=bookmark_marker)
                    marker._bookmark_annotation = True
                    runs.append(marker)
            elif child.tag == f"{{{W_NS}}}commentRangeEnd":
                comment_id = _w_attr(child, "id")
                annotation = self._comment_annotation(comment_id)
                if annotation:
                    if runs and runs[-1].equation is not None:
                        marker = TextRun(text=f" {annotation}")
                        marker._equation_annotation = True
                        runs.append(marker)
                    elif runs:
                        runs[-1].text = f"{runs[-1].text} {annotation}"
                    else:
                        runs.append(TextRun(text=annotation))
            elif child.tag == f"{{{W_NS}}}commentRangeStart":
                continue
            elif child.tag == f"{{{W_NS}}}ins":
                runs.extend(self._parse_runs(child, depth + 1))
            elif child.tag == f"{{{W_NS}}}moveTo":
                runs.extend(self._parse_runs(child, depth + 1))
            elif child.tag == f"{{{W_NS}}}moveFrom":
                continue
            elif child.tag == f"{{{W_NS}}}del":
                continue
            elif child.tag == f"{{{M_NS}}}oMath":
                for equation in self._equations_in(child, include_self=True):
                    run = TextRun(text=equation.latex, equation=equation)
                    direct_equations.add(id(run))
                    runs.append(run)
            elif child.tag == f"{{{M_NS}}}oMathPara":
                run = TextRun()
                run._flow_elements = self._equations_in(child, include_self=True)
                runs.append(run)
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(child)
                if preferred is not child:
                    runs.extend(self._parse_runs(preferred, depth + 1))
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}fldSimple",
            ):
                runs.extend(self._parse_runs(child, depth + 1))
        # Place visible anchors at the containing paragraph's front so an
        # anchor inside a word (also inside w:ins/sdt) preserves that word.
        # Resolve textbox spacing only after the text neighbours are final.
        bookmarks = [run for run in runs if getattr(run, '_bookmark_annotation', False)]
        runs = [run for run in runs if not getattr(run, '_bookmark_annotation', False)]
        if direct_equations:
            next_text = [None] * len(runs)
            source = None
            for index in range(len(runs) - 1, -1, -1):
                next_text[index] = source
                run = runs[index]
                if run.equation is None and run.text.strip() and not run.note_ref \
                        and not run.note_reference_type \
                        and not getattr(run, '_equation_annotation', False):
                    source = run
            previous = None
            for index, run in enumerate(runs):
                if id(run) in direct_equations:
                    source = previous or next_text[index]
                    if source is not None:
                        for field in ('bold', 'italic', 'underline', 'strikeout',
                                      'superscript', 'subscript', 'font_size_pt'):
                            setattr(run, field, getattr(source, field))
                elif run.equation is None and run.text.strip() and not run.note_ref \
                        and not run.note_reference_type \
                        and not getattr(run, '_equation_annotation', False):
                    previous = run
        for previous, current in zip(runs, runs[1:]):
            if (previous.text and current.text and
                    (getattr(previous, "_textbox_end", False) or
                     getattr(current, "_textbox_start", False)) and
                    not previous.text[-1].isspace() and not current.text[0].isspace()):
                current.text = " " + current.text
        return bookmarks + runs

    def _run_comment_reference_ids(self, r_elem) -> set:
        return {
            _w_attr(reference, "id")
            for reference in r_elem.findall("w:commentReference", namespaces=NS)
            if _w_attr(reference, "id")
        }

    def _hyperlink_target(self, hyperlink_elem) -> str:
        rel_id = _r_attr(hyperlink_elem, "id")
        target = getattr(self, "_active_relationships", {}).get(rel_id, "")
        if not target:
            target = getattr(self, "_document_relationships", {}).get(rel_id, "")
        if target:
            return target
        anchor = _w_attr(hyperlink_elem, "anchor")
        return f"#{anchor}" if anchor else ""

    def _bookmark_marker(self, bookmark_elem) -> str:
        name = _w_attr(bookmark_elem, "name")
        if not name or name.startswith("_"):
            return ""
        return f"[bookmark: {name}] "

    def _parse_run(self, r_elem, depth: int = 0) -> List[TextRun]:
        segments = []
        text_parts = []

        def flush_text():
            text = ""
            boundary = False
            for piece in text_parts:
                if piece is None:
                    boundary = True
                    continue
                if boundary and text and piece and not text[-1].isspace() and not piece[0].isspace():
                    text += " "
                text += piece
                if piece:
                    boundary = False
            if text:
                edges = (text_parts[0] is None, text_parts[-1] is None)
                segments.append((text, "textbox_text", edges))
            text_parts.clear()

        for child in r_elem:
            if child.tag == f"{{{W_NS}}}t":
                text_parts.append(child.text or "")
            elif child.tag in (f"{{{W_NS}}}tab", f"{{{W_NS}}}ptab"):
                text_parts.append("\t")
            elif child.tag in (f"{{{W_NS}}}br", f"{{{W_NS}}}cr"):
                text_parts.append("\n")
            elif child.tag == f"{{{W_NS}}}fldChar":
                checkbox_marker = self._form_checkbox_marker(child)
                if checkbox_marker:
                    text_parts.append(checkbox_marker)
            elif child.tag == f"{{{W_NS}}}footnoteReference":
                number = self._register_note_reference(
                    "footnote", _w_attr(child, "id"),
                )
                if number is not None:
                    flush_text()
                    segments.append((f"[{number}]", "footnote", number))
            elif child.tag == f"{{{W_NS}}}endnoteReference":
                number = self._register_note_reference(
                    "endnote", _w_attr(child, "id"),
                )
                if number is not None:
                    flush_text()
                    segments.append((f"[{number}]", "endnote", number))
            elif child.tag == f"{{{W_NS}}}commentReference":
                if _w_attr(child, "id") in getattr(self, "_annotated_comments", set()):
                    continue
                number = self._register_comment_reference(_w_attr(child, "id"))
                if number is not None:
                    flush_text()
                    segments.append((f"[comment {number}]", "comment", number))
            else:
                for drawing_run in self._drawing_runs(child, depth + 1):
                    flow = getattr(drawing_run, "_flow_elements", None)
                    if getattr(drawing_run, "_text_boundary", False):
                        text_parts.append(None)
                    elif drawing_run.equation is not None:
                        flush_text()
                        segments.append((drawing_run.text, "equation", drawing_run.equation))
                    elif flow is not None:
                        flush_text()
                        segments.append(("", "flow", flow))
                    elif drawing_run.text:
                        text_parts.append(drawing_run.text)

        flush_text()
        if not segments:
            return []

        r_pr = r_elem.find("w:rPr", namespaces=NS)
        runs = []
        for text, note_type, note_number in segments:
            if note_type == "flow":
                run = TextRun(text="")
                run._flow_elements = note_number
                runs.append(run)
                continue
            equation = note_number if note_type == "equation" else None
            if equation is not None:
                note_type, note_number = "", None
            textbox_edges = note_number if note_type == "textbox_text" else (False, False)
            if note_type == "textbox_text":
                note_type, note_number = "", None
            run = TextRun(
                text=text,
                note_reference_type=note_type,
                note_reference_number=note_number,
                equation=equation,
            )
            run._textbox_start, run._textbox_end = textbox_edges
            # Markdown 렌더러는 note_ref 로 각주 참조를 그린다. 두 표현을 함께 채워
            # 의미 필드(note_reference_*)와 렌더 필드가 어긋나지 않게 한다.
            if note_number is not None and note_type in ('footnote', 'endnote'):
                run.note_ref = note_number
            self._apply_run_style(run, self._inherited_run_style(r_elem, r_pr))
            if r_pr is not None:
                bold = r_pr.find("w:b", namespaces=NS)
                italic = r_pr.find("w:i", namespaces=NS)
                underline = r_pr.find("w:u", namespaces=NS)
                strikeout = r_pr.find("w:strike", namespaces=NS)
                if bold is not None:
                    run.bold = _w_on_off_enabled(bold)
                if italic is not None:
                    run.italic = _w_on_off_enabled(italic)
                if underline is not None:
                    run.underline = _w_on_off_enabled(
                        underline, false_values={"none"},
                    )
                if strikeout is not None:
                    run.strikeout = _w_on_off_enabled(strikeout)
                size = r_pr.find("w:sz", namespaces=NS)
                if size is not None:
                    try:
                        points = int(_w_attr(size, "val")) / 2
                        if 0 < points <= 1000:
                            run.font_size_pt = points
                    except (ValueError, TypeError):
                        pass
                vert_align = r_pr.find("w:vertAlign", namespaces=NS)
                if vert_align is not None:
                    value = _w_attr(vert_align, "val")
                    run.superscript = value == "superscript"
                    run.subscript = value == "subscript"
            runs.append(run)
        return runs

    def _drawing_runs(self, elem, depth):
        """그룹 도형의 텍스트·차트·이미지를 선택된 XML 갈래에서 한 번 읽는다."""
        stack = [elem]
        anchored = elem.find(".//wp:anchor", namespaces=NS) is not None
        while stack:
            node = stack.pop()
            if node.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(node)
                if preferred is not node:
                    stack.append(preferred)
                    continue
            if (node.tag == f"{{{A_NS}}}graphicData" and node.get("uri") == DGM_NS
                    and node.find("dgm:relIds", namespaces=NS) is None):
                self._smartart_warning("diagramData relationship missing")
            if node.tag == f"{{{DGM_NS}}}relIds":
                run = TextRun()
                run._flow_elements = self._smartart_blocks(node)
                yield run
                continue
            if node.tag == f"{{{W_NS}}}txbxContent":
                paragraphs = []
                for p_elem, paragraph_depth in self._textbox_paragraphs(node, depth, include_tables=True):
                    if p_elem.tag == f"{{{W_NS}}}tbl":
                        run = TextRun()
                        run._flow_elements = [self._parse_table(p_elem, 0, structure_depth=paragraph_depth)]
                        paragraphs.append([run])
                        continue
                    para = Paragraph()
                    self._apply_numbering(para, p_elem, getattr(self, "_numbering", {}))
                    para.runs.extend(self._parse_runs(p_elem, paragraph_depth))
                    runs = para.runs
                    if runs:
                        paragraphs.append(runs)
                if paragraphs:
                    boundary = TextRun()
                    boundary._text_boundary = True
                    yield boundary
                for index, runs in enumerate(paragraphs):
                    # 기존 텍스트박스의 문단 줄바꿈 및 호스트 런 서식을 유지한다.
                    has_text = any(item.text.strip() and item.equation is None for item in runs)
                    for run in runs:
                        if run.equation is not None and not has_text:
                            block = TextRun()
                            block._flow_elements = [run.equation]
                            yield block
                            continue
                        yield run
                    if index < len(paragraphs) - 1 or anchored:
                        yield TextRun(text="\n")
                if paragraphs:
                    yield boundary
                continue
            if node.tag in {f"{{{W_NS}}}del", f"{{{W_NS}}}moveFrom"}:
                continue
            if node.tag == f"{{{M_NS}}}oMath":
                for equation in self._equations_in(node, include_self=True):
                    yield TextRun(text=equation.latex, equation=equation)
                continue
            if node.tag == f"{{{M_NS}}}oMathPara":
                run = TextRun()
                run._flow_elements = self._equations_in(node, include_self=True)
                yield run
                continue
            if isinstance(node.tag, str) and etree.QName(node).localname == "chart":
                blocks = self._chart_blocks_in(node)
                if blocks:
                    run = TextRun()
                    run._flow_elements = blocks
                    yield run
                continue
            if node.tag in {f"{{{A_NS}}}blip", f"{{{V_NS}}}imagedata"}:
                image_start = len(getattr(self, "_image_elements", []))
                reference = self._image_reference(node)
                if reference:
                    yield TextRun(text=reference)
                images = getattr(self, "_image_elements", [])[image_start:]
                if images:
                    run = TextRun()
                    run._flow_elements = images
                    yield run
                continue
            if node.tag == f"{{{WP_NS}}}docPr":
                # 이미지 설명은 _image_reference가 참조의 대체 텍스트로 낸다.
                # 이미지 없는 도형의 설명은 종전처럼 본문에 남긴다.
                parent = self._parents.get(node)
                blip = parent.find(".//a:blip", namespaces=NS) if parent is not None else None
                rel_id = _r_attr(blip, "embed")
                if rel_id and (getattr(self, "_active_relationships", {}).get(rel_id) or
                               getattr(self, "_document_relationships", {}).get(rel_id)):
                    continue
                alt = " ".join(part for part in (node.get("title", ""), node.get("descr", "")) if part)
                if alt:
                    yield TextRun(text=alt)
                continue
            stack.extend(reversed(list(node)))

    def _textbox_texts(self, elem, depth: int = 0) -> List[str]:
        search_root = self._alternate_content_preferred_child(elem)
        textboxes = self._outermost_textbox_contents(search_root)
        if not textboxes or not self._structure_depth_allowed(depth):
            return []
        texts = []
        anchored = search_root.find(".//wp:anchor", namespaces=NS) is not None
        for textbox in textboxes:
            paragraph_texts = []
            for p_elem, paragraph_depth in self._textbox_paragraphs(textbox, depth):
                text = "".join(
                    run.text for run in self._parse_runs(p_elem, paragraph_depth)
                ).strip()
                if text:
                    paragraph_texts.append(text)
            if paragraph_texts:
                text = "\n".join(paragraph_texts)
                texts.append(f"{text}\n" if anchored else text)
        return texts

    def _textbox_paragraphs(self, container, depth, include_tables=False):
        if not self._structure_depth_allowed(depth):
            return
        wrappers = {f"{{{W_NS}}}{name}" for name in
                    ("sdt", "sdtContent", "smartTag", "ins", "moveTo", "tbl", "tr", "tc")}
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                yield child, depth
            elif include_tables and child.tag == f"{{{W_NS}}}tbl":
                yield child, depth
            elif child.tag in wrappers:
                yield from self._textbox_paragraphs(child, depth + 1, include_tables)
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                yield from self._textbox_paragraphs(
                    self._alternate_content_preferred_child(child), depth + 1, include_tables)

    def _outermost_textbox_contents(self, elem) -> List[object]:
        textboxes = []
        stack = [elem]
        while stack:
            current = stack.pop()
            if current.tag == f"{{{W_NS}}}txbxContent":
                textboxes.append(current)
                continue
            if current.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(current)
                if preferred is not current:
                    stack.append(preferred)
                    continue
            stack.extend(reversed(list(current)))
        return textboxes

    def _alternate_content_preferred_child(self, elem):
        if elem.tag != f"{{{MC_NS}}}AlternateContent":
            return elem
        choice = elem.find("mc:Choice", namespaces=NS)
        if choice is not None:
            return choice
        fallback = elem.find("mc:Fallback", namespaces=NS)
        return fallback if fallback is not None else elem

    def _form_checkbox_marker(self, fld_char) -> str:
        check_box = fld_char.find("w:ffData/w:checkBox", namespaces=NS)
        if check_box is None:
            return ""
        checked = check_box.find("w:checked", namespaces=NS)
        default = check_box.find("w:default", namespaces=NS)
        value = _w_attr(checked, "val") if checked is not None else _w_attr(default, "val")
        if checked is not None and value == "":
            value = "1"
        return "[x]" if str(value).lower() in {"1", "true", "on", "yes"} else "[ ]"

    def _referenced_run_style(self, r_pr) -> _RunStyle:
        style_id = _w_attr(r_pr.find("w:rStyle", namespaces=NS), "val")
        return getattr(self, "_run_styles", {}).get(style_id, _RunStyle())

    def _equations_in(self, elem, include_self: bool = False) -> List[Equation]:
        """활성 수식 갈래만 제한된 깊이로 읽는다. 문단 뒤 재검색하지 않는다."""
        omaths = []
        stack = [(elem, 0)] if include_self else [(c, 0) for c in reversed(list(elem))]
        while stack:
            node, depth = stack.pop()
            if not self._structure_depth_allowed(depth):
                continue
            if node.tag in {f"{{{W_NS}}}del", f"{{{W_NS}}}moveFrom"}:
                continue
            if node.tag == f"{{{M_NS}}}oMath":
                omaths.append(node)
            elif node.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(node)
                if preferred is not node:
                    stack.append((preferred, depth + 1))
            else:
                stack.extend((c, depth + 1) for c in reversed(list(node)))
        equations = []
        for omath in omaths:
            latex = _omml_to_latex(omath).strip()
            if latex:
                equations.append(Equation(latex_override=latex))
        return equations

    def _apply_run_style(self, run: TextRun, style: _RunStyle):
        run.bold = run.bold or style.bold
        run.italic = run.italic or style.italic
        run.underline = run.underline or style.underline
        run.strikeout = run.strikeout or style.strikeout
        run.superscript = run.superscript or style.superscript
        run.subscript = run.subscript or style.subscript

    def _image_reference(self, elem) -> str:
        image_elem = elem if elem.tag in {f"{{{A_NS}}}blip", f"{{{V_NS}}}imagedata"} else elem.find(".//a:blip", namespaces=NS)
        if image_elem is None:
            image_elem = elem.find(".//v:imagedata", namespaces=NS)
        if image_elem is None:
            return ""
        rel_id = _r_attr(image_elem, "embed") or _r_attr(image_elem, "id")
        target = getattr(self, "_active_relationships", {}).get(rel_id, "")
        if not target:
            target = getattr(self, "_document_relationships", {}).get(rel_id, "")
        if not target:
            return ""
        context = elem
        doc_pr = context.find(".//wp:docPr", namespaces=NS)
        while doc_pr is None and self._parents.get(context) is not None:
            context = self._parents[context]
            doc_pr = context.find("wp:docPr", namespaces=NS)
            if context.tag in {f"{{{W_NS}}}drawing", f"{{{W_NS}}}pict", f"{{{W_NS}}}txbxContent"}:
                break
        label = self._doc_pr_label(doc_pr)
        image_start = len(getattr(self, "_image_elements", []))
        self._record_image_asset(rel_id, target, label)
        if len(getattr(self, "_image_elements", [])) == image_start:
            self._extract_image_element(getattr(self, "_package", None), target, label)
        return f"![{label or 'image'}]({target})"

    def _doc_pr_label(self, doc_pr) -> str:
        if doc_pr is None:
            return ""
        return " ".join(
            part
            for part in (
                doc_pr.get("title", ""),
                doc_pr.get("descr", ""),
                doc_pr.get("name", ""),
            )
            if part
        )

    def _record_image_asset(self, rel_id: str, target: str, label: str):
        if not rel_id or not target:
            return
        key = ("image", target)
        if key in getattr(self, "_image_asset_ids", set()):
            return
        if getattr(self, "_image_asset_count", 0) >= MAX_IMAGE_ASSET_REFS:
            if not getattr(self, "_image_asset_limit_reported", False):
                self._active_document_errors.append(
                    "WARN: DOCX image asset reference limit exceeded "
                    f"({MAX_IMAGE_ASSET_REFS})"
                )
                self._image_asset_limit_reported = True
            return
        package = getattr(self, "_package", None)
        missing = package is not None and not package.exists(target)
        self._image_asset_ids.add(key)
        self._image_asset_count = getattr(self, "_image_asset_count", 0) + 1
        assets = getattr(self, "_assets", None)
        if assets is None:
            assets = []
            self._assets = assets
        assets.append(
            AssetRef(
                id=rel_id,
                source_path=target,
                filename=posixpath.basename(target),
                content_type=self._image_content_type(target),
                metadata={
                    "kind": "image",
                    "label": label,
                    "missing": missing,
                    "source_format": "docx",
                },
            )
        )
        if missing:
            warning = (
                "WARN: DOCX image part not found: "
                f"{_bounded_diagnostic_path(target)}"
            )
            if warning not in self._active_document_errors:
                self._active_document_errors.append(warning)
        else:
            self._extract_image_element(package, target, label)

    def _preload_image_bytes(self, package) -> dict:
        """패키지가 열려 있는 동안 이미지 파트 바이트를 미리 읽어 둔다.

        문단 파싱은 with 블록 밖(zip 닫힌 뒤)에서 일어나므로 여기서
        캐시하지 않으면 read_part 가 실패한다. 총량 상한으로 메모리 방어.
        """
        cache = {}
        rels_path = self._relationships_path(self._document_part)
        if not package.exists(rels_path):
            return cache
        try:
            root = package.read_xml_part(rels_path)
        except Exception:
            return cache
        total = 0
        for rel in root.findall("rel:Relationship", namespaces=NS):
            if not rel.get("Type", "").endswith("/image"):
                continue
            try:
                # 제어문자·외부 스킴이 섞인 조작된 대상은 여기서 걸러진다.
                target = _resolve_internal_target(
                    posixpath.dirname(self._document_part), rel.get("Target", ""))
            except ValueError:
                continue
            if not target or target in cache or total >= _MAX_IMAGE_BYTES_TOTAL:
                continue
            try:
                data = package.read_part(target)
            except Exception:
                continue
            if data:
                cache[target] = data
                total += len(data)
        return cache

    def _extract_image_element(self, package, target: str, label: str):
        """미리 캐시한 이미지 바이트로 Image 요소를 만든다 (OCR·자산 추출용)."""
        data = getattr(self, "_image_data_cache", {}).get(target)
        if not data:
            return
        if getattr(self, "_image_occurrences", 0) >= MAX_IMAGE_ASSET_REFS:
            warning = "WARN: DOCX image occurrence limit exceeded (%s)" % MAX_IMAGE_ASSET_REFS
            if warning not in self._active_document_errors:
                self._active_document_errors.append(warning)
            return
        self._image_occurrences = getattr(self, "_image_occurrences", 0) + 1
        ext = posixpath.splitext(target)[1].lstrip(".").lower()
        self._image_elements.append(
            Image(
                filename=posixpath.basename(target),
                image_data=data,
                alt_text=label,
                image_format=ext,
                provenance=Provenance(source_format="docx", path=target),
                inline_reference=True,
            )
        )

    def _record_embedded_asset(self, rel_id: str, target: str, rel_type: str):
        if not rel_id or not target:
            return
        key = ("embedded", rel_id)
        if key in getattr(self, "_image_asset_ids", set()):
            return
        package = getattr(self, "_package", None)
        if package is not None and not package.exists(target):
            return
        self._image_asset_ids.add(key)
        assets = getattr(self, "_assets", None)
        if assets is None:
            assets = []
            self._assets = assets
        assets.append(
            AssetRef(
                id=rel_id,
                source_path=target,
                filename=posixpath.basename(target),
                content_type=self._embedded_content_type(target, rel_type),
                metadata={
                    "kind": "embedded",
                    "relationship_type": rel_type.rsplit("/", 1)[-1],
                    "source_format": "docx",
                },
            )
        )

    def _image_content_type(self, target: str) -> str:
        extension = posixpath.splitext(target.lower())[1]
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".emf": "image/x-emf",
            ".wmf": "image/x-wmf",
        }.get(extension, "application/octet-stream")

    def _embedded_content_type(self, target: str, rel_type: str) -> str:
        if rel_type.endswith("/oleObject"):
            return "application/vnd.ms-office.oleObject"
        extension = posixpath.splitext(target.lower())[1]
        return {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".doc": "application/msword",
            ".ppt": "application/vnd.ms-powerpoint",
            ".xls": "application/vnd.ms-excel",
        }.get(extension, "application/octet-stream")

    def _register_note_reference(
        self, note_type: str, note_id: str,
    ) -> Optional[int]:
        if not note_id or note_id not in getattr(self, "_notes", {}).get(note_type, {}):
            return None
        key = (note_type, note_id)
        if key not in self._note_reference_numbers:
            self._note_reference_numbers[key] = len(self._note_reference_numbers) + 1
            self._note_reference_order.append(key)
        number = self._note_reference_numbers[key]
        self._notes[note_type][note_id].number = number
        return number

    def _register_comment_reference(self, comment_id: str) -> Optional[int]:
        if not comment_id or comment_id not in getattr(self, "_comments", {}):
            return None
        if comment_id not in self._comment_reference_numbers:
            self._comment_reference_numbers[comment_id] = len(self._comment_reference_numbers) + 1
            self._comment_reference_order.append(comment_id)
        number = self._comment_reference_numbers[comment_id]
        self._comments[comment_id].number = number
        return number

    def _comment_marker(self, comment_id: str) -> str:
        number = self._register_comment_reference(comment_id)
        return f"[comment {number}]" if number is not None else ""

    def _comment_annotation(self, comment_id: str) -> str:
        marker = self._comment_marker(comment_id)
        if not marker:
            return ""
        self._annotated_comments.add(comment_id)
        comment = getattr(self, "_comments", {}).get(comment_id)
        comment_text = self._comment_primary_text(comment)
        if not comment_text:
            return marker
        return f"{marker[:-1]}: {comment_text}]"

    def _comment_primary_text(self, comment: Comment) -> str:
        if not comment:
            return ""
        for paragraph in comment.paragraphs:
            text = (getattr(paragraph, "text", "") or "").strip()
            if text:
                return text
        return ""

    def _parse_table(
        self,
        tbl_elem,
        paragraph_index: int,
        table_depth: int = 0,
        structure_depth: int = 0,
    ) -> Table:
        if table_depth > MAX_NESTED_TABLE_DEPTH:
            return Table(rows=[])
        if not self._structure_depth_allowed(structure_depth):
            return Table(rows=[])
        rows = []
        open_vmerges: Dict[int, Tuple[int, int]] = {}
        row_entries = self._iter_table_rows(tbl_elem, structure_depth)
        for row_idx, (tr_elem, row_structure_depth) in enumerate(row_entries):
            grid_before = self._row_grid_before(tr_elem)
            if not self._reserve_table_cells(grid_before):
                return Table(rows=[])
            row = [
                Cell(provenance=self._table_cell_provenance(row_idx, col_idx))
                for col_idx in range(grid_before)
            ]
            col_idx = len(row)
            cell_entries = self._iter_row_cells(tr_elem, row_structure_depth)
            for tc_elem, cell_structure_depth in cell_entries:
                provenance = self._table_cell_provenance(row_idx, col_idx)
                vmerge = self._cell_vmerge(tc_elem)
                if vmerge == "continue":
                    if not self._reserve_table_cells(1):
                        return Table(rows=[])
                    row.append(Cell(row_span=0, col_span=0, provenance=provenance))
                    if col_idx in open_vmerges:
                        start_row_idx, start_col_idx = open_vmerges[col_idx]
                        rows[start_row_idx][start_col_idx].row_span += 1
                    col_idx += 1
                    continue

                cell_paragraphs = []
                nested_paragraphs, paragraph_index = self._parse_cell_paragraphs(
                    tc_elem,
                    paragraph_index,
                    table_depth,
                    cell_structure_depth,
                )
                cell_paragraphs.extend(nested_paragraphs)
                col_span = self._cell_col_span(tc_elem)
                if not self._reserve_table_cells(col_span):
                    return Table(rows=[])
                cell = Cell(paragraphs=cell_paragraphs, col_span=col_span, provenance=provenance)
                row.append(cell)
                if vmerge == "restart":
                    open_vmerges[col_idx] = (len(rows), len(row) - 1)
                elif col_idx in open_vmerges:
                    del open_vmerges[col_idx]
                for _ in range(col_span - 1):
                    row.append(Cell(
                        row_span=0,
                        col_span=0,
                        provenance=self._table_cell_provenance(row_idx, len(row)),
                    ))
                col_idx += col_span
            rows.append(row)
        return Table(rows=rows)

    def _reserve_table_cells(self, count: int) -> bool:
        if count < 0 or count > getattr(self, "_table_cell_budget", 0):
            errors = getattr(self, "_active_document_errors", None)
            if errors is not None:
                errors.append("ERR: DOCX table cell limit exceeded")
            return False
        self._table_cell_budget -= count
        return True

    def _iter_table_rows(
        self, container, structure_depth: int = 0,
    ) -> List[Tuple[object, int]]:
        if not self._structure_depth_allowed(structure_depth):
            return []
        rows = []
        for child in list(container):
            if child.tag == f"{{{W_NS}}}tr":
                rows.append((child, structure_depth))
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
            ):
                rows.extend(self._iter_table_rows(child, structure_depth + 1))
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                rows.extend(
                    self._iter_table_rows(
                        self._alternate_content_preferred_child(child),
                        structure_depth + 1,
                    )
                )
        return rows

    def _iter_row_cells(
        self, container, structure_depth: int = 0,
    ) -> List[Tuple[object, int]]:
        if not self._structure_depth_allowed(structure_depth):
            return []
        cells = []
        for child in list(container):
            if child.tag == f"{{{W_NS}}}tc":
                cells.append((child, structure_depth))
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
            ):
                cells.extend(self._iter_row_cells(child, structure_depth + 1))
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                cells.extend(
                    self._iter_row_cells(
                        self._alternate_content_preferred_child(child),
                        structure_depth + 1,
                    )
                )
        return cells

    def _table_cell_provenance(self, row_idx: int, col_idx: int) -> Provenance:
        return Provenance(
            source_format="docx",
            cell=f"R{row_idx + 1}C{col_idx + 1}",
            path=self._document_part,
        )

    def _row_grid_before(self, tr_elem) -> int:
        grid_before = tr_elem.find("w:trPr/w:gridBefore", namespaces=NS)
        if grid_before is None:
            return 0
        try:
            value = int(_w_attr(grid_before, "val"))
        except ValueError:
            self._active_document_errors.append("ERR: DOCX invalid gridBefore value")
            return 0
        if value < 0:
            self._active_document_errors.append("ERR: DOCX invalid gridBefore value")
            return 0
        return value

    def _parse_cell_paragraphs(
        self,
        tc_elem,
        paragraph_index: int,
        table_depth: int = 0,
        structure_depth: int = 0,
    ):
        if not self._structure_depth_allowed(structure_depth):
            return [], paragraph_index
        paragraphs = []
        for child in list(tc_elem):
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(
                    child,
                    paragraph_index,
                    structure_depth=structure_depth,
                    numbering=getattr(self, "_numbering", {}),
                )
                paragraph_index += 1
                paragraphs.extend(self._paragraph_flow(para))
            elif child.tag in (f"{{{M_NS}}}oMath", f"{{{M_NS}}}oMathPara"):
                paragraphs.extend(self._equations_in(child, include_self=True))
            elif child.tag == f"{{{W_NS}}}commentRangeEnd":
                annotation = self._comment_annotation(_w_attr(child, "id"))
                if annotation:
                    paragraphs.append(Paragraph(runs=[TextRun(text=annotation)]))
            elif child.tag == f"{{{W_NS}}}tbl":
                if table_depth >= MAX_NESTED_TABLE_DEPTH:
                    paragraphs.append(Paragraph(runs=[TextRun(text="[nested table omitted: depth limit exceeded]")]))
                    continue
                table = self._parse_table(
                    child,
                    paragraph_index,
                    table_depth + 1,
                    structure_depth,
                )
                table._source_element = child
                paragraphs.append(table)
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
            ):
                nested_paragraphs, paragraph_index = self._parse_cell_paragraphs(
                    child,
                    paragraph_index,
                    table_depth,
                    structure_depth + 1,
                )
                paragraphs.extend(nested_paragraphs)
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                nested_paragraphs, paragraph_index = self._parse_cell_paragraphs(
                    self._alternate_content_preferred_child(child),
                    paragraph_index,
                    table_depth,
                    structure_depth + 1,
                )
                paragraphs.extend(nested_paragraphs)
        return paragraphs, paragraph_index

    def _cell_col_span(self, tc_elem) -> int:
        grid_span = tc_elem.find("w:tcPr/w:gridSpan", namespaces=NS)
        if grid_span is None:
            return 1
        try:
            value = int(_w_attr(grid_span, "val"))
        except ValueError:
            self._active_document_errors.append("ERR: DOCX invalid gridSpan value")
            return 1
        if value <= 0:
            self._active_document_errors.append("ERR: DOCX invalid gridSpan value")
            return 1
        return value

    def _cell_vmerge(self, tc_elem) -> str:
        vmerge = tc_elem.find("w:tcPr/w:vMerge", namespaces=NS)
        if vmerge is None:
            return ""
        value = _w_attr(vmerge, "val")
        return "restart" if value == "restart" else "continue"
