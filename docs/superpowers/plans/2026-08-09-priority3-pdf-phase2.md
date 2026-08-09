# Priority 3 — PDF Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modern-PDF structural coverage (xref streams + object streams + PNG predictors), outline bookmarks, link-annotation URLs, font-size heading detection, and best-effort simple table reconstruction — each README flip backed by tests, tables flipped only if real-document validation passes.

**Architecture:** Additive to `dochan/pdf/`. filters.py gains PNG predictor decoding (needed by virtually all xref streams). structure.py gains xref-stream parsing (`/Type/XRef`, `/W`, `/Index`, type-2 entries) and ObjStm object loading, replacing the scan-fallback warning path for PDF 1.5+. reader.py gains outline (`/Outlines` tree) paragraphs, `/Annots` Link-URI extraction, and font-size-based heading levels from a size-annotated line API in content.py. Table reconstruction clusters x-positions across adjacent lines; it ships behind honest validation (checkbox flips only if `[별표 19]` 표 재구성 품질이 확인될 때).

**Tech Stack:** stdlib only. **Validation:** `PYTHONPATH=. pytest tests/ -q` (539 passing at start) + real-doc smoke (`별표 19`, HWP/HWPX/PDF 80쌍 유사도 재측정).

## Task 1: PNG predictors in filters

- [ ] Failing tests: Flate+Predictor 12 (Up) round-trip for xref-stream-like data; Sub/Paeth cases; corrupted predictor data → warning + b"".
- [ ] Implement `_apply_png_predictor(data, columns)` (filter types 0-4: None/Sub/Up/Average/Paeth), wire via DecodeParms {Predictor≥10, Columns}; Predictor 2 (TIFF) → warning+drop 유지.
- [ ] Commit `feat(pdf): PNG predictor 해제 — xref 스트림 선행 조건`.

## Task 2: xref streams + object streams

- [ ] Failing tests: 합성 PDF with xref stream (W [1 2 1], type-1 entries) resolves objects without scan fallback; ObjStm-compressed object loads via type-2 entry; /Prev chain mixing classic+stream; encrypted flag from xref-stream trailer dict.
- [ ] structure.py: `_parse_xref_chain` branch — offset points at `N G obj` whose object is PDFStream with `/Type/XRef` → decode (predictor), parse W/Index fields, merge trailer keys (Root/Encrypt/Prev), record type-2 entries in `self._compressed: Dict[num, (objstm, idx)]`; `get_object` falls back to `_load_from_objstm` (parse `/N`,`/First`, header pairs, lex object at offset; cache whole ObjStm parse). Remove the xref-stream "미지원" warning on success path (keep for parse failure).
- [ ] Real-doc check: Downloads 암호화 PDF(붙임1)와 리모컨 매뉴얼 재확인 + 별표 19 무회귀.
- [ ] Commit `feat(pdf): xref 스트림·객체 스트림(PDF 1.5+) 네이티브 지원`.

## Task 3: Outline bookmarks

- [ ] Failing test: `/Outlines` 2-level tree → 문서 선두에 "목차" 문단들(들여쓰기 표기), Dest 페이지 번호 표기; 순환 outline 종료.
- [ ] reader.py: `_outline_paragraphs(pdf)` — First/Next 체인 순회(가드), title 디코드(UTF-16BE BOM/PDFDocEncoding), Dest/A→D 해석해 페이지 번호 매핑.
- [ ] Commit `feat(pdf): Outline 북마크 추출`. README 내부 북마크 PDF → ✅.

## Task 4: Link annotation URLs

- [ ] Failing test: page `/Annots` Link with `/A /URI` → 페이지 끝에 `Link: <url>` 문단 + provenance.
- [ ] Commit `feat(pdf): 링크 주석 URL 추출`. README 하이퍼링크 URL PDF → ✅ (본문 텍스트 연결은 좌표 매핑 없이는 부정직 — 하이퍼링크 행은 ⬜ 유지).

## Task 5: Font-size heading detection

- [ ] Failing test: Tf size 24 라인이 본문(size 10) 대비 heading_level ≥ 1; 동일 크기 문서는 heading 없음.
- [ ] content.py: 라인별 max font size 수집(`extract` → `(text, size)`), reader 에서 페이지 전체 중앙값 대비 임계(≥1.5× → h1, ≥1.25× → h2)로 heading_level 부여. 첫 페이지 상단 편향 없는 순수 크기 기반.
- [ ] Real-doc check 후 README 제목 감지 PDF → ✅ (품질 미달 시 보류).
- [ ] Commit `feat(pdf): 폰트 크기 기반 제목 감지`.

## Task 6: Best-effort table reconstruction

- [ ] content.py 확장: 라인 내 세그먼트 (x,text) 보존. reader: 연속 ≥2 라인이 ≥2개 공통 x 경계(허용오차)를 공유하면 Table 로 묶기, 아니면 기존 문단 유지.
- [ ] `[별표 19]` 실측: 표 행·열이 의미있게 복원되면 README 표(단순) PDF → ✅, 아니면 코드는 남기되 체크 보류 + 스펙에 기록.
- [ ] Commit.

## Task 7: Docs

- [ ] README에 "현대 PDF(1.5+) 구조" 행 추가(✅), 검증된 체크 반영, spec Phase 6 상태·CHANGELOG 갱신, HWPX↔PDF 80쌍 유사도 재측정 기록.
- [ ] Commit `docs: PDF Phase 2 반영`.

## Self-Review

- 모든 ✅ 는 테스트+실문서 근거. 예산·한도 기존 체계 유지(ObjStm 파싱도 decode budget 통과). 순환 outline/ObjStm 참조 가드.
