"""Shared OOXML package metadata helpers."""
from typing import Dict, List

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from .package import OOXMLPackage

DC_NS = "http://purl.org/dc/elements/1.1/"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS = {"dc": DC_NS, "cp": CP_NS}


def read_core_properties(package: OOXMLPackage) -> Dict[str, str]:
    if not package.exists("docProps/core.xml"):
        return {}
    root = package.read_xml_part("docProps/core.xml")
    return {
        "title": _child_text(root, "dc:title"),
        "creator": _child_text(root, "dc:creator"),
    }


def core_property_elements(core_properties: Dict[str, str], source_format: str) -> List[Paragraph]:
    elements = []
    title = core_properties.get("title", "")
    if title:
        elements.append(
            Paragraph(
                runs=[TextRun(title)],
                heading_level=1,
                provenance=Provenance(source_format=source_format, path="docProps/core.xml"),
            )
        )
    creator = core_properties.get("creator", "")
    if creator:
        elements.append(
            Paragraph(
                runs=[TextRun(f"Author: {creator}")],
                provenance=Provenance(source_format=source_format, path="docProps/core.xml"),
            )
        )
    return elements


def _child_text(elem, path: str) -> str:
    child = elem.find(path, namespaces=NS)
    return (child.text or "").strip() if child is not None else ""
