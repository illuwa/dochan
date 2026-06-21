# Native Universal Document Conversion Design

## Purpose

dochan should become a Korean-first universal document converter that can process common office and document formats from one Python package while preserving its own MIT-licensed, native-only conversion identity.

The target is not to wrap external converters. The target is to grow dochan's own parsing and normalization layer so HWP, HWPX, legacy Office, Office Open XML, and PDF can all flow into the same internal model and export clean Markdown, JSON, and plain text for LLM/RAG use.

## Product Position

dochan should be positioned as:

> A native-only, permissively licensed document-to-Markdown/JSON converter with first-class Korean HWP/HWPX, Office Open XML, and PDF support.

This creates a clearer identity than "another MarkItDown wrapper":

- HWP/HWPX remain first-class native formats.
- OOXML formats are implemented directly from the ZIP/XML package structure.
- Legacy Office binary formats are implemented directly from OLE compound streams and BIFF/PPT/DOC records where practical.
- Markdown output remains optimized for AI/LLM ingestion.
- JSON output preserves structure and provenance for citation, review, and downstream automation.
- External engines are not part of the product path.

## License Policy

The dochan core must remain safe for MIT distribution.

Core dependency rules:

- Allowed in core: MIT, BSD, Apache-2.0, similarly permissive licenses.
- Excluded from core: GPL, AGPL, SSPL, source-available commercial licenses, or dependencies that would force dochan or downstream users into reciprocal source disclosure.
- Runtime backend integrations are outside this design. dochan should not depend on external conversion engines to satisfy supported format claims.
- AGPL/GPL engines must not be added as normal Python dependencies, even optional extras, unless the project deliberately changes license strategy later.

Current core status:

- dochan is MIT licensed.
- Existing required dependencies are permissive:
  - `olefile`: BSD
  - `lxml`: BSD
  - `pyyaml`: MIT
- Existing optional OCR dependencies are permissive enough for optional use:
  - `pytesseract`: Apache-2.0
  - `Pillow`: MIT-CMU style permissive license

External engine assessment:

- MarkItDown: MIT, useful as an external comparison point for output quality and format coverage, but not a runtime backend.
- Docling: MIT codebase, useful as an external comparison point for layout/PDF behavior, but not a runtime backend.
- Unstructured: Apache-2.0 project, useful as an external comparison point for broad ingestion, but not a runtime backend.
- PyMuPDF/PyMuPDF4LLM: AGPL/commercial dual license; exclude from dochan core and normal extras.
- Marker: GPL-3.0/commercial; exclude from dochan core and normal extras.

## Scope

### In Scope

- Preserve existing HWP/HWPX behavior.
- Introduce a common conversion result model that can represent multiple source formats.
- Add native readers for modern Office Open XML formats:
  - `.docx`
  - `.pptx`
  - `.xlsx`
- Add native readers for legacy Office binary formats:
  - `.doc`
  - `.ppt`
  - `.xls`
- Add a native PDF reader roadmap:
  - Phase 1: first-party PDF tokenizer/object parser sufficient for simple digital text extraction.
  - Phase 2: first-party page content stream interpretation, text positioning, and reading order.
  - Phase 3: first-party layout, table, image, and OCR strategy as separate research-backed milestones.
- Keep Markdown, JSON, and plain text outputs.
- Preserve provenance metadata:
  - source file path
  - format
  - page number for PDFs
  - slide number for PPTX
  - sheet name and cell/range for XLSX
  - section/paragraph/table references where available
- Maintain security posture:
  - zip bomb checks
  - XML external entity protection
  - path traversal prevention
  - bounded memory use

### Out of Scope for the First Native Roadmap

- Pixel-perfect Office rendering.
- Round-trip editing back into DOCX/PPTX/XLSX.
- Full PDF layout reconstruction.
- Cloud OCR/VLM integration.
- Audio/video transcription.
- ZIP archive recursive conversion.
- Email formats such as EML/MSG.
- CAD/GIS formats.
- Runtime use of external conversion engines.

## External Evidence Summary

Community and ecosystem research points to these requirements:

- Users want one conversion entry point for DOCX, PPTX, PDF, XLSX, images, and text-like formats.
- RAG users care about more than Markdown text. They need provenance: page numbers, bounding boxes, slide numbers, sheet/cell positions, and element types.
- Complex PDFs cannot be solved well by a single simple text extractor. Digital PDFs, scanned PDFs, and table-heavy PDFs need different strategies.
- Existing broad converters are useful external references but must not become dochan backends:
  - MarkItDown is broad and MIT licensed, but is primarily LLM-oriented conversion, not high-fidelity parsing.
  - Docling is strong for layout and PDF understanding, but is heavier and has Python/runtime constraints.
  - Unstructured is broad but operationally heavy.
  - PyMuPDF and Marker have license constraints that are not suitable for dochan core.
- Korean document workflows still need strong HWP/HWPX support; this is dochan's durable advantage.

## Architecture

### Conversion Pipeline

```text
input file
  -> format detector
  -> native reader
  -> normalized Document model
  -> ConversionResult
  -> Markdown / JSON / plain text outputs
```

### Core Interfaces

Add a reader abstraction that lets each format parser share a common contract.

```python
class DocumentReader:
    format_name: str
    extensions: tuple[str, ...]

    def can_read(self, file_path: str, magic: bytes) -> bool:
        ...

    def read(self, file_path: str, options: ConversionOptions) -> ConversionResult:
        ...
```

Add a conversion result wrapper around the existing `Document`.

```python
@dataclass
class ConversionResult:
    document: Document
    source_path: str
    source_format: str
    markdown: str = ""
    plain_text: str = ""
    metadata: dict = field(default_factory=dict)
    assets: list[AssetRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

Add provenance to elements without breaking existing callers.

```python
@dataclass
class Provenance:
    source_format: str = ""
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    cell: str | None = None
    section: int | None = None
    paragraph: int | None = None
    path: str = ""
```

Existing model classes can receive optional `provenance` fields over time. This must be additive so existing tests and API behavior remain stable.

### Format Detection

Detection should use extension and magic bytes:

- `.hwp`: OLE compound file plus HWP FileHeader validation.
- `.hwpx`: ZIP package with HWPX/OWPML entries.
- `.docx`: ZIP package with `word/document.xml`.
- `.pptx`: ZIP package with `ppt/presentation.xml`.
- `.xlsx`: ZIP package with `xl/workbook.xml`.
- `.doc`: OLE compound file with `WordDocument` stream.
- `.ppt`: OLE compound file with `PowerPoint Document` stream.
- `.xls`: OLE compound file with `Workbook` or `Book` BIFF stream.
- `.pdf`: `%PDF-` magic header.
- `.txt`, `.md`, `.csv`, `.html`: extension and content sniffing.

Unknown ZIP files must not be blindly parsed as HWPX. The detector should inspect package entries and choose a specific reader.

## Native Format Roadmap

### Phase 1: Core Registry and Result Model

Goal: prepare dochan for multiple native formats without changing user-facing behavior.

Tasks:

- Add `dochan/core/` or `dochan/reader_registry.py` for detector and reader registration.
- Wrap existing HWP/HWPX logic behind native reader classes.
- Keep `Dochan(file_path).to_markdown()` behavior unchanged.
- Add `metadata["source_format"]`.
- Add tests proving `.hwp` and `.hwpx` still route to existing parsers.

### Phase 2: DOCX Native Reader

Goal: parse common Word documents without external conversion engines.

Phase 1 implementation status:

- Completed for simple paragraphs, heading styles, bold/italic/underline/strike runs, simple tables, `Dochan("file.docx")` routing, and batch `.docx` collection.
- Not yet completed for DOCX images, footnotes/endnotes, numbering, style inheritance, merged cells, and equations.

Implementation targets:

- Read OPC ZIP package safely.
- Parse:
  - `[Content_Types].xml`
  - `_rels/.rels`
  - `word/document.xml`
  - `word/_rels/document.xml.rels`
  - `word/styles.xml`
  - `word/numbering.xml`
  - `word/footnotes.xml`
  - `word/endnotes.xml`
- Convert:
  - paragraphs to `Paragraph`
  - runs to `TextRun`
  - headings from style names and outline levels
  - bold/italic/underline where practical
  - tables to `Table`
  - images to `Image` asset references
  - footnotes/endnotes to existing `Footnote`
- Preserve provenance:
  - paragraph index
  - table index
  - relationship id for images

Success criteria:

- Simple DOCX paragraphs convert to Markdown.
- Heading styles convert to Markdown headings.
- Basic tables convert to Markdown tables.
- JSON output includes source format and element structure.

### Phase 3: PPTX Native Reader

Goal: extract slide text, tables, images, and speaker notes.

Phase 1 implementation status:

- Completed for presentation relationship parsing, slide order, slide-level provenance, text box extraction, simple DrawingML tables, `Dochan("file.pptx")` routing, CLI info, and batch `.pptx` collection.
- Not yet completed for speaker notes, images, grouped shapes, comments, slide layouts/masters, shape geometry ordering, rich text formatting, charts, SmartArt, and embedded media.

Implementation targets:

- Read:
  - `ppt/presentation.xml`
  - `ppt/_rels/presentation.xml.rels`
  - `ppt/slides/slideN.xml`
  - `ppt/slides/_rels/slideN.xml.rels`
  - `ppt/notesSlides/notesSlideN.xml` where present
- Convert:
  - each slide to a section or slide element group
  - text boxes to paragraphs
  - tables to `Table`
  - images to `Image`
  - notes to footnote-like or metadata blocks
- Preserve provenance:
  - slide number
  - shape id
  - relationship id

Success criteria:

- Slide order is stable.
- Text boxes are extracted in a deterministic reading order.
- Speaker notes are available in JSON and optionally Markdown.

### Phase 4: XLSX Native Reader

Goal: extract workbook data in a Markdown and JSON shape suitable for LLM/RAG use.

Phase 1 implementation status:

- Completed for workbook sheet ordering, workbook relationships, shared strings, inline strings, numeric cell values, simple rectangular table output, sheet provenance, cell provenance, `Dochan("file.xlsx")` routing, CLI info, and batch `.xlsx` collection.
- Not yet completed for style-aware formatting, formulas as separate metadata, merged cells, date/number format interpretation, charts, images, tables metadata, hidden sheets, and encrypted workbooks.

Implementation targets:

- Read:
  - `xl/workbook.xml`
  - `xl/_rels/workbook.xml.rels`
  - `xl/sharedStrings.xml`
  - `xl/styles.xml`
  - `xl/worksheets/sheetN.xml`
- Convert:
  - each sheet to a section
  - rectangular used ranges to Markdown tables
  - merged cells to `Cell.row_span` and `Cell.col_span`
  - formulas as metadata alongside displayed values where available
- Preserve provenance:
  - sheet name
  - cell address
  - row/column index

Success criteria:

- Shared strings resolve correctly.
- Multiple sheets are preserved.
- Merged cells do not corrupt table dimensions.

### Phase 5: Legacy Office Binary Readers

Goal: provide native first-pass support for `.doc`, `.ppt`, and `.xls` without invoking LibreOffice, MarkItDown, antiword, catdoc, or other runtime converters.

Phase 1 implementation status:

- Completed for `.doc` OLE `WordDocument` text extraction into paragraphs, `Dochan("file.doc")` routing, CLI info, and batch `.doc` collection.
- Completed for `.ppt` OLE `PowerPoint Document` text atom extraction into paragraphs, `Dochan("file.ppt")` routing, CLI info, and batch `.ppt` collection.
- Completed for `.xls` OLE `Workbook`/`Book` BIFF parsing of `BOUNDSHEET`, `SST`, `LABELSST`, and `NUMBER` records into sheet tables, `Dochan("file.xls")` routing, CLI info, and batch `.xls` collection.
- Not yet completed for `.doc` piece table fidelity, paragraph formatting, tables, images, footnotes, tracked changes, encrypted documents, or complex code pages.
- Not yet completed for `.ppt` slide boundary fidelity, shape ordering, rich text formatting, speaker notes, images, charts, SmartArt, embedded media, or encrypted documents.
- Not yet completed for `.xls` formulas, dates, styles, merged cells, RK/BOOL/FORMULA/LABEL/CONTINUE records, charts, images, macros, hidden sheets, or encrypted workbooks.

Implementation targets:

- Keep `olefile` as the only OLE container dependency because it is already permissive and used by HWP parsing.
- Parse `.xls` BIFF records incrementally rather than delegating to a spreadsheet engine.
- Parse `.ppt` text records from the PowerPoint Document stream and add slide-level reconstruction later.
- Parse `.doc` WordDocument text as a conservative first milestone, then add FIB and piece-table interpretation.

Success criteria:

- Legacy files route by extension without breaking HWP OLE routing.
- Text-only legacy documents produce non-empty Markdown/plain text.
- XLS shared strings and numeric cells produce Markdown tables with sheet/cell provenance.
- Unsupported legacy features are documented as incomplete rather than silently claimed as full fidelity.

### Phase 6: PDF Native Reader

Goal: provide a safe first-party PDF path without AGPL/GPL/runtime backend dependencies.

PDF is the hardest format in this roadmap. It still must be native-only. The first milestone should be deliberately limited, but it should establish dochan's own PDF parser foundation rather than delegating to an external converter.

Implementation targets:

- Parse the PDF header and cross-reference structures needed for simple files.
- Resolve indirect objects and page tree structure.
- Decode common stream filters that are safe and practical for the first milestone.
- Interpret basic text operators in page content streams.
- Extract page-level text with page-number provenance.
- Detect unsupported encryption, object streams, malformed xref tables, and scanned-only pages with clear warnings.
- Keep advanced layout, table reconstruction, image extraction, and OCR as native follow-up milestones.

Success criteria:

- Detect PDFs by magic header.
- Extract page-level text from simple digital PDFs using dochan-owned code.
- Preserve page numbers in provenance.
- Return clear warnings for unsupported encrypted/scanned/layout-heavy PDFs.

### Phase 7: Quality Benchmark Suite

Goal: prevent broad format support from becoming shallow and unreliable.

Add a repeatable corpus and metrics:

- sample DOCX:
  - paragraphs
  - headings
  - tables
  - images
  - footnotes
- sample PPTX:
  - text boxes
  - tables
  - images
  - speaker notes
- sample XLSX:
  - multiple sheets
  - shared strings
  - merged cells
  - formulas
- sample PDF:
  - simple digital text
  - table-heavy page
  - scanned page marked expected unsupported until OCR phase

Metrics:

- paragraph count
- table count
- non-empty cell ratio
- image reference count
- warning count
- provenance coverage
- Markdown snapshot stability

## CLI Design

Keep current commands but broaden accepted inputs.

```bash
dochan convert file.docx
dochan convert file.pptx --format json
dochan convert file.xlsx --format markdown
dochan convert file.doc
dochan convert file.ppt
dochan convert file.xls
dochan convert file.pdf --format text
dochan info file.docx
dochan batch input_dir output_dir --format markdown
```

Later options:

```bash
dochan convert file.pdf --pdf-mode basic
dochan convert slides.pptx --include-notes
dochan convert workbook.xlsx --sheet "Sheet1"
```

Do not add external-engine flags to the core design. Supported conversion behavior must come from dochan native readers.

## Error Handling

Reader errors should be recoverable wherever possible.

Rules:

- Unsupported format: produce a clear error.
- Unsupported feature inside supported format: produce a warning and continue.
- Encrypted document: warn and stop parsing that file.
- Oversized ZIP/XML content: stop with safety error.
- Malformed XML: report parser error with part path.
- Missing relationships: keep text content and warn about missing asset.

## Security Requirements

All ZIP/XML readers must reuse the same defensive posture as the HWPX reader:

- reject or skip oversized parts
- reject extreme compression ratios
- disable XML network access and external entity resolution
- normalize and validate package paths
- never extract ZIP entries directly to arbitrary filesystem paths
- cap table dimensions
- cap recursion depth
- cap number of parsed package parts

## Testing Strategy

Unit tests:

- detector tests for HWP/HWPX/DOC/PPT/XLS/DOCX/PPTX/XLSX/PDF magic and package entries
- DOCX XML parser tests with minimal in-memory package fixtures
- PPTX slide parser tests with minimal slide XML fixtures
- XLSX shared string and worksheet parser tests
- DOC/PPT/XLS OLE stream parser tests with minimal in-memory fixtures
- provenance serialization tests
- Markdown output snapshot tests

Integration tests:

- one small fixture per format
- CLI conversion test per format
- batch conversion test over mixed formats

Regression tests:

- existing HWP/HWPX tests must keep passing
- current `Dochan` public API must keep working
- current CLI flags must keep working

Validation command:

```bash
pytest dochan/tests/
```

In this workspace, `pytest` runs under Python 3.9.6. `python3 -m pytest` currently points to a Python 3.14 install without pytest, so the project-local validation command should use `pytest` unless the environment is changed.

## Rollout Plan

1. Add conversion registry and result/provenance models.
2. Move existing HWP/HWPX parsing behind native reader adapters without changing behavior.
3. Implement DOCX native reader.
4. Implement PPTX native reader.
5. Implement XLSX native reader.
6. Implement legacy DOC/PPT/XLS native first-pass readers.
7. Add mixed-format batch support.
8. Add native PDF parser foundation and simple digital text extraction.
9. Add benchmark corpus and quality reports.
10. Use external tools only for offline comparison reports, not runtime conversion.

## Open Decisions

- Whether `Document.sections` is enough for slide/sheet grouping or whether explicit `Slide` and `Sheet` model classes are needed.
- Whether Markdown should include provenance comments by default or keep provenance JSON-only.
- Whether DOCX/PPTX/XLSX image binary extraction should be default or opt-in.
- Whether PDF support should be released as experimental until layout/OCR quality is mature.

## Non-Negotiables

- Do not add AGPL/GPL conversion libraries to dochan core.
- Do not add runtime conversion backends that make MarkItDown, Docling, Unstructured, PyMuPDF, Marker, or similar tools part of dochan's supported conversion path.
- Do not break existing HWP/HWPX public API.
- Do not claim full PDF support until layout, table, scanned, and encrypted cases are explicitly classified.
- Do not flatten all formats into plain Markdown only; preserve structured JSON and provenance.
