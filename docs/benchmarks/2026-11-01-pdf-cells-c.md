# PDF 표 셀 C 이식 검증 — 2026-11-01

**판정: 구현과 출력 동일성 검증은 완료했지만 성능 합류 조건은 통과하지 못했다. 합류 보류.**
300개 중앙값 개선은 2.5~2.6%로 목표 8%에 미달한다. 전수 파일별 회귀도 규정상 3.9에서 87개, 3.12에서 74개 남는다. 커밋·푸시는 하지 않았다.

## 변경 범위

- `_clayout.c`: 줄 병합, 가장자리 공백 제거, 문단 생성, 숫자 문자열/공백 분리 판정의 수작업 C 구현. 제한 API `0x03090000` 사용.
- `layout.py`: 공개 호출 인자 유지, `LAYOUT_BACKEND`, `DOCHAN_DISABLE_ACCEL`, ImportError/Bailout 폴백. 관찰 훅과 교체된 띄어쓰기 함수/모델 로더는 Python 경로로 처리.
- `_ctables_text.h`: 같은 `_clayout.c`를 직접 포함해 셀의 merge/paragraph를 C 함수로 호출한다. 숫자 행은 단어 리스트와 정규식 Match 객체를 만들지 않는다. 변경된 숫자 정규식은 Bailout한다.
- 실제 `_Line` 한 줄만 든 셀은 경계 계산 없이 원래 필드 객체를 유지한다. TextRun은 위치 인자로 생성해 매 run의 키워드 딕셔너리/문자열 키 할당을 줄였다. 모델 dataclass 생성자 호출은 여전히 남는다.
- `_ctables_geometry.h`: 3.9~3.11은 정수 0 시작, 왼쪽부터 `PyNumber_Add`로 누적. **3.12 이상은 builtin sum을 유지했다.** 3.12 보정 합산을 단순 누적으로 바꾸면 출력 비트가 달라진다. 실측 `sum([1e16, 1., -1e16])`은 3.9=0.0, 3.12=1.0이다. 따라서 모든 런타임에서 sum 콜백을 없애는 요구는 충족하지 않았다.
- setup/manifest/wheel 검증 목록과 해당 테스트에 `_clayout`만 추가. `_ctables.c`, `content.py`, `tables.py`, README, CHANGELOG는 수정하지 않았다. 런타임·빌드 의존성 추가 없음.

기준은 `base-round3`, HEAD `73a05cb`. 코퍼스는 읽기 전용으로 사용했다. 내부 문서 이름이나 내용은 기록하지 않았다.

## 최종 소스 검증

| 검사 | 결과 |
|---|---|
| 공개 PDF 2,281개, 가속 켬 | Markdown/JSON/text/진단 해시 차이 0, 실패 변화 0 |
| 같은 2,281개, 가속 끔 | 4종 해시 차이 0, 실패 변화 0 |
| 전체 테스트 켬 | 7107 passed, 39 skipped, 14 xfailed |
| 전체 테스트 끔 | 7097 passed, 49 skipped, 14 xfailed |
| ruff | 통과 |
| 3.9 헤더 C99, Wall/Wextra/Wpedantic/Werror | `_clayout.c`, `_ctables.c` 통과 |
| 크기 `#` 포맷 금지 | 전체 release contract 테스트 통과 |
| 실물 셀 차등 | 실제 셀 줄 505묶음 + 변형 100,000건, 차이 0 |
| Unicode 판정 | 전 코드포인트 단일 문자열 + 무작위 100,000개 = 1,214,112개, 차이 0 |
| 추가 단어 퍼징 | 무작위 단어 1,000,000개, Unicode decimal 650종 포함, 숫자·split 판정 차이 0 |
| ASan+UBSan | 최종 소스 셀 100,000건/문자열 1,214,112개 + 실물 PDF 300개, 진단 0 |
| ASan 실물 출력 | 동일 환경 기준 PDF 300개 4종 해시 차이 0 |
| 3.13 헤더 → 지정 3.12 실행 | 300개 변환 성공, 3.9 헤더 빌드 및 같은 환경의 기준 소스와 해시 차이 0 |

셀 비교는 dataclass 전 필드, 컨테이너 순서, Python 타입, IEEE float 비트를 비교했다. 방향, 좌표 경계, 공백, 빈 문자열, 문자 표식, 링크/노트/주석 run을 변형했다. Python 기준의 trim 호출도 C를 사용하지 않도록 분리했다.

ASan의 leak detector는 macOS Python 실행을 위해 `detect_leaks=0`으로 껐다. 메모리 누수 검증을 주장하지 않는다. `UBSAN_OPTIONS=halt_on_error=1`을 사용했다.
3.13 환경의 setuptools가 없어 새 의존성을 설치하지 않고 clang으로 해당 두 확장을 직접 빌드했다. 지정 pipcheck 3.12는 Pillow가 없고 bench-venv 3.12는 Pillow가 있으므로, 서로 다른 환경에서 발생한 14개 출력 차이는 동일 환경 대조로 분리했다. Python 버전 자체의 회귀로 단정하지 않는다.

TDD 최초 신규 검사 8개 실패를 확인했고, 주입된 spacing 모델의 AttributeError도 별도 실패 테스트로 재현한 뒤 폴백 가드를 고쳤다. 개발 중 바이너리 교체와 옛 Python 모듈이 섞였던 초기 전체 테스트는 근거에서 제외했다. 최종 두 모드 테스트와 모든 위 검사는 마지막 C 변경 이후 실행했다. `final-sources.json`의 SHA-256으로 이후 소스 불변을 확인했다.

## 성능

자체 테스트/퍼징/해시 수집 종료 후, 같은 manifest와 명령으로 전·후·후·전·전·후 실행했다. 300개 표본과 전수 2,281개 모두 parse-only, 단일 worker다. 전수는 각 소스 2회의 파일별 최솟값이며, 10ms 미만 의심 파일은 전·후 각각 20회 중앙값으로 재검사했다.

| Python | 전 중앙값(초) | 후 중앙값(초) | 개선 | 최초 ≥1.2배 파일 | 작은 파일 재검사 | 규정상 남은 회귀 |
|---|---:|---:|---:|---:|---:|---:|
| 3.9.6 | 5.184192 | 5.048928 | 2.609% | 169 | 82 | **87** |
| 3.12.12 | 3.920766 | 3.822938 | 2.495% | 159 | 85 | **74** |

- Python 39: 전 5.184192, 4.931112, 5.215113; 후 5.048928, 4.831539, 5.072127초.
- Python 312: 전 4.234726, 3.882856, 3.920766; 후 4.007635, 3.808620, 3.822938초.

두 런타임 모두 작은 파일의 재검사에서는 회귀가 해소됐지만, 나머지 파일의 규정상 회귀 수는 0이 아니다. 측정 중 시스템 load average를 원본 로그에 남겼다(교대 측정 시작 1분 load 약 9.4, 이후 약 4~6). 본 작업의 다른 부하는 종료했으나 다른 세션의 부하까지 확인할 권한은 없었다. 완전한 무부하 측정이라고 주장하지 않는다.

### 추가 원인 진단 — 합류 게이트를 대체하지 않음

각 버전에서 회귀 비율이 큰 공개 파일 3개를 별도 manifest로 전·후 각각 20회 교대 측정했다.

| Python | 공개 표본 | 최초 전수 비율 | 별도 20회 중앙값 비율 |
|---|---|---:|---:|
| 39 | `press-pairs/156784231.pdf` | 1.678× | 1.006× |
| 39 | `press-pairs/156784206.pdf` | 1.630× | 1.001× |
| 39 | `press-pairs/156784181.pdf` | 1.574× | 0.990× |
| 312 | `press-pairs-holdout2/156782518.pdf` | 1.595× | 0.970× |
| 312 | `press-pairs-holdout3/156782168.pdf` | 1.565× | 0.986× |
| 312 | `press-pairs-holdout/156782956.pdf` | 1.546× | 1.221× |

3.12의 `156782956.pdf`는 별도 20회에서 1.221배였으나, 같은 프로세스에서 100회 읽은 진단 프로파일에서는 전체 1.544→1.474초, `_ctables.build_tables` 누적 0.130→0.113초였다. 지속적으로 재현되는 C 셀 경로의 지연 원인은 특정하지 못했다. 전체 코퍼스 순서·캐시·시스템 부하와 단독 반복 측정의 차이를 분리해야 한다. 이 표본 진단으로 전수 게이트의 87/74개를 지우지 않았다.

300개 프로파일에서 Python `merge_lines` 호출은 26,916→1,813, paragraph는 36,761→6,115, Python `_trim_runs`는 49,692→0으로 줄었다. 그러나 모델 객체 생성과 속성 접근이 남아, Python 프레임 감소가 같은 비율의 전체 속도 향상으로 이어지지는 않았다. 서로 다른 부하에서 얻은 전후 프로파일 초 단위 수치를 속도 향상 근거로 사용하지 않았다.

## 재현 및 증거

로컬 작업 기록은 `.codex-work/`에 있다. 코퍼스 원본은 포함하지 않았다.

- `TASK.md`, `PROGRESS.md`, `final-sources.json`: 범위·과정·최종 소스 해시.
- `tdd-before.txt`, `custom-model-red.txt`: 실패 재현.
- `tests-final-on.txt`, `tests-final-off.txt`, `ruff-final.txt`, `strict-final.txt`: 최종 검사.
- `fuzz.py`, `fuzz-final.txt`, `number-fuzz.py`, `number-fuzz.txt`: 재현 스크립트와 차등 결과.
- `sanitized-run.py`, `sanitized.txt`, `sanitized-corpus.py`, `sanitized-corpus-compare.txt`: sanitizer 실행과 실물 대조.
- `cross-runtime.py`, `cross-compare.txt`, `cross-baseline-compare.txt`: 3.13 헤더/3.12 런타임 대조.
- `all-pdf.json`, `sample-pdf-300.json`, `hash-before.json`, `hash-final-{on,off}.json`, `compare-final-{on,off}.txt`: 동일성.
- `timing.py`, `timing.txt`, `timing-summary.json`, `time-*`, `all-time-*`, `small-time-*`: 성능 원본과 전수 회귀 목록.
- `diagnose-regressions.py`, `diagnostic-summary.json`, `regression-{before,after}.{txt,prof}`: 추가 회귀 진단.
- `profile-after-tottime.txt`, `profile-after.prof`: 최종 프로파일.

대표 실행 명령(저장소 루트, Python 3.9):

```sh
DOCHAN_BUILD_ACCEL=1 python setup.py build_ext --inplace --force
python -m pytest tests/ -q -p no:cacheprovider
DOCHAN_DISABLE_ACCEL=1 python -m pytest tests/ -q -p no:cacheprovider
python -m ruff check dochan scripts tests setup.py
python .codex-work/fuzz.py
python .codex-work/number-fuzz.py
python .codex-work/timing.py
```

합류 전에는 독립된 부하 환경에서 전수 파일별 회귀 0을 다시 증명해야 한다. 현재 결과는 -8% 달성 또는 성능 합류 성공으로 사용하면 안 된다.
