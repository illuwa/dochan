# XLS 텍스트박스·도형 글자 실물 검증

2026년 10월 4일에 README `Supported Elements`의 XLS `텍스트박스/도형 텍스트` 칸을 검증했다. [MS-XLS]의 `Obj.ftCmo.ot`와 `TxO`·`Continue`, [MS-ODRAW]의 OfficeArt 클라이언트 앵커를 기준으로 했다. 메모형 `ot=0x0019`는 셀 주석에만 남겼다. 폼 컨트롤 `ot=0x0007` 및 `0x000B`–`0x0014`의 문구는 XLSX 리더의 출력 계약에 맞춰 문단에서 제외하지만, 뒤따르는 도형과 앵커를 연결할 때는 해당 Obj의 위치를 유지한다. 비메모 도형 글자는 XLSX처럼 줄마다 공백을 제거하고 빈 줄을 생략한다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLS 텍스트박스/도형 텍스트 | POI `ConditionalFormattingSamples.xls`와 같은 이름의 `.xlsx` | XLSX 리더의 drawing 문단 출력과 XLS의 `Obj`·`TxO` 바이트를 대조했다. | 두 형식의 공통 16시트에서 공통 도형 문구 47개의 내용과 순서가 일치해야 한다. | 47/47개가 순서까지 일치했다. XLSX에만 있는 시트 2개와 두 형식에 공통되지 않은 문구는 비교에서 제외했다. | 통과했다. |
| XLS 텍스트박스/도형 텍스트 | 아래 POI 공개 XLS 23파일 | `dochan.cfb`와 제품의 `_iter_records`로 레코드를 순회하되, `TxO.cchText`·`Continue` 글자만 별도로 해독해 SHA-256으로 대조했다. | 폼 컨트롤·차트 하위 스트림·메모를 제외한 시트 도형 문구 578개가 문단에 남아야 한다. | 578/578개가 문구 해시와 개수 기준으로 일치했다. | 통과했다. |
| XLS 텍스트박스/도형 텍스트 | 아래 LibreOffice 공개 XLS 4파일 | 위와 같은 원시 바이트 관찰을 사용했다. 같은 이름의 XLSX 짝은 없다. | 시트 도형 문구 11개가 문단에 남아야 한다. | 11/11개가 문구 해시와 개수 기준으로 일치했다. | 통과했다. |

POI XLS 417개와 LibreOffice XLS 303개, 합계 720개를 99dcf19 기준과 최종 코드로 각각 파싱했다. Markdown 전문은 저장하지 않고 UTF-8 SHA-256·문자 수·오류 목록만 보관했다. 최종 코드에서 변경된 파일은 아래 27개뿐이고, 693개의 Markdown 해시는 같다. 720개의 오류 목록도 모두 같다. 원시 CFB를 열 수 없어 바이트 검사를 완료하지 못한 39개(POI 6개, LibreOffice 33개)는 589개 문구 검증의 분모에 넣지 않았다. 이 39개 파일의 Markdown 해시도 변하지 않았다.

독립 프로브의 `verify`는 전체 `Paragraph`의 문구 해시를 다중집합으로 비교한다. 따라서 589/589는 문구 보존을 검증하지만 문구 순서나 화면 위치를 증명하지 않는다. 순서는 위 XLS/XLSX 짝 47개에 한해 별도로 비교했다. 여러 줄 문구에 대한 XLS/XLSX 실물 짝 검증은 없다. 감수자는 제품 코드를 쓰지 않는 별도 스캐너(각 Obj 를 바로 앞에서 끝나는 ClientData 와 바이트 위치로 짝지음)로 워크시트 46개 시트 전체의 문구 순서와 셀 위치를 대조했고, 문구 589개(앵커 있는 545개)가 모두 일치했다. 나머지 3개 시트는 의도적으로 제외한 차트 시트다. Obj 하나의 ftCmo 를 망가뜨린 손상 실험 750회·ClientData 를 지운 실험 652회에서 짝 없는 ClientData 가 뒤 앵커를 밀어 잘못된 셀을 붙이던 결함을 찾아, 같은 drawing 위치의 Obj 묶음마다 직전 묶음 뒤에 끝난 ClientData 만 뒤에서부터 짝짓도록 고쳤다(두 실험 모두 잘못된 셀 0).

`python -m scripts.compare_office_pairs`로 POI spreadsheet의 같은 이름 XLS/XLSX 36쌍을 다시 비교했다. 파싱 실패는 0개이고, 평균 토큰 유사도는 99dcf19 기준 0.9266에서 최종 0.9273으로 변했다. `ConditionalFormattingSamples` 짝은 0.9387에서 0.9626으로 변했다. 두 값에는 도형 글자 외에 시트 수와 표 차이도 포함되므로 글자 정확도의 정답 지표로 사용하지 않았다.

## 출력이 바뀐 공개 파일 전체

표의 문구 수는 폼 컨트롤·차트 하위 스트림·메모를 제외한 비메모 도형의 `TxO` 문구 수다. POI 파일은 `corpus/poi-src/test-data/spreadsheet/`, LibreOffice 파일은 `corpus/lo-src/` 아래에 있다.

| 코퍼스 | 파일 | 문구 수 |
| --- | --- | ---: |
| POI | `31749.xls` | 2 |
| POI | `37684-2.xls` | 170 |
| POI | `44010-SingleChart.xls` | 6 |
| POI | `44010-TwoCharts.xls` | 6 |
| POI | `45129.xls` | 30 |
| POI | `45538_form_Footer.xls` | 4 |
| POI | `45538_form_Header.xls` | 4 |
| POI | `45565.xls` | 2 |
| POI | `46137.xls` | 5 |
| POI | `ConditionalFormattingSamples.xls` | 47 |
| POI | `LIBRE_OFFICE-94379-0.zip-57.xls` | 3 |
| POI | `angelo.edu_content_files_19555-nsse-2011-multiyear-benchmark.xls` | 10 |
| POI | `ar.org.apsme.www_Form%20Inscripcion%20Curso%20NO%20Socios.xls` | 5 |
| POI | `cf9f845e73447b092477d0472402a5baea4b8c9f.xls` | 13 |
| POI | `clusterfuzz-testcase-minimized-POIHSSFFuzzer-4977868385681408.xls` | 30 |
| POI | `clusterfuzz-testcase-minimized-POIHSSFFuzzer-5285517825277952.xls` | 30 |
| POI | `clusterfuzz-testcase-minimized-POIHSSFFuzzer-5436547081830400.xls` | 30 |
| POI | `crash-e329fca9087fe21bca4a80c8bc472a661c98d860.xls` | 170 |
| POI | `dg-text.xls` | 5 |
| POI | `drawings.xls` | 2 |
| POI | `ex42570-20305.xls` | 1 |
| POI | `external_image.xls` | 2 |
| POI | `text.xls` | 1 |
| LibreOffice | `sc/qa/unit/data/xls/forum-mso-de-48440.xls` | 2 |
| LibreOffice | `sc/qa/unit/data/xls/forum-mso-en4-102737.xls` | 2 |
| LibreOffice | `sc/qa/unit/data/xls/pictureOrder.xls` | 5 |
| LibreOffice | `sc/qa/unit/data/xls/pivottable_dates_grouping.xls` | 2 |

폼 컨트롤 제외로 이전 집계의 38파일·670문구에서 11파일·81문구가 빠져 27파일·589문구가 됐다. 빠진 파일은 POI `39512.xls`, `39634.xls`, `50939.xls`, `StringContinueRecords.xls`, `external_name.xls`와 LibreOffice `sc/qa/unit/data/xls/forum-mso-en4-109082.xls`, `sc/qa/unit/data/xls/forum-mso-en4-368528.xls`, `sc/qa/unit/data/xls/opencl/logical/xor.xls`, `sc/qa/unit/data/xls/opencl/math/sumproductTest.xls`, `sc/qa/unit/data/xls/tdf120177.xls`, `sc/qa/unit/data/xls/tdf170285_controlsInGroupShape.xls`이다.

`12843-1.xls`의 비메모 `TxO` 네 개와 `forum-mso-de-48440.xls`의 19개는 차트 `BOF(0x0020)` 하위 스트림에 있어 이번 시트 도형 출력에서 제외된다. 특히 뒤 파일의 19개는 차트 안의 텍스트박스 문구이며 현재 시트 문단으로 출력되지 않는 한계가 있다. 이 둘은 위 589개 집계에 넣지 않았다.

## 같은 행 XLSX 칸의 검증 근거

POI의 공개 XSSF 테스트 `poi-ooxml/src/test/java/org/apache/poi/xssf/usermodel/TestXSSFDrawing.java:485,512`는 텍스트박스의 여러 문단을 `Line 1\nLine 2\nLine 3`으로 기대한다. 이는 XLSX 도형에 실제 글자 구조가 있다는 근거다. 다만 이 기대값은 POI가 테스트 중 생성한 문서에 대한 단언으로, 위 실물 짝의 정답을 대신하지 않는다.

공개 `ConditionalFormattingSamples.xlsx`를 dochan XLSX 리더로 직접 읽었을 때 공통 16시트에 drawing 문단 63개가 있었고, 그중 XLS와 공통인 47개가 내용과 순서까지 일치했다. XLSX의 전체 18시트에는 drawing 문단 71개가 있었다. `tests/test_xlsx_reader.py`의 `test_reads_xlsx_drawing_textboxes_and_image_references`도 합성 XLSX 도형 글자 경로를 검사한다. 따라서 README의 같은 행 XLSX `—`도 구조 부재를 뜻하는 표기로는 맞지 않는다. 다만 XLSX 칸 전체에 대한 별도 공개 실물 코퍼스 검증 범위는 이 보고서의 1쌍보다 넓어야 하므로 XLSX 칸을 `✅`로 확정하자는 뜻은 아니다.

XLS 칸은 단위 테스트와 위 실물 검증을 모두 통과했으므로 README의 XLS `—`를 `✅`로 바꾸자고 제안한다. 실제 README 수정은 오케스트레이터가 검증 후 수행한다.
