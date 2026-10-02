# XLS 초기 실물 검증의 리뷰 정정

아래 내용은 Ftab 후속 전의 기록이다. Ftab 표 완성과 최신 수식 집계·잔여 원인은 [xls-ftab 실물 검증](2026-10-02-xls-ftab-real-docs.md)에 있다. 표는 완료했지만 미지원 수식 기능이 남아 수식 칸의 ⬜ 판정은 유지한다.

초기 수치와 판정을 두 독립 리뷰에 따라 정정했다. 최신 전수 비교, 실패 근거, 수치와 재현 명령은 [xls-fix 실물 검증](2026-10-02-xls-fix-real-docs.md)에 있다. 초기의 수식 ✅ 제안은 철회하며 Ftab 전체 표가 완료될 때까지 ⬜로 유지한다. 차트는 오래된 캐시보다 내부 참조 셀을 우선한다. 아래 표는 초기 공개 표본의 개별 기대값 근거이며 전수 지원을 뜻하지 않는다.

| 칸 | 구현 여부 | 단위 테스트 이름 | 실물 검증 결과 | 제안 |
|---|---|---|---|---|
| 수식 | 스택·경고·공유 3D·STRING·ARRAY 복구를 수정했지만 Ftab 전체 표는 미완료다. | `test_formula_unknown_fixed_function_warns_and_drops_incomplete_expression`, `test_formula_shared_3d_reference_keeps_stored_coordinate`, `test_formula_string_continue_switches_encoding_without_nul`이 통과했다. | 36쌍 전수 검사 중 20쌍의 1,070수식에서 832개가 정확히 일치했다. STRING 캐시 2,300개는 모두 일치했다. | ⬜를 유지한다. |
| rich text 문자열 | 일반 SST 공유, 서식 조각 캐시와 워크북 전체 런·바이트 예산을 적용했다. | `test_plain_sst_retains_shared_string_identity`, `test_rich_output_budget_falls_back_to_plain_text`, `test_rejected_cells_do_not_capture_rich_runs`가 통과했다. | xlrd 독립 정답 32문서 731/731셀의 텍스트·굵게·기울임이 일치했다. | SST 범위에서 ✅를 제안하며 RSTRING 실물은 미검증이다. |
| 내부 하이퍼링크 | 범위 표시문구를 앵커에만 넣고 모든 대상 링크를 보존한다. | `test_hyperlink_range_display_only_at_anchor`와 기존 HLINK 테스트가 통과했다. | xlrd 독립 정답 6문서 99/99개가 일치했다. | ✅를 제안한다. |
| 이미지 참조 | 모든 배치를 유지하고 pib별 바이트는 한 번만 출력한다. | `test_xls_reused_pib_exports_bytes_once_across_sheets`가 통과했다. | 공개 4문서 14배치·9자산을 확인했고 전체 짝 배치 18/18개가 일치했다. | ✅를 제안한다. |
| 이미지 OCR | 데이터 보유 배치에서 공용 OCR로 전달한다. | 대체 OCR 테스트만 통과했다. | 실제 OCR 엔진 결과는 미검증이다. | ⬜를 유지한다. |
| 차트 제목/데이터 | 내부 참조 우선, 외부 분리, 보조 계열 제외, 손상 복구와 워크북 예산을 수정했다. | `test_review_internal_reference_overrides_stale_zero_cache`, `test_review_serparent_auxiliary_series_excluded`, `test_review_workbook_chart_and_point_limits_shared_across_calls` 등이 통과했다. | 28파일 88차트를 검사했고 23파일의 참조 Y값 2,275/2,275개, 비영 숫자 2,216/2,216개가 일치했다. 외부·삭제 참조 등 40계열은 미검증이다. | 검증한 내부 참조와 기존 제목·캐시 범위에서 ✅를 제안하며 미검증 계열을 명시한다. |

## 실물 검증 표

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| RK 결함 | `SimpleMultiCell.xls` | 같은 이름의 XLSX 출력과 상위 IEEE 워드 0x3FF00000을 확인했다. | 비어 있지 않은 15개 셀이 1부터 15여야 한다. | 숫자 15개가 순서까지 완전히 일치했다. | 통과했다. |
| COLINFO 결함 | `54206.xls`, `ConditionalFormattingSamples.xls`, `FormatChoiceTests.xls`, `comments.xls`, `resize_compare.xls`, `tile-range-test.xls` | COLINFO의 마지막 열 0x100은 끝까지의 서식 선언이다. 기존 기준선의 오류 6쌍이다. | 존재하지 않는 257번째 열을 생성하거나 범위 오류를 내지 않아야 한다. | 6문서 모두 `doc.errors=[]`이며 짝 비교에서 정상 집계됐다. | 6/6 통과했다. |
| 수식 | `SimpleWithFormula.xls` | `extractor/TestExcelExtractor.java:107-114`의 캐시·수식 단언이다. | A3가 `replacemereplaceme (=CONCATENATE(A1,A2))`여야 한다. | 기대 문자열과 일치했다. | 통과했다. |
| 수식 | `StringFormulas.xls` | 같은 테스트 120–127행과 `usermodel/TestFormulas.java:600-604`이다. | A1이 `XYZ (=UPPER("xyz"))`여야 한다. | 기대 문자열과 일치했다. | 통과했다. |
| 수식 | `FormulaSheetRange.xls` | 같은 이름의 XLSX 출력이다. | D11이 `10 (=SUM(Sheet2:Sheet5!A11))`, D12가 `60 (=SUM(Sheet2:Sheet5!A12:C12))`여야 한다. | 2셀 모두 일치했다. | 통과했다. |
| 수식 | `shared_formulas.xls` | 같은 이름의 XLSX 출력이다. | Label A2:A41의 40개 셀이 캐시와 B2부터 B41까지의 수식을 함께 출력해야 한다. | A2의 `ProductionOrderConfirmation (=B2)`를 포함해 40셀 모두 일치했다. | 40/40 통과했다. |
| rich text 문자열 | `duprich2.xls` | `record/TestSSTRecord.java:323-331`의 문자열 단언과 원시 SST4·SST5, FONT5·FONT6, XF15·XF21을 확인했다. | A1은 `Test` 일반·`in` 굵게·`g` 일반이고 A5는 `Tes` 기울임·`ting` 일반이어야 한다. | 경계와 서식이 5런 모두 일치했다. | 통과했다. |
| rich text 문자열 | `15228.xls` | SST78/79/80의 `(ich, ifnt)`와 FONT19의 grbit=2·bls=400을 직접 읽었다. | B7/E7/I7에서 CFM·PM·BM만 기울임이어야 한다. | 세 셀의 일반/기울임/일반 경계와 서식 9런이 일치했다. | 통과했다. |
| rich text 문자열 | `53984.xls` | SST10의 13런과 FONT6~12의 grbit=2·bls=700을 직접 읽었다. | B16의 일반 구간과 굵게·기울임 동시 구간이 원시 배열과 같아야 한다. | 문자열 경계와 두 서식 플래그가 13런 모두 일치했다. | 통과했다. |
| 내부 하이퍼링크 | `HyperlinksOnManySheets.xls` | `usermodel/TestHSSFHyperlink.java:79-87`이다. | Internal A5가 `Link To First Sheet <#WebLinks!A1>`여야 한다. | 기대 문자열과 일치했다. | 통과했다. |
| 내부 하이퍼링크 | `com.aida-tour.www_SPO_files_maldives%20august%20october.xls` | 원시 HLINK의 범위 B8과 UTF-16 location을 확인했다. | 대상이 `#Отель__BANYAN_TREE_VABBINFARU_MALDIVES_5___Мале`여야 한다. | 원래 셀 표시문구 뒤의 대상 조각이 정확히 일치했다. | 통과했다. |
| 이미지 참조 | `SimpleWithImages.xls` | `usermodel/TestHSSFPictureData.java:49-76`의 JPEG·PNG 크기와 원시 BStore/ClientAnchor를 확인했다. | JPEG 192×176, PNG 300×300 및 원시 WMF·EMF를 복원해야 한다. | JPEG 11,988바이트, PNG 751바이트, WMF 28,674바이트, EMF 6,184바이트를 A1·E2·B21·F25에 연결했다. | 크기 2/2와 4배치를 확인했다. |
| 이미지 참조 | `53446.xls` | 같은 테스트 85–108행의 고유 PNG 1개·78×76 단언이다. | PNG 자산 1개가 각 시트의 그림에 연결돼야 한다. | 2,111바이트 자산 1개를 5배치에 연결했고 크기가 일치했다. | 통과했다. |
| 이미지 참조 | `drawings.xls` | `usermodel/TestHSSFPicture.java:204-212`의 picture 시트 그림 1개 단언과 원시 BStore이다. | picture 시트에 그림 1개가 있어야 한다. | picture A1에 PNG를 출력했고 다른 두 시트의 JPEG·EMF도 복원했다. | 그림 수가 일치했다. |
| 이미지 OCR | 위 이미지 표본 | `dochan/utils/ocr.py`는 `MIN_OCR_PYTHON=(3,10)`을 요구한다. | 실제 OCR 엔진의 문자 결과를 검증해야 한다. | Python 3.9에서 `is_ocr_available()`이 False다. | 미검증이다. |
| 차트 제목/데이터 | `WithChart.xls` | 같은 이름의 XLSX 출력과 `usermodel/TestHSSFChart.java:48-60`이다. | line 차트 1개에 두 계열과 6개 점이 있어야 한다. | 7행·3열 표와 종류가 완전히 일치했다. | 통과했다. |
| 차트 제목/데이터 | `WithTwoCharts.xls` | 같은 이름의 XLSX 출력과 같은 테스트 78–100행이다. | line·area 차트 2개에 각각 두 계열이 있어야 한다. | 두 표와 종류가 완전히 일치했다. | 통과했다. |
| 차트 제목/데이터 | `WithThreeCharts.xls` | 같은 이름의 XLSX 출력과 같은 테스트 111–145행이다. | line·pie·area와 제목 `Pie Chart Title Thingy`, `Sheet 3 Chart with Title`이 있어야 한다. | 세 표·종류와 두 제목이 완전히 일치했다. | 통과했다. |
| 차트 제목/데이터 | `SimpleScatterChart.xls` | 같은 이름의 XLSX 출력 및 Chart1의 BOF subtype=0x20, BRAI와 SIIndex 캐시를 확인했다. | Sheet1과 Chart1에서 X=[0,1], Y=[0.5,1.5]를 복원해야 한다. | 두 scatter 표가 일치했다. XLSX가 출력하지 않는 Chart1은 별도로 원시 바이트와 비교했다. | 두 경로 모두 통과했다. |


이미지의 반복 배치는 참조로 유지하고 바이트는 pib별로 한 번만 출력한다. 위 표의 배치 수와 고유 이미지 바이트 근거는 유지되며 배치마다 바이트를 복제한다는 뜻이 아니다. 전체 차트 대조는 최신 문서의 28파일 표를 따른다. 전체 테스트와 417파일 프로브의 최신 수치도 최신 문서에 기록한다.
