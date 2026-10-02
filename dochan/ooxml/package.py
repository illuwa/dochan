"""Safe helpers for Office Open XML ZIP packages."""
import posixpath
import re
import zipfile
import zlib
from copy import deepcopy
from typing import List

from lxml import etree


MAX_PART_SIZE = 100 * 1024 * 1024
MAX_XML_PART_SIZE = 32 * 1024 * 1024
MAX_XML_ELEMENTS = 1000000
MAX_XML_NAMESPACE_BINDINGS = 1000000
# Valid Office packages can contain highly compressible XML or bitmap parts.
# The absolute per-part and archive budgets remain the primary allocation caps;
# this ratio is a secondary signal and therefore intentionally conservative.
MAX_COMPRESSION_RATIO = 2000
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10000

_safe_xml_parser = etree.XMLParser(resolve_entities=False, no_network=True)
_deep_xml_parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
_recovery_xml_parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    huge_tree=True,
    recover=True,
)
_doctype_with_subset_re = re.compile(br"<!DOCTYPE\b[^[]*\[[\s\S]*?\]\s*>", re.IGNORECASE)
_doctype_without_subset_re = re.compile(br"<!DOCTYPE\b[^>]*>", re.IGNORECASE)
_named_entity_ref_re = re.compile(br"&([A-Za-z_][A-Za-z0-9_.:-]*);")
_xml_predefined_entities = {b"amp", b"lt", b"gt", b"apos", b"quot"}

# ISO/IEC 29500-1 namespace names -> the Part 4 names used by our readers.
# These are exact URI mappings, not a replacement of user text or ZIP bytes.
_STRICT_BASE = "http://purl.oclc.org/ooxml/"
_TRANSITIONAL_BASE = "http://schemas.openxmlformats.org/"
_STRICT_NAMESPACES = {
    _STRICT_BASE + name: _TRANSITIONAL_BASE + target
    for name, target in (
        ("wordprocessingml/main", "wordprocessingml/2006/main"),
        ("spreadsheetml/main", "spreadsheetml/2006/main"),
        ("presentationml/main", "presentationml/2006/main"),
        ("drawingml/main", "drawingml/2006/main"),
        ("drawingml/chart", "drawingml/2006/chart"),
        ("drawingml/chartDrawing", "drawingml/2006/chartDrawing"),
        ("drawingml/diagram", "drawingml/2006/diagram"),
        ("drawingml/lockedCanvas", "drawingml/2006/lockedCanvas"),
        ("drawingml/picture", "drawingml/2006/picture"),
        ("drawingml/spreadsheetDrawing", "drawingml/2006/spreadsheetDrawing"),
        ("drawingml/wordprocessingDrawing", "drawingml/2006/wordprocessingDrawing"),
        ("officeDocument/math", "officeDocument/2006/math"),
        ("officeDocument/relationships", "officeDocument/2006/relationships"),
        ("officeDocument/extendedProperties", "officeDocument/2006/extended-properties"),
        ("officeDocument/customProperties", "officeDocument/2006/custom-properties"),
        ("officeDocument/docPropsVTypes", "officeDocument/2006/docPropsVTypes"),
        ("officeDocument/customXml", "officeDocument/2006/customXml"),
        ("officeDocument/bibliography", "officeDocument/2006/bibliography"),
    )
}
_STRICT_RELATIONSHIP = _STRICT_BASE + "officeDocument/relationships/"
_TRANSITIONAL_RELATIONSHIP = _TRANSITIONAL_BASE + "officeDocument/2006/relationships/"
_RELATIONSHIP_TAG = "{" + _TRANSITIONAL_BASE + "package/2006/relationships}Relationship"
_GRAPHIC_DATA_TAG = "{" + _TRANSITIONAL_BASE + "drawingml/2006/main}graphicData"


def _transitional_name(name: str) -> str:
    if name.startswith("{"):
        namespace, local_name = name[1:].split("}", 1)
        mapped = _STRICT_NAMESPACES.get(namespace)
        if mapped:
            return "{" + mapped + "}" + local_name
    return name


def _normalize_strict_tree(root):
    if root is None:
        return root
    strict_namespaces = False
    namespace_bindings = 0

    # start-ns reports local declarations, unlike node.nsmap which repeatedly
    # materializes all inherited bindings (namespace-count x element-count).
    for event, node in etree.iterwalk(root, events=("start-ns", "start")):
        if event == "start-ns":
            namespace_bindings += 1
            if namespace_bindings > MAX_XML_NAMESPACE_BINDINGS:
                raise ValueError("package XML namespace limit exceeded")
            strict_namespaces = strict_namespaces or node[1] in _STRICT_NAMESPACES
            continue
        if not isinstance(node.tag, str):
            continue
        if node.tag == _RELATIONSHIP_TAG:
            kind = node.get("Type", "")
            if kind.startswith(_STRICT_RELATIONSHIP):
                suffix = kind[len(_STRICT_RELATIONSHIP):]
                if suffix == "metadata/thumbnail":
                    kind = _TRANSITIONAL_BASE + "package/2006/relationships/" + suffix
                else:
                    suffix = {"extendedProperties": "extended-properties",
                              "customProperties": "custom-properties"}.get(suffix, suffix)
                    kind = _TRANSITIONAL_RELATIONSHIP + suffix
                node.set("Type", kind)
        elif _transitional_name(node.tag) == _GRAPHIC_DATA_TAG:
            uri = node.get("uri", "")
            if uri in _STRICT_NAMESPACES:
                node.set("uri", _STRICT_NAMESPACES[uri])
    if not strict_namespaces:
        return root

    def copy_element(node, nsmap, parent=None):
        # Preserve prefix bindings as well as expanded names: mc:Choice Requires
        # and QName-valued attributes use the original (possibly rebound) prefix.
        attributes = {_transitional_name(name): value for name, value in node.attrib.items()}
        tag = _transitional_name(node.tag)
        if parent is None:
            result = etree.Element(tag, attrib=attributes, nsmap=nsmap)
        else:
            result = etree.SubElement(parent, tag, attrib=attributes, nsmap=nsmap)
        result.text, result.tail = node.text, node.tail
        return result

    # Iterative depth-first copying avoids Python recursion on recovered XML.
    # The same part-size and element limits apply before this transformation.
    normalized = None
    stack = []
    nsmap = {}
    for event, node in etree.iterwalk(root, events=("start-ns", "start", "end", "comment", "pi")):
        if event == "start-ns":
            prefix, uri = node
            nsmap[prefix or None] = _STRICT_NAMESPACES.get(uri, uri)
        elif event == "start":
            if isinstance(node.tag, str):
                copied = copy_element(node, nsmap, stack[-1] if stack else None)
            else:
                # Unresolved entities can produce start/end events too. Keep
                # them opaque just as resolve_entities=False requested.
                copied = deepcopy(node)
                stack[-1].append(copied)
            if normalized is None:
                normalized = copied
            stack.append(copied)
            nsmap = {}
        elif event == "end":
            stack.pop()
        elif stack:
            stack[-1].append(deepcopy(node))
    return normalized


def _validate_part_name(name: str) -> str:
    slash_name = name.replace("\\", "/")
    if ".." in slash_name.split("/"):
        raise ValueError(f"unsafe package path: {name}")
    normalized = posixpath.normpath(slash_name)
    parts = normalized.split("/")
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/") or ".." in parts:
        raise ValueError(f"unsafe package path: {name}")
    return normalized


def _neutralize_custom_entities(data: bytes) -> bytes:
    def replace(match: re.Match[bytes]) -> bytes:
        if match.group(1) in _xml_predefined_entities:
            return match.group(0)
        return b""

    return _named_entity_ref_re.sub(replace, data)


def _sanitize_dtd(data: bytes) -> bytes:
    if b"<!DOCTYPE" not in data.upper():
        return data
    data = _doctype_with_subset_re.sub(b"", data)
    data = _doctype_without_subset_re.sub(b"", data)
    return _neutralize_custom_entities(data)


class OOXMLPackage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._zip = None
        self._name_map = {}
        self._strict_parts = set()

    def __enter__(self):
        self._zip = zipfile.ZipFile(self.file_path, "r")
        self._name_map = {}
        self._strict_parts = set()
        try:
            infos = self._zip.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError(
                    f"package has too many entries: {len(infos)} > {MAX_ARCHIVE_ENTRIES}"
                )
            total_size = sum(info.file_size for info in infos)
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                raise ValueError(
                    "package total uncompressed size too large: "
                    f"{total_size} > {MAX_ARCHIVE_UNCOMPRESSED_SIZE}"
                )
            for info in infos:
                normalized = _validate_part_name(info.filename)
                if normalized in self._name_map:
                    raise ValueError(f"duplicate package part name: {normalized}")
                self._name_map[normalized] = info.filename
            return self
        except Exception:
            self._zip.close()
            self._zip = None
            raise

    def __exit__(self, exc_type, exc, tb):
        if self._zip:
            self._zip.close()
        self._zip = None
        # 차트 resolver가 보관한 내장 ZIP 바이트와 희소 셀 캐시도 문서와 함께 해제한다.
        self._chart_reference_state = None

    def namelist(self) -> List[str]:
        return self._zip.namelist()

    def exists(self, name: str) -> bool:
        return _validate_part_name(name) in self._name_map

    def part_size(self, name: str) -> int:
        safe_name = _validate_part_name(name)
        stored_name = self._name_map.get(safe_name, safe_name)
        return self._zip.getinfo(stored_name).file_size

    def is_strict_part(self, name: str) -> bool:
        """Whether an XML part already read had a Strict root namespace."""
        return _validate_part_name(name) in self._strict_parts

    def open_part(self, name: str):
        safe_name = _validate_part_name(name)
        stored_name = self._name_map.get(safe_name, safe_name)
        info = self._zip.getinfo(stored_name)
        if info.file_size > MAX_PART_SIZE:
            raise ValueError(f"package part too large: {safe_name}")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError(f"package part compression ratio too high: {safe_name}")
        return self._zip.open(stored_name)

    def read_part(self, name: str) -> bytes:
        safe_name = _validate_part_name(name)
        stored_name = self._name_map.get(safe_name, safe_name)
        info = self._zip.getinfo(stored_name)
        if info.file_size > MAX_PART_SIZE:
            raise ValueError(f"package part too large: {safe_name}")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError(f"package part compression ratio too high: {safe_name}")
        try:
            return self._zip.read(stored_name)
        except (zlib.error, RuntimeError, NotImplementedError, EOFError) as exc:
            raise ValueError(f"package part could not be decoded: {safe_name}: {exc}") from exc

    def read_xml_part(self, name: str, recover: bool = False):
        if self.part_size(name) > MAX_XML_PART_SIZE:
            raise ValueError(f"package XML part too large: {_validate_part_name(name)}")
        data = _sanitize_dtd(self.read_part(name))
        if data.count(b"<") > MAX_XML_ELEMENTS:
            raise ValueError(f"package XML element limit exceeded: {_validate_part_name(name)}")
        if recover:
            root = etree.fromstring(data, parser=_recovery_xml_parser)
        else:
            try:
                root = etree.fromstring(data, parser=_safe_xml_parser)
            except etree.XMLSyntaxError as exc:
                if "Excessive depth" not in str(exc):
                    raise
                try:
                    root = etree.fromstring(data, parser=_deep_xml_parser)
                except etree.XMLSyntaxError as deep_exc:
                    if "Excessive depth" not in str(deep_exc):
                        raise
                    root = etree.fromstring(data, parser=_recovery_xml_parser)
        if root is not None and etree.QName(root).namespace in _STRICT_NAMESPACES:
            self._strict_parts.add(_validate_part_name(name))
        return _normalize_strict_tree(root)


def detect_ooxml_format(file_path: str) -> str:
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            if len(zf.filelist) > MAX_ARCHIVE_ENTRIES:
                return ""
            names = {_validate_part_name(name) for name in zf.namelist()}
    except (OSError, ValueError, zipfile.BadZipFile):
        return ""

    detected = []
    if "word/document.xml" in names:
        detected.append("docx")
    if "ppt/presentation.xml" in names:
        detected.append("pptx")
    if "xl/workbook.xml" in names:
        detected.append("xlsx")
    if len(detected) > 1:
        return "ambiguous"
    return detected[0] if detected else ""
