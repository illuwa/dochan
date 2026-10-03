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

Phase 1 implementation status (updated 2026-08-08):

- Completed for paragraphs, heading styles, bold/italic/underline/strike runs, tables (merged cells, nested text), numbering, style inheritance, footnotes/endnotes, comments, tracked changes, control/smart-tag text, field results, headers/footers, image references and alt text, OMML equations → LaTeX (2026-08-09), `Dochan("file.docx")` routing, and batch `.docx` collection.
- Completed additionally (2026-10-03, 1.7.0) for image binary export via `Dochan.save_images()` and `--images-dir` (7426d93; the reader already stored image bytes in `Image.image_data`/`Document.assets` — see `docs/superpowers/plans/2026-10-02-improvement-backlog.md` §1, which noted this sentence had fallen behind the code), table/figure captions bound to the adjacent top-level table or image (312504a; 2026-10-02-ooxml-fix-real-docs.md, LibreOffice 7/7), charts with title, type/axis caption and data including uncached `c:f` references into the embedded workbook and chartEx parts (312504a, aca8b5a; 2026-10-02-ooxml-fix-real-docs.md, POI 8 tables 248/248 cells; 2026-10-02-docx-polish-real-docs.md), reading order of text boxes, floating shapes, content controls and group shapes (628cf90; 2026-10-02-docx-order-real-docs.md, 464/466 LibreOffice files fully aligned), ISO/IEC 29500 Strict packages (2151996; 2026-10-02-ooxml-strict-real-docs.md), and Standard/Agile encrypted documents (eb65aed; 2026-10-02-crypto-real-docs.md, 6/6).
- Not yet completed for captions in the same paragraph as the image or inside group shapes and text boxes (2026-10-02-ooxml-fix-real-docs.md), real-document verification of linked images (2026-10-02-docx-polish-real-docs.md), and a reading-order re-run on Strict documents, which are the remaining 2 of the 466 (2026-10-02-ooxml-strict-real-docs.md).

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

Phase 1 implementation status (updated 2026-08-08):

- Completed for presentation relationship parsing, slide order, slide-level provenance, text box extraction, simple DrawingML tables, speaker notes, image references and alt text, grouped shapes, comments, slide layout inheritance text, shape reading order, rich text formatting (bold/italic/underline/strike — verified 2026-08-09), `Dochan("file.pptx")` routing, CLI info, and batch `.pptx` collection.
- Completed additionally (2026-10-03, 1.7.0) for chart type and axis-title captions, scatter/bubble `c:xVal`/`c:yVal` values, single-branch `mc:AlternateContent` reading, uncached references and chartEx parts (ce82928, 0a870f1, 312504a; 2026-10-02-ooxml-fix-real-docs.md), OMML equations wrapped in `a14:m` (312504a; 2026-10-02-ooxml-fix-real-docs.md, 1/1 real equation plus unit tests), table cells with multiple paragraphs, line breaks and continuing numbering (312504a), video/audio references as paragraphs and `AssetRef` kinds (312504a; unit tests only), Strict packages (2151996; 2026-10-02-ooxml-strict-real-docs.md), and encrypted presentations (eb65aed; one public Apache Tika sample, 2026-10-02-crypto-real-docs.md). SmartArt diagram text was already implemented (`_parse_smartart`, `test_reads_pptx_smartart_diagram_text`); the earlier "SmartArt" item was stale (`docs/superpowers/plans/2026-10-02-improvement-backlog.md` §3).
- Not yet completed for real-document verification of media references, complex OMML (fractions, scripts) and encrypted PPTX beyond the single sample (2026-10-02-ooxml-fix-real-docs.md, 2026-10-02-crypto-real-docs.md). Table/figure captions and nested tables are not applicable: DrawingML has no caption element and a table cell cannot hold another table (2026-10-02-ooxml-fix-real-docs.md).

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

Phase 1 implementation status (updated 2026-08-08):

- Completed for workbook sheet ordering, workbook relationships, shared strings, inline strings, numeric cell values, formulas (including shared formulas), date/number format interpretation, merged cells, comments, style-aware formatting (bold/italic/underline/strike via cellXfs fontId, 2026-08-09), simple rectangular table output, sheet provenance, cell provenance, `Dochan("file.xlsx")` routing, CLI info, and batch `.xlsx` collection.
- Completed additionally (2026-10-03, 1.7.0) for chart type and axis-title captions, scatter long tables, uncached `c:f` references within the workbook, chartEx parts and bubble sizes, verified on Office-made charts (ce82928, 0a870f1, 312504a; 2026-10-02-ooxml-fix-real-docs.md: POI 26 files, 32 output parts, values 1,828/1,828, titles 16/16, captions 32/32), image binary export (images were already read; 7426d93, improvement backlog §1), hidden and very hidden sheets marked with a `*Sheet visibility: …*` line under the sheet title (312504a; 2026-10-02-ooxml-fix-real-docs.md), Standard/Agile encrypted workbooks including the default `VelvetSweatshop` password (eb65aed; 2026-10-02-crypto-ooxml.md, 2/2), and Strict workbooks including ISO date cells (2151996; 2026-10-02-ooxml-strict-real-docs.md, Transitional pairs 3/3).
- Not yet completed for number-format display of chart categories (e.g. `h:mm`), real-document verification of chartEx clustered-column/Pareto parts, `txData` titles, bubble sizes, automatic titles, scatter X/Y axis semantics and bar+scatter combinations (2026-10-02-ooxml-fix-real-docs.md), and encrypted XLSB workbooks (rejected with an error; eb65aed).

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

Phase 1 implementation status (updated 2026-08-08):

- Completed for `.doc` FIB validation, piece-table text extraction, field result/hyperlink text restoration, simple tables, heading detection, `Dochan("file.doc")` routing, CLI info, and batch `.doc` collection.
- Completed for `.ppt` slide text record extraction with slide boundaries, text-type-based heading detection, simple tables, field results, `Dochan("file.ppt")` routing, CLI info, and batch `.ppt` collection.
- Completed for `.xls` BIFF parsing of `BOUNDSHEET`/`SST`/`CONTINUE`/`LABELSST`/`LABEL`/`RSTRING`/`NUMBER`/`RK`/`MULRK`/`BOOLERR`/`FORMULA`(cached)/`SHRFMLA` records, merged cells, `DATEMODE`/`FORMAT`/`XF` date interpretation, headers/footers, `Dochan("file.xls")` routing, CLI info, and batch `.xls` collection.
- Completed additionally (2026-10-03, 1.7.0) for a shared OfficeArt parser ([MS-ODRAW] record tree, BStore/BLIP, EMF/WMF/PICT, DIB→BMP) used by all three formats (95077a5; 2026-10-02-legacy-foundation-real-docs.md, 108 BLIPs from 9 POI files) and image OCR through the existing OCR path (2026-10-02-legacy-ocr-real-docs.md: PPT 8/8 and XLS 16/16 identical to the OOXML twin, DOC checked by eye on 2 files).
- Completed additionally for `.doc` structural reading per [MS-DOC]: character/paragraph formatting via FKP/sprm, STSH style inheritance, merged and nested tables, footnotes/endnotes, comments with authors, headers/footers, text boxes, bookmarks, internal/external hyperlinks, inline and floating pictures with alt text, tracked changes (insertions kept, deletions dropped), table/figure captions, embedded Excel/MS Graph charts and Equation 3.0 equations, with fallback to the previous text path (6c7aec0, d146344, 83a0f83, ee078bb; 2026-10-02-doc-fix-real-docs.md: 353 public files, 0 unclassified word loss, 37/37 feature checks; 2026-10-02-doc-caption-real-docs.md: 7/7; 2026-10-02-legacy-objects-fix-real-docs.md: equations 42/54), and RC4/CryptoAPI encryption (eb65aed; 2026-10-02-crypto-legacy.md, 2/2).
- Completed additionally for `.ppt` structural reading per [MS-PPT]: UserEdit/PersistDirectory chain, slides/notes/masters, OfficeArt shape tree with coordinate reading order, rich text formatting, placeholder/master inheritance, grouped shapes, table grids with merges, pictures with alt text, notes and comments in the PPTX contract, hyperlinks, slide-number fields, embedded charts and Equation 3.0 equations, with fallback to and supplement from the previous text path (21e03da, d146344, ee078bb; 2026-10-02-ppt-fix-real-docs.md: PPT↔PPTX 8 pairs, token similarity 0.3129 → 0.6406; 2026-10-02-legacy-objects-fix-real-docs.md: charts 8/8, equations 13/18), and RC4 CryptoAPI encryption (eb65aed; 2026-10-02-crypto-ppt.md, 5/5).
- Completed additionally for `.xls` formulas from the [MS-XLS] Ftab table, external workbook references, NameX, user-defined functions, array constants and deleted references (d281ad5, f097521; 2026-10-02-xls-formula-fix-real-docs.md: 1,059/1,070 after whitespace normalization), rich text runs, internal hyperlinks, OfficeArt pictures with cell anchors, BIFF8 chart substreams and chart sheets (d281ad5; 2026-10-02-xls-fix-real-docs.md: rich text 731/731 cells, internal links 99/99, chart Y values 2,275/2,275), the RK and COLINFO fixes, hidden-sheet markers (312504a), and XOR/RC4/CryptoAPI encryption (eb65aed; 2026-10-02-crypto-legacy.md, 4/4).
- Not yet completed for `.doc` pictures stored without an FBSE, linked text-box chains and visual placement, per-page header placement, real-document verification of XOR obfuscation and of embedded charts (no public sample), and TOP/localized captions beyond synthetic tests (2026-10-02-doc-fix-real-docs.md, 2026-10-02-crypto-legacy.md, 2026-10-02-legacy-objects-fix-real-docs.md, 2026-10-02-doc-caption-real-docs.md).
- Done in 1.11.0: `.ppt` character-format inheritance from the document defaults, master levels and text types, measured against Microsoft PowerPoint (font size match 73.1% → 99.3% on 38 public files; docs/SUPPORT_NOTES.md "스타일 상속 · PPT").
- Not yet completed for `.ppt` unconfirmed fields of the extended format masks (pp10ext/pp11ext), and embedded media and SmartArt (not investigated) (2026-10-02-ppt-fix-real-docs.md).
- Done in 1.12.0: `.xls` memory tokens (`PtgMemFunc`, `PtgMemArea`, `PtgMemErr`, `PtgMemNoMem`), `PtgElfLel` and BIFF5 cell references/shared formulas (845 more public formula cells; 2026-10-03-xls-tokens-real-docs.md).
- Not yet completed for `.xls` DDE/OLE link calls and data tables (`PtgTbl`), real-document verification of RSTRING records and of chart series pointing to external or deleted ranges, conditional K/M number formats, and macros (2026-10-02-xls-formula-fix-real-docs.md, 2026-10-02-xls-fix-real-docs.md).
- Completed additionally for `.xls` FONT/XF style formatting (bold/italic/underline/strike with the BIFF font-index-4 quirk, 2026-08-09).

Implementation targets:

- Read OLE containers with the native `dochan/cfb.py` implementation of [MS-CFB]. Keep `olefile` only as an optional local comparison oracle; runtime readers and ordinary tests do not require it.
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

Phase 1 implementation status (updated 2026-08-08):

- Completed for classic xref table/trailer chain parsing with `N G obj` scan fallback and free-entry tombstones, indirect object resolution with cycle guards, page tree traversal with inherited resources, FlateDecode/ASCIIHexDecode/ASCII85Decode stream filters, text operator interpretation (Tj/TJ/'/"/Td/TD/Tm/T* with leftward-return line breaks), ToUnicode CMap decoding (Korean CID text, longest-code-first matching), page-number provenance, encrypted/xref-stream/ObjStm/scanned-page/no-ToUnicode-CID warnings, magic-sniffed `.pdf` routing (extension mismatch tolerant, same policy as HWP), CLI, and batch `.pdf` collection.
- Security limits in place (2026-08-08 감수 2회 반영): per-stream decode cap 50MB, per-document cumulative decode budget 200MB with stream result caching, CMap mapping total cap 100k entries, parser nesting depth 64, resolve depth 32, object count 500k, page count 10k, per-page content stream count 256, collection width 100k, file size 500MB; defensive exception handling downgrades parser failures to `doc.errors`.
- Phase 2 completed (2026-08-09): xref streams + object streams (PNG predictors Sub/Up/Average/Paeth 포함 — 실물 검증: qpdf 변환 xref 스트림 PDF 에서 클래식 원본과 바이트 단위 동일 추출), outline bookmarks (목차 섹션 + 페이지 번호 매핑, 순환 가드), link annotation URI 추출(TextRun.link), font-size 기반 제목 감지(페이지 중앙값 대비 1.5×/1.25× 임계 — 별표19 실문서에서 실제 제목 감지 확인).
- Table reconstruction was deferred in 1.3.0 (HWP→PDF 내보내기가 어절 단위 좌표를 찍어 텍스트 x 클러스터링만으로는 열 경계를 잡지 못함). Resolved in 1.4.0 by using the vector ruling lines as the grid evidence — see Phase 4 below.
- Phase 4 completed (2026-09-07, 1.4.0): 그래픽 상태(CTM, q/Q, cm) 추적으로 텍스트 조각을 장치 좌표에 배치(한글 'PDF로 저장' 출력의 `q … cm BT … ET Q` 런 구조 대응), 글리프 폭 레이아웃·bold/italic·이미지 XObject 추출+OCR(1.3.0), 경로 연산자(m/l/re + S)에서 축 정렬 괘선 수집 → 군집화 → 연결 성분 → 격자 → 병합 셀(가로/세로, L자형 행별 분할) → 셀 텍스트 배치, 바깥 괘선 없는 표의 괘선 범위 확장(가로 괘선 2개 이상이 닿는 범위, 세로 방향은 확장 안 함), 꽉 찬 줄 기반 문단 병합(항목 표식 분리, 한글·숫자 무공백 결합), 본문 기준 제목 판정, MacRomanEncoding 단순 폰트. 자원 상한: 페이지 콘텐츠 합계 64MB, 선분·서브패스 2만, 교차 검사 200만, 표 셀 페이지 5만·문서 20만, 성분 선 2천. 검증(scripts/compare_pdf_pairs.py, docs/benchmarks/2026-09-07-pdf-layout-tables-real-doc-validation.md): 동일 문서 HWPX↔PDF 79쌍 공백 토큰 유사도 0.032 → 0.938(최저 0.805), PDF 표 0 → 864개(HWPX 845개), 셀 텍스트 일치율 0.894, 표 구조 완전 일치 0.620, 병합 셀 구성 일치 0.913. codex 독립 리뷰(P1 3건·P2 4건)와 Opus 감수 반영.
- Phase 3 completed (2026-08-09): 표준 보안 핸들러 복호화 — RC4(V1/V2/V4), AESV2(AES-128-CBC), AESV3(AES-256-CBC, R6 경화 해시). 빈 사용자 암호(소유자만 잠근 문서)와 사용자 제공 암호 처리. stdlib 전용(hashlib + 순정 AES-CBC 확장). 검증: RFC 6229/NIST SP 800-38A 공인 벡터 + qpdf 생성 3종 암호화 PDF 엔드투엔드 + 실제 암호화 정부 PDF(0자→한글 1279자).
- Phase 5-A completed (2026-09-07): 한글 줄바꿈 결합 공백을 문자 통계 모델로 판정 — 공개 코퍼스 학습 모델(209KB, 패키지 데이터), 결합 정확도 0.607 → 0.932(79쌍 표본 외, 공개 코퍼스 2,538건 학습), 토큰 유사도 0.961. 남은 Phase 5 과제(중첩 표 트리, 페이지 걸침 병합, 세로쓰기, 괘선 없는 표)는 docs/superpowers/plans/2026-09-07-pdf-phase5-nesting-pagination-vertical-spacing.md 참조.
- Phase 5-B/C/D/E completed (2026-09-24): 분리형 중첩 표 트리(nested_match 0.364 = 괘선으로 도달 가능한 24/66 전부), 페이지 걸침 표 병합(진짜 연속 3건, 본문 띠·열 일치·남은 공간 조건), 세로쓰기·회전 텍스트 읽기 순서(합성 픽스처 검증, 실물 미확보로 README 보류), 괘선 없는 표 옵션(기본 꺼짐). 근거: docs/benchmarks/2026-09-24-pdf-phase5-nested-pagination-vertical.md.
- Phase 6-A completed (2026-09-24, 1.6.0): 페이지마다 반복되는 머리글(문서 제목)·바닥글(쪽번호) 검출 — 상·하단 12% 구역의 연속 가장자리 블록만 후보, 쪽번호형 줄만 숫자 접기, max(2, ⌈0.3×텍스트 페이지⌉) 반복 임계, 첫 출현 페이지 섹션 앞에 HeaderFooter 한 번(HWPX 와 같은 위치). 79쌍 실측 hf_hit 0.9913, 본문 오제거 0, 토큰 유사도 0.9617 → 0.9753. 근거: docs/benchmarks/2026-09-24-pdf-running-headers.md. 남은 PDF 항목(각주/미주·주석·내부 링크)은 코퍼스 정답이 각주 6건(1개 문서)·주석 0·내부 링크 0 이라 검증 자원이 없어 보류.
- Phase 6-B completed (2026-10-03, 1.7.0): LZWDecode(EarlyChange 0/1)·TIFF Predictor 2(1–16비트, 문서 공유 연산 예산), 사용자 암호 R2–R6(RC4·AES-128·AES-256, R6 SASLprep·R2–R4 PDFDocEncoding)와 `Dochan(password=)` 연결(열 수 없으면 ERR), 마크업 주석 17종 → Comment(대상 글자 위치가 확실하면 본문 런 끝에 참조), 내부 링크(Dest·GoTo·Dests·Names → `#page-N`, 대상 페이지 `[bookmark: page-N]`), 표준 14 글꼴 AFM 폭으로 본문 링크 연결, 각주(하단 정의·고유 위첨자·구분선)와 명시 미주 구역, WMode 1 세로 폰트(Identity-V·DW2/W2). 근거: 3811f59, 767e73a, 876faa5, 477d37a, eb65aed; 2026-10-02-pdf-real-docs.md(LZW 이미지 2건·TIFF 3,260,320바이트 일치, 세로 첫 런 2/2·열 10/10), 2026-10-02-pdf-fix-real-docs.md(주석 158/158, 내부 링크 47/47, 암호 7/7 개방·7/7 차단), 2026-10-02-pdf-links-real-docs.md(본문 링크 372/372·연결률 54.87%, 각주 6/6·261/261자, 79쌍 레이아웃 지표 동일), 2026-10-02-pdf-polish-real-docs.md(pdf.js 983개 암호 회귀 0, text_tables 66/66 손실 0).
- Not yet completed for 괘선 없는 1×1 글상자(HWPX 서명 27개 중 4개 일치), 부모와 테두리를 공유하는 연결형 중첩 표(중첩 일치 24/66, 하위 격자 추정은 오탐 211건으로 폐기 유지), 페이지 경계에서 잘린 셀의 결합(경계 후보 14건 중 양성 0), 병합 셀 완전 일치(행·열이 맞는 병합 표 235개 중 span 일치 216개, 전체 370개 기준 216개), 연결을 보류한 본문 링크 306건(실제 글자가 있는 267건), 미주 실물 복원(0/1), 수식 구조의 Equation 연결, 다른 파일을 가리키는 링크(GoToR), RC 리치 텍스트·Sound·Redact 주석과 비어 있지 않은 R2 암호·LZW EarlyChange 0·TIFF 1/2/4/16비트·W2 의 실물 검증, 한 글자 문맥으로 결정되지 않는 줄바꿈 공백(약 6%). 근거: 2026-10-02-pdf-real-docs.md, 2026-10-02-pdf-links-real-docs.md.
- Real-document validation (2026-08-08): 80 same-document HWP/HWPX/PDF pairs — 0 crashes, 0 empty outputs, 0 control-character leaks; HWPX↔PDF text similarity mean 0.868, all 79 comparable pairs ≥ 0.73. Downloads 실문서 34건 — 0 crashes; 4 empty outputs all with correct warnings (encrypted 1, scanned 2, no-ToUnicode CID 1).

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
