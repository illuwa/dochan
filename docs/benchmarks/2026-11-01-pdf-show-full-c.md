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
