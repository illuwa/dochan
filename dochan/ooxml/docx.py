"""Native DOCX reader."""
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import posixpath
import re
import zipfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

from lxml import etree

from ..conversion import AssetRef, Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.equation import Equation
from ..model.header_footer import Comment, Footnote, HeaderFooter
from ..model.image import Image
from ..model.table import Cell, Table
from .package import OOXMLPackage

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
}
MAX_NESTED_TABLE_DEPTH = 32
MAX_TABLE_CELLS = 200000
MAX_STRUCTURE_DEPTH = 64
MAX_NUMBERING_VALUE = 100000
MAX_NUMBERING_LEVEL = 8
MAX_NUMBERING_TEMPLATE_CHARS = 256
MAX_IMAGE_ASSET_REFS = 10000
MAX_DIAGNOSTIC_PATH_CHARS = 256
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
        self._numbering_counts = {}
        self._note_reference_numbers = {}
        self._note_reference_order = []
        self._comment_reference_numbers = {}
        self._comment_reference_order = []
        self._image_asset_ids = set()
        self._image_asset_count = 0
        self._image_asset_limit_reported = False
        self._assets = []
        self._image_elements = []
        self._image_bytes_total = 0
        self._table_cell_budget = MAX_TABLE_CELLS
        self._active_document_errors = doc.errors
        try:
            with OOXMLPackage(file_path) as package:
                self._package = package
                root = package.read_xml_part("word/document.xml")
                self._document_relationships = self._read_document_relationships(package)
                self._active_relationships = self._document_relationships
                self._alt_chunk_data = self._read_alt_chunk_data(package, self._document_relationships)
                self._image_data_cache = self._preload_image_bytes(package)
                self._record_embedded_relationship_assets(package)
                self._paragraph_styles = self._read_paragraph_styles(package)
                self._run_styles = self._read_run_styles(package)
                numbering = self._read_numbering(package)
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
            doc.errors.append(f"ERR: DOCX package parse failed: {exc}")
            return doc

        section = Section(
            provenance=Provenance(source_format="docx", section=0, path="word/document.xml")
        )
        body = root.find("w:body", namespaces=NS)
        if body is None:
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

        section.elements.extend(getattr(self, "_image_elements", []))
        doc.assets = getattr(self, "_assets", [])
        doc.sections.append(section)
        self._package = None
        self._active_relationships = {}
        self._alt_chunk_data = {}
        return doc

    def _parse_block_elements(
        self,
        container,
        paragraph_index_ref: List[int],
        numbering,
        depth: int = 0,
    ) -> List[object]:
        if not self._structure_depth_allowed(depth):
            return []
        elements = []
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(
                    child,
                    paragraph_index_ref[0],
                    structure_depth=depth,
                )
                self._apply_numbering(para, child, numbering)
                paragraph_index_ref[0] += 1
                if para.text.strip():
                    elements.append(para)
                elements.extend(self._equations_in(child))
            elif child.tag in (f"{{{M_NS}}}oMathPara", f"{{{M_NS}}}oMath"):
                elements.extend(self._equations_in(child, include_self=True))
            elif child.tag == f"{{{W_NS}}}altChunk":
                alt_chunk_elements = self._parse_alt_chunk(child, paragraph_index_ref[0])
                paragraph_index_ref[0] += len(alt_chunk_elements)
                elements.extend(alt_chunk_elements)
            elif child.tag == f"{{{W_NS}}}tbl":
                elements.append(
                    self._parse_table(
                        child,
                        paragraph_index_ref[0],
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
        return elements

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

    def _parse_paragraph(
        self,
        p_elem,
        paragraph_index: int,
        path: str = "word/document.xml",
        structure_depth: int = 0,
    ) -> Paragraph:
        para = Paragraph(
            provenance=Provenance(
                source_format="docx",
                section=0,
                paragraph=paragraph_index,
                path=path,
            )
        )
        para.heading_level = self._heading_level(p_elem)
        para.runs = self._parse_runs(p_elem, structure_depth)
        for run in para.runs:
            if run.provenance is None:
                run.provenance = para.provenance
        return para

    def _read_notes(self, package: OOXMLPackage, path: str, note_type: str) -> Dict[str, Footnote]:
        if not package.exists(path):
            return {}
        root = package.read_xml_part(path)
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
                blocks.append(para)
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
                if para.text.strip():
                    paragraphs.append(para)
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
            or digits == "0"
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
        for style in root.findall("w:style", namespaces=NS):
            if _w_attr(style, "type") != "paragraph":
                continue
            style_id = _w_attr(style, "styleId")
            if not style_id:
                continue
            based_on = _w_attr(style.find("w:basedOn", namespaces=NS), "val")
            styles[style_id] = based_on
        return styles

    def _read_run_styles(self, package: OOXMLPackage) -> Dict[str, _RunStyle]:
        if not package.exists("word/styles.xml"):
            return {}
        root = package.read_xml_part("word/styles.xml")
        styles = {}
        for style in root.findall("w:style", namespaces=NS):
            if _w_attr(style, "type") != "character":
                continue
            style_id = _w_attr(style, "styleId")
            if not style_id:
                continue
            styles[style_id] = self._run_style_from_rpr(style.find("w:rPr", namespaces=NS))
        return styles

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
        rels_path = "word/_rels/document.xml.rels"
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
                    "word", target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/image"):
                resolved = self._validated_internal_relationship_target(
                    "word", target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/aFChunk"):
                resolved = self._validated_internal_relationship_target(
                    "word", target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
            elif rel_type.endswith("/hyperlink"):
                resolved = self._validated_internal_relationship_target(
                    "word", target, rels_path, rel_id,
                )
                if resolved:
                    relationships[rel_id] = resolved
        return relationships

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
            if rel_type.endswith("/image"):
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
        rels_path = "word/_rels/document.xml.rels"
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
                "word", target, rels_path, rel_id,
            )
            if source_path:
                self._record_embedded_asset(rel_id, source_path, rel_type)

    def _apply_numbering(self, para: Paragraph, p_elem, numbering: Dict[Tuple[str, str], _NumberingLevel]):
        num_pr = p_elem.find("w:pPr/w:numPr", namespaces=NS)
        if num_pr is None:
            return
        num_id = _w_attr(num_pr.find("w:numId", namespaces=NS), "val")
        ilvl = self._validated_numbering_level(
            _w_attr(num_pr.find("w:ilvl", namespaces=NS), "val") or "0",
        )
        if ilvl is None:
            return
        level = numbering.get((num_id, ilvl))
        if not level:
            return
        count = getattr(self, "_numbering_counts", {}).get((num_id, ilvl))
        if count is None:
            count = level.start
        if not 1 <= count <= MAX_NUMBERING_VALUE:
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
        if not 1 <= count <= MAX_NUMBERING_VALUE:
            self._record_numbering_limit("generated marker")
            return ""
        if fmt == "decimalZero":
            return str(count).zfill(2)
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
        runs = []
        annotated_comments = set()
        for child in p_elem:
            if child.tag == f"{{{W_NS}}}r":
                comment_reference_ids = self._run_comment_reference_ids(child)
                if comment_reference_ids and comment_reference_ids.issubset(annotated_comments):
                    continue
                runs.extend(self._parse_run(child, depth))
            elif child.tag == f"{{{W_NS}}}hyperlink":
                hyperlink_runs = []
                for r_elem in child.findall("w:r", namespaces=NS):
                    hyperlink_runs.extend(self._parse_run(r_elem, depth))
                target = self._hyperlink_target(child)
                if target and hyperlink_runs:
                    hyperlink_runs[-1].text = f"{hyperlink_runs[-1].text} <{target}>"
                runs.extend(hyperlink_runs)
            elif child.tag == f"{{{W_NS}}}bookmarkStart":
                bookmark_marker = self._bookmark_marker(child)
                if bookmark_marker:
                    runs.append(TextRun(text=bookmark_marker))
            elif child.tag == f"{{{W_NS}}}commentRangeEnd":
                comment_id = _w_attr(child, "id")
                annotation = self._comment_annotation(comment_id)
                if annotation:
                    annotated_comments.add(comment_id)
                    if runs:
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
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}fldSimple",
            ):
                runs.extend(self._parse_runs(child, depth + 1))
        return runs

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
            text = "".join(text_parts)
            if text:
                segments.append((text, "", None))
            text_parts.clear()

        for child in r_elem:
            if child.tag == f"{{{W_NS}}}t":
                text_parts.append(child.text or "")
            elif child.tag == f"{{{W_NS}}}tab":
                text_parts.append("\t")
            elif child.tag == f"{{{W_NS}}}br":
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
                number = self._register_comment_reference(_w_attr(child, "id"))
                if number is not None:
                    flush_text()
                    segments.append((f"[comment {number}]", "comment", number))
            else:
                text_parts.extend(self._textbox_texts(child, depth + 1))
                image_reference = self._image_reference(child)
                if image_reference:
                    text_parts.append(image_reference)
                for doc_pr in child.findall(".//wp:docPr", namespaces=NS):
                    alt_parts = [doc_pr.get("title", ""), doc_pr.get("descr", "")]
                    alt_text = " ".join(part for part in alt_parts if part)
                    if alt_text:
                        text_parts.append(alt_text)

        flush_text()
        if not segments:
            return []

        r_pr = r_elem.find("w:rPr", namespaces=NS)
        runs = []
        for text, note_type, note_number in segments:
            run = TextRun(
                text=text,
                note_reference_type=note_type,
                note_reference_number=note_number,
            )
            # Markdown 렌더러는 note_ref 로 각주 참조를 그린다. 두 표현을 함께 채워
            # 의미 필드(note_reference_*)와 렌더 필드가 어긋나지 않게 한다.
            if note_number is not None and note_type in ('footnote', 'endnote'):
                run.note_ref = note_number
            if r_pr is not None:
                self._apply_run_style(run, self._referenced_run_style(r_pr))
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
                vert_align = r_pr.find("w:vertAlign", namespaces=NS)
                if vert_align is not None:
                    value = _w_attr(vert_align, "val")
                    run.superscript = value == "superscript"
                    run.subscript = value == "subscript"
            runs.append(run)
        return runs

    def _textbox_texts(self, elem, depth: int = 0) -> List[str]:
        search_root = self._alternate_content_preferred_child(elem)
        textboxes = self._outermost_textbox_contents(search_root)
        if not textboxes or not self._structure_depth_allowed(depth):
            return []
        texts = []
        anchored = search_root.find(".//wp:anchor", namespaces=NS) is not None
        for textbox in textboxes:
            paragraph_texts = []
            for p_elem in textbox.findall("w:p", namespaces=NS):
                text = "".join(
                    run.text for run in self._parse_runs(p_elem, depth)
                ).strip()
                if text:
                    paragraph_texts.append(text)
            if paragraph_texts:
                text = "\n".join(paragraph_texts)
                texts.append(f"{text}\n" if anchored else text)
        return texts

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
        """요소 안의 m:oMath 를 Equation(LaTeX) 목록으로 변환."""
        if include_self and elem.tag == f"{{{M_NS}}}oMath":
            omaths = [elem]
        else:
            omaths = elem.findall(".//m:oMath", namespaces=NS)
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
        image_elem = elem.find(".//a:blip", namespaces=NS)
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
        doc_pr = elem.find(".//wp:docPr", namespaces=NS)
        label = self._doc_pr_label(doc_pr)
        self._record_image_asset(rel_id, target, label)
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
        if not package.exists("word/_rels/document.xml.rels"):
            return cache
        try:
            root = package.read_xml_part("word/_rels/document.xml.rels")
        except Exception:
            return cache
        total = 0
        for rel in root.findall("rel:Relationship", namespaces=NS):
            if not rel.get("Type", "").endswith("/image"):
                continue
            try:
                # 제어문자·외부 스킴이 섞인 조작된 대상은 여기서 걸러진다.
                target = _resolve_internal_target("word", rel.get("Target", ""))
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
        ext = posixpath.splitext(target)[1].lstrip(".").lower()
        self._image_elements.append(
            Image(
                filename=posixpath.basename(target),
                image_data=data,
                alt_text=label,
                image_format=ext,
                provenance=Provenance(source_format="docx", path=target),
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
            path="word/document.xml",
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
                )
                paragraph_index += 1
                if para.text.strip():
                    paragraphs.append(para)
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
                for row in table.rows:
                    for cell in row:
                        if cell.text.strip():
                            paragraphs.append(Paragraph(runs=[TextRun(text=cell.text)]))
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


# ── OMML(Office Math Markup Language) → LaTeX ──

def _m_tag(name: str) -> str:
    return f"{{{M_NS}}}{name}"


_OMML_CONTAINER_TAGS = frozenset(
    _m_tag(name)
    for name in ("oMath", "oMathPara", "e", "num", "den", "sub", "sup", "deg", "fName", "lim")
)

_NARY_OPERATORS = {
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint",
    "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap", "⋁": r"\bigvee", "⋀": r"\bigwedge",
}

_OMML_MAX_DEPTH = 32


def _omml_child(elem, name: str):
    return elem.find(f"m:{name}", namespaces=NS)


def _omml_join(elem, depth: int) -> str:
    return "".join(_omml_to_latex(child, depth + 1) for child in elem)


def _omml_to_latex(elem, depth: int = 0) -> str:
    """OMML 트리를 LaTeX 문자열로 재귀 변환. 미지원 요소는 자식 텍스트를 보존."""
    if depth > _OMML_MAX_DEPTH:
        return ""
    tag = elem.tag
    if tag == _m_tag("t"):
        return elem.text or ""
    if tag == _m_tag("r"):
        return "".join(t.text or "" for t in elem.findall("m:t", namespaces=NS))
    if tag in _OMML_CONTAINER_TAGS:
        return _omml_join(elem, depth)
    if tag == _m_tag("f"):
        num = _omml_child(elem, "num")
        den = _omml_child(elem, "den")
        return "\\frac{%s}{%s}" % (
            _omml_to_latex(num, depth + 1) if num is not None else "",
            _omml_to_latex(den, depth + 1) if den is not None else "",
        )
    if tag == _m_tag("sSup"):
        base = _omml_child(elem, "e")
        sup = _omml_child(elem, "sup")
        return "{%s}^{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(sup, depth + 1) if sup is not None else "",
        )
    if tag == _m_tag("sSub"):
        base = _omml_child(elem, "e")
        sub = _omml_child(elem, "sub")
        return "{%s}_{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(sub, depth + 1) if sub is not None else "",
        )
    if tag == _m_tag("sSubSup"):
        base = _omml_child(elem, "e")
        sub = _omml_child(elem, "sub")
        sup = _omml_child(elem, "sup")
        return "{%s}_{%s}^{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(sub, depth + 1) if sub is not None else "",
            _omml_to_latex(sup, depth + 1) if sup is not None else "",
        )
    if tag == _m_tag("rad"):
        deg = _omml_child(elem, "deg")
        base = _omml_child(elem, "e")
        deg_tex = _omml_to_latex(deg, depth + 1) if deg is not None else ""
        base_tex = _omml_to_latex(base, depth + 1) if base is not None else ""
        if deg_tex:
            return "\\sqrt[%s]{%s}" % (deg_tex, base_tex)
        return "\\sqrt{%s}" % base_tex
    if tag == _m_tag("nary"):
        nary_pr = _omml_child(elem, "naryPr")
        chr_elem = nary_pr.find("m:chr", namespaces=NS) if nary_pr is not None else None
        chr_val = chr_elem.get(f"{{{M_NS}}}val", "") if chr_elem is not None else ""
        operator = _NARY_OPERATORS.get(chr_val, r"\int")
        sub = _omml_child(elem, "sub")
        sup = _omml_child(elem, "sup")
        base = _omml_child(elem, "e")
        parts = operator
        sub_tex = _omml_to_latex(sub, depth + 1) if sub is not None else ""
        sup_tex = _omml_to_latex(sup, depth + 1) if sup is not None else ""
        if sub_tex:
            parts += "_{%s}" % sub_tex
        if sup_tex:
            parts += "^{%s}" % sup_tex
        base_tex = _omml_to_latex(base, depth + 1) if base is not None else ""
        return f"{parts} {base_tex}".rstrip()
    if tag == _m_tag("d"):  # 구분자 (기본 괄호)
        inner = ",".join(
            _omml_to_latex(e, depth + 1) for e in elem.findall("m:e", namespaces=NS)
        )
        d_pr = _omml_child(elem, "dPr")
        beg = end = None
        if d_pr is not None:
            beg_elem = d_pr.find("m:begChr", namespaces=NS)
            end_elem = d_pr.find("m:endChr", namespaces=NS)
            beg = beg_elem.get(f"{{{M_NS}}}val") if beg_elem is not None else None
            end = end_elem.get(f"{{{M_NS}}}val") if end_elem is not None else None
        return f"{beg if beg is not None else '('}{inner}{end if end is not None else ')'}"
    if tag == _m_tag("func"):
        fname = _omml_child(elem, "fName")
        base = _omml_child(elem, "e")
        return "%s(%s)" % (
            _omml_to_latex(fname, depth + 1) if fname is not None else "",
            _omml_to_latex(base, depth + 1) if base is not None else "",
        )
    if tag == _m_tag("limLow"):
        base = _omml_child(elem, "e")
        lim = _omml_child(elem, "lim")
        return "{%s}_{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(lim, depth + 1) if lim is not None else "",
        )
    if tag == _m_tag("limUpp"):
        base = _omml_child(elem, "e")
        lim = _omml_child(elem, "lim")
        return "{%s}^{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(lim, depth + 1) if lim is not None else "",
        )
    # 미지원 구조 — 자식을 이어붙여 텍스트 보존
    return _omml_join(elem, depth)
