# HWPX 차트 ZIP/API 통합 검증

검증일: 2026-09-19. 구현: `dochan/hwpx/parser.py`와 `dochan/hwpx/charts.py`.
검증 진입점: `tests/test_hwpx_chart_integration.py`.
API 연결, 자원 제한, revision/assets 호환성과 공개 실물 gold 비교를 기록한다.

## 연결 계약

- `Dochan(path, include_assets=..., revision_mode=...).doc`의 기존 HWPX 경로에서
  `hp:chart@chartIDRef`를 읽고 `charts.parse_chart_xml(bytes)`를 호출한다.
- 실제 표본처럼 ZIP 루트 기준 `Chart/...xml`의 정확한 경로만 허용한다.
  manifest ID 추측, 확장자 보충, 이름 유사 매칭, URL 접근은 하지 않는다.
  `..`, `.`, 빈 경로 구간, 절대 경로, 역슬래시, URI 구분자·percent 인코딩,
  query/fragment, 제어문자/공백, 비정규 ZIP 이름 별칭을 거부한다.
- `http://www.hancom.co.kr/hwpml/2016/ooxmlchart` switch 분기를 선택한다.
  선택한 분기만 처리하고 default OLE를 중복 출력하지 않는다.
  미지원 유형이나 손상 XML도 그 위치의 errors에 명시하며 OLE로 조용히 덮지 않는다.
- 본문 텍스트를 차트 앞에서 flush하고 명시적 제목 Paragraph, 계열별 Table,
  뒤 텍스트 순서로 넣는다. 표 셀·도형·머리글·ctrl의 차트도 같은 경로를 쓴다.
  선택된 차트가 처리하지 못하는 컨테이너에 있으면 `unsupported_placement`를 남긴다.
- ZIP이 열려 있는 동안만 part를 읽는다. 캐시는 **bytes와 정수 개수**만 보관한다.
  같은 part의 압축 해제는 한 번이며, 각 배치마다 모델은 새로 생성한다.
  따라서 서로 다른 위치·호출의 Table/Cell/Paragraph/TextRun이 공유되지 않는다.
  성공/실패 모두 finally에서 ZIP 참조·캐시·section 노드 참조를 해제한다.
- XML 모듈의 경고를 part 경로와 차트 순번을 붙여 `Document.errors`로 전달한다.
  참조 오류, 누락, CRC/압축 스트림 오류, byte/ratio 제한도 별도 chart 코드로 기록한다.
  오류에 raw XML·수식·값·예외 전문은 담지 않는다.

## 제한과 회귀 호환성

| 제한 | 값 | 적용 |
| --- | ---: | --- |
| 차트 part XML | 4 MiB | charts.MAX_XML_BYTES, ZIP 메타데이터 및 실제 read 결과 |
| ZIP 압축률 | 2,000배 | 기존 MAX_COMPRESSION_RATIO 유지, 읽기 전 검사 |
| 문서 차트 배치 | 256 | 같은 part의 반복 배치도 포함 |
| 문서 차트 XML 처리량 | 32 MiB | 같은 part를 다시 쓰는 경우에도 누적 |
| 문서 차트 series | 1,024 | XML의 c:ser 원소 누적 |
| 문서 차트 points | 200,000 | 제목/이름 캐시 및 잘못된·중복 c:pt도 포함 |
| 문서 차트 출력 셀 | 200,000 | 헤더 포함, 모든 계열·섹션 누적 |
| 문서 일반 표+차트 셀 | 200,000 | 실제 셀·격자 채움·중첩 셀과 차트 합산 |

원래 패키지 총량/엔트리/중복 part 가드는 유지한다. 차트의 ZIP 읽기는
`stream.read(MAX_XML_BYTES + 1)`로 제한한다. series/points는 안전한 XML
사전 검사 후 모델 생성 전에 문서 예산을 확인한다. 코어의 part별
128 series, 캐시당 10,000 points, 총 50,000 points 및 50,000 cells 제한도 유지한다.

문서 셀 예산은 코어가 반환한 표의 실제 셀 수로 확인하고 초과 차트의 제목·표
전체를 제외한다. 따라서 **문서에 보관되는 결과 외에, 검사 시 한 차트 분량의
임시 결과(최대 50,000셀)가 생성될 수 있다.** immutable XML 캐시는 문서 XML
처리량 제한 안에 있다. RSS 최대치를 측정한 결과는 아니다.

일반 표의 기존 격자/실제 셀 예산과 별도로 실제 셀 수를 세어, 차트가 들어간 뒤
일반 표나 폴백 표가 공동 셀 예산을 우회하지 못하게 했다. 일반 표가 먼저 예산을
사용한 경우 차트가 거부된다. 차트가 없는 문서의 기존 폴백 정책은 유지한다.

revision은 기존 **텍스트만 투영**하는 정책을 유지한다. 차트를 가로지르는 변경
범위는 기존 opaque object와 동일하게 보존하고 `revision partial [object]`를 낸다.
이를 위해 revision 검사 동안만 hp:chart를 opaque hp:ole로 취급한 뒤 finally에서
원래 QName을 복원한다. 차트 밖의 확정된 텍스트 변경은 정상 투영한다.
이미지 include_assets 설정과 무관하게 차트 XML은 처리한다.

## 공개 실물과 독립 XML gold

oracle은 표준 라이브러리 `zipfile`과 `xml.etree.ElementTree`만 사용한다.
본문의 실제 chartIDRef 순서, XML 유형, c:order, 계열명, c:ptCount,
idx별 범주/수치 또는 X/Y를 직접 읽는다. parser/charts helper나 Dochan 출력으로
정답을 생성하지 않는다. 원형·꺾은선은 사양에 전사된 고정 수치와도 비교한다.
최종 비교 대상은 **Dochan API로 읽은 문서의 차트 Table 전체 셀과 계열 캡션**이다.

| 공개 실물 | 참조 차트 | gold 일치 계열 | 데이터 행 | 차트 출력 셀 | 오류 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2차원원형.hwpx | 1 | 1 | 4 | 10 | 0 |
| 꺽은선형.hwpx | 1 | 3 | 12 | 30 | 0 |
| 14_chart.hwpx | 24 | 44 | 232 | 552 | 미지원 유형 3 |
| charts.hwpx | 12 | 25 | 98 | 246 | 미지원 유형 2 |
| 합계 | 38 | 73 | 346 | 838 | 미지원 차트 5 |

38개 중 지원 차트 33개의 모든 계열 데이터를 비교했다. `14_chart.hwpx`에는
별도로 일반 표 4개, 107셀이 있어 총 표 48개/659셀이 반환된다. 이것을 차트
gold에 섞지 않는다. 차트 표는 TOP 계열 캡션으로 식별하고 목록 전체를 비교한다.

원형 수치: `10, 3.5, 1.5, 1.2`.
꺾은선 수치: `4.3, 2.5, 3.5, 4.5` / `2.4, 4.4, 1.8, 2.8` / `2, 2, 3, 5`.

| 파일 | ZIP SHA-256 |
| --- | --- |
| 2차원원형.hwpx | ce4304b8aa4fba79d493647d6fb1204b527bc2aac50c55a94bea9ec67f8994a8 |
| 꺽은선형.hwpx | a8a4449c3641c107aadb6e597dbb780b5b7ae3dc50d4a144a2e87075af2fc398 |
| 14_chart.hwpx | bf630bc7c87ed48b267c496059846392125eea59ebe3dccaccda815b53cd4aca |
| charts.hwpx | 9e5b3ff8f879ea207681b70f2ccbaf330c942e6cc1e77bf16d83363524792a56 |

원형·꺾은선 원본 경로·파트 해시는 [chart-spec.md](chart-spec.md)에 있다.
나머지 두 공개 표본은 로컬 `corpus/hwp-public/SOURCES.json`에 기록된
[HwpForge 14_chart.hwpx](https://github.com/ai-screams/HwpForge/blob/main/examples/showcase/features/feature_isolation/14_chart.hwpx),
[HwpForge charts.hwpx](https://github.com/ai-screams/HwpForge/blob/main/crates/hwpforge-smithy-hwpx/tests/fixtures/charts.hwpx)다.
이번 실행은 다운로드를 다시 하지 않았으며, main URL의 현재 내용 대신 위 로컬
SHA-256으로 검증 대상을 고정했다. 원본 바이너리는 추가/수정하지 않았다.
두 표본의 `Apache-2.0` 표기는 **수집 인덱스의 기록**이다. 이 통합 검증에서
해당 저장소의 라이선스 원문이나 개별 표본의 권리까지 직접 확인한 것은 아니다.
공개 접근 가능성·해시 일치를 재배포 권리 또는 저작권 보증으로 해석하지 않는다.

실물 미지원 진단도 별도 검증했다.

- 14_chart: chart14.xml=ofPieChart, chart17.xml=bubbleChart, chart20.xml=stockChart.
- charts: chart6.xml=ofPieChart, chart12.xml=surface3DChart.
- 다섯 참조 각각에 `unsupported_type`와 정확한 part 경로가 있으며 무음 누락은 없다.

초기 통합 당시의 참고 스모크 기록: 로컬 HWPX 1,699개 중 Chart/*.xml이 있는 **41개**를
`Dochan(..., include_assets=False)`로 읽었다. chart 진단은 unsupported_type 9건,
missing_cache 2건이며 다른 오류는 0건이었다. 고정된 전체 코퍼스 매니페스트를
제공하지 않는 과거 관측이며 현재 재스캔 결과나 41개 전체의 정확도 검증으로 세지 않는다.

## 초기 TDD 기록과 재검증 명령

아래는 초기 통합 당시의 기록이다. 현재 체크아웃의 실행 결과는
[implementation-progress.md](implementation-progress.md)의 검증 표를 기준으로 한다.

1. 구현 전 최초 통합 테스트 53건 실패. revision fixture에 필수 `paraend=0`을
   보충한 후 **52 failed, 1 passed**를 다시 확인했다. 공개 실물 4건 모두
   독립 XML gold 생성 이후 Dochan의 빈 차트 결과와 비교하는 지점에서 실패했다.
2. 구현 후 공동 셀 예산(일반/폴백 표의 앞뒤 배치)과 revision opaque object
   정책을 추가로 실패 확인하고 수정했다.
3. 압축 스트림 오류로 전체 section이 버려지는 문제를 추가 테스트로 재현했다.
   `part_read`로 격리하고 주변 본문 보존을 확인했다.
4. 최종 신규 통합 테스트: **66 passed, 0 skipped**, 0.14초.
5. 최종 전체 저장소 테스트: **1,497 passed, 14 xfailed**, 22.16초.
   기존 xfail은 성공으로 계산하지 않는다. HWPX/revision/assets/보안 회귀 포함.
6. Ruff와 `git diff --check` 통과.

```sh
python -m pytest tests/test_hwpx_chart_integration.py -q --tb=short
python -m pytest tests/ -q --tb=short
ruff check dochan/hwpx/parser.py tests/test_hwpx_chart_integration.py
git diff --check
```

66건에는 traversal/URL 거부, 크기·압축률 사전 차단, 실제 read 상한, ZIP 별칭,
CRC/deflate 손상, DTD/손상 XML/미지원 유형 진단, 반복 참조·다중 섹션 누적 예산,
제목/중복 points 계산, mutable 격리·재사용 초기화, switch·본문 순서·중첩 위치,
revision/assets 호환성 및 공개 실물 4건의 독립 gold 비교가 포함된다.
corpus가 없는 환경의 실물 테스트는 명시적으로 skip하며 검증 성공으로 세지 않는다.

## 한계

추출값은 저장된 OOXML 캐시/literal이다. workbook 수식 재계산, 외부 데이터 갱신,
한글 UI/차트 그림의 동일성, 축·범례·색상·숫자 표시 형식은 검증하지 않았다.
코어의 혼합/미지원 유형 및 캐시 부재 정책은 [chart-validation.md](chart-validation.md)와 같다.
차트 개체 자체의 삽입/삭제 투영은 지원하지 않으며 보존과 진단으로 처리한다.
README 지원 표·공용 모델·외부 변환 엔진/의존성은 변경하지 않았다.
