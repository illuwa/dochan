"""Native PPTX reader."""
import posixpath
from copy import deepcopy
import zipfile
from fractions import Fraction
from typing import Dict, List

from lxml import etree

from ..conversion import AssetRef, Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.table import Cell, Table
from ..model.equation import Equation
from .math import omml_to_latex
from .charts import (chart_elements, chart_series, text_table, xy_series_rows,
                     bubble_series_rows, mixed_series_rows, is_xy_series, chart_point_formatter, hydrate_chart_references, normalize_chart)
from .core import core_property_elements, read_core_properties
from .package import OOXMLPackage
from .pptx_styles import TextStyleResolver

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DGM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
CX_NS = "http://schemas.microsoft.com/office/drawing/2014/chartex"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": P_NS, "a": A_NS, "c": C_NS, "dgm": DGM_NS, "r": R_NS, "rel": REL_NS}
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
MAX_MEDIA_ASSET_REFS = 10000
MAX_GROUP_DEPTH = 64
MAX_SHAPE_NODES = 100000
MAX_NUMBERING_VALUE = 100000
MAX_CHART_SERIES = 1000
MAX_CHART_POINTS = 200000
MAX_CHART_OUTPUT_CELLS = 200000
MAX_CHART_REFERENCES = 1000
MAX_CHART_BYTES_TOTAL = 64 * 1024 * 1024
MAX_IMAGE_ASSET_REFS = 10000
MAX_DIAGNOSTIC_PATH_CHARS = 256


def _r_attr(elem, name: str) -> str:
    return elem.get(f"{{{R_NS}}}{name}", "")


def _resolve_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/")).replace("\\", "/")
    return posixpath.normpath(posixpath.join(base_dir, target)).replace("\\", "/")


def _int_attr(elem, name: str, default: int = 1) -> int:
    try:
        value = int(elem.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _bool_attr(elem, name: str) -> bool:
    value = elem.get(name)
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "off", "no"}


def _bounded_diagnostic_path(path: str) -> str:
    value = str(path).replace("\r", "\\r").replace("\n", "\\n")
    if len(value) <= MAX_DIAGNOSTIC_PATH_CHARS:
        return value
    return value[:MAX_DIAGNOSTIC_PATH_CHARS - 3] + "..."


class PPTXReader:
    format_name = "pptx"
    extensions = (".pptx",)

    def read(self, file_path: str) -> Document:
        try:
            return self._read_document(file_path)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
            return Document(
                source_format=self.format_name,
                errors=[f"ERR: PPTX package parse failed: {exc}"],
            )

    def _read_document(self, file_path: str) -> Document:
        doc = Document(source_format="pptx")
        self._errors = doc.errors
        self._shape_budget = MAX_SHAPE_NODES
        self._shape_limit_reported = False
        self._chart_series_remaining = MAX_CHART_SERIES
        self._chart_points_remaining = MAX_CHART_POINTS
        self._chart_output_cells_remaining = MAX_CHART_OUTPUT_CELLS
        self._chart_budget_exhausted = False
        self._chart_roots = {}
        self._chart_references_remaining = MAX_CHART_REFERENCES
        self._chart_bytes_total = 0
        self._image_asset_ids = set()
        self._image_asset_count = 0
        self._image_asset_limit_reported = False
        self._assets = []
        self._media_asset_ids = set()
        self._media_content_types = None
        self._slide_images = {}
        self._image_bytes_total = 0
        with OOXMLPackage(file_path) as package:
            self._package = package
            self._comment_authors = self._read_comment_authors(package)
            core_elements = core_property_elements(read_core_properties(package), "pptx")
            relationships = self._read_presentation_relationships(package)
            presentation = package.read_xml_part("ppt/presentation.xml")
            self._text_styles = TextStyleResolver(package, presentation, doc.errors, self._alternate_branch)
            slide_paths = self._read_slide_paths(presentation, relationships)
            for index, slide_path in enumerate(slide_paths, start=1):
                section = Section(
                    provenance=Provenance(
                        source_format="pptx",
                        slide=index,
                        path=slide_path,
                    )
                )
                if package.exists(slide_path):
                    slide_root = package.read_xml_part(slide_path)
                    slide_relationships = self._read_part_relationships(package, slide_path)
                    layout_path, layout_root = self._text_styles.related_part(slide_path, "slideLayout")
                    if layout_root is not None:
                        layout_relationships = self._read_part_relationships(package, layout_path)
                        section.elements.extend(
                            self._read_slide_elements(
                                package,
                                layout_root,
                                index,
                                layout_path,
                                layout_relationships,
                                skip_placeholder_shapes=True,
                            )
                        )
                    section.elements.extend(
                        self._read_slide_elements(package, slide_root, index, slide_path, slide_relationships)
                    )
                    notes_path = self._read_slide_notes_path(package, slide_path)
                    if notes_path and package.exists(notes_path):
                        notes_root = package.read_xml_part(notes_path)
                        notes_relationships = self._read_part_relationships(package, notes_path)
                        section.elements.extend(
                            self._read_slide_elements(package, notes_root, index, notes_path, notes_relationships)
                        )
                    for comments_path in self._read_slide_comment_paths(package, slide_path):
                        section.elements.extend(self._read_slide_comments(package, comments_path, index))
                    section.elements.extend(self._slide_images.get(index, []))
                else:
                    doc.errors.append(f"ERR: PPTX slide part not found: {slide_path}")
                if index == 1 and core_elements:
                    section.elements = core_elements + section.elements
                doc.sections.append(section)
            if not slide_paths and core_elements:
                doc.sections.append(
                    Section(
                        elements=core_elements,
                        provenance=Provenance(source_format="pptx", path="docProps/core.xml"),
                    )
                )
            doc.assets = getattr(self, "_assets", [])
            self._package = None
        return doc

    def _read_presentation_relationships(self, package: OOXMLPackage) -> Dict[str, str]:
        if not package.exists("ppt/_rels/presentation.xml.rels"):
            return {}
        root = package.read_xml_part("ppt/_rels/presentation.xml.rels")
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if rel_id and target:
                relationships[rel_id] = _resolve_target("ppt", target)
        return relationships

    def _read_slide_paths(self, presentation, relationships: Dict[str, str]) -> List[str]:
        slide_paths = []
        for slide_id in presentation.findall("p:sldIdLst/p:sldId", namespaces=NS):
            rel_id = _r_attr(slide_id, "id")
            path = relationships.get(rel_id, "")
            if path:
                slide_paths.append(path)
        return slide_paths

    def _read_part_relationships(self, package: OOXMLPackage, part_path: str) -> Dict[str, str]:
        part_dir = posixpath.dirname(part_path)
        rels_path = f"{part_dir}/_rels/{posixpath.basename(part_path)}.rels"
        if not package.exists(rels_path):
            return {}
        root = package.read_xml_part(rels_path)
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if not rel_id or not target:
                continue
            if rel.get("TargetMode") == "External":
                relationships[rel_id] = target
            else:
                relationships[rel_id] = f"#{_resolve_target(part_dir, target)}"
        return relationships

    def _read_slide_notes_path(self, package: OOXMLPackage, slide_path: str) -> str:
        return self._read_relationship_target_by_type(package, slide_path, "/notesSlide")

    def _read_slide_comment_paths(self, package: OOXMLPackage, slide_path: str) -> List[str]:
        return self._read_relationship_targets_by_type(package, slide_path, "/comments")

    def _read_relationship_target_by_type(self, package: OOXMLPackage, part_path: str, type_suffix: str) -> str:
        targets = self._read_relationship_targets_by_type(package, part_path, type_suffix)
        return targets[0] if targets else ""

    def _read_relationship_targets_by_type(self, package: OOXMLPackage, part_path: str, type_suffix: str) -> List[str]:
        part_dir = posixpath.dirname(part_path)
        rels_path = f"{part_dir}/_rels/{posixpath.basename(part_path)}.rels"
        if not package.exists(rels_path):
            return []
        root = package.read_xml_part(rels_path)
        targets = []
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_type = rel.get("Type", "")
            target = rel.get("Target", "")
            if rel_type.endswith(type_suffix) and target:
                targets.append(_resolve_target(part_dir, target))
        return targets

    def _read_comment_authors(self, package: OOXMLPackage) -> Dict[str, str]:
        if not package.exists("ppt/commentAuthors.xml"):
            return {}
        root = package.read_xml_part("ppt/commentAuthors.xml")
        authors = {}
        for author in root.findall("p:cmAuthor", namespaces=NS):
            author_id = author.get("id", "")
            name = author.get("name", "")
            if author_id and name:
                authors[author_id] = name
        return authors

    def _read_slide_comments(self, package: OOXMLPackage, comments_path: str, slide_number: int) -> List[Paragraph]:
        if not comments_path or not package.exists(comments_path):
            return []
        root = package.read_xml_part(comments_path)
        comments = []
        for comment in root.findall("p:cm", namespaces=NS):
            text_elem = comment.find("p:text", namespaces=NS)
            text = (text_elem.text or "").strip() if text_elem is not None else ""
            if not text:
                continue
            author = getattr(self, "_comment_authors", {}).get(comment.get("authorId", ""), "")
            prefix = f"{author}: " if author else ""
            provenance = Provenance(source_format="pptx", slide=slide_number, path=comments_path)
            comments.append(
                Paragraph(
                    runs=[TextRun(text=f"[comment: {prefix}{text}]", provenance=provenance)],
                    provenance=provenance,
                )
            )
        return comments

    def _read_slide_elements(
        self,
        package: OOXMLPackage,
        slide_root,
        slide_number: int,
        slide_path: str,
        relationships: Dict[str, str],
        skip_placeholder_shapes: bool = False,
    ) -> List[object]:
        positioned = []
        ordinal = [0]
        style_context = self._text_styles.context(slide_root, slide_path)
        for tree in slide_root.findall(".//p:spTree", namespaces=NS):
            self._collect_positioned_elements(
                package,
                tree,
                slide_number,
                slide_path,
                relationships,
                positioned,
                ordinal,
                skip_placeholder_shapes=skip_placeholder_shapes,
                style_context=style_context,
            )
        elements = [item[-1] for item in sorted(positioned, key=lambda item: item[:3])]
        return elements

    def _collect_positioned_elements(
        self,
        package: OOXMLPackage,
        container,
        slide_number: int,
        slide_path: str,
        relationships: Dict[str, str],
        positioned: List[object],
        ordinal_ref: List[int],
        base_x: int = 0,
        base_y: int = 0,
        scale_x: Fraction = Fraction(1, 1),
        scale_y: Fraction = Fraction(1, 1),
        skip_placeholder_shapes: bool = False,
        depth: int = 0,
        style_context=None,
    ):
        if depth > MAX_GROUP_DEPTH:
            if not self._shape_limit_reported:
                self._errors.append("ERR: PPTX group depth limit exceeded")
                self._shape_limit_reported = True
            return
        for child in list(container):
            if self._shape_budget <= 0:
                if not self._shape_limit_reported:
                    self._errors.append("ERR: PPTX shape node limit exceeded")
                    self._shape_limit_reported = True
                return
            self._shape_budget -= 1
            if child.tag == f"{{{P_NS}}}sp":
                if skip_placeholder_shapes and self._is_placeholder_shape(child):
                    ordinal_ref[0] += 1
                    continue
                x, y = self._element_offset(child)
                absolute_x = base_x + x * scale_x
                absolute_y = base_y + y * scale_y
                ordinal = ordinal_ref[0]
                shape_link = self._shape_hyperlink_target(child, relationships)
                heading_level = self._shape_heading_level(child)
                added_text = False
                bullet_counts = {}
                style_layers = self._text_styles.shape_layers(child, style_context)
                for p_elem in child.findall("p:txBody/a:p", namespaces=NS):
                    blocks = self._paragraph_blocks(
                        p_elem,
                        slide_number,
                        slide_path,
                        relationships,
                        default_hyperlink=shape_link,
                        heading_level=heading_level,
                        bullet_counts=bullet_counts,
                        character_defaults=self._text_styles.paragraph_defaults(style_layers, p_elem),
                    )
                    for block in blocks:
                        positioned.append((absolute_y, absolute_x, ordinal, block))
                        added_text = True
                for reference in self._media_references(child, relationships, slide_number):
                    positioned.append((absolute_y, absolute_x, ordinal,
                                       self._text_paragraph(reference, slide_number, slide_path)))
                    added_text = True
                if not added_text:
                    alt_text = self._shape_alt_text(child)
                    if alt_text:
                        positioned.append(
                            (
                                absolute_y,
                                absolute_x,
                                ordinal,
                                self._text_paragraph(alt_text, slide_number, slide_path),
                            )
                        )
                ordinal_ref[0] += 1
            elif child.tag == f"{{{P_NS}}}pic":
                x, y = self._element_offset(child)
                absolute_x = base_x + x * scale_x
                absolute_y = base_y + y * scale_y
                ordinal = ordinal_ref[0]
                media_references = self._media_references(child, relationships, slide_number)
                for reference in media_references:
                    positioned.append((absolute_y, absolute_x, ordinal,
                                       self._text_paragraph(reference, slide_number, slide_path)))
                image_reference = self._picture_reference(child, relationships, slide_number)
                if image_reference:
                    positioned.append(
                        (
                            absolute_y,
                            absolute_x,
                            ordinal,
                            self._text_paragraph(image_reference, slide_number, slide_path),
                        )
                    )
                elif not media_references:
                    alt_text = self._shape_alt_text(child)
                    if alt_text:
                        positioned.append(
                            (
                                absolute_y,
                                absolute_x,
                                ordinal,
                                self._text_paragraph(alt_text, slide_number, slide_path),
                            )
                        )
                ordinal_ref[0] += 1
            elif child.tag == f"{{{P_NS}}}graphicFrame":
                x, y = self._element_offset(child)
                absolute_x = base_x + x * scale_x
                absolute_y = base_y + y * scale_y
                ordinal = ordinal_ref[0]
                for table_elem in child.findall(".//a:tbl", namespaces=NS):
                    table = self._parse_table(table_elem, slide_number, slide_path, relationships)
                    if table.rows:
                        positioned.append((absolute_y, absolute_x, ordinal, table))
                for chart_elem in self._graphic_chart_references(child):
                    for offset, element in enumerate(
                        self._parse_chart(chart_elem, package, slide_number, slide_path, relationships)
                    ):
                        positioned.append((absolute_y, absolute_x, ordinal + offset / 1000, element))
                for offset, element in enumerate(
                    self._parse_smartart(child, package, slide_number, relationships)
                ):
                    positioned.append((absolute_y, absolute_x, ordinal + offset / 1000, element))
                ordinal_ref[0] += 1
            elif child.tag == f"{{{MC_NS}}}AlternateContent":
                branch = self._alternate_branch(child)
                if branch is not None:
                    self._collect_positioned_elements(
                        package, branch, slide_number, slide_path, relationships,
                        positioned, ordinal_ref, base_x, base_y, scale_x, scale_y,
                        skip_placeholder_shapes, depth + 1,
                        style_context,
                    )
            elif child.tag == f"{{{P_NS}}}grpSp":
                transform = self._group_transform(child)
                self._collect_positioned_elements(
                    package,
                    child,
                    slide_number,
                    slide_path,
                    relationships,
                    positioned,
                    ordinal_ref,
                    base_x=base_x + scale_x * transform["base_x"],
                    base_y=base_y + scale_y * transform["base_y"],
                    scale_x=scale_x * transform["scale_x"],
                    scale_y=scale_y * transform["scale_y"],
                    skip_placeholder_shapes=skip_placeholder_shapes,
                    depth=depth + 1,
                    style_context=style_context,
                )

    def _alternate_branch(self, elem):
        supported = {P_NS, A_NS, C_NS, CX_NS, DGM_NS, M_NS, A14_NS, P14_NS,
                     "http://schemas.microsoft.com/office/drawing/2015/9/8/chartex"}
        for choice in elem.findall("{%s}Choice" % MC_NS):
            prefixes = choice.get("Requires", "").split()
            if prefixes and all(choice.nsmap.get(prefix) in supported for prefix in prefixes):
                return choice
        return elem.find("{%s}Fallback" % MC_NS)

    def _graphic_chart_references(self, container, depth=0):
        if depth > MAX_GROUP_DEPTH:
            warning = "WARN: PPTX graphic wrapper depth limit exceeded"
            if warning not in self._errors:
                self._errors.append(warning)
            return
        for child in container:
            if child.tag in {"{%s}chart" % C_NS, "{%s}chart" % CX_NS}:
                yield child
            elif child.tag == "{%s}AlternateContent" % MC_NS:
                branch = self._alternate_branch(child)
                if branch is not None:
                    yield from self._graphic_chart_references(branch, depth + 1)
            else:
                yield from self._graphic_chart_references(child, depth + 1)

    def _paragraph_blocks(self, p_elem, slide_number, slide_path, relationships, **kwargs):
        """OMML 을 문단의 앞뒤 텍스트 사이에 기존 Equation 모델로 보존한다."""
        blocks = []
        chunk = etree.Element(p_elem.tag)

        def flush():
            if not any(child.tag != "{%s}pPr" % A_NS for child in chunk):
                return
            para = self._parse_paragraph(chunk, slide_number, slide_path, relationships, **kwargs)
            if para.text.strip():
                blocks.append(para)
            chunk.clear()

        def visit(container, depth=0):
            if depth > MAX_GROUP_DEPTH:
                warning = "WARN: PPTX paragraph wrapper depth limit exceeded"
                if warning not in self._errors:
                    self._errors.append(warning)
                return
            for child in container:
                if child.tag == "{%s}pPr" % A_NS:
                    continue
                if child.tag == "{%s}AlternateContent" % MC_NS:
                    branch = self._alternate_branch(child)
                    if branch is not None:
                        visit(branch, depth + 1)
                elif child.tag in {"{%s}m" % A14_NS, "{%s}oMath" % M_NS,
                                   "{%s}oMathPara" % M_NS}:
                    flush()
                    latex = omml_to_latex(child)
                    if latex.strip():
                        blocks.append(Equation(script="".join(child.itertext()), latex_override=latex))
                else:
                    chunk.append(deepcopy(child))

        visit(p_elem)
        flush()
        # 번호는 텍스트 조각이 아니라 원본 문단당 한 번만 소비한다.
        prefix = self._bullet_prefix(p_elem, kwargs.get("bullet_counts"))
        if prefix and blocks:
            if isinstance(blocks[0], Paragraph):
                blocks[0].runs.insert(0, TextRun(text=prefix + " ",
                                               provenance=blocks[0].provenance))
            else:
                blocks.insert(0, self._text_paragraph(prefix, slide_number, slide_path))
        return blocks

    def _media_references(self, shape, relationships, slide_number):
        """미디어의 호환용 이중 관계는 대상 경로 기준으로 한 번만 낸다."""
        tags = {"{%s}videoFile" % A_NS: "video", "{%s}videoFile" % P_NS: "video",
                "{%s}audioFile" % A_NS: "audio", "{%s}audioFile" % P_NS: "audio",
                "{%s}media" % P14_NS: "media"}
        nodes = []
        for node in shape.iter():
            if node.tag in tags:
                if len(nodes) >= MAX_MEDIA_ASSET_REFS:
                    warning = "WARN: PPTX media reference limit exceeded"
                    if warning not in self._errors:
                        self._errors.append(warning)
                    break
                nodes.append(node)
        kinds = {relationships.get(_r_attr(n, "link") or _r_attr(n, "embed"), ""): tags[n.tag]
                 for n in nodes if tags[n.tag] != "media"}
        seen = set()
        references = []
        for node in nodes:
            rel_id = _r_attr(node, "embed") or _r_attr(node, "link")
            target = relationships.get(rel_id, "")
            if not target or target in seen:
                continue
            seen.add(target)
            source_path = target.lstrip("#")
            kind = kinds.get(target, tags[node.tag])
            label = self._shape_label(shape) or kind
            references.append("[%s](%s)" % (label, source_path))
            if not target.startswith("#") or source_path in self._media_asset_ids:
                continue
            if len(self._media_asset_ids) >= MAX_MEDIA_ASSET_REFS:
                warning = "WARN: PPTX media asset reference limit exceeded"
                if warning not in self._errors:
                    self._errors.append(warning)
                continue
            try:
                missing = not self._package.exists(source_path)
            except ValueError:
                self._errors.append("WARN: PPTX unsafe media target: " + _bounded_diagnostic_path(source_path))
                continue
            self._media_asset_ids.add(source_path)
            content_type = self._media_content_type(source_path)
            if kind == "media":
                kind = content_type.split("/", 1)[0] if content_type.startswith(("audio/", "video/")) else "media"
            self._assets.append(AssetRef(
                id=rel_id, source_path=source_path, filename=posixpath.basename(source_path),
                content_type=content_type,
                metadata={"kind": kind, "label": label, "missing": missing,
                          "source_format": "pptx", "slide": slide_number},
            ))
            if missing:
                self._errors.append("WARN: PPTX media part not found: " + _bounded_diagnostic_path(source_path))
        return references

    def _media_content_type(self, source_path):
        package = self._package
        extension = posixpath.splitext(source_path)[1].lstrip(".").lower()
        if self._media_content_types is None:
            defaults, overrides = {}, {}
            self._media_content_types = (defaults, overrides)
            if package.exists("[Content_Types].xml"):
                try:
                    root = package.read_xml_part("[Content_Types].xml")
                    for node in root:
                        content_type = node.get("ContentType", "application/octet-stream")
                        if node.get("PartName"):
                            overrides[node.get("PartName").lstrip("/")] = content_type
                        elif node.get("Extension"):
                            defaults[node.get("Extension").lower()] = content_type
                except (ValueError, etree.XMLSyntaxError):
                    self._errors.append("WARN: PPTX media content types could not be read")
        defaults, overrides = self._media_content_types
        if source_path in overrides:
            return overrides[source_path]
        if extension in defaults:
            return defaults[extension]
        return {"mp4": "video/mp4", "mp3": "audio/mpeg", "wav": "audio/wav",
                "m4a": "audio/mp4", "wmv": "video/x-ms-wmv", "avi": "video/x-msvideo"}.get(
                    extension, "application/octet-stream")

    def _picture_reference(self, pic_elem, relationships: Dict[str, str], slide_number: int) -> str:
        blip = pic_elem.find(".//a:blip", namespaces=NS)
        if blip is None:
            return ""
        rel_id = _r_attr(blip, "embed") or _r_attr(blip, "link")
        target = relationships.get(rel_id, "")
        if not target:
            return ""
        label = self._shape_label(pic_elem)
        source_path = target.lstrip("#")
        if target.startswith("#"):  # 내부(임베드) 이미지 — 바이트 추출 + 자산 기록
            self._record_image_asset(rel_id, source_path, label, slide_number)
            self._extract_image_element(source_path, label, slide_number)
        return f"![{label or 'image'}]({source_path})"

    def _extract_image_element(self, target: str, label: str, slide_number: int):
        """임베드 이미지 바이트를 읽어 슬라이드별 Image 요소로 보관 (OCR 용)."""
        from ..model.image import Image
        _MAX_IMAGE_BYTES_TOTAL = 100 * 1024 * 1024
        if self._image_bytes_total >= _MAX_IMAGE_BYTES_TOTAL:
            return
        package = getattr(self, "_package", None)
        if package is None:
            return
        try:
            data = package.read_part(target)
        except Exception:
            return
        if not data:
            return
        self._image_bytes_total += len(data)
        ext = posixpath.splitext(target)[1].lstrip(".").lower()
        self._slide_images.setdefault(slide_number, []).append(
            Image(
                filename=posixpath.basename(target),
                image_data=data,
                alt_text=label,
                image_format=ext,
                provenance=Provenance(source_format="pptx", slide=slide_number, path=target),
            )
        )

    def _record_image_asset(self, rel_id: str, target: str, label: str, slide_number: int):
        if not rel_id or not target:
            return
        key = ("image", target)
        if key in getattr(self, "_image_asset_ids", set()):
            return
        if getattr(self, "_image_asset_count", 0) >= MAX_IMAGE_ASSET_REFS:
            if not getattr(self, "_image_asset_limit_reported", False):
                self._errors.append(
                    "WARN: PPTX image asset reference limit exceeded "
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
                    "source_format": "pptx",
                    "slide": slide_number,
                },
            )
        )
        if missing:
            warning = (
                "WARN: PPTX image part not found: "
                f"{_bounded_diagnostic_path(target)}"
            )
            if warning not in self._errors:
                self._errors.append(warning)

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

    def _shape_label(self, shape_elem) -> str:
        c_nv_pr = shape_elem.find("p:nvSpPr/p:cNvPr", namespaces=NS)
        if c_nv_pr is None:
            c_nv_pr = shape_elem.find("p:nvPicPr/p:cNvPr", namespaces=NS)
        if c_nv_pr is None:
            return ""
        return " ".join(
            part
            for part in (c_nv_pr.get("title", ""), c_nv_pr.get("descr", ""), c_nv_pr.get("name", ""))
            if part
        ).strip()

    def _is_placeholder_shape(self, shape_elem) -> bool:
        return shape_elem.find("p:nvSpPr/p:nvPr/p:ph", namespaces=NS) is not None

    def _shape_heading_level(self, shape_elem) -> int:
        placeholder = shape_elem.find("p:nvSpPr/p:nvPr/p:ph", namespaces=NS)
        if placeholder is None:
            return 0
        placeholder_type = placeholder.get("type", "")
        if placeholder_type in {"title", "ctrTitle"}:
            return 1
        return 0

    def _shape_hyperlink_target(self, shape_elem, relationships: Dict[str, str]) -> str:
        hyperlink = shape_elem.find("p:nvSpPr/p:cNvPr/a:hlinkClick", namespaces=NS)
        return relationships.get(_r_attr(hyperlink, "id"), "") if hyperlink is not None else ""

    def _shape_alt_text(self, shape_elem) -> str:
        c_nv_pr = shape_elem.find("p:nvSpPr/p:cNvPr", namespaces=NS)
        if c_nv_pr is None:
            c_nv_pr = shape_elem.find("p:nvPicPr/p:cNvPr", namespaces=NS)
        if c_nv_pr is None:
            return ""
        return " ".join(part for part in (c_nv_pr.get("title", ""), c_nv_pr.get("descr", "")) if part).strip()

    def _text_paragraph(self, text: str, slide_number: int, slide_path: str) -> Paragraph:
        return Paragraph(
            runs=[TextRun(text=text)],
            provenance=Provenance(
                source_format="pptx",
                slide=slide_number,
                path=slide_path,
            ),
        )

    def _element_offset(self, elem):
        off = None
        for path in (
            "p:spPr/a:xfrm/a:off",
            "p:grpSpPr/a:xfrm/a:off",
            "p:xfrm/a:off",
            ".//a:xfrm/a:off",
        ):
            off = elem.find(path, namespaces=NS)
            if off is not None:
                break
        if off is None:
            return (0, 0)
        return self._offset_xy(off)

    def _offset_xy(self, off):
        try:
            y = int(off.get("y", "0"))
        except ValueError:
            y = 0
        try:
            x = int(off.get("x", "0"))
        except ValueError:
            x = 0
        return (x, y)

    def _extent_xy(self, ext):
        try:
            cy = int(ext.get("cy", "1"))
        except ValueError:
            cy = 1
        try:
            cx = int(ext.get("cx", "1"))
        except ValueError:
            cx = 1
        return (max(cx, 1), max(cy, 1))

    def _group_transform(self, group_elem):
        xfrm = group_elem.find("p:grpSpPr/a:xfrm", namespaces=NS)
        if xfrm is None:
            x, y = self._element_offset(group_elem)
            return {
                "base_x": Fraction(x, 1),
                "base_y": Fraction(y, 1),
                "scale_x": Fraction(1, 1),
                "scale_y": Fraction(1, 1),
            }
        off = xfrm.find("a:off", namespaces=NS)
        child_off = xfrm.find("a:chOff", namespaces=NS)
        ext = xfrm.find("a:ext", namespaces=NS)
        child_ext = xfrm.find("a:chExt", namespaces=NS)
        x, y = self._offset_xy(off) if off is not None else (0, 0)
        child_x, child_y = self._offset_xy(child_off) if child_off is not None else (0, 0)
        ext_x, ext_y = self._extent_xy(ext) if ext is not None else (1, 1)
        child_ext_x, child_ext_y = self._extent_xy(child_ext) if child_ext is not None else (ext_x, ext_y)
        scale_x = Fraction(ext_x, child_ext_x)
        scale_y = Fraction(ext_y, child_ext_y)
        return {
            "base_x": Fraction(x, 1) - Fraction(child_x, 1) * scale_x,
            "base_y": Fraction(y, 1) - Fraction(child_y, 1) * scale_y,
            "scale_x": scale_x,
            "scale_y": scale_y,
        }

    def _parse_paragraph(
        self,
        p_elem,
        slide_number: int,
        slide_path: str,
        relationships: Dict[str, str],
        default_hyperlink: str = "",
        heading_level: int = 0,
        bullet_counts: Dict[tuple, int] = None,
        character_defaults=None,
    ) -> Paragraph:
        runs = []
        has_run_hyperlink = False
        for child in p_elem:
            if child.tag == f"{{{A_NS}}}r":
                text = "".join(t.text or "" for t in child.findall("a:t", namespaces=NS))
                if text:
                    r_pr = child.find("a:rPr", namespaces=NS)
                    hyperlink = r_pr.find("a:hlinkClick", namespaces=NS) if r_pr is not None else None
                    target = relationships.get(_r_attr(hyperlink, "id"), "") if hyperlink is not None else ""
                    if target:
                        text = f"{text} <{target}>"
                        has_run_hyperlink = True
                    run = TextRun(text=text)
                    if r_pr is not None:
                        run.bold = r_pr.get("b") in {"1", "true"}
                        run.italic = r_pr.get("i") in {"1", "true"}
                        run.underline = bool(r_pr.get("u") and r_pr.get("u") != "none")
                        run.strikeout = bool(r_pr.get("strike") and r_pr.get("strike") != "noStrike")
                    if character_defaults is not None:
                        self._text_styles.apply(run, r_pr, character_defaults)
                    runs.append(run)
            elif child.tag == f"{{{A_NS}}}br":
                run = TextRun(text="\n")
                if character_defaults is not None:
                    self._text_styles.apply(run, child.find("a:rPr", namespaces=NS), character_defaults)
                runs.append(run)
            elif child.tag == f"{{{A_NS}}}fld":
                text = "".join(t.text or "" for t in child.findall("a:t", namespaces=NS))
                if text:
                    run = TextRun(text=text)
                    if character_defaults is not None:
                        self._text_styles.apply(run, child.find("a:rPr", namespaces=NS), character_defaults)
                    runs.append(run)
        if default_hyperlink and runs and not has_run_hyperlink:
            runs[-1].text = f"{runs[-1].text} <{default_hyperlink}>"
        bullet_prefix = self._bullet_prefix(p_elem, bullet_counts)
        if bullet_prefix and runs:
            runs.insert(0, TextRun(text=f"{bullet_prefix} "))
        provenance = Provenance(
            source_format="pptx",
            slide=slide_number,
            path=slide_path,
        )
        for run in runs:
            if run.provenance is None:
                run.provenance = provenance
        return Paragraph(
            runs=runs,
            heading_level=heading_level,
            provenance=provenance,
        )

    def _bullet_prefix(self, p_elem, bullet_counts: Dict[tuple, int] = None) -> str:
        p_pr = p_elem.find("a:pPr", namespaces=NS)
        if p_pr is None:
            return ""
        bullet = p_pr.find("a:buChar", namespaces=NS)
        if bullet is not None:
            return bullet.get("char", "") or "•"
        auto_number = p_pr.find("a:buAutoNum", namespaces=NS)
        if auto_number is None:
            return ""
        numbering_type = auto_number.get("type", "arabicPeriod")
        level = p_pr.get("lvl", "0")
        count = self._auto_number_count(auto_number, bullet_counts, level, numbering_type)
        return self._auto_number_marker(numbering_type, count)

    def _auto_number_count(
        self,
        auto_number,
        bullet_counts: Dict[tuple, int] = None,
        level: str = "0",
        numbering_type: str = "arabicPeriod",
    ) -> int:
        if bullet_counts is None:
            bullet_counts = {}
        key = (level, numbering_type)
        start_at = auto_number.get("startAt")
        if start_at:
            count = self._validated_numbering_value(
                start_at,
                "start value",
            )
        else:
            count = bullet_counts.get(key, 1)
        if not 1 <= count <= MAX_NUMBERING_VALUE:
            self._record_numbering_limit("list counter")
            count = 1
        bullet_counts[key] = min(count + 1, MAX_NUMBERING_VALUE + 1)
        return count

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
        error = f"ERR: PPTX numbering value limit exceeded ({context})"
        if error not in self._errors:
            self._errors.append(error)

    def _auto_number_marker(self, numbering_type: str, count: int) -> str:
        if not 1 <= count <= MAX_NUMBERING_VALUE:
            self._record_numbering_limit("generated marker")
            return ""
        if numbering_type.endswith("ParenR"):
            suffix = ")"
        else:
            suffix = "."
        if numbering_type.startswith("alphaLc"):
            marker = self._letter_marker(count)
        elif numbering_type.startswith("alphaUc"):
            marker = self._letter_marker(count).upper()
        elif numbering_type.startswith("romanLc"):
            marker = self._roman_marker(count).lower()
        elif numbering_type.startswith("romanUc"):
            marker = self._roman_marker(count)
        else:
            marker = str(count)
        return f"{marker}{suffix}"

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

    def _parse_table(
        self,
        table_elem,
        slide_number: int,
        slide_path: str,
        relationships: Dict[str, str],
    ) -> Table:
        rows = []
        for row_idx, tr_elem in enumerate(table_elem.findall("a:tr", namespaces=NS)):
            row = []
            for col_idx, tc_elem in enumerate(tr_elem.findall("a:tc", namespaces=NS)):
                paragraphs = []
                bullet_counts = {}
                for p_elem in tc_elem.findall("a:txBody/a:p", namespaces=NS):
                    paragraphs.extend(self._paragraph_blocks(
                        p_elem, slide_number, slide_path, relationships,
                        bullet_counts=bullet_counts,
                    ))
                row.append(
                    Cell(
                        paragraphs=paragraphs,
                        row_span=(
                            0 if _bool_attr(tc_elem, "vMerge")
                            else _int_attr(tc_elem, "rowSpan")
                        ),
                        col_span=(
                            0 if _bool_attr(tc_elem, "hMerge")
                            else _int_attr(tc_elem, "gridSpan")
                        ),
                        provenance=Provenance(
                            source_format="pptx",
                            slide=slide_number,
                            cell=f"R{row_idx + 1}C{col_idx + 1}",
                            path=slide_path,
                        ),
                    )
                )
            rows.append(row)
        return Table(rows=rows)

    def _parse_chart(
        self,
        chart_elem,
        package: OOXMLPackage,
        slide_number: int,
        slide_path: str,
        relationships: Dict[str, str],
    ) -> List[object]:
        chart_path = relationships.get(_r_attr(chart_elem, "id"), "").lstrip("#")
        if not chart_path:
            return []
        if self._chart_references_remaining <= 0:
            warning = "WARN: PPTX chart reference limit exceeded"
            if warning not in self._errors:
                self._errors.append(warning)
            return []
        self._chart_references_remaining -= 1
        try:
            if not package.exists(chart_path):
                self._errors.append("WARN: PPTX chart part not found: " + _bounded_diagnostic_path(chart_path))
                return []
            roots = self._chart_roots
            if chart_path not in roots:
                # 실패한 파트도 캐시하여 반복 참조가 같은 압축/파싱을 반복하지 않는다.
                roots[chart_path] = None
                size = package.part_size(chart_path)
                if self._chart_bytes_total + size > MAX_CHART_BYTES_TOTAL:
                    self._errors.append("WARN: PPTX chart byte limit exceeded")
                    return []
                self._chart_bytes_total += size
                chart_root = normalize_chart(package.read_xml_part(chart_path), self._errors)
                hydrate_chart_references(chart_root, package, chart_path, self._errors)
                roots[chart_path] = chart_root
            chart_root = roots[chart_path]
            if chart_root is None:
                return []
            return chart_elements(
                chart_root,
                self._chart_series_table(chart_root),
                lambda text: self._text_paragraph(text, slide_number, chart_path),
            )
        except (KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
            self._errors.append(
                "WARN: PPTX chart could not be read: %s (%s)" %
                (_bounded_diagnostic_path(chart_path), type(exc).__name__)
            )
            return []

    def _parse_smartart(
        self,
        graphic_frame,
        package: OOXMLPackage,
        slide_number: int,
        relationships: Dict[str, str],
    ) -> List[Paragraph]:
        elements = []
        seen_paths = set()
        for rel_ids in graphic_frame.findall(".//dgm:relIds", namespaces=NS):
            diagram_path = relationships.get(_r_attr(rel_ids, "dm"), "").lstrip("#")
            if not diagram_path or diagram_path in seen_paths or not package.exists(diagram_path):
                continue
            seen_paths.add(diagram_path)
            diagram_root = package.read_xml_part(diagram_path)
            for text in self._diagram_texts(diagram_root):
                elements.append(self._text_paragraph(text, slide_number, diagram_path))
        return elements

    def _diagram_texts(self, diagram_root) -> List[str]:
        texts = []
        for text_container in diagram_root.findall(".//dgm:t", namespaces=NS):
            paragraph_texts = []
            for p_elem in text_container.findall("a:p", namespaces=NS):
                text = "".join(node.text or "" for node in p_elem.findall(".//a:t", namespaces=NS)).strip()
                if text:
                    paragraph_texts.append(text)
            if paragraph_texts:
                texts.append("\n".join(paragraph_texts))
        return texts

    def _chart_series_table(self, chart_root) -> Table:
        if getattr(self, "_chart_budget_exhausted", False):
            return Table()
        series_items = []
        implicit_x = []
        sizes = []
        xy_flags = []
        xy = False
        for series in chart_series(chart_root):
            if not self._reserve_chart_resource(
                "_chart_series_remaining",
                1,
                MAX_CHART_SERIES,
                "series",
            ):
                return Table()
            series_name = self._chart_series_name(series)
            # 분산형·거품형은 c:cat/c:val 대신 c:xVal/c:yVal 에 값을 둔다.
            has_x_values = series.find("c:xVal", namespaces=NS) is not None
            xy_flags.append(is_xy_series(series))
            xy = xy or xy_flags[-1]
            implicit_x.append(not has_x_values and series.find("c:cat", namespaces=NS) is None)
            categories = self._chart_points(series, "c:cat") or self._chart_points(series, "c:xVal")
            values = self._chart_points(series, "c:val") or self._chart_points(series, "c:yVal")
            sizes.append(self._chart_points(series, "c:bubbleSize"))
            if getattr(self, "_chart_budget_exhausted", False):
                return Table()
            series_items.append((series_name, categories, values))
        if not series_items:
            return Table()

        if not any(values for _, _, values in series_items) and not any(sizes):
            return Table()
        long_rows = mixed_series_rows(series_items, xy_flags, sizes, implicit_x)
        if long_rows is None:
            long_rows = bubble_series_rows(series_items, sizes, implicit_x)
        if long_rows is None:
            long_rows = xy_series_rows(series_items, xy, implicit_x)
        if long_rows is not None:
            if not self._reserve_chart_resource(
                "_chart_output_cells_remaining",
                len(long_rows[0]) * len(long_rows),
                MAX_CHART_OUTPUT_CELLS,
                "output cell",
            ):
                return Table()
            return text_table(long_rows)

        category_labels = {}
        indexes = set()
        for _, categories, values in series_items:
            indexes.update(categories)
            indexes.update(values)
            for index, category in categories.items():
                category_labels.setdefault(index, category)

        if not indexes:
            return Table()
        output_cells = (len(indexes) + 1) * (len(series_items) + 1)
        if not self._reserve_chart_resource(
            "_chart_output_cells_remaining",
            output_cells,
            MAX_CHART_OUTPUT_CELLS,
            "output cell",
        ):
            return Table()

        rows = [
            [
                Cell(paragraphs=[Paragraph(runs=[TextRun(text="Category")])]),
                *[
                    Cell(paragraphs=[Paragraph(runs=[TextRun(text=series_name or f"Series {index + 1}")])])
                    for index, (series_name, _, _) in enumerate(series_items)
                ],
            ]
        ]
        for point_index in sorted(indexes):
            rows.append(
                [
                    Cell(paragraphs=[Paragraph(runs=[TextRun(text=category_labels.get(point_index, ""))])]),
                    *[
                        Cell(paragraphs=[Paragraph(runs=[TextRun(text=values.get(point_index, ""))])])
                        for _, _, values in series_items
                    ],
                ]
            )
        return Table(rows=rows)

    def _chart_series_name(self, series) -> str:
        tx = series.find("c:tx", namespaces=NS)
        if tx is None:
            return ""
        text = " ".join(
            node.text or ""
            for node in tx.findall(".//c:v", namespaces=NS)
            if node.text
        ).strip()
        if text:
            return text
        return " ".join(
            node.text or ""
            for node in tx.findall(".//a:t", namespaces=NS)
            if node.text
        ).strip()

    def _chart_points(self, series, parent_path: str) -> Dict[int, str]:
        points = {}
        parent = series.find(parent_path, namespaces=NS)
        if parent is None:
            return points
        format_point = chart_point_formatter(parent)
        for point in parent.iterfind(".//c:pt", namespaces=NS):
            if not self._reserve_chart_resource(
                "_chart_points_remaining",
                1,
                MAX_CHART_POINTS,
                "point",
            ):
                return {}
            try:
                index = int(point.get("idx", "0"))
            except ValueError:
                index = len(points)
            value = "".join(node.text or "" for node in point.findall("c:v", namespaces=NS)).strip()
            if value:
                points[index] = format_point(point, value)
        return points

    def _reserve_chart_resource(
        self,
        remaining_attribute: str,
        amount: int,
        limit: int,
        label: str,
    ) -> bool:
        if getattr(self, "_chart_budget_exhausted", False):
            return False
        remaining = getattr(self, remaining_attribute, limit)
        if amount < 0 or amount > remaining:
            error = f"ERR: PPTX chart {label} limit exceeded"
            errors = getattr(self, "_errors", None)
            if errors is not None and error not in errors:
                errors.append(error)
            self._chart_budget_exhausted = True
            return False
        setattr(self, remaining_attribute, remaining - amount)
        return True
