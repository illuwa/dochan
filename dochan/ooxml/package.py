"""Safe helpers for Office Open XML ZIP packages."""
import posixpath
import re
import zipfile
from typing import List

from lxml import etree


MAX_PART_SIZE = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

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

    def __enter__(self):
        self._zip = zipfile.ZipFile(self.file_path, "r")
        self._name_map = {}
        for name in self._zip.namelist():
            normalized = _validate_part_name(name)
            self._name_map.setdefault(normalized, name)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._zip:
            self._zip.close()

    def namelist(self) -> List[str]:
        return self._zip.namelist()

    def exists(self, name: str) -> bool:
        return _validate_part_name(name) in self._name_map

    def part_size(self, name: str) -> int:
        safe_name = _validate_part_name(name)
        stored_name = self._name_map.get(safe_name, safe_name)
        return self._zip.getinfo(stored_name).file_size

    def open_part(self, name: str):
        safe_name = _validate_part_name(name)
        stored_name = self._name_map.get(safe_name, safe_name)
        info = self._zip.getinfo(stored_name)
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
        return self._zip.read(stored_name)

    def read_xml_part(self, name: str, recover: bool = False):
        data = _sanitize_dtd(self.read_part(name))
        if recover:
            return etree.fromstring(data, parser=_recovery_xml_parser)
        try:
            return etree.fromstring(data, parser=_safe_xml_parser)
        except etree.XMLSyntaxError as exc:
            if "Excessive depth" not in str(exc):
                raise
            try:
                return etree.fromstring(data, parser=_deep_xml_parser)
            except etree.XMLSyntaxError as deep_exc:
                if "Excessive depth" not in str(deep_exc):
                    raise
                return etree.fromstring(data, parser=_recovery_xml_parser)


def detect_ooxml_format(file_path: str) -> str:
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = {_validate_part_name(name) for name in zf.namelist()}
    except zipfile.BadZipFile:
        return ""

    if "word/document.xml" in names:
        return "docx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    return ""
