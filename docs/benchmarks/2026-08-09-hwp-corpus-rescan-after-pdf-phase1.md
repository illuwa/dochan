# 2026-08-09 — PDF Phase 1 이후 공개 HWP/HWPX 코퍼스 회귀 재스캔

## 목적

네이티브 PDF 리더 Phase 1 도입과 Opus 감수 2회 반영(라우팅 변경 포함)이
기존 HWP/HWPX 파싱 품질에 회귀를 일으키지 않았는지 2026-07-27 기준선과
동일한 방법으로 검증한다.

## 코퍼스

- 2026-08-09 재다운로드: 7,688개 URL 시도 → **7,594개 성공** (94개 실패),
  디스크 기준 HWP/HWPX **7,188개 / 5.4GB** (`corpus/hwp-public/`, gitignored).
- 7월 기준선(6,977개)보다 211개 많다 — 당시 실패했던 원본 서버 일부가
  이번에 응답한 결과로, 코퍼스 구성이 완전히 동일하지는 않다.
- 출처·라이선스 근거는 7월 문서와 동일 (법제처·국세청·보도자료 공공누리,
  GitHub 픽스처 MIT/Apache-2.0). `SOURCES.json`/`FAILURES.json` 재생성됨.

## 방법

다운로드(약 1시간 40분)와 스캔을 병렬화했다. 받는 도중 하드링크 스냅샷으로
중간 스캔 2회(2,276개 + 973개)를 먼저 돌려 조기 경보를 확보하고, 완료 후
전체 7,190개 대상 최종 스캔을 기준선과 동일 조건으로 실행했다.

```bash
python3 scripts/download_public_hwp_corpus.py corpus/hwp-public \
  --fixture-index docs/benchmarks/hwp-corpus-fixtures.json --delay 0.4
PYTHONPATH=. python3 scripts/scan_corpus_quality.py corpus/hwp-public --workers 8 \
  --output /tmp/hwp-quality-rescan.json
```

## 결과 — 기준선 대비

| 지표 | 2026-07-27 기준선 (6,977개) | 2026-08-09 재스캔 (7,190개) | 판정 |
| --- | --- | --- | --- |
| crashed | 2 | 2 | **동일 파일** — 신규 0 |
| succeeded_with_internal_errors | 8 | 7 | 전부 알려진 카테고리 |
| empty_output | 288 (4.13%) | 322 (4.48%) | 비율 동급 — 표본 검증 통과 |
| thin_output_suspect | 1,568 (22.5%) | 1,639 (22.8%) | 휴리스틱 잡음 범위 |

### 크래시 2건 — 기준선과 파일 단위로 동일

`hwpers-converted_output.hwp`, `hwpers-minimal_base_template.hwp`
(`invalid stored block lengths`). Indosaram/hwpers 라이터 라이브러리가 생성한
손상 zlib 스트림으로, 7월에 "dochan 버그 아님(원본 손상)"으로 기결론.

### 내부 오류 7건 — 기준선 8건과 카테고리 1:1 대응

- 암호화 `.hwp` 경고 2건 (`hwpjs-password-12345.hwp`, `password-12345.hwp`) —
  사양상 보고 후 중단. 기준선의 암호화 경고 3건 중 1건은 이번 다운로드에서
  받히지 않아 코퍼스에 없음 (94개 실패분에 포함).
- 암호화 HWPX의 XML 파싱 실패 2건 (`encrypt.hwpx`,
  `hwpjs-password-12345.hwpx`) — 기준선과 동일 파일, 동일 근본 원인(암호화).
- 원본 손상 HWPX 2건 (`ministry-[별표 3]…`, `nts-20250512…`) — 기준선의
  BadZipFile 2건과 동일 파일. 오류 메시지만 7월 수정 이후 형태
  (`유효하지 않은 HWPX 파일`)로 바뀜.
- 이미지 크기 상한 거부 1건 (`2026년 2분기 가축동향조사…hwpx`) — 기준선에도
  존재한 "정상 동작하는 안전 상한" 카테고리.

### empty/thin — 비율 동급, 표본 검증 통과

empty 322건 중 무작위 5건 표본 검사 결과 전부 차트 전용·오브젝트 전용
GitHub 테스트 픽스처로, 파싱 모델에 텍스트·이미지·표가 실제로 없고
내부 오류도 0건 (`3차원묶은가로막대형.hwp`, `2차원원형.hwp` 등 —
차트 오브젝트는 미지원 요소로 문서화된 한계). 절대치 증가(+34)는
코퍼스가 211개 늘어난 구성 변화 범위 안이다.

## 결론

**PDF Phase 1 작업(신규 모듈 + `.pdf`/`%PDF-` 라우팅 + 감수 반영 12건 수정)은
HWP/HWPX 경로에 회귀를 일으키지 않았다.** 크래시·내부 오류가 파일/카테고리
단위로 기준선과 일치하며, 신규 이상 클러스터가 하나도 없다. 라우팅 변경이
순수 추가(`.pdf` 분기, OLE/PK 매직 판정 뒤의 `%PDF-` 분기)라는 코드 리뷰
판단이 실측으로 확인됐다.

같은 날 별도로 수행한 PDF 실문서 검증(동일 문서 HWP/HWPX/PDF 80쌍,
크래시·제어문자 유출 0건, HWPX↔PDF 텍스트 유사도 평균 0.868)은 스펙 문서
Phase 6 상태 블록에 기록되어 있다.
