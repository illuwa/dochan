# PDF 레이아웃 잔여 Python 비용 최적화 — 합류 보류

기준은 읽기 전용 `base-round3`(73a05cb)다. 출력 동일성과 안전성 검증은 통과했지만,
300개 8% 단축 목표와 전수 파일별 회귀 0건 조건을 충족하지 못했다. 미커밋 후보이며 합류 승인 근거가 아니다.

## 구현 범위

- `notes.py`: 문자별 공백 판정 제너레이터를 `split`/`join` 길이로 대체. 크기 집계 순서와 정의 정규식은 유지했다.
- `running.py`: 가장자리 좌표로 먼저 거르고 판독한다. 공백 제거 후 C0/C1 및 대체 문자의 Python 정규식 집계로 문자별 목록/제너레이터를 없앴다. heapq의 안정적 선택 순서는 유지했다.
- `pagination.py`: `any` 제너레이터를 조기 반환 루프로 바꿨다.
- `annotations.py`: 두 끝점의 중간 좌표 목록과 네 개 제너레이터를 없앴다. 연산 순서, min/max 순서, 기하 검사 예산을 유지했다.
- `heading_font.py`: 이미 내용 런으로 걸러진 목록을 다시 거르지 않는다. 공개 함수 계약은 유지했다.
- `_cheadings.c`: `dataclasses.replace`의 필드 복사 루프를 C에서 처리한다. 캐시한 필드 이름, 생성자 키워드 순서, 덮어쓴 필드 미접근을 보존한다. 생성자와 동등성 비교는 그대로 호출한다. 바뀐 필드 목록/순서/init 및 비-dict 스키마는 Bailout한다.

새 가속 모듈·런타임 의존성은 없다. `_DEFINITION` 등 정규식을 C로 옮기지 않았다.
`reader.py`, `content.py`, `tables.py`, `layout.py`, `structure.py`, `output/`, README, CHANGELOG는 변경하지 않았다.
공유 파일의 등록 변경도 필요 없다. 입력 코퍼스는 읽기 전용으로 사용했다.

## 교대 성능

단일 작업자로 전·후·후·전·전·후 순서, 같은 공개 PDF 300개를 `--parse-only`로 측정했다.
자체 테스트·해시·퍼징·프로파일 프로세스가 종료한 것을 확인한 뒤 시작했다.
시스템 전체 유휴 상태는 확인하지 못했으며 load average를 `timing.log`에 기록했다.
아래 합계는 파일별 파싱 시간 합계의 3회 중앙값이다.

| Python | 기준(초) | 후보(초) | 단축률 |
| --- | ---: | ---: | ---: |
| 3.9.6 | 4.712238 | 4.577989 | 2.85% |
| 3.12.12 | 3.649615 | 3.531288 | 3.24% |

- 3.9.6: 기준 4.712238, 4.736762, 4.694469; 후보 4.569990, 4.595779, 4.577989초.
- 3.12.12: 기준 3.649615, 3.643140, 3.668887; 후보 3.529123, 3.560438, 3.531288초.

전수 2회 최솟값을 비교하고, 기준 10ms 미만의 회귀 후보는 교대 20회 중앙값으로 재판정했다.

| Python | PDF 수 | 최초 1.2배 후보 | 10ms 미만 재검사 | 규정 판정 후 회귀 |
| --- | ---: | ---: | ---: | ---: |
| 3.9.6 | 2281 | 27 | 16 | 11 |
| 3.12.12 | 2281 | 6 | 6 | 0 |

추가 원인 진단:

- Python 3.9: 규정 gate에서 남은 11건을 추가 교대 20회 측정하니 0건이 1.2배 이상으로 재현됐다.

이 추가 진단은 시간 변동의 재현성을 보는 참고 자료다. 규정된 gate 수치를 덮어쓰지 않는다.
환경/측정 순서의 영향 가능성과 코드 자체 회귀를 분리해서 확정할 수 없어 합류는 보류한다.
근거는 `timing-summary.json`, `all-time-*`, `small-time-*`, `large-diagnostic.json`이다.
초기 스키마 가드 이전 수치는 `timing-preliminary.*`이며 위 표에 사용하지 않았다.

## 프로파일

동일 300개/3.12/parse-only cProfile의 누적 초다. 계측 오버헤드가 있으므로 성능 gate를 대신하지 않는다.

| 함수 | 기준 | 후보 |
| --- | ---: | ---: |
| notes.py:detect_notes | 0.3339 | 0.2927 |
| running.py:detect_running | 0.1780 | 0.0258 |
| _cheadings:sized_runs | 0.1802 | 0.0872 |
| annotations.py:_attach_unique_links | 0.0917 | 0.0615 |
| pagination.py:body_between | 0.0404 | 0.0127 |
| heading_font.py:body_font_size | 0.1332 | 0.1274 |
| heading_font.py:_sample_exclusions | 0.1085 | 0.1068 |

C `sized_runs`에서 `dataclasses.replace`로 가던 42,041회 콜백은 0회가 됐다.
`Paragraph.text` 및 모델 생성자/동등성 계약은 유지한다. `profile-*-callbacks.txt`와
`profile-after-tottime.txt`에 근거가 있다. 최초 제공된 빈 프로파일 텍스트는 제공 `.prof`에서 복원했다.

## 출력 및 계약 검증

| 대상 | 수 | 가속 켬 | 가속 끔 |
| --- | ---: | --- | --- |
| 공개 PDF(pdf.js, 정책브리핑 짝, LibreOffice) | 2,281 | 4종 해시 차이 0 | 4종 해시 차이 0 |
| 공개 HWP/HWPX/DOCX/PPTX/XLSX | 각 100, 총 500 | 4종 해시 차이 0 | 4종 해시 차이 0 |

해시 수집은 Xcode Python 3.9.6에서 수행했다. Markdown·JSON·일반 텍스트·진단의 SHA-256을 `probe_output_speed` 수집기와 비교기로 대조했다.
수집 예외/시간 초과도 0이었다. 문서의 경고 내용이 없다는 의미는 아니며 진단 해시로 보존 여부를 검증했다.
`validate-hashes.py`는 `benchmark_pdf_layout`을 통해 같은 `measure_file`/`compare_records`를 사용한다.
최종 `compare-verified.log`, `hash-summary.json`과 8개 원시 수집 JSON이 근거다.

- TDD: 가장자리 외 판독/replace 콜백 red 2건, 생성자 키워드 순서 red 1건, 비표준 스키마 조기 거부 red 1건을 확인한 뒤 구현했다.
- 일반 및 최종 ASan+UBSan: 제목 실물320+변형100000, 각주 실물160+변형100000, 판독/쪽나눔/공통 본문 글꼴 각100000 차이 0. 결과 및 입력 전체 필드, 타입, 순서, float bit를 대조했다.
- 변형 한계: 제목은 최대48세그먼트 단일 줄, 각주는 최대32조각/16선분. 원래 실물 입력 전체는 별도로 먼저 비교했다.
- 링크: 실물 입력 전체32+변형100000 차이 0. 변형은 최대16조각/3영역, 두 clipped-edge 모드를 포함한다.
- Unicode 1,114,112 code point 전수에서 판독 정규식이 기존 category 판정과 같았다.
- 전체 테스트: 켬 **7101 passed, 39 skipped, 14 xfailed**, 끔 **7091 passed, 49 skipped, 14 xfailed**.
- `ruff check dochan scripts tests setup.py`, 3.9 헤더 C99 엄격 컴파일, 금지된 `#` API 포맷 검사 통과.
- ASan/UBSan은 최종 소스·3.9 제한 API 헤더로 빌드, Homebrew 3.13 실제 실행 파일에서 수행했다. 메모리 접근/UB 진단0이며 프로세스 전체 누수 검사는 껐다.
- 최종 3.13 헤더 abi3 확장을 3.12에서 로드해 공개 PDF20건을 변환했다. 같은 3.12에서 3.9 헤더 빌드 대비 4종 해시 차이 0. 3.13의 setuptools 부재 때문에 새 의존성 설치 없이 clang으로 별도 빌드했다.
- 3.9와 3.12 런타임 자체를 섞어 비교하면 공개 `156783245.pdf`에서 3종 출력 차이가 있었고, 기준 소스에서도 동일하게 재현됐다. ABI 빌드 비교와 구분했다.

## 재현 및 남은 범위

작업 폴더에 manifest, 캡처/차등/측정 스크립트와 원시 결과를 남겼다.
`PY39`는 Xcode 3.9, `PY313_EXECUTABLE`은 3.13 framework의 실제 실행 파일,
`ASAN_RUNTIME`은 clang ASan 런타임 경로를 가리킨다.

```sh
DOCHAN_BUILD_ACCEL=1 "$PY39" setup.py build_ext --inplace --force
"$PY39" .codex-work/capture-layout.py
"$PY39" .codex-work/fuzz-rest.py .codex-work/fuzz-verified.json
"$PY39" .codex-work/fuzz-links.py
bash .codex-work/sanitize-build.sh
DYLD_INSERT_LIBRARIES="$ASAN_RUNTIME" ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$PY313_EXECUTABLE" .codex-work/run-sanitized.py .codex-work/fuzz-rest.py .codex-work/fuzz-asan-verified.json
"$PY39" .codex-work/validate-hashes.py
"$PY39" -m pytest tests/ -q -p no:cacheprovider
DOCHAN_DISABLE_ACCEL=1 "$PY39" -m pytest tests/ -q -p no:cacheprovider
"$PY39" .codex-work/timing.py
"$PY39" .codex-work/recheck-large.py
```

`_sample_exclusions`의 순환/깊이/중복 방어와 전체 모델 재귀 탐색은 유지해 개선이 작다.
PDF 제목 마무리의 proxy/문맥 처리도 남았다. `reader.py:_body_groups`의 Python 조립 경로와
공용 모델 재귀 탐색 최적화는 별도 범위에서 검토해야 한다. 이번 소유 범위를 넘어 수정하지 않았다.

`final-source-hashes.json`과 `final-audit.json`에 최종 소스 지문 및 검증 시각을 기록한다.
빌드 임시 폴더와 실물 모델 캡처 pickle은 검증 후 정리했다. 캡처는 제공 스크립트로 재생성할 수 있다.
커밋·푸시·스테이징은 하지 않았다. 기존 미추적 `.serena/`는 보존했다.
