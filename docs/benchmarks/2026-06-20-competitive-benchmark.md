# dochan Competitive Benchmark - 2026-06-20

## Scope

This benchmark compares dochan against current document-ingestion competitors:

- Microsoft MarkItDown
- IBM/LF AI Docling
- Unstructured
- Apache Tika

The local executable benchmark measures dochan directly. MarkItDown and Docling were also measured in temporary isolated Python 3.14 virtual environments so they do not become runtime dependencies. Competitor capability and license rows are based on current public project documentation checked on 2026-06-20.

## Local dochan Corpus Result

Corpus: `test_pairs/` HWP/HWPX files.

Command interpreter: `/Applications/Xcode.app/Contents/Developer/usr/bin/python3` because the Homebrew `python3` in this environment does not have project dependencies installed.

| Metric | Result |
| --- | ---: |
| Files tested | 157 |
| Total time | 2.1165s |
| Clean success | 157 / 157 (100.0%) |
| Non-empty output | 157 / 157 (100.0%) |
| Median time/file | 0.0071s |
| Mean time/file | 0.0135s |
| P95 time/file | 0.0398s |
| Max time/file | 0.2170s |
| Median Markdown chars | 7,232 |
| Total Markdown chars | 2,043,335 |

Breakdown:

| Format | Count | Non-empty | Clean | Median time | Median chars |
| --- | ---: | ---: | ---: | ---: | ---: |
| `.hwp` | 77 | 77 | 77 | 0.0085s | 8,192 |
| `.hwpx` | 80 | 80 | 80 | 0.0058s | 6,655 |

## Focused OOXML Competitor Result

Corpus: deterministic generated `.docx`, `.pptx`, `.xlsx` fixtures from `scripts/generate_ooxml_benchmark_corpus.py`.

Latest isolated competitive rerun: 2026-06-21, Python 3.14.6, `competitive_summary` output.

Repeat command:

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

This corpus is intentionally narrow. It covers selected edge cases dochan now handles natively: DOCX core properties, headers/footers, tabs, breaks, text inside text boxes, drawing alt text from `wp:docPr`, embedded image relationships from `a:blip r:embed` and VML `v:imagedata` as Markdown image references plus `Document.assets` entries, external and internal anchor hyperlink targets, visible bookmark anchors, style inheritance for headings, character style inheritance for run-level bold/italic/underline/strike/subscript formatting, direct run-level bold/italic/underline/strike/superscript/subscript Markdown formatting, decimal/lower-letter/upper-roman numbering, multilevel numbering with parent markers such as `1.a)`, footnotes/endnotes, comment reference extraction plus inline `commentRangeStart`/`commentRangeEnd` annotations, comment replies from `commentsExtended.xml`, tracked insertions/deletions, content-control and smart-tag wrapper text, field result text, horizontal and vertical merged tables, `w:gridBefore` skipped leading table cells, and nested table text; PPTX core properties, breaks, fields, bullet and auto-numbered paragraphs, run-level bold/italic/underline/strike Markdown formatting, run-level external hyperlink targets, shape-level external hyperlink targets, internal slide hyperlink targets, picture alt text and embedded image relationships from `p:cNvPr` plus `a:blip r:embed` as Markdown image references plus `Document.assets` entries, multi-slide Markdown headings, chart title, chart series names, multi-series chart tables, cached series data, SmartArt diagram data text from `dgm:relIds`, speaker notes, static slide-layout text, tables, grouped shapes, grouped-shape child coordinate transforms through `a:chOff`/`a:chExt`, merged table cells, and shape/table reading order by position; XLSX core properties, booleans, comments, error cells, cached formulas plus shared formula metadata translated for follower cells, shared formula whole-column and whole-row ranges, shared/inline rich text strings, external, internal, and range hyperlinks, merged cells, sparse row/column coordinates, dates, times, durations, percentages, fixed decimals, currency formats, thousands separators, negative accounting-style formats, zero-padded identifier custom formats such as `00000` and `000-0000`, literal prefix/suffix custom number formats such as `0 "kg"`, `0.0"x"`, and `"SKU-"0000`, fraction number formats such as `# ?/?` and `# ??/??`, scientific number formats such as `0.00E+00` and `0.0E+00`, multiple sheet-name headings, drawing text boxes, embedded drawing image relationships as Markdown image references plus `Document.assets` entries, chart titles, multi-series chart tables, chart series names, and cached chart category/value data. Blank merged-away expectation cells are excluded from cell-level scoring so failed converters do not receive credit for empty strings; row-level expectations are also scored for sparse table structure. The generated DOCX, PPTX, and XLSX fixtures declare `image/png` and embed a minimal valid PNG so competitor failures are not caused by malformed package metadata or invalid placeholder image bytes.

For broader real-world corpora without `expected.json`, the benchmark also records output profile metrics, `format_summary` aggregates, `competitive_summary` deltas against dochan, and sorted `improvement_candidates` for cases where dochan trails an installed competitor on accuracy, success rate, table rows, meaningful headings, links, image references, comments, bookmarks, formulas, or unique text tokens. Link profiling includes `mailto:` targets, image references are tracked separately from text tokens, image alt text may contain bracketed filename fragments such as `[1]`, spreadsheet placeholder tokens such as `NaN`, `NaT`, and `Unnamed: n` are filtered from unique-token deltas, numeric-only tokens are filtered so raw decimal spreadsheet values do not count as extra semantic text, generated empty-alt `ShapeNNN.jpg`-style image placeholders are ignored when no real package media relationship exists, and generic wrapper headings such as empty `#`, `## Sheet`, `### Chart`, and `### Notes:` are ignored. Explicit `--converters` requests are reflected in `converter_status`, so missing MarkItDown or Docling installations are visible in the JSON instead of being mistaken for a successful comparison. dochan result rows and summary rows also include structured JSON profile metrics for assets, provenance coverage, tables, nested cell paragraphs, run provenance, and rich runs; `competitive_summary` carries JSON metric deltas when competitors are present, making dochan's JSON/provenance advantage measurable even when competitors only expose Markdown.

The native JSON output now preserves package image assets as a top-level `assets` array for DOCX, PPTX, and XLSX, and DOCX also records embedded OLE/package relationships such as attached Office objects. Each asset includes relationship id, package source path, filename, content type, and format-specific metadata such as label, slide, sheet, relationship type, or source format. JSON also preserves OOXML provenance for sections, paragraphs, runs, and table cells, table row/column counts, cell row/column spans, nested cell paragraph/run structure, heading levels, and rich run flags such as underline, strikeout, superscript, and subscript. DOCX/PPTX text runs carry paragraph provenance, DOCX/PPTX table cells carry `R{row}C{column}` provenance, and XLSX cell text runs carry cell-level provenance for downstream citation and review.

The isolated runner also saves converter Markdown outputs under `outputs/<competitor>/...`; those files are the primary evidence for turning a weak `improvement_candidates` row into the next parser fixture. The benchmark now emits file-level competitive summaries and file-level improvement candidates with representative dochan/competitor output paths, so a single weak fixture is not hidden by a strong format median. Table-row-only file candidates are filtered unless the competitor also exposes more unique text tokens, which keeps table-fragmentation differences from dominating the queue. Its `index.json` includes each competitor's compact `report_summary`, including `format_summary`, so broad corpus runs can be scanned without opening every full report and without losing dochan JSON profile medians. The Markdown index summary includes a dochan JSON Profile section plus JSON asset/run-provenance deltas in the competitive table.

Apache POI broad-probe sampling is now manifestable: `build_apache_poi_fixture_index.py` builds a license-tagged Apache POI DOCX/PPTX/XLSX fixture index from GitHub, and `download_public_ooxml_corpus.py` accepts `--fixture-index`, `--probe-manifest`, `--probe-name`, and `--probe-per-format`. `run_apache_poi_probe.py` wraps the full loop: index generation, manifest-based download, ZIP validation, dochan-only smoke, isolated MarkItDown/Docling runs, output capture, and `probe.json` summary. Helper functions persist used fixture ids by format and choose unseen DOCX/PPTX/XLSX candidates deterministically. This keeps future evidence loops from relying on accidental duplicate samples after temporary corpus directories are deleted.

Generic GitHub fixture probing is now available as the Apache POI follow-up path. `build_github_ooxml_fixture_index.py` builds a license-tagged index from `python-openxml/python-docx`, `scanny/python-pptx`, `pyexcel/pyexcel`, and `ChrisPappalardo/eparse`; `run_fixture_probe.py` runs the same manifest/download/ZIP-validation/dochan-only/isolated-competitor loop against any fixture index JSON.

The Apache POI runner now treats corrupt fuzz fixtures as invalid corpus inputs rather than parser failures. Invalid ZIP files are removed before benchmark execution, retained in `probe.json` as `zip_invalid`, and valid files continue through dochan and isolated competitor runs.

### MarkItDown

Command: isolated Python 3.14 venv, `pip install -e . 'markitdown[docx,pptx,xlsx]'`, `--converters dochan,markitdown --runs 3`.

| Format | Competitor | dochan median | Competitor median | Speedup | dochan accuracy | Competitor accuracy | Accuracy delta | Success delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docx | MarkItDown | 0.0027s | 0.0195s | 7.18x | 1.000 | 0.435 | +0.565 | 0.000 |
| pptx | MarkItDown | 0.0010s | 0.0081s | 7.83x | 1.000 | 0.000 | +1.000 | +1.000 |
| xlsx | MarkItDown | 0.0019s | 0.0129s | 6.93x | 1.000 | 0.259 | +0.741 | 0.000 |

### Docling

Command: isolated Python 3.14 venv, `pip install -e . docling`, `--converters dochan,docling --runs 3`.

| Format | Competitor | dochan median | Competitor median | Speedup | dochan accuracy | Competitor accuracy | Accuracy delta | Success delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docx | Docling | 0.0018s | 0.0261s | 14.85x | 1.000 | 0.174 | +0.826 | 0.000 |
| pptx | Docling | 0.0011s | 0.0115s | 10.94x | 1.000 | 0.000 | +1.000 | +1.000 |
| xlsx | Docling | 0.0013s | 0.0160s | 12.49x | 1.000 | 0.259 | +0.741 | 0.000 |

Interpretation:

- On the focused generated OOXML corpus, dochan is faster and more accurate than MarkItDown and Docling for DOCX/PPTX/XLSX. The latest isolated MarkItDown and Docling reruns also verify that isolated `index.json` and the Markdown index summary preserve dochan JSON profile medians plus JSON asset/run-provenance deltas.
- This does not prove broad superiority. A real-world OOXML corpus is still required before claiming general-purpose parity or superiority.
- Docling remains much stronger for advanced PDF/layout/OCR workflows, which this benchmark does not test.

## Public OOXML Smoke Corpus

Corpus: `scripts/download_public_ooxml_corpus.py --formats docx,pptx,xlsx`.

The current public smoke corpus downloads permissively licensed fixtures from:

- `python-openxml/python-docx` test files under MIT.
- `bgreenwell/doxx` test fixtures under MIT.
- `scanny/python-pptx` test files under MIT.
- `pyexcel/pyexcel` test fixtures under BSD-3-Clause.
- `ChrisPappalardo/eparse` test fixtures under MIT.
- `apache/poi` test fixtures under Apache-2.0.

Latest dochan-only smoke result after expanding the public corpus to 50 files and adding full semantic expectations:

| Format | Files | Non-empty outputs | Finding |
| --- | ---: | ---: | --- |
| DOCX | 18 | 18 | Expanded coverage now includes comments, headers/footers, Unicode headers/footers, numbering, footnotes/endnotes, bookmarks, heading levels, legacy form checkboxes, anchored shape text boxes, doxx comprehensive structure, Apache POI sample documents, image-heavy documents, an excessive-depth nested-table fixture, and embedded OLE/package object relationships; DOCX core properties, image relationships, and embedded object asset metadata are preserved when present. |
| PPTX | 14 | 14 | Public fixtures cover metadata-only minimal decks, notes, slide comments, Unicode text, hyperlinks, master-slide text, shapes, pictures, chart titles/data, and tables. |
| XLSX | 18 | 18 | Expanded coverage now includes `pyexcel` Strict OOXML, `eparse` nested/unit workbooks, Apache POI Strict workbooks, inline strings, shared hyperlinks, formulas, cell comments, drawing text boxes, embedded drawing image references, picture worksheets, chart titles, cached chart series data, worksheet header/footer strings, escaped ampersands, and header/footer formatting control codes; all eighteen produce non-empty Markdown with table rows, sheet headings, drawing text, image references, chart data, or header/footer comments. |

The public corpus now writes `expected.json` for all 50 public fixtures. Expectations cover DOCX headings, bookmarks, comments, headers/footers, Unicode text, footnotes/endnotes, image references including VML object preview images, embedded OLE/package assets, core properties, nested block content, excessive-depth nested tables, legacy form checkbox markers such as `[ ]` and `[x]`, and anchored shape text boxes without `mc:AlternateContent` fallback duplication; PPTX metadata-only decks, notes, slide comments, master-slide text, Unicode text, hyperlinks, slide provenance, images, tables, and chart cached data; and XLSX sheet headings, Strict namespaces, inline strings, sparse/nested rows, formulas, hyperlinks, comments, drawing text boxes, embedded drawing images, picture worksheets, chart titles, chart cached series data, worksheet headers/footers, escaped ampersands, stripped header/footer formatting control codes, and large real-world table metadata. dochan scores accuracy 1.0 on all 50 public fixtures.

Latest public isolated competitor rerun on the 50-file corpus with semantic expectations using Python 3.14:

| Competitor | Format | Speedup | Accuracy delta | Success delta | Improvement candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | docx | 12.53x | +0.504 | +0.056 | none |
| MarkItDown | pptx | 7.92x | +0.372 | +0.071 | none |
| MarkItDown | xlsx | 17.68x | +0.789 | +0.222 | none |
| Docling | docx | 16.29x | +0.533 | +0.056 | none |
| Docling | pptx | 19.25x | +0.618 | +0.214 | none |
| Docling | xlsx | 22.62x | +0.891 | +0.389 | none |

Additional 2026-06-21 Apache POI wide probe: 41 valid previously unused Apache POI OOXML fixtures, after excluding one non-ZIP `.pptx`, found two real dochan gaps and one MarkItDown placeholder-noise candidate. dochan now reads DOCX body-level `w:sdt`/`w:sdtContent` blocks, fixing resume-template text dropped from `60316.docx`, and emits PPTX link-only external images from `a:blip r:link`, fixing `56812.pptx`. The profiler also ignores `NaT` placeholders alongside `NaN` and `Unnamed: n`.

Post-fix isolated MarkItDown rerun on the 41-file probe:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 14.11x | +0.143 | none |
| pptx | 13.67x | +0.077 | none |
| xlsx | 10.86x | +0.000 | none |

The preceding full MarkItDown/Docling rerun on the same probe, after DOCX/PPTX parser fixes but before the `NaT` profiler filter, already had no Docling file-level candidates and showed dochan ahead by 15.28x DOCX, 23.19x PPTX, and 12.21x XLSX with better success deltas in all three formats.

Additional 2026-06-21 Apache POI next probe: 36 more valid previously unused Apache POI OOXML fixtures found a real DOCX packaging edge case. `Bug60341.docx` uses a package-root absolute footer relationship target (`/word/footer.xml`) and stores the visible footer text under nested `w:sdtContent`; dochan now resolves package-root absolute internal OOXML targets for DOCX/PPTX/XLSX while keeping package part validation strict, and reads header/footer paragraphs nested inside content controls. Dochan-only rerun on the 36-file probe reports DOCX/PPTX/XLSX success rate 1.0 with zero empty outputs.

Post-fix isolated MarkItDown/Docling rerun on the 36-file probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 12.09x | +0.250 | none |
| MarkItDown | pptx | 3.85x | +0.000 | none |
| MarkItDown | xlsx | 12.28x | +0.000 | none |
| Docling | docx | 14.74x | +0.250 | none |
| Docling | pptx | 9.91x | +0.083 | none |
| Docling | xlsx | 18.32x | +0.083 | none |

The only initial MarkItDown file-level candidates in this 36-file probe were false positives: Dochan image alt text preserved Windows filenames containing `[1]`, which the profiler's older Markdown image regex under-counted. After the profiler fix, PPTX image counts match on those files and file candidates are empty.

Additional 2026-06-21 Apache POI third probe: 47 more valid previously unused Apache POI OOXML fixtures, after excluding one non-ZIP `.pptx`, found one true package compatibility issue. `49609.xlsx` stores ZIP entries with backslashes (`xl\workbook.xml`, `xl\_rels\workbook.xml.rels`, etc.); dochan now maps stored ZIP member names to normalized OOXML part names while preserving the existing unsafe-path checks. The only remaining Dochan empty output in the batch, `59378.docx`, contains no visible Word text in `word/*.xml`, so it is treated as a legitimate empty document rather than a parser miss.

Post-fix isolated MarkItDown/Docling rerun on the 47-file probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 15.12x | +0.188 | none |
| MarkItDown | pptx | 13.72x | +0.067 | none |
| MarkItDown | xlsx | 7.38x | +0.062 | none |
| Docling | docx | 14.39x | +0.125 | none |
| Docling | pptx | 18.42x | +0.400 | none |
| Docling | xlsx | 8.70x | +0.250 | none |

Additional 2026-06-21 Apache POI fourth probe: 57 valid previously unused Apache POI OOXML fixtures after excluding three corrupt/non-ZIP `.pptx` files. Dochan-only conversion reported success 1.0 for DOCX/PPTX/XLSX with no empty outputs. MarkItDown produced no file-level candidates. Docling initially exposed one real DOCX structure gap: `IllustrativeCases.docx` uses the built-in Word `Title` paragraph style for the visible document title. dochan now maps that style to H1, producing `# (V) ILLUSTRATIVE CASES`.

Post-fix isolated Docling rerun on the 57-file probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| Docling | docx | 16.15x | +0.200 | none |
| Docling | pptx | 18.81x | +0.294 | none |
| Docling | xlsx | 23.52x | +0.100 | none |

Additional 2026-06-21 Apache POI fifth probe: 60 valid previously unused Apache POI OOXML fixtures, 20 each for DOCX/PPTX/XLSX. Dochan-only conversion reported success 1.0 in all three formats with no empty outputs. MarkItDown produced no file-level candidates and dochan led by 14.73x DOCX, 8.33x PPTX, and 13.51x XLSX. Docling initially surfaced `AverageTaxRates.xlsx` as an XLSX table-row candidate, but manual output review showed a profiler false positive: dochan emitted compact wide tables with formatted percentages, while Docling split merged regions into many smaller tables and emitted raw decimal/floating-point values. The profiler now ignores numeric-only tokens in unique-token deltas, preventing raw spreadsheet number formatting from turning table fragmentation into a semantic candidate.

Post-filter isolated Docling rerun on the 60-file fifth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| Docling | docx | 12.38x | +0.050 | none |
| Docling | pptx | 10.25x | +0.100 | none |
| Docling | xlsx | 15.91x | +0.100 | none |

Additional 2026-06-21 Apache POI sixth probe: 60 valid previously unused Apache POI OOXML fixtures, 20 each for DOCX/PPTX/XLSX. Dochan-only conversion reported success 1.0 in all three formats with no empty outputs. Initial MarkItDown candidates split into one profiler false positive and one native output improvement. `missing-blip-fill.pptx` has an empty `p:blipFill` with no media relationship, while MarkItDown generated `![](Shape662.jpg)` for a non-existent package image; the profiler now ignores generated empty-alt `ShapeNNN` image placeholders. `craftonhills.edu_programreview_report.aspx_goalpriorityreport_0011d159-1eeb-4b63-8833-867b0926e5f3.xlsx` has a single meaningful sheet named `Report`; dochan now emits `## Report` while still suppressing generic default `Sheet*` names.

Post-fix isolated MarkItDown rerun on the 60-file sixth probe:

| Format | Speedup | Success delta | File candidates |
| --- | ---: | ---: | --- |
| docx | 12.39x | +0.300 | none |
| pptx | 11.97x | +0.000 | none |
| xlsx | 15.13x | +0.000 | none |

The initial isolated Docling run on the same sixth probe already had no file-level candidates and showed dochan ahead by 16.03x DOCX, 19.09x PPTX, and 21.16x XLSX, with success deltas of +0.300, +0.300, and +0.050.

Additional 2026-06-21 Apache POI seventh probe: 60 valid previously unused Apache POI OOXML fixtures, 20 each for DOCX/PPTX/XLSX. Dochan-only conversion reported success 1.0 in all three formats with no empty outputs. MarkItDown and Docling both produced no format-level or file-level improvement candidates, so no parser change was needed in this pass.

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

Additional 2026-06-21 Apache POI eighth probe: 60 valid previously unused Apache POI OOXML fixtures, 20 each for DOCX/PPTX/XLSX. The selector excluded several fuzz PPTX files whose ZIP signature was present but central directory or CRC validation failed, then marked `48779.xlsx` as `expected_empty` after manual inspection showed three default sheets with no values. Dochan-only conversion reported success 1.0 in all three formats with no unexpected empty outputs. MarkItDown and Docling both produced no format-level or file-level improvement candidates.

Isolated MarkItDown rerun on the 60-file eighth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 13.15x | +0.100 | n/a | none |
| pptx | 12.76x | +0.000 | n/a | none |
| xlsx | 19.70x | +0.050 | +1.000 | none |

Isolated Docling rerun on the 60-file eighth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.85x | +0.100 | n/a | none |
| pptx | 23.72x | +0.100 | n/a | none |
| xlsx | 31.66x | +0.000 | +0.000 | none |

Additional 2026-06-21 Apache POI ninth probe: 54 valid remaining previously unused Apache POI OOXML fixtures, 20 DOCX, 14 PPTX, and 20 XLSX. The remaining unused PPTX pool only had 14 valid files after ZIP central-directory and CRC validation; corrupt fuzz/crash samples were skipped. `Tika-792.docx` and `52425.xlsx` were marked `expected_empty` after manual inspection showed no visible final DOCX text and no XLSX cell values. Dochan-only conversion reported success 1.0 in all three formats with no unexpected empty outputs. MarkItDown and Docling both produced no format-level or file-level improvement candidates.

Isolated MarkItDown rerun on the 54-file ninth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.54x | +0.000 | +0.000 | none |
| pptx | 11.67x | +0.000 | n/a | none |
| xlsx | 15.65x | +0.050 | +1.000 | none |

Isolated Docling rerun on the 54-file ninth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 18.48x | +0.000 | +0.000 | none |
| pptx | 21.20x | +0.214 | n/a | none |
| xlsx | 19.66x | +0.100 | +0.000 | none |

Additional 2026-06-21 Apache POI tenth probe: 60 valid Apache POI OOXML fixtures, 20 DOCX, 20 PPTX, and 20 XLSX. The Dochan-only pass initially found `zero-length.docx` as an unexpected empty output. Manual OOXML inspection showed the file has no body text but does have a header image relationship, so dochan now resolves header/footer part relationships and emits the header image as Markdown plus `Document.assets`. The first isolated MarkItDown pass then found a real DOCX table gap in `tika-3816.docx`: a table row and one table cell were nested under `w:sdt/w:sdtContent`; dochan now expands those wrappers inside DOCX tables. Post-fix Dochan-only conversion reported success 1.0 in all three formats with no unexpected empty outputs, and MarkItDown/Docling both produced no format-level or file-level improvement candidates.

Post-fix isolated MarkItDown rerun on the 60-file tenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.36x | +0.150 | n/a | none |
| pptx | 11.10x | +0.000 | n/a | none |
| xlsx | 24.31x | +0.000 | n/a | none |

Post-fix isolated Docling rerun on the 60-file tenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 15.71x | +0.150 | n/a | none |
| pptx | 20.25x | +0.150 | n/a | none |
| xlsx | 33.85x | +0.100 | n/a | none |

Additional 2026-06-21 Apache POI eleventh probe: 60 more valid Apache POI OOXML fixtures, 20 DOCX, 20 PPTX, and 20 XLSX. One corrupt PPTX (`Divino_Revelado.pptx`) was excluded by ZIP validation. Dochan-only conversion reported success 1.0 in all three formats with no unexpected empty outputs. MarkItDown and Docling both produced no format-level or file-level improvement candidates, so no parser change was needed in this pass.

Isolated MarkItDown rerun on the 60-file eleventh probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.23x | +0.200 | n/a | none |
| pptx | 10.48x | +0.050 | n/a | none |
| xlsx | 10.44x | +0.000 | n/a | none |

Isolated Docling rerun on the 60-file eleventh probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 16.29x | +0.150 | n/a | none |
| pptx | 17.77x | +0.300 | n/a | none |
| xlsx | 16.43x | +0.150 | n/a | none |

Additional 2026-06-21 Apache POI twelfth probe: 30 fixture-index/manifest-selected Apache POI OOXML files, 10 DOCX, 10 PPTX, and 10 XLSX. ZIP validation passed for all files. Two initial dochan empty outputs were manually inspected and found semantically empty: `59378.docx` has empty Word paragraphs and no visible text/media payload, and `48779.xlsx` has only generic empty `Sheet1`/`Sheet2`/`Sheet3` worksheets. The benchmark now records `input_semantic_empty` for no-manifest corpora so competitor boilerplate such as generic empty sheet headings does not become a false improvement candidate.

Rescored isolated MarkItDown rerun on the 30-file twelfth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.15x | +0.200 | n/a | none |
| pptx | 3.76x | +0.000 | n/a | none |
| xlsx | 13.46x | +0.100 | n/a | none |

Rescored isolated Docling rerun on the 30-file twelfth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.26x | +0.200 | n/a | none |
| pptx | 15.78x | +0.000 | n/a | none |
| xlsx | 22.30x | +0.100 | n/a | none |

Additional 2026-06-21 Apache POI thirteenth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files, 10 DOCX, 10 PPTX, and 10 XLSX. ZIP validation passed for all files. Dochan-only conversion reported success 1.0 in all three formats with no errors and no empty outputs.

Isolated MarkItDown rerun on the 30-file thirteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 10.54x | +0.400 | n/a | none |
| pptx | 12.57x | +0.000 | n/a | none |
| xlsx | 16.24x | +0.000 | n/a | none |

Isolated Docling rerun on the 30-file thirteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 16.32x | +0.400 | n/a | none |
| pptx | 22.70x | +0.200 | n/a | none |
| xlsx | 25.85x | +0.000 | n/a | none |

Additional 2026-06-21 Apache POI fourteenth probe: 15 more fixture-index/manifest-selected Apache POI OOXML files, 5 DOCX, 5 PPTX, and 5 XLSX. ZIP validation passed for all files. Dochan-only conversion reported success 1.0 in all three formats with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown rerun on the 15-file fourteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 9.34x | +0.000 | n/a | none |
| pptx | 19.09x | +0.000 | n/a | none |
| xlsx | 14.50x | +0.000 | n/a | none |

Isolated Docling rerun on the 15-file fourteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 4.69x | +0.000 | n/a | none |
| pptx | 20.80x | +0.200 | n/a | none |
| xlsx | 14.34x | +0.200 | n/a | none |

Additional 2026-06-21 Apache POI fifteenth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files, 10 DOCX, 10 PPTX, and 10 XLSX. ZIP validation passed for all files. Dochan-only conversion reported success 1.0 in all three formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown failed `2411-Performance_Up.pptx` with a `PptxConverter` `InvalidXmlError` for a missing required `p:blipFill` child. Docling produced empty outputs for `51187.pptx`, `60042.pptx`, `61515.pptx`, `63200.pptx`, and `45430.xlsx`; dochan produced non-empty outputs for all five.

Isolated MarkItDown rerun on the 30-file fifteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.32x | +0.000 | n/a | none |
| pptx | 12.45x | +0.100 | n/a | none |
| xlsx | 11.51x | +0.000 | n/a | none |

Isolated Docling rerun on the 30-file fifteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 17.57x | +0.000 | n/a | none |
| pptx | 23.86x | +0.400 | n/a | none |
| xlsx | 10.26x | +0.100 | n/a | none |

Additional 2026-06-21 Apache POI sixteenth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files, 10 DOCX, 10 PPTX, and 10 XLSX. ZIP validation passed for all files. Dochan-only conversion reported success 1.0 in all three formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown failed `60329.docx` with a `DocxConverter` `KeyError` for `w:type` and produced empty outputs for `61470.docx` and `61745.docx`; dochan produced non-empty outputs for all three. Docling produced empty outputs for `61470.docx`, `61745.docx`, `EmbeddedVideo.pptx`, and `SmartArt.pptx`; dochan produced non-empty outputs for all four. Docling also produced empty outputs for `47090.xlsx` and `47504.xlsx`, both classified as semantic-empty inputs.

Isolated MarkItDown rerun on the 30-file sixteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 11.86x | +0.300 | n/a | none |
| pptx | 10.11x | +0.000 | n/a | none |
| xlsx | 18.82x | +0.000 | n/a | none |

Isolated Docling rerun on the 30-file sixteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 12.18x | +0.200 | n/a | none |
| pptx | 15.37x | +0.200 | n/a | none |
| xlsx | 24.83x | +0.000 | n/a | none |

Additional 2026-06-21 Apache POI seventeenth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files were downloaded. Seven PPTX clusterfuzz fixtures were invalid ZIP files and were excluded from conversion while remaining listed under `zip_invalid`: `clusterfuzz-testcase-minimized-POIFuzzer-5205835528404992.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-4838644450394112.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-4986044400861184.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-5463285576892416.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-5471515212382208.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-5611274456596480.pptx`, and `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6071540680032256.pptx`. Dochan-only conversion on the remaining 23 valid files reported success 1.0 in all three formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. Docling produced empty outputs for the three valid PPTX chart-background fixtures, `chart-picture-bg.pptx`, `chart-slide-bg.pptx`, and `chart-texture-bg.pptx`; dochan produced non-empty outputs for all three.

Isolated MarkItDown rerun on the 23-valid-file seventeenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 9.74x | +0.000 | n/a | none |
| pptx | 11.18x | +0.000 | n/a | none |
| xlsx | 9.56x | +0.000 | n/a | none |

Isolated Docling rerun on the 23-valid-file seventeenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 18.79x | +0.000 | n/a | none |
| pptx | 17.53x | +1.000 | n/a | none |
| xlsx | 14.87x | +0.000 | n/a | none |

Additional 2026-06-21 Apache POI eighteenth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files were downloaded. Five files were invalid ZIP inputs and were excluded from conversion while remaining listed under `zip_invalid`: `bug53475-password-is-pass.docx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6254434927378432.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6372932378820608.pptx`, `clusterfuzz-testcase-minimized-POIXSLFFuzzer-6435650376957952.pptx`, and `crash-57308ca363f5b71763c489d1b432aff009d4bc4f.pptx`. Dochan-only conversion on the remaining 25 valid files reported success 1.0 in all three formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown and Docling also produced no error or empty outputs on the 25 valid files, but neither produced a format-level or file-level improvement candidate over dochan.

Isolated MarkItDown rerun on the 25-valid-file eighteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 14.35x | +0.000 | n/a | none |
| pptx | 4.18x | +0.000 | n/a | none |
| xlsx | 15.78x | +0.000 | n/a | none |

Isolated Docling rerun on the 25-valid-file eighteenth probe:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 22.84x | +0.000 | n/a | none |
| pptx | 9.25x | +0.000 | n/a | none |
| xlsx | 22.36x | +0.000 | n/a | none |

Additional 2026-06-21 Apache POI nineteenth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files were downloaded. One password-protected/non-ZIP DOCX file was excluded from conversion while remaining listed under `zip_invalid`: `bug53475-password-is-solrcell.docx`. The first dochan-only pass on the remaining 29 valid files exposed two XLSX XML-bomb failures, `54764.xlsx` and `54764-2.xlsx`, caused by DTD entity-amplification payloads in OOXML XML parts. The OOXML package reader now strips DTD declarations and neutralizes custom named entity references without expanding them. Re-running dochan-only conversion on the same 29 valid files reported success 1.0 in DOCX, PPTX, and XLSX with no errors, no unexpected empty outputs, and no semantic-empty inputs.

Isolated MarkItDown comparison on the 29-valid-file nineteenth probe, captured before the dochan XML-bomb fix, produced no format-level or file-level candidates:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 6.84x | +0.000 | n/a | none |
| pptx | 12.07x | +0.000 | n/a | none |
| xlsx | 14.81x | +0.000 | n/a | none |

Isolated Docling comparison on the same nineteenth probe, also captured before the dochan XML-bomb fix, produced no retained candidates after current filtering. Saved isolated XLSX success rates were dochan 0.8, MarkItDown 0.8, and Docling 0.7; after the fix, dochan-only XLSX success on that same corpus is 1.0:

| Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | ---: | ---: | ---: | --- |
| docx | 11.55x | +0.000 | n/a | none |
| pptx | 18.44x | +0.000 | n/a | none |
| xlsx | 21.32x | +0.100 before fix | n/a | none |

Additional 2026-06-21 Apache POI twentieth probe: 30 more fixture-index/manifest-selected Apache POI OOXML files were downloaded. Seven DOCX clusterfuzz files were invalid ZIP inputs and were excluded from conversion. Dochan-only conversion on the remaining 23 valid files reported success 1.0 in DOCX, PPTX, and XLSX with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with speedups of 7.42x for DOCX, 10.88x for PPTX, and 16.14x for XLSX. Docling produced no candidates, with speedups of 51.90x for DOCX, 14.24x for PPTX, and 24.46x for XLSX; Docling's PPTX success rate trailed dochan by 0.3 on this probe.

Additional 2026-06-21 Apache POI twenty-first probe: 27 more fixture-index/manifest-selected Apache POI OOXML files were downloaded. Six DOCX clusterfuzz/crash files were invalid ZIP or bad-member inputs and were excluded. Dochan-only conversion on the remaining 21 valid files reported success 1.0 in all three formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. This probe exposed a real XLSX gap on `56278.xlsx`: worksheet rows and cells lacked explicit `r` references, so dochan collapsed each unnumbered row/cell sequence to a single final value while MarkItDown and Docling kept 164 table rows. The native XLSX reader now uses row order and cell order as fallback coordinates when explicit references are absent. After the fix, dochan renders 164 Markdown table rows for `56278.xlsx`, preserves rows including `Description | Rate`, `Prime | 0.032500`, and `20 Years | 0.043600 | 0.041700`, and the file-level candidate disappears against both MarkItDown and Docling.

Isolated comparisons on the twenty-first probe, captured before the implicit-cell fix:

| Competitor | Format | Speedup | Success delta | Accuracy delta | File candidates |
| --- | --- | ---: | ---: | ---: | --- |
| MarkItDown | docx | 6.29x | +0.500 | n/a | none |
| MarkItDown | pptx | 8.75x | +0.000 | n/a | none |
| MarkItDown | xlsx | 19.04x | +0.000 | n/a | `56278.xlsx` before fix |
| Docling | docx | 4.87x | +0.500 | n/a | none |
| Docling | pptx | 14.56x | +0.143 | n/a | none |
| Docling | xlsx | 27.75x | +0.100 | n/a | `56278.xlsx` before fix |

Additional 2026-06-21 Apache POI twenty-second probe: the current Apache POI PPTX fixture index was exhausted, so the probe covered DOCX and XLSX only. It downloaded 20 valid files with no invalid ZIP inputs. Dochan-only conversion reported success 1.0 for both DOCX and XLSX with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with speedups of 15.24x for DOCX and 16.87x for XLSX. Docling produced no candidates, with speedups of 16.79x for DOCX and 25.28x for XLSX; Docling's XLSX success rate trailed dochan by 0.2.

Additional 2026-06-21 Apache POI twenty-third probe: 20 more DOCX/XLSX files were downloaded with no invalid ZIP inputs. Dochan-only conversion reported success 1.0 for both formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with speedups of 10.84x for DOCX and 17.93x for XLSX; MarkItDown's DOCX success rate trailed dochan by 0.2. Docling also produced no candidates, with speedups of 26.46x for DOCX and 22.28x for XLSX; Docling's DOCX success rate trailed dochan by 0.2.

Additional 2026-06-21 Apache POI twenty-fourth probe: 20 more DOCX/XLSX files were downloaded. One non-ZIP DOCX, `truncated62886.docx`, was excluded before conversion. Dochan-only conversion on the remaining 19 valid files reported success 1.0 for both formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with speedups of 12.59x for DOCX and 15.66x for XLSX; MarkItDown's XLSX success rate trailed dochan by 0.1. Docling also produced no candidates, with speedups of 12.34x for DOCX and 17.00x for XLSX; Docling's XLSX success rate trailed dochan by 0.2.

Additional 2026-06-21 Apache POI twenty-fifth probe: a docs-derived seed manifest selected 18 valid DOCX/XLSX files with no invalid ZIP inputs. Dochan-only conversion reported success 1.0 for both formats with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with speedups of 13.61x for DOCX and 14.77x for XLSX; MarkItDown's DOCX success rate trailed dochan by 0.25. Docling also produced no candidates, with speedups of 15.67x for DOCX and 21.23x for XLSX; Docling's DOCX success rate trailed dochan by 0.25.

Additional 2026-06-21 Apache POI twenty-sixth probe: the current index/manifest combination selected no further DOCX fixtures and 10 XLSX fixtures. One non-ZIP XLSX, `58616.xlsx`, was excluded before conversion. Dochan-only conversion on the remaining 9 valid XLSX files reported success 1.0 with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with a 12.07x XLSX speedup and equal success. Docling also produced no candidates, with a 16.55x XLSX speedup; Docling's XLSX success rate trailed dochan by 0.111.

Additional 2026-06-21 Apache POI twenty-seventh probe: a docs-derived seed manifest was reconstructed from documented probe file names and used against the current Apache POI index. That left 8 PPTX and 208 XLSX fixtures not yet documented as used; the probe downloaded 18 valid files with no invalid ZIP inputs. Dochan-only conversion reported success 1.0 for PPTX and XLSX with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with speedups of 3.61x for PPTX and 16.63x for XLSX. The first Docling isolated run with a 30-second per-file timeout exited with `SIGSEGV`; every file succeeded when converted individually, and a no-timeout Docling rerun over the full corpus produced no candidates, with speedups of 13.20x for PPTX and 21.69x for XLSX.

Additional 2026-06-21 Apache POI twenty-eighth probe: the regenerated docs-derived seed manifest showed DOCX and PPTX exhausted in the current Apache POI index, with 198 XLSX fixtures remaining. The probe downloaded the next 10 valid XLSX files with no invalid ZIP inputs. Dochan-only conversion reported success 1.0 with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with a 15.93x XLSX speedup and equal success. Docling produced no candidates, with a 22.42x XLSX speedup; Docling's XLSX success rate trailed dochan by 0.2.

Additional 2026-06-21 Apache POI twenty-ninth probe: the regenerated docs-derived seed manifest showed 188 XLSX fixtures remaining. The probe downloaded the next 10 valid XLSX files with no invalid ZIP inputs. Dochan-only conversion reported success 1.0 with no errors, no unexpected empty outputs, and no semantic-empty inputs. MarkItDown produced no candidates, with a 9.79x XLSX speedup and equal success. Docling produced no candidates, with a 16.27x XLSX speedup; Docling's XLSX success rate trailed dochan by 0.1.

Additional 2026-06-21 GitHub OOXML fixture index: 115 permissively licensed fixtures outside Apache POI's broad index were discovered: 45 DOCX from `python-openxml/python-docx`, 66 PPTX from `scanny/python-pptx`, and 4 XLSX from `pyexcel/pyexcel` plus `ChrisPappalardo/eparse`. The first generic probe downloaded 24 valid files and dochan converted all of them successfully. One input, `doc-no-coreprops.docx`, is a semantic-empty Word package with no core properties and no body text, only an automatic `_GoBack` bookmark and section settings; it is now covered by a regression test so it does not look like an unexpected empty conversion. MarkItDown produced no candidates, with speedups of 16.38x DOCX, 7.94x PPTX, and 3.14x XLSX; MarkItDown's XLSX success rate trailed dochan by 0.25. Docling also produced no candidates, with speedups of 15.78x DOCX, 9.48x PPTX, and 4.82x XLSX; Docling's PPTX success rate trailed dochan by 1.0 and XLSX by 0.25.

Additional 2026-06-21 GitHub OOXML second probe: the same manifest selected the next 20 valid files, 10 DOCX and 10 PPTX, with the four XLSX fixtures already exhausted. Dochan-only conversion reported success 1.0 for both formats. MarkItDown produced no candidates, with speedups of 13.55x DOCX and 8.28x PPTX. Docling also produced no candidates, with speedups of 14.11x DOCX and 10.94x PPTX; Docling's PPTX success rate trailed dochan by 0.6.

Additional 2026-06-21 GitHub OOXML third probe: seeding the first two generic passes by fixture-index order selected the next 20 valid files, 10 DOCX and 10 PPTX, with the XLSX pool still exhausted. Dochan-only conversion reported success 1.0 for both formats. MarkItDown produced no candidates, with speedups of 20.08x DOCX and 20.40x PPTX; MarkItDown's PPTX success rate trailed dochan by 0.4. Docling also produced no candidates, with speedups of 17.36x DOCX and 27.30x PPTX; Docling's PPTX success rate trailed dochan by 0.7.

Additional 2026-06-21 GitHub OOXML fourth probe: seeding the first three generic passes by fixture-index order selected the next 20 valid files, 10 DOCX and 10 PPTX, with the XLSX pool still exhausted. Dochan-only conversion reported success 1.0 for both formats, with no errors or empty outputs. MarkItDown produced no candidates, with speedups of 13.28x DOCX and 14.32x PPTX; MarkItDown's PPTX success rate trailed dochan by 0.1. Docling also produced no candidates, with speedups of 17.71x DOCX and 18.26x PPTX; Docling's DOCX success rate trailed dochan by 0.1 and PPTX by 0.6.

Additional 2026-06-21 GitHub OOXML fifth through seventh probes: the remaining permissive GitHub fixture index was exhausted. The fifth probe selected 15 valid files, covering the final 5 DOCX fixtures and 10 more PPTX fixtures; the sixth selected 10 PPTX fixtures; the seventh selected the final 6 PPTX fixtures. The final manifest recorded all 45 DOCX, 66 PPTX, and 4 XLSX fixture ids as used. Dochan-only conversion reported success 1.0 throughout, with no errors or unexpected empty outputs. MarkItDown produced no candidates, with speedups of 12.13x DOCX / 10.33x PPTX on the fifth probe, 9.74x PPTX on the sixth, and 12.85x PPTX on the seventh; MarkItDown's final PPTX success rate trailed dochan by 0.167. Docling also produced no candidates, with speedups of 13.83x DOCX / 19.66x PPTX on the fifth probe, 18.79x PPTX on the sixth, and 31.17x PPTX on the seventh; Docling's PPTX success rate trailed dochan by 0.3 on the fifth and 0.333 on the seventh.

Additional 2026-06-21 Apache Tika OOXML first probe: a new Apache Tika fixture index discovered 116 Apache-2.0 Microsoft-parser test documents, 56 DOCX, 27 PPTX, and 33 XLSX. The first generic probe downloaded 30 files and kept 28 valid ZIP packages after excluding two protected/non-ZIP XLSX inputs. The pass found one real dochan gap: DOCX `w:altChunk` imports whose visible text lives in HTML or MHTML package parts. dochan now extracts HTML/MHTML altChunk paragraphs, table rows, and image alt text, and the benchmark semantic-empty detector now treats DOCX altChunk HTML text as meaningful input.

Post-fix isolated comparison on the 28-valid-file Apache Tika first probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 13.75x | +0.300 | none |
| MarkItDown | pptx | 12.82x | +0.000 | none |
| MarkItDown | xlsx | 13.20x | +0.125 | none |
| Docling | docx | 14.93x | +0.300 | none |
| Docling | pptx | 17.55x | +0.100 | none |
| Docling | xlsx | 15.90x | +0.250 | none |

Additional 2026-06-21 Apache Tika OOXML second probe: the next manifest-selected 30 files, 10 DOCX, 10 PPTX, and 10 XLSX, were all valid ZIP packages. The initial dochan-only run found one XLSX gap: `testEXCEL_embeddedPDF_windows.xlsx` has no cell values but does contain a visible embedded PDF preview through worksheet `legacyDrawing` VML plus an `oleObject` relationship. dochan now follows XLSX VML image relationships and records both the EMF preview and embedded OLE payload as structured assets, raising dochan XLSX success on this probe from 0.9 to 1.0.

Post-fix isolated comparison on the 30-valid-file Apache Tika second probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 24.96x | +0.000 | none |
| MarkItDown | pptx | 10.51x | +0.000 | none |
| MarkItDown | xlsx | 14.13x | +0.000 | none |
| Docling | docx | 27.06x | +0.200 | none |
| Docling | pptx | 10.13x | +0.300 | none |
| Docling | xlsx | 9.38x | +0.200 | none |

Additional 2026-06-21 Apache Tika OOXML third probe: the next manifest-selected batch downloaded 27 files. Three password-protected/non-ZIP inputs were excluded before conversion, leaving 24 valid files: 10 DOCX, 6 PPTX, and 8 XLSX. Dochan-only conversion reported success 1.0 for every covered format with no errors and no unexpected empty outputs. MarkItDown and Docling produced no format-level or file-level candidates.

Isolated comparison on the 24-valid-file Apache Tika third probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 19.87x | +0.100 | none |
| MarkItDown | pptx | 7.18x | +0.000 | none |
| MarkItDown | xlsx | 17.41x | +0.000 | none |
| Docling | docx | 16.14x | +0.100 | none |
| Docling | pptx | 10.53x | +0.167 | none |
| Docling | xlsx | 18.81x | +0.375 | none |

Additional 2026-06-21 Apache Tika OOXML fourth probe: the next manifest-selected batch contained 13 valid files, 10 DOCX and 3 XLSX. The initial dochan-only pass exposed two real parser robustness gaps: tracked-move DOCX text under `w:moveFrom`/`w:moveTo`, and a 328 MB XLSX worksheet part with 200,000 inline-string rows. dochan now descends into tracked-move containers while still ignoring deleted text, and uses a bounded streaming preview for oversized XLSX worksheet parts. Post-fix dochan-only conversion reported success 1.0 for DOCX and XLSX with zero errors and no unexpected empty outputs.

Post-fix isolated comparison on the Apache Tika fourth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 12.55x | +0.100 | none after endnote-table fix |
| MarkItDown | xlsx | 21.78x | +0.333 | none |
| Docling | docx | 9.04x | +0.100 | none |
| Docling | xlsx | 6.64x | +0.333 | none |

Format-level improvement candidates are empty after the fix. Manual review of the remaining MarkItDown file-level candidate, `testWORD_endnote_table.docx`, confirmed a real native parser miss: the visible endnote table lived in `word/endnotes.xml` as a `w:tbl` block, while dochan only parsed direct note paragraphs. dochan now preserves footnote/endnote/comment tables in Markdown and structured JSON, and a one-file isolated MarkItDown rerun reports no remaining candidate for that fixture. A 30-second timeout run against Docling crashed in the isolated Python 3.14 process with `SIGSEGV`, but a no-timeout Docling rerun completed successfully and produced the table above. The benchmark CLI and isolated runner now accept `--timeout` so future loops can bound per-file converter stalls.

Additional 2026-06-21 Apache Tika OOXML fifth probe: after reconstructing the manifest through the fourth Tika probe, the next DOCX-only batch selected 10 more Tika DOCX fixtures. One protected/non-ZIP input, `testWORD_protected_passtika.docx`, was excluded before conversion. Dochan-only conversion on the remaining 9 valid DOCX files reported success 1.0 with zero errors and no unexpected empty outputs. MarkItDown and Docling both produced no format-level or file-level improvement candidates.

Isolated comparison on the 9-valid-file Apache Tika fifth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 6.50x | +0.111 | none |
| Docling | docx | 11.25x | +0.222 | none |

Additional 2026-06-21 Apache Tika OOXML sixth probe: the final DOCX-only pass exhausted the remaining Apache Tika OOXML fixture index after PPTX and XLSX had already been exhausted. It downloaded the remaining 6 DOCX fixtures and excluded `testWORD_truncated.docx` as a non-ZIP/truncated package. Dochan-only conversion on the remaining 5 valid DOCX files reported success 1.0 with zero errors, zero unexpected empty outputs, and zero semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level improvement candidates.

Isolated comparison on the 5-valid-file Apache Tika sixth probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | docx | 10.25x | +0.000 | none |
| Docling | docx | 3.27x | +1.000 | none |

Additional Apache POI XLSX probe: the 30th Apache POI pass initially found a real native robustness miss in `BrNotClosed.xlsx`. Its VML drawing part contains legacy HTML-like `<br>` tags inside a button textbox, which strict XML parsing rejected with `XMLSyntaxError`; dochan now reads XLSX VML drawing parts with recovery parsing while leaving ordinary OOXML parts strict. Focused verification confirms `BrNotClosed.xlsx` now reads all three sheets instead of producing an empty failed output.

Initial isolated comparison on the Apache POI 30th probe before the fix:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 15.71x | -0.100 | `BrNotClosed.xlsx` |
| Docling | xlsx | 24.55x | +0.000 | `BrNotClosed.xlsx` |

The following Apache POI XLSX batch selected `DataTableCities.xlsx`, `DataValidationEvaluations.xlsx`, `DataValidationListTooLong.xlsx`, `DataValidations-49244.xlsx`, `DateFormatNumberTests.xlsx`, `DateFormatTests.xlsx`, `ElapsedFormatTests.xlsx`, `ExcelPivotTableSample.xlsx`, `ExcelTables.xlsx`, and `Excel_file_with_trash_item.xlsx`. dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates.

Isolated comparison on the Apache POI next-XLSX probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 6.04x | +0.000 | none |
| Docling | xlsx | 9.08x | +0.100 | none |

Additional Apache POI XLSX 31st probe: after marking all DOCX/PPTX fixtures and the first 192 XLSX fixtures as used, the next XLSX-only batch selected `FormatChoiceTests.xlsx`, `FormatConditionTests.xlsx`, `FormatKM.xlsx`, `Formatting.xlsx`, `FormulaEvalTestData_Copy.xlsx`, `FormulaSheetRange.xlsx`, `GeneralFormatTests.xlsx`, `GroupTest.xlsx`, `HeaderFooterComplexFormats.xlsx`, and `HsGetVal.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates.

Isolated comparison on the Apache POI 31st probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 11.82x | +0.000 | none |
| Docling | xlsx | 12.47x | +0.100 | none |

Additional Apache POI XLSX 32nd probe: after marking all DOCX/PPTX fixtures and the first 202 XLSX fixtures as used, the next XLSX-only batch selected `InlineString.xlsx`, `InlineStrings.xlsx`, `Intersection-52111-xssf.xlsx`, `LIBRE_OFFICE-128382-0.xlsx`, `MalformedSSTCount.xlsx`, `MatrixFormulaEvalTestData.xlsx`, `NewStyleConditionalFormattings.xlsx`, `NewlineInFormulas.xlsx`, `NumberFormatApproxTests.xlsx`, and `NumberFormatTests.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown produced no format-level or file-level candidates. The initial isolated Docling process exited with `SIGSEGV`, but a Docling-only rerun with a 120-second per-file timeout completed and also produced no candidates. Both MarkItDown and Docling produced empty output for `LIBRE_OFFICE-128382-0.xlsx`.

Isolated comparison on the Apache POI 32nd probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 2.24x | +0.100 | none |
| Docling | xlsx | 3.71x | +0.100 | none after 120s rerun |

Additional Apache POI XLSX 33rd probe: after marking all DOCX/PPTX fixtures and the first 212 XLSX fixtures as used, the next XLSX-only batch selected `RepeatingRowsCols.xlsx`, `SampleSS.strict.xlsx`, `SampleSS.xlsx`, `SheetTabColors.xlsx`, `ShrinkToFit.xlsx`, `SimpleMultiCell.xlsx`, `SimpleNormal.xlsx`, `SimpleScatterChart.xlsx`, `SimpleStrict.xlsx`, and `SimpleWithComments.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. MarkItDown produced empty output for the two Strict XLSX files; Docling produced empty output for the Strict files plus `RepeatingRowsCols.xlsx` and `SheetTabColors.xlsx`.

Isolated comparison on the Apache POI 33rd probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 11.89x | +0.200 | none |
| Docling | xlsx | 21.95x | +0.400 | none |

Additional Apache POI XLSX 34th probe: after marking all DOCX/PPTX fixtures and the first 222 XLSX fixtures as used, the next XLSX-only batch selected `SingleCellTable.xlsx`, `StructuredReferences.xlsx`, `StructuredRefs-lots-with-lookups.xlsx`, `Tables.xlsx`, `TablesWithDifferentHeaders.xlsx`, `TestShiftRowSharedFormula.xlsx`, `TextFormatTests.xlsx`, `Themes.xlsx`, `Themes2.xlsx`, and `TwoSheetsNoneHidden.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates, and neither competitor produced empty outputs.

Isolated comparison on the Apache POI 34th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 13.48x | +0.000 | none |
| Docling | xlsx | 14.50x | +0.000 | none |

Additional Apache POI XLSX 35th probe: after marking all DOCX/PPTX fixtures and the first 232 XLSX fixtures as used, the next XLSX-only batch selected `TwoSheetsOneHidden.xlsx`, `VLookupFullColumn.xlsx`, `ValueFunctionOfBlank.xlsx`, `WidthsAndHeights.xlsx`, `WithChart.xlsx`, `WithChartSheet.xlsx`, `WithConditionalFormatting.xlsx`, `WithDrawing.xlsx`, `WithEmbeded.xlsx`, and `WithMoreVariousData.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown produced no format-level or file-level candidates. The initial isolated Docling process exited with `SIGSEGV`, but a Docling-only rerun with a 120-second per-file timeout completed, emitted warnings for unsupported WMF image dropping and ignored header/footer parsing, and also produced no candidates.

Isolated comparison on the Apache POI 35th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 8.44x | +0.000 | none |
| Docling | xlsx | 17.62x | +0.000 | none after 120s rerun |

Additional Apache POI XLSX 36th probe: after marking all DOCX/PPTX fixtures and the first 242 XLSX fixtures as used, the next XLSX-only batch selected `WithTable.xlsx`, `WithTextBox.xlsx`, `WithTextBox2.xlsx`, `WithThreeCharts.xlsx`, `WithTwoCharts.xlsx`, `WithVariousData.xlsx`, `XSSFSheet.copyRows.xlsx`, `absolute-anchor-over-empty-sheet.xlsx`, `atp.xlsx`, and `bug54803.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. Docling timed out after 30 seconds on `WithTable.xlsx` and `WithTextBox.xlsx`, produced empty output for `WithTextBox2.xlsx`, and had a 0.7 success rate. Dochan preserved textbox text, chart tables/titles, formulas, and defined names across the same batch.

Isolated comparison on the Apache POI 36th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 8.99x | +0.000 | none |
| Docling | xlsx | 15.88x | +0.300 | none |

Additional Apache POI XLSX 37th probe: after marking all DOCX/PPTX fixtures and the first 252 XLSX fixtures as used, the next XLSX-only batch selected `bug60848_sumproduct_unary_minus.xlsx`, `bug60858.xlsx`, `bug62181.xlsx`, `bug63189.xlsx`, `bug64512_embed.xlsx`, `bug65306.xlsx`, `bug65464.xlsx`, `bug66215.xlsx`, `bug66675.xlsx`, and `bug66827.xlsx`. Dochan converted all 10 with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. Docling timed out after 30 seconds on `bug60848_sumproduct_unary_minus.xlsx` and `bug60858.xlsx`, produced empty output for `bug64512_embed.xlsx`, and had a 0.7 success rate. Dochan preserved defined names, formulas, embedded EMF image references, and large-sheet comments across the same batch.

Isolated comparison on the Apache POI 37th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 13.39x | +0.000 | none |
| Docling | xlsx | 83.87x | +0.300 | none |

Additional Apache POI XLSX 38th probe: after marking all DOCX/PPTX fixtures and the first 262 XLSX fixtures as used, the next XLSX-only batch selected `bug67784.xlsx`, `bug69769.xlsx`, `bug69812.xlsx`, `chartTitle_noTitle.xlsx`, `chartTitle_withTitle.xlsx`, `chartTitle_withTitleFormula.xlsx`, `chart_sheet.xlsx`, `clone_sheet.xlsx`, `clusterfuzz-testcase-minimized-POIFuzzer-5040805309710336.xlsx`, and `clusterfuzz-testcase-minimized-POIXSSFFuzzer-4828727001088000.xlsx`. ZIP validation rejected the two clusterfuzz files before benchmarking because one had a bad `_rels/.rels` member and the other had a bad central-directory magic number. Dochan converted the 8 valid files with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown and Docling both produced no format-level or file-level candidates. Dochan preserved literal/formula-backed chart titles, chart-sheet headings, clone-sheet formulas, and chart tables across the same batch.

Isolated comparison on the Apache POI 38th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 11.63x | +0.000 | none |
| Docling | xlsx | 20.85x | +0.000 | none |

Additional Apache POI XLSX 39th probe: after marking all DOCX/PPTX fixtures and the first 272 XLSX fixtures as used, the next XLSX-only batch selected 10 clusterfuzz-minimized XLSX files. ZIP validation rejected all 10 before benchmarking because they were not valid ZIP files, had bad central-directory magic, or contained bad ZIP members such as `_rels/.rels` and `xl/worksheets/sheet8.xml`. No dochan or competitor conversion was run for this batch.

Additional Apache POI XLSX 40th probe: after marking all DOCX/PPTX fixtures and the first 282 XLSX fixtures as used, the next XLSX-only batch selected `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6504225896792064.xlsx`, `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6594557414080512.xlsx`, `commentTest.xlsx`, `comments.xlsx`, `conditional_formatting_cell_is.xlsx`, `conditional_formatting_multiple_ranges.xlsx`, `conditional_formatting_with_formula_on_second_sheet.xlsx`, `craftonhills.edu_programreview_report.aspx_goalpriorityreport_0011d159-1eeb-4b63-8833-867b0926e5f3.xlsx`, `crash-274d6342e4842d61be0fb48eaadad6208ae767ae.xlsx`, and `crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx`. ZIP validation rejected the two clusterfuzz files plus the two crash files before benchmarking. Dochan converted the 6 valid files with success 1.0, zero errors, zero unexpected empty outputs, and no semantic-empty failures. MarkItDown produced no candidates. The initial isolated Docling process exited with `SIGSEGV`, but a Docling-only rerun with a 120-second per-file timeout completed and also produced no candidates. Dochan preserved comments, defined names, hidden-sheet text, conditional-formatting rule text, and second-sheet visible content across the same batch.

Isolated comparison on the Apache POI 40th probe:

| Competitor | Format | Speedup | Success delta | File candidates |
| --- | --- | ---: | ---: | --- |
| MarkItDown | xlsx | 17.75x | +0.000 | none |
| Docling | xlsx | 18.89x | +0.000 | none after 120s rerun |

The isolated runner creates temporary competitor venvs outside the benchmark corpus, preventing package fixtures inside a venv from inflating `file_count`. This run reported `file_count: 50` for both MarkItDown and Docling. The Apache POI `EmbeddedDocument.docx` fixture verifies DOCX embedded OLE/package asset recording plus VML object preview image extraction; dochan resolves `word/embeddings/Microsoft_Office_Excel_97-2003_Worksheet1.xls` and `word/media/image1.emf` into `Document.assets`, emits `![image](word/media/image1.emf)`, and `expected_assets` plus `expected_markdown` scoring count both toward accuracy. The Apache POI `deep-table-cell.docx` fixture reproduced an excessive XML-depth failure in dochan before the parser fallback/depth cap fix; after the fix dochan converts it in about 0.003s, while Docling's Word backend fails on the same file with an excessive-depth XML error. The Apache POI `checkboxes.docx` fixture verifies that legacy Word form checkbox fields are preserved as `[ ]` and `[x]` markers in paragraphs, tables, and sequences. The Apache POI `shapes-with-text.docx` fixture exposed duplicate textbox extraction from `mc:AlternateContent` Choice/Fallback branches and missing boundaries between anchored text boxes; dochan now prefers Choice over Fallback and separates anchored shape text as block text. The Apache POI `45545_Comment.pptx` fixture verifies PPTX slide comments from slide relationship parts, preserving author names and comment text as `[comment: author: text]`. The Apache POI XLSX header/footer fixtures exposed worksheet metadata that broad converters often flatten away; dochan now preserves sheet headers and footers as Markdown comments, decodes escaped ampersands, and strips formatting control codes while keeping visible text. The public semantic corpus is still fixture-oriented, but all public smoke files now have explicit accuracy evidence in addition to success rate, speed, and output profile deltas.

Latest file-level harness check: file-level candidates are emitted separately from format-level candidates and include output paths for manual review. The harness now filters table-row-only deltas unless the competitor also exposes more unique text tokens at both file and format level, ignores spreadsheet placeholder tokens such as `NaN`, `NaT`, and `Unnamed: n`, ignores numeric-only unique-token deltas, ignores generated empty-alt `ShapeNNN` image placeholders, and ignores empty or placeholder-only Markdown table rows for profile row-count deltas while keeping explicit `expected_table_rows` and `expected_assets` scoring intact. This keeps layout-fragmentation cases such as `eparse-unit.xlsx`, pandas blank-cell output in `apache-poi-sample.xlsx`, focused generated `sample.xlsx`, and placeholder-only rows in the broader Apache POI `Booleans.xlsx` probe from staying in the candidate queue. It also scores meaningful-heading, image-reference, comment, bookmark, and formula-marker deficits as candidate reasons, which makes broader real-world runs better at surfacing semantic misses before a hand-written `expected.json` exists. It caught real PPTX misses: dochan omitted chart series header `Category | Sales`, did not promote title placeholders to Markdown headings, emitted chart titles as plain paragraphs, and ignored PPTX slide comments. It also caught native XLSX gaps where worksheet drawing parts, chart relationship parts, and worksheet header/footer strings were ignored; dochan now follows sheet drawing relationships, extracts drawing text boxes, emits embedded drawing image references such as Apache POI `WithTextBox.xlsx`, `WithDrawing.xlsx`, and `picture.xlsx`, parses chart titles plus cached category/value series from `xl/charts/chartN.xml`, and emits sheet header/footer text as Markdown comments. Native chart parsing now preserves series names, PPTX/XLSX core properties become Markdown metadata, PPTX title placeholders become headings, chart titles become level-3 headings, PPTX slide comments become `[comment: author: text]` paragraphs, excessive-depth DOCX XML falls back to bounded recovery parsing, legacy DOCX form checkboxes render as `[ ]` and `[x]`, DOCX AlternateContent shape text avoids fallback duplication, DOCX embedded OLE/package relationships and VML object preview images become structured assets, and generic competitor wrapper headings such as `### Chart:`, `## Sheet1`, and `## Hoja1` are ignored during profile comparison. Re-scoring the latest Python 3.14 isolated 50-file outputs reports no format-level or file-level candidates for MarkItDown or Docling.

Latest dochan-only XLSX profile after sheet heading preservation, early blank-cell skipping, shared-formula single-pass capture, one-pass cell child classification, number-format metadata caching, and fast empty-cell/reference skipping: `pyexcel-bug-176.xlsx` median 0.259s across 5 runs, 311,559 chars, 3 headings, non-empty; `pyexcel-empty-sheet.xlsx` median 0.00039s, 132 chars, 3 headings, non-empty.

Latest XLSX generated-corpus sheet-heading, core-property, defined-name, shared formula range translation, time/duration number-format, currency/thousands number-format, negative accounting-style format, zero-padded identifier custom format, literal prefix/suffix custom format, fraction number format, scientific number format, embedded drawing image asset tracking, multi-series chart, and multi-block table check: `sample.xlsx` dochan-only median 0.00224s across 2 runs, accuracy 1.0, 1291 chars, 28 profiled table rows, 4 headings, 1 image reference, including `# Financial Workbook`, `Author: Finance Team`, `Defined name: SalesRange = Data!$A$1:$C$24`, `Defined name: Print_Area = Data!$A$1:$C$24`, `![Workbook revenue snapshot Picture 1](xl/media/image1.png)`, `## Data`, `### Revenue Chart`, `## Summary`, `12:00`, `36:00:00`, `$1,234.50`, `1,234`, `1,234.6`, `($1,234.50)`, `(1,234)`, `(12.5%)`, `00123`, `123-4567`, `12 kg`, `3.5x`, `SKU-0042`, `1/2`, `3 1/4`, `-1 1/8`, `1.23E+04`, `1.20E-03`, `-9.9E+03`, `10 (=SUM(A:A)+SUM(1:1))`, `20 (=SUM(B:B)+SUM(2:2))`, chart table header `Category | ARR | Profit`, `General Information`, `Business Description`, `Financials`, `809127967.92`, and `847831.96`. The same embedded XLSX image is also recorded in `Document.assets` with `source_path: xl/media/image1.png`, `content_type: image/png`, and sheet metadata. In Python 3.14 isolated competitor runs on this focused XLSX fixture, dochan kept accuracy 1.0 and led MarkItDown by +0.741 accuracy / 6.93x speed and Docling by +0.741 accuracy / 12.49x speed.

Latest dochan-only PPTX generated-corpus core-property, slide-heading, list, run-level formatting, image-reference, grouped-shape child coordinate transforms, SmartArt, image asset tracking, and multi-series chart check: `sample.pptx` median 0.00130s across 2 runs, accuracy 1.0, 740 chars, 4 headings, 3 links, including `# Board Update Deck`, `Author: Alice Analyst`, `## Slide 1`, `## Slide 2`, `• Bullet point`, `3. Third item`, `4. Fourth item`, `**Bold insight** *Italic caveat* <u>Underlined action</u> ~~Deprecated slide note~~`, `Grouped coordinate insight`, SmartArt diagram text `Plan` and `Build`, `![Revenue Chart ARR up 42 percent Picture 1](ppt/media/image1.png)`, and chart table header `Category | ARR | Profit`. The same embedded PPTX image is also recorded in `Document.assets` with `source_path: ppt/media/image1.png`, `content_type: image/png`, and slide metadata.

Latest dochan-only DOCX generated-corpus core-properties, character-style run formatting, run-level underline/strike/superscript/subscript formatting, multilevel numbering, skipped-leading-cell table, embedded image relationship asset tracking, comment-range annotation, and comment-reply check: `sample.docx` median 0.01188s across 2 runs, accuracy 1.0, 1127 chars, 3 headings, 2 links, 1 image reference, 1 comment marker, 6 profiled table rows, including `# Board Report`, `Author: Alice Analyst`, `<u>Underlined decision</u> and ~~Deprecated note~~`, `CO<sub>2</sub> target<sup>1</sup>`, `***Styled emphasis*** <u>Styled action</u> ~~Styled obsolete~~ <sub>2</sub>`, `a) Alpha item`, `X. Roman item`, `1.a) Child alpha`, `2.a) Child reset`, `![Revenue Chart ARR increased 42 percent Revenue chart](word/media/image1.png)`, `Body comment [comment 1: Comment detail]`, `Reply from Approver: Approved after legal review`, and the sparse table row `["", "Q3"]` from `w:gridBefore`. The same embedded DOCX image is also recorded in `Document.assets` with `source_path: word/media/image1.png` and `content_type: image/png`.

## Competitive Position

| Product | License posture | Best at | Main gap vs dochan | Main advantage vs dochan |
| --- | --- | --- | --- | --- |
| dochan | MIT; small permissive dependency set | Korean HWP/HWPX native parsing, low-latency local Markdown/JSON/text, native-only roadmap | No native PDF yet; Office support is early; no image/email/audio/archive ingestion | HWP/HWPX specialization, Python 3.9 support, very small dependency footprint, no runtime conversion backend |
| MarkItDown | MIT; Python >=3.10; many optional extras | Broad LLM-oriented Markdown conversion across PDF, Word, PowerPoint, Excel, images, audio, HTML, text formats, ZIP, EPUB, YouTube | No HWP/HWPX first-class advantage; broad support depends on optional format packages/services | Much broader format coverage today and strong ecosystem visibility |
| Docling | MIT codebase; model licenses must be checked separately | Advanced PDF layout, reading order, tables, OCR, multimodal document understanding, rich JSON/Markdown export | Heavier stack; no HWP/HWPX focus; Python 3.9 dropped in recent versions | Far ahead on PDF/layout/table/OCR quality and document AI features |
| Unstructured | Apache-2.0 | Enterprise ingestion pipelines, partitioning, element metadata, connectors and production ETL | Heavier operational/dependency surface; no HWP/HWPX focus | Strong production ingestion workflow, many file types, cloud/platform story |
| Apache Tika | Apache-2.0; Java stack | File type detection and metadata/text extraction over very broad file universe | JVM dependency; output is extraction-oriented rather than dochan-style Korean Markdown/JSON model | Massive mature format coverage, including legacy Office and PDF |

## Scorecard

Scores are current-state estimates on a 1-5 scale.

| Dimension | dochan | MarkItDown | Docling | Unstructured | Tika |
| --- | ---: | ---: | ---: | ---: | ---: |
| Korean HWP/HWPX | 5 | 1 | 1 | 1 | 1 |
| Office OOXML breadth | 3 | 4 | 4 | 4 | 4 |
| Legacy Office breadth | 2 | 3 | 2 | 3 | 5 |
| PDF extraction/layout | 0 | 3 | 5 | 4 | 4 |
| RAG-ready Markdown | 4 | 5 | 4 | 3 | 2 |
| Structured JSON/provenance | 4 | 2 | 5 | 4 | 3 |
| Dependency footprint | 5 | 3 | 2 | 2 | 2 |
| License fit for MIT core | 5 | 4 | 4 | 4 | 4 |
| Production maturity | 2 | 4 | 4 | 4 | 5 |

## Interpretation

dochan is not yet a general-purpose ingestion competitor to Docling, Unstructured, or Tika. Its current defensible wedge is narrower and stronger:

- Native Korean HWP/HWPX conversion.
- Very fast local parsing on Korean office/regulation documents.
- Small permissive dependency surface.
- Markdown/JSON/plain text output tuned for AI ingestion.
- A native-only Office/PDF roadmap that avoids GPL/AGPL/runtime-converter lock-in.

The current product level is best described as:

> Strong Korean document specialist with early native Office support, not yet a broad document AI platform.

## Priority Gaps

1. Native PDF Phase 1: simple digital text extraction with page provenance.
2. DOCX: images, broader numbering, richer nested table structure, and remaining style coverage beyond current paragraph/direct-run/character-style formatting.
3. XLSX/XLS: broader formula function coverage, remaining custom formats, charts, workbook metadata, more Strict OOXML samples, and streaming/compact Markdown paths for very large sheets.
4. PPTX/PPT: richer binary image asset export, broader chart variants, more complex grouped shapes, SmartArt variants, and richer table geometry.
5. Benchmark harness: same input corpus across dochan, MarkItDown, Docling, Unstructured, and Tika in isolated environments.

## Source Notes

- MarkItDown public docs list broad conversion support for PDF, PowerPoint, Word, Excel, images, audio, HTML, text formats, ZIP, YouTube, EPUB, and optional extras for individual formats.
- MarkItDown PyPI metadata lists MIT and Python >=3.10.
- Docling public docs list PDF/DOCX/PPTX/XLSX/HTML/EPUB/audio/email/images/LaTeX/plain text support, advanced PDF understanding, OCR, and local execution. Current README notes Python 3.9 was dropped in Docling 2.70.0.
- Docling README states the codebase is MIT, with model licenses checked separately.
- Unstructured README describes open-source components for ingesting and preprocessing PDFs, HTML, Word docs, images, and many more, and is Apache-2.0.
- Apache Tika public site states it detects and extracts metadata/text from over a thousand file types including PPT, XLS, and PDF.
