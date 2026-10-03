"""Safe helpers for Office Open XML ZIP packages."""
import posixpath
import zipfile
import zlib
from typing import List

from ..utils import safe_xml as etree


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
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        node.tag = _transitional_name(node.tag)
        for key, value in list(node.attrib.items()):
            mapped = _transitional_name(key)
            if mapped != key:
                del node.attrib[key]
                node.set(mapped, value)
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
        elif node.tag == _GRAPHIC_DATA_TAG:
            uri = node.get("uri", "")
            if uri in _STRICT_NAMESPACES:
                node.set("uri", _STRICT_NAMESPACES[uri])
    etree.map_namespaces(root, _STRICT_NAMESPACES)
    return root


def _validate_part_name(name: str) -> str:
    slash_name = name.replace("\\", "/")
    if ".." in slash_name.split("/"):
        raise ValueError(f"unsafe package path: {name}")
    normalized = posixpath.normpath(slash_name)
    parts = normalized.split("/")
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/") or ".." in parts:
        raise ValueError(f"unsafe package path: {name}")
    return normalized


def _sanitize_dtd(data: bytes) -> bytes:
    return etree.sanitize_dtd(data)


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
        needs_scopes = (b'Requires' in data or _STRICT_BASE.encode() in data or b'&#' in data)
        if not needs_scopes and b'\0' in data:
            compact = data.replace(b'\0', b'')
            needs_scopes = (b'Requires' in compact or _STRICT_BASE.encode() in compact or b'&#' in compact)
        root = etree.fromstring(data, namespaces='choices' if needs_scopes else False,
                                max_namespaces=MAX_XML_NAMESPACE_BINDINGS,
                                max_depth=2048, truncate=True, recover=recover)
        if root is not None and etree.QName(root).namespace in _STRICT_NAMESPACES:
            self._strict_parts.add(_validate_part_name(name))
        # Transitional parts need no rewriting. The exact URI prefix check is
        # only a fast-path gate; structural names alone are changed below.
        strict = any(uri.startswith(_STRICT_BASE) for uri in etree.namespace_uris(root))
        if root is not None and not strict and (_STRICT_BASE.encode() in data or b'&#' in data):
            # A Strict relationship Type or graphicData URI can occur in a
            # Transitional part without a Strict namespace declaration.
            strict = any(value.startswith(_STRICT_BASE)
                         for node in root.iter() for key, value in node.attrib.items()
                         if key in ('Type', 'uri'))
        return _normalize_strict_tree(root) if strict else root


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
