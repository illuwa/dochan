"""Native XLSX reader."""
from datetime import datetime, timedelta
from dataclasses import dataclass
from fractions import Fraction
import posixpath
import re
from typing import Dict, List, Tuple

from lxml import etree

from ..conversion import AssetRef, Provenance
from ..model.header_footer import HeaderFooter
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.table import Cell, Table
from .core import core_property_elements, read_core_properties
from .package import MAX_PART_SIZE, OOXMLPackage

S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
STRICT_S_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
STRICT_R_NS = "http://purl.oclc.org/ooxml/officeDocument/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
NS = {"s": S_NS, "r": R_NS, "rel": REL_NS, "xdr": XDR_NS, "a": A_NS, "c": C_NS, "v": V_NS, "o": O_NS}
BUILTIN_NUM_FORMATS = {
    0: "General",
    1: "0",
    2: "0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    12: "# ?/?",
    13: "# ??/??",
    14: "m/d/yy",
    15: "d-mmm-yy",
    16: "d-mmm",
    17: "mmm-yy",
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: "h:mm",
    21: "h:mm:ss",
    22: "m/d/yy h:mm",
}
STREAMING_ROW_LIMIT = 200
STREAMING_CELL_LIMIT = 5000


@dataclass(frozen=True)
class _FormatMetadata:
    kind: str = ""
    decimals: int = 0
    thousands: bool = False
    currency_symbol: str = ""
    negative_parentheses: bool = False
    pattern: str = ""
    literal_prefix: str = ""
    literal_suffix: str = ""
    denominator_limit: int = 0


def _attr(elem, namespace: str, name: str) -> str:
    return elem.get(f"{{{namespace}}}{name}", "")


def _namespaces(elem) -> Dict[str, str]:
    namespace = S_NS
    if elem is not None and elem.tag.startswith("{"):
        namespace = elem.tag[1:].split("}", 1)[0]
    return {"s": namespace, "r": R_NS, "rel": REL_NS}


def _rel_attr(elem, name: str) -> str:
    return _attr(elem, R_NS, name) or _attr(elem, STRICT_R_NS, name)


def _local_name(elem) -> str:
    return elem.tag.rsplit("}", 1)[-1]


def _column_index(cell_ref: str) -> int:
    value = 0
    for char in cell_ref.upper():
        if not ("A" <= char <= "Z"):
            break
        value = value * 26 + (ord(char) - ord("A") + 1)
    if value == 0:
        return 0
    return value - 1


def _column_name(index: int) -> str:
    index = max(index, 0)
    name = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _row_index(cell_ref: str) -> int:
    match = re.search(r"(\d+)", cell_ref)
    if not match:
        return 0
    return max(int(match.group(1)) - 1, 0)


def _resolve_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/")).replace("\\", "/")
    return posixpath.normpath(posixpath.join(base_dir, target)).replace("\\", "/")


class XLSXReader:
    format_name = "xlsx"
    extensions = (".xlsx",)

    def read(self, file_path: str) -> Document:
        doc = Document(source_format="xlsx")
        self._image_asset_ids = set()
        self._assets = []
        with OOXMLPackage(file_path) as package:
            self._package = package
            core_elements = core_property_elements(read_core_properties(package), "xlsx")
            shared_strings = self._read_shared_strings(package)
            styles = self._read_styles(package)
            relationships = self._read_workbook_relationships(package)
            workbook = package.read_xml_part("xl/workbook.xml")
            defined_name_elements = self._defined_name_elements(workbook)
            sheets = self._read_sheets(workbook, relationships)
            for index, (sheet_name, sheet_path) in enumerate(sheets, start=1):
                section = Section(
                    provenance=Provenance(
                        source_format="xlsx",
                        sheet=sheet_name,
                        path=sheet_path,
                    )
                )
                if package.exists(sheet_path):
                    if package.part_size(sheet_path) > MAX_PART_SIZE:
                        table = self._read_large_sheet_table(package, sheet_path, sheet_name, shared_strings, styles)
                        if table.rows:
                            section.elements.append(table)
                    else:
                        sheet_root = package.read_xml_part(sheet_path)
                        headers, footers = self._read_sheet_headers_footers(sheet_root)
                        section.elements.extend(headers)
                        table = self._read_sheet_table(package, sheet_root, sheet_path, sheet_name, shared_strings, styles)
                        if table.rows:
                            section.elements.append(table)
                        section.elements.extend(self._read_sheet_drawings(package, sheet_root, sheet_path, sheet_name))
                        section.elements.extend(footers)
                else:
                    doc.errors.append(f"ERR: XLSX sheet part not found: {sheet_path}")
                if index == 1 and core_elements:
                    section.elements = core_elements + section.elements
                if index == 1 and defined_name_elements:
                    insert_at = len(core_elements) if core_elements else 0
                    section.elements[insert_at:insert_at] = defined_name_elements
                doc.sections.append(section)
            if not sheets and core_elements:
                doc.sections.append(
                    Section(
                        elements=core_elements,
                        provenance=Provenance(source_format="xlsx", path="docProps/core.xml"),
                    )
                )
            doc.assets = getattr(self, "_assets", [])
            self._package = None
        return doc

    def _defined_name_elements(self, workbook) -> List[Paragraph]:
        elements = []
        for defined_name in workbook.findall("s:definedNames/s:definedName", namespaces=_namespaces(workbook)):
            name = self._defined_name_label(defined_name.get("name", ""))
            target = (defined_name.text or "").strip()
            if not name or not target:
                continue
            elements.append(
                Paragraph(
                    runs=[TextRun(text=f"Defined name: {name} = {target}")],
                    provenance=Provenance(source_format="xlsx", path="xl/workbook.xml"),
                )
            )
        return elements

    def _defined_name_label(self, name: str) -> str:
        if name.startswith("_xlnm."):
            return name.split(".", 1)[1]
        return name

    def _read_shared_strings(self, package: OOXMLPackage) -> List[str]:
        if not package.exists("xl/sharedStrings.xml"):
            return []
        root = package.read_xml_part("xl/sharedStrings.xml")
        values = []
        for si in root.findall("s:si", namespaces=_namespaces(root)):
            values.append(self._text_runs(si))
        return values

    def _read_styles(self, package: OOXMLPackage) -> List[str]:
        if not package.exists("xl/styles.xml"):
            return []
        root = package.read_xml_part("xl/styles.xml")
        custom_formats: Dict[int, str] = {}
        for num_fmt in root.findall("s:numFmts/s:numFmt", namespaces=_namespaces(root)):
            try:
                num_fmt_id = int(num_fmt.get("numFmtId", ""))
            except ValueError:
                continue
            custom_formats[num_fmt_id] = num_fmt.get("formatCode", "")

        styles = []
        for xf in root.findall("s:cellXfs/s:xf", namespaces=_namespaces(root)):
            try:
                num_fmt_id = int(xf.get("numFmtId", "0"))
            except ValueError:
                num_fmt_id = 0
            styles.append(custom_formats.get(num_fmt_id, BUILTIN_NUM_FORMATS.get(num_fmt_id, "")))
        return styles

    def _read_workbook_relationships(self, package: OOXMLPackage) -> Dict[str, str]:
        if not package.exists("xl/_rels/workbook.xml.rels"):
            return {}
        root = package.read_xml_part("xl/_rels/workbook.xml.rels")
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if rel_id and target:
                relationships[rel_id] = _resolve_target("xl", target)
        return relationships

    def _read_sheets(self, workbook, relationships: Dict[str, str]) -> List[Tuple[str, str]]:
        sheets = []
        for sheet in workbook.findall("s:sheets/s:sheet", namespaces=_namespaces(workbook)):
            name = sheet.get("name", "")
            rel_id = _rel_attr(sheet, "id")
            path = relationships.get(rel_id, "")
            if name and path:
                sheets.append((name, path))
        return sheets

    def _read_sheet_headers_footers(self, root) -> Tuple[List[HeaderFooter], List[HeaderFooter]]:
        header_footer = root.find("s:headerFooter", namespaces=_namespaces(root))
        if header_footer is None:
            return [], []

        headers = []
        footers = []
        for tag_name, target, hf_type in (
            ("oddHeader", headers, "header"),
            ("evenHeader", headers, "header"),
            ("firstHeader", headers, "header"),
            ("oddFooter", footers, "footer"),
            ("evenFooter", footers, "footer"),
            ("firstFooter", footers, "footer"),
        ):
            elem = header_footer.find(f"s:{tag_name}", namespaces=_namespaces(root))
            text = self._header_footer_text((elem.text or "") if elem is not None else "")
            if text:
                target.append(HeaderFooter(type=hf_type, paragraphs=[Paragraph(runs=[TextRun(text=text)])]))
        return headers, footers

    def _header_footer_text(self, raw: str) -> str:
        sections = {"L": [], "C": [], "R": []}
        current = "C"
        index = 0
        while index < len(raw):
            char = raw[index]
            if char != "&":
                sections[current].append(char)
                index += 1
                continue
            if index + 1 >= len(raw):
                sections[current].append("&")
                index += 1
                continue

            code = raw[index + 1]
            if code == "&":
                sections[current].append("&")
                index += 2
            elif code in sections:
                current = code
                index += 2
            elif code == '"':
                index = self._skip_quoted_header_footer_code(raw, index + 2)
            elif code == "K":
                index = self._skip_header_footer_color(raw, index + 2)
            else:
                index += 2

        return " | ".join(
            text
            for text in ("".join(sections[key]).strip() for key in ("L", "C", "R"))
            if text
        )

    def _skip_quoted_header_footer_code(self, raw: str, index: int) -> int:
        while index < len(raw):
            if raw[index] == '"':
                return index + 1
            index += 1
        return index

    def _skip_header_footer_color(self, raw: str, index: int) -> int:
        end = min(index + 6, len(raw))
        while index < end and re.match(r"[0-9A-Fa-f+\-]", raw[index]):
            index += 1
        return index

    def _read_sheet_table(
        self,
        package: OOXMLPackage,
        root,
        sheet_path: str,
        sheet_name: str,
        shared_strings: List[str],
        styles: List[str],
    ) -> Table:
        merges = self._read_merges(root)
        merge_refs = self._merge_refs(merges)
        hyperlinks = self._read_hyperlinks(package, root, sheet_path)
        comments = self._read_comments(package, sheet_path)
        shared_formulas = {}
        row_maps = {}
        max_row = -1
        max_col = -1
        for fallback_row_idx, row_elem in enumerate(root.findall("s:sheetData/s:row", namespaces=_namespaces(root))):
            row_idx = self._sheet_row_index(row_elem, fallback_row_idx)
            by_col = {}
            next_col_idx = 0
            for cell_elem in row_elem.findall("s:c", namespaces=_namespaces(row_elem)):
                explicit_cell_ref = cell_elem.get("r", "")
                if explicit_cell_ref and self._is_fast_blank_unreferenced_cell(cell_elem, explicit_cell_ref, hyperlinks, comments, merge_refs):
                    continue
                col_idx = _column_index(explicit_cell_ref) if explicit_cell_ref else next_col_idx
                cell_ref = explicit_cell_ref or f"{_column_name(col_idx)}{row_idx + 1}"
                next_col_idx = col_idx + 1
                if not explicit_cell_ref and self._is_fast_blank_unreferenced_cell(cell_elem, cell_ref, hyperlinks, comments, merge_refs):
                    continue
                merge_span = merges.get((row_idx, col_idx))
                if self._is_empty_unreferenced_cell(cell_elem, cell_ref, hyperlinks, comments, merge_span):
                    continue
                cell_children = self._cell_children(cell_elem)
                if self._is_blank_unreferenced_cell(cell_children, cell_ref, hyperlinks, comments, merge_span):
                    continue
                self._capture_shared_formula(cell_elem, shared_formulas, cell_children)
                cell_text = self._commented_cell_text(
                    self._linked_cell_text(
                        self._cell_text(cell_elem, shared_strings, styles, shared_formulas, cell_children),
                        hyperlinks.get(cell_ref),
                    ),
                    comments.get(cell_ref),
                )
                if not cell_text and not merge_span:
                    continue
                if not cell_text and merge_span == (0, 0):
                    continue
                max_col = max(max_col, col_idx)
                provenance = Provenance(
                    source_format="xlsx",
                    sheet=sheet_name,
                    cell=cell_ref,
                    path=sheet_path,
                )
                cell = Cell(
                    paragraphs=[
                        Paragraph(
                            runs=[TextRun(text=cell_text, provenance=provenance)],
                            provenance=provenance,
                        )
                    ],
                    provenance=provenance,
                )
                if merge_span:
                    row_span, col_span = merge_span
                    cell.row_span = row_span
                    cell.col_span = col_span
                    max_col = max(max_col, col_idx + max(col_span, 1) - 1)
                by_col[col_idx] = cell
            if by_col:
                max_row = max(max_row, row_idx)
                row_maps[row_idx] = by_col

        rows = []
        for row_idx in range(max_row + 1):
            by_col = row_maps.get(row_idx, {})
            cells = [
                by_col.get(col_idx, self._empty_or_merged_cell(merges, row_idx, col_idx))
                for col_idx in range(max_col + 1)
            ]
            if cells:
                rows.append(cells)
        return Table(rows=rows)

    def _read_large_sheet_table(
        self,
        package: OOXMLPackage,
        sheet_path: str,
        sheet_name: str,
        shared_strings: List[str],
        styles: List[str],
    ) -> Table:
        rows = []
        max_col = -1
        cell_count = 0
        shared_formulas = {}
        with package.open_part(sheet_path) as stream:
            context = etree.iterparse(
                stream,
                events=("end",),
                tag=(f"{{{S_NS}}}row", f"{{{STRICT_S_NS}}}row"),
                huge_tree=True,
                recover=True,
            )
            for _, row_elem in context:
                row_cells = {}
                next_col_idx = 0
                for cell_elem in row_elem:
                    if _local_name(cell_elem) != "c":
                        continue
                    explicit_cell_ref = cell_elem.get("r", "")
                    col_idx = _column_index(explicit_cell_ref) if explicit_cell_ref else next_col_idx
                    next_col_idx = col_idx + 1
                    cell_children = self._cell_children(cell_elem)
                    if not any(name in cell_children for name in ("v", "f", "is")):
                        continue
                    self._capture_shared_formula(cell_elem, shared_formulas, cell_children)
                    cell_text = self._cell_text(cell_elem, shared_strings, styles, shared_formulas, cell_children)
                    if not cell_text:
                        continue
                    cell_ref = explicit_cell_ref or f"{_column_name(col_idx)}{len(rows) + 1}"
                    provenance = Provenance(
                        source_format="xlsx",
                        sheet=sheet_name,
                        cell=cell_ref,
                        path=sheet_path,
                    )
                    row_cells[col_idx] = Cell(
                        paragraphs=[
                            Paragraph(
                                runs=[TextRun(text=cell_text, provenance=provenance)],
                                provenance=provenance,
                            )
                        ],
                        provenance=provenance,
                    )
                    max_col = max(max_col, col_idx)
                    cell_count += 1
                    if cell_count >= STREAMING_CELL_LIMIT:
                        break
                if row_cells:
                    rows.append(row_cells)
                row_elem.clear()
                while row_elem.getprevious() is not None:
                    del row_elem.getparent()[0]
                if len(rows) >= STREAMING_ROW_LIMIT or cell_count >= STREAMING_CELL_LIMIT:
                    break

        if max_col < 0:
            return Table()
        return Table(
            rows=[
                [row_map.get(col_idx, Cell()) for col_idx in range(max_col + 1)]
                for row_map in rows
            ]
        )

    def _read_sheet_drawings(self, package: OOXMLPackage, sheet_root, sheet_path: str, sheet_name: str) -> List[object]:
        relationships = self._read_sheet_relationships(package, sheet_path, resolve_internal=True)
        elements = []
        seen = set()
        for drawing in sheet_root.findall("s:drawing", namespaces=_namespaces(sheet_root)):
            drawing_path = relationships.get(_rel_attr(drawing, "id"), "")
            if not drawing_path or drawing_path in seen or not package.exists(drawing_path):
                continue
            seen.add(drawing_path)
            elements.extend(self._read_drawing_part(package, drawing_path, sheet_name))
        for legacy_drawing in sheet_root.findall("s:legacyDrawing", namespaces=_namespaces(sheet_root)):
            vml_path = relationships.get(_rel_attr(legacy_drawing, "id"), "")
            if not vml_path or vml_path in seen or not package.exists(vml_path):
                continue
            seen.add(vml_path)
            elements.extend(self._read_vml_drawing_part(package, vml_path, sheet_name))
        self._record_sheet_embedded_assets(package, sheet_root, sheet_path, sheet_name)
        return elements

    def _read_vml_drawing_part(self, package: OOXMLPackage, vml_path: str, sheet_name: str) -> List[Paragraph]:
        root = package.read_xml_part(vml_path, recover=True)
        relationships = self._read_part_relationships(package, vml_path)
        paragraphs = []
        for image_data in root.findall(".//v:imagedata", namespaces=NS):
            rel_id = _attr(image_data, O_NS, "relid")
            target = relationships.get(rel_id, "")
            if not target:
                continue
            label = _attr(image_data, O_NS, "title") or image_data.get("title", "") or "image"
            self._record_image_asset(rel_id, target, label, sheet_name)
            paragraphs.append(self._drawing_paragraph(f"![{label}]({target})", sheet_name, vml_path))
        return paragraphs

    def _record_sheet_embedded_assets(self, package: OOXMLPackage, sheet_root, sheet_path: str, sheet_name: str):
        rels_path = self._relationships_path(sheet_path)
        if not package.exists(rels_path):
            return
        embedded_rel_ids = {
            _rel_attr(ole_object, "id")
            for ole_object in sheet_root.findall(".//s:oleObject", namespaces=_namespaces(sheet_root))
            if _rel_attr(ole_object, "id")
        }
        if not embedded_rel_ids:
            return
        root = package.read_xml_part(rels_path)
        sheet_dir = posixpath.dirname(sheet_path)
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            rel_type = rel.get("Type", "")
            target = rel.get("Target", "")
            if rel_id not in embedded_rel_ids or not rel_type.endswith("/oleObject") or not target:
                continue
            self._record_embedded_asset(rel_id, _resolve_target(sheet_dir, target), rel_type, sheet_name)

    def _read_drawing_part(self, package: OOXMLPackage, drawing_path: str, sheet_name: str) -> List[object]:
        root = package.read_xml_part(drawing_path)
        relationships = self._read_part_relationships(package, drawing_path)
        positioned = []
        ordinal = 0
        for anchor in root.findall("xdr:twoCellAnchor", namespaces=NS) + root.findall("xdr:oneCellAnchor", namespaces=NS):
            row, col = self._anchor_position(anchor)
            for text in self._drawing_texts(anchor):
                positioned.append((row, col, ordinal, self._drawing_paragraph(text, sheet_name, drawing_path)))
                ordinal += 1
            image_reference = self._drawing_image_reference(anchor, relationships, sheet_name)
            if image_reference:
                positioned.append((row, col, ordinal, self._drawing_paragraph(image_reference, sheet_name, drawing_path)))
                ordinal += 1
            for chart_elem in anchor.findall(".//c:chart", namespaces=NS):
                for element in self._parse_chart(chart_elem, package, relationships, sheet_name):
                    positioned.append((row, col, ordinal, element))
                    ordinal += 1
        return [item[-1] for item in sorted(positioned, key=lambda item: item[:3])]

    def _read_part_relationships(self, package: OOXMLPackage, part_path: str) -> Dict[str, str]:
        part_dir = posixpath.dirname(part_path)
        rels_path = self._relationships_path(part_path)
        if not package.exists(rels_path):
            return {}
        root = package.read_xml_part(rels_path)
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if rel_id and target:
                relationships[rel_id] = _resolve_target(part_dir, target)
        return relationships

    def _relationships_path(self, part_path: str) -> str:
        part_dir = posixpath.dirname(part_path)
        return f"{part_dir}/_rels/{posixpath.basename(part_path)}.rels"

    def _anchor_position(self, anchor) -> Tuple[int, int]:
        marker = anchor.find("xdr:from", namespaces=NS)
        if marker is None:
            return (0, 0)
        return (
            self._int_child(marker, "xdr:row"),
            self._int_child(marker, "xdr:col"),
        )

    def _int_child(self, elem, path: str) -> int:
        child = elem.find(path, namespaces=NS)
        try:
            return int(child.text or "0") if child is not None else 0
        except ValueError:
            return 0

    def _drawing_texts(self, anchor) -> List[str]:
        texts = []
        for tx_body in anchor.findall(".//xdr:txBody", namespaces=NS):
            paragraph_texts = []
            for p_elem in tx_body.findall("a:p", namespaces=NS):
                text = "".join(node.text or "" for node in p_elem.findall(".//a:t", namespaces=NS)).strip()
                if text:
                    paragraph_texts.append(text)
            if paragraph_texts:
                texts.append("\n".join(paragraph_texts))
        return texts

    def _drawing_image_reference(self, anchor, relationships: Dict[str, str], sheet_name: str) -> str:
        blip = anchor.find(".//a:blip", namespaces=NS)
        if blip is None:
            return ""
        rel_id = _rel_attr(blip, "embed")
        target = relationships.get(rel_id, "")
        if not target:
            return ""
        label = self._drawing_label(anchor)
        self._record_image_asset(rel_id, target, label, sheet_name)
        return f"![{label or 'image'}]({target})"

    def _record_image_asset(self, rel_id: str, target: str, label: str, sheet_name: str):
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
                metadata={"label": label, "source_format": "xlsx", "sheet": sheet_name},
            )
        )

    def _record_embedded_asset(self, rel_id: str, target: str, rel_type: str, sheet_name: str):
        if not rel_id or not target:
            return
        key = ("embedded", rel_id, target)
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
                    "source_format": "xlsx",
                    "sheet": sheet_name,
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
            return "application/vnd.openxmlformats-officedocument.oleObject"
        extension = posixpath.splitext(target.lower())[1]
        return {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".doc": "application/msword",
            ".ppt": "application/vnd.ms-powerpoint",
            ".xls": "application/vnd.ms-excel",
        }.get(extension, "application/octet-stream")

    def _drawing_label(self, anchor) -> str:
        c_nv_pr = anchor.find(".//xdr:cNvPr", namespaces=NS)
        if c_nv_pr is None:
            return ""
        return " ".join(
            part
            for part in (c_nv_pr.get("descr", ""), c_nv_pr.get("name", ""))
            if part
        ).strip()

    def _drawing_paragraph(self, text: str, sheet_name: str, drawing_path: str) -> Paragraph:
        return Paragraph(
            runs=[TextRun(text=text)],
            provenance=Provenance(source_format="xlsx", sheet=sheet_name, path=drawing_path),
        )

    def _parse_chart(self, chart_elem, package: OOXMLPackage, relationships: Dict[str, str], sheet_name: str) -> List[object]:
        chart_path = relationships.get(_rel_attr(chart_elem, "id"), "")
        if not chart_path or not package.exists(chart_path):
            return []
        chart_root = package.read_xml_part(chart_path)
        elements = []
        title = self._chart_title(chart_root)
        if title:
            title_paragraph = self._drawing_paragraph(title, sheet_name, chart_path)
            title_paragraph.heading_level = 3
            elements.append(title_paragraph)
        table = self._chart_series_table(chart_root)
        if table.rows:
            elements.append(table)
        return elements

    def _chart_title(self, chart_root) -> str:
        title = chart_root.find(".//c:title", namespaces=NS)
        if title is None:
            return ""
        return self._chart_text(title)

    def _chart_series_table(self, chart_root) -> Table:
        series_items = []
        for series in chart_root.findall(".//c:ser", namespaces=NS):
            series_name = self._chart_series_name(series)
            categories = self._chart_points(series, "c:cat") or self._chart_points(series, "c:xVal")
            values = self._chart_points(series, "c:val") or self._chart_points(series, "c:yVal")
            series_items.append((series_name, categories, values))
        if not series_items:
            return Table()

        category_labels = {}
        indexes = set()
        for _, categories, values in series_items:
            indexes.update(categories)
            indexes.update(values)
            for index, category in categories.items():
                category_labels.setdefault(index, category)

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
                    Cell(paragraphs=[Paragraph(runs=[TextRun(text=category_labels.get(point_index, str(point_index)))] )]),
                    *[
                        Cell(paragraphs=[Paragraph(runs=[TextRun(text=values.get(point_index, ""))])])
                        for _, _, values in series_items
                    ],
                ]
            )
        return Table(rows=rows)

    def _chart_series_name(self, series) -> str:
        tx = series.find("c:tx", namespaces=NS)
        return self._chart_text(tx) if tx is not None else ""

    def _chart_text(self, elem) -> str:
        text = " ".join(
            node.text or ""
            for node in elem.findall(".//a:t", namespaces=NS)
            if node.text
        ).strip()
        if text:
            return text
        return " ".join(
            node.text or ""
            for node in elem.findall(".//c:v", namespaces=NS)
            if node.text
        ).strip()

    def _chart_points(self, series, parent_path: str) -> Dict[int, str]:
        points = {}
        parent = series.find(parent_path, namespaces=NS)
        if parent is None:
            return points
        for point in parent.findall(".//c:pt", namespaces=NS):
            try:
                index = int(point.get("idx", "0"))
            except ValueError:
                index = len(points)
            value = "".join(node.text or "" for node in point.findall("c:v", namespaces=NS)).strip()
            if value:
                points[index] = value
        return points

    def _cell_children(self, cell_elem) -> Dict[str, object]:
        children = {}
        for child in cell_elem:
            children.setdefault(_local_name(child), child)
        return children

    def _merge_refs(self, merges: Dict[Tuple[int, int], Tuple[int, int]]) -> set:
        return {f"{_column_name(col_idx)}{row_idx + 1}" for row_idx, col_idx in merges}

    def _is_fast_blank_unreferenced_cell(self, cell_elem, cell_ref: str, hyperlinks, comments, merge_refs) -> bool:
        if len(cell_elem) != 0:
            return False
        return not hyperlinks.get(cell_ref) and not comments.get(cell_ref) and cell_ref not in merge_refs

    def _is_empty_unreferenced_cell(self, cell_elem, cell_ref: str, hyperlinks, comments, merge_span) -> bool:
        if len(cell_elem) != 0:
            return False
        if hyperlinks.get(cell_ref) or comments.get(cell_ref):
            return False
        return not merge_span or merge_span == (0, 0)

    def _capture_shared_formula(self, cell_elem, shared_formulas: Dict[str, Tuple[str, str]], cell_children=None):
        formula = (cell_children or self._cell_children(cell_elem)).get("f")
        if formula is None or formula.get("t", "") != "shared":
            return
        shared_index = formula.get("si", "")
        if shared_index and formula.text:
            shared_formulas[shared_index] = (formula.text, cell_elem.get("r", ""))

    def _is_blank_unreferenced_cell(self, cell_children, cell_ref: str, hyperlinks, comments, merge_span) -> bool:
        if hyperlinks.get(cell_ref) or comments.get(cell_ref):
            return False
        if merge_span and merge_span != (0, 0):
            return False
        return not any(name in cell_children for name in ("v", "f", "is"))

    def _sheet_row_index(self, row_elem, fallback: int = 0) -> int:
        try:
            row_ref = row_elem.get("r", "")
            if row_ref:
                return max(int(row_ref) - 1, 0)
        except ValueError:
            pass
        first_cell = row_elem.find("s:c", namespaces=_namespaces(row_elem))
        first_cell_ref = first_cell.get("r", "") if first_cell is not None else ""
        if first_cell_ref:
            return _row_index(first_cell_ref)
        return fallback

    def _read_hyperlinks(self, package: OOXMLPackage, root, sheet_path: str) -> Dict[str, Tuple[str, str]]:
        rels = self._read_sheet_relationships(package, sheet_path)
        hyperlinks = {}
        for hyperlink in root.findall("s:hyperlinks/s:hyperlink", namespaces=_namespaces(root)):
            cell_ref = hyperlink.get("ref", "")
            rel_id = _rel_attr(hyperlink, "id")
            display = hyperlink.get("display", "")
            location = hyperlink.get("location", "")
            target = rels.get(rel_id, "")
            if not target and location:
                target = f"#{location}"
            if cell_ref and target:
                for ref in self._cell_refs_in_range(cell_ref):
                    hyperlinks[ref] = (display, target)
        return hyperlinks

    def _cell_refs_in_range(self, cell_ref: str) -> List[str]:
        if ":" not in cell_ref:
            return [cell_ref]
        start_ref, end_ref = cell_ref.split(":", 1)
        start_row, start_col = _row_index(start_ref), _column_index(start_ref)
        end_row, end_col = _row_index(end_ref), _column_index(end_ref)
        row_start, row_end = sorted((start_row, end_row))
        col_start, col_end = sorted((start_col, end_col))
        refs = []
        for row_idx in range(row_start, row_end + 1):
            for col_idx in range(col_start, col_end + 1):
                refs.append(f"{_column_name(col_idx)}{row_idx + 1}")
        return refs

    def _read_sheet_relationships(self, package: OOXMLPackage, sheet_path: str, resolve_internal: bool = False) -> Dict[str, str]:
        sheet_dir = posixpath.dirname(sheet_path)
        rels_path = f"{sheet_dir}/_rels/{posixpath.basename(sheet_path)}.rels"
        if not package.exists(rels_path):
            return {}
        root = package.read_xml_part(rels_path)
        relationships = {}
        for rel in root.findall("rel:Relationship", namespaces=NS):
            rel_id = rel.get("Id", "")
            target = rel.get("Target", "")
            if rel_id and target:
                relationships[rel_id] = _resolve_target(sheet_dir, target) if resolve_internal else target
        return relationships

    def _read_comments(self, package: OOXMLPackage, sheet_path: str) -> Dict[str, str]:
        sheet_dir = posixpath.dirname(sheet_path)
        rels_path = f"{sheet_dir}/_rels/{posixpath.basename(sheet_path)}.rels"
        if not package.exists(rels_path):
            return {}
        rels_root = package.read_xml_part(rels_path)
        comments_path = ""
        for rel in rels_root.findall("rel:Relationship", namespaces=NS):
            if rel.get("Type", "").endswith("/comments") and rel.get("Target"):
                comments_path = _resolve_target(sheet_dir, rel.get("Target", ""))
                break
        if not comments_path or not package.exists(comments_path):
            return {}

        root = package.read_xml_part(comments_path)
        authors = [
            author.text or ""
            for author in root.findall("s:authors/s:author", namespaces=_namespaces(root))
        ]
        comments = {}
        for comment in root.findall("s:commentList/s:comment", namespaces=_namespaces(root)):
            cell_ref = comment.get("ref", "")
            text = self._text_runs(comment.find("s:text", namespaces=_namespaces(comment))).strip()
            if not cell_ref or not text:
                continue
            author = self._comment_author(comment, authors)
            comments[cell_ref] = f"{author}: {text}" if author else text
        return comments

    def _comment_author(self, comment, authors: List[str]) -> str:
        try:
            author_index = int(comment.get("authorId", ""))
        except ValueError:
            return ""
        if 0 <= author_index < len(authors):
            return authors[author_index]
        return ""

    def _linked_cell_text(self, text: str, hyperlink) -> str:
        if not hyperlink:
            return text
        display, target = hyperlink
        label = text or display
        return f"{label} <{target}>" if label else target

    def _commented_cell_text(self, text: str, comment: str) -> str:
        if not comment:
            return text
        return f"{text} [comment: {comment}]" if text else f"[comment: {comment}]"

    def _empty_or_merged_cell(self, merges: Dict[Tuple[int, int], Tuple[int, int]], row_idx: int, col_idx: int) -> Cell:
        if (row_idx, col_idx) in merges:
            row_span, col_span = merges[(row_idx, col_idx)]
            return Cell(row_span=row_span, col_span=col_span)
        return Cell()

    def _read_merges(self, root) -> Dict[Tuple[int, int], Tuple[int, int]]:
        merges: Dict[Tuple[int, int], Tuple[int, int]] = {}
        for merge_cell in root.findall("s:mergeCells/s:mergeCell", namespaces=_namespaces(root)):
            ref = merge_cell.get("ref", "")
            if ":" not in ref:
                continue
            start_ref, end_ref = ref.split(":", 1)
            start_row, start_col = _row_index(start_ref), _column_index(start_ref)
            end_row, end_col = _row_index(end_ref), _column_index(end_ref)
            row_span = max(end_row - start_row + 1, 1)
            col_span = max(end_col - start_col + 1, 1)
            merges[(start_row, start_col)] = (row_span, col_span)
            for row_idx in range(start_row, end_row + 1):
                for col_idx in range(start_col, end_col + 1):
                    if (row_idx, col_idx) != (start_row, start_col):
                        merges[(row_idx, col_idx)] = (0, 0)
        return merges

    def _read_shared_formulas(self, root) -> Dict[str, Tuple[str, str]]:
        formulas = {}
        for cell_elem in root.findall(".//s:c", namespaces=_namespaces(root)):
            formula = cell_elem.find("s:f", namespaces=_namespaces(cell_elem))
            if formula is None:
                continue
            if formula.get("t", "") != "shared":
                continue
            shared_index = formula.get("si", "")
            if shared_index and formula.text:
                formulas[shared_index] = (formula.text, cell_elem.get("r", ""))
        return formulas

    def _cell_text(
        self,
        cell_elem,
        shared_strings: List[str],
        styles: List[str],
        shared_formulas: Dict[str, Tuple[str, str]],
        cell_children=None,
    ) -> str:
        cell_children = cell_children or self._cell_children(cell_elem)
        cell_type = cell_elem.get("t", "")
        if cell_type == "s":
            value = self._value_text(cell_elem, cell_children)
            try:
                return self._with_formula(shared_strings[int(value)], cell_elem, shared_formulas, cell_children.get("f"))
            except (ValueError, IndexError):
                return ""
        if cell_type == "inlineStr":
            return self._with_formula(self._text_runs(cell_children.get("is")), cell_elem, shared_formulas, cell_children.get("f"))
        if cell_type == "b":
            value = self._value_text(cell_elem, cell_children)
            return self._with_formula("TRUE" if value == "1" else "FALSE", cell_elem, shared_formulas, cell_children.get("f"))
        if cell_type == "str":
            return self._with_formula(self._value_text(cell_elem, cell_children), cell_elem, shared_formulas, cell_children.get("f"))
        return self._with_formula(
            self._format_cell_value(self._value_text(cell_elem, cell_children), self._cell_format(cell_elem, styles)),
            cell_elem,
            shared_formulas,
            cell_children.get("f"),
        )

    def _text_runs(self, elem) -> str:
        if elem is None:
            return ""
        return "".join(t.text or "" for t in elem.findall(".//s:t", namespaces=_namespaces(elem)))

    def _with_formula(self, text: str, cell_elem, shared_formulas: Dict[str, Tuple[str, str]], formula=None) -> str:
        formula_text = formula.text if formula is not None and formula.text is not None else ""
        if not formula_text and formula is not None and formula.get("t", "") == "shared":
            shared_formula = shared_formulas.get(formula.get("si", ""), ("", ""))
            formula_text = self._translate_shared_formula(
                shared_formula[0],
                shared_formula[1],
                cell_elem.get("r", ""),
            )
        if not formula_text:
            return text
        return f"{text} (={formula_text})" if text else f"={formula_text}"

    def _translate_shared_formula(self, formula_text: str, origin_ref: str, cell_ref: str) -> str:
        if not formula_text or not origin_ref or not cell_ref:
            return formula_text
        row_offset = _row_index(cell_ref) - _row_index(origin_ref)
        col_offset = _column_index(cell_ref) - _column_index(origin_ref)

        formula_text = self._translate_whole_column_ranges(formula_text, col_offset)
        formula_text = self._translate_whole_row_ranges(formula_text, row_offset)

        def replace_ref(match) -> str:
            col_absolute, col_name, row_absolute, row_text = match.groups()
            col_idx = _column_index(col_name)
            row_idx = int(row_text) - 1
            if not col_absolute:
                col_idx += col_offset
            if not row_absolute:
                row_idx += row_offset
            return f"{col_absolute}{_column_name(col_idx)}{row_absolute}{max(row_idx + 1, 1)}"

        return re.sub(r"(?<![A-Za-z0-9_])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_])", replace_ref, formula_text)

    def _translate_whole_column_ranges(self, formula_text: str, col_offset: int) -> str:
        if not col_offset:
            return formula_text

        def replace_range(match) -> str:
            start_absolute, start_col, end_absolute, end_col = match.groups()
            start_idx = _column_index(start_col)
            end_idx = _column_index(end_col)
            if not start_absolute:
                start_idx += col_offset
            if not end_absolute:
                end_idx += col_offset
            return f"{start_absolute}{_column_name(start_idx)}:{end_absolute}{_column_name(end_idx)}"

        return re.sub(
            r"(?<![A-Za-z0-9_:$])(\$?)([A-Z]{1,3}):(\$?)([A-Z]{1,3})(?![A-Za-z0-9_:])",
            replace_range,
            formula_text,
        )

    def _translate_whole_row_ranges(self, formula_text: str, row_offset: int) -> str:
        if not row_offset:
            return formula_text

        def replace_range(match) -> str:
            start_absolute, start_row, end_absolute, end_row = match.groups()
            start_idx = int(start_row)
            end_idx = int(end_row)
            if not start_absolute:
                start_idx += row_offset
            if not end_absolute:
                end_idx += row_offset
            return f"{start_absolute}{max(start_idx, 1)}:{end_absolute}{max(end_idx, 1)}"

        return re.sub(
            r"(?<![A-Za-z0-9_:$])(\$?)(\d+):(\$?)(\d+)(?![A-Za-z0-9_:])",
            replace_range,
            formula_text,
        )

    def _cell_format(self, cell_elem, styles: List[str]) -> str:
        try:
            style_index = int(cell_elem.get("s", ""))
        except ValueError:
            return ""
        if 0 <= style_index < len(styles):
            return styles[style_index]
        return ""

    def _format_cell_value(self, value: str, fmt: str) -> str:
        if not value or not fmt:
            return value
        metadata = self._format_metadata(fmt)
        try:
            number = float(value)
        except ValueError:
            return value
        if metadata.kind == "duration":
            return self._excel_duration(number, include_seconds="ss" in fmt.lower())
        if metadata.kind == "time":
            return self._excel_time(number, include_seconds="ss" in fmt.lower())
        if metadata.kind == "date":
            return self._excel_date(number).strftime("%Y-%m-%d")
        if metadata.kind == "zero_fill":
            formatted = self._zero_filled_number(number, metadata.pattern)
            return self._apply_literal_affixes(formatted, metadata)
        if metadata.kind == "fraction":
            formatted = self._fraction_number(number, metadata.denominator_limit)
            return self._apply_literal_affixes(formatted, metadata)
        if metadata.kind == "scientific":
            formatted = f"{number:.{metadata.decimals}E}"
            return self._apply_literal_affixes(formatted, metadata)
        if metadata.kind == "percent":
            formatted = f"{abs(number) * 100:.{metadata.decimals}f}%" if metadata.negative_parentheses and number < 0 else f"{number * 100:.{metadata.decimals}f}%"
            formatted = self._apply_literal_affixes(formatted, metadata)
            return f"({formatted})" if metadata.negative_parentheses and number < 0 else formatted
        if metadata.kind == "decimal":
            separator = "," if metadata.thousands else ""
            display_number = abs(number) if metadata.negative_parentheses and number < 0 else number
            formatted = f"{display_number:{separator}.{metadata.decimals}f}"
            formatted = f"{metadata.currency_symbol}{formatted}"
            formatted = self._apply_literal_affixes(formatted, metadata)
            return f"({formatted})" if metadata.negative_parentheses and number < 0 else formatted
        return value

    def _format_metadata(self, fmt: str) -> _FormatMetadata:
        cache = getattr(self, "_format_metadata_cache", None)
        if cache is None:
            cache = {}
            self._format_metadata_cache = cache
        cached = cache.get(fmt)
        if cached is not None:
            return cached
        lower_fmt = fmt.lower()
        if self._is_duration_format(lower_fmt):
            metadata = _FormatMetadata(kind="duration")
        elif self._is_time_only_format(lower_fmt):
            metadata = _FormatMetadata(kind="time")
        elif self._is_date_format(lower_fmt):
            metadata = _FormatMetadata(kind="date")
        elif self._is_zero_fill_format(fmt):
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="zero_fill",
                pattern=self._format_without_literals(fmt),
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
            )
        elif self._is_fraction_format(fmt):
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="fraction",
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
                denominator_limit=self._fraction_denominator_limit(fmt),
            )
        elif self._is_scientific_format(fmt):
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="scientific",
                decimals=self._scientific_decimal_places(fmt),
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
            )
        elif "%" in fmt:
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="percent",
                decimals=self._decimal_places_before_percent(fmt),
                negative_parentheses=self._negative_uses_parentheses(fmt),
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
            )
        else:
            decimals = self._decimal_places(fmt)
            thousands = self._uses_thousands_separator(fmt)
            currency_symbol = self._currency_symbol(fmt)
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            if decimals is not None or thousands or currency_symbol or literal_prefix or literal_suffix:
                metadata = _FormatMetadata(
                    kind="decimal",
                    decimals=decimals if decimals is not None else 0,
                    thousands=thousands,
                    currency_symbol=currency_symbol,
                    negative_parentheses=self._negative_uses_parentheses(fmt),
                    literal_prefix=literal_prefix,
                    literal_suffix=literal_suffix,
                )
            else:
                metadata = _FormatMetadata()
        cache[fmt] = metadata
        return metadata

    def _is_date_format(self, lower_fmt: str) -> bool:
        if "%" in lower_fmt:
            return False
        return any(token in lower_fmt for token in ("yy", "mm", "dd", "mmm", "h:mm"))

    def _is_duration_format(self, lower_fmt: str) -> bool:
        clean_fmt = self._format_without_literals(lower_fmt)
        return "[h]" in clean_fmt or "[m]" in clean_fmt or "[s]" in clean_fmt

    def _is_time_only_format(self, lower_fmt: str) -> bool:
        clean_fmt = self._format_without_literals(lower_fmt)
        if not any(token in clean_fmt for token in ("h:mm", "hh:mm")):
            return False
        return not any(token in clean_fmt for token in ("yy", "dd", "mmm", "m/d", "d/m"))

    def _excel_date(self, serial: float) -> datetime:
        base = datetime(1899, 12, 30)
        return base + timedelta(days=serial)

    def _excel_time(self, serial: float, include_seconds: bool = False) -> str:
        total_seconds = int(round((serial % 1) * 86400))
        total_seconds %= 86400
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if include_seconds else f"{hours:02d}:{minutes:02d}"

    def _excel_duration(self, serial: float, include_seconds: bool = False) -> str:
        total_seconds = int(round(serial * 86400))
        sign = "-" if total_seconds < 0 else ""
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{sign}{hours}:{minutes:02d}:{seconds:02d}" if include_seconds else f"{sign}{hours}:{minutes:02d}"

    def _zero_filled_number(self, number: float, pattern: str) -> str:
        sign = "-" if number < 0 else ""
        digits = str(int(abs(number)))
        width = pattern.count("0")
        overflow = max(len(digits) - width, 0)
        prefix = digits[:overflow]
        digits = digits[overflow:].zfill(width)
        result = []
        digit_index = 0
        for char in pattern:
            if char == "0":
                result.append(digits[digit_index] if digit_index < len(digits) else "0")
                digit_index += 1
            else:
                result.append(char)
        return sign + prefix + "".join(result)

    def _fraction_number(self, number: float, denominator_limit: int) -> str:
        sign = "-" if number < 0 else ""
        value = abs(number)
        whole = int(value)
        fraction = Fraction(value - whole).limit_denominator(max(denominator_limit, 1))
        if fraction.numerator == fraction.denominator:
            whole += 1
            fraction = Fraction(0, 1)
        if fraction.numerator == 0:
            return f"{sign}{whole}"
        if whole:
            return f"{sign}{whole} {fraction.numerator}/{fraction.denominator}"
        return f"{sign}{fraction.numerator}/{fraction.denominator}"

    def _apply_literal_affixes(self, text: str, metadata: _FormatMetadata) -> str:
        if not metadata.literal_prefix and not metadata.literal_suffix:
            return text
        sign = ""
        if text.startswith("-"):
            sign = "-"
            text = text[1:]
        return f"{sign}{metadata.literal_prefix}{text}{metadata.literal_suffix}"

    def _decimal_places_before_percent(self, fmt: str) -> int:
        before_percent = fmt.split("%", 1)[0]
        decimals = self._decimal_places(before_percent)
        return decimals if decimals is not None else 0

    def _decimal_places(self, fmt: str):
        match = re.search(r"0\.([0#]+)", fmt)
        if match:
            return len(match.group(1))
        return None

    def _uses_thousands_separator(self, fmt: str) -> bool:
        return "," in self._format_without_literals(fmt)

    def _is_zero_fill_format(self, fmt: str) -> bool:
        clean_fmt = self._format_without_literals(fmt)
        if "." in clean_fmt or "#" in clean_fmt or "%" in clean_fmt or "," in clean_fmt:
            return False
        if not re.fullmatch(r"[0\-\s/()]+", clean_fmt):
            return False
        return clean_fmt.count("0") > 1

    def _is_fraction_format(self, fmt: str) -> bool:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        return "/" in first_section and "?" in first_section

    def _fraction_denominator_limit(self, fmt: str) -> int:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        denominator = first_section.rsplit("/", 1)[-1]
        digit_slots = sum(1 for char in denominator if char in {"?", "0", "#"})
        return (10 ** max(digit_slots, 1)) - 1

    def _is_scientific_format(self, fmt: str) -> bool:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        return bool(re.search(r"[0#?](?:\.[0#?]+)?E[+-]0+", first_section, flags=re.IGNORECASE))

    def _scientific_decimal_places(self, fmt: str) -> int:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        mantissa = re.split(r"E[+-]", first_section, maxsplit=1, flags=re.IGNORECASE)[0]
        match = re.search(r"\.([0#?]+)", mantissa)
        return len(match.group(1)) if match else 0

    def _currency_symbol(self, fmt: str) -> str:
        clean_fmt = self._format_without_literals(fmt)
        bracketed = re.search(r"\[\$([^-\]]+)", clean_fmt)
        if bracketed:
            return bracketed.group(1)
        return "$" if "$" in clean_fmt else ""

    def _format_without_literals(self, fmt: str) -> str:
        without_quoted = re.sub(r'"[^"]*"', "", fmt)
        return re.sub(r"\\.", "", without_quoted)

    def _literal_affixes(self, fmt: str) -> Tuple[str, str]:
        section = self._format_sections(fmt)[0]
        tokens = self._format_literal_tokens(section)
        numeric_indexes = [
            index
            for index, token in enumerate(tokens)
            if token[1] and token[0] in {"0", "#", "?", ".", ",", "%", "$"}
        ]
        if not numeric_indexes:
            return ("", "")
        first_numeric = numeric_indexes[0]
        last_numeric = numeric_indexes[-1]
        prefix = "".join(token for token, is_format in tokens[:first_numeric] if not is_format)
        suffix = "".join(token for token, is_format in tokens[last_numeric + 1:] if not is_format)
        return (prefix, suffix)

    def _format_literal_tokens(self, fmt: str) -> List[Tuple[str, bool]]:
        tokens: List[Tuple[str, bool]] = []
        index = 0
        while index < len(fmt):
            char = fmt[index]
            if char == '"':
                end = fmt.find('"', index + 1)
                if end == -1:
                    tokens.append((fmt[index + 1:], False))
                    break
                tokens.append((fmt[index + 1:end], False))
                index = end + 1
                continue
            if char == "\\":
                if index + 1 < len(fmt):
                    tokens.append((fmt[index + 1], False))
                    index += 2
                else:
                    index += 1
                continue
            if char == "[":
                end = fmt.find("]", index + 1)
                if end != -1:
                    tokens.append((fmt[index:end + 1], True))
                    index = end + 1
                    continue
            tokens.append((char, char in "0#?.,%$"))
            index += 1
        return tokens

    def _negative_uses_parentheses(self, fmt: str) -> bool:
        sections = self._format_sections(fmt)
        if len(sections) < 2:
            return False
        negative_section = self._format_without_literals(sections[1])
        return "(" in negative_section and ")" in negative_section

    def _format_sections(self, fmt: str) -> List[str]:
        sections = []
        current = []
        in_quote = False
        escaped = False
        for char in fmt:
            if escaped:
                current.append(char)
                escaped = False
                continue
            if char == "\\":
                current.append(char)
                escaped = True
                continue
            if char == '"':
                current.append(char)
                in_quote = not in_quote
                continue
            if char == ";" and not in_quote:
                sections.append("".join(current))
                current = []
                continue
            current.append(char)
        sections.append("".join(current))
        return sections

    def _value_text(self, cell_elem, cell_children=None) -> str:
        value = (cell_children or self._cell_children(cell_elem)).get("v")
        return value.text if value is not None and value.text is not None else ""
