"""Native DOCX reader."""
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import posixpath
import re
from typing import Dict, List, Tuple

from ..conversion import AssetRef, Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.header_footer import Footnote, HeaderFooter
from ..model.table import Cell, Table
from .package import OOXMLPackage

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
DC_NS = "http://purl.org/dc/elements/1.1/"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
V_NS = "urn:schemas-microsoft-com:vml"
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
}
MAX_NESTED_TABLE_DEPTH = 32


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


def _w_attr(elem, name: str) -> str:
    if elem is None:
        return ""
    return elem.get(f"{{{W_NS}}}{name}", "")


def _r_attr(elem, name: str) -> str:
    if elem is None:
        return ""
    return elem.get(f"{{{R_NS}}}{name}", "")


def _w15_attr(elem, name: str) -> str:
    if elem is None:
        return ""
    return elem.get(f"{{{W15_NS}}}{name}", "")


def _resolve_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/")).replace("\\", "/")
    return posixpath.normpath(posixpath.join(base_dir, target)).replace("\\", "/")


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
        self._assets = []
        with OOXMLPackage(file_path) as package:
            self._package = package
            root = package.read_xml_part("word/document.xml")
            self._document_relationships = self._read_document_relationships(package)
            self._active_relationships = self._document_relationships
            self._alt_chunk_data = self._read_alt_chunk_data(package, self._document_relationships)
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

        doc.assets = getattr(self, "_assets", [])
        doc.sections.append(section)
        self._package = None
        self._active_relationships = {}
        self._alt_chunk_data = {}
        return doc

    def _parse_block_elements(self, container, paragraph_index_ref: List[int], numbering) -> List[object]:
        elements = []
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(child, paragraph_index_ref[0])
                self._apply_numbering(para, child, numbering)
                paragraph_index_ref[0] += 1
                if para.text.strip():
                    elements.append(para)
            elif child.tag == f"{{{W_NS}}}altChunk":
                alt_chunk_elements = self._parse_alt_chunk(child, paragraph_index_ref[0])
                paragraph_index_ref[0] += len(alt_chunk_elements)
                elements.extend(alt_chunk_elements)
            elif child.tag == f"{{{W_NS}}}tbl":
                elements.append(self._parse_table(child, paragraph_index_ref[0]))
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
                f"{{{W_NS}}}moveFrom",
                f"{{{W_NS}}}moveTo",
            ):
                elements.extend(self._parse_block_elements(child, paragraph_index_ref, numbering))
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(child)
                elements.extend(self._parse_block_elements(preferred, paragraph_index_ref, numbering))
        return elements

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

    def _parse_paragraph(self, p_elem, paragraph_index: int, path: str = "word/document.xml") -> Paragraph:
        para = Paragraph(
            provenance=Provenance(
                source_format="docx",
                section=0,
                paragraph=paragraph_index,
                path=path,
            )
        )
        para.heading_level = self._heading_level(p_elem)
        para.runs = self._parse_runs(p_elem)
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
            note = Footnote(type=note_type)
            note.author = _w_attr(note_elem, "author")
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

    def _parse_note_blocks(self, container, paragraph_index: int, path: str) -> List[object]:
        blocks = []
        paragraph_ref = [paragraph_index]
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(child, paragraph_ref[0], path=path)
                para._source_element = child
                blocks.append(para)
                paragraph_ref[0] += 1
            elif child.tag == f"{{{W_NS}}}tbl":
                blocks.append(self._parse_table(child, paragraph_ref[0]))
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
                f"{{{W_NS}}}moveFrom",
                f"{{{W_NS}}}moveTo",
            ):
                nested = self._parse_note_blocks(child, paragraph_ref[0], path)
                paragraph_ref[0] += sum(isinstance(item, Paragraph) for item in nested)
                blocks.extend(nested)
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                nested = self._parse_note_blocks(self._alternate_content_preferred_child(child), paragraph_ref[0], path)
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

    def _parse_header_footer_paragraphs(self, container, paragraph_index_ref: List[int], path: str) -> List[Paragraph]:
        paragraphs = []
        for child in container:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(child, paragraph_index_ref[0], path=path)
                paragraph_index_ref[0] += 1
                if para.text.strip():
                    paragraphs.append(para)
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
                f"{{{W_NS}}}moveFrom",
                f"{{{W_NS}}}moveTo",
            ):
                paragraphs.extend(self._parse_header_footer_paragraphs(child, paragraph_index_ref, path))
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                preferred = self._alternate_content_preferred_child(child)
                paragraphs.extend(self._parse_header_footer_paragraphs(preferred, paragraph_index_ref, path))
        return paragraphs

    def _read_numbering(self, package: OOXMLPackage) -> Dict[Tuple[str, str], _NumberingLevel]:
        if not package.exists("word/numbering.xml"):
            return {}
        root = package.read_xml_part("word/numbering.xml")
        abstract_levels: Dict[Tuple[str, str], _NumberingLevel] = {}
        for abstract in root.findall("w:abstractNum", namespaces=NS):
            abstract_id = _w_attr(abstract, "abstractNumId")
            for level in abstract.findall("w:lvl", namespaces=NS):
                ilvl = _w_attr(level, "ilvl") or "0"
                fmt = _w_attr(level.find("w:numFmt", namespaces=NS), "val") or "decimal"
                text = _w_attr(level.find("w:lvlText", namespaces=NS), "val") or "%1."
                start_raw = _w_attr(level.find("w:start", namespaces=NS), "val") or "1"
                try:
                    start = int(start_raw)
                except ValueError:
                    start = 1
                abstract_levels[(abstract_id, ilvl)] = _NumberingLevel(fmt=fmt, text=text, start=start)

        levels: Dict[Tuple[str, str], _NumberingLevel] = {}
        for num in root.findall("w:num", namespaces=NS):
            num_id = _w_attr(num, "numId")
            abstract_id = _w_attr(num.find("w:abstractNumId", namespaces=NS), "val")
            for (candidate_id, ilvl), level in abstract_levels.items():
                if candidate_id == abstract_id:
                    levels[(num_id, ilvl)] = level
        return levels

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
        style.bold = r_pr.find("w:b", namespaces=NS) is not None
        style.italic = r_pr.find("w:i", namespaces=NS) is not None
        style.underline = r_pr.find("w:u", namespaces=NS) is not None
        style.strikeout = r_pr.find("w:strike", namespaces=NS) is not None
        vert_align = r_pr.find("w:vertAlign", namespaces=NS)
        if vert_align is not None:
            value = _w_attr(vert_align, "val")
            style.superscript = value == "superscript"
            style.subscript = value == "subscript"
        return style

    def _read_document_relationships(self, package: OOXMLPackage) -> Dict[str, str]:
        if not package.exists("word/_rels/document.xml.rels"):
            return {}
        root = package.read_xml_part("word/_rels/document.xml.rels")
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            rel_type = rel.get("Type", "")
            target = rel.get("Target", "")
            if not rel_id or not target:
                continue
            if rel_type.endswith("/hyperlink"):
                relationships[rel_id] = target
            elif rel_type.endswith("/header") or rel_type.endswith("/footer"):
                relationships[rel_id] = _resolve_target("word", target)
            elif rel_type.endswith("/image"):
                relationships[rel_id] = _resolve_target("word", target)
            elif rel_type.endswith("/aFChunk"):
                relationships[rel_id] = _resolve_target("word", target)
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
            if rel_type.endswith("/hyperlink"):
                relationships[rel_id] = target
            elif rel_type.endswith("/image"):
                relationships[rel_id] = _resolve_target(part_dir, target)
            elif rel_type.endswith("/aFChunk"):
                relationships[rel_id] = _resolve_target(part_dir, target)
        return relationships

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
        if not package.exists("word/_rels/document.xml.rels"):
            return
        root = package.read_xml_part("word/_rels/document.xml.rels")
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_type = rel.get("Type", "")
            if not (rel_type.endswith("/oleObject") or rel_type.endswith("/package")):
                continue
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if not rel_id or not target:
                continue
            source_path = _resolve_target("word", target)
            self._record_embedded_asset(rel_id, source_path, rel_type)

    def _apply_numbering(self, para: Paragraph, p_elem, numbering: Dict[Tuple[str, str], _NumberingLevel]):
        num_pr = p_elem.find("w:pPr/w:numPr", namespaces=NS)
        if num_pr is None:
            return
        num_id = _w_attr(num_pr.find("w:numId", namespaces=NS), "val")
        ilvl = _w_attr(num_pr.find("w:ilvl", namespaces=NS), "val") or "0"
        level = numbering.get((num_id, ilvl))
        if not level:
            return
        count = getattr(self, "_numbering_counts", {}).get((num_id, ilvl))
        if count is None:
            count = level.start
        self._numbering_counts[(num_id, ilvl)] = count + 1
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
            while value >= number:
                result.append(marker)
                value -= number
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

    def _parse_runs(self, p_elem) -> List[TextRun]:
        runs = []
        annotated_comments = set()
        for child in p_elem:
            if child.tag == f"{{{W_NS}}}r":
                comment_reference_ids = self._run_comment_reference_ids(child)
                if comment_reference_ids and comment_reference_ids.issubset(annotated_comments):
                    continue
                runs.extend(self._parse_run(child))
            elif child.tag == f"{{{W_NS}}}hyperlink":
                hyperlink_runs = []
                for r_elem in child.findall("w:r", namespaces=NS):
                    hyperlink_runs.extend(self._parse_run(r_elem))
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
                runs.extend(self._parse_runs(child))
            elif child.tag in (
                f"{{{W_NS}}}moveFrom",
                f"{{{W_NS}}}moveTo",
            ):
                runs.extend(self._parse_runs(child))
            elif child.tag == f"{{{W_NS}}}del":
                continue
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}fldSimple",
            ):
                runs.extend(self._parse_runs(child))
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

    def _parse_run(self, r_elem) -> List[TextRun]:
        text_parts = []
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
                text_parts.append(self._note_marker("footnote", _w_attr(child, "id")))
            elif child.tag == f"{{{W_NS}}}endnoteReference":
                text_parts.append(self._note_marker("endnote", _w_attr(child, "id")))
            elif child.tag == f"{{{W_NS}}}commentReference":
                text_parts.append(self._comment_marker(_w_attr(child, "id")))
            else:
                text_parts.extend(self._textbox_texts(child))
                image_reference = self._image_reference(child)
                if image_reference:
                    text_parts.append(image_reference)
                for doc_pr in child.findall(".//wp:docPr", namespaces=NS):
                    alt_parts = [doc_pr.get("title", ""), doc_pr.get("descr", "")]
                    alt_text = " ".join(part for part in alt_parts if part)
                    if alt_text:
                        text_parts.append(alt_text)

        text = "".join(text_parts)
        if not text:
            return []

        r_pr = r_elem.find("w:rPr", namespaces=NS)
        run = TextRun(text=text)
        if r_pr is not None:
            self._apply_run_style(run, self._referenced_run_style(r_pr))
            run.bold = run.bold or r_pr.find("w:b", namespaces=NS) is not None
            run.italic = run.italic or r_pr.find("w:i", namespaces=NS) is not None
            run.underline = run.underline or r_pr.find("w:u", namespaces=NS) is not None
            run.strikeout = run.strikeout or r_pr.find("w:strike", namespaces=NS) is not None
            vert_align = r_pr.find("w:vertAlign", namespaces=NS)
            if vert_align is not None:
                value = _w_attr(vert_align, "val")
                run.superscript = value == "superscript"
                run.subscript = value == "subscript"
        return [run]

    def _textbox_texts(self, elem) -> List[str]:
        search_root = self._alternate_content_preferred_child(elem)
        texts = []
        anchored = search_root.find(".//wp:anchor", namespaces=NS) is not None
        for textbox in search_root.findall(".//w:txbxContent", namespaces=NS):
            paragraph_texts = []
            for p_elem in textbox.findall("w:p", namespaces=NS):
                text = "".join(run.text for run in self._parse_runs(p_elem)).strip()
                if text:
                    paragraph_texts.append(text)
            if paragraph_texts:
                text = "\n".join(paragraph_texts)
                texts.append(f"{text}\n" if anchored else text)
        return texts

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
        key = ("image", rel_id, target)
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
                content_type=self._image_content_type(target),
                metadata={"label": label, "source_format": "docx"},
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

    def _note_marker(self, note_type: str, note_id: str) -> str:
        if not note_id or note_id not in getattr(self, "_notes", {}).get(note_type, {}):
            return ""
        key = (note_type, note_id)
        if key not in self._note_reference_numbers:
            self._note_reference_numbers[key] = len(self._note_reference_numbers) + 1
            self._note_reference_order.append(key)
        return f"[{self._note_reference_numbers[key]}]"

    def _comment_marker(self, comment_id: str) -> str:
        if not comment_id or comment_id not in getattr(self, "_comments", {}):
            return ""
        if comment_id not in self._comment_reference_numbers:
            self._comment_reference_numbers[comment_id] = len(self._comment_reference_numbers) + 1
            self._comment_reference_order.append(comment_id)
        return f"[comment {self._comment_reference_numbers[comment_id]}]"

    def _comment_annotation(self, comment_id: str) -> str:
        marker = self._comment_marker(comment_id)
        if not marker:
            return ""
        comment = getattr(self, "_comments", {}).get(comment_id)
        comment_text = self._comment_primary_text(comment)
        if not comment_text:
            return marker
        return f"{marker[:-1]}: {comment_text}]"

    def _comment_primary_text(self, comment: Footnote) -> str:
        if not comment:
            return ""
        for paragraph in comment.paragraphs:
            text = (paragraph.text or "").strip()
            if text:
                return text
        return ""

    def _parse_table(self, tbl_elem, paragraph_index: int, depth: int = 0) -> Table:
        if depth > MAX_NESTED_TABLE_DEPTH:
            return Table(rows=[])
        rows = []
        open_vmerges: Dict[int, Tuple[int, int]] = {}
        for row_idx, tr_elem in enumerate(self._iter_table_rows(tbl_elem)):
            row = [
                Cell(provenance=self._table_cell_provenance(row_idx, col_idx))
                for col_idx in range(self._row_grid_before(tr_elem))
            ]
            col_idx = len(row)
            for tc_elem in self._iter_row_cells(tr_elem):
                provenance = self._table_cell_provenance(row_idx, col_idx)
                vmerge = self._cell_vmerge(tc_elem)
                if vmerge == "continue":
                    row.append(Cell(row_span=0, col_span=0, provenance=provenance))
                    if col_idx in open_vmerges:
                        start_row_idx, start_col_idx = open_vmerges[col_idx]
                        rows[start_row_idx][start_col_idx].row_span += 1
                    col_idx += 1
                    continue

                cell_paragraphs = []
                nested_paragraphs, paragraph_index = self._parse_cell_paragraphs(tc_elem, paragraph_index, depth)
                cell_paragraphs.extend(nested_paragraphs)
                col_span = self._cell_col_span(tc_elem)
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

    def _iter_table_rows(self, container) -> List[object]:
        rows = []
        for child in list(container):
            if child.tag == f"{{{W_NS}}}tr":
                rows.append(child)
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
            ):
                rows.extend(self._iter_table_rows(child))
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                rows.extend(self._iter_table_rows(self._alternate_content_preferred_child(child)))
        return rows

    def _iter_row_cells(self, container) -> List[object]:
        cells = []
        for child in list(container):
            if child.tag == f"{{{W_NS}}}tc":
                cells.append(child)
            elif child.tag in (
                f"{{{W_NS}}}sdt",
                f"{{{W_NS}}}sdtContent",
                f"{{{W_NS}}}smartTag",
                f"{{{W_NS}}}ins",
            ):
                cells.extend(self._iter_row_cells(child))
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                cells.extend(self._iter_row_cells(self._alternate_content_preferred_child(child)))
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
            return max(int(_w_attr(grid_before, "val")), 0)
        except ValueError:
            return 0

    def _parse_cell_paragraphs(self, tc_elem, paragraph_index: int, depth: int = 0):
        paragraphs = []
        for child in list(tc_elem):
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(child, paragraph_index)
                paragraph_index += 1
                if para.text.strip():
                    paragraphs.append(para)
            elif child.tag == f"{{{W_NS}}}tbl":
                if depth >= MAX_NESTED_TABLE_DEPTH:
                    paragraphs.append(Paragraph(runs=[TextRun(text="[nested table omitted: depth limit exceeded]")]))
                    continue
                table = self._parse_table(child, paragraph_index, depth + 1)
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
                    child, paragraph_index, depth
                )
                paragraphs.extend(nested_paragraphs)
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                nested_paragraphs, paragraph_index = self._parse_cell_paragraphs(
                    self._alternate_content_preferred_child(child), paragraph_index, depth
                )
                paragraphs.extend(nested_paragraphs)
        return paragraphs, paragraph_index

    def _cell_col_span(self, tc_elem) -> int:
        grid_span = tc_elem.find("w:tcPr/w:gridSpan", namespaces=NS)
        if grid_span is None:
            return 1
        try:
            return max(int(_w_attr(grid_span, "val")), 1)
        except ValueError:
            return 1

    def _cell_vmerge(self, tc_elem) -> str:
        vmerge = tc_elem.find("w:tcPr/w:vMerge", namespaces=NS)
        if vmerge is None:
            return ""
        value = _w_attr(vmerge, "val")
        return "restart" if value == "restart" else "continue"
