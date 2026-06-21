# Office Native Phase 1 DOCX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first native Office document path by parsing DOCX files with dochan-owned code and routing them through the existing `Document` model.

**Architecture:** Keep HWP/HWPX behavior unchanged. Add small native conversion primitives, an OOXML ZIP/XML helper, a DOCX reader, and a narrow `Dochan` integration path for `.docx`. This first slice deliberately avoids external conversion engines and prepares the same OOXML package helper for later PPTX/XLSX work.

**Tech Stack:** Python 3.9+, standard library `zipfile`, `io`, `xml.etree` only where safe, existing `lxml.etree` safe parser pattern, existing dochan dataclasses and Markdown/JSON output modules.

## Global Constraints

- Core remains MIT/permissive-only.
- Do not add MarkItDown, Docling, Unstructured, PyMuPDF, Marker, or any runtime conversion backend.
- Do not add GPL, AGPL, SSPL, or source-available conversion dependencies.
- Preserve existing `Dochan(file_path).to_markdown()`, `to_json()`, `to_plain_text()`, `find_all()`, `metadata`, and `errors` behavior.
- Preserve current HWP/HWPX behavior and tests.
- Read before editing.
- Use TDD: write a failing test, verify it fails for the expected reason, then write implementation.
- Validation command in this workspace: `pytest dochan/tests/`.
- Do not commit automatically; stop with a clean status report unless the user explicitly asks for a commit.

---

## File Structure

- Create `dochan/conversion.py`: native conversion dataclasses that do not depend on any specific format.
- Create `dochan/ooxml/__init__.py`: package marker for Office Open XML readers.
- Create `dochan/ooxml/package.py`: safe ZIP/XML package utilities shared by DOCX, PPTX, and XLSX.
- Create `dochan/ooxml/docx.py`: DOCX native reader that converts WordprocessingML into the existing `Document` model.
- Modify `dochan/reader.py`: route `.docx` and DOCX ZIP packages to the native DOCX reader without disturbing HWP/HWPX paths.
- Modify `dochan/model/document.py`: add additive optional provenance support and metadata fields without breaking current model construction.
- Create `dochan/tests/test_ooxml_package.py`: tests for safe OOXML package loading and type detection.
- Create `dochan/tests/test_docx_reader.py`: tests for DOCX paragraphs, headings, formatting, tables, and Dochan integration.

## Task 1: Add Conversion Metadata Primitives

**Files:**
- Create: `dochan/conversion.py`
- Modify: `dochan/model/document.py`
- Test: `dochan/tests/test_conversion_model.py`

**Interfaces:**
- Produces: `Provenance`, `AssetRef`, `ConversionOptions`, `ConversionResult`
- Produces: optional `provenance` field on `TextRun`, `Paragraph`, `Section`, and `Document`
- Consumed by: DOCX reader and later PPTX/XLSX/PDF readers

- [ ] **Step 1: Write the failing test**

Create `dochan/tests/test_conversion_model.py`:

```python
from dochan.conversion import AssetRef, ConversionOptions, ConversionResult, Provenance
from dochan.model.document import Document, Paragraph, Section, TextRun


def test_provenance_defaults_are_empty_and_serializable():
    prov = Provenance(source_format="docx", section=1, paragraph=2, path="word/document.xml")

    assert prov.source_format == "docx"
    assert prov.section == 1
    assert prov.paragraph == 2
    assert prov.path == "word/document.xml"
    assert prov.page is None
    assert prov.slide is None
    assert prov.sheet is None
    assert prov.cell is None


def test_conversion_result_wraps_document_without_output_side_effects():
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun(text="Hello")])])])
    result = ConversionResult(document=doc, source_path="/tmp/sample.docx", source_format="docx")

    assert result.document.sections[0].elements[0].text == "Hello"
    assert result.source_path == "/tmp/sample.docx"
    assert result.source_format == "docx"
    assert result.metadata == {}
    assert result.assets == []
    assert result.warnings == []


def test_document_metadata_includes_source_format_when_set():
    doc = Document(source_format="docx")

    assert doc.metadata["source_format"] == "docx"


def test_asset_ref_records_package_relationship():
    asset = AssetRef(
        id="rId5",
        source_path="word/media/image1.png",
        filename="image1.png",
        content_type="image/png",
    )

    assert asset.id == "rId5"
    assert asset.source_path == "word/media/image1.png"
    assert asset.filename == "image1.png"
    assert asset.content_type == "image/png"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest dochan/tests/test_conversion_model.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'dochan.conversion'
```

- [ ] **Step 3: Write minimal implementation**

Create `dochan/conversion.py`:

```python
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
```

Modify `dochan/model/document.py` by adding `provenance` and `source_format` as optional additive fields:

```python
from dataclasses import dataclass, field
from typing import List, Optional, Any
```

```python
@dataclass
class TextRun:
    text: str = ""
    char_shape_id: int = -1
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikeout: bool = False
    superscript: bool = False
    subscript: bool = False
    font_size_pt: float = 10.0
    provenance: Any = None
```

```python
@dataclass
class Paragraph:
    runs: List[TextRun] = field(default_factory=list)
    para_shape_id: int = -1
    style_id: int = -1
    heading_level: int = 0
    provenance: Any = None
```

```python
@dataclass
class Section:
    elements: List[Any] = field(default_factory=list)
    provenance: Any = None
```

```python
@dataclass
class Document:
    sections: List[Section] = field(default_factory=list)
    char_shapes: list = field(default_factory=list)
    para_shapes: list = field(default_factory=list)
    styles: list = field(default_factory=list)
    face_names: list = field(default_factory=list)
    bin_data_list: list = field(default_factory=list)
    file_header: Any = None
    errors: List[str] = field(default_factory=list)
    source_format: str = ""
    provenance: Any = None
```

Update `Document.metadata`:

```python
    @property
    def metadata(self) -> dict:
        metadata = {
            'sections': len(self.sections),
            'char_shapes': len(self.char_shapes),
            'para_shapes': len(self.para_shapes),
            'styles': len(self.styles),
            'face_names': len(self.face_names),
            'errors': self.errors,
        }
        if self.source_format:
            metadata['source_format'] = self.source_format
        return metadata
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest dochan/tests/test_conversion_model.py -v
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Run existing tests**

Run:

```bash
pytest dochan/tests/
```

Expected:

```text
24 passed
```

- [ ] **Step 6: Review without committing**

Run:

```bash
git diff -- dochan/conversion.py dochan/model/document.py dochan/tests/test_conversion_model.py
git status --short
```

Expected: only intended files changed or added. Do not commit automatically.

## Task 2: Add Safe OOXML Package Utilities

**Files:**
- Create: `dochan/ooxml/__init__.py`
- Create: `dochan/ooxml/package.py`
- Test: `dochan/tests/test_ooxml_package.py`

**Interfaces:**
- Produces: `OOXMLPackage`
- Produces: `detect_ooxml_format(file_path: str) -> str`
- Produces: `read_xml_part(part_name: str) -> etree._Element`
- Consumed by: DOCX, PPTX, XLSX native readers

- [ ] **Step 1: Write the failing test**

Create `dochan/tests/test_ooxml_package.py`:

```python
import io
import zipfile

import pytest

from dochan.ooxml.package import OOXMLPackage, detect_ooxml_format


def _write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_detects_docx_from_package_entries(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<w:document xmlns:w='w'/>"})

    assert detect_ooxml_format(str(path)) == "docx"


def test_detects_pptx_from_package_entries(tmp_path):
    path = tmp_path / "sample.pptx"
    _write_zip(path, {"ppt/presentation.xml": "<p:presentation xmlns:p='p'/>"})

    assert detect_ooxml_format(str(path)) == "pptx"


def test_detects_xlsx_from_package_entries(tmp_path):
    path = tmp_path / "sample.xlsx"
    _write_zip(path, {"xl/workbook.xml": "<workbook/>"})

    assert detect_ooxml_format(str(path)) == "xlsx"


def test_unknown_zip_returns_empty_format(tmp_path):
    path = tmp_path / "sample.zip"
    _write_zip(path, {"data/file.txt": "hello"})

    assert detect_ooxml_format(str(path)) == ""


def test_reads_xml_part_with_xxe_disabled(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<root><child>ok</child></root>"})

    with OOXMLPackage(str(path)) as package:
        root = package.read_xml_part("word/document.xml")

    assert root.tag == "root"
    assert root.find("child").text == "ok"


def test_rejects_path_traversal_part_name(tmp_path):
    path = tmp_path / "sample.docx"
    _write_zip(path, {"word/document.xml": "<root/>"})

    with OOXMLPackage(str(path)) as package:
        with pytest.raises(ValueError, match="unsafe package path"):
            package.read_part("../evil.xml")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest dochan/tests/test_ooxml_package.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'dochan.ooxml'
```

- [ ] **Step 3: Write minimal implementation**

Create `dochan/ooxml/__init__.py`:

```python
"""Native Office Open XML readers."""
```

Create `dochan/ooxml/package.py`:

```python
"""Safe helpers for Office Open XML ZIP packages."""
import posixpath
import zipfile
from typing import List

from lxml import etree


MAX_PART_SIZE = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

_safe_xml_parser = etree.XMLParser(resolve_entities=False, no_network=True)


def _validate_part_name(name: str) -> str:
    normalized = posixpath.normpath(name).replace("\\", "/")
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        raise ValueError(f"unsafe package path: {name}")
    return normalized


class OOXMLPackage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._zip = None

    def __enter__(self):
        self._zip = zipfile.ZipFile(self.file_path, "r")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._zip:
            self._zip.close()

    def namelist(self) -> List[str]:
        return self._zip.namelist()

    def exists(self, name: str) -> bool:
        return _validate_part_name(name) in self._zip.namelist()

    def read_part(self, name: str) -> bytes:
        safe_name = _validate_part_name(name)
        info = self._zip.getinfo(safe_name)
        if info.file_size > MAX_PART_SIZE:
            raise ValueError(f"package part too large: {safe_name}")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError(f"package part compression ratio too high: {safe_name}")
        return self._zip.read(safe_name)

    def read_xml_part(self, name: str):
        return etree.fromstring(self.read_part(name), parser=_safe_xml_parser)


def detect_ooxml_format(file_path: str) -> str:
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return ""

    if "word/document.xml" in names:
        return "docx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest dochan/tests/test_ooxml_package.py -v
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Run existing tests**

Run:

```bash
pytest dochan/tests/
```

Expected:

```text
30 passed
```

- [ ] **Step 6: Review without committing**

Run:

```bash
git diff -- dochan/ooxml dochan/tests/test_ooxml_package.py
git status --short
```

Expected: only intended files changed or added. Do not commit automatically.

## Task 3: Add DOCX Paragraph, Heading, and Run Parsing

**Files:**
- Create: `dochan/ooxml/docx.py`
- Test: `dochan/tests/test_docx_reader.py`

**Interfaces:**
- Consumes: `OOXMLPackage`
- Produces: `DOCXReader.read(file_path: str) -> Document`
- Consumed by: `Dochan` integration in Task 5

- [ ] **Step 1: Write the failing tests**

Create `dochan/tests/test_docx_reader.py`:

```python
import zipfile

from dochan.ooxml.docx import DOCXReader


def _write_docx(path, document_xml, styles_xml=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", document_xml)
        if styles_xml:
            zf.writestr("word/styles.xml", styles_xml)


def test_reads_simple_docx_paragraph(tmp_path):
    path = tmp_path / "simple.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    doc = DOCXReader().read(str(path))

    assert doc.source_format == "docx"
    assert doc.sections[0].elements[0].text == "Hello DOCX"
    assert doc.sections[0].elements[0].provenance.source_format == "docx"
    assert doc.sections[0].elements[0].provenance.path == "word/document.xml"


def test_reads_bold_and_italic_runs(tmp_path):
    path = tmp_path / "runs.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:rPr><w:b/></w:rPr><w:t>Bold</w:t></w:r>
          <w:r><w:t> and </w:t></w:r>
          <w:r><w:rPr><w:i/></w:rPr><w:t>Italic</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.runs[0].text == "Bold"
    assert para.runs[0].bold
    assert para.runs[1].text == " and "
    assert para.runs[2].text == "Italic"
    assert para.runs[2].italic


def test_detects_heading_from_paragraph_style(tmp_path):
    path = tmp_path / "heading.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
          <w:r><w:t>Title</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """)

    para = DOCXReader().read(str(path)).sections[0].elements[0]

    assert para.text == "Title"
    assert para.heading_level == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest dochan/tests/test_docx_reader.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'dochan.ooxml.docx'
```

- [ ] **Step 3: Write minimal implementation**

Create `dochan/ooxml/docx.py`:

```python
"""Native DOCX reader."""
from typing import List

from ..conversion import Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from .package import OOXMLPackage

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _w_attr(elem, name: str) -> str:
    return elem.get(f"{{{W_NS}}}{name}", "")


class DOCXReader:
    format_name = "docx"
    extensions = (".docx",)

    def read(self, file_path: str) -> Document:
        doc = Document(source_format="docx")
        with OOXMLPackage(file_path) as package:
            root = package.read_xml_part("word/document.xml")

        section = Section(provenance=Provenance(source_format="docx", section=0, path="word/document.xml"))
        body = root.find("w:body", namespaces=NS)
        if body is None:
            doc.errors.append("ERR: DOCX body not found")
            doc.sections.append(section)
            return doc

        paragraph_index = 0
        for child in body:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(child, paragraph_index)
                paragraph_index += 1
                if para.text.strip():
                    section.elements.append(para)

        doc.sections.append(section)
        return doc

    def _parse_paragraph(self, p_elem, paragraph_index: int) -> Paragraph:
        para = Paragraph(provenance=Provenance(
            source_format="docx",
            section=0,
            paragraph=paragraph_index,
            path="word/document.xml",
        ))
        para.heading_level = self._heading_level(p_elem)
        para.runs = self._parse_runs(p_elem)
        return para

    def _heading_level(self, p_elem) -> int:
        p_style = p_elem.find("w:pPr/w:pStyle", namespaces=NS)
        style = _w_attr(p_style, "val") if p_style is not None else ""
        lower = style.lower()
        if lower.startswith("heading"):
            suffix = lower.replace("heading", "", 1)
            if suffix.isdigit():
                return max(1, min(int(suffix), 6))
            return 1
        return 0

    def _parse_runs(self, p_elem) -> List[TextRun]:
        runs = []
        for r_elem in p_elem.findall("w:r", namespaces=NS):
            text = "".join(t.text or "" for t in r_elem.findall("w:t", namespaces=NS))
            if not text:
                continue
            r_pr = r_elem.find("w:rPr", namespaces=NS)
            run = TextRun(text=text)
            if r_pr is not None:
                run.bold = r_pr.find("w:b", namespaces=NS) is not None
                run.italic = r_pr.find("w:i", namespaces=NS) is not None
                run.underline = r_pr.find("w:u", namespaces=NS) is not None
                run.strikeout = r_pr.find("w:strike", namespaces=NS) is not None
            runs.append(run)
        return runs
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest dochan/tests/test_docx_reader.py -v
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Run existing tests**

Run:

```bash
pytest dochan/tests/
```

Expected:

```text
33 passed
```

- [ ] **Step 6: Review without committing**

Run:

```bash
git diff -- dochan/ooxml/docx.py dochan/tests/test_docx_reader.py
git status --short
```

Expected: only intended files changed or added. Do not commit automatically.

## Task 4: Add DOCX Table Parsing

**Files:**
- Modify: `dochan/ooxml/docx.py`
- Modify: `dochan/tests/test_docx_reader.py`

**Interfaces:**
- Consumes: `DOCXReader._parse_paragraph`
- Produces: `Table` elements in `Document.sections[0].elements`
- Consumed by: existing Markdown and JSON output modules

- [ ] **Step 1: Write the failing test**

Append to `dochan/tests/test_docx_reader.py`:

```python
def test_reads_docx_table_as_document_table(tmp_path):
    path = tmp_path / "table.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:tr>
            <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
      </w:body>
    </w:document>
    """)

    table = DOCXReader().read(str(path)).sections[0].elements[0]

    assert table.row_count == 2
    assert table.col_count == 2
    assert table.rows[0][0].text == "Name"
    assert table.rows[1][1].text == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest dochan/tests/test_docx_reader.py::test_reads_docx_table_as_document_table -v
```

Expected:

```text
IndexError: list index out of range
```

or a failure showing no table element is produced.

- [ ] **Step 3: Write minimal implementation**

Modify imports in `dochan/ooxml/docx.py`:

```python
from ..model.table import Cell, Table
```

Modify `DOCXReader.read` child loop:

```python
        for child in body:
            if child.tag == f"{{{W_NS}}}p":
                para = self._parse_paragraph(child, paragraph_index)
                paragraph_index += 1
                if para.text.strip():
                    section.elements.append(para)
            elif child.tag == f"{{{W_NS}}}tbl":
                section.elements.append(self._parse_table(child, paragraph_index))
```

Add methods:

```python
    def _parse_table(self, tbl_elem, paragraph_index: int) -> Table:
        rows = []
        for tr_elem in tbl_elem.findall("w:tr", namespaces=NS):
            row = []
            for tc_elem in tr_elem.findall("w:tc", namespaces=NS):
                cell_paragraphs = []
                for p_elem in tc_elem.findall("w:p", namespaces=NS):
                    para = self._parse_paragraph(p_elem, paragraph_index)
                    paragraph_index += 1
                    if para.text.strip():
                        cell_paragraphs.append(para)
                row.append(Cell(paragraphs=cell_paragraphs))
            rows.append(row)
        return Table(rows=rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest dochan/tests/test_docx_reader.py::test_reads_docx_table_as_document_table -v
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run all DOCX tests**

Run:

```bash
pytest dochan/tests/test_docx_reader.py -v
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Review without committing**

Run:

```bash
git diff -- dochan/ooxml/docx.py dochan/tests/test_docx_reader.py
git status --short
```

Expected: only intended files changed or added. Do not commit automatically.

## Task 5: Route DOCX Through Dochan

**Files:**
- Modify: `dochan/reader.py`
- Modify: `dochan/tests/test_docx_reader.py`

**Interfaces:**
- Consumes: `detect_ooxml_format(file_path) -> str`
- Consumes: `DOCXReader().read(file_path) -> Document`
- Produces: `Dochan("file.docx").to_markdown()`

- [ ] **Step 1: Write the failing integration test**

Append to `dochan/tests/test_docx_reader.py`:

```python
from dochan import Dochan


def test_dochan_routes_docx_to_native_reader(tmp_path):
    path = tmp_path / "integrated.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
          <w:r><w:t>Office Title</w:t></w:r>
        </w:p>
        <w:p><w:r><w:t>Body text</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    doc = Dochan(str(path))

    assert doc.metadata["source_format"] == "docx"
    assert doc.to_markdown() == "# Office Title\n\nBody text"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest dochan/tests/test_docx_reader.py::test_dochan_routes_docx_to_native_reader -v
```

Expected:

```text
AssertionError
```

or a failure showing `.docx` was not routed to `DOCXReader`.

- [ ] **Step 3: Write minimal implementation**

Modify imports in `dochan/reader.py`:

```python
from .ooxml.package import detect_ooxml_format
from .ooxml.docx import DOCXReader
```

Modify `_parse`:

```python
    def _parse(self):
        ext = os.path.splitext(self.file_path)[1].lower()

        if ext == '.hwpx':
            self._parse_hwpx()
        elif ext == '.hwp':
            self._parse_hwp()
        elif ext == '.docx':
            self._parse_docx()
        else:
            with open(self.file_path, 'rb') as f:
                magic = f.read(8)
            if magic[:4] == b'\xd0\xcf\x11\xe0':
                self._parse_hwp()
            elif magic[:2] == b'PK':
                ooxml_format = detect_ooxml_format(self.file_path)
                if ooxml_format == "docx":
                    self._parse_docx()
                elif ooxml_format:
                    self.doc.errors.append(f"ERR: 아직 지원하지 않는 OOXML 형식: {ooxml_format}")
                else:
                    self._parse_hwpx()
            else:
                self.doc.errors.append(f"ERR: 알 수 없는 파일 형식: {self.file_path}")
```

Add method:

```python
    def _parse_docx(self):
        """DOCX (Office Open XML) 파싱"""
        self.doc = DOCXReader().read(self.file_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest dochan/tests/test_docx_reader.py::test_dochan_routes_docx_to_native_reader -v
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run all tests**

Run:

```bash
pytest dochan/tests/
```

Expected:

```text
35 passed
```

- [ ] **Step 6: Review without committing**

Run:

```bash
git diff -- dochan/reader.py dochan/ooxml dochan/tests/test_docx_reader.py
git status --short
```

Expected: only intended files changed or added. Do not commit automatically.

## Task 6: Add CLI and Batch Awareness for DOCX

**Files:**
- Modify: `dochan/batch.py`
- Modify: `dochan/tests/test_docx_reader.py`

**Interfaces:**
- Consumes: `Dochan("file.docx")`
- Produces: batch conversion includes `.docx`

- [ ] **Step 1: Write the failing batch test**

Append to `dochan/tests/test_docx_reader.py`:

```python
from dochan.batch import batch_convert


def test_batch_convert_includes_docx_by_default(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    path = input_dir / "doc.docx"
    _write_docx(path, """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Batch DOCX</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """)

    summary = batch_convert(str(input_dir), str(output_dir), output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "doc.md").read_text(encoding="utf-8") == "Batch DOCX"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest dochan/tests/test_docx_reader.py::test_batch_convert_includes_docx_by_default -v
```

Expected:

```text
assert 0 == 1
```

- [ ] **Step 3: Write minimal implementation**

Modify `batch_convert` default extensions in `dochan/batch.py`:

```python
    extensions: tuple = ('.hwp', '.hwpx', '.docx'),
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest dochan/tests/test_docx_reader.py::test_batch_convert_includes_docx_by_default -v
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run all tests**

Run:

```bash
pytest dochan/tests/
```

Expected:

```text
36 passed
```

- [ ] **Step 6: Review without committing**

Run:

```bash
git diff -- dochan/batch.py dochan/tests/test_docx_reader.py
git status --short
```

Expected: only intended files changed or added. Do not commit automatically.

## Task 7: Documentation Update for DOCX Native Support

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md`

**Interfaces:**
- Consumes: implemented DOCX native support
- Produces: user-facing description that `.docx` is supported natively in this phase

- [ ] **Step 1: Write documentation diff**

Update README feature table from:

```markdown
| **HWP + HWPX** | 바이너리(.hwp)와 XML(.hwpx) 모두 자동 감지 파싱 |
```

to:

```markdown
| **HWP + HWPX + DOCX** | HWP/HWPX와 Word OOXML(.docx)을 native parser로 자동 감지 파싱 |
```

Add CLI example:

```markdown
# Word DOCX 변환
dochan convert 문서.docx
```

Update supported elements table by adding DOCX column if the table is still maintained. Mark only implemented items:

```markdown
| 요소 | HWP (바이너리) | HWPX (XML) | DOCX |
|------|:-:|:-:|:-:|
| 텍스트 | ✅ | ✅ | ✅ |
| 표 (단순) | ✅ | ✅ | ✅ |
| 서식 (bold/italic) | ✅ | ✅ | ✅ |
| 제목 감지 | ✅ | ✅ | ✅ |
| 이미지 참조 | ✅ | ✅ | ⬜ |
| 수식 | ✅ | ✅ | ⬜ |
```

- [ ] **Step 2: Verify docs mention no external runtime backend**

Run:

```bash
rg -n "MarkItDown|Docling|PyMuPDF|external backend|runtime backend" README.md docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md
```

Expected: README has no external backend claims; spec only contains native-only/external comparison language.

- [ ] **Step 3: Run all tests**

Run:

```bash
pytest dochan/tests/
```

Expected:

```text
36 passed
```

- [ ] **Step 4: Review without committing**

Run:

```bash
git diff -- README.md docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md
git status --short
```

Expected: only intended docs changed. Do not commit automatically.

## Self-Review Checklist

- Spec coverage: This plan covers the first native Office implementation slice: shared conversion metadata, safe OOXML package reading, DOCX paragraphs/runs/headings/tables, Dochan integration, batch support, and documentation. PPTX/XLSX/PDF remain later implementation plans.
- Native-only constraint: No task adds external conversion dependencies or runtime backends.
- License constraint: No new dependency is introduced.
- API compatibility: `Dochan` public methods stay unchanged.
- TDD coverage: Every code task starts with a failing test and explicit expected failure.
- Validation: Every task ends with targeted test and full `pytest dochan/tests/`.
- Commit policy: Every task explicitly says not to commit automatically.

