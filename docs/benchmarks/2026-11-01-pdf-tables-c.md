# PDF 괘선 표 복원의 선택적 C 이식

**판정: 합류 보류.** 동일성·안전성 검증은 통과했으나 전체 15% 단축 목표와
파일별 1.2배 회귀 0건 조건을 충족하지 못했다. 검토용 구현을 워크트리에 남겼다.

기준은 시작 HEAD `56b0fcd5d448f4b7d68a811a9e48f4ae745f0cfc`의 `base-release`다.
원본 `tables.py` 알고리즘을 보존하고 손으로 쓴 CPython 3.9 제한 API 확장을 추가했다.
새 런타임·빌드 의존성, 외부 프로젝트 구현, README 지원 표·CHANGELOG 변경은 없다.
커밋·스테이징하지 않는다.

## 구현

- `_ctables.c`: 선분 분류, 성분 분리 연결, 후보 정렬, 중첩 부모 선택, 셀 예약,
  자식 채택·거부·승격, 최종 후보 생성과 예산 반영.
- `_ctables_geometry.h`: 선분 군집, union-find, 피복, 직사각형 분해, 격자,
  외곽 확장, 소유 셀, 점선 보강. 셀은 원래 모델 생성자를 호출하며 문단 목록은
  셀마다 독립적이고 Provenance는 원본처럼 격자 안에서 공유한다.
- `_ctables_text.h`: 쓰기·위쪽 축, 기준점 색인, 읽기 순서, 줄 캐시, 셀 배정,
  숫자 행 보강. 숫자·문자 판정과 `merge_lines`는 기존 공개 객체 의미를 유지한다.
  줄 조립은 기존 `_clines` C callable을 직접 호출하고, 미지원 반환에만 기존 조립기로 돌아간다.
- `split_connected`는 기존 모듈을 그대로 호출한다. 연결형 표의 별도 예산과 진단도 유지한다.
- `TableBudget`과 `TableCandidate`의 공개 Python 타입은 바꾸지 않는다. 예산은 예약 시점이
  아니라 채택 시점에만 차감하며, Bailout 때 시도 중 경고·예산을 버린 뒤 처음부터 재실행한다.
- 원본은 `_build_tables_python` 및 원래 보조 함수로 남긴다. `TABLE_BACKEND`는 선택된
  백엔드를 노출한다. `DOCHAN_BUILD_ACCEL=1`로만 빌드, `DOCHAN_DISABLE_ACCEL=1`로 해제,
  import 실패 중 `ImportError`만 폴백한다. 교체된 Python 보조 함수가 있으면 계측·사용자
  교체 동작을 보존하기 위해 Python 경로를 사용한다.
- 일반 list와 정확한 Segment/Fragment, 유한한 내장 숫자를 C에서 처리한다. 특수 숫자,
  큰 정수, 비유한 값 등 확신 없는 입력은 Python으로 되돌린다. 폴백 예외 문맥을
  원래 Python 오류에 붙이지 않는다.

## 순서·수치 감사

정상적인 유한 좌표 입력에는 먼저 바꿔야 할 비결정적 Python 순서 의존이 없었다.
따라서 선행 Python 결정화 패치는 하지 않았다.

| 위치 | 보존한 계약 |
| --- | --- |
| `_components` groups | 가로선, 세로선 방문 순서에 따른 dict 첫 삽입 순서 |
| `_make_grid` regions/boxes | 행 우선 셀 방문, union 크기 동률의 첫 루트, 영역·직사각형 삽입 순서 |
| `_assign_text` by_cell/events | 입력 조각의 첫 셀 등장 순서와 이벤트 삽입 순서 |
| `_short_dash_runs` axes | 축의 첫 등장 순서; parts 집합은 정렬 후 소비 |
| `_snap_runs`, `_rectangles`, `_supplement_rules` | Python 튜플 비교와 정렬 순서 |
| 기준점 색인, 읽기 키, 후보·노드 면적, 이벤트 키, 최종 anchor | 키 동률일 때 입력 순서를 보존하는 안정 정렬 |
| xs/ys 집합 | 정렬 전에 int/float/signed-zero 중복의 첫 대표 객체 보존 |
| 소유 셀 집합, fragment_orders | singleton pop 또는 집합 연산/min만 사용; 임의 순서를 출력에 쓰지 않음 |

C의 수치 정렬은 안정 병합 정렬을 쓴다. Python 객체 정렬은 `PyList_Sort`를 사용하며
모델 객체가 동률 비교에 참여하지 않도록 원래 순번으로 장식한다.
부동소수 연산 순서와 `pow`/`hypot` 선택을 보존하고 `-ffp-contract=off`를 적용했다.
Python 3.12부터 달라진 `sum(float)` 보상 합산을 하드코딩하지 않고 해당 인터프리터의
내장 `sum`으로 위임한다. 0·1개 피복 구간은 동일한 결과를 직접 계산한다.

## 검증 방법과 범위

공개 PDF는 pdf.js 983건, LibreOffice 24건, press-pairs 375건과 holdout 217/232/233/217건,
합계 2,281건이다. 공개 입력만 읽었으며 원본 코퍼스는 수정·복사하지 않았다.
해시는 기존 `scripts.benchmark_pdf_layout`와 `scripts.probe_output_speed`로
Markdown·JSON·일반 텍스트·진단 네 종류를 비교한다. 출력 동일성은 변환 정확도를
새로 입증하는 것이 아니다.

차등 퍼징은 공개 96쪽에서 얻은 선분·조각과 합성 숫자 행·점선 9종을 바탕으로 한다.
실물 전체 쪽과 부분 입력, 좌표 흔들기, 선분 추가·삭제, 조각/선분 순서 섞기,
방향 변형, 중복, 허용오차 경계, 빈 입력, 3,000선분 입력 및 문서 예산 소진을 비교한다.
전체 dataclass 필드·숫자 타입·IEEE 비트·순서·경고·남은 예산·입력 불변을 확인하고,
C 직접 성공·비어 있지 않은 결과·Bailout 횟수를 별도로 기록한다.

성능은 자체 검증 프로세스를 모두 끝낸 뒤 단일 프로세스로 전·후·후·전·전·후 순서의
300개 파싱 합계 중앙값을 구한다. 이어 2,281건 각각 전후 2회 최솟값을 비교하고,
기준 10ms 미만의 1.2배 회귀 후보는 20회 중앙값으로 재검사한다.
호스트의 다른 작업 부하까지 배제했다고 보장할 수는 없다.

재현 명령은 실행 환경에 맞는 경로 변수를 사용한다.

```sh
DOCHAN_BUILD_ACCEL=1 "$PY39" setup.py build_ext --inplace --force
"$PY39" -m pytest tests/ -q -p no:cacheprovider
DOCHAN_DISABLE_ACCEL=1 "$PY39" -m pytest tests/ -q -p no:cacheprovider
"$PY312" -m scripts.probe_pdf_ctables_fuzz --corpus "$PUBLIC_CORPUS" \
  --cases 100000 --capture-cache .codex-work/pages.pkl --output .codex-work/fuzz.json
"$PY39" -m scripts.benchmark_pdf_layout --source . \
  --manifest .codex-work/all-pdf.json --workers 4 --output .codex-work/after.json
"$PY39" -m scripts.probe_output_speed compare .codex-work/before.json .codex-work/after.json
```

ASan·UBSan은 3.9 헤더로 같은 소스를 빌드하고 macOS 시스템 Python의 플랫폼 제한을
피해 Homebrew 3.13 framework 실행 파일에서 구동한다. 프로세스 전체 누수 검사는 끄고
메모리 접근·정의되지 않은 동작을 검사한다. Linux·Windows 실행은 검증 범위가 아니다.

## 최종 소스 검증 결과

| 항목 | 범위 | 결과 |
| --- | --- | --- |
| 기준 → 가속 ON | Python 3.9, 공개 2,281건 | 네 해시 차이 0, 변환 실패 0 |
| 기준 → 가속 OFF | Python 3.9, 같은 2,281건 | 네 해시 차이 0, 변환 실패 0 |
| 기준 → 가속 ON | Python 3.12, 같은 2,281건 | 네 해시 차이 0, 변환 실패 0 |
| 차등 퍼징 | 최종 C 소스, Python 3.12, 100,000건 | C 직접 성공 100,000 / 비어 있지 않은 표 47,320 / Bailout 0 / 차이 0 |
| ASan+UBSan 차등 | 같은 최종 소스, Python 3.13, 100,000건 | 같은 성공 건수, 차이 0, 진단 0 |
| ASan+UBSan 실물 | 공개 300건, 같은 3.13 일반 빌드와 비교 | 네 해시 차이 0, 변환 실패 0, 진단 0 |
| 전체 테스트 ON | Python 3.9.6 | 6,898 passed, 36 skipped, 14 xfailed |
| 전체 테스트 OFF | Python 3.9.6 | 6,888 passed, 46 skipped, 14 xfailed |
| 엄격 컴파일 | 3.9 제한 API, C99, Wall/Wextra/Wpedantic/Werror | 통과 |
| Ruff·공백·로컬 경로 | dochan/scripts/tests/setup.py 및 경로 테스트 | 통과 |
| ABI3 wheel smoke | 설치 target의 3.9/3.12, 각각 ON/OFF | 모듈 존재·실제 설치 경로 import·표 결과 일치 |

Bailout은 특수 입력·큰 정수 허용오차·표현 불가능한 좌표·시도 중 경고와 예산 변경을
별도 회귀 테스트로 확인한다. 상한 소진, 중첩 깊이·부모 거부·자식 승격은 기존 표 테스트와
퍼징의 예산 변형을 함께 사용한다. 기존 테스트 단언은 수정하지 않았다. 새 테스트의
거대 좌표 기대값은 원본의 실제 OverflowError를 확인하여 메시지·예외 문맥 비교로 고쳤다.

산티타이저 300건을 다른 인터프리터인 3.9 결과와 직접 대조하면 본문 해시가 14건 달랐다.
따라서 산티타이저 동일성 수치는 같은 Python 3.13 일반 빌드와 비교한 값이다.
이 기록은 Python 버전 간 모든 출력의 동일성을 주장하지 않는다.

정식 PEP517 빌드는 로컬에 고정 요구 버전 `wheel==0.48.0`이 없어 실행되지 않았다.
네트워크 설치나 의존성 변경 없이 기존 `wheel 0.47.0`의 `setup.py bdist_wheel`로 smoke를
수행했다. 따라서 이 휠은 정식 릴리스 빌드 검증을 대신하지 않는다.

최종 증거는 `.codex-work/complete-sources.json`, `build-complete.log`,
`tests-verified-{on,off}.log`, `fuzz-complete.json`, `fuzz-complete-sanitized.json`,
`hashes-complete-*.json`, `complete-hash-comparisons.json`, `strict-complete.log`,
`ruff-complete.log`에 있다. 이전 `final`·`frozen` 이름 산출물은 개발 중 후보이므로
최종 수치에 사용하지 않는다.


## 단계별 통합 재검증

처음에는 독립 헤더를 병렬 구현하고 전체 제어 흐름에 함께 연결했다. 이후 동결된 최종
소스를 아래 순서로 부분 연결하여 각 단계에서 전수 해시를 다시 검증했다. 이전 단계의
C 보조 함수를 유지하면서 다음 단계의 함수를 추가하고, 마지막에는 전체 C 진입점을
사용한다. 이는 개발 당시 각 중간 소스를 측정했다는 주장이 아니라 최종 보조 함수의
통합 단계를 재생한 검증이다. 각 단계에서 C 직접 호출이 발생한 횟수도 기록했다.

| 누적 단계 | 공개 PDF | 네 해시 차이 | 실패 |
| --- | ---: | ---: | ---: |
| 격자·성분·피복·영역 | 2,281 | 0 | 0 |
| 기준점·셀 배정·줄 캐시 추가 | 2,281 | 0 | 0 |
| 숫자 행 추가 | 2,281 | 0 | 0 |
| 점선 보강 추가 | 2,281 | 0 | 0 |
| 전체 C 제어·중첩·예산 반영 | 2,281 | 0 | 0 |

근거는 `.codex-work/stage-complete.log`, `stage-*-complete.json`이다.

## 교대 3회 성능

단위는 초이며 프로파일을 끈 단일 프로세스의 300개 파싱 합계다.

| Python | 기준 3회 | C 3회 | 기준 중앙값 | C 중앙값 | 단축률 |
| --- | --- | --- | ---: | ---: | ---: |
| 3.9.6 | 6.7685 / 6.8070 / 6.7454 | 6.3900 / 6.3013 / 6.2133 | 6.7685 | 6.3013 | 6.90% |
| 3.12.12 | 6.0022 / 6.1042 / 5.9791 | 5.8315 / 5.8808 / 5.6551 | 6.0022 | 5.8315 | 2.84% |

두 인터프리터 모두 목표 15%에 미달한다.

## 전수 파일별 회귀 판정

| Python | 파일 수 | 2회 최솟값에서 1.2배 이상 | 10ms 미만 20회 재검사 | 최종 회귀 판정 |
| --- | ---: | ---: | ---: | ---: |
| 3.9.6 | 2,281 | 80 | 41 | 39 |
| 3.12.12 | 2,281 | 404 | 291 | 123 |

3.9의 남은 39건은 모두 기준 10ms 이상이다. 3.12는 기준 10ms 이상 113건과
작은 파일 재검사에서 남은 10건이다. 공개 표본 `issue8372.pdf`는 25.570 → 39.995ms,
`156783592.pdf`는 10.990 → 16.848ms로 측정됐다(3.9, 두 번 최솟값).
3.12의 `156782605.pdf`는 10.757 → 21.963ms다.
전체 파일별 기록과 작은 파일 20회 원시값은 `.codex-work/timing-summary.json`,
`all-time-*.json`, `small-time-*.json`에 있다.

자체 테스트·퍼징·병렬 해시 수집과 위 성능 측정을 겹치지 않았다. 다만 호스트의
프로세스 CPU 목록 조회가 샌드박스에서 차단되어 외부 부하가 완전히 없었는지는
검증하지 못했다. 이 한계를 회귀를 제외하거나 합류 조건을 완화하는 근거로 쓰지 않았다.

## 추가 원인 계측과 해석

속도 측정 후 `reader.build_tables` 경계에만 타이머를 넣은 별도 1회 검사다.
일반 교대 중앙값과 합치지 않는다. 네 실행 모두 표 복원 진입은 840회다.

| Python | 전체 기준 → C | 표 복원 기준 → C | 기준 표 비중 |
| --- | --- | --- | ---: |
| 3.9.6 | 6.4887 → 6.1268초 | 1.3798 → 1.1440초 | 21.27% |
| 3.12.12 | 4.8634 → 4.5745초 | 1.0722 → 0.7562초 | 22.05% |

표 복원의 단축은 이 검사에서 약 17.1% / 29.5%다. 전체 15%를 줄이려면 표 복원
비용의 약 68~71%를 없애야 하므로 현재 이식은 그 수준에 미치지 못한다.
현재 구현은 모델 객체 생성, 기존 줄·문단 조립, Python 객체 API 및 연결형 표 콜백을
유지한다. C로 루프를 옮겼다는 사실만으로 이 비용이 모두 사라지지는 않는다.

작은 파일의 비정상적인 비율도 별도로 조사했다. 3.12 `issue17998.pdf`는 원래
재검사에서 0.183 → 2.735ms였지만 표 복원 호출은 0회다. GC callback을 넣은 별도
진단에서는 0.186 → 0.206ms였다. 같은 291개 입력 전체의 GC 시간은 기준 0.0877초,
C 0.0834초로 오히려 줄었다. 따라서 모든 파일별 차이를 표 내부 계산 지연이나
GC 총량 증가로 단정할 수 없다. GC 발생 위치·실행 환경에 따른 변동 가능성은 있지만,
계측 자체도 할당 타이밍을 바꾸므로 이 진단으로 원래 회귀 판정을 뒤집지 않았다.

근거는 `.codex-work/table-share-*.json`, `gc-{before,after,pure}.json`,
`gc-probe.log`다. 후보는 미커밋 상태로 보존하며, 성능 합류 조건을 통과한 변경으로
취급하지 않는다.
