# PDF 내용 스트림 스캐너의 선택적 C 가속 모듈

2026-10-06. `docs/benchmarks/2026-10-04-speed-pdf-accelerator-feasibility.md` 의 조사에서 가장 좁고 효과가 큰 후보였던
내용 스트림 스캐너를 제품 코드로 옮겼다. 기본 배포물은 바뀌지 않는다. 가속 모듈은 빌드를 명시적으로 켠 경우에만 생기고,
없거나 로드에 실패하면 지금까지의 순수 Python 스캐너가 그대로 동작한다. 이 문서에 README 기능 칸은 배정되지 않았다.

## 무엇을 만들었나

- `dochan/pdf/_cscan.c`: 손으로 쓴 C 확장(`dochan.pdf._cscan.Scanner`). Cython·mypyc 같은 코드 생성기와 그 산출물을 쓰지
  않았고, 다른 PDF 엔진의 코드를 보거나 옮기지 않았다. 근거는 ISO 32000-1 §7.2·§7.3 과 이 저장소의 `ContentScanner`·
  `PDFLexer` 계약뿐이다. CPython 제한 API(`Py_LIMITED_API 0x03090000`)만 써서 `_cscan.abi3.so` 하나가 3.9 이상에서 로드된다.
- 공백·주석 건너뛰기, 일반 토큰 읽기, 숫자 토큰 변환, 간접 참조 예비 판별을 C 반복문으로 한다. 문자열·16진 문자열·이름·
  배열·사전, 참조일 수 있는 숫자, 변환에 실패한 숫자 토큰은 지금처럼 `PDFLexer.parse_object()` 에 맡긴다.
- 숫자는 출력 동일성이 우선이다. 부호 하나와 ASCII 숫자 18자리 이하 정수, 점이 하나뿐인 64바이트 이하 실수
  (`PyOS_string_to_double`, Python `float()` 가 쓰는 같은 함수)만 C 에서 바꾸고, 밑줄·지수·긴 수는 Python `int`/`float` 를 부른다.
- `dochan/pdf/content.py`: 기존 클래스는 `_PythonContentScanner` 로 남고 `ContentScanner` 가 가속 모듈 또는 순수 Python 을
  가리킨다. `CONTENT_SCANNER_BACKEND` 가 `"c"` 또는 `"python"` 이다. `DOCHAN_DISABLE_ACCEL=1` 이면 항상 순수 Python 이고,
  `ImportError` 만 조용히 폴백한다(다른 예외는 전파).
- `setup.py`: `DOCHAN_BUILD_ACCEL=1` 일 때만 `optional=True` 확장을 빌드한다. 그 변수가 없으면 `python -m build` 결과는
  전과 같은 `py3-none-any` 휠이고 C 소스는 sdist 에만 들어간다. 컴파일에 실패해도 빌드는 성공하고 순수 Python 으로 돈다.

```bash
DOCHAN_BUILD_ACCEL=1 python setup.py build_ext --inplace   # 저장소에서 바로 쓰기
DOCHAN_BUILD_ACCEL=1 python -m build --wheel               # cp39-abi3 플랫폼 휠
```

## 출력 동일성

| 검증 | 범위 | 결과 |
| --- | --- | --- |
| 전수 변환 대조 | PDF 2,362건(공개 pdf.js 983·정책브리핑 보도자료 1,274·LibreOffice 24, 내부 81) | Markdown·JSON·일반 텍스트·오류 목록 해시가 순수 Python 과 모두 같다. 교대 6회 실행 전부 동일 |
| 실물 스트림 차등 퍼징 | 위 PDF 260건에서 뽑은 내용 스트림 778개(44MB)의 조각과 변형(바이트 치환·절단·토큰 삽입·이어 붙이기), `pos` 임의 변경 포함 | 150초 동안 458,422건, 이벤트 종류·값(실수는 비트 단위)·`pos`·예외 타입 불일치 0건 |
| 합성 차등 테스트 | `tests/test_pdf_cscan.py`: 시드 고정 바이트·토큰 조합 20,000개, 위치 변경 1,000개, 숫자 8,000개, 경계 사례 | 통과 |
| 전체 테스트 | 가속 켬 / `DOCHAN_DISABLE_ACCEL=1` | 각각 5,887 passed, 36 skipped, 14 xfailed |

퍼징은 `python -m scripts.probe_pdf_cscan_fuzz <초> <PDF 경로 JSON>` 으로 다시 돌릴 수 있다. 이 표는 기존 출력과의
동일성 검증이며 변환 정확도를 따로 검증한 것은 아니다.

## 속도

Apple M5 Pro, macOS, Xcode Python 3.9.6, 작업자 8개로 PDF 2,362건을 순수 Python·C·C·순수 Python·순수 Python·C 순서로
여섯 번 변환했다. 문서별 파싱 시간을 더한 값이다.

| 백엔드 | 파싱 합계 1회 / 2회 / 3회 (초) | 중앙값 |
| --- | --- | ---: |
| 순수 Python | 314.7 / 298.4 / 295.0 | 298.4 |
| C 스캐너 | 217.9 / 210.6 / 196.1 | 210.6 |

중앙값 기준 1.42배다. Markdown·JSON·일반 텍스트 출력까지 더하면 304.5 → 216.9초(1.40배)다. 타당성 조사의 Cython 시제품은
공개 300개·Python 3.12 에서 1.65배였다. 표본과 인터프리터가 달라 두 수치를 직접 비교하지 않는다.

## 메모리 안전

- 스캔 루프의 모든 색인은 0 이상이고 버퍼 길이 미만임을 확인한 뒤에만 읽는다. 호출자가 바꾸는 `pos` 는 비교에만 쓰고
  포인터 색인으로 쓰지 않는다(아주 큰 정수는 포화시킨다). 자체 `malloc` 이 없고 객체 할당은 CPython 에 맡긴다.
- 스캐너가 `bytes` 의 강한 참조를 들고, `next()` 는 Python 으로 들어가는 호출 동안 그 참조를 하나 더 든다.
- 스캔 루프 함수들을 그대로 옮긴 독립 C 하네스를 AddressSanitizer·UndefinedBehaviorSanitizer 로 돌렸다: 입력 200,000개,
  길이 0–512, 모든 시작 위치(-2 ~ 길이+2, 극단값 포함), 버퍼 끝 뒤를 poison — 발견 0건.
- 확장 모듈 전체를 sanitizer 로 돌리지는 못했다. macOS 가 시스템 Python 에 sanitizer 런타임을 선로드하는 것을 막는다
  (`Sanitizer load violates platform policy`). 참조 계수와 순환 해제는 Python 테스트(반복 재초기화 뒤 참조 수, GC 수거)로만 확인했다.

## 확인하지 못한 것과 남은 결정

- macOS arm64 의 Python 3.9·3.11 에서만 빌드·로드했다. Linux·Windows, 다른 CPU 는 미검증이다.
- 릴리스 워크플로는 바꾸지 않았다. 가속 휠을 PyPI 에 올리려면 운영체제·CPU 별 빌드 행렬(예: cibuildwheel)이 필요하고,
  그 전에 Linux 에서 sanitizer 로 확장 전체를 돌리는 CI 작업을 두는 것이 맞다. 올리지 않더라도 소스 설치에서
  `DOCHAN_BUILD_ACCEL=1` 로 직접 빌드해 쓸 수 있다.
- 남은 PDF 시간의 대부분은 해석기 루프의 연산자 분기, 경로 수집, 줄·문단 조립이다. 이 모듈은 스캐너만 옮겼다.
