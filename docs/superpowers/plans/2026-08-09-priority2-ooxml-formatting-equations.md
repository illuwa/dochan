# Priority 2 — OOXML Formatting & Equations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the README Supported Elements gaps for OOXML/legacy-spreadsheet formats: XLSX/XLS style-based bold/italic, DOCX OMML equations → LaTeX, and honest verification (test-then-flip) of already-implemented PPTX formatting and DOCX/PPTX image references.

**Architecture:** Additive only. XLSX gains a font table read from `xl/styles.xml` (`fonts` + `cellXfs` `fontId`) applied to cell `TextRun`s. XLS gains BIFF `FONT` (0x0031) record parsing and `XF` font-index resolution (with the index-4 skip quirk). DOCX gains a recursive OMML→LaTeX converter emitting `Equation` elements; `Equation` gets an additive `latex_override` field so non-HWP sources can carry pre-converted LaTeX. README rows flip to ✅ only with passing verification tests; rows that are semantically inapplicable (날짜/숫자 서식 for word/slide formats) become `—` with rationale.

**Tech Stack:** Python 3.9+, stdlib + existing lxml pattern. No new dependencies.

**Validation:** `PYTHONPATH=. pytest tests/ -q` (535 passing at start).

## Task 1: Verification tests for already-implemented features (PPTX formatting, DOCX/PPTX image refs)

**Files:** Test: `tests/test_pptx_reader.py`, `tests/test_docx_reader.py` (append)

- [ ] Step 1: Add tests asserting PPTX `a:rPr` b/i/u/strike map to TextRun flags; PPTX picture → image reference paragraph + asset; DOCX drawing blip → `![label](target)` markdown + asset. These verify existing behavior (expected PASS — verification, not TDD).
- [ ] Step 2: Run; if any FAIL, implement the missing piece before flipping README.
- [ ] Step 3: Commit `test(ooxml): 기구현 서식·이미지 참조 검증 테스트`.

## Task 2: XLSX style-based bold/italic

**Files:** Modify `dochan/ooxml/xlsx.py`; Test `tests/test_xlsx_reader.py` (append)

- [ ] Step 1: Failing test — workbook with `xl/styles.xml` fonts `[normal, bold, italic]`, cellXfs mapping; assert cell runs carry bold/italic.
- [ ] Step 2: Extend the existing `_read_styles` path to also collect `fonts/font` (`b`,`i`,`u`,`strike` presence) and `cellXfs/xf@fontId` → per-style-index font flags; apply to the TextRun created for each cell (both table and provenance paths).
- [ ] Step 3: Full suite; commit `feat(xlsx): 스타일 기반 bold/italic 서식`.

## Task 3: XLS FONT/XF formatting

**Files:** Modify `dochan/office_binary/xls.py`; Test `tests/test_xls_reader.py` (append)

- [ ] Step 1: Failing test — synthetic BIFF stream with FONT records (bls=700 bold; grbit 0x0002 italic) + XF ifnt indices (including index ≥ 4 skip quirk) + LABELSST cells; assert run flags.
- [ ] Step 2: Parse FONT (0x0031): bold = bls ≥ 600, italic = grbit & 0x0002, underline = uls ≠ 0, strikeout = grbit & 0x0008; store font list with the BIFF quirk (indices 0-3 then 5+; resolver subtracts 1 for ifnt ≥ 5... implement as: fonts appended in order, lookup skips phantom index 4). XF already parsed at 0x00E0 — extend to keep `ifnt` per XF. Apply via each cell's XF index.
- [ ] Step 3: Full suite; commit `feat(xls): BIFF FONT/XF 기반 bold/italic 서식`.

## Task 4: DOCX OMML equations → LaTeX

**Files:** Modify `dochan/model/equation.py` (additive `latex_override`), `dochan/ooxml/docx.py`; Test `tests/test_docx_reader.py` (append)

- [ ] Step 1: Failing tests — DOCX with `m:oMath` fraction/superscript/sqrt/n-ary; assert `find_all('equation')` returns Equation with expected LaTeX; markdown contains `$...$`.
- [ ] Step 2: `Equation.latex_override: str = ""` — `latex` property returns override when set (HWP path unchanged). New `_omml_to_latex(elem)` recursive converter in docx.py covering: `m:r`/`m:t` text, `m:f` (`\frac{num}{den}`), `m:sSup`/`m:sSub` (`{base}^{sup}` / `_{sub}`), `m:sSubSup`, `m:rad` (`\sqrt[deg]{e}`), `m:nary` (chr → `\sum`/`\int`/`\prod` with `_{}^{}` limits), `m:d` (parens), `m:func`, `m:limLow`/`m:limUpp`, fallback: concatenated descendant text. Block `m:oMathPara`/`m:oMath` children of body → Equation element in section flow; inline oMath inside `w:p` → Equation appended after the paragraph (document order preserved).
- [ ] Step 3: Verify markdown output path renders Equation (existing `_element_to_md`); full suite; commit `feat(docx): OMML 수식 → LaTeX 변환`.

## Task 5: README/spec honesty pass

**Files:** `README.md`, `docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md`, `CHANGELOG.md`

- [ ] Step 1: Flip verified rows: 서식 PPTX/XLS/XLSX → ✅, 수식 DOCX → ✅, 이미지 참조 DOCX/PPTX → ✅ (each backed by a test added/verified above).
- [ ] Step 2: 날짜/숫자 서식 row: DOC/PPT/DOCX/PPTX ⬜ → `—` (already-rendered text formats carry no raw values to format — spreadsheet-only semantics).
- [ ] Step 3: Update spec Phase 2/4/5 status blocks; CHANGELOG entry; full suite; commit `docs: 비교표 갱신 — 검증 기반 ✅ 반영`.

## Self-Review Checklist

- Every README flip is backed by a named test.
- No new dependencies; existing public API unchanged.
- HWP equation path untouched (`latex_override` additive).
- XLS font index quirk (no index 4) handled and tested.
