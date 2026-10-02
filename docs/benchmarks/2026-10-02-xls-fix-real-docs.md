# XLS 리뷰 반영 실물 검증

2026년 10월 2일 `illuwa/w-xls`의 두 독립 리뷰를 합쳐 수정했다. 이 문서가 초기 `xls` 검증의 최신 정정본이다. README와 공유 모델·출력 파일은 변경하지 않았다. 공개 코퍼스는 읽기만 했으며 원본을 저장소에 복사하지 않았다. 새 런타임 의존성과 외부 변환 엔진을 추가하지 않았다.

아래 내용은 Ftab 후속 전의 기록이다. 당시에는 공식 원본이 없어 이름표 18개 상태로 수식의 초기 ✅ 제안을 철회했다. 이후 제공된 공식 원본으로 전체 표를 완성했으며 최신 집계·잔여 원인은 [xls-ftab 실물 검증](2026-10-02-xls-ftab-real-docs.md)에 있다. 미지원 수식 기능이 남아 수식 칸의 ⬜ 판정은 유지한다.

## 칸별 판정

| 칸 | 구현 여부 | 단위 테스트 이름 | 실물 검증 결과 | 제안 |
|---|---|---|---|---|
| 수식 | 스택·경고·공유 3D·STRING·ARRAY 복구를 수정했지만 Ftab 전체 표는 미완료다. | `test_formula_unknown_fixed_function_warns_and_drops_incomplete_expression`, `test_formula_shared_3d_reference_keeps_stored_coordinate`, `test_formula_string_continue_switches_encoding_without_nul`이 통과했다. | 36쌍 전수 검사 중 20쌍의 1,070수식에서 832개가 정확히 일치했다. STRING 캐시 2,300개는 모두 일치했다. | ⬜를 유지한다. |
| rich text 문자열 | 일반 SST 공유, 서식 조각 캐시와 워크북 전체 런·바이트 예산을 적용했다. | `test_plain_sst_retains_shared_string_identity`, `test_rich_output_budget_falls_back_to_plain_text`, `test_rejected_cells_do_not_capture_rich_runs`가 통과했다. | xlrd 독립 정답 32문서 731/731셀의 텍스트·굵게·기울임이 일치했다. | SST 범위에서 ✅를 제안하며 RSTRING 실물은 미검증이다. |
| 내부 하이퍼링크 | 범위 표시문구를 앵커에만 넣고 모든 대상 링크를 보존한다. | `test_hyperlink_range_display_only_at_anchor`와 기존 HLINK 테스트가 통과했다. | xlrd 독립 정답 6문서 99/99개가 일치했다. | ✅를 제안한다. |
| 이미지 참조 | 모든 배치를 유지하고 pib별 바이트는 한 번만 출력한다. | `test_xls_reused_pib_exports_bytes_once_across_sheets`가 통과했다. | 공개 4문서 14배치·9자산을 확인했고 전체 짝 배치 18/18개가 일치했다. | ✅를 제안한다. |
| 이미지 OCR | 데이터 보유 배치에서 공용 OCR로 전달한다. | 대체 OCR 테스트만 통과했다. | 실제 OCR 엔진 결과는 미검증이다. | ⬜를 유지한다. |
| 차트 제목/데이터 | 내부 참조 우선, 외부 분리, 보조 계열 제외, 손상 복구와 워크북 예산을 수정했다. | `test_review_internal_reference_overrides_stale_zero_cache`, `test_review_serparent_auxiliary_series_excluded`, `test_review_workbook_chart_and_point_limits_shared_across_calls` 등이 통과했다. | 28파일 88차트를 검사했고 23파일의 참조 Y값 2,275/2,275개, 비영 숫자 2,216/2,216개가 일치했다. 외부·삭제 참조 등 40계열은 미검증이다. | 검증한 내부 참조와 기존 제목·캐시 범위에서 ✅를 제안하며 미검증 계열을 명시한다. |

## 독립 정답지와 비교 방법

파서는 `/usr/bin/python3` 3.9에서 실행했다. 정답지는 사용자가 지정한 `corpus/.venv-oracle/bin/python`을 별도 프로세스로 실행해 xlrd가 읽은 셀 값·서식·링크를 JSON으로 받았다. xlrd는 런타임 의존성으로 추가하지 않았다. xlrd가 읽지 못한 26파일은 rich text·링크 분모에 넣어 성공으로 세지 않았다.

수식 프로브는 같은 이름의 XLS/XLSX 36쌍을 모두 검사했다. XLSX ZIP의 실제 `<f>` 텍스트 219개와 그 템플릿에서 상대좌표를 확장한 공유 후속 셀 851개를 대조했다. 정확한 문자열 일치는 832/1,070(77.76%)이고, 문자열 및 참조 교차 공백을 보존하면서 연산자 주변 공백만 정규화하면 834/1,070(77.94%)이다. xlrd 캐시는 같은 표기 860개, 숫자 표시 서식까지 대조한 동등값 194개, 불일치 10개, 짝 위치 부재 6개였다. `FormatKM.xls`의 조건부 K/M 표시 서식 10개는 남은 불일치다.

`48703.xls`는 3시트이며 XLSX는 4시트이고 수식 좌표도 다르다. `ConditionalFormattingSamples.xlsx`의 Regional sales2/3 시트 네 수식은 XLS에 해당 시트가 없다. 이런 원본 차이 여섯 셀은 파서 실패로 단정하지 않으며 전체 비교 분모에서는 숨기지 않았다.

차트 프로브는 원시 BRAI에서 참조 좌표를 독립적으로 읽고 xlrd 셀과 실제 출력 표를 비교했다. 숫자 표시의 쉼표·통화·백분율을 되돌리고 상대 오차 1e-9·절대 오차 1e-10 이하를 같은 값으로 보았다. 비영 값이 0이 되는 경우는 허용하지 않았다. 이번 집계의 2,275개는 이 비교를 모두 통과했다. 제목은 기존 OOXML 짝의 두 제목이 일치했고 차트 표·종류 7/7도 유지했다.

## 실물 검증 표

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| STRING 수식 캐시 | `StringContinueRecords.xls` | 원시 FORMULA의 문자열 캐시 표식과 독립 xlrd 문자열을 확인했다. | 2,300개 문자열이 완전히 같아야 한다. | 2,300/2,300개가 같고 최장 24,732자 및 8,224자 초과 두 문자열도 일치했다. | 통과했다. |
| rich text | `duprich2.xls`, `15228.xls`, `53984.xls`를 포함한 32문서이다. | xlrd의 SST 런과 FONT·XF를 정답으로 사용했다. | 731셀의 원문과 굵게·기울임이 같아야 한다. | 731/731셀이 일치했다. | 통과했다. |
| 내부 링크 | `HyperlinksOnManySheets.xls`, `com.aida-tour.www_SPO_files_maldives%20august%20october.xls`를 포함한 6문서이다. | xlrd의 텍스트 마크와 원시 HLINK 범위를 확인했다. | 99개 내부 대상이 같아야 하고 표시문구를 빈 범위 전체에 복제하면 안 된다. | 대상 99/99개가 일치했고 표시문구는 앵커에만 남는다. | 통과했다. |
| 그림 | `SimpleWithImages.xls`, `53446.xls`, `drawings.xls`, `resize_compare.xls`이다. | 원시 BStore·ClientAnchor 및 기존 POI 크기 단언을 사용했다. | 14배치의 앵커와 9고유 pib 바이트를 보존해야 한다. | 14배치·9바이트 자산을 유지하고 문서 오류가 없다. | 통과했다. |
| 이미지 OCR | 위 그림 표본이다. | 기존 공용 OCR의 Python 3.10 이상 조건이다. | 실제 문자 인식 결과를 대조해야 한다. | 지정 Python 3.9에서 실제 엔진을 실행하지 못했다. | 미검증이다. |
| 차트 비영 값 | `45538_classic_Header.xls`이다. | BRAI의 셀을 xlrd로 읽었다. | 0.217과 0.164 등 실제 값이 0으로 바뀌면 안 된다. | `21.7%`, `16.400000000000002%` 등 표시값을 되돌리면 셀 값과 일치한다. | 통과했다. |
| 차트 비영 값 | `25183.xls`, `44861.xls`이다. | BRAI의 셀을 xlrd로 읽었다. | 각각 12516·13386·13710과 0.0145851288·0.79385509445·0.00001075213 등을 보존해야 한다. | 대조 가능한 41개와 28개 Y값이 모두 일치했다. | 통과했다. |
| 보조 계열 | `angelo.edu_content_files_19555-nsse-2011-multiyear-benchmark.xls`, `26100.xls`이다. | 원시 Series의 Begin/End 안 SerParent 레코드를 확인했다. | 추세선·오차막대 25계열을 일반 데이터 열로 출력하면 안 된다. | 각각 20개와 5개 보조 계열을 제외했다. | 통과했다. |

## 수식 전수 짝 결과

| 표본 파일 | 정답 근거 | 기대 수식 수 | 정확한 문자열 일치 | 공백 정규화 포함 일치 | 판정 |
|---|---|---:|---:|---:|---|
| `48703.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 2 | 0 | 0 | 불일치와 미지원 항목을 유지한다. |
| `52575_main.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 3 | 0 | 0 | 불일치와 미지원 항목을 유지한다. |
| `54206.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 176 | 76 | 76 | 불일치와 미지원 항목을 유지한다. |
| `55906-MultiSheetRefs.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 13 | 10 | 10 | 불일치와 미지원 항목을 유지한다. |
| `56737.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 8 | 4 | 4 | 불일치와 미지원 항목을 유지한다. |
| `57798.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 1 | 1 | 1 | 통과했다. |
| `ConditionalFormattingSamples.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 352 | 315 | 315 | 불일치와 미지원 항목을 유지한다. |
| `ForShifting.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 31 | 31 | 31 | 통과했다. |
| `FormatChoiceTests.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 51 | 0 | 0 | 불일치와 미지원 항목을 유지한다. |
| `FormatKM.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 22 | 22 | 22 | 통과했다. |
| `FormulaSheetRange.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 2 | 2 | 2 | 통과했다. |
| `MatrixFormulaEvalTestData.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 36 | 5 | 7 | 불일치와 미지원 항목을 유지한다. |
| `NewStyleConditionalFormattings.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 304 | 304 | 304 | 통과했다. |
| `SampleSS.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 1 | 1 | 1 | 통과했다. |
| `WithConditionalFormatting.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 1 | 1 | 1 | 통과했다. |
| `WithThreeCharts.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 6 | 6 | 6 | 통과했다. |
| `WithTwoCharts.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 6 | 6 | 6 | 통과했다. |
| `atp.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 7 | 0 | 0 | 불일치와 미지원 항목을 유지한다. |
| `shared_formulas.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 40 | 40 | 40 | 통과했다. |
| `tile-range-test.xls` | 같은 이름 XLSX의 raw `<f>`와 공유 템플릿이다. | 8 | 8 | 8 | 통과했다. |

나머지 16쌍은 원문 `<f>`가 없었으며 검사에서 제외한 것이 아니다. Ftab 전체 표 외에도 외부 워크북의 실제 이름, NameX·add-in UDF, 배열 상수 토큰 등이 남아 있다. 모르는 고정 함수는 수식을 생략하고 캐시와 WARN을 보존한다. 가변 함수는 토큰에 명시된 인자만 소비하고 F번호와 WARN을 남긴다.

## 차트 28파일 전수 결과

아래 기대값은 모두 원시 BRAI의 참조 셀을 xlrd로 읽은 값이다. 분모 0은 통과를 뜻하지 않는다. 28파일 88차트를 검사했지만 모든 계열을 검증했다는 주장은 하지 않는다. 외부·삭제된 참조 등 40계열과 다섯 파일의 참조 값은 미검증으로 남긴다.

| 표본 파일 | 차트 수 | 참조 셀 일치 | 비영 숫자 일치 | 참조 대조 불가 계열 | 판정 |
|---|---:|---:|---:|---:|---|
| `12843-1.xls` | 17 | 1299/1299 | 1299/1299 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `15573.xls` | 1 | 3/3 | 3/3 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `25183.xls` | 1 | 41/41 | 41/41 | 1 | 대조한 참조 셀은 모두 일치했다. 일부 계열은 참조 대조가 불가능했다. |
| `26100.xls` | 1 | 0/0 | 0/0 | 5 | 참조 셀 값은 미검증이다. 일부 계열은 참조 대조가 불가능했다. |
| `34775.xls` | 10 | 175/175 | 166/166 | 9 | 대조한 참조 셀은 모두 일치했다. 일부 계열은 참조 대조가 불가능했다. |
| `44010-SingleChart.xls` | 1 | 16/16 | 16/16 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `44010-TwoCharts.xls` | 2 | 24/24 | 24/24 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `44861.xls` | 3 | 28/28 | 28/28 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `45538_classic_Footer.xls` | 2 | 13/13 | 13/13 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `45538_classic_Header.xls` | 2 | 13/13 | 13/13 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `45784.xls` | 1 | 2/2 | 2/2 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `46137.xls` | 4 | 0/0 | 0/0 | 0 | 참조 셀 값은 미검증이다. |
| `48180.xls` | 1 | 2/2 | 2/2 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `49096.xls` | 1 | 4/4 | 4/4 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `49581.xls` | 8 | 46/46 | 46/46 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `50939.xls` | 1 | 0/0 | 0/0 | 0 | 참조 셀 값은 미검증이다. |
| `52527.xls` | 1 | 0/0 | 0/0 | 2 | 참조 셀 값은 미검증이다. 일부 계열은 참조 대조가 불가능했다. |
| `EmbeddedChartHeaderTest.xls` | 1 | 9/9 | 9/9 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `SimpleChart.xls` | 1 | 15/15 | 15/15 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `SimpleScatterChart.xls` | 2 | 4/4 | 4/4 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `WithChart.xls` | 1 | 12/12 | 12/12 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `WithFormattedGraphTitle.xls` | 1 | 3/3 | 3/3 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `WithThreeCharts.xls` | 3 | 30/30 | 30/30 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `WithTwoCharts.xls` | 2 | 24/24 | 24/24 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `angelo.edu_content_files_19555-nsse-2011-multiyear-benchmark.xls` | 10 | 104/104 | 74/74 | 0 | 대조한 참조 셀은 모두 일치했다. |
| `ex42570-20305.xls` | 1 | 146/146 | 146/146 | 1 | 대조한 참조 셀은 모두 일치했다. 일부 계열은 참조 대조가 불가능했다. |
| `external_name.xls` | 7 | 262/262 | 242/242 | 14 | 대조한 참조 셀은 모두 일치했다. 일부 계열은 참조 대조가 불가능했다. |
| `florida_data.ashx.xls` | 2 | 0/0 | 0/0 | 8 | 참조 셀 값은 미검증이다. 일부 계열은 참조 대조가 불가능했다. |

## 메모리·연산량 및 회귀

서식 없는 32,767자 SST를 1,000셀이 참조하는 46,819바이트 합성 입력은 `tracemalloc` 최대 1,558,620바이트였다. 리뷰의 34.65MB 증폭 경로를 제거하고 원문 문자열 공유를 유지했다. 1만 런을 200셀이 참조하는 53,052바이트 입력은 최대 RSS 약 60MB, 출력 TextRun 90,191개였으며 상한 초과 셀은 원문과 WARN을 남겼다. 리뷰의 같은 200×10,000 증폭에서는 약 774MB였다. RSS와 tracemalloc은 서로 다른 지표이므로 혼합 비교하지 않는다.

워크북 서식 예산은 100,000런과 16MiB이며, 바이트 비용은 재인코딩하지 않는 보수적 상한 `문자 수 × 4`로 계산한다. 서식 조각은 원문·기본 폰트별로 한 번 분할하고 셀 출처는 각 TextRun에 따로 유지한다. 거부된 셀은 서식 메타데이터를 쌓지 않는다. 차트 수·방문 포인트·출력 셀 예산은 워크북에서 공유하고 큰 희소 범위는 실제 셀 사전만 순회한다. 시트 스트림은 memoryview로 전달한다.

동일 pib 4배치 합성 입력의 이미지 내보내기 SHA-256 호출은 4회에서 1회로 줄었다. 모든 배치와 앵커는 유지되며 반복 배치는 데이터 없는 참조가 된다. 따라서 반복 배치 자체에 OCR을 다시 실행하지 않는다. 전체 XLSX 짝의 이미지 배치는 18/18개이지만 바이트 항목은 17/18개다. `resize_compare`가 같은 PNG를 두 번 배치하는 자산 구조 차이이며 그림 누락은 아니다.

XLS/XLSX 36쌍은 파싱 실패 0개이고 평균 토큰 유사도는 0.7493이다. 차트 표·종류는 7/7, 일반 셀 텍스트 다중집합은 6,829/7,890이다. 초기의 6,878/7,890보다 줄어든 값도 숨기지 않는다. 캐시보다 실제 셀을 우선하고 모르는 수식 조각을 정상 수식으로 표시하지 않도록 바뀌었으므로 이 수치만으로 내용 손실 여부를 판단하지 않는다. 별도의 정답지 대조 수치를 우선한다.

공개 XLS 417개 전체 검사에서 예외·시간 초과·비정상 종료는 0개, ERR 문서는 27개, WARN만 있는 문서는 154개였다. 초기 완료본 대비 새로운 ERR는 0개이고 시트 수 감소는 0개였다. 그림은 36문서 344배치를 유지했다. WARN 증가는 모르는 함수·토큰·외부 참조를 명시한 결과이며 정상 완료 문서 수와 혼동하지 않는다.

전체 테스트는 **1,969 passed, 24 skipped, 14 xfailed**로 끝났다. 예상 실패와 건너뜀을 통과한 검증으로 세지 않았다. Python 3.9 문법 검사와 `git diff --check`도 통과했다.

## 기존 테스트 정정 근거

이번 리뷰에서 바꾼 HEAD 단언은 F250 한 개다. 기존 `0 (=F250(A2,10))`는 인자 수가 없는 미지원 PtgFunc에 스택 전체를 인자로 붙이던 오류를 고정했다. `0` 캐시와 명시적 WARN을 검사하도록 바꿨다. `7, 1, PtgFunc(2), +` 합성 재현은 같은 오류가 외부 피연산자까지 삼킨다는 근거다. 기존 HEAD의 AVERAGE 고정 토큰 단일 범위 회복은 단언을 유지하되 WARN을 남기는 제한적 호환 경로로 유지했고 공식 전체 표로 검증할 일이 남아 있다.

초기 작업에서 바꾼 빈 캐시 `(=A2)`에서 `=A2`로의 단언과 PtgAttr 4바이트 합성 보정은 기존 XLSX 계약 및 레코드 크기 정정이다. 새 미추적 차트 테스트의 캐시 우선 기대는 `45538_classic_Header` 등 실물에서 틀린 0을 기대하던 계약이므로 내부 참조 우선으로 정정했다. 다른 HEAD 단언은 유지했다.

## 재현 명령

프로브의 코퍼스 경로와 xlrd 인터프리터 경로는 모두 인자로 받는다. 아래 CORPUS는 공개 spreadsheet 디렉터리이고 ORACLE은 사용자가 지정한 xlrd venv Python이다.

```sh
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
/usr/bin/python3 -m scripts.probe_xls_formula_pairs CORPUS --oracle-python ORACLE --output .codex-work/formula-pairs-final.json
/usr/bin/python3 -m scripts.probe_xls_charts_review CORPUS --oracle-python ORACLE --output .codex-work/chart-review-probe.json
/usr/bin/python3 -m scripts.probe_xls_review_cells CORPUS --oracle-python ORACLE --output .codex-work/xls-review-cells.json
/usr/bin/python3 -m scripts.probe_xls_corpus CORPUS --output .codex-work/xls-corpus-fix.json
/usr/bin/python3 -m scripts.compare_office_pairs CORPUS --output .codex-work/xls-pairs-fix.json
```
