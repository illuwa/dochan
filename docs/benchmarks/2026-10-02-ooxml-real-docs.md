# OOXML 실물 검증 기록

2026년 10월 2일 리뷰 반영 후의 최종 판정이다. 초기의 DOCX 읽기 순서 및 PPTX 중첩 표 ✅ 제안은 철회했다. 캡션과 수식의 실물 표본 부재 기록은 추가 LibreOffice 검사로 갱신했다. 전체 비교 기준·추가 실물 표·84개 읽기 순서 결과·공용 Markdown 영향은 [리뷰 반영 실물 검증 기록](2026-10-02-ooxml-fix-real-docs.md)에 있다.

| 칸 | 구현 여부 | 단위 테스트 이름 | 실물 검증 결과(표본 수·일치율) | 제안 |
| --- | --- | --- | --- | --- |
| XLSX 차트 제목/데이터 | 캐시·참조·chartEx를 구현하고 손상·공유 예산을 보강했다. | `test_chart_infers_missing_cell_coordinates_without_fatal_errors`, `test_embedded_chart_resolver_reuses_sheet_across_charts` 및 기존 차트 테스트다. | POI 26파일·38파트 중 출력 32파트의 값 1,828/1,828개, 제목 16/16개, 캡션 32/32개가 일치했다. 64450.xlsx의 참조 이름·값도 16/16개 일치했다. | 검증한 연결 차트 범위에서 ✅를 제안한다. |
| DOCX 차트 제목/데이터 | 런 앵커와 반복 출력 예산을 구현했다. | `test_docx_repeated_chart_occurrences_share_output_budget`, `test_docx_group_chart_keeps_textbox_siblings_in_order`, `test_damaged_embedded_deflate_keeps_document_body`다. | POI 2파일·8표·248/248셀, 캐시 값 155/155개, 제목 6/6개가 일치했다. | ✅를 제안한다. |
| DOCX 표/그림 캡션 | 최상위 인접 캡션을 결합하고 셀 캡션은 문단으로 유지한다. | `test_docx_cell_caption_stays_original_paragraph`, `test_docx_caption_adjacency_crosses_sdt_only_without_gap`, `test_docx_sequential_captions_skip_already_captioned_target`다. | LO 1,366파일 스캔 중 18파일·활성 Caption/SEQ 30문단을 확인했다. 5파일의 명확한 최상위 인접 캡션 7/7개가 Table/Image에 올바르게 결합했다. 나머지는 아래 한계를 따른다. | 최상위 인접 표·그림 계약에 ✅를 제안한다. |
| DOCX 읽기 순서 | 앵커·텍스트박스·SDT를 처리하고 중복과 단어 결합을 수정했다. | `test_docx_textbox_boundaries_do_not_merge_words`, `test_docx_textbox_image_is_emitted_once`, `test_alignment_detects_duplicate_and_extra_output_tokens`다. | LO 84파일의 원문/출력 완전 토큰열 일치는 62/84(73.81%)다. 원문 텍스트가 있는 70파일만 보면 52/70(74.29%)다. | 기존 ✅ 제안을 철회하고 ⬜를 유지한다. |
| PPTX 표 (중첩 텍스트) | 일반 셀 문단·수식은 보존하지만 셀 안 중첩 Table은 형식 계약에 없다. | 기존 `tests/test_hwpx_reader.py:629`, `test_reads_docx_nested_table_text_inside_parent_cell` 등의 중첩 계약을 확인했다. | POI 997/997셀과 LO 293/293셀은 일반 표 증거다. 중첩 표 증거로 사용하지 않는다. | 기존 ✅ 제안을 철회하고 —를 제안한다. |
| PPTX 수식 | OMML과 수식 전용 번호 문단을 구현했다. | `test_math_only_numbered_paragraph_consumes_and_displays_marker`, `test_pptx_probe_equation_cell_compares_raw_omml`다. | LO 427개 정상 PPTX에서 tdf129372.pptx의 𝜕 1식이 script·LaTeX 1/1 일치했다. | 단순 기호 실물과 구조별 단위 테스트 근거로 ✅를 제안한다. 복잡한 실물 수식은 미검증이다. |
| PPTX 표/그림 캡션 | 일반 도형 텍스트를 유지한다. | picTx·objTx 레이아웃과 개별 Table/Image.caption의 차이를 확인했다. | POI 84개와 LO 427개 정상 PPTX에서 별도 caption 요소는 0개다. | —를 제안한다. |

전체 테스트는 1,922 passed, 24 skipped, 14 xfailed다. 공용 캡션 이스케이프의 HEAD 대비 영향은 HWPX 1,700개 중 6파일·26줄이고 XLS 숨김 시트 표기는 417개 중 9파일·38줄이다. 캡션은 `< > [ ]`를 그대로 둔다. 숨김 상태는 제목 뒤 별도 `Sheet visibility` 문단으로 표시하고 숨김 시트가 있으면 모든 시트의 제목을 낸다. 셀 캡션은 원래 문단으로 유지하며 중첩 Table의 Markdown 구분자는 열 ` / `, 행 ` ; `다.

## 재실행으로 확인한 차트별 증거

아래 표의 기존 캐시값은 최종 프로브에서도 모두 일치했다. 미연결·데이터 없음·손상 표본은 성공으로 세지 않는다. 참고로 123233_charts.xlsx의 미출력 Revenue 때문에 전체 17개 명시 제목 중 출력된 제목은 16개이며 성공 수는 16/16이다.

| 칸 | 표본 파일과 파트 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLSX 차트 제목/데이터 | `123233_charts.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 0개, 제목 없음 | Y 0개 일치, 실제 표 없음 | 미출력 |
| XLSX 차트 제목/데이터 | `123233_charts.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 0개, 제목 Revenue | Y 0개 일치, 실제 표 없음 | 미출력 |
| XLSX 차트 제목/데이터 | `123233_charts.xlsx` | `xl/charts/chart3.xml` 원시 캐시/제목 | Y 0개, 제목 없음 | Y 0개 일치, 실제 표 없음 | 미출력 |
| XLSX 차트 제목/데이터 | `123233_charts.xlsx` | `xl/charts/chart4.xml` 원시 캐시/제목 | Y 0개, 제목 없음 | Y 0개 일치, 실제 표 없음 | 미출력 |
| XLSX 차트 제목/데이터 | `45540_classic_Footer.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 6개, 제목 Top Five Industries - Intern | Y 6개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `45540_classic_Footer.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 7개, 제목 Top Six Functions - Intern | Y 7개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `45540_classic_Header.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 6개, 제목 Top Five Industries - Intern | Y 6개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `45540_classic_Header.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 7개, 제목 Top Six Functions - Intern | Y 7개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `45544.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 6개, 제목 Top Five Industries - Intern | Y 6개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `45544.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 7개, 제목 Top Six Functions - Intern | Y 7개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `47813.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 1440개, 제목 없음 | Y 1440개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `56557.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 0개, 제목 없음 | Y 0개 일치, 실제 표 없음 | 미출력 |
| XLSX 차트 제목/데이터 | `57362.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 4개, 제목 없음 | Y 4개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `60255_extra_drawingparts.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 8개, 제목 없음 | Y 8개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `60509.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 8개, 제목 없음 | Y 8개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `64450.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 0개, 제목 없음 | Y 0개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `65016.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 0개, 제목 없음 | Y 0개 일치, 실제 표 없음 | 미출력 |
| XLSX 차트 제목/데이터 | `DataTableCities.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 26개, 제목 없음 | Y 26개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `LIBRE_OFFICE-128382-0.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 40개, 제목 Example of 3D Line chart | Y 40개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `LIBRE_OFFICE-128382-0.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 7개, 제목 Example of 3D Pie chart | Y 7개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `SimpleScatterChart.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 2개, 제목 없음 | Y 2개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `SimpleScatterChart.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 2개, 제목 없음 | Y 2개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `StructuredRefs-lots-with-lookups.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 14개, 제목 Category 1 | Y 14개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithChart.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 12개, 제목 없음 | Y 12개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithChartSheet.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 6개, 제목 없음 | Y 6개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithThreeCharts.xlsx` | `xl/charts/chart3.xml` 원시 캐시/제목 | Y 12개, 제목 Sheet 3 Chart with Title | Y 12개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithThreeCharts.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 12개, 제목 없음 | Y 12개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithThreeCharts.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 6개, 제목 Pie Chart Title Thingy | Y 6개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithTwoCharts.xlsx` | `xl/charts/chart2.xml` 원시 캐시/제목 | Y 12개, 제목 없음 | Y 12개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `WithTwoCharts.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 12개, 제목 없음 | Y 12개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `chartTitle_noTitle.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 4개, 제목 없음 | Y 4개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `chartTitle_withTitle.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 4개, 제목 Original title set in Excel 2013 | Y 4개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `chartTitle_withTitleFormula.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 4개, 제목 Formula Title from Excel 2016 | Y 4개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `chart_sheet.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 8개, 제목 없음 | Y 8개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `clone_sheet.xlsx` | `xl/charts/chart4.xml` 원시 캐시/제목 | Y 34개, 제목 Inductive transducer | Y 34개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `clone_sheet.xlsx` | `xl/charts/chart3.xml` 원시 캐시/제목 | Y 34개, 제목 Rate generator | Y 34개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `dataValidationTableRange.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 76개, 제목 Ranking of Washington Counties on Days per Patient (ALOS) in 2015 | Y 76개 일치, 실제 표 있음 | 일치 |
| XLSX 차트 제목/데이터 | `simple-monthly-budget.xlsx` | `xl/charts/chart1.xml` 원시 캐시/제목 | Y 2개, 제목 없음 | Y 2개 일치, 실제 표 있음 | 일치 |
| DOCX 차트 제목/데이터 | `61745.docx`, `word/charts/chart1.xml`와 `chart2.xml` | 원시 classic 차트의 계열명·범주·숫자 캐시와 POI `poi-ooxml/src/test/java/org/apache/poi/xwpf/usermodel/TestXWPFChart.java:45-60` | 두 막대 차트에 각각 3계열과 4개 데이터 행이 있으며, 헤더 포함 40셀이다. | 표 2/2개와 40/40셀이 일치했다. 캡션은 `Chart type: bar`, `Chart type: column`이다. | 통과했다. |
| DOCX 차트 제목/데이터 | `chartex.docx`, classic `chart1.xml`, `chart2.xml`, `chart3.xml`, `chart5.xml` | 원시 c:title와 c:ser/cat/val 캐시를 독립적으로 읽은 값이다. POI `TestXWPFDocument.java:527`도 이 공개 표본을 사용한다. | 명시 제목 4개와 헤더 포함 82셀이다. | 제목 4/4개와 82/82셀이 일치했다. 종류는 column, line, radar, stock이다. | 통과했다. |
| DOCX 차트 제목/데이터 | `chartex.docx`, chartEx `chart4.xml`와 `chart6.xml` | 원시 cx:series의 dataId와 cx:chartData의 strDim/numDim 값이다. sunburst 범주는 leaf→stem→branch 저장 순서를 뒤집어 원시 계층을 결합했다. | box-and-whisker 22행과 sunburst 16행, 명시 제목 2개와 헤더 포함 126셀이다. | 제목 2/2개와 126/126셀이 일치했다. 캡션은 `Chart type: box and whisker`, `Chart type: sunburst`이다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart19.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 2개, Gráfico de Setores ou Pizza, Chart type: 3-D pie이다. | 실제 출력 값 2/2개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart11.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 3개, Gráfico de Setores ou Pizza, Chart type: 3-D pie이다. | 실제 출력 값 3/3개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart12.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 3개, Gráfico de Colunas ou Barras, Chart type: 3-D bar이다. | 실제 출력 값 3/3개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart13.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 3개, Gráfico de Setores ou Pizza, Chart type: 3-D pie이다. | 실제 출력 값 3/3개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart14.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 3개, Gráfico de Colunas ou Barras, Chart type: 3-D bar이다. | 실제 출력 값 3/3개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart15.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 3개, Gráfico de Setores ou Pizza, Chart type: 3-D pie이다. | 실제 출력 값 3/3개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart16.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 3개, Gráfico de Colunas ou Barras, Chart type: 3-D bar이다. | 실제 출력 값 3/3개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart17.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, Gráfico de Setores ou Pizza, Chart type: 3-D pie이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart18.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, Gráfico de Colunas ou Barras, Chart type: 3-D bar이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `LIBRE_OFFICE-100610-0.pptx` · `ppt/charts/chart20.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 2개, Gráfico de Colunas ou Barras, Chart type: 3-D bar이다. | 실제 출력 값 2/2개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_hbcu_leadershipsummit_cooper_.pptx` · `ppt/charts/chart2.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 8개, 명시 제목 없음, Chart type: column이다. | 실제 출력 값 8/8개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_hbcu_leadershipsummit_cooper_.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 20개, 명시 제목 없음, Chart type: column이다. | 실제 출력 값 20/20개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart5.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 47개, 명시 제목 없음, Chart type: column + line이다. | 실제 출력 값 47/47개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart6.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 15개, Average scores around age 1 (relative to those with grad-school parents), Chart type: column이다. | 실제 출력 값 15/15개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart7.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 20개, Average scores around age 2 (relative to those with grad-school parents), Chart type: column이다. | 실제 출력 값 20/20개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart8.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 20개, Average scores around age 4 (relative to those with grad-school parents), Chart type: column이다. | 실제 출력 값 20/20개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart4.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 16개, 명시 제목 없음, Chart type: line이다. | 실제 출력 값 16/16개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 21개, 명시 제목 없음, Chart type: 3-D column이다. | 실제 출력 값 21/21개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart3.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 15개, Employment of workers with a Bachelor’s degree or better grew at a 2 percent to 3 percent rate over the past two decades., Chart type: column이다. | 실제 출력 값 15/15개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `aascu.org_workarea_downloadasset.aspx_id=5864.pptx` · `ppt/charts/chart2.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 33개, 명시 제목 없음, Chart type: column이다. | 실제 출력 값 33/33개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `bar-chart.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, 명시 제목 없음, Chart type: bar이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `chart-picture-bg.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 12개, 명시 제목 없음, Chart type: column이다. | 실제 출력 값 12/12개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `chart-slide-bg.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 12개, 명시 제목 없음, Chart type: column이다. | 실제 출력 값 12/12개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `chart-texture-bg.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 12개, 명시 제목 없음, Chart type: column이다. | 실제 출력 값 12/12개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `line-chart.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, 명시 제목 없음, Chart type: line이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `pie-chart.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, 명시 제목 없음, Chart type: pie이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `radar-chart.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, 명시 제목 없음, Chart type: radar이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
| PPTX 차트 제목/데이터 | `scatter-chart.pptx` · `ppt/charts/chart1.xml` | 원시 XML의 idx·범주·값·제목·종류와 축 제목이다. | 값 4개, 명시 제목 없음, Chart type: scatter이다. | 실제 출력 값 4/4개와 제목·캡션이 일치했다. | 통과했다. |
