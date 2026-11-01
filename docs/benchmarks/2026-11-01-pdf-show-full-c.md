# PDF 글자 연산 전체의 선택적 C 실행

## 구현과 범위

기준은 `d9683a9`다. 기존 `_cinterp`는 글자 연산마다 Python으로 돌아와
`_text_operator`와 `_show`를 호출했다. 이제 지원하는 가로 글꼴의 `Tj`, `TJ`,
작은따옴표·큰따옴표 연산은 해석기 안에서 디코딩 표 조회, 폭·행렬·위치 계산,
Fragment 생성까지 끝낸다. 숫자 TJ 원소와 줄 이동도 같은 루프에서 처리한다.

`_show_table.py`는 첫 사용 시 정확한 내장 구현과 자료형만 허용해 글꼴 표를
만든다. 단순 글꼴은 256칸 문자열 표, Identity CID는 코드 사전, 고정 길이
Encoding CMap은 코드 공간·코드→CID·폭·명시 폭을 유한한 표로 옮긴다.
표는 Python 콜백이 글꼴을 바꿀 수 있는 경계에서 무효화한다. 마크드 콘텐츠
경계와 부작용 없는 내장 폴백에서는 재사용한다.

| 디코더/글꼴 | 처리 | 근거/제한 |
| --- | --- | --- |
| Core14Decoder | C | 구현이 바이트별 결과의 연결이며 fallback이 알려진 구현이거나 undefined 보존 모드 |
| ToUnicodeCMap, 고정 1/2바이트 | C | mapping의 키 길이와 code_lengths가 폭 청크 길이와 같음 |
| Encoding CMap + reader의 decode_encoded | C | 정확한 closure 코드 identity 확인, 고정 1/2바이트 코드공간에 한정 |
| 잘린 CID, 코드 공간 밖/미지 CID | 해당 연산 Python | 전체 TJ를 상태 변경 전에 검사, 경고/부분 코드 의미 보존 |
| default_byte_decoder | Python | cp1252 실패 시 문자열 전체가 latin1으로 바뀌므로 바이트 결과 연결과 다름 |
| 세로, Type3/신뢰할 수 없는 비-Encoding 글꼴, 가변 코드 공간, CID 복원, 사용자 디코더·폭 | Python | 합성성/부작용 또는 글꼴 종류를 증명할 수 없는 입력 |
| 교체된 `_show`/`_text_operator`, extractor 하위 클래스 | 기존 경로 | 호출자가 교체한 동작을 우회하지 않음 |

`FontInfo`에는 subtype이 없고 TASK에서 `reader.py` 수정을 금지하므로 Type3를
직접 구분하는 새 필드를 넣지 않았다. 대신 비-Encoding 글꼴의
`link_metrics_reliable=False`를 모두 보수적으로 위임한다. 정상 글꼴 일부도
이 제한에 걸린다. `reader.py`, `fonts.py` 등 금지된 파일은 수정하지 않았다
(이 체크아웃의 글꼴 생성 코드는 별도 fonts.py가 아니라 reader.py에 있다).

Fragment dataclass의 공개 필드와 기본값은 그대로다. C가 같은 타입의 인스턴스와
독립적인 list 기본값을 만들고 `__dict__`를 채운다. 정수/실수 꼬리표, signed zero,
연산 순서, Python hypot/power, 위치 예산, 신뢰도, 렌더 스타일, marked stack을
보존한다. pow를 sqrt로 바꾸지 않는다. 새 런타임/빌드 의존성과 외부 엔진 코드는 없다.

## 검증 기록

| 검증 | 범위 | 결과 |
| --- | --- | --- |
| TDD | 네 글자 연산·위치 추적 4건, 고정 Encoding CMap 1건 | 구현 전 실패 확인 후 통과 |
| 최종 집중 회귀 | 글자·C 해석기·Form | 427 passed |
| 실물 기반 차등 | 공개 PDF 300개, 실물 피연산자 11,063개와 변형 100,000건 | 모든 Fragment vars 필드·타입·IEEE 비트·tm/tlm·예산·신뢰도 차이 0 |
| 출력 비교 | 공개 PDF 2,281개, Markdown·JSON·text·errors | 기준→가속 및 기준→비가속 각각 해시 차이 0, 실패 0 |
| 전체 테스트, 가속 | Xcode Python 3.9 | 6,718 passed, 36 skipped, 14 xfailed |
| 전체 테스트, 비가속 | DOCHAN_DISABLE_ACCEL=1 | 6,709 passed, 45 skipped, 14 xfailed |
| 엄격 컴파일 | Python 3.9 제한 API, C99, Wall/Wextra/Wpedantic/Werror | 통과 |
| ASan+UBSan | Homebrew Python 3.13 framework, 공개 250개/차등 100,000건 | 진단 0, 출력 차이 0 |
| ASan+UBSan API 오용 | 폭 dict 조회 중 Unicode 표 변경·GC, 10,000회 | 진단 0 |
| ruff | dochan scripts tests setup.py | 통과 |

TASK의 2,362개는 기존 기록에서 공개 2,281개와 내부 81개를 합한 수다.
이번에는 내부 자료를 포함하지 않았다. 공개 범위는 pdfjs-src 983,
press-pairs 375, holdout 217, holdout2 232, holdout3 233, holdout4 217,
lo-src 24개다. collect는 기존 probe_output_speed의 EXTENSIONS를 pdf로
제한하는 작업용 wrapper로 실행했다. 문서 원본은 복사하지 않았다.

실물 표본의 글자 연산은 313,937회이며 C 표로 준비할 수 있는 연산은
259,725회(82.73%)다. 변형 100,000건에서는 C 완료 46,738건, Python yield
53,262건, 페이지 Bailout 0건이었다. 변형은 바이트 역순·잘림·공백/영 바이트 추가,
행렬과 간격 변경, 렌더 모드 0–7, 추적 예산 0/7/200000을 포함한다.
따라서 변형 수용률을 실물 수용률로 해석하면 안 된다.

최초 전체 검사에서 `_show` monkeypatch를 C가 우회하는 Form 회귀 1건을
발견했다. 사용자 콜백 교체 시 기존 경로를 유지하도록 수정했으며 기존
테스트의 단언은 바꾸지 않았다. C 사전 조회의 재진입으로 문자열이 해제될
가능성을 검토해 폭 조회 전에 문자열 소유권을 확보했고 sanitizer로 검증했다.

## 재현

- 빌드: `DOCHAN_BUILD_ACCEL=1 /usr/bin/python3 setup.py build_ext --inplace --force`.
- 전체: `/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider`, 같은 명령에
  `DOCHAN_DISABLE_ACCEL=1`을 붙여 반복한다.
- 차등: `python -m scripts.probe_pdf_show_full <공개 pdfjs 루트> <공개 press-pairs 루트> --cases 100000`.
- 출력: `scripts.probe_output_speed`의 `collect(..., source=<기준 체크아웃>)`와
  현재 소스 수집 결과를 `python -m scripts.probe_output_speed compare <before> <after>`로 비교한다.
- 세부 원자료와 실행 wrapper는 작업 기록 디렉터리의 `hash-*.json`,
  `fuzz-verified.log`, `sanitizer-final.log`, `sanitizer-api.log`,
  `tests-*-final2.log`, `bench-final.log`에 있다. 로그에는 문서 텍스트를 저장하지 않는다.

## 한계

Linux·Windows 빌드는 수행하지 않았다. 이 검증은 기준 출력과의 동일성을
검사하며 PDF 원본의 시각적/의미적 정확성을 새로 보증하지 않는다.
성능은 동일 기기의 교대 측정이며 다른 사용자 작업의 부하까지 통제하지는 못한다.


## 속도: 공개 300개, 전·후·후·전·전·후

기준은 시작 커밋과 같은 HEAD의 기존 detached 기준 체크아웃이며 tracked 수정이
없음을 확인했다. 각 행은 별도 프로세스에서 같은 300개를 파싱한 합계다.
측정 중 이 작업의 테스트/코퍼스 검증/sanitizer를 함께 실행하지 않았다.

| Python | 변경 전 3회 (초) | 변경 후 3회 (초) | 중앙값 전→후 | 개선 |
| --- | --- | --- | --- | --- |
| Xcode 3.9.6 | 11.520 / 11.632 / 11.277 | 10.445 / 10.297 / 10.090 | 11.520 → 10.297 | 10.62% |
| 3.12.12 | 7.566 / 9.357 / 9.174 | 8.907 / 8.370 / 7.551 | 9.174 → 8.370 | 8.76% |

**15% 개선 목표는 미달**이다. 관측 중앙값은 두 환경 모두 5% 기준을 넘지만,
특히 3.12는 기준 회차가 7.566–9.357초로 흔들렸다. 독점 사용한 장비의
안정된 처리량으로 일반화하지 않는다. 커밋·푸시·합류는 수행하지 않았다.

처음에는 Fragment마다 새 combined dict를 만들었고 준비 표도 자주 버렸다.
마크드 콘텐츠 경계의 표 재사용, interned 필드 이름, 활성 글꼴 캐시,
Fragment의 공유 키 사전 복사로 비용을 줄였다. 초기 측정은 최종 결과와
구분해 작업 기록의 bench-initial에 보존했다.

## 글꼴 종류별 실물 수용률

차등 표본 300개(속도 표본과 다른 고정 난수 표본)의 연산 기회 집계다.

| 디코더 | C 표 | Python 전용 | C 표 비율 |
| --- | ---: | ---: | ---: |
| ToUnicodeCMap | 257,031 | 15,882 | 94.18% |
| Core14Decoder | 2,488 | 4 | 99.84% |
| decode_encoded | 206 | 0 | 100% |
| default_byte_decoder | 0 | 34,449 | 0% |
| lambda | 0 | 3,839 | 0% |
| CIDDecoder | 0 | 5 | 0% |
| drop / missing | 0 | 33 | 0% |

주요 미수용 원인은 비합성 default_byte_decoder, 신뢰도/코드 길이 제한에 걸린
ToUnicode, 식별되지 않은 lambda다. 잘린 raw는 표가 있는 글꼴이어도 위임될 수 있다.

## 남은 비용

동일 속도 표본 300개를 별도로 cProfile 실행했다. 아래 시간에는 프로파일러
오버헤드가 있어 위 파싱 합계와 합산하거나 직접 비교하지 않는다.

| 호출 | 변경 전 횟수 | 변경 후 횟수 | 누적 시간 전→후 (초) |
| --- | ---: | ---: | ---: |
| Interpreter.next | 232,022 | 83,507 | 0.871 → 2.226 |
| Python _text_operator | 191,901 | 43,386 | 4.396 → 0.964 |
| Python _show | 515,943 | 123,237 | 3.912 → 0.851 |
| Python _matmul | 1,352,012 | 323,517 | 0.364 → 0.088 |
| 표 준비 font_table | — | 19,871 | — → 0.848 |

next의 누적 시간 증가에는 이전에 Python에서 하던 글자 작업이 포함된다.
왕복은 64.0%, Python _show 호출은 76.1% 감소했다. 표 준비의 반복 비용과
미수용 글꼴 123,237회의 Python _show가 여전히 남는다.

`DOCHAN_PROFILE_SHOW`로만 켜지는 C 계측 빌드에서 같은 300개를 실행했다.
일반 빌드에는 타이머 호출이 없다. clock 기반 CPU 누적이며 스캐너·정리·표 준비는
아래 네 구간에 포함되지 않는다. 계측 자체 비용도 있으므로 병목 분해용이다.

| C 글자 루프 구간 | CPU 누적 (초) |
| --- | ---: |
| 디코딩 표·폭 조회, 문자열 연결 | 0.147 |
| 행렬·위치 예산·char_offsets | 0.181 |
| 공간 폭·유효 크기(power) | 0.140 |
| strip·Fragment 구성·최종 행렬 전진 | 0.451 |

C show 392,706회, 글리프 473,958개였다. Fragment 구간이 측정된 C 글자 비용의
약 49%다. 많은 연산이 한 글자뿐이므로 글자당 수치 루프만 빨라지는 효과가 작고,
인스턴스·독립 list 필드 생성과 표 재준비 비용이 상대적으로 크다.
15%를 달성하려면 안전한 글꼴 표 수명 연장이나 글꼴 종류 메타데이터가 개선 후보다.
금지 파일을 건드리거나 디코더 합성성/공개 Fragment 계약을 완화하지 않았다.


## 감수 후 수정 (TASK-FIX)

감수에서 확인한 Do/gs/미지원 글꼴 yield 뒤 표 전체 폐기와 쪽·Form별
표 재생성을 제거했다. FontInfo에 snapshot을 보관하며, 해석기의 주소 키
캐시 값에는 `(font, table)`을 넣어 글꼴 강참조도 유지한다. 전역 캐시는 없다.
고정 Encoding CMap은 희소 ToUnicode/폭 맵과 정규화된 CID/notdef 범위를
그대로 C에 넘긴다. 사용된 코드만 이진 검색하고 코드공간의 바이트별 상자를
검사한다. 65,536칸 전개와 `_space`/`_lookup`/`decode` Python 호출을
피하며 부모의 정상 CID가 자식 notdef보다 우선하는 규칙을 보존한다.
Core14는 기존 매핑과 상수 바이트 폴백을 재사용한다. 대형 맵의 정확 타입
검사는 제한 API C 순회로 옮기며 미지원 디코더는 폭 전체 검사 전에 위임한다.

활성 표 캐시 적중에서도 `glyph_yield_safe`를 갱신한다. 이 플래그에 의존하던
표 무효화 자체도 없어졌다. 기존 Python `_text_operator`는 `bool`을
`int`로 받아 TJ 간격을 계산한다. 따라서 감수의 "bool 항목 무시" 제안은
기준 출력 위치를 바꾸므로 채택하지 않고, 같은 수치를 C에서 처리하여
쪽 전체 Bailout만 제거했다.

초기 회귀 묶음 21건은 수정 전 별도 소스/바이너리에서 4건 실패했다.
최종 집중 묶음은 37건 모두 통과했다. 추가로 sparse 미전개와 Core14 디코더 호출 0 검사의
수정 전 실패 3건도 확인했다. gs/글꼴 전환/여러 쪽에서 생성 횟수, UniKS-UCS2-H
50회 gs와 Form 반복에서 문서 수명당 1회 생성, FontInfo 강참조 해제,
부모 CMap·notdef·바이트 상자, TJ bool의 전 필드·IEEE 비트 일치를 검사한다.

### 최종 검증과 판정

기준은 tracked 변경이 없는 `base-d9683a9`(HEAD `d9683a9`), 감수 전
구현 비교는 이 워크트리의 시작 HEAD `e44cd0e`다. 커밋·푸시·합류는 하지 않았다.

| 검사 | 결과 |
| --- | --- |
| 공개 PDF 4종 해시 | 2,281개, 기준→가속/비가속 모두 차이 0·실패 0 |
| 최종 전체 테스트, 가속 | 6,739 passed / 36 skipped / 14 xfailed |
| 최종 전체 테스트, 비가속 | 6,730 passed / 45 skipped / 14 xfailed |
| 집중 회귀 | 37 passed |
| 다중 연산 차등 | 20,000건 가속 해석 완료(페이지 Bailout 0), 전 필드·타입·IEEE 비트 차이 0 |
| 최종 소스 ASan+UBSan | 250 공개문서 기반 100,000 차등 사례, 추가 다중 연산 2,000건, API/참조 수명 10,000회 모두 통과·진단 0 |
| Xcode 3.9 빌드·제한 API 엄격 컴파일 | 통과 |
| ruff / diff whitespace | 통과 |
| 파일별 전체 변환 1.2배 이상 회귀 | 2 / 2,281 |
| 파일별 파싱 1.2배 이상 회귀 | 2 / 2,281 |

ASan의 100,000건 중 C 실행 45,573건, Python yield 54,427건이다.
모든 사례를 C 검증으로 과장하지 않는다. 추가 다중 연산 2,000건은 페이지 Bailout 없이 가속 해석을 완료했다.
이 수치는 모든 글자 연산이 C였다는 뜻은 아니며, 실제 연산 비율은 아래 별도 카운터로 제시한다. `detect_leaks=0`이므로 별도 누수 탐지 결과는 주장하지 않는다.
소스 6개 해시는 `fix-sanitizer-source.json`에 기록했고 이후 변경이 없음을 확인했다.
Linux/Windows는 검사하지 않았다.

### 파일별 속도: 2,281개 각각 2회 최솟값

최종 대조는 같은 프로세스·스레드에서 기준/수정 모듈 상태를 교체해 수행했다.
각 소스와 C 확장의 실제 경로, 새 전용 API 존재 여부를 매 전환 확인한다.
양쪽 파일당 예열 1회와 GC 후 전·후·후·전 또는 후·전·전·후로 각 2회
새 Dochan 객체를 변환하고 최솟값을 취한다. 소스 전환·예열·GC는 시간 밖이며,
각 측정 결과의 4종 해시도 기준과 대조해 총 2,281개 모두 일치했다.
전체 변환은 `Dochan` + Markdown + JSON + plain text이고, 파싱 시간도
별도로 기록했다. 두 모드의 실패는 0이다. 테스트·sanitizer·프로파일 작업을
모두 종료한 뒤 속도 파이프라인만 순차 실행했다. 호스트 외부 부하를 계측한
결과는 아니며, 타이밍 자료의 범위는 이 실행의 관측치다.

| 감수 지목 파일 | 기준 전체(초) | 수정 전체(초) | 비율 | 기준 파싱(초) | 수정 파싱(초) |
| --- | ---: | ---: | ---: | ---: | ---: |
| issue20232.pdf | 0.078021 | 0.078831 | 1.010 | 0.076734 | 0.077565 |
| issue840.pdf | 0.132665 | 0.129948 | 0.980 | 0.124884 | 0.122361 |
| freeculture.pdf | 2.391319 | 2.368019 | 0.990 | 2.265289 | 2.242171 |
| 156782883.pdf | 1.604474 | 1.360453 | 0.848 | 1.508085 | 1.266398 |
| 156782662.pdf | 0.472684 | 0.449672 | 0.951 | 0.457356 | 0.434493 |
| 156782137.pdf | 1.033592 | 0.929918 | 0.900 | 0.949948 | 0.847085 |
| 156783095.pdf | 1.270760 | 1.094026 | 0.861 | 1.091570 | 0.915768 |

1.2배 이상 느린 전체 변환 파일 목록: IdentityToUnicodeMap_charCodeOf.pdf, mesh_shading_empty.pdf
파싱 시간 기준의 같은 목록: IdentityToUnicodeMap_charCodeOf.pdf, mesh_shading_empty.pdf

첫 캐시 수정만 적용한 전수 검사에서는 66개 회귀가 남았다. 해당 프로파일에서
Core14의 256회 디코더 호출, 대형 폭/ToUnicode 맵의 Python 타입 검사,
최초 Encoding 코드공간 전개를 확인해 추가 수정한 뒤 위 전수를 다시 측정했다.
첫 검사 자료는 `first-fix-filewise.json`이며 최종 자료로 덮어 해석하지 않는다.
최종 소스의 예열 없는 전수에서는 1ms 미만 2개(`issue11555.pdf`,
`issue5567.pdf`)가 1.474/1.241배로 관측됐다. 같은 소스를 파일별 20회
교대 재검사하면 모든 회차가 1.07배 이하였고 중앙값은 각각 약 3%/0%
차이였다. 이 관측을 삭제하지 않고 `fix-filewise-unwarmed.json`과
`fix-repeat-two.json`에 보존했다. 분리 프로세스에 동일 예열·GC를 적용한 전수에서도 다른 3개
(`issue6652.pdf`, `issue6769.pdf`, `js-colors.pdf`)가 1.2배를 넘었다.
이 기록은 `fix-filewise.json`에 보존했다.

위 단일 프로세스 최종 전수에서도 아래 2개가 남아 **요청한 원시 계측
회귀 0 조건은 충족하지 못했다. 합류 판정은 보류한다.** 두 파일을 각각
20회 교대 확인하면 모든 비율이 1.10 미만이며 중앙값 차이는 약 3%/0%다
(`fix-repeat-final.json`). 프로파일에서도 Identity 파일의 차이는 약 3%였다.
반복 관측은 큰 코드 회귀를 뒷받침하지 않지만, 이를 근거로 전수의 초과
기록을 삭제하거나 회귀 0이라고 보고하지 않는다.

| 최종 초과 파일 | 전체 비율 | 파싱 비율 | 20회 재검사 비율 범위 |
| --- | ---: | ---: | --- |
| IdentityToUnicodeMap_charCodeOf.pdf | 1.292 | 1.292 | 1.000–1.072 |
| mesh_shading_empty.pdf | 1.203 | 1.207 | 0.921–1.092 |

1ms 미만 변환의 재현되지 않는 타이밍 변동이 남았으며, 외부 부하가 통제된
독립 계측 환경에서 원시 2회 조건을 재검증해야 한다. 이전 전수와 새 전수의
값을 섞어 최솟값을 선택하지 않았다.

### 300개 교대 3회

동일 `sample-pdf-300.json`, 순서 전·후·후·전·전·후. 합계 중앙값이다.

| Python | 전 3회(초) | 후 3회(초) | 중앙값 전→후(초) | 개선 |
| --- | --- | --- | --- | ---: |
| 3.9.6 | 10.720410 / 10.729770 / 10.710799 | 9.223524 / 9.247448 / 9.402582 | 10.720410 → 9.247448 | 13.74% |
| 3.12.12 | 6.745323 / 6.720462 / 6.778292 | 6.158901 / 6.205042 / 6.134039 | 6.745323 → 6.158901 | 8.69% |

15% 목표: 39: 미달, 312: 미달.

### 합성 재현과 실제 카운터

`UniKS-UCS2-H` + ToUnicode, gs 사이 Tj 50회, 폭 65,536항목이다.
표 생성 횟수 회귀는 시간이 아닌 호출 수로 검증한다. 같은 FontInfo를
2쪽과 100개 Form 호출에 재사용하는 테스트에서도 `font_table`은 1회다.

```text
encoding N 50 size 65536 sep b'/GS1 gs' frags 50 sec 3.221
encoding N 50 size 65536 sep b'/GS1 gs' frags 50 sec 0.001
encoding N 50 size 65536 sep b'/GS1 gs' frags 50 sec 0.001
```

위 출력 순서는 감수 전 `e44cd0e`, 최종 수정, 기준 `d9683a9`다.

| 300개 표본 계측 | 감수 전 e44cd0e | 최종 수정 |
| --- | ---: | ---: |
| font_table 실제 호출 | 19,871 | 1,445 |
| font_table cProfile 누적(초) | 0.900795 | 0.026121 |
| cached_font_table 호출 | 해당 없음 | 3,687 |

C 연산 완료 카운터는 **148,515 / 191,901 = 77.39%**다.
Python yield 43,386회, C raw show 392,706회, glyph 473,958개다.
표가 존재하는 비율에서 추정하지 않고 `show_operator`의 실제 반환 결과를
계측했다. 일반 빌드에는 카운터·타이머 비용이 없다.

### 원자료

- `fix-inprocess.json`, `fix-inprocess-regressions.json`: 최종 파일별 두 번의 전체 시간과 파싱 최솟값, 전후 비율.
- `fix-filewise*.json`, `fix-repeat-two.json`, `fix-repeat-final.json`: 분리 프로세스 전수 및 sub-ms 이상치의 반복 진단.
- `fix-bench-results.json`, `fix-bench.log`: Python 두 버전의 교대 12회.
- `fix-hash-native.json`, `fix-hash-python.json`, 각 compare 로그: 4종 출력 해시.
- `fix-tdd-all-red.log`, `fix-sparse-red.log`, `fix-core14-red.log`: 결함 경로에서의 실패 증거.
- `fix-sequences.log`, `fix-sanitizer*.log`, `fix-sanitizer-source.json`: 차등·최종 소스 sanitizer.
- `fix-tests-*-final.log`, `fix-profile-summary.json`, `fix-profile-native.json`: 테스트·호출 수·실제 C 카운터.

모든 원자료는 `.codex-work/` 아래에 있다. 공개 코퍼스만 사용했다.
금지 파일, README, CHANGELOG는 수정하지 않았고 새 의존성은 없다.
