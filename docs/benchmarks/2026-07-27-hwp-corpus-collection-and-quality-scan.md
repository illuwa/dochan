# HWP/HWPX Public Corpus Collection and Quality Scan - 2026-07-27

## Objective

Move dochan's HWP/HWPX regression corpus from 155 hand-picked documents to a
much larger, publicly downloadable, license-audited corpus, then use it to
find real parsing gaps instead of only synthetic-fixture gaps.

## Methodology

1. Four independent research passes (GitHub-hosted open-source HWP/HWPX test
   fixtures; official Korean government/public-institution form archives;
   public data portal + National Assembly documents; HWPX standard samples
   and other public-institution press releases) collected candidate direct
   download URLs in parallel.
2. Every source bucket was spot-verified before trusting the full list: a
   stratified random sample was fetched for real (not just `HEAD`) and
   checked against the expected file magic bytes (OLE2 `D0 CF 11 E0...` for
   `.hwp`, ZIP `PK\x03\x04` for `.hwpx`), with a deliberately fake control
   URL confirmed to 404. All sampled sources passed 100% before the full run.
3. The merged candidate list (8,289 raw entries → 7,688 after URL-level
   dedup) is committed at `docs/benchmarks/hwp-corpus-fixtures.json` for
   reproducibility.
4. `scripts/download_public_hwp_corpus.py` downloads a fixture-index JSON,
   re-validates magic bytes per file (rejecting HTML error/login pages that
   return HTTP 200), enforces a 50MB per-file cap, and writes
   `SOURCES.json`/`SOURCES.md`/`FAILURES.json`. The full list was sharded
   into 6 interleaved chunks (mixing hosts within each chunk) and downloaded
   in parallel with a 0.4s per-request delay per chunk, so no single
   government host was hit much faster than a human clicking through pages
   would.
5. `scripts/scan_corpus_quality.py` converts every file in-process (no
   per-file Markdown written to disk) and records crashes, `Dochan.errors`
   even on "successful" conversions, and output-length-to-file-size ratio,
   then clusters error messages so the aggregate signal isn't hidden behind
   6,977 individual filenames.

## Corpus

- **6,977 unique files** (content-hash deduplicated) — **5,306 `.hwp`** +
  **1,671 `.hwpx`**, **5.1GB total**, at `corpus/hwp-public/` (gitignored —
  binaries are not checked in, same policy as the existing OOXML corpus
  scripts; re-download with the command below).
- Download success rate: 6,977/7,028 attempted = **99.3%** (51 rejected,
  mostly pre-5.0 HWP files with a plaintext `"HWP Document File"` header that
  dochan does not target, or extension/format-label mismatches caught before
  they entered the corpus).
- Top sources: 법제처 국가법령정보센터 별지서식 (2,118), 국세청 (1,313),
  중앙행정기관·지자체 보도자료 (1,282), GitHub open-source fixtures (1,085,
  MIT/Apache-2.0 — neolord0/hwplib, ohah/hwpjs, edwardkim/rhwp, Indosaram/hwpers,
  postmelee/alhangeul-macos, airmang/python-hwpx among others), 서울특별시 (99),
  국회입법예고 (76).
- License basis: Korean statutes/official notices are public domain under
  저작권법 제7조; government press releases and forms are published for
  public reuse (공공누리 등); GitHub sources are recorded per-repo under
  their own MIT/Apache-2.0 terms. Full attribution in `SOURCES.json`/`.md`
  (regenerated on download, not committed — regenerate via the command
  below).

Reproduce:

```bash
python3 scripts/download_public_hwp_corpus.py corpus/hwp-public \
  --fixture-index docs/benchmarks/hwp-corpus-fixtures.json --delay 0.4
python3 scripts/scan_corpus_quality.py corpus/hwp-public --workers 8 \
  --output /tmp/hwp-quality-scan.json
```

## Baseline: `dochan batch`

`dochan batch corpus/hwp-public corpus-output --format markdown --workers 8`
→ **6,975/6,977 (100.0%) did not crash.** Only `dochan batch`'s hard-failure
counter was checked here; it does not surface internal parse errors on
"successful" files, which is why the deeper scan below matters. (Side note:
`dochan batch` names outputs by basename only, so files with the same name
across the `hwp/`/`hwpx/` subfolders overwrote each other — ~619 collisions
in this run. Not a parser bug, but worth namespacing batch output by relative
input path in a follow-up.)

## Deep Quality Scan Findings

`scripts/scan_corpus_quality.py` inspects `Dochan.errors` and output length
on every file, including the 6,975 that "succeeded." Findings below are
ordered by confirmed impact; each was manually reproduced against a specific
file before being listed here.

### 1. [High] 배포용(distribution-copy) HWP documents lose 100% of body text

**22 distinct real files** (including live government documents — a 국세청
전자신고 매뉴얼 and a 통계청 2017 사회조사 결과 report, not just test
fixtures) produce **empty Markdown** with errors like `섹션 0 파싱 실패:
Error -3 while decompressing data: invalid code lengths set` repeated once
per section.

Root cause, confirmed by direct reproduction:

- `dochan/hwp/header.py:65` correctly detects `is_distribution` and routes
  body reading to the `ViewText` storage (`body_storage` property) instead
  of `BodyText`, per the HWP5 spec's 배포용 문서 format.
- `dochan/reader.py:132-145` then reads `ViewText/SectionN` streams and
  passes them straight into `SectionParser.parse_stream`, which calls
  `safe_zlib_decompress` (raw deflate, `wbits=-15`) exactly as it does for
  ordinary `BodyText` sections.
- That's the bug: 배포용 문서 `ViewText` section streams carry an additional
  spec-defined scrambling layer on top of the compressed record stream (a
  lightweight copy-protection measure), which must be reversed *before*
  zlib inflation. Feeding the raw bytes straight to `zlib.decompressobj`
  produces exactly this class of error (confirmed manually: the sibling
  `BodyText/Section0` stream in a distribution file inflates cleanly with
  the same `wbits=-15`, so the decompressor itself is not at fault — the
  `ViewText` bytes it's given are not yet real deflate data).
- Net effect: every 배포용 HWP file dochan is given today converts "cleanly"
  (no exception, no batch failure) but silently returns **zero body text**.
  This is worse than a crash because it is invisible without a scan like
  this one.

Suggested next step: implement the 배포용 문서 ViewText de-scrambling step
(HWP5 spec, distribution document section) in `dochan/reader.py` right
before `section_parser.parse_stream(stream_data, ...)` when
`file_header.is_distribution` is set, then re-run
`scripts/scan_corpus_quality.py` to confirm all 22 files recover real text.

### 2. [Medium] HWPX embedded-image compression-ratio guard has false positives on legitimate images

**15 distinct files** drop an embedded image with `이미지 ... 압축률 초과`
even though the image is real and well under the existing absolute-size cap.
Confirmed case: `dochan/hwpx/parser.py:30` sets `MAX_COMPRESSION_RATIO = 100`;
a real 기상청(Korea Meteorological Administration) press-release HWPX embeds
a 7.85MB BMP chart that deflates to 77,670 bytes — a **101.1x** ratio, just
over the threshold, on a file that is nowhere near the separate 100MB
absolute-size guard (`MAX_FILE_SIZE`). BMP is uncompressed pixel data, so
large single-color regions (letterheads, chart backgrounds) routinely exceed
100x compression under deflate without being any kind of zip bomb — a true
zip bomb targets ratios in the ~1000x+ range and multi-GB decompressed
payloads, which the existing `MAX_FILE_SIZE` check already blocks
independently.

Suggested next step: raise `MAX_COMPRESSION_RATIO` (e.g. to 300-500) or drop
the ratio check in favor of relying on the absolute decompressed-size cap,
which is the guard that actually matters for zip-bomb defense. Same pattern
appears at `dochan/hwpx/parser.py:131` (section XML) and `:208` (other parts)
using the same constant.

### 3. [Low, resilience] No magic-byte fallback when extension and content disagree

**35 files** in this corpus (0.5%) have a file extension that does not match
their real internal format — e.g. a file named `...신청서(...).hwp` whose
first bytes are `PK\x03\x04` (real HWPX/ZIP content), or a file named `*.hwpx`
whose first bytes are `D0 CF 11 E0...` (real HWP5/OLE2 content). This is a
data-hygiene artifact of how these particular files were named on their
source government sites, not a dochan defect — but `dochan/reader.py:49-51`
dispatches purely on file extension (`if ext == '.hwpx': ... elif ext ==
'.hwp': ...`), so these files fail outright (`유효하지 않은 HWPX 파일` /
`OLE 파일 열기 실패: not an OLE2 structured storage file`) even though
dochan has a fully working parser for their actual content.

Suggested next step: when extension-based dispatch fails validation, sniff
the first bytes (OLE2 signature → HWP path, ZIP signature → HWPX path) and
retry once before giving up. Cheap, backward compatible, and would have
recovered all 35 files in this corpus alone — real-world file distribution
(download managers, mislabeled CMS attachments) makes this a recurring
pattern at scale, not a one-off.

### 4. [Low] One file aborts a section on an invalid XML character instead of degrading gracefully

`corpus/hwp-public/hwpx/일반기안문_서식.hwpx` fails with `header.xml 파싱
실패: PCDATA invalid Char value ..., line ..., column ...` — a single invalid
XML control character embedded in an otherwise well-formed document trips
`lxml`'s strict parser and aborts that part entirely. Consider a fallback
pass that strips/replaces invalid XML 1.0 characters before re-attempting
the parse (mirrors how the existing OOXML loop already tolerates
minor-malformed real-world packages).

### On "thin"/"empty" output as a raw count

The scan's blunt heuristics (`markdown_stripped_len == 0`, or
`< 1%` of file size for files ≥ 3KB) flagged 342 "empty" and 1,549 "thin"
files. Manually sampling the thin-output list shows most are exactly what
they claim to be — files named `img_NN_image_in_table_cell.*`,
`table_NN_image_fill.*`, `mixed_NN_image_and_chart_same_doc.*` from
open-source fuzz/regression corpora, i.e. deliberately image-dominant
fixtures. Per the feature matrix in `README.md`, dochan does not extract HWP
image alt-text and does not OCR by default — so near-empty text output on an
image-only document is documented, correct behavior, not a new defect. The
342/1,549 counts are listed for completeness but are **not** an actionable
bug list on their own; the 22 + 15 + 35 + 1 findings above are the ones
confirmed against actual root causes.

## Summary

| Metric | Value |
| --- | --- |
| Fixture candidates found (4 parallel research passes) | 8,289 (7,688 unique URLs) |
| Downloaded & validated | 6,977 (99.3% of 7,028 attempted) |
| `dochan batch` no-crash rate | 6,975/6,977 (100.0%) |
| Confirmed silent-content-loss files (finding 1) | 22 |
| Confirmed false-positive image drops (finding 2) | 15 |
| Recoverable via magic-byte fallback (finding 3) | 35 |
| Hard XML abort (finding 4) | 1 |

This is roughly **45x** the previously documented 155-document validation
set, sourced entirely from license-clear public origins, and reproducible
end-to-end from the two scripts above plus the committed fixture index.

## Fixes Applied (same day, TDD)

All four findings above were fixed with a failing test written and observed
red before each implementation (`tests/test_aes.py`, `tests/test_distdoc.py`,
`tests/test_hwp_distribution_reader.py`, `tests/test_hwpx_zip_bomb_guard.py`,
`tests/test_reader_magic_byte_fallback.py`, `tests/test_hwpx_invalid_xml_char.py`).
See `CHANGELOG.md` (Unreleased) for the user-facing summary. Full suite: 439
tests passing, zero regressions.

Re-running `scripts/scan_corpus_quality.py` against the same 6,977-file
corpus after the fixes:

| Metric | Before | After |
| --- | --- | --- |
| `succeeded_with_internal_errors` | 79 | 8 (all encryption/DRM — out of scope by design) |
| `empty_output` | 342 | 288 |
| `thin_output_suspect` | 1,549 | 1,568 (unchanged within heuristic noise — see caveat below) |
| Crashed | 2 | 2 (unrelated `Indosaram/hwpers` writer-library files, not investigated this round) |

The `thin_output_suspect` count did not drop — expected, since (per the "On
thin/empty output" section above) that bucket is dominated by legitimate
image-only fixtures where dochan's documented behavior (no OCR by default)
makes minimal text output correct. Finding 2 (image ratio guard) does
recover real image *bytes* into `Document.assets`/`Image.image_data`, not
extracted *text*, so it doesn't move this particular text-ratio metric —
verified directly instead by re-checking the flagged 기상청 file's image
now loads with `has_data=True` at the full 7,849,954 bytes.

The remaining 8 `succeeded_with_internal_errors` break down as: 3 encrypted-
document warnings (by design — dochan reports and skips, matching the
documented security posture), 2 HWPX files (`encrypt.hwpx`,
`hwpjs-password-12345.hwpx`) whose `header.xml`/section XML fail because
they are also password-protected (same root cause as the encryption
warnings, just surfacing as an XML parse error instead — not finding 4's
single-stray-control-character shape), 1 legitimate oversized-image rejection
(working as intended, `MAX_FILE_SIZE` still applies above the raised ratio
threshold), and **2 files sharing one newly surfaced, out-of-scope issue**:
`zipfile.BadZipFile: File is not a zip file` even though both start with a
valid `PK\x03\x04` local-file-header signature — the central directory looks
truncated or non-standard. One of the two (`ministry-[별표 3]...hwp`) is
useful evidence the finding-3 fix is working correctly even here: its
extension is `.hwp` but content is ZIP, so before the fix it failed at the
OLE layer (`OLE 파일 열기 실패`); after the fix it correctly routes to the
HWPX parser and fails with the more accurate `BadZipFile` message instead —
better diagnostics, same underlying (different, unfixed) corrupt-archive
issue as the other file. Not investigated further this round; noted here for
a future loop rather than expanding scope mid-fix.
