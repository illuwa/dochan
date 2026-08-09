# Priority 1 — HWP Binary Column Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the README Supported Elements gaps in the HWP (binary) column — 텍스트박스/도형 텍스트, 하이퍼링크/URL, 이미지 대체 텍스트, 주석(메모) — bringing HWP parity with the HWPX column. **절대 원칙: 체크는 (1) 단위 테스트 + (2) 공개 코퍼스 실문서 검증을 모두 통과한 항목만. 거짓 체크 금지.**

**Architecture:** Additive extensions to `dochan/hwp/section.py` control parsing. GSO(`gso `) controls already route to `_parse_image`; shapes with text carry `LIST_HEADER → PARA_HEADER` subtrees whose paragraphs must surface (HWPX 는 이미 지원 — 동작 동등성 목표). Hyperlink fields are CTRL_HEADER records whose ctrlId starts with `%` (`%hlk`); the URL lives in the field Command string, the visible text in the paragraph text stream. 이미지 대체 텍스트는 개체 공통 속성(스펙 표 70)의 설명문 문자열. 주석은 `tcmt` 메모 컨트롤.

**핵심 검증 자원 (모두 로컬):**
- 공개 HWP 코퍼스 7,188개: `corpus/hwp-public/` (스펙 추정이 어긋나면 실물 바이트로 확인)
- 동일 문서 HWP/HWPX 쌍: `/Users/illuwa/dev/personal/dochan/test_pairs/` — **HWPX 추출 결과가 정답지** (같은 문서에서 HWPX 가 뽑는 하이퍼링크/도형 텍스트를 HWP 도 뽑아야 함)
- 검증 명령: `PYTHONPATH=. pytest tests/ -q` (시작 시점 552개 통과), 회귀: `PYTHONPATH=. python3 scripts/scan_corpus_quality.py corpus/hwp-public --workers 8` (기준: crashed 2, internal 7 — docs/benchmarks/2026-08-09-hwp-corpus-rescan-after-pdf-phase1.md)

## Task 1: HWP GSO 텍스트박스/도형 텍스트

- [ ] 조사: corpus 에서 도형 텍스트가 있는 파일 하나를 찾아(같은 문서 HWPX 쌍의 도형 텍스트 존재로 판별) GSO ctrl_node 의 children 구조 덤프.
- [ ] 실패 테스트: 합성 픽스처(기존 tests/ 의 HWP 레코드 빌더 관례 활용) 또는 test_pairs 실파일 기반 — HWP 파싱 결과에 도형 내부 문단 텍스트 포함.
- [ ] 구현: `_parse_image`(GSO 경로)에서 LIST_HEADER 하위 PARA_HEADER 문단들을 파싱해 Image.caption 또는 문서 흐름 문단으로 배치 (HWPX 의 동작과 동일한 위치 규칙 선택).
- [ ] 검증: test_pairs 에서 HWPX 가 도형 텍스트를 뽑는 문서들의 HWP↔HWPX 유사도 개선 측정.
- [ ] Commit `feat(hwp): GSO 텍스트박스·도형 내부 텍스트 추출`.

## Task 2: HWP 하이퍼링크/URL (`%hlk` 필드)

- [ ] 조사: test_pairs 중 HWPX 하이퍼링크가 있는 문서의 HWP 바이너리에서 `%hlk` CTRL_HEADER 데이터 hexdump → Command 문자열 오프셋 실증 (스펙 추정 금지, 실물 우선).
- [ ] 실패 테스트: 해당 실파일(또는 최소 합성 레코드)로 `TextRun.link` 또는 `text <url>` 병기 형식(기존 XLS/PPTX 관례) 검증.
- [ ] 구현: `_parse_control` 에 field 분기(`ctrl_id[3:4] == b'%'` — LE 역순 주의: '%hlk' → b'klh%'). Command 에서 URL 추출(세미콜론 구분 꼬리 제거), 직후 텍스트 런에 link 부여 또는 URL 병기.
- [ ] 검증: HWPX 쌍이 뽑는 URL 집합과 HWP 추출 URL 집합 비교 (표본 ≥ 3개 문서).
- [ ] Commit `feat(hwp): 하이퍼링크 필드(%hlk) URL 추출`.

## Task 3: HWP 이미지 대체 텍스트 (개체 설명문)

- [ ] 조사: HWPX 대체 텍스트가 있는 쌍 문서의 HWP CTRL_HEADER 개체 공통 속성에서 설명문 문자열 위치 실증.
- [ ] 실패 테스트 → 구현(`Image.alt_text` — HWPX 필드명 확인 후 동일 필드) → 쌍 비교 검증.
- [ ] Commit `feat(hwp): 이미지 대체 텍스트(개체 설명문) 추출`.

## Task 4: HWP/HWPX 주석(메모)

- [ ] 조사: `tcmt` 메모 컨트롤 구조(HWP) + HWPX 주석 파트(`Contents/memo` 또는 comment 요소) — corpus 에서 메모 있는 실파일 탐색 (`b'tmct'` LE 패턴 grep).
- [ ] 실패 테스트 → 구현: DOCX 관례(`[comment: ...]` 마커 + Footnote(type='comment'))와 동일한 출력 형식.
- [ ] 실파일 검증 필수 — 실파일을 못 찾으면 합성 테스트만으로 README 를 올리지 말 것 (스펙에 부분 완료로 기록).
- [ ] Commit `feat(hwp,hwpx): 주석(메모) 추출`.

## Task 5: 회귀 검증 + 문서화 (오케스트레이터가 수행)

- [ ] 전체 테스트 + 코퍼스 7,188개 재스캔 (기준선 대비 무회귀).
- [ ] test_pairs HWP↔HWPX 유사도 재측정 (개선 방향 확인).
- [ ] README (검증 통과 항목만) / spec / CHANGELOG 갱신, 커밋.

## Self-Review

- 각 Task 의 판정 기준이 "HWPX 와 같은 문서에서 같은 결과" 라는 정답지 기반임.
- 코퍼스 재스캔이 최종 게이트 — 새 파싱이 기존 7,188개에서 크래시/오류 클러스터를 만들면 되돌린다.
