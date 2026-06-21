"""Shared conversion result types for native readers."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .model.document import Document


@dataclass
class Provenance:
    source_format: str = ""
    page: Optional[int] = None
    slide: Optional[int] = None
    sheet: Optional[str] = None
    cell: Optional[str] = None
    section: Optional[int] = None
    paragraph: Optional[int] = None
    path: str = ""


@dataclass
class AssetRef:
    id: str = ""
    source_path: str = ""
    filename: str = ""
    content_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversionOptions:
    ocr: bool = False
    include_assets: bool = True


@dataclass
class ConversionResult:
    document: Document
    source_path: str = ""
    source_format: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    assets: List[AssetRef] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
