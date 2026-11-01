# PDF 글꼴 준비의 선택적 C 가속

2026-11-01. 기준 커밋은 `56b0fcd5d448f4b7d68a811a9e48f4ae745f0cfc`.
기준 체크아웃과 작업 워크트리의 시작 HEAD가 같음을 확인했다. 커밋하지 않았다.

## 구현 범위와 동일성

- 손으로 작성한 `_ccmap.c`, CPython 3.9 제한 API. 새 의존성 없음.
- ToUnicode의 codespacerange/bfchar/bfrange를 처리하고 기존과 같은 dict·set·bool을
  반환한다. 블록 종류별 처리 순서, 중복 키의 삽입 순서, 홀수 자리 hex,
  UTF-16 대체 문자, surrogate/overflow, 손상 배열의 부분 복구와 매핑 상한을 보존한다.
- 이 파서는 PDF 객체 lexer가 아니라 기존 CMap 정규식의 관용 문법을 따른다.
  ToUnicode 주석 안의 부분 일치도 원래 동작대로 유지한다.
- Encoding의 codespacerange/cidrange/cidchar/notdefrange/notdefchar 행 파싱은 C로 옮겼다.
  주석 제거, 메타데이터, usecmap 부모 이름 해석·순환/깊이 제한·경고 합성 및
  EncodingCMap 인덱스 구축은 기존 Python 로직을 공유한다. 전체 C 재작성으로 주장하지 않는다.
- 단순 Widths/FirstChar와 CID W 배열의 숫자/범위 반복, Differences 표 구성을 C로 옮겼다.
  간접 참조 해석과 경고 전달은 reader에 유지한다. WidthMap의 int/float 변환,
  비유한 값 거부, 음의 0 비트, 항목 예산, reliable/cid_default를 보존한다.
- 15자리보다 긴 hex, 큰 정수, 지원하지 않는 입력/숫자 하위 클래스는 Bailout하여
  Python이 원점에서 다시 계산한다. C가 만든 중간 매핑이나 경고를 게시하지 않는다.
  매핑/범위 제한 상수가 변경된 경우에도 Python 경로를 사용한다.
- 정렬되어 서로 겹치지 않는 정확한 정수 범위는 sweep-line과 같은 결과를 C에서 바로
  반환한다. 역전·겹침·숫자 하위 클래스·비정수·사용자 정의 constant는 기존 경로로 보낸다.
  기존 predefined CMap의 LRU 캐시는 유지하며 Identity-H/V에서는 큰 데이터 모듈을
  가져오기 전에 반환한다. 공개 mutable 매핑의 사본을 공유하는 새 캐시는 도입하지 않았다.
- `CMAP_BACKEND`, `DOCHAN_BUILD_ACCEL=1`, `DOCHAN_DISABLE_ACCEL=1` 지원.
  ImportError만 폴백한다. setup·sdist manifest·휠 검증기에 모듈을 연결했다.
- `_parse_tounicode_python`, `_encoding_rows_python` 및 Python Encoding 진입점을
  차등 기준으로 남겼다. 겹침 범위의 안정 정렬/heap 계산과 set 순회 정책은 유지했다.
  기존 `_boxes`는 이미 sorted 순서로 인덱스를 만든다.

`content.py`, `_cinterp*`, `_show_table.py`, `tables.py`, `objects.py`, README,
CHANGELOG는 변경하지 않았다. 작업서의 `fonts.py`는 이 트리에 없으며 실제 폭 구성은
reader의 소유 함수에서 연결했다. C 소비자에는 기존 Python 매핑을 그대로 제공하며,
별도 C font-table 캐시나 decoder 실행 경로 변경은 포함하지 않는다.

## 검증

공개 PDF만 2,281건 사용했다. 내부 문서·코퍼스 원본은 수정하거나 저장소로 복사하지 않았다.

| 공개 묶음 | PDF 수 |
| --- | ---: |
| lo-src | 24 |
| pdfjs-src | 983 |
| press-pairs | 375 |
| press-pairs-holdout | 217 |
| press-pairs-holdout2 | 232 |
| press-pairs-holdout3 | 233 |
| press-pairs-holdout4 | 217 |


| 항목 | 결과 |
| --- | --- |
| CMap 추출 | 2,281 PDF, 스트림 12,988개, 고유 10,372개, 추출 오류 0 |
| 차등 검증 | 원본/합성 10,379건 + 변형 100,000건, 결과 전 필드·타입·매핑 순서·경고·예외 종류 차이 0 |
| 직접 C 경로 | 변형 입력 중 성공 95,973건, Bailout 4,027건 |
| 범위 차등 검증 | 200,000건 및 predefined 61종·124,475행, 차이 0 |
| 폭 차등 검증 | 20,000건, dict 순서·float IEEE 비트·기본값·경고 차이 0 |
| ASan + UBSan | 최종 C 소스, 위 전체 차등 검증 재실행, 진단 0 |
| sanitizer 공개 PDF | 300건, 일반 Python 3.13 C 빌드와 4종 해시 차이 0 |
| 전체 테스트, 가속 켬 | 6,878 passed, 36 skipped, 14 xfailed |
| 전체 테스트, 가속 끔 | 6,868 passed, 46 skipped, 14 xfailed |
| 엄격 컴파일 | Xcode 3.9 헤더, C99, Wall/Wextra/Wpedantic/Werror 통과 |
| 정적 검사 | ruff dochan/scripts/tests/setup.py 통과 |
| 패키징 | cp39-abi3 휠 격리 설치, Python 3.9/3.12의 C/해제 모드 smoke 통과 |
| 휠 내용 스캔 | 파일 멤버 146개·4,082,235 bytes 모두 스캔, 비밀 검출 0; binary/무확장 canary 2개 검출 |

차등 퍼징 시드는 20261101이다. 잘림, 임의 토큰 삽입, block 중첩, 뒤집힌 범위,
거대 범위/hex, 공백·주석·NUL 변형, usecmap 순환을 포함한다. 원본 스트림은 모두
전체 길이로 대조하고, 변형 반복의 원본 조각만 2,048 bytes로 제한한다.
추출·변환 결과 본문은 기록하지 않고 집계·해시만 보관한다.

TDD에서 새 CMap 인터페이스 13건, 폭/Differences 6건, 정렬 범위 16건의 실패를 먼저 확인했다.
첫 전체 실행의 휠 fixture 누락과 변경 가능한 상한 처리 실패를 수정하고 전체를 재실행했다.
기존 테스트 단언은 바꾸지 않았으며, 정상 휠 fixture에 새 필수 모듈만 추가했다.

ASan은 macOS Python 실행 래퍼 및 multiprocessing 자식에서 런타임 주입이 제거되어
초기 실행에 실패했다. framework의 실제 실행 파일과 단일 프로세스 추출로 전환했다.
최종 검증은 3.9 헤더로 컴파일한 C를 3.13 framework에서 실행한다.
`detect_leaks=0`이므로 Python 프로세스 전체의 누수 검사 통과를 주장하지 않는다.

## 전수 출력 동일성

기준판의 기존 가속을 켠 상태와 새 CMap 가속을 켠 상태, 모든 가속을 끈 상태를 비교했다.
`probe_output_speed.measure_file`/`compare_records`의 동일한 수집·비교 코드를 사용했다.

| 비교 | PDF 수 | Markdown | JSON | 텍스트 | 진단 | 실패 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 기준 → 새 C 가속 | 2,281 | 0 | 0 | 0 | 0 | 0 |
| 기준 → 모든 가속 해제 | 2,281 | 0 | 0 | 0 | 0 | 0 |

표의 0은 차이/실패 건수다. 기존 결과와의 동일성이며 내용 정확성 자체의 독립 검증은 아니다.
해시 수집은 다른 검증과 함께 실행했으므로 그 로그의 소요 시간은 성능 증거로 사용하지 않는다.

## 최종 성능과 합류 판정

**합류 보류.** 300개 표본에서 두 버전 모두 5% 목표 미달이며, 전수 파일별 게이트도 미충족이다.
자체 테스트·퍼징·해시 수집은 종료한 뒤 측정했다. 외부 프로세스의 완전한 무부하는
샌드박스의 프로세스/CPU 조회 제한으로 확인하지 못했다. 따라서 아래 관측값을 다른 부하/장비의 보장값으로 해석하지 않는다.

| Python | 기준 3회(초) | C 3회(초) | 중앙값 전→후(초) | 감소 |
| --- | --- | --- | --- | ---: |
| 3.9.6 | 6.306017 / 6.401899 / 6.361417 | 6.102215 / 6.127968 / 6.124593 | 6.361417 → 6.124593 | 3.72% |
| 3.12.12 | 4.550329 / 4.540348 / 4.551959 | 4.446837 / 4.459729 / 4.495467 | 4.550329 → 4.459729 | 1.99% |

전·후·후·전·전·후 순서다. 각 회차는 새 프로세스에서 같은 300개를 읽는다.
최종 round JSON에는 실제 import 경로·CMap 백엔드·프로세스 CPU 시간도 기록했다.

전수 2,281개 파일별 2회 최솟값 합계는 **40.568433 → 38.856935초(-4.22%)**다.
초기 1.2배 의심 39건 중 10ms 미만 27건은 20회 중앙값 재검사에서 모두 해소됐다.
10ms 이상 **12건**은 공통 규칙의 파일별 게이트에 남는다. 이를 임의로 제외하거나 전체 합계로 상쇄하지 않는다.

| 공개 파일 | 기준 최소(ms) | C 최소(ms) | 배율 |
| --- | ---: | ---: | ---: |
| `press-pairs/156783504.pdf` | 11.674 | 14.816 | 1.269 |
| `press-pairs/156783592.pdf` | 10.901 | 15.427 | 1.415 |
| `press-pairs/156783645.pdf` | 10.644 | 14.386 | 1.352 |
| `press-pairs/156783674.pdf` | 13.011 | 15.928 | 1.224 |
| `press-pairs/156783737.pdf` | 13.879 | 17.093 | 1.232 |
| `press-pairs/156783754.pdf` | 12.525 | 15.352 | 1.226 |
| `press-pairs/156783822.pdf` | 11.235 | 14.345 | 1.277 |
| `press-pairs/156783908.pdf` | 17.027 | 20.882 | 1.226 |
| `press-pairs/156783918.pdf` | 18.401 | 22.501 | 1.223 |
| `press-pairs/156784079.pdf` | 12.041 | 15.428 | 1.281 |
| `press-pairs/156784206.pdf` | 12.154 | 15.145 | 1.246 |
| `press-pairs/156784224.pdf` | 10.065 | 13.102 | 1.302 |

초기 후보에서는 35건이 같은 게이트에 남았다. 이 35건을 최종 소스의 같은 프로세스에서
글꼴 준비 C 경로만 번갈아 켜고 끄며 20회 중앙값으로 확인한 진단에서는 벽시계/CPU 회귀가 모두 0건이었다.
벽시계 비율 범위는 0.887~1.032였다.
하지만 이 진단은 서로 다른 소스의 전수 2회 최소 규칙을 대체하지 않는다.
단독 반복과 전수 순회 간 불일치의 원인은 확정하지 못했으며 최종 12건을 미해결로 남긴다.

### 글꼴이 많은 문서

`_build_font_info` 실제 호출 수로 300개 중 상위 8개를 골랐다(총 1,466회).
시간은 정식 교대 3회에서 해당 파일의 중앙값이며 별도 유리한 회차를 고르지 않았다.

| 공개 파일 | 글꼴 준비 수 | 3.9 전→후(ms) | 3.12 전→후(ms) |
| --- | ---: | ---: | ---: |
| `pdfjs-src/test/pdfs/tracemonkey_annotation_on_page_8.pdf` | 24 | 226.051 → 222.338 | 142.035 → 238.177 |
| `pdfjs-src/test/pdfs/issue6961.pdf` | 20 | 45.849 → 42.736 | 120.523 → 32.234 |
| `press-pairs-holdout/156783340.pdf` | 20 | 76.961 → 76.959 | 51.804 → 54.361 |
| `press-pairs/156783589.pdf` | 20 | 1271.616 → 1238.717 | 832.534 → 818.995 |
| `press-pairs/156783747.pdf` | 19 | 47.109 → 49.277 | 38.545 → 34.104 |
| `press-pairs/156783899.pdf` | 19 | 44.544 → 43.153 | 30.702 → 29.786 |
| `press-pairs-holdout/156782918.pdf` | 18 | 27.653 → 26.204 | 16.706 → 15.815 |
| `press-pairs/156783710.pdf` | 18 | 262.241 → 270.565 | 198.697 → 195.720 |

### 준비 단계의 별도 계측

정식 속도 측정과 분리해 `_font_infos` 호출 전체를 perf_counter로 감쌌다. 869회 호출의
누적값이며 C font-table 구축 등 이 함수 밖의 비용은 포함하지 않는다. 한 번의 진단 계측이므로
이 표의 전체 시간으로 정식 교대 측정 결과를 대체하지 않는다.

| Python | 글꼴 준비 전→후(초) | 기준 전체 중 글꼴 준비 비중 |
| --- | ---: | ---: |
| 3.9 | 0.308113 → 0.155934 | 5.01% |
| 3.12 | 0.199558 → 0.113885 | 4.47% |

입력 스트림 1,338개의 ToUnicode 준비만 따로 잰 후보 1 진단에서도
3.9는 0.159952→0.052651초, 3.12는 0.106636→0.047339초였다.
이 수치를 문서 전체 개선율로 환산하지 않는다. 처음 cProfile의 비중과 실제 비계측 전체 소요의 비중은 구별해야 한다.

초기 후보의 불안정한 교대 값(3.9 -21.41%, 3.12 +8.05%)과 35건 회귀 기록은
`.codex-work/candidate-1/`에 보존했다. 이들을 최종 성능 주장에 섞지 않았다.

## 재현 방법

`PATHS`는 공개 PDF 전수 경로 JSON, `BASE`는 기준 체크아웃, `PY312`는 3.12 환경이다.
벤치마크 실행 도우미와 원시 JSON·로그는 `.codex-work/`에 남긴다.

```sh
DOCHAN_BUILD_ACCEL=1 python setup.py build_ext --inplace --force
python -m scripts.probe_pdf_fontprep --paths "$PATHS" --count 100000 --output fuzz.json
python -m pytest tests/ -q -p no:cacheprovider
DOCHAN_DISABLE_ACCEL=1 python -m pytest tests/ -q -p no:cacheprovider
python -m ruff check dochan scripts tests setup.py
```

C 빌드/테스트는 Xcode Python 3.9로 수행한다. `collect_pdf.py`는 명시된 소스에서
4종 출력을 수집한다. `benchmark.py`는 3.9/3.12의 300개 교대 3회와 3.9 전수
파일별 2회 최솟값을 측정하고, 10ms 미만 의심 파일을 20회 중앙값으로 재검사한다.
ASan은 `-fsanitize=address,undefined -fno-omit-frame-pointer -ffp-contract=off`로 빌드하고
framework 실제 실행 파일에 런타임을 주입한다. `sitecustomize.py` finder로 새 모듈만
계측본을 선택하여, 다른 모듈의 소스/바이너리는 변경하지 않는다.

## 한계

macOS ARM64 로컬 검증이며 다른 운영체제 및 x86_64 실행 검증은 포함하지 않는다. 전체 Encoding
부모 해석과 decoder 생성 자체를 C로 모두 옮긴 구현은 아니다. 미지원/큰 정수 입력의
성능은 Python 재실행 비용을 포함한다. 공개 매핑 구조와 기존 C font-table 소비 계약은 유지했다.

## 감수 후속: bfrange 메모리 증폭 수정

후속 시작 HEAD는 `c78650ceea3d8a8fc9ba8474de5d526961e52620`이다.
기존 기록은 앞선 작업의 결과이며, 아래는 TASK-FIX 최종 소스로 다시 검증한 결과다.

### 결함과 구현

기존 `unicode_block`은 32바이트 Token을 블록 전체에 대해 배열로 보관했다.
16MiB 미만의 `[` 반복 입력도 수천만 토큰 슬롯으로 증폭될 수 있었다.
FlateDecode ToUnicode가 들어 있는 17,079바이트 재현 PDF로 새 프로세스에서
최대 RSS를 비교한 회귀 테스트가 기존 C에서 실제 실패했다:
C 592,740,352 bytes, 전체 가속 해제 205,144,064 bytes(허용은 1.2배).
처음 테스트 fixture의 dict/list 착오를 고친 뒤 이 자원 단언의 실패를 확인했다.

수정은 토큰 배열을 제거하고 **3개 토큰 창**과 목적지 배열의 순차 소비로 바꾼 것이다.
codespacerange와 bfchar도 토큰을 저장하지 않고 처리한다. 매핑 결과 공간을 제외한
토큰 보관 공간은 상수이며 토큰 수 상한으로 Python에 넘기는 방식이 아니다.
손상 범위의 1칸/3칸 이동, 중첩 `[`의 블록 중단, 배열 뒤의 재개,
미닫힘 배열, 매핑 상한·경고·삽입 순서는 유지한다.
전체 블록 사전 스캔은 무시되는 꼬리에 있는 긴 hex의 기존 Bailout 계약도 보존한다.
16자리 이상 hex를 토큰별로 처리하는 선택 개선은 이번 수정에 포함하지 않았다.

### 후속 정확성·안전성 검증

| 항목 | 결과 |
| --- | --- |
| CMap 테스트 | 45 passed; 신규 RSS 1건, 복구 7건, 무시된 꼬리 Bailout 1건 |
| RSS 회귀 방식 | 새 subprocess에서 PDFReader.read, C/전체가속해제 각각 실제 backend 단언, C RSS ≤ Python RSS × 1.2 |
| 플랫폼 처리 | macOS bytes / Linux KiB를 bytes로 정규화, 그 외 플랫폼 skip; 실제 실행은 macOS ARM64 |
| 전체 테스트 3.9, 가속 켬 | 6887 passed / 36 skipped / 14 xfailed |
| 전체 테스트 3.9, 가속 끔 | 6877 passed / 46 skipped / 14 xfailed |
| 공개 CMap 추출 | PDF2281, 스트림12988 / 고유10372, 오류0 |
| 일반 및 ASan+UBSan 각각 | 원본·합성10379 + 변형100000, 폭20000, 범위200000, predefined61종/124475행; 차이0 |
| 직접 ToUnicode C | 변형 중 성공95973, Bailout4027 |
| ASan PDF | 공개300건 일반3.13 대비 4종 해시 차이0; 메모리 증폭 재현 PDF도 진단0 |
| 엄격 컴파일 | 3.9 헤더, C99 Wall/Wextra/Wpedantic/Werror 통과 |
| ruff | dochan/scripts/tests/setup.py 통과 |
| 기준판 → 수정 C | PDF2281, Markdown/JSON/텍스트/진단 각각 차이0, 실패0 |
| 기준판 → 전체가속해제 | PDF2281, Markdown/JSON/텍스트/진단 각각 차이0, 실패0 |

ASan은 최종 `_ccmap.c`를 3.9 헤더로 빌드해 3.13 framework 실행 파일에서
검증했다. `detect_leaks=0`, ASan/UBSan의 `halt_on_error=1`이며 프로세스 전체
누수 검증을 주장하지 않는다. 다른 OS·x86_64 실측과 휠 재검증은 이번 후속에 포함하지 않았다.
기존 테스트 단언·금지 소유 파일·README·CHANGELOG는 변경하지 않았다.
후속 원자료는 `.codex-work/fix/`, 앞선 작업 원자료는 그대로 보존했다.

### 후속 RSS·시간 실측

각 칸은 **최대 RSS(MB, 10⁶ bytes) / 시간(초)** 이며 각각 새 프로세스다.
재현 PDF는 감수 재현기의 동일 17,079 bytes다. 직접 스트림은 16MiB 상한 미만의
`[` 또는 `<0>` 반복이며, 해당 시간에는 입력 생성도 포함한다.
기존 C는 수정 전, 기준판·전체가속해제·수정 C는 수정 후 단독 재측정 값이다.

| 입력 | 기준판 | 전체가속해제 | 기존 C | 수정 C |
| --- | ---: | ---: | ---: | ---: |
| 재현 PDF | 197.62 / 2.845309 | 205.49 / 2.827373 | 592.90 / 0.073989 | 53.71 / 0.087030 |
| `[` 반복 | 197.39 / 2.869635 | 205.11 / 2.903795 | 743.69 / 0.075586 | 69.78 / 0.083535 |
| `<0>` 반복 | 107.92 / 2.179560 | 115.64 / 2.144406 | 251.43 / 0.115884 | 69.62 / 0.124221 |

재현 PDF의 수정 C / 전체가속해제 RSS 비율은 **0.261배**로 1.2배 게이트를 통과했다.
수정 전/후 모든 기준·해제 값과 원시 bytes는 `.codex-work/fix/memory-before.json`과
`.codex-work/fix/memory-after.json`에 별도로 보존했다.

### 독립 감수 퍼저

감수자의 `fuzz_ccmap.py`를 복사해 수정하지 않고 Python 3.9, seed20261102,
30000회와 결정적 경계 사례를 실행했다. 모든 범주에서 차이0, 정상 종료0이다.

```text
seed 20261102 iterations 30000
cid_widths                   cases=   30000 mismatches=0
differences                  cases=   30000 mismatches=0
encoding                     cases=   30045 mismatches=0
encoding_direct_ok           cases=   30045 mismatches=0
encoding_rows_direct         cases=   30045 mismatches=0
flatten                      cases=   60000 mismatches=0
predefined                   cases=      61 mismatches=0
simple_widths                cases=   30000 mismatches=0
tounicode                    cases=   30049 mismatches=0
tounicode_direct_bail        cases=   11088 mismatches=0
tounicode_direct_ok          cases=   18961 mismatches=0
```

### 후속 성능과 합류 판정

자체 검증 프로세스가 모두 종료된 뒤 RSS 측정과 성능 측정을 순차 실행했다.
외부 프로세스 조회는 샌드박스가 차단하므로 호스트 전체 무부하는 확인하지 못했다.
다음은 base-release 대비 전·후·후·전·전·후 300개 교대 3회의 관측값이다.

| Python | 기준 3회(초) | 수정 C 3회(초) | 중앙값 전→후(초) | 감소 |
| --- | --- | --- | --- | ---: |
| 3.9 | 6.769544 / 6.356446 / 6.314734 | 6.114580 / 6.164312 / 6.370675 | 6.356446 → 6.164312 | 3.02% |
| 3.12 | 4.516268 / 4.519469 / 4.513921 | 4.477459 / 4.453143 / 4.474651 | 4.516268 → 4.474651 | 0.92% |

전수 2281개 파일별 2회 최소 합계: 40.841173 → 39.091982초(4.28% 감소).
초기 1.2배 의심 46건, 10ms 미만 32건은 20회 중앙값 재검사.
최종 남은 회귀 18건(10ms 이상 14, 짧은 파일 4).

| 공개 파일 | 기준 최소(ms) | 수정 C 최소(ms) | 배율 |
| --- | ---: | ---: | ---: |
| `press-pairs/156783504.pdf` | 11.725 | 14.758 | 1.259 |
| `press-pairs/156783592.pdf` | 11.381 | 15.902 | 1.397 |
| `press-pairs/156783645.pdf` | 10.953 | 14.104 | 1.288 |
| `press-pairs/156783665.pdf` | 20.899 | 25.458 | 1.218 |
| `press-pairs/156783674.pdf` | 12.963 | 16.205 | 1.250 |
| `press-pairs/156783681.pdf` | 14.533 | 17.982 | 1.237 |
| `press-pairs/156783694.pdf` | 12.846 | 15.771 | 1.228 |
| `press-pairs/156783737.pdf` | 13.853 | 17.282 | 1.248 |
| `press-pairs/156783822.pdf` | 11.267 | 14.376 | 1.276 |
| `press-pairs/156783918.pdf` | 18.539 | 22.568 | 1.217 |
| `press-pairs/156783959.pdf` | 12.371 | 15.208 | 1.229 |
| `press-pairs/156784079.pdf` | 12.268 | 15.631 | 1.274 |
| `press-pairs/156784206.pdf` | 12.303 | 15.136 | 1.230 |
| `press-pairs/156784224.pdf` | 10.184 | 13.049 | 1.281 |

짧은 파일의 재검사 잔여 회귀:

- `lo-src/sd/qa/unit/data/PdfWithAnnotation.pdf`: 1.199 → 1.835ms (1.530배)
- `pdfjs-src/test/pdfs/90ms_rksj_h_sample.pdf`: 5.472 → 7.804ms (1.426배)
- `pdfjs-src/test/pdfs/bitmap-refine.pdf`: 0.161 → 0.193ms (1.202배)
- `pdfjs-src/test/pdfs/bug1937438_af_from_latex.pdf`: 1.959 → 2.596ms (1.325배)

**메모리 회귀는 해소했다. 기존 5% 목표 및 파일별 회귀0을 모두 충족하지 못해 성능 합류는 여전히 보류한다.**
이번 후속은 감수의 메모리 결함 수정이며 이전 성능 보류를 승인으로 바꾸지 않는다.
전수 해시 비교는 출력 동일성의 근거이며 문서 내용 정확성의 독립 정답 검증은 아니다.
