# HWPX XML 캐시 차트 구현·검증

검증일: 2026-09-19. 기준 사양: [chart-spec.md](chart-spec.md).
구현: `dochan/hwpx/charts.py`. 검증: `tests/test_hwpx_charts.py`.
이 문서는 XML 해석 모듈의 계약을 기록한다. ZIP/API 연결 검증은
[chart-integration-validation.md](chart-integration-validation.md)에 별도로 기록한다.

## 인터페이스·출력 계약

~~~python
from dochan.hwpx.charts import parse_chart_xml

elements, warnings = parse_chart_xml(data)
# parse_chart_xml(data: bytes) -> tuple[list, list[str]]
~~~

입력은 ZIP에서 이미 읽은 **차트 파트의 XML bytes**다. 이 모듈은 파일·ZIP·
네트워크를 열지 않는다. 호출자가 차트 참조 해석, 제한된 ZIP 읽기, 본문 위치,
switch/OLE 대체 분기 선택, 경고 전달을 담당한다. 현재 `parser.py`가 이 호출자 역할을 한다.

1. 명시적 차트 제목이 있으면 Paragraph(runs=[TextRun(...)]) 하나를 먼저 반환한다.
   c:title/c:tx/c:rich의 DrawingML 텍스트·줄바꿈·문단 또는 문자열 캐시를 읽는다.
   c:title/c:txPr, 축 제목, 계열명으로 차트 제목을 만들어 내지 않는다.
2. 계열마다 독립된 Table 하나를 반환한다. 서로 다른 범주나 X 값을 가진 계열을
   한 격자에 합치지 않는다. 계열명은 Table.caption의 Paragraph/TextRun,
   caption_side="TOP"에 둔다.
3. 첫 행은 범주형 ["범주", "값"], 산점도 ["X", "Y"]다.
   각 Cell에 row/col과 텍스트 문단을 설정한다. 별도 차트 모델은 추가하지 않는다.
4. 계열은 c:order 숫자 오름차순이다. 동률은 XML 순서를 유지한다.
   누락·잘못된 order는 해당 계열의 0기준 XML 위치를 정렬 키로 쓰고 경고한다.
   c:idx는 정렬 키나 격자 크기로 사용하지 않는다.
5. 행은 c:pt/@idx의 0기준 순서다. ptCount와 관찰한 최대 idx로 길이를 정한다.
   범주/값 및 X/Y를 **같은 idx끼리** 대응시키며 X 값 자체로 정렬하지 않는다.
6. 계열명이 없거나 빈 문자열이면 표시 순서 기준 "계열 N"을 생성하고
   missing_name 경고를 반환한다. 자동 차트 제목은 생성하지 않는다.

## 데이터 보존·오류 처리

| 입력 상태 | 반환 정책 |
| --- | --- |
| 숫자 0, -0.00, 2.00, 1e3 | 유효한 유한 십진수인지 검사하고 원래 문자열 그대로 반환 |
| 명시적 빈 c:v | 빈 셀 유지; 0으로 바꾸지 않음 |
| 누락 idx·희소 캐시 | 해당 위치를 빈 셀로 남기고 sparse_cache 경고 |
| 서로 다른 캐시 길이 | 긴 쪽 길이까지 빈 셀 보존, length_mismatch 경고 |
| 중복 idx | 첫 값을 유지하고 duplicate_index 경고 |
| 누락·음수·잘못된 idx | 해당 포인트 제외, invalid_index 경고 |
| 잘못되거나 없는 ptCount | 관찰한 idx로 길이 도출, invalid_count 경고 |
| ptCount와 포인트 수/최대 idx 불일치 | 관찰 데이터 보존, count_mismatch 경고 |
| 숫자 변환 실패·NaN·INF | 빈 셀과 invalid_number 경고; 정상 숫자로 처리하지 않음 |
| 필수 cat/val 또는 xVal/yVal 캐시 없음 | 해당 계열 표 생략, missing_cache 경고 |
| 다단계 범주·문자열 Y 값·중복 데이터 소스 | 해당 계열 표 생략, unsupported_cache/ambiguous_cache 경고 |
| 양쪽 캐시의 길이가 0 | 계열 표 생략, empty_series 경고 |
| 혼합/미지원 차트 유형 | 명시적 제목만 보존하고 mixed_chart/unsupported_type 경고 |
| XML 오류·DTD·예산 초과 | 요소 전체를 비우고 해당 경고 반환 |

문자열은 XML 파서의 표준 개행·엔티티 정규화를 거친 텍스트다.
숫자 표시 형식이나 날짜 일련번호를 적용·변환하지 않는다.
c:f 수식·관계·원본 워크북·OLE는 평가하거나 따라가지 않으며 출력 모델에도
별도로 담지 않는다. 반환 수치는 **저장된 캐시 또는 literal**이며 원본 시트의 최신 값이 아니다.
축·범례 레이아웃·서식·색상·렌더링도 반환하지 않는다.

경고는 별도 list[str]이고 [chart:code]로 시작한다. 같은 계열/캐시의
같은 문제는 중복 경고하지 않는다. 원문 수식·숫자·XML 오류 전문은 경고에 넣지 않는다.
일부 계열에 캐시가 없으면 나머지 유효한 계열은 반환한다. 자원 제한을 초과하면
앞서 만든 제목·표까지 반환하지 않아 잘린 결과를 완전한 차트처럼 전달하지 않는다.

## 지원·검증 범위

namespace는 http://schemas.openxmlformats.org/drawingml/2006/chart,
제목 DrawingML은 http://schemas.openxmlformats.org/drawingml/2006/main이다.
접두사는 바뀌어도 되지만 URI가 다른 동명 요소는 차트로 해석하지 않는다.
Strict OOXML URI, bubble/stock/surface, 다단계 범주, 한 plotArea의 여러 차트
그룹 및 보조 축의 시각적 의미는 지원하지 않는다.

| 범위 | 구현 | 검증 수준 |
| --- | --- | --- |
| pieChart, lineChart의 strRef/strCache·numRef/numCache | 제목 유무, 계열명, 범주/값, 다중계열 표 | 아래 공개 실물 2유형 + 합성 테스트 |
| pie3DChart, doughnutChart, line3DChart, barChart, bar3DChart, areaChart, area3DChart, radarChart | 동일한 cat/val 캐시 추출 | 합성 XML만 검증; 3D/시각적 재현 아님 |
| scatterChart | numRef/numCache 또는 numLit의 xVal/yVal을 계열별 idx로 결합 | 합성 XML의 다중계열·비단조 X·0·희소·다른 길이 검증 |
| strLit, numLit, 숫자 범주 | 문자·숫자·날짜 일련번호 원문 유지 | 합성 XML만 검증 |
| 명시적 rich-text/문자열 캐시 제목 | run/줄바꿈/문단 텍스트 추출 | 합성 XML만 검증; 실물 두 표본에는 명시적 제목 없음 |
| 빈값·누락·중복·잘못된 값·외부 참조 | 위 정책에 따른 출력과 경고 | 합성 XML만 검증 |

실물 검증을 하지 않은 범위를 README의 지원 완료 표시로 승격하지 않는다.
전체 XSD 적합성, 한글 UI 렌더링 동일성, 워크북 재계산 결과를 검증한 것은 아니다.

## 보안·자원 예산

매 호출마다 아래 파서를 새로 만든다.

~~~python
lxml.etree.XMLParser(resolve_entities=False, no_network=True,
                    load_dtd=False, huge_tree=False, recover=False)
~~~

DTD 선언이 있으면 결과를 거부하며, XInclude나 외부 워크북을 실행·조회하지 않는다.

| 예산 상수 | 기본값 | 검사 위치 |
| --- | ---: | --- |
| MAX_XML_BYTES | 4,194,304 bytes (4 MiB) | XML 파싱 전 |
| MAX_SERIES | 128 | 계열 표 처리 전 |
| MAX_POINTS | 10,000 | 캐시별 ptCount·실제 pt 수·최대 idx+1 |
| MAX_TOTAL_POINTS | 50,000 | 제목/계열명 포함 실제 pt 수 누적; 중복·잘못된 pt도 계산 |
| MAX_GRID_CELLS | 50,000 | 모든 표의 헤더 포함 누적 셀 수; 각 표의 Cell 생성 전 |

idx/ptCount는 긴 정수로 변환하거나 range/격자를 만들기 전에 문자열 길이·값으로
상한을 검사한다. 예산은 호출마다 초기화한다. 경계값 허용, 누적 예산,
거대한 선언값, 중복 포인트, Cell 생성 전 거부를 테스트했다.
사용자 정의 외부 엔티티(local/HTTPS)와 내부 엔티티의 resolver 호출이 없음을
검사했고, UTF-16 외부 DTD와 과도한 XML 깊이도 거부함을 확인했다.
외부 workbook 수식과 externalData가 있어도 캐시만 읽으며 socket 호출은 0회였다.

## 공개 실물 XML의 독립 수치 대조

원본 공개 경로·커밋·라이선스 조사와 전체 gold는 [chart-spec.md](chart-spec.md)에 있다.
이번 실행은 네트워크 없이 로컬 corpus의 ZIP 및 차트 파트 SHA-256을 확인했다.

| 표본 | 유형 | 계열/포인트 | 반환 값 (계열 순서) |
| --- | --- | --- | --- |
| corpus/hwp-public/hwpx/2차원원형.hwpx | pieChart | 판매 / 4 | 10, 3.5, 1.5, 1.2 |
| corpus/hwp-public/hwpx/꺽은선형.hwpx | lineChart | 계열 1, 2, 3 / 각 4 | 4.3, 2.5, 3.5, 4.5 / 2.4, 4.4, 1.8, 2.8 / 2, 2, 3, 5 |

| 표본 | ZIP SHA-256 | Chart/chart1.xml SHA-256 |
| --- | --- | --- |
| 원형 | ce4304b8aa4fba79d493647d6fb1204b527bc2aac50c55a94bea9ec67f8994a8 | d97cfe9edf27f2b41116ac9d6d7102554743972934ebfa098136d688eddd3a26 |
| 꺾은선 | a8a4449c3641c107aadb6e597dbb780b5b7ae3dc50d4a144a2e87075af2fc398 | 9c869af6b69e6eeba07a1d81e8d15f6ba701367def9baac3c21cb6ab1c0cfb14 |

테스트의 독립 oracle은 zipfile과 표준 라이브러리 xml.etree.ElementTree만 사용한다.
차트 QName/유형, 명시적 제목 부재, c:order, 계열명, 범주, ptCount=4,
idx=0..3과 모든 값을 XML에서 직접 도출한다. 구현의 helper/출력을 정답 생성에
사용하지 않는다. 사양에서 전사한 고정 계열명·수치와도 비교한 뒤, 모든 표 셀을
독립 oracle과 대조한다. **두 표본의 4계열, 숫자 16개 및 범주 16개가 일치했고 경고는 없었다.**

corpus가 없는 환경에서는 실물 테스트 2건만 명시적으로 skip한다.
skip은 실물 검증 성공이 아니다. 이번 로컬 검증에서는 두 건 모두 실행·통과했다.

## 초기 TDD 기록과 재검증 명령

초기 개발 당시 Python 3.9.6, pytest 8.4.2의 기록이다.
아래 단계별 수치는 현재 전체 테스트 수와 구분한다.

1. 구현 파일 생성 전 아래 테스트를 먼저 실행했다.
   **3 failed, 34 deselected**: 정렬/0/문자열 보존 1건과 공개 실물 2건 모두
   "ModuleNotFoundError: No module named 'dochan.hwpx.charts'"로 실패했다.
   실물 테스트는 독립 XML gold·해시 검사 이후 신규 모듈 호출 지점에서 실패했다.

   ~~~sh
   python -m pytest tests/test_hwpx_charts.py -q -k 'cached_series_order or public_corpus' --tb=short
   ~~~

2. 독립 모듈 구현 후 최초 차트 테스트 **37 passed**.
   경계·출력기 호환성 검증을 추가한 최종 차트 테스트 수는 **53개**다.

3. 최종 관련 회귀 실행: **101 passed**, 실패/skip 0.
   차트 53개 + 기존 HWPX reader/ZIP guard/회귀 48개다.

   ~~~sh
   python -m pytest tests/test_hwpx_charts.py tests/test_hwpx_reader.py tests/test_hwpx_zip_bomb_guard.py tests/test_hwpx_regressions.py -q --tb=short
   ruff check dochan/hwpx/charts.py tests/test_hwpx_charts.py
   ~~~

   Ruff: **All checks passed**. 기존 Markdown/JSON/plain-text 출력기에서 계열
   캡션·빈 셀·0을 보존하는 테스트도 포함한다. 전체 저장소 실행 결과는 진행 기록,
   parser 연결의 근거는 별도 통합 검증 문서에서 확인한다.

현재 체크아웃의 재실행 결과는 [implementation-progress.md](implementation-progress.md)의
검증 표에 기록한다. corpus가 없는 환경의 skip은 실물 검증 통과가 아니다.
