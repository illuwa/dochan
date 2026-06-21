# OOXML Improvement Loop - 2026-06-20

## Objective

Move dochan's `.docx`, `.pptx`, and `.xlsx` conversion toward a measurable position where it can beat MarkItDown and Docling on speed and selected accuracy dimensions.

The current strategy is not to claim broad superiority. The loop is:

1. Add a reproducible benchmark harness.
2. Add minimal fixtures for a missed OOXML behavior.
3. Verify the test fails.
4. Implement the smallest native parser improvement.
5. Run the full regression suite.
6. Repeat with real corpus files and installed competitors.

## Benchmark Harness

Added:

```bash
/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/benchmark_competitors.py <corpus-dir> \
  --formats docx,pptx,xlsx \
  --converters dochan,markitdown,docling \
  --save-outputs /tmp/dochan-ooxml-outputs
```

For isolated competitor runs:

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 scripts/run_isolated_competitor_benchmark.py <corpus-dir> \
  --output-dir /tmp/dochan-ooxml-competitive \
  --competitors markitdown,docling \
  --python /opt/homebrew/opt/python@3.14/bin/python3.14 \
  --formats docx,pptx,xlsx \
  --runs 3
/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/summarize_competitive_index.py \
  /tmp/dochan-ooxml-competitive/index.json \
  --output /tmp/dochan-ooxml-competitive/summary.md
```

Latest isolated competitive rerun: 2026-06-21, Python 3.14.6, `competitive_summary` output.

Behavior:

- Always runs dochan.
- Auto-detects local `markitdown` if installed.
- Auto-detects local `docling` if installed.
- Supports explicit converter selection through `--converters`; requested but unavailable converters are recorded in `converter_status` instead of silently disappearing.
- Emits JSON rows with converter, file, format, elapsed seconds, output length, non-empty status, and error.
- With `--save-outputs`, writes converter Markdown outputs under `<output-root>/<converter>/<relative-input>.runN.md` and records each path in the row as `output_path`.
- Emits output profile metrics for every corpus: line count, meaningful heading count, Markdown table row count, link count including `mailto:`, Markdown image reference count, comment markers, bookmark markers, formula markers, and unique text token count.
- Emits dochan-only structured JSON profile metrics in result rows and summary rows: asset count, section provenance count, table count, table-cell count, cell provenance count, nested cell paragraph count, run provenance count, and rich run count. `competitive_summary` also carries JSON metric deltas when competitor rows are present, so dochan's structured JSON/provenance advantage is visible above the per-file row level.
- Native JSON output preserves `Document.assets` as a top-level `assets` array with package relationship id, source path, filename, content type, and format-specific metadata for DOCX, PPTX, and XLSX image relationships. DOCX embedded OLE/package relationships are also recorded as assets with relationship-type metadata, and VML `v:imagedata` object preview images are emitted as Markdown image references plus assets. JSON output also preserves section, paragraph, run, and cell provenance; table row/column counts; cell row/column spans; nested cell paragraph/run structure; paragraph heading levels; and rich run flags for underline, strikeout, superscript, and subscript. DOCX/PPTX text runs now carry paragraph provenance, DOCX/PPTX table cells carry `R{row}C{column}` provenance, and XLSX cell text runs carry cell provenance.
- Emits expected-output accuracy fields when `expected.json` exists.
- Emits `format_summary` grouped by converter and format so real-world corpora without `expected.json` can still be compared by success rate, median speed, output size, table rows, meaningful headings, links, image references, comments, bookmarks, and formula markers.
- Emits `competitive_summary` for installed competitors, comparing each converter against dochan by format with speedup, accuracy delta, success-rate delta, and selected output-profile deltas.
- Emits `improvement_candidates` sorted by dochan weakness score so the next parser or fixture loop can start where dochan trails an installed competitor on accuracy, success rate, table rows, meaningful headings, links, image references, comments, bookmarks, or formula markers.
- Emits `file_competitive_summary` and `file_improvement_candidates` so one weak public fixture cannot be hidden by a strong format-level median. File-level candidates include representative dochan and competitor output paths when `--save-outputs` is used, making manual inspection the next step before treating a profile delta as a parser bug. Table-row-only file candidates are filtered unless the competitor also exposes more unique text tokens, reducing layout-fragmentation false positives; spreadsheet placeholder tokens such as `NaN`, `NaT`, and `Unnamed: n` are ignored for unique-token deltas; numeric-only tokens are ignored for unique-token deltas so raw floating-point spreadsheet values do not masquerade as extra semantic text; empty or placeholder-only Markdown table rows are ignored for profile row-count deltas while explicit `expected_table_rows` scoring still preserves blank rows; image references with `]` inside alt text, such as Windows filenames containing `[1]`, are counted correctly; and generated empty-alt `ShapeNNN.jpg`-style image placeholders are ignored when no real package media relationship exists.
- `scripts/run_isolated_competitor_benchmark.py` creates one temporary venv per competitor outside the benchmark corpus, installs dochan editable plus the competitor package, runs `benchmark_competitors.py`, writes `<competitor>.json`, `outputs/<competitor>/...`, and `index.json`, then removes the venv unless `--keep-venv` is set. Each index record includes a compact `report_summary` with file count, converters, `format_summary`, `competitive_summary`, and `improvement_candidates`, so dochan JSON profile medians survive isolated competitor runs.
- `scripts/summarize_competitive_index.py` renders `index.json` into Markdown tables for run status, competitive deltas, dochan JSON profile medians, and improvement candidates.
- `scripts/download_public_ooxml_corpus.py` now includes Apache POI probe-manifest helpers. The next broad probe can persist per-format fixture ids, select unseen DOCX/PPTX/XLSX samples deterministically, and avoid accidentally reusing the same Apache POI files across improvement loops.

Generated corpus:

- `scripts/generate_ooxml_benchmark_corpus.py <output-dir>` creates deterministic `.docx`, `.pptx`, `.xlsx`, and `expected.json` files.
- The generated corpus covers DOCX core properties from `docProps/core.xml`, header/footer/heading/style-inheritance/character-style run formatting/tab/break/text-box text/drawing alt text from `wp:docPr`/embedded image relationships from `a:blip r:embed` as Markdown image references plus `Document.assets` entries/external hyperlink target/internal anchor hyperlink target/visible bookmark anchor/run-level bold, italic, underline, strike, superscript, and subscript Markdown formatting/decimal, lower-letter, upper-roman, and parent-aware multilevel numbering/footnotes/endnotes/comment reference extraction plus inline `commentRangeStart`/`commentRangeEnd` annotations/comment replies from `commentsExtended.xml`/tracked insertions and deletions/content-control and smart-tag wrapper text/field result text/gridSpan table/vMerge table/`w:gridBefore` skipped leading table cells/nested table text, PPTX core properties/break/field/bullet and auto-numbered paragraphs/run-level bold, italic, underline, and strike Markdown formatting/run-level external hyperlink target/shape-level external hyperlink target/internal slide hyperlink target/picture alt text and embedded image relationships from `p:cNvPr` plus `a:blip r:embed` as Markdown image references plus `Document.assets` entries/multi-slide Markdown headings/chart title/multi-series chart table/cached series data/SmartArt diagram data text through `dgm:relIds`/speaker notes/static slide-layout text/table/grouped-shape text/grouped-shape child coordinate transforms through `a:chOff`/`a:chExt`/merged table cells/position-based reading order, and XLSX core properties/workbook defined names/boolean/comment/error cell/cached formula/shared formula metadata with follower-cell reference translation/shared formula whole-column and whole-row ranges/shared and inline rich text/external, internal, and range hyperlink/merged cell/sparse row and column coordinates/date/time/duration/percent/fixed-decimal/currency/thousands/negative-accounting number formats/zero-padded identifier custom formats such as `00000` and `000-0000`/literal prefix and suffix custom number formats/fraction number formats such as `# ?/?` and `# ??/??`/scientific number formats such as `0.00E+00` and `0.0E+00`/multiple sheet-name heading/multi-block business table/drawing textbox/embedded drawing image relationships as Markdown image references plus `Document.assets` entries/chart title/multi-series chart table/chart cached series cases.
- The generated DOCX, PPTX, and XLSX fixtures declare `image/png` in `[Content_Types].xml` and embed a minimal valid PNG, so MarkItDown/Docling failures are not caused by missing package content types or invalid placeholder image bytes.
- The scorer ignores blank expected table cells for cell-level coverage so merged-away placeholders do not inflate failed-converter accuracy; `expected_table_rows` separately scores row structure, including blank cells in sparse rows.
- Binary fixtures are generated on demand instead of checked into the repository.

Public corpus:

- `scripts/download_public_ooxml_corpus.py <output-dir> --formats docx,pptx,xlsx` downloads a 50-file license-audited public OOXML corpus and writes `SOURCES.json`, `SOURCES.md`, and semantic `expected.json`.
- Current fixtures are sourced from permissively licensed test corpora: `python-openxml/python-docx` under MIT, `bgreenwell/doxx` under MIT, `scanny/python-pptx` under MIT, `pyexcel/pyexcel` under BSD-3-Clause, `ChrisPappalardo/eparse` under MIT, and `apache/poi` under Apache-2.0.
- This corpus has semantic expectations for all 50 fixtures: 18 DOCX, 14 PPTX, and all 18 XLSX files. The minimal PPTX fixture is scored as a metadata-only deck because it has core presentation metadata but no slide part or presentation text nodes.
- For broad Apache POI probes, first build a fixture index, then pass it with a persistent manifest:
  `scripts/build_apache_poi_fixture_index.py docs/benchmarks/apache-poi-fixtures.json --formats docx,pptx,xlsx`
  followed by
  `scripts/download_public_ooxml_corpus.py <output-dir> --fixture-index docs/benchmarks/apache-poi-fixtures.json --probe-manifest docs/benchmarks/apache-poi-probe-manifest.json --probe-name apache-poi-12 --probe-per-format 20`.
  The fixture index is a JSON object with a `fixtures` list using the same `name`, `format`, `url`, `source`, `license`, and optional `source_name` fields as the built-in corpus records.
- The same flow is now wrapped by `scripts/run_apache_poi_probe.py <output-dir> --probe-name apache-poi-14 --probe-manifest docs/benchmarks/apache-poi-probe-manifest.json --probe-per-format 10 --python /opt/homebrew/opt/python@3.14/bin/python3.14`. It writes `apache-poi-fixtures.json`, `corpus/`, `dochan.json`, isolated competitor reports, converter outputs, and a top-level `probe.json` summary.
- The wrapper now treats corrupt Apache POI fuzz fixtures as invalid corpus inputs instead of parser failures. Invalid ZIP files are removed from the benchmark corpus, preserved in `probe.json` as `zip_invalid`, and the dochan/isolated competitor runs continue on the valid files.
- Apache POI is no longer the only manifestable broad-probe source. `scripts/build_github_ooxml_fixture_index.py` indexes permissively licensed OOXML fixtures from `python-openxml/python-docx` (MIT), `scanny/python-pptx` (MIT), `pyexcel/pyexcel` (BSD-3-Clause), and `ChrisPappalardo/eparse` (MIT). `scripts/run_fixture_probe.py` runs the same manifest/download/ZIP-validation/dochan-only/isolated-competitor loop against any fixture index JSON, so newly indexed GitHub fixture pools can be sampled without writing a source-specific runner.
- `scripts/build_apache_tika_fixture_index.py` indexes Apache Tika's Microsoft parser test documents under Apache-2.0. The current index discovers 56 DOCX, 27 PPTX, and 33 XLSX fixtures from `apache/tika`, and can be passed to the same generic `scripts/run_fixture_probe.py` loop.
- The first runs exposed two native gaps: `pyexcel-bug-176.xlsx` uses Strict OOXML spreadsheet namespaces (`http://purl.oclc.org/ooxml/...`), while the native reader only searched Transitional namespaces; `python-docx-having-images.docx` contains image relationships but no text nodes, while dochan previously emitted no image placeholder.

Current limitation:

- MarkItDown was benchmarked in a temporary isolated Python 3.14 venv.
- Docling was benchmarked in a temporary isolated Python 3.14 venv.
- The focused generated corpus is not a substitute for a broad real-world OOXML corpus.

## Accuracy Improvements Completed In This Loop

### DOCX

Added native extraction for:

- `docProps/core.xml` title and creator as Markdown metadata: `# title` and `Author: creator`.
- `w:tab` as tab characters.
- `w:br` as line breaks.
- section header/footer parts through `w:headerReference` and `w:footerReference` relationships.
- embedded image relationships inside DOCX header/footer parts, using each header/footer part's own `.rels` file.
- text inside `w:hyperlink`.
- external hyperlink targets from `word/_rels/document.xml.rels` as `text <URL>`.
- internal anchor hyperlink targets from `w:hyperlink w:anchor` as `text <#anchor>`.
- visible `w:bookmarkStart` anchors as `[bookmark: name]`, while skipping hidden `_` bookmarks.
- built-in Word `Title` paragraph style as a level-1 Markdown heading.
- `word/styles.xml` paragraph style inheritance through `w:basedOn` for heading detection.
- `w:gridSpan` table cells as `Cell.col_span` plus merged-away cells.
- `w:vMerge` table cells as `Cell.row_span` plus merged-away cells.
- `w:gridBefore` skipped leading table cells as explicit blank leading `Cell` instances.
- table rows and cells wrapped by `w:sdt`, `w:sdtContent`, `w:smartTag`, tracked insertions, or preferred `mc:AlternateContent` blocks.
- nested table text inside parent cells.
- basic `word/numbering.xml` decimal numbering as `1.`, `2.`, etc.
- lower-letter, upper-letter, lower-roman, and upper-roman `word/numbering.xml` markers such as `a)` and `X.`.
- parent-aware multilevel `word/numbering.xml` markers such as `1.a)`, with lower-level counters reset when a parent level increments.
- `word/footnotes.xml` and `word/endnotes.xml` extraction as document footnote/endnote elements, with inline reference markers.
- `word/comments.xml` extraction as document comment elements, with inline comment reference markers.
- `w:commentRangeStart` and `w:commentRangeEnd` as inline annotations on the commented text, while suppressing duplicate `w:commentReference` markers for that range.
- `word/commentsExtended.xml` comment reply relationships through `w15:paraIdParent`, preserving reply text under the parent comment.
- tracked changes: include `w:ins` text and ignore `w:del` deleted text.
- text wrapped by `w:sdt`, `w:sdtContent`, and `w:smartTag`.
- body-level text wrapped by `w:sdt`, `w:sdtContent`, `w:smartTag`, tracked insertions, and preferred `mc:AlternateContent` blocks.
- header/footer paragraphs nested inside content controls.
- package-root absolute relationship targets such as `/word/footer.xml` for headers, footers, images, and embedded objects.
- text inside `w:txbxContent` text boxes.
- drawing alt text from `wp:docPr` `title` and `descr` attributes.
- embedded image relationships from `a:blip r:embed` as Markdown image references with the `wp:docPr` label and resolved `word/media/...` target.
- embedded image relationships as `Document.assets` entries with relationship id, source path, filename, content type, label metadata, and `source_format: docx`.
- embedded OLE/package relationships as `Document.assets` entries with relationship id, source path, filename, content type, relationship-type metadata, and `source_format: docx`.
- VML object preview images from `v:imagedata r:id` as Markdown image references plus image `Document.assets` entries.
- field result text from `w:fldSimple` and complex fields while excluding field instructions.
- character style formatting from `w:rStyle` in `word/styles.xml`, including bold, italic, underline, strikeout, superscript, and subscript properties.
- HTML and MHTML `w:altChunk` imports through `aFChunk` relationships, including imported paragraphs, table rows as pipe-separated text, and image `alt` text.

Regression test:

```bash
pytest dochan/tests/test_docx_reader.py::test_reads_docx_tabs_line_breaks_and_hyperlink_text -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_headers_and_footers_from_section_relationships -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_header_embedded_image_relationship -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_external_hyperlink_target -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_visible_bookmark_anchor_names -v
pytest dochan/tests/test_docx_reader.py::test_detects_heading_from_based_on_paragraph_style -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_gridspan_as_col_span -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_vmerge_as_row_span -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_grid_before_as_leading_empty_cells -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_table_rows_and_cells_inside_content_controls -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_nested_table_text_inside_parent_cell -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_numbered_list_from_numbering_xml -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_letter_and_roman_numbering_formats -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_multilevel_numbering_with_parent_markers -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_footnotes_and_endnotes -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_comments_and_comment_reference_marker -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_comment_range_as_inline_annotated_text -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_comment_replies_from_comments_extended -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_inserted_text_and_ignores_deleted_text -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_text_inside_sdt_and_smart_tag_wrappers -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_text_inside_textbox_content -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_drawing_alt_text_from_docpr -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_embedded_image_relationship_as_markdown_reference -v
pytest dochan/tests/test_docx_reader.py::test_records_docx_embedded_image_relationship_as_asset -v
pytest dochan/tests/test_docx_reader.py::test_records_docx_embedded_object_relationships_as_assets -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_vml_object_preview_image_as_markdown_reference -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_field_results_without_instructions -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_core_properties_as_markdown_metadata -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_html_alt_chunk_text -v
pytest dochan/tests/test_docx_reader.py::test_reads_docx_mhtml_alt_chunk_text_and_image_alt -v
```

### PPTX

Added native extraction for:

- `docProps/core.xml` title and creator as Markdown metadata: `# title` and `Author: creator`.
- `a:br` as line breaks.
- text inside `a:fld` fields, such as slide number fields.
- bullet paragraphs from `a:buChar` and auto-numbered paragraphs from `a:buAutoNum`, preserving markers such as `•`, `3.`, and `4.`.
- external hyperlink targets from slide relationship files as `text <URL>`.
- shape-level external hyperlink targets from `p:cNvPr/a:hlinkClick` as `text <URL>`.
- internal slide hyperlink targets from slide relationship files as `text <#ppt/slides/slideN.xml>`.
- multiple slide boundaries are preserved as `## Slide N` Markdown headings when a deck has more than one slide.
- slide speaker notes through slide-level `notesSlide` relationships.
- slide comments through slide-level `comments` relationships plus `ppt/commentAuthors.xml` author metadata, emitted as `[comment: author: text]`.
- static slide-layout text through slide-level `slideLayout` relationships, while skipping placeholder prompt shapes.
- `a:tc` table merge attributes: `gridSpan`, `rowSpan`, `hMerge`, and `vMerge`.
- shape and table reading order by y/x position, including `p:xfrm` graphic frame positions.
- text inside grouped shapes (`p:grpSp`) with recursive position-aware traversal.
- grouped-shape child coordinate transforms from `p:grpSpPr/a:xfrm`, including `a:off`, `a:ext`, `a:chOff`, and `a:chExt`.
- picture alt text from `p:cNvPr` `title` and `descr` attributes.
- embedded image relationships from `a:blip r:embed` as Markdown image references with the `p:cNvPr` label and resolved `ppt/media/...` target.
- linked external image relationships from `a:blip r:link` as Markdown image references without recording a package asset.
- package-root absolute relationship targets such as `/ppt/slides/slide1.xml` and `/ppt/media/image1.png`.
- embedded image relationships as `Document.assets` entries with relationship id, source path, filename, content type, label metadata, slide number, and `source_format: pptx`.
- chart titles, series names, multi-series chart tables, and cached category/value series data from related `ppt/charts/chartN.xml` parts.
- SmartArt diagram text by following `dgm:relIds r:dm` relationships to `ppt/diagrams/dataN.xml`.

Regression test:

```bash
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_breaks_and_field_text -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_bullets_and_auto_numbered_paragraphs -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_core_properties_as_markdown_metadata -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_external_hyperlink_target -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_shape_level_hyperlink_target -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_internal_slide_hyperlink_target -v
pytest dochan/tests/test_pptx_reader.py::test_pptx_markdown_preserves_multiple_slide_boundaries -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_speaker_notes_from_slide_relationship -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_static_text_from_slide_layout -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_merged_table_cells_as_spans -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_elements_by_vertical_position -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_graphic_frames_by_position -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_text_inside_grouped_shape -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_grouped_shape_position_from_child_coordinate_space -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_picture_alt_text_from_cnvpr -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_embedded_image_relationship_as_markdown_reference -v
pytest dochan/tests/test_pptx_reader.py::test_records_pptx_embedded_image_relationship_as_asset -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_chart_title_and_cached_series_data -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_multi_series_chart_as_single_table -v
pytest dochan/tests/test_pptx_reader.py::test_reads_pptx_smartart_diagram_text -v
```

### XLSX

Added native cell handling for:

- `docProps/core.xml` title and creator as Markdown metadata: `# title` and `Author: creator`.
- boolean cells (`t="b"`) as `TRUE` / `FALSE`.
- error cells (`t="e"`) such as `#N/A` and formula errors such as `#DIV/0! (=1/0)`.
- cached formula cells from `<v>` plus formula metadata from `<f>`.
- shared formula follower cells by reusing matching `si` metadata and translating relative references for the follower cell position.
- shared formula whole-column and whole-row ranges such as `A:A` and `1:1`.
- sharedStrings and inline strings with rich text runs.
- external hyperlinks through worksheet relationship targets.
- range hyperlinks such as `A1:B1` by applying the relationship target to each covered cell.
- internal hyperlinks through `location` and `display` attributes as `display <#location>`.
- cell comments from related `xl/commentsN.xml` parts as `[comment: author: text]`.
- merged cell ranges as `Cell.row_span`, `Cell.col_span`, and merged-away cells.
- sparse rows and columns using actual cell references such as `A1`, `C1`, and `A3`.
- multiple sheet names are preserved as Markdown headings when workbook output contains more than one sheet.
- single meaningful sheet names, such as `Report`, are preserved as Markdown headings, while generic default names such as `Sheet`, `Sheet1`, and `Sheet 1` stay suppressed.
- workbook defined names from `xl/workbook.xml`, including built-in names such as `_xlnm.Print_Area`, are emitted as Markdown metadata.
- basic `xl/styles.xml` number formats for dates, percentages, and fixed decimals.
- time and duration number formats such as `h:mm` and `[h]:mm:ss`.
- currency, thousands, and negative accounting-style number formats such as `$#,##0.00`, `#,##0`, `#,##0.0`, `$#,##0.00;[Red]($#,##0.00)`, and `0.0%;[Red](0.0%)`.
- zero-padded identifier number formats such as `00000` and `000-0000`, preserving leading-zero values such as `00123` and `123-4567`.
- literal prefix and suffix number formats such as `0 "kg"`, `0.0"x"`, and `"SKU-"0000`, preserving values such as `12 kg`, `3.5x`, and `SKU-0042`.
- fraction number formats such as `# ?/?` and `# ??/??`, preserving values such as `1/2`, `3 1/4`, and `-1 1/8`.
- scientific number formats such as `0.00E+00` and `0.0E+00`, preserving values such as `1.23E+04`, `1.20E-03`, and `-9.9E+03`.
- Strict OOXML spreadsheet namespaces from `http://purl.oclc.org/ooxml/spreadsheetml/main` and strict relationship attributes from `http://purl.oclc.org/ooxml/officeDocument/relationships`.
- worksheet drawing parts through `<drawing r:id>` relationships.
- sheet header/footer text from worksheet `<headerFooter>` metadata, preserving left/center/right sections as Markdown comments.
- escaped literal ampersands in header/footer text.
- visible header/footer text after quoted font, color, and other formatting control codes.
- drawing text boxes from `xdr:txBody`.
- embedded drawing image relationships from `a:blip r:embed` as Markdown image references with resolved `xl/media/...` targets.
- embedded drawing image relationships as `Document.assets` entries with relationship id, source path, filename, content type, label metadata, sheet name, and `source_format: xlsx`.
- chart titles, series names, multi-series chart tables, and cached category/value series data from related `xl/charts/chartN.xml` parts.
- blank styled cells with no value, formula, comment, hyperlink, or merge origin are ignored when calculating table width, preventing inflated Markdown for large workbook templates.
- blank styled cells are skipped before value parsing so large worksheet templates avoid unnecessary cell-format and value-resolution work.
- empty unreferenced cells are skipped before child scanning and, when possible, before column reference parsing, even when unrelated merge metadata exists.
- trailing blank styled rows are ignored when calculating the emitted table height.
- shared formula definitions are captured while reading cells, removing the previous full-sheet shared-formula pre-scan.
- cell child elements (`v`, `f`, `is`) are classified once and reused for value parsing, formula rendering, and blank-cell checks.
- parsed number format metadata is cached, so repeated date, percentage, and decimal formats avoid repeated format classification.
- package-root absolute relationship targets such as `/xl/worksheets/sheet1.xml`, `/xl/drawings/drawing1.xml`, and `/xl/media/image1.png`.
- ZIP members stored with backslashes, such as `xl\workbook.xml`, through normalized package name lookup while retaining strict traversal checks.

Regression test:

```bash
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_booleans_and_cached_formula_values -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_core_properties_as_markdown_metadata -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_error_cells_and_formula_errors -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_formula_metadata_with_cached_values -v
pytest dochan/tests/test_xlsx_reader.py::test_xlsx_cell_text_uses_single_child_scan_for_value_and_formula -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_shared_formula_metadata -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_shared_formula_whole_column_and_row_ranges -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_shared_formula_without_prescanning_sheet_cells -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_rich_text_shared_and_inline_strings -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_external_hyperlinks_with_targets -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_range_hyperlinks_with_targets -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_internal_hyperlinks_with_display_and_location -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_cell_comments_from_comment_relationship -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_merged_cells_as_spans -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_drawing_textboxes_and_image_references -v
pytest dochan/tests/test_xlsx_reader.py::test_records_xlsx_drawing_image_relationship_as_asset -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_chart_title_and_cached_series_data -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_multi_series_chart_as_single_table -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_sparse_rows_and_columns_by_cell_references -v
pytest dochan/tests/test_xlsx_reader.py::test_xlsx_markdown_preserves_multiple_sheet_names -v
pytest dochan/tests/test_xlsx_reader.py::test_xlsx_markdown_preserves_single_meaningful_sheet_name -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_workbook_defined_names_as_metadata -v
pytest dochan/tests/test_xlsx_reader.py::test_ignores_blank_styled_cells_when_calculating_xlsx_table_width -v
pytest dochan/tests/test_xlsx_reader.py::test_skips_blank_styled_xlsx_cells_before_value_parsing -v
pytest dochan/tests/test_xlsx_reader.py::test_skips_unreferenced_empty_xlsx_cells_before_child_scanning -v
pytest dochan/tests/test_xlsx_reader.py::test_ignores_trailing_blank_styled_xlsx_rows -v
pytest dochan/tests/test_xlsx_reader.py::test_caches_xlsx_number_format_metadata -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_dates_percentages_and_decimals_from_styles -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_time_and_duration_number_formats -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_currency_and_thousands_number_formats -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_negative_accounting_number_formats -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_zero_padded_identifier_number_formats -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_xlsx_literal_prefix_and_suffix_number_formats -v
pytest dochan/tests/test_xlsx_reader.py::test_reads_strict_xlsx_namespace_shared_strings_as_table -v
```

## Verification

Fresh full suite:

```bash
pytest dochan/tests/
```

Result:

```text
195 passed
```

Generated corpus benchmark:

```bash
TMPDIR=$(mktemp -d /tmp/dochan-ooxml-bench.XXXXXX)
/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/generate_ooxml_benchmark_corpus.py "$TMPDIR"
/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/benchmark_competitors.py "$TMPDIR" --formats docx,pptx,xlsx --runs 2
rm -rf "$TMPDIR"
```

Result:

```json
{
  "file_count": 3,
  "requested_converters": ["dochan", "markitdown", "docling"],
  "converter_status": {
    "dochan": {"available": true, "error": ""},
    "markitdown": {"available": false, "error": "ModuleNotFoundError(...)"},
    "docling": {"available": false, "error": "ModuleNotFoundError(...)"}
  },
  "converters": ["dochan"],
  "runs": 2,
  "summary": [
    {"format": "docx", "median_seconds": 0.0118, "mean_accuracy": 1.0},
    {"format": "pptx", "median_seconds": 0.0012, "mean_accuracy": 1.0},
    {"format": "xlsx", "median_seconds": 0.0020, "mean_accuracy": 1.0}
  ],
  "profile_fields": [
    "median_table_rows",
    "median_headings",
    "median_links",
    "median_image_references",
    "median_comments",
    "median_bookmarks",
    "median_formula_markers"
  ],
  "format_summary_fields": [
    "files",
    "runs",
    "success_rate",
    "best_seconds",
    "median_seconds",
    "mean_accuracy",
    "median_chars",
    "median_table_rows",
    "median_headings",
    "median_links",
    "median_image_references",
    "median_comments",
    "median_bookmarks",
    "median_formula_markers"
  ],
  "competitive_summary_fields": [
    "format",
    "competitor",
    "speedup_vs_competitor",
    "accuracy_delta",
    "success_rate_delta",
    "median_chars_delta",
    "median_table_rows_delta",
    "median_links_delta",
    "median_image_references_delta",
    "median_comments_delta",
    "median_bookmarks_delta",
    "median_formula_markers_delta"
  ],
  "improvement_candidate_fields": [
    "format",
    "competitor",
    "worst_gap_score",
    "reasons"
  ]
}
```

Latest focused DOCX generated-corpus core-properties, character-style run formatting, run-level underline/strike/superscript/subscript Markdown formatting, multilevel numbering, skipped-leading-cell table, embedded image relationship asset tracking, comment-range annotation, and comment-reply check:

| File | Runs | Median seconds | Accuracy | Chars | Headings | Links | Images | Comments |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `sample.docx` | 2 | 0.01188s | 1.0 | 1127 | 3 | 2 | 1 | 1 |

The output includes `# Board Report`, `Author: Alice Analyst`, `<u>Underlined decision</u> and ~~Deprecated note~~`, `CO<sub>2</sub> target<sup>1</sup>`, `***Styled emphasis*** <u>Styled action</u> ~~Styled obsolete~~ <sub>2</sub>`, `a) Alpha item`, `X. Roman item`, `1.a) Child alpha`, `2.a) Child reset`, `![Revenue Chart ARR increased 42 percent Revenue chart](word/media/image1.png)`, `Body comment [comment 1: Comment detail]`, `Reply from Approver: Approved after legal review`, and the sparse table row `["", "Q3"]` from `w:gridBefore`, so DOCX core properties, character-style run formatting, run-level underline/strike/superscript/subscript Markdown formatting, non-decimal numbering, parent-aware multilevel numbering, lower-level counter reset, embedded image Markdown references, comment range annotations, comment replies, and skipped leading table cells now contribute to the benchmark scorer through `expected_markdown`, `expected_text`, and `expected_tables`. The same image relationship is recorded in `Document.assets` as `word/media/image1.png` with `image/png` content type.

Latest focused PPTX generated-corpus core-property, slide-heading, list, run-level formatting, image-reference, grouped-shape child coordinate transform, SmartArt, image asset tracking, and multi-series chart check:

| File | Runs | Median seconds | Accuracy | Chars | Headings | Links |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `sample.pptx` | 2 | 0.00130s | 1.0 | 740 | 4 | 3 |

The output includes `# Board Update Deck`, `Author: Alice Analyst`, `## Slide 1`, `## Slide 2`, `• Bullet point`, `3. Third item`, `4. Fourth item`, `**Bold insight** *Italic caveat* <u>Underlined action</u> ~~Deprecated slide note~~`, `Grouped coordinate insight`, SmartArt diagram text `Plan` and `Build`, `![Revenue Chart ARR up 42 percent Picture 1](ppt/media/image1.png)`, and chart table header `Category | ARR | Profit`, so package metadata, multi-slide boundaries, PPTX list markers, run-level bold/italic/underline/strike Markdown formatting, grouped-shape child-coordinate ordering, SmartArt diagram data, embedded PPTX image relationships, and multi-series chart data now contribute to the benchmark scorer through `expected_markdown`, `expected_text`, and `expected_tables`. The same PPTX image relationship is recorded in `Document.assets` as `ppt/media/image1.png` with `image/png` content type and slide metadata.

Latest focused XLSX generated-corpus core-property, workbook-defined-name, sheet-heading, shared formula range translation, currency/thousands number-format, negative accounting-style format, zero-padded identifier custom format, literal prefix/suffix custom format, fraction number format, scientific number format, embedded drawing image asset tracking, multi-series chart, and multi-block table check:

| File | Runs | Median seconds | Accuracy | Chars | Table rows | Headings | Images |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `sample.xlsx` | 2 | 0.00224s | 1.0 | 1291 | 28 | 4 | 1 |

The output includes `# Financial Workbook`, `Author: Finance Team`, `Defined name: SalesRange = Data!$A$1:$C$24`, `Defined name: Print_Area = Data!$A$1:$C$24`, `![Workbook revenue snapshot Picture 1](xl/media/image1.png)`, `## Data`, `### Revenue Chart`, `## Summary`, `12:00`, `36:00:00`, `$1,234.50`, `1,234`, `1,234.6`, `($1,234.50)`, `(1,234)`, `(12.5%)`, `00123`, `123-4567`, `12 kg`, `3.5x`, `SKU-0042`, `1/2`, `3 1/4`, `-1 1/8`, `1.23E+04`, `1.20E-03`, `-9.9E+03`, `10 (=SUM(A:A)+SUM(1:1))`, `20 (=SUM(B:B)+SUM(2:2))`, chart table header `Category | ARR | Profit`, `General Information`, `Business Description`, `Financials`, `809127967.92`, and `847831.96`, so package metadata, workbook defined names, sheet names, embedded drawing image references, shared formula whole-column/whole-row range translation, time/duration, currency/thousands, accounting-style negative number formats, zero-padded identifier formats, literal prefix/suffix custom number formats, fraction number formats, scientific number formats, multi-series chart data, and separated business-table blocks now contribute to the benchmark scorer through `expected_markdown`, `expected_tables`, and `expected_table_rows`. The same image relationship is recorded in `Document.assets` as `xl/media/image1.png` with `image/png` content type and sheet metadata.

Public corpus smoke:

```bash
TMPDIR=$(mktemp -d /tmp/dochan-public-ooxml.XXXXXX)
/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/download_public_ooxml_corpus.py "$TMPDIR" --formats docx,pptx,xlsx
/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/benchmark_competitors.py "$TMPDIR" \
  --formats docx,pptx,xlsx \
  --converters dochan \
  --runs 1 \
  --save-outputs "$TMPDIR/outputs" \
  --output "$TMPDIR/dochan.json"
```

Latest result after expanding the public corpus to 50 files and adding full 50-file semantic expectations:

| Format | Files | Non-empty outputs | Notes |
| --- | ---: | ---: | --- |
| DOCX | 18 | 18 | Expanded public coverage now includes comments, headers/footers, Unicode headers/footers, numbering, footnotes, endnotes, bookmarks, heading levels, legacy form checkboxes, anchored shape text boxes, doxx comprehensive structure, Apache POI sample documents, image-heavy documents, an excessive-depth nested-table fixture, and embedded OLE/package object relationships. |
| PPTX | 14 | 14 | The minimal fixture is a metadata-only deck with no slide part or presentation text nodes. Public fixtures cover notes, slide comments, Unicode text, hyperlinks, shapes, pictures, charts, chart titles/data, tables, and master-slide text. |
| XLSX | 18 | 18 | Expanded public coverage now includes `pyexcel` Strict OOXML, Apache POI Strict OOXML, inline strings, shared hyperlinks, `eparse` nested/unit workbooks, Apache POI formulas, Apache POI cell comments, drawing text boxes, embedded drawing image references, picture worksheets, chart titles, cached chart series data, worksheet header/footer strings, escaped ampersands, and header/footer formatting control codes; all eighteen produce non-empty Markdown with table rows, drawing text, image references, chart data, or header/footer comments. |

The public corpus now scores every public fixture semantically. dochan scores accuracy 1.0 and success 1.0 on all 50 expected public fixtures, including legacy form checkbox markers in paragraphs, tables, and sequences, anchored DOCX shape text without Choice/Fallback duplication, DOCX embedded OLE/package assets, PPTX slide comments, and XLSX sheet header/footer comments with escaped ampersands and stripped formatting control codes.

Public XLSX parser profile after sheet heading preservation, early blank-cell skipping, shared-formula single-pass capture, one-pass cell child classification, number-format metadata caching, and fast empty-cell/reference skipping:

| File | Runs | Median seconds | Chars | Headings | Non-empty |
| --- | ---: | ---: | ---: | ---: | --- |
| `pyexcel-bug-176.xlsx` | 5 | 0.259s | 311,559 | 3 | true |
| `pyexcel-empty-sheet.xlsx` | 5 | 0.00039s | 132 | 3 | true |

`pyexcel-bug-176.xlsx` profile changed from roughly 65,025 `_cell_text` calls plus a full shared-formula pre-scan to 24,503 `_cell_text` calls with formula capture during the main cell pass. Reusing a single child scan per cell then reduced repeated `find()`/namespace work, caching number-format metadata avoids repeated classification for the same style formats, and fast empty-cell/reference skipping reduced `_cell_children()` and `_column_index()` work to content-bearing cells. End-to-end benchmark median for this file remains about 0.259s in the latest 5-run dochan-only smoke run while preserving 18 formula markers and adding 3 sheet headings.

Public isolated competitor rerun on the 50-file corpus with full semantic expectations using Python 3.14:

| Competitor | Format | Speedup | Accuracy delta | Success delta | Improvement candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | docx | 12.53x | +0.504 | +0.056 | none |
| MarkItDown | pptx | 7.92x | +0.372 | +0.071 | none |
| MarkItDown | xlsx | 17.68x | +0.789 | +0.222 | none |
| Docling | docx | 16.29x | +0.533 | +0.056 | none |
| Docling | pptx | 19.25x | +0.618 | +0.214 | none |
| Docling | xlsx | 22.62x | +0.891 | +0.389 | none |

Additional Apache POI wide probe, run on 2026-06-21, downloaded 42 previously unused `apache/poi` OOXML fixtures and excluded one non-ZIP `.pptx`, leaving 41 files: 14 DOCX, 13 PPTX, and 14 XLSX. The first file-level pass found three candidates. Manual inspection classified one XLSX candidate as MarkItDown `NaT`/`NaN`/`Unnamed` placeholder row noise and two as real native gaps:

- DOCX body-level `w:sdt` content controls were skipped, which dropped resume-template body text in `60316.docx`; dochan now recursively expands block-level `w:sdt`/`w:sdtContent` while preserving document order.
- PPTX linked external images using `a:blip r:link` were skipped as image references in `56812.pptx`; dochan now emits link-only pictures as Markdown image references without recording them as package assets.
- The benchmark profiler now treats `NaT` like `NaN` and `Unnamed: n`, so pandas placeholder rows do not become semantic file-level candidates.

After those fixes, an isolated MarkItDown rerun on the 41-file probe reported no format-level or file-level candidates:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 14.11x | +0.143 | none |
| MarkItDown | pptx | 13.67x | +0.077 | none |
| MarkItDown | xlsx | 10.86x | +0.000 | none |

The preceding full MarkItDown/Docling rerun on the same probe, after DOCX/PPTX parser fixes but before the `NaT` profiler filter, already had no Docling file-level candidates and showed dochan ahead by 15.28x DOCX, 23.19x PPTX, and 12.21x XLSX with better success deltas in all three formats. The remaining MarkItDown XLSX candidate disappeared after placeholder filtering.

Additional Apache POI third probe, run on 2026-06-21, downloaded 47 more valid previously unused `apache/poi` OOXML fixtures after excluding one non-ZIP `.pptx`: 16 DOCX, 15 PPTX, and 16 XLSX. The Dochan-only pass found one true compatibility gap and one legitimate empty document:

- `49609.xlsx` stores package entries with backslashes such as `xl\workbook.xml`; dochan now normalizes ZIP member names into OOXML part names so the workbook, relationships, sheets, styles, and shared strings are found.
- `59378.docx` has no `w:t` or field instruction text in `word/*.xml`; it remains a legitimate empty-output fixture rather than a parser miss.

Post-fix Dochan-only rerun on the 47-file probe: DOCX success 0.9375 because of the empty DOCX, PPTX success 1.0, XLSX success 1.0, and no parser errors. Post-fix isolated MarkItDown/Docling rerun produced no format-level or file-level candidates: MarkItDown speedups were 15.12x DOCX, 13.72x PPTX, and 7.38x XLSX; Docling speedups were 14.39x DOCX, 18.42x PPTX, and 8.70x XLSX. Dochan had better success deltas in every compared format.

Additional Apache POI fourth probe, run on 2026-06-21, covered 57 valid previously unused `apache/poi` OOXML fixtures after excluding three corrupt or non-ZIP `.pptx` files: 20 DOCX, 17 PPTX, and 20 XLSX. The Dochan-only pass reported success 1.0 for DOCX/PPTX/XLSX with no empty outputs. The isolated MarkItDown pass had no file-level candidates. The isolated Docling pass found one real structural DOCX gap: `IllustrativeCases.docx` uses Word's built-in `Title` paragraph style for the visible document title, while dochan only promoted `HeadingN` style ids to Markdown headings. Dochan now treats the `Title` paragraph style as H1, so the file begins with `# (V) ILLUSTRATIVE CASES` and the profile heading count matches Docling.

Post-fix isolated Docling rerun on the 57-file probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 16.15x | +0.200 | none |
| pptx | 18.81x | +0.294 | none |
| xlsx | 23.52x | +0.100 | none |

Additional Apache POI fifth probe, run on 2026-06-21, covered another 60 valid previously unused `apache/poi` OOXML fixtures: 20 DOCX, 20 PPTX, and 20 XLSX. The Dochan-only pass reported success 1.0 for DOCX/PPTX/XLSX with no empty outputs. Isolated MarkItDown produced no file-level candidates and showed dochan ahead by 14.73x DOCX, 8.33x PPTX, and 13.51x XLSX, with a +0.050 DOCX success delta and equal PPTX/XLSX success. The first isolated Docling pass found one file-level XLSX candidate, `AverageTaxRates.xlsx`, where Docling emitted many more Markdown table rows. Manual inspection showed this was not a native parser miss: dochan preserved the workbook's three tax-rate sheets as compact wide tables with formatted percentages, while Docling split merged spreadsheet regions into many smaller tables and emitted raw decimal/floating-point values such as `0.0617` and `0.13079200000000002`. The profiler now ignores numeric-only tokens for unique-token deltas, keeping table-row-only spreadsheet layout fragmentation out of the candidate queue unless there is additional non-numeric text evidence.

Post-filter isolated Docling rerun on the 60-file fifth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 12.38x | +0.050 | none |
| pptx | 10.25x | +0.100 | none |
| xlsx | 15.91x | +0.100 | none |

Additional Apache POI sixth probe, run on 2026-06-21, covered another 60 valid previously unused `apache/poi` OOXML fixtures: 20 DOCX, 20 PPTX, and 20 XLSX. The Dochan-only pass reported success 1.0 for DOCX/PPTX/XLSX with no empty outputs; median conversion times were about 0.00093s DOCX, 0.00082s PPTX, and 0.00093s XLSX. The initial isolated MarkItDown pass found two file-level candidates. Manual inspection classified one as profiler noise: `missing-blip-fill.pptx` contains a picture element with an empty `p:blipFill` and no image relationship, while MarkItDown generated `![](Shape662.jpg)` for a non-existent media file. The profiler now ignores generated empty-alt `ShapeNNN` image placeholders. The second candidate was a useful native output improvement: `craftonhills.edu_programreview_report.aspx_goalpriorityreport_0011d159-1eeb-4b63-8833-867b0926e5f3.xlsx` has a single meaningful sheet named `Report`; dochan now emits `## Report` for such workbooks while still suppressing generic default `Sheet*` names.

Post-fix isolated MarkItDown rerun on the 60-file sixth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 12.39x | +0.300 | none |
| pptx | 11.97x | +0.000 | none |
| xlsx | 15.13x | +0.000 | none |

The initial isolated Docling run on the same sixth probe already had no file-level candidates and showed dochan ahead by 16.03x DOCX, 19.09x PPTX, and 21.16x XLSX, with success deltas of +0.300, +0.300, and +0.050.

Additional Apache POI seventh probe, run on 2026-06-21, covered another 60 valid previously unused `apache/poi` OOXML fixtures: 20 DOCX, 20 PPTX, and 20 XLSX. The Dochan-only pass reported success 1.0 for DOCX/PPTX/XLSX with no empty outputs; median conversion times were about 0.00106s DOCX, 0.00297s PPTX, and 0.00140s XLSX. Isolated MarkItDown and Docling produced no format-level or file-level candidates, so this loop did not require a parser change.

Isolated MarkItDown rerun on the 60-file seventh probe:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 14.73x | +0.200 | none |
| pptx | 5.19x | +0.050 | none |
| xlsx | 10.97x | +0.000 | none |

Isolated Docling rerun on the 60-file seventh probe:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 15.39x | +0.150 | none |
| pptx | 10.43x | +0.250 | none |
| xlsx | 15.04x | +0.150 | none |

Additional Apache POI eighth probe, run on 2026-06-21, covered another 60 valid previously unused `apache/poi` OOXML fixtures: 20 DOCX, 20 PPTX, and 20 XLSX. The selector now validates OOXML ZIPs by opening the central directory and running `ZipFile.testzip()`, not just `zipfile.is_zipfile()`, because several Apache POI fuzz samples have a ZIP signature but a broken central directory or CRC failure. Those corrupt PPTX files were excluded before benchmarking. `48779.xlsx` was inspected manually and marked `expected_empty` because it is a valid workbook with three default sheets and no values. The Dochan-only pass then reported success 1.0 for DOCX/PPTX/XLSX with no unexpected empty outputs.

Isolated MarkItDown rerun on the 60-file eighth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 13.15x | +0.100 | n/a | none |
| pptx | 12.76x | +0.000 | n/a | none |
| xlsx | 19.70x | +0.050 | +1.000 | none |

Isolated Docling rerun on the 60-file eighth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.85x | +0.100 | n/a | none |
| pptx | 23.72x | +0.100 | n/a | none |
| xlsx | 31.66x | +0.000 | +0.000 | none |

Additional Apache POI ninth probe, run on 2026-06-21, covered 54 valid remaining previously unused Apache POI OOXML fixtures: 20 DOCX, 14 PPTX, and 20 XLSX. The remaining PPTX pool had only 14 valid unused files after ZIP central-directory and CRC validation; corrupt fuzz/crash samples were skipped. `Tika-792.docx` was marked `expected_empty` after manual XML inspection showed only deleted or moved-from tracked text, not visible final text. `52425.xlsx` was also marked `expected_empty` because the workbook has no cell values, only blank comment author metadata and an empty VML note. Dochan-only conversion reported success 1.0 for DOCX/PPTX/XLSX with no unexpected empty outputs, and no parser change was needed.

Isolated MarkItDown rerun on the 54-file ninth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.54x | +0.000 | +0.000 | none |
| pptx | 11.67x | +0.000 | n/a | none |
| xlsx | 15.65x | +0.050 | +1.000 | none |

Isolated Docling rerun on the 54-file ninth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 18.48x | +0.000 | +0.000 | none |
| pptx | 21.20x | +0.214 | n/a | none |
| xlsx | 19.66x | +0.100 | +0.000 | none |

Additional Apache POI tenth probe, run on 2026-06-21, covered 60 valid Apache POI OOXML fixtures selected from less-exercised tail names after ZIP central-directory and CRC validation: 20 DOCX, 20 PPTX, and 20 XLSX. The Dochan-only pass initially exposed one real DOCX gap: `zero-length.docx` has no body text but does contain a header image relationship, so it is not semantically empty. Dochan now reads header/footer part relationships such as `word/_rels/header1.xml.rels`, emits `<!-- header: ![Picture](word/media/image1.png) -->`, and records the image as a structured DOCX asset.

The first isolated MarkItDown pass then exposed one real table-structure gap in `tika-3816.docx`: a table row and one table cell were wrapped inside nested `w:sdt/w:sdtContent` content controls, so dochan emitted blank cells while MarkItDown surfaced `Choose an item.` and `Here is just a sample`. Dochan now expands content controls, smart tags, tracked insertions, and preferred `mc:AlternateContent` wrappers inside DOCX table rows, cells, and table cells. A post-fix Dochan-only pass reported DOCX/PPTX/XLSX success 1.0 with zero unexpected empty outputs.

Post-fix isolated MarkItDown rerun on the 60-file tenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.36x | +0.150 | n/a | none |
| pptx | 11.10x | +0.000 | n/a | none |
| xlsx | 24.31x | +0.000 | n/a | none |

Post-fix isolated Docling rerun on the 60-file tenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 15.71x | +0.150 | n/a | none |
| pptx | 20.25x | +0.150 | n/a | none |
| xlsx | 33.85x | +0.100 | n/a | none |

Additional Apache POI eleventh probe, run on 2026-06-21, covered 60 more valid Apache POI OOXML fixtures selected from early repository names after excluding documented/public and recent ninth/tenth samples: 20 DOCX, 20 PPTX, and 20 XLSX. One corrupt PPTX (`Divino_Revelado.pptx`) was skipped after ZIP validation. Dochan-only conversion reported DOCX/PPTX/XLSX success 1.0 with zero unexpected empty outputs, so no expected-empty override or parser change was needed.

Isolated MarkItDown rerun on the 60-file eleventh probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.23x | +0.200 | n/a | none |
| pptx | 10.48x | +0.050 | n/a | none |
| xlsx | 10.44x | +0.000 | n/a | none |

Isolated Docling rerun on the 60-file eleventh probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 16.29x | +0.150 | n/a | none |
| pptx | 17.77x | +0.300 | n/a | none |
| xlsx | 16.43x | +0.150 | n/a | none |

Additional Apache POI twelfth probe, run on 2026-06-21, exercised the fixture-index plus probe-manifest path against 30 Apache POI files: 10 DOCX, 10 PPTX, and 10 XLSX. ZIP validation passed for all 30 files. The initial Dochan-only pass reported two empty outputs, `59378.docx` and `48779.xlsx`; manual package inspection showed both are semantically empty fixtures with no visible text/value/media payload. `48779.xlsx` only has generic empty `Sheet1`/`Sheet2`/`Sheet3` sheets, and MarkItDown emitted those generic sheet headings plus blank tables. The benchmark now marks no-payload OOXML inputs as `input_semantic_empty`, so broad no-manifest corpora do not treat dochan's empty output as a failure while rewarding competitor boilerplate.

Rescored isolated MarkItDown rerun on the 30-file twelfth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.15x | +0.200 | n/a | none |
| pptx | 3.76x | +0.000 | n/a | none |
| xlsx | 13.46x | +0.100 | n/a | none |

Rescored isolated Docling rerun on the 30-file twelfth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.26x | +0.200 | n/a | none |
| pptx | 15.78x | +0.000 | n/a | none |
| xlsx | 22.30x | +0.100 | n/a | none |

Additional Apache POI thirteenth probe, run on 2026-06-21, used `build_apache_poi_fixture_index.py` plus a seeded probe manifest to select the next 30 Apache POI files after the eleventh/twelfth samples: 10 DOCX, 10 PPTX, and 10 XLSX. The selected files were `DiffFirstPageHeadFoot.docx`, `EmbeddedDocument.docx`, `EmptyDocumentWithHeaderFooter.docx`, `EnforcedWith.docx`, `ExternalEntityInText.docx`, `FancyFoot.docx`, `FieldCodes.docx`, `FldSimple.docx`, `HeaderFooterUnicode.docx`, `Headers.docx`, `bug54570.pptx`, `bug58144-headers-footers-2007.pptx`, `bug60499.pptx`, `bug60715.pptx`, `bug60993.pptx`, `bug62513.pptx`, `bug62736.pptx`, `bug63290.pptx`, `bug64693.pptx`, `bug65228.pptx`, `49928.xlsx`, `49966.xlsx`, `50096.xlsx`, `50299.xlsx`, `50755_workday_formula_example.xlsx`, `50784-font_theme_colours.xlsx`, `50786-indexed_colours.xlsx`, `50795.xlsx`, `50846-border_colours.xlsx`, and `50867_with_table.xlsx`. ZIP validation passed for all 30 files. Dochan-only conversion reported success 1.0 in all three formats, with no errors and no empty outputs.

Isolated MarkItDown rerun on the 30-file thirteenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 10.54x | +0.400 | n/a | none |
| pptx | 12.57x | +0.000 | n/a | none |
| xlsx | 16.24x | +0.000 | n/a | none |

Isolated Docling rerun on the 30-file thirteenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 16.32x | +0.400 | n/a | none |
| pptx | 22.70x | +0.200 | n/a | none |
| xlsx | 25.85x | +0.000 | n/a | none |

Additional Apache POI fourteenth probe, run on 2026-06-21, used the same fixture-index/manifest flow on the next 15 Apache POI files: 5 DOCX, 5 PPTX, and 5 XLSX. The selected files were `IllustrativeCases.docx`, `MultipleBodyBug.docx`, `NoHeadFoot.docx`, `Numbering.docx`, `NumberingWOverrides.docx`, `bug65523.pptx`, `bug65551.pptx`, `bug65673.pptx`, `bug68703.pptx`, `ca.ubc.cs.people_~emhill_presentations_HowWeRefactor.pptx`, `51222.xlsx`, `51470.xlsx`, `51519.xlsx`, `51585.xlsx`, and `51626.xlsx`. ZIP validation passed for all 15 files. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 15-file fourteenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 9.34x | +0.000 | n/a | none |
| pptx | 19.09x | +0.000 | n/a | none |
| xlsx | 14.50x | +0.000 | n/a | none |

Isolated Docling rerun on the 15-file fourteenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 4.69x | +0.000 | n/a | none |
| pptx | 20.80x | +0.200 | n/a | none |
| xlsx | 14.34x | +0.200 | n/a | none |

Additional Apache POI fifteenth probe, run on 2026-06-21, used a seed manifest containing the known twelfth, thirteenth, and fourteenth fixture ids, then selected the next 30 Apache POI files: 10 DOCX, 10 PPTX, and 10 XLSX. The selected files were `51921-Word-Crash067.docx`, `52288.docx`, `52449.docx`, `55733.docx`, `55966.docx`, `56392.docx`, `57312.docx`, `58067.docx`, `58618.docx`, `59030.docx`, `2411-Performance_Up.pptx`, `45541_Footer.pptx`, `45541_Header.pptx`, `49386-null_dates.pptx`, `51187.pptx`, `54542_cropped_bitmap.pptx`, `60042.pptx`, `60810.pptx`, `61515.pptx`, `63200.pptx`, `123233_charts.xlsx`, `1_NoIden.xlsx`, `45430.xlsx`, `45540_classic_Footer.xlsx`, `45540_classic_Header.xlsx`, `45540_form_Footer.xlsx`, `45540_form_Header.xlsx`, `45544.xlsx`, `46535.xlsx`, and `46536.xlsx`. ZIP validation passed for all 30 files. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 30-file fifteenth probe produced no format-level or file-level candidates. MarkItDown failed one PPTX fixture, `2411-Performance_Up.pptx`, with a `PptxConverter` `InvalidXmlError` for a missing required `p:blipFill` child:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.32x | +0.000 | n/a | none |
| pptx | 12.45x | +0.100 | n/a | none |
| xlsx | 11.51x | +0.000 | n/a | none |

Isolated Docling rerun on the 30-file fifteenth probe produced no format-level or file-level candidates. Docling produced empty outputs for `51187.pptx`, `60042.pptx`, `61515.pptx`, `63200.pptx`, and `45430.xlsx`, while dochan produced non-empty outputs for all five:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.57x | +0.000 | n/a | none |
| pptx | 23.86x | +0.400 | n/a | none |
| xlsx | 10.26x | +0.100 | n/a | none |

Additional Apache POI sixteenth probe, run on 2026-06-21, used a seed manifest containing the known fixture ids through the fifteenth probe, then selected the next 30 Apache POI files: 10 DOCX, 10 PPTX, and 10 XLSX. The selected files were `60293.docx`, `60329.docx`, `61470.docx`, `61745.docx`, `61787.docx`, `61991.docx`, `65099.docx`, `Bug51170.docx`, `Bug54771a.docx`, `Bug54771b.docx`, `ArtisticEffectSample.pptx`, `EmbeddedAudio.pptx`, `EmbeddedVideo.pptx`, `KEY02.pptx`, `LIBRE_OFFICE-100610-0.pptx`, `OverlappingRelations.pptx`, `SampleShow.pptx`, `SmartArt.pptx`, `aascu.org_hbcu_leadershipsummit_cooper_.pptx`, `aascu.org_workarea_downloadasset.aspx_id=5864.pptx`, `47090.xlsx`, `47504.xlsx`, `47668.xlsx`, `47737.xlsx`, `47804.xlsx`, `47813.xlsx`, `47862.xlsx`, `47889.xlsx`, `48495.xlsx`, and `48539.xlsx`. ZIP validation passed for all 30 files. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 30-file sixteenth probe produced no format-level or file-level candidates. MarkItDown failed `60329.docx` with a `DocxConverter` `KeyError` for `w:type`, and produced empty outputs for `61470.docx` and `61745.docx`, while dochan produced non-empty outputs for all three:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 11.86x | +0.300 | n/a | none |
| pptx | 10.11x | +0.000 | n/a | none |
| xlsx | 18.82x | +0.000 | n/a | none |

Isolated Docling rerun on the 30-file sixteenth probe produced no format-level or file-level candidates. Docling produced empty outputs for `61470.docx`, `61745.docx`, `EmbeddedVideo.pptx`, and `SmartArt.pptx`, while dochan produced non-empty outputs for all four. Docling also produced empty outputs for `47090.xlsx` and `47504.xlsx`, both classified as semantic-empty inputs:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 12.18x | +0.200 | n/a | none |
| pptx | 15.37x | +0.200 | n/a | none |
| xlsx | 24.83x | +0.000 | n/a | none |

Additional Apache POI seventeenth probe, run on 2026-06-21, selected the next 30 Apache POI files after the known fixture ids through the sixteenth probe. Seven PPTX clusterfuzz fixtures were invalid ZIP files and were excluded from conversion: `clusterfuzz-testcase-minimized-POIFuzzer-5205835528404992.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-4838644450394112.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-4986044400861184.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-5463285576892416.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-5471515212382208.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-5611274456596480.pptx`, and `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6071540680032256.pptx`. The remaining 23 valid files were `NumberingWithOutOfOrderId.docx`, `PageSpecificHeadFoot.docx`, `SampleDoc.docx`, `SimpleHeadThreeColFoot.docx`, `Styles.docx`, `TestDocument.docx`, `TestPoiXMLDocumentCorePropertiesGetKeywords.docx`, `TestTableCellAlign.docx`, `TestTableColumns.docx`, `ThreeColFoot.docx`, `chart-picture-bg.pptx`, `chart-slide-bg.pptx`, `chart-texture-bg.pptx`, `51626_contact.xlsx`, `51710.xlsx`, `51850.xlsx`, `51963.xlsx`, `51998.xlsx`, `52348.xlsx`, `52575_main.xlsx`, `52716.xlsx`, `53101.xlsx`, and `53105.xlsx`. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 23-valid-file seventeenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 9.74x | +0.000 | n/a | none |
| pptx | 11.18x | +0.000 | n/a | none |
| xlsx | 9.56x | +0.000 | n/a | none |

Isolated Docling rerun on the 23-valid-file seventeenth probe produced no format-level or file-level candidates. Docling produced empty outputs for all three valid PPTX chart-background fixtures, `chart-picture-bg.pptx`, `chart-slide-bg.pptx`, and `chart-texture-bg.pptx`, while dochan produced non-empty outputs:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 18.79x | +0.000 | n/a | none |
| pptx | 17.53x | +1.000 | n/a | none |
| xlsx | 14.87x | +0.000 | n/a | none |

Additional Apache POI eighteenth probe, run on 2026-06-21, selected the next 30 Apache POI files after the known fixture ids through the seventeenth probe. Five files were invalid ZIP inputs and were excluded from conversion: `bug53475-password-is-pass.docx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6254434927378432.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6372932378820608.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6435650376957952.pptx`, and `crash-57308ca363f5b71763c489d1b432aff009d4bc4f.pptx`. The remaining 25 valid files were `ThreeColHead.docx`, `ThreeColHeadFoot.docx`, `VariousPictures.docx`, `WithGIF.docx`, `WithTabs.docx`, `WordWithAttachments.docx`, `bib-chernigovka.netdo.ru_download_docs_17459.docx`, `bookmarks.docx`, `bug-paragraph-alignment.docx`, `copy-slide-demo.pptx`, `customGeo.pptx`, `ececapstonespring2012.pptx`, `highlight-test-case.pptx`, `keyframes.pptx`, `layouts.pptx`, `53282.xlsx`, `53282b.xlsx`, `53568.xlsx`, `53734.xlsx`, `53798.xlsx`, `53798_shiftNegative_TMPL.xlsx`, `54034.xlsx`, `54071.xlsx`, `54084 - Greek - beyond BMP.xlsx`, and `54206.xlsx`. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 25-valid-file eighteenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.35x | +0.000 | n/a | none |
| pptx | 4.18x | +0.000 | n/a | none |
| xlsx | 15.78x | +0.000 | n/a | none |

Isolated Docling rerun on the 25-valid-file eighteenth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 22.84x | +0.000 | n/a | none |
| pptx | 9.25x | +0.000 | n/a | none |
| xlsx | 22.36x | +0.000 | n/a | none |

Additional Apache POI nineteenth probe, run on 2026-06-21, selected the next 30 Apache POI files after the known fixture ids through the eighteenth probe. One password-protected/non-ZIP DOCX file was excluded from conversion: `bug53475-password-is-solrcell.docx`. The remaining 29 valid files were `bug56075-changeTracking_off.docx`, `bug56075-changeTracking_on.docx`, `bug56076.docx`, `bug57031.docx`, `bug59058.docx`, `bug65649.docx`, `bug65738.docx`, `bug66312.docx`, `bug69628.docx`, `line-chart.pptx`, `minimal-gradient-fill-issue.pptx`, `picture-transparency.pptx`, `pie-chart.pptx`, `placeholder-layout-color.pptx`, `pptx2svg.pptx`, `prProps.pptx`, `present1.pptx`, `radar-chart.pptx`, `rain.pptx`, `54288-ref.xlsx`, `54288.xlsx`, `54399.xlsx`, `54436.xlsx`, `54524.xlsx`, `54607.xlsx`, `54764-2.xlsx`, `54764.xlsx`, `55406_Conditional_formatting_sample.xlsx`, and `55640.xlsx`. The first dochan-only pass reported XLSX success 0.8 because `54764.xlsx` and `54764-2.xlsx` contain DTD entity-amplification payloads in OOXML XML parts. The OOXML package reader now strips DTD declarations and neutralizes custom named entity references without expanding them, preserving normal XML predefined entities. Re-running dochan-only conversion on the same 29 valid files reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs. The two XML-bomb XLSX fixtures now convert to non-empty Markdown containing `Test  Spreadsheet` rather than an expanded entity payload.

Isolated MarkItDown on the 29-valid-file nineteenth probe produced no format-level or file-level candidates before the dochan XML-bomb fix:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 6.84x | +0.000 | n/a | none |
| pptx | 12.07x | +0.000 | n/a | none |
| xlsx | 14.81x | +0.000 | n/a | none |

Isolated Docling on the same nineteenth probe produced no retained candidates after current file-level filtering. Docling also failed on the XML-bomb XLSX fixtures. The isolated comparison below was captured before the dochan XML-bomb fix; after the fix, dochan-only XLSX success on the same corpus is 1.0, while the saved isolated competitor runs remain MarkItDown 0.8 and Docling 0.7:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 11.55x | +0.000 | n/a | none |
| pptx | 18.44x | +0.000 | n/a | none |
| xlsx | 21.32x | +0.100 before fix | n/a | none |

Additional Apache POI twentieth probe, run on 2026-06-21, continued from the nineteenth probe's fixture-index position and selected 30 more Apache POI files. Seven DOCX clusterfuzz files were invalid ZIP inputs and were excluded from conversion: `clusterfuzz-testcase-minimized-POIFuzzer-6709287337197568.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-4791943399604224.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-4959857092198400.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-4961551840247808.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-5166796835258368.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-5313273089884160.docx`, and `clusterfuzz-testcase-minimized-POIXWPFFuzzer-5564805011079168.docx`. The remaining 23 valid files were `capitalized.docx`, `chartex.docx`, `checkboxes.docx`, `missing-blip-fill.pptx`, `sample.pptx`, `sample_pptx_grouping_issues.pptx`, `scatter-chart.pptx`, `shapes.pptx`, `smartart-rotated-text.pptx`, `smartart-simple.pptx`, `table-with-different-font-colors.pptx`, `table-with-no-theme.pptx`, `table-with-theme.pptx`, `55745.xlsx`, `55814.xlsx`, `55850.xlsx`, `55864.xlsx`, `55906-MultiSheetRefs.xlsx`, `55923.xlsx`, `55924.xlsx`, `55926.xlsx`, `55927.xlsx`, and `56011.xlsx`. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 23-valid-file twentieth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 7.42x | +0.000 | n/a | none |
| pptx | 10.88x | +0.000 | n/a | none |
| xlsx | 16.14x | +0.000 | n/a | none |

Isolated Docling rerun on the 23-valid-file twentieth probe produced no candidates. Docling failed on three PPTX files while dochan produced non-empty output:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 51.90x | +0.000 | n/a | none |
| pptx | 14.24x | +0.300 | n/a | none |
| xlsx | 24.46x | +0.000 | n/a | none |

Additional Apache POI twenty-first probe, run on 2026-06-21, continued with 27 downloaded files. Six DOCX clusterfuzz/crash files were invalid ZIP or bad-member inputs and were excluded: `clusterfuzz-testcase-minimized-POIXWPFFuzzer-5569740188549120.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-6061520554164224.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-6120975439364096.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-6442791109263360.docx`, `clusterfuzz-testcase-minimized-POIXWPFFuzzer-6733884933668864.docx`, and `crash-517626e815e0afa9decd0ebb6d1dee63fb9907dd.docx`. The remaining 21 valid files were `comment.docx`, `deep-table-cell.docx`, `delins.docx`, `documentProperties.docx`, `table_test.pptx`, `table_test2.pptx`, `templatePPTWithOnlyOneText.pptx`, `testPPT.pptx`, `themes.pptx`, `tika-2605.pptx`, `with_japanese.pptx`, `56017.xlsx`, `56169.xlsx`, `56170.xlsx`, `56274.xlsx`, `56278.xlsx`, `56295.xlsx`, `56315.xlsx`, `56420.xlsx`, `56502.xlsx`, and `56511.xlsx`. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

The twenty-first probe exposed a real XLSX miss on `56278.xlsx`: its worksheet XML omits `r` cell references and row numbers, relying on row/cell order. Dochan had treated every unreferenced cell as column A and every unnumbered row as row 1, so each row collapsed to the final visible value. MarkItDown and Docling both showed 164 Markdown table rows while dochan showed only 10. The XLSX reader now uses row order as a fallback row index and cell order as a fallback column index, while preserving the existing fast path that skips referenced empty cells before column parsing. After the fix, dochan renders the same file with 164 Markdown table rows, preserves rows such as `Description | Rate`, `Prime | 0.032500`, `10 Year Treasury | 0.026480`, and `20 Years | 0.043600 | 0.041700`, and the file-level candidate disappears against both MarkItDown and Docling.

Isolated MarkItDown comparison on the 21-valid-file twenty-first probe, captured before the implicit-cell fix:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 6.29x | +0.500 | n/a | none |
| pptx | 8.75x | +0.000 | n/a | none |
| xlsx | 19.04x | +0.000 | n/a | `56278.xlsx` before fix |

Isolated Docling comparison on the same twenty-first probe, also captured before the implicit-cell fix:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 4.87x | +0.500 | n/a | none |
| pptx | 14.56x | +0.143 | n/a | none |
| xlsx | 27.75x | +0.100 | n/a | `56278.xlsx` before fix |

Additional Apache POI twenty-second probe, run on 2026-06-21, continued from the twenty-first probe's fixture-index position. The current Apache POI PPTX fixture index was exhausted, so this probe covered DOCX and XLSX only. It downloaded 20 valid files with no invalid ZIP inputs: `documentProtection_comments_no_password.docx`, `documentProtection_forms_no_password.docx`, `documentProtection_no_protection.docx`, `documentProtection_no_protection_tag_existing.docx`, `documentProtection_readonly_no_password.docx`, `documentProtection_trackedChanges_no_password.docx`, `drawing.docx`, `emptyPPr.docx`, `endnotes.docx`, `footnotes.docx`, `56514.xlsx`, `56557.xlsx`, `56574.xlsx`, `56644.xlsx`, `56688_1.xlsx`, `56688_2.xlsx`, `56688_3.xlsx`, `56688_4.xlsx`, `56702.xlsx`, and `56730.xlsx`. Dochan-only conversion reported success 1.0 for both DOCX and XLSX, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 20-valid-file twenty-second probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 15.24x | +0.000 | n/a | none |
| xlsx | 16.87x | +0.000 | n/a | none |

Isolated Docling rerun on the same twenty-second probe produced no candidates. Docling's XLSX success rate trailed dochan by 0.2 on this probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 16.79x | +0.000 | n/a | none |
| xlsx | 25.28x | +0.200 | n/a | none |

Additional Apache POI twenty-third probe, run on 2026-06-21, continued DOCX and XLSX after the twenty-second probe. It downloaded 20 valid files with no invalid ZIP inputs: `form_footnotes.docx`, `headerFooter.docx`, `headerPic.docx`, `heading123.docx`, `issue_51265_1.docx`, `issue_51265_2.docx`, `issue_51265_3.docx`, `protected_sample.docx`, `sample.docx`, `saut_page.docx`, `56737.xlsx`, `56822-Countifs.xlsx`, `56957.xlsx`, `57171_57163_57165.xlsx`, `57176.xlsx`, `57196.xlsx`, `57236.xlsx`, `57362.xlsx`, `57423.xlsx`, and `57482-OnlyNumeric.xlsx`. Dochan-only conversion reported success 1.0 for both DOCX and XLSX, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 20-valid-file twenty-third probe produced no format-level or file-level candidates. MarkItDown's DOCX success rate trailed dochan by 0.2:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 10.84x | +0.200 | n/a | none |
| xlsx | 17.93x | +0.000 | n/a | none |

Isolated Docling rerun on the same twenty-third probe also produced no candidates. Docling's DOCX success rate trailed dochan by 0.2:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 26.46x | +0.200 | n/a | none |
| xlsx | 22.28x | +0.000 | n/a | none |

Additional Apache POI twenty-fourth probe, run on 2026-06-21, continued DOCX and XLSX after the twenty-third probe. It downloaded 20 files and excluded one invalid non-ZIP DOCX, `truncated62886.docx`. The remaining 19 valid files were `shapes-with-text.docx`, `smarttag-snippet.docx`, `table-alignment.docx`, `table-indent.docx`, `table_footnotes.docx`, `testComment.docx`, `tika-3388.docx`, `tika-3816.docx`, `unicode-path.docx`, `57523.xlsx`, `57535.xlsx`, `57798.xlsx`, `57826.xlsx`, `57828.xlsx`, `57838.xlsx`, `57890.xlsx`, `57893-many-merges.xlsx`, `57914.xlsx`, and `58106.xlsx`. Dochan-only conversion reported success 1.0 for both DOCX and XLSX, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 19-valid-file twenty-fourth probe produced no format-level or file-level candidates. MarkItDown's XLSX success rate trailed dochan by 0.1:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 12.59x | +0.000 | n/a | none |
| xlsx | 15.66x | +0.100 | n/a | none |

Isolated Docling rerun on the same twenty-fourth probe also produced no candidates. Docling's XLSX success rate trailed dochan by 0.2:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 12.34x | +0.000 | n/a | none |
| xlsx | 17.00x | +0.200 | n/a | none |

Additional Apache POI twenty-fifth probe, run on 2026-06-21, used a docs-derived seed manifest and continued DOCX/XLSX coverage. It downloaded 18 valid files with no invalid ZIP inputs: `Bug54849.docx`, `Bug55142.docx`, `Bug60337.docx`, `Bug60341.docx`, `Bug62859.docx`, `Bug64561.docx`, `Bug66988.docx`, `ComplexNumberedLists.docx`, `48703.xlsx`, `48923.xlsx`, `48962.xlsx`, `49156.xlsx`, `49273.xlsx`, `49325.xlsx`, `49783.xlsx`, `49872.xlsx`, `58315.xlsx`, and `58325_db.xlsx`. Dochan-only conversion reported success 1.0 for both DOCX and XLSX, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 18-valid-file twenty-fifth probe produced no format-level or file-level candidates. MarkItDown's DOCX success rate trailed dochan by 0.25:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 13.61x | +0.250 | n/a | none |
| xlsx | 14.77x | +0.000 | n/a | none |

Isolated Docling rerun on the same twenty-fifth probe also produced no candidates. Docling's DOCX success rate trailed dochan by 0.25:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 15.67x | +0.250 | n/a | none |
| xlsx | 21.23x | +0.000 | n/a | none |

Additional Apache POI twenty-sixth probe, run on 2026-06-21, continued after the docs-derived seed manifest. No more DOCX fixtures were selected by the current index/manifest combination, so this pass covered XLSX only. It downloaded 10 XLSX files and excluded one invalid non-ZIP input, `58616.xlsx`. The remaining 9 valid files were `58325_lt.xlsx`, `58648.xlsx`, `58731.xlsx`, `58747.xlsx`, `58760.xlsx`, `58896.xlsx`, `59021.xlsx`, `59026.xlsx`, and `59106.xlsx`. Dochan-only conversion reported XLSX success 1.0, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 9-valid-file twenty-sixth probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| xlsx | 12.07x | +0.000 | n/a | none |

Isolated Docling rerun on the same twenty-sixth probe also produced no candidates. Docling's XLSX success rate trailed dochan by 0.111:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| xlsx | 16.55x | +0.111 | n/a | none |

Additional Apache POI twenty-seventh probe, run on 2026-06-21, reconstructed a docs-derived seed manifest from the documented probe file names, then continued the current Apache POI index. The reconstructed state marked all 127 DOCX fixtures, 85 of 93 PPTX fixtures, and 142 of 350 XLSX fixtures as already used, leaving 8 PPTX and 208 XLSX entries. The probe downloaded 18 valid files with no invalid ZIP inputs: `WithMaster.pptx`, `ae.ac.uaeu.faculty_nafaachbili_GeomLec1.pptx`, `alterman_security.pptx`, `aptia.pptx`, `at.ecodesign.www_downloads_Vertiefungsvortrag_elektronik.pptx`, `au.asn.aes.www_conferences_2011_presentations_Fri_20Room4Level4_20930_20Maloney.pptx`, `backgrounds.pptx`, `bar-chart.pptx`, `59132.xlsx`, `59264.xlsx`, `59388.xlsx`, `59687.xlsx`, `59736.xlsx`, `59746_NoRowNums.xlsx`, `59775.xlsx`, `60255_extra_drawingparts.xlsx`, `60289.xlsx`, and `60384.xlsx`. Dochan-only conversion reported success 1.0 for PPTX and XLSX, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 18-valid-file twenty-seventh probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| pptx | 3.61x | +0.000 | n/a | none |
| xlsx | 16.63x | +0.000 | n/a | none |

The first isolated Docling run with a 30-second per-file timeout exited with `SIGSEGV`. Individual Docling conversions for all 18 files succeeded, and a no-timeout Docling rerun over the same corpus produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| pptx | 13.20x | +0.000 | n/a | none |
| xlsx | 21.69x | +0.000 | n/a | none |

Additional Apache POI twenty-eighth probe, run on 2026-06-21, regenerated the docs-derived seed manifest after the twenty-seventh probe. The current Apache POI index then had all DOCX and PPTX fixtures documented as used, with 198 XLSX fixtures remaining. The probe downloaded 10 valid XLSX files with no invalid ZIP inputs: `60509.xlsx`, `60709.xlsx`, `60825.xlsx`, `61034.xlsx`, `61060-conditional-number-formatting.xlsx`, `61063.xlsx`, `61281.xlsx`, `61605.xlsx`, `61652.xlsx`, and `61869.xlsx`. Dochan-only conversion reported XLSX success 1.0, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown and Docling reruns on the 10-valid-file twenty-eighth probe produced no format-level or file-level candidates:

| Competitor | Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | xlsx | 15.93x | +0.000 | n/a | none |
| Docling | xlsx | 22.42x | +0.200 | n/a | none |

Additional Apache POI twenty-ninth probe, run on 2026-06-21, regenerated the docs-derived seed manifest after the twenty-eighth probe. The current Apache POI index then had 188 XLSX fixtures remaining. The probe downloaded 10 valid XLSX files with no invalid ZIP inputs: `62272.xlsx`, `62629_toMerge.xlsx`, `62834.xlsx`, `63934.xlsx`, `64450.xlsx`, `64508.xlsx`, `64667.xlsx`, `64750.xlsx`, `64759.xlsx`, and `65016.xlsx`. Dochan-only conversion reported XLSX success 1.0, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown and Docling reruns on the 10-valid-file twenty-ninth probe produced no format-level or file-level candidates:

| Competitor | Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | xlsx | 9.79x | +0.000 | n/a | none |
| Docling | xlsx | 16.27x | +0.100 | n/a | none |

Additional GitHub OOXML fixture index, built on 2026-06-21, expanded beyond Apache POI with 115 permissively licensed fixtures: 45 DOCX from `python-openxml/python-docx`, 66 PPTX from `scanny/python-pptx`, and 4 XLSX from `pyexcel/pyexcel` plus `ChrisPappalardo/eparse`. The first generic fixture probe downloaded 24 valid files: 10 DOCX, 10 PPTX, and all 4 XLSX files. Dochan-only conversion reported success 1.0 in all three formats, with no errors, no unexpected empty outputs, and one semantic-empty DOCX input (`doc-no-coreprops.docx`). That fixture has no core properties and no body text, only an automatic `_GoBack` bookmark and section settings, and is covered by a regression test so it does not look like an unexpected empty conversion.

Isolated MarkItDown rerun on the 24-valid-file first GitHub OOXML probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 16.38x | +0.000 | n/a | none |
| pptx | 7.94x | +0.000 | n/a | none |
| xlsx | 3.14x | +0.250 | n/a | none |

Isolated Docling rerun on the same first GitHub OOXML probe also produced no candidates. Docling failed to produce non-empty output for all 10 selected python-pptx chart fixtures and for one XLSX fixture:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 15.78x | +0.000 | n/a | none |
| pptx | 9.48x | +1.000 | n/a | none |
| xlsx | 4.82x | +0.250 | n/a | none |

The second generic GitHub OOXML probe reused the same manifest and downloaded the next 20 valid files: 10 DOCX from `python-docx` and 10 PPTX from `python-pptx`; the four XLSX fixtures had already been exhausted by the first pass. Dochan-only conversion again reported success 1.0 for both formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 20-valid-file second GitHub OOXML probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 13.55x | +0.000 | n/a | none |
| pptx | 8.28x | +0.000 | n/a | none |

Isolated Docling rerun on the same second GitHub OOXML probe also produced no candidates. Docling's PPTX success rate trailed dochan by 0.6:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.11x | +0.000 | n/a | none |
| pptx | 10.94x | +0.600 | n/a | none |

The third generic GitHub OOXML probe seeded the first two passes by fixture-index order and downloaded the next 20 valid files: 10 DOCX from `python-docx` and 10 PPTX from `python-pptx`; the XLSX pool was already exhausted. Dochan-only conversion again reported success 1.0 for both formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 20-valid-file third GitHub OOXML probe produced no format-level or file-level candidates. MarkItDown's PPTX success rate trailed dochan by 0.4:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 20.08x | +0.000 | n/a | none |
| pptx | 20.40x | +0.400 | n/a | none |

Isolated Docling rerun on the same third GitHub OOXML probe also produced no candidates. Docling's PPTX success rate trailed dochan by 0.7:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.36x | +0.000 | n/a | none |
| pptx | 27.30x | +0.700 | n/a | none |

The fourth generic GitHub OOXML probe seeded the first three passes by fixture-index order and downloaded the next 20 valid files: 10 DOCX from `python-docx` table/text fixtures and 10 PPTX from `python-pptx` presentation/shape fixtures; the XLSX pool remained exhausted. Dochan-only conversion again reported success 1.0 for both formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 20-valid-file fourth GitHub OOXML probe produced no format-level or file-level candidates. MarkItDown's PPTX success rate trailed dochan by 0.1:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 13.28x | +0.000 | n/a | none |
| pptx | 14.32x | +0.100 | n/a | none |

Isolated Docling rerun on the same fourth GitHub OOXML probe also produced no candidates. Docling's DOCX success rate trailed dochan by 0.1 and PPTX success rate trailed by 0.6:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.71x | +0.100 | n/a | none |
| pptx | 18.26x | +0.600 | n/a | none |

The fifth generic GitHub OOXML probe downloaded the next 15 valid files: the final 5 DOCX fixtures from `python-docx` and 10 more PPTX fixtures from `python-pptx`; the XLSX pool remained exhausted. Dochan-only conversion again reported success 1.0 for both formats, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 15-valid-file fifth GitHub OOXML probe produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 12.13x | +0.000 | n/a | none |
| pptx | 10.33x | +0.000 | n/a | none |

Isolated Docling rerun on the same fifth GitHub OOXML probe also produced no candidates. Docling's PPTX success rate trailed dochan by 0.3:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 13.83x | +0.000 | n/a | none |
| pptx | 19.66x | +0.300 | n/a | none |

The sixth generic GitHub OOXML probe downloaded 10 additional PPTX fixtures from `python-pptx`; DOCX and XLSX were already exhausted. Dochan-only conversion reported PPTX success 1.0, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown and Docling reruns on the 10-valid-file sixth GitHub OOXML probe produced no format-level or file-level candidates:

| Competitor | Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | pptx | 9.74x | +0.000 | n/a | none |
| Docling | pptx | 18.79x | +0.000 | n/a | none |

The seventh generic GitHub OOXML probe downloaded the final 6 PPTX fixtures from `python-pptx`, completing the 115-file permissive GitHub fixture index. The final manifest recorded all 45 DOCX, 66 PPTX, and 4 XLSX fixture ids as used. Dochan-only conversion reported PPTX success 1.0, with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown and Docling reruns on the 6-valid-file seventh GitHub OOXML probe produced no format-level or file-level candidates:

| Competitor | Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | pptx | 12.85x | +0.167 | n/a | none |
| Docling | pptx | 31.17x | +0.333 | n/a | none |

Additional 2026-06-21 Apache Tika first probe: the new Apache Tika fixture index discovered 116 Apache-2.0 OOXML test documents, 56 DOCX, 27 PPTX, and 33 XLSX. The first manifest-selected probe downloaded 30 fixtures and kept 28 valid ZIP packages after excluding `protect.xlsx` and `protectedFile.xlsx` as non-ZIP XLSX inputs. The initial pass exposed a real DOCX native gap: `testAltChunkHTML.docx` and `testAltChunkMHT.docx` store visible content in `w:altChunk` imported HTML/MHTML parts rather than in `word/document.xml` text nodes. dochan now resolves `aFChunk` relationships, extracts HTML/MHTML paragraphs, table rows, and image alt text, and the semantic-empty detector now counts DOCX altChunk imports as meaningful input.

Post-fix isolated rerun on the 28-valid-file Apache Tika first probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 13.75x | +0.300 | none |
| MarkItDown | pptx | 12.82x | +0.000 | none |
| MarkItDown | xlsx | 13.20x | +0.125 | none |
| Docling | docx | 14.93x | +0.300 | none |
| Docling | pptx | 17.55x | +0.100 | none |
| Docling | xlsx | 15.90x | +0.250 | none |

Additional 2026-06-21 Apache Tika second probe: the manifest-selected next 30 Apache Tika OOXML files, 10 each for DOCX/PPTX/XLSX, downloaded as valid ZIP packages with no invalid inputs. Dochan-only conversion initially reported DOCX/PPTX success 1.0 but XLSX success 0.9 because `testEXCEL_embeddedPDF_windows.xlsx` contains no cell values and stores its visible embedded PDF preview through worksheet `legacyDrawing` VML, `v:imagedata`, and an `oleObject` relationship. dochan now follows XLSX VML drawing relationships, emits the preview image reference, and records both the EMF preview and OLE object as structured assets.

Post-fix isolated rerun on the 30-valid-file Apache Tika second probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 24.96x | +0.000 | none |
| MarkItDown | pptx | 10.51x | +0.000 | none |
| MarkItDown | xlsx | 14.13x | +0.000 | none |
| Docling | docx | 27.06x | +0.200 | none |
| Docling | pptx | 10.13x | +0.300 | none |
| Docling | xlsx | 9.38x | +0.200 | none |

Additional 2026-06-21 Apache Tika third probe: the next manifest-selected Apache Tika OOXML batch downloaded 27 files. Three password-protected/non-ZIP fixtures, `testPPT_protected_passtika.pptx`, `testEXCEL_protected_passtika.xlsx`, and `testEXCEL_protected_passtika_2.xlsx`, were excluded before conversion. Dochan-only conversion on the remaining 24 valid files, 10 DOCX, 6 PPTX, and 8 XLSX, reported success 1.0 in every covered format with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown and Docling both produced no format-level or file-level improvement candidates, so no parser change was needed in this pass.

Isolated comparisons on the 24-valid-file Apache Tika third probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 19.87x | +0.100 | none |
| MarkItDown | pptx | 7.18x | +0.000 | none |
| MarkItDown | xlsx | 17.41x | +0.000 | none |
| Docling | docx | 16.14x | +0.100 | none |
| Docling | pptx | 10.53x | +0.167 | none |
| Docling | xlsx | 18.81x | +0.375 | none |

Additional 2026-06-21 Apache Tika fourth probe: the next manifest-selected batch contained 13 valid files, 10 DOCX and 3 XLSX, with the PPTX pool exhausted for this selection. The initial dochan-only pass found two real native gaps. `testWORD_missing_ooxml_bean1.docx` stores visible text only inside tracked-move revision containers (`w:moveFrom`/`w:moveTo`) rather than direct paragraph runs; dochan now descends into those containers while still ignoring deleted `w:del` text. `testRecordSizeExceeded.xlsx` has a 328 MB worksheet XML part with 200,000 inline-string rows, which correctly tripped the package part-size guard but left a meaningful spreadsheet empty; dochan now uses a bounded streaming worksheet preview for oversized sheet parts instead of loading the whole XML tree.

Post-fix dochan-only rerun on the 13-valid-file Apache Tika fourth probe reported success 1.0 for DOCX and XLSX, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. The benchmark harness also gained a per-conversion `--timeout` option so slow or unstable competitor conversions can be recorded as timeout failures instead of blocking the improvement loop indefinitely.

Post-fix isolated comparisons on the Apache Tika fourth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 12.55x | +0.100 | none after endnote-table fix |
| MarkItDown | xlsx | 21.78x | +0.333 | none |
| Docling | docx | 9.04x | +0.100 | none |
| Docling | xlsx | 6.64x | +0.333 | none |

The remaining MarkItDown file-level candidate, `testWORD_endnote_table.docx`, was a real parser gap: the endnote contains a `w:tbl` block after its first paragraph, and dochan previously read only direct note paragraphs. dochan now preserves tables inside footnotes/endnotes/comments in Markdown and structured JSON; a one-file isolated MarkItDown rerun reports no format-level or file-level candidates for that fixture. Format-level `improvement_candidates` are empty after the fix.

Additional 2026-06-21 Apache Tika fifth probe: after reconstructing the Apache Tika manifest state through the fourth probe, the next DOCX-only pass downloaded the next 10 Tika DOCX fixtures. One protected/non-ZIP input, `testWORD_protected_passtika.docx`, was excluded before conversion. Dochan-only conversion on the remaining 9 valid DOCX files reported success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates.

Isolated comparisons on the 9-valid-file Apache Tika fifth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 6.50x | +0.111 | none |
| Docling | docx | 11.25x | +0.222 | none |

Additional 2026-06-21 Apache Tika sixth probe: the final manifest-selected Tika DOCX pass exhausted the remaining Apache Tika OOXML index entries after PPTX and XLSX had already been exhausted in earlier passes. It downloaded the final 6 DOCX fixtures; `testWORD_truncated.docx` was excluded as a non-ZIP/truncated package, leaving 5 valid DOCX files: `testWORD_totalTimeOutOfRange.docx`, `testWORD_various.docx`, `testWPSAttachment.docx`, `test_recursive_embedded.docx`, and `test_recursive_embedded_npe.docx`. Dochan-only conversion reported success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level improvement candidates, so no parser change was needed in this pass.

Isolated comparisons on the 5-valid-file Apache Tika sixth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 10.25x | +0.000 | none |
| Docling | docx | 3.27x | +1.000 | none |

Additional 2026-06-21 Apache POI 30th probe: after reconstructing the Apache POI manifest through the 29th probe, the next XLSX-only batch selected `66365.xlsx`, `70005-countifs.xlsx`, `AmpersandHeader.xlsx`, `BrNotClosed.xlsx`, `CVLKRA-KYC_Download_File_Structure_V3.1.xlsx`, `ConditionalFormattingSamples.xlsx`, `CustomXMLMapping-singleattributenamespace.xlsx`, `CustomXMLMappings-complex-type.xlsx`, `CustomXMLMappings.xlsx`, and `CustomXmlMappings-inverse-order.xlsx`. The initial run exposed a real dochan robustness gap: `BrNotClosed.xlsx` stores a VML button textbox with HTML-like `<br>` tags that are not closed as XML elements, causing strict XML parsing of `xl/drawings/vmlDrawing1.vml` to raise `XMLSyntaxError`. dochan now parses XLSX VML drawing parts with recovery mode while keeping ordinary OOXML parts strict, so malformed legacy VML markup no longer fails the whole workbook. A focused verification on `BrNotClosed.xlsx` now reads all three sheets and emits metadata instead of an empty failed output.

Initial isolated comparisons on the Apache POI 30th probe before the VML recovery fix:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 15.71x | -0.100 | `BrNotClosed.xlsx` |
| Docling | xlsx | 24.55x | +0.000 | `BrNotClosed.xlsx` |

Additional Apache POI next-XLSX probe: the following manifest-selected batch downloaded `DataTableCities.xlsx`, `DataValidationEvaluations.xlsx`, `DataValidationListTooLong.xlsx`, `DataValidations-49244.xlsx`, `DateFormatNumberTests.xlsx`, `DateFormatTests.xlsx`, `ElapsedFormatTests.xlsx`, `ExcelPivotTableSample.xlsx`, `ExcelTables.xlsx`, and `Excel_file_with_trash_item.xlsx`. dochan-only conversion reported success 1.0 with zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates.

Isolated comparisons on the Apache POI next-XLSX probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 6.04x | +0.000 | none |
| Docling | xlsx | 9.08x | +0.100 | none |

Additional Apache POI 31st probe: after marking all DOCX/PPTX fixtures and the first 192 XLSX fixtures as used, the next XLSX-only batch selected `FormatChoiceTests.xlsx`, `FormatConditionTests.xlsx`, `FormatKM.xlsx`, `Formatting.xlsx`, `FormulaEvalTestData_Copy.xlsx`, `FormulaSheetRange.xlsx`, `GeneralFormatTests.xlsx`, `GroupTest.xlsx`, `HeaderFooterComplexFormats.xlsx`, and `HsGetVal.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates.

Isolated comparisons on the Apache POI 31st probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 11.82x | +0.000 | none |
| Docling | xlsx | 12.47x | +0.100 | none |

Additional Apache POI 32nd probe: after marking all DOCX/PPTX fixtures and the first 202 XLSX fixtures as used, the next XLSX-only batch selected `InlineString.xlsx`, `InlineStrings.xlsx`, `Intersection-52111-xssf.xlsx`, `LIBRE_OFFICE-128382-0.xlsx`, `MalformedSSTCount.xlsx`, `MatrixFormulaEvalTestData.xlsx`, `NewStyleConditionalFormattings.xlsx`, `NewlineInFormulas.xlsx`, `NumberFormatApproxTests.xlsx`, and `NumberFormatTests.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown produced no format-level or file-level candidates. The first isolated Docling run exited with `SIGSEGV`; a Docling-only rerun with a 120-second per-file timeout completed and also produced no candidates. Both MarkItDown and Docling produced empty output for `LIBRE_OFFICE-128382-0.xlsx`, while dochan converted the batch successfully.

Isolated comparisons on the Apache POI 32nd probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 2.24x | +0.100 | none |
| Docling | xlsx | 3.71x | +0.100 | none after 120s rerun |

Additional Apache POI 33rd probe: after marking all DOCX/PPTX fixtures and the first 212 XLSX fixtures as used, the next XLSX-only batch selected `RepeatingRowsCols.xlsx`, `SampleSS.strict.xlsx`, `SampleSS.xlsx`, `SheetTabColors.xlsx`, `ShrinkToFit.xlsx`, `SimpleMultiCell.xlsx`, `SimpleNormal.xlsx`, `SimpleScatterChart.xlsx`, `SimpleStrict.xlsx`, and `SimpleWithComments.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. MarkItDown produced empty output for the two Strict XLSX files, `SampleSS.strict.xlsx` and `SimpleStrict.xlsx`; Docling produced empty output for those plus `RepeatingRowsCols.xlsx` and `SheetTabColors.xlsx`.

Isolated comparisons on the Apache POI 33rd probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 11.89x | +0.200 | none |
| Docling | xlsx | 21.95x | +0.400 | none |

Additional Apache POI 34th probe: after marking all DOCX/PPTX fixtures and the first 222 XLSX fixtures as used, the next XLSX-only batch selected `SingleCellTable.xlsx`, `StructuredReferences.xlsx`, `StructuredRefs-lots-with-lookups.xlsx`, `Tables.xlsx`, `TablesWithDifferentHeaders.xlsx`, `TestShiftRowSharedFormula.xlsx`, `TextFormatTests.xlsx`, `Themes.xlsx`, `Themes2.xlsx`, and `TwoSheetsNoneHidden.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates, and neither competitor produced empty outputs in this batch.

Isolated comparisons on the Apache POI 34th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 13.48x | +0.000 | none |
| Docling | xlsx | 14.50x | +0.000 | none |

Additional Apache POI 35th probe: after marking all DOCX/PPTX fixtures and the first 232 XLSX fixtures as used, the next XLSX-only batch selected `TwoSheetsOneHidden.xlsx`, `VLookupFullColumn.xlsx`, `ValueFunctionOfBlank.xlsx`, `WidthsAndHeights.xlsx`, `WithChart.xlsx`, `WithChartSheet.xlsx`, `WithConditionalFormatting.xlsx`, `WithDrawing.xlsx`, `WithEmbeded.xlsx`, and `WithMoreVariousData.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown produced no format-level or file-level candidates. The initial isolated Docling process exited with `SIGSEGV`; a Docling-only rerun with a 120-second per-file timeout completed, emitted openpyxl warnings for unsupported WMF image dropping and ignored header/footer parsing, and still produced no format-level or file-level candidates.

Isolated comparisons on the Apache POI 35th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 8.44x | +0.000 | none |
| Docling | xlsx | 17.62x | +0.000 | none after 120s rerun |

Additional Apache POI 36th probe: after marking all DOCX/PPTX fixtures and the first 242 XLSX fixtures as used, the next XLSX-only batch selected `WithTable.xlsx`, `WithTextBox.xlsx`, `WithTextBox2.xlsx`, `WithThreeCharts.xlsx`, `WithTwoCharts.xlsx`, `WithVariousData.xlsx`, `XSSFSheet.copyRows.xlsx`, `absolute-anchor-over-empty-sheet.xlsx`, `atp.xlsx`, and `bug54803.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. Docling timed out after 30 seconds on `WithTable.xlsx` and `WithTextBox.xlsx`, produced empty output for `WithTextBox2.xlsx`, and had a 0.7 success rate in this batch. Dochan extracted visible textbox text from `WithTextBox.xlsx` and `WithTextBox2.xlsx`, extracted chart titles/series from `WithThreeCharts.xlsx` and `WithTwoCharts.xlsx`, and preserved defined names in `absolute-anchor-over-empty-sheet.xlsx`.

Isolated comparisons on the Apache POI 36th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 8.99x | +0.000 | none |
| Docling | xlsx | 15.88x | +0.300 | none |

Additional Apache POI 37th probe: after marking all DOCX/PPTX fixtures and the first 252 XLSX fixtures as used, the next XLSX-only batch selected `bug60848_sumproduct_unary_minus.xlsx`, `bug60858.xlsx`, `bug62181.xlsx`, `bug63189.xlsx`, `bug64512_embed.xlsx`, `bug65306.xlsx`, `bug65464.xlsx`, `bug66215.xlsx`, `bug66675.xlsx`, and `bug66827.xlsx`. ZIP validation passed for all 10 files. Dochan-only conversion reported XLSX success 1.0, zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. Docling timed out after 30 seconds on `bug60848_sumproduct_unary_minus.xlsx` and `bug60858.xlsx`, produced empty output for `bug64512_embed.xlsx`, and had a 0.7 success rate in this batch. Dochan preserved defined names and formulas in `bug60848_sumproduct_unary_minus.xlsx`, emitted embedded EMF image references from `bug64512_embed.xlsx`, and preserved the large sheet plus comments in `bug66827.xlsx`.

Isolated comparisons on the Apache POI 37th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 13.39x | +0.000 | none |
| Docling | xlsx | 83.87x | +0.300 | none |

Additional Apache POI 38th probe: after marking all DOCX/PPTX fixtures and the first 262 XLSX fixtures as used, the next XLSX-only batch selected `bug67784.xlsx`, `bug69769.xlsx`, `bug69812.xlsx`, `chartTitle_noTitle.xlsx`, `chartTitle_withTitle.xlsx`, `chartTitle_withTitleFormula.xlsx`, `chart_sheet.xlsx`, `clone_sheet.xlsx`, `clusterfuzz-testcase-minimized-POIFuzzer-5040805309710336.xlsx`, and `clusterfuzz-testcase-minimized-POIXSSFFuzzer-4828727001088000.xlsx`. ZIP validation rejected the two clusterfuzz files before benchmarking: `clusterfuzz-testcase-minimized-POIFuzzer-5040805309710336.xlsx` had a bad `_rels/.rels` member and `clusterfuzz-testcase-minimized-POIXSSFFuzzer-4828727001088000.xlsx` had a bad central-directory magic number. Dochan converted the 8 valid files with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. Dochan preserved chart titles from literal and formula-backed title fixtures, emitted the `Chart1` chart-sheet heading, and retained clone-sheet formulas plus chart tables.

Isolated comparisons on the Apache POI 38th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 11.63x | +0.000 | none |
| Docling | xlsx | 20.85x | +0.000 | none |

Additional Apache POI 39th probe: after marking all DOCX/PPTX fixtures and the first 272 XLSX fixtures as used, the next XLSX-only batch selected 10 clusterfuzz-minimized XLSX files: `clusterfuzz-testcase-minimized-POIXSSFFuzzer-5089447305609216.xlsx`, `clusterfuzz-testcase-minimized-POIXSSFFuzzer-5185049589579776.xlsx`, `clusterfuzz-testcase-minimized-POIXSSFFuzzer-5265527465181184.xlsx`, `clusterfuzz-testcase-minimized-POIXSSFFuzzer-5937385319563264.xlsx`, `clusterfuzz-testcase-minimized-POIXSSFFuzzer-6123461607817216.xlsx`, `clusterfuzz-testcase-minimized-POIXSSFFuzzer-6419366255919104.xlsx`, `clusterfuzz-testcase-minimized-POIXSSFFuzzer-6448258963341312.xlsx`, `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5025401116950528.xlsx`, `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5542865479270400.xlsx`, and `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5636439151607808.xlsx`. ZIP validation rejected all 10 before benchmarking (`File is not a zip file`, bad central-directory magic, or bad ZIP members such as `_rels/.rels` and `xl/worksheets/sheet8.xml`). No dochan or competitor conversion was run for this batch.

Additional Apache POI 40th probe: after marking all DOCX/PPTX fixtures and the first 282 XLSX fixtures as used, the next XLSX-only batch selected `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6504225896792064.xlsx`, `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6594557414080512.xlsx`, `commentTest.xlsx`, `comments.xlsx`, `conditional_formatting_cell_is.xlsx`, `conditional_formatting_multiple_ranges.xlsx`, `conditional_formatting_with_formula_on_second_sheet.xlsx`, `craftonhills.edu_programreview_report.aspx_goalpriorityreport_0011d159-1eeb-4b63-8833-867b0926e5f3.xlsx`, `crash-274d6342e4842d61be0fb48eaadad6208ae767ae.xlsx`, and `crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx`. ZIP validation rejected the two clusterfuzz files plus the two crash files before benchmarking. Dochan converted the 6 valid files with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown produced no format-level or file-level candidates. The initial isolated Docling process exited with `SIGSEGV`; a Docling-only rerun with a 120-second per-file timeout completed and produced no candidates. Dochan preserved cell comments in `commentTest.xlsx` and `comments.xlsx`, defined names plus hidden-sheet content in `conditional_formatting_cell_is.xlsx`, conditional-formatting rule range text in `conditional_formatting_multiple_ranges.xlsx`, and second-sheet visible content in `conditional_formatting_with_formula_on_second_sheet.xlsx`.

Isolated comparisons on the Apache POI 40th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 17.75x | +0.000 | none |
| Docling | xlsx | 18.89x | +0.000 | none after 120s rerun |

This rerun also verified an isolated-runner correctness fix: competitor venvs are created outside the benchmark corpus, so dependency package fixtures cannot inflate `file_count`. Both MarkItDown and Docling runs reported `file_count: 50`. The fixture-probe runner now retries a failed isolated competitor benchmark command once by default, so transient competitor process failures such as Docling `SIGSEGV` do not require a manual rerun. The Apache POI `EmbeddedDocument.docx` fixture verifies DOCX embedded OLE/package asset tracking and VML object preview image extraction: dochan records `word/embeddings/Microsoft_Office_Excel_97-2003_Worksheet1.xls` and `word/media/image1.emf` in `Document.assets`, emits `![image](word/media/image1.emf)`, and `expected_assets` plus `expected_markdown` scoring count them toward accuracy. The Apache POI `deep-table-cell.docx` fixture reproduced dochan's excessive XML-depth failure before the parser fallback/depth cap fix and now converts in about 0.003s; Docling's Word backend fails on that same file with an excessive-depth XML error. The Apache POI `checkboxes.docx` fixture verifies legacy Word form checkbox fields as `[ ]` and `[x]` markers in paragraphs, tables, and sequences. The Apache POI `shapes-with-text.docx` fixture exposed a dochan-specific DOCX gap where `mc:AlternateContent` Choice and Fallback text boxes were both read and anchored shape text boxes were concatenated without boundaries; dochan now prefers Choice over Fallback and emits anchored shape text as separated block text. The Apache POI `45545_Comment.pptx` fixture exposed ignored PPTX slide comment parts; dochan now follows slide `comments` relationships, resolves author names from `ppt/commentAuthors.xml`, and emits `[comment: author: text]` paragraphs. The Apache POI XLSX header/footer fixtures exposed worksheet metadata that was previously ignored; dochan now emits sheet headers and footers as Markdown comments, decodes escaped `&&` as visible ampersands, and strips quoted font, color, and other formatting control codes while preserving visible text. The public semantic corpus is still fixture-oriented rather than broad real-world coverage, but every public smoke fixture now has accuracy evidence in addition to success/speed/profile coverage. The next harness layer reports file-level candidates with output paths and now filters table-row-only deltas unless the competitor also exposes more unique text tokens at both file and format level. It also ignores spreadsheet placeholder tokens such as `NaN` and `Unnamed: n`, so layout-fragmentation and pandas blank-cell output cases do not stay in the candidate queue without semantic evidence. Empty or placeholder-only Markdown table rows are also ignored for profile row-count deltas, while explicit `expected_table_rows` and `expected_assets` scoring still preserve semantic fixtures. This removes the prior layout-fragmentation candidates, including `eparse-unit.xlsx`, after manual output review showed Docling splitting content into many smaller tables rather than proving a dochan semantic miss. It also removes the placeholder-only MarkItDown candidates on `apache-poi-sample.xlsx`, the table-only focused generated `sample.xlsx` candidate, the broader Apache POI `Booleans.xlsx` probe fixture, and the former embedded-DOCX image-reference candidate. True misses found by the loop include the missing PPTX chart series header `Category | Sales` in `python-pptx-shp-shapes.pptx`, missing title/chart heading structure in PPTX outputs, ignored PPTX slide comments, ignored XLSX worksheet drawing parts, ignored XLSX chart relationship parts, ignored XLSX header/footer metadata, the excessive-depth DOCX table case, missing legacy DOCX form checkbox markers, duplicated DOCX AlternateContent shape text, and missing DOCX VML object preview images. Native chart parsing now preserves series names, PPTX/XLSX core properties become Markdown metadata, PPTX title placeholders become Markdown headings, chart titles become level-3 headings, PPTX slide comments become `[comment: author: text]` paragraphs, XLSX drawing text boxes become paragraphs, XLSX drawing images become Markdown image references, XLSX chart titles plus cached category/value series become headings and Markdown tables, XLSX sheet headers/footers become Markdown comments, excessive-depth DOCX XML falls back to bounded recovery parsing, legacy DOCX form checkbox fields render as `[ ]` and `[x]`, DOCX text boxes inside `mc:AlternateContent` no longer double-count fallback content, DOCX embedded OLE/package relationships become structured assets, and DOCX VML object preview images become Markdown image references plus assets. The heading profiler now ignores empty and generic wrapper headings such as `#`, `## Sheet`, `## Sheet1`, `## Hoja1`, `### Chart`, `### Chart:`, and `### Notes:`, so broad-corpus candidate queues are driven by meaningful structure rather than converter boilerplate. Re-scoring the latest Python 3.14 isolated 50-file outputs reports no format-level or file-level candidates for MarkItDown or Docling.

Isolated MarkItDown comparison:

```bash
TMPVENV=$(mktemp -d /tmp/dochan-markitdown-venv.XXXXXX)
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv "$TMPVENV"
"$TMPVENV/bin/python" -m pip install --upgrade pip
"$TMPVENV/bin/python" -m pip install -e . 'markitdown[docx,pptx,xlsx]'
TMPDIR=$(mktemp -d /tmp/dochan-ooxml-bench.XXXXXX)
"$TMPVENV/bin/python" scripts/generate_ooxml_benchmark_corpus.py "$TMPDIR"
"$TMPVENV/bin/python" scripts/benchmark_competitors.py "$TMPDIR" --formats docx,pptx,xlsx --converters dochan,markitdown --runs 3
rm -rf "$TMPDIR" "$TMPVENV"
```

Focused corpus result from `competitive_summary`:

| Format | Competitor | dochan median | Competitor median | Speedup | dochan accuracy | Competitor accuracy | Accuracy delta | Success delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docx | MarkItDown | 0.0027s | 0.0195s | 7.18x | 1.000 | 0.435 | +0.565 | 0.000 |
| pptx | MarkItDown | 0.0010s | 0.0081s | 7.83x | 1.000 | 0.000 | +1.000 | +1.000 |
| xlsx | MarkItDown | 0.0019s | 0.0129s | 6.93x | 1.000 | 0.259 | +0.741 | 0.000 |
 
Interpretation:

- On this focused generated corpus, dochan is both faster and more accurate than MarkItDown for all three OOXML formats.
- The latest isolated MarkItDown rerun also verified the new index path: `format_summary` survives into `index.json`, the Markdown index summary includes a dochan JSON Profile section, and competitive rows show JSON asset/run-provenance deltas of `+1/+59` for DOCX, `+1/+38` for PPTX, and `+1/+53` for XLSX.
- MarkItDown missed headers/footers, comment range annotations, comment replies, visible bookmark anchors, drawing alt text, DOCX image references, heading Markdown structure, DOCX character-style and direct underline/strike/superscript/subscript formatting, PPTX bold/italic/underline/strike formatting, PPTX grouped-shape child-coordinate ordering, expected external/internal link target format, non-decimal and parent-aware multilevel DOCX numbering, skipped leading DOCX table cells, nested DOCX table text, PPTX/XLSX multi-series chart structure, XLSX workbook defined names, formula metadata, shared formula range translation, comments, range/internal hyperlinks, sparse row structure, currency/thousands/accounting/zero-padded/literal/fraction/scientific formatted values, and merged/formatted/link/rich-string cell coverage.
- This does not prove broad superiority. It proves the current focused edge cases are now covered by dochan and are weak spots for MarkItDown under the same generated inputs.
- The next proof step is to run the same harness on a broader real-world OOXML corpus.

Isolated Docling comparison:

```bash
TMPVENV=$(mktemp -d /tmp/dochan-docling-venv.XXXXXX)
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv "$TMPVENV"
"$TMPVENV/bin/python" -m pip install --upgrade pip
"$TMPVENV/bin/python" -m pip install -e . docling
TMPDIR=$(mktemp -d /tmp/dochan-ooxml-docling-bench.XXXXXX)
"$TMPVENV/bin/python" scripts/generate_ooxml_benchmark_corpus.py "$TMPDIR"
"$TMPVENV/bin/python" scripts/benchmark_competitors.py "$TMPDIR" --formats docx,pptx,xlsx --converters dochan,docling --runs 3
rm -rf "$TMPDIR" "$TMPVENV"
```

Focused corpus result from `competitive_summary`:

| Format | Competitor | dochan median | Competitor median | Speedup | dochan accuracy | Competitor accuracy | Accuracy delta | Success delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docx | Docling | 0.0018s | 0.0261s | 14.85x | 1.000 | 0.174 | +0.826 | 0.000 |
| pptx | Docling | 0.0011s | 0.0115s | 10.94x | 1.000 | 0.000 | +1.000 | +1.000 |
| xlsx | Docling | 0.0013s | 0.0160s | 12.49x | 1.000 | 0.259 | +0.741 | 0.000 |

Interpretation:

- On this focused generated corpus, dochan is faster and more accurate than Docling for DOCX/PPTX/XLSX.
- The latest isolated Docling rerun also verified the new index path: `format_summary` survives into `index.json`, the Markdown index summary includes a dochan JSON Profile section, and competitive rows show JSON asset/run-provenance deltas of `+1/+59` for DOCX, `+1/+38` for PPTX, and `+1/+53` for XLSX.
- The DOCX median includes dochan and Docling cold-start effects. Best seconds better represent warmed conversion cost for this tiny corpus.
- Docling's DOCX output preserved some expected text but missed heading Markdown structure and most expected table cell coverage under this scorer.
- Docling's PPTX conversion still failed on the generated PPTX after the fixture was corrected to include an `image/png` content type and a minimal valid PNG image part.

## Next Loop Candidates

Priority order:

1. Run larger MarkItDown and Docling comparisons with repeated timing on a broader real-world OOXML corpus.
2. Improve benchmark scoring to classify table structure separately from raw text presence.
3. Expand the public OOXML corpus:
   - simple document
   - headings and broader numbering variants
   - heading style inheritance
   - internal and external hyperlinks
   - tables with merged cells
   - nested tables
   - PPTX title/body/table/slide-number/notes/grouped shapes/reading order/slide headings/embedded image references
   - XLSX booleans, formulas, shared formulas, rich strings, dates, merged cells, multiple sheet headings, Strict OOXML workbooks
4. Extend benchmark metrics:
   - wall time
   - non-empty output
   - expected text coverage
   - expected table cell coverage
   - expected heading/list coverage
   - expected sheet/slide provenance coverage
   - no-manifest output profile deltas for headings, tables, links, comments, bookmarks, and formulas
5. Next parser improvements:
   - DOCX richer image asset export, richer nested table structure, more numbering variants, and remaining style coverage beyond current paragraph/direct-run/character-style formatting.
   - PPTX richer binary image asset export, more complex grouped shapes, broader chart variants, SmartArt variants, and richer table geometry.
   - XLSX broader formula function coverage, remaining custom format coverage, broader chart variants, workbook metadata, and streaming/compact Markdown paths for very large sheets.

## Current Competitive Read

dochan now improves on small native OOXML edge cases without adding dependencies and reaches `accuracy: 1.0` on the generated focused corpus. In isolated runs on that focused corpus, dochan beats both MarkItDown and Docling on speed and measured accuracy. The expanded 50-file public OOXML corpus, including Apache POI fixtures, found and verified DOCX/PPTX/XLSX core-property extraction, Unicode headers/footers, endnotes, comment range annotations, DOCX character-style run formatting, DOCX run-level underline/strike/superscript/subscript Markdown formatting, excessive-depth DOCX XML recovery with a nested-table depth cap, legacy DOCX form checkbox marker extraction, DOCX AlternateContent textbox fallback de-duplication, anchored DOCX shape text boundaries, DOCX embedded image relationship Markdown references and asset tracking, DOCX VML object preview image references, DOCX embedded OLE/package asset tracking, PPTX embedded image relationship Markdown references and asset tracking, PPTX slide comment extraction, XLSX embedded drawing image Markdown references and asset tracking, JSON asset/provenance/rich-format serialization through `Dochan.to_json()`, PPTX run-level bold/italic/underline/strike Markdown formatting, PPTX grouped-shape child-coordinate transforms, bookmarks, heading levels, skipped leading DOCX table cells, Strict XLSX namespace support, DOCX image relationship placeholders, PPTX embedded image relationship references, PPTX slide heading preservation, PPTX title placeholder headings, PPTX SmartArt diagram data text, PPTX chart title headings/data, PPTX master-slide text, PPTX/XLSX multi-series chart table rendering, XLSX sheet heading preservation including single meaningful sheet names, XLSX sheet header/footer extraction, escaped ampersand decoding, header/footer formatting control stripping, inline strings, shared hyperlinks, worksheet drawing text boxes, embedded drawing image references, XLSX chart title/series extraction, XLSX time/duration/currency/thousands/accounting/zero-padded/literal-prefix-suffix/fraction/scientific number-format rendering, XLSX blank-style-cell compaction, earlier blank-cell skipping, shared-formula single-pass capture, one-pass cell child classification, number-format metadata caching, fast empty-cell/reference skipping, metadata-only deck scoring, structured asset scoring, placeholder-token filtering, generated Shape image-placeholder filtering, meaningful-heading filtering, format-level table-only candidate filtering, and isolated-runner corpus isolation. On the latest 50-file public rerun with full semantic `expected.json`, Python 3.14 isolated comparisons produced no format-level or file-level `improvement_candidates` after re-scoring saved outputs with the meaningful-heading profiler; dochan was faster than MarkItDown and Docling in all DOCX/PPTX/XLSX format summaries, had better success rate, and scored `accuracy: 1.0` on every public fixture. This still does not prove broad superiority because the corpus remains small and fixture-oriented, so a larger real-world OOXML corpus with broader semantic expectations still needs to be run.
