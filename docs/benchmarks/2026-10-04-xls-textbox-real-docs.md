# XLS 텍스트박스·도형 글자 실물 검증

2026년 10월 4일에 README `Supported Elements`의 XLS `텍스트박스/도형 텍스트` 칸을 검증했다. 기존 `—` 표기는 XLS의 시트 도형에도 `Obj`·`TxO` 글자가 있으므로 맞지 않는다. [MS-XLS] 2.4.181의 `Obj.ftCmo.ot`와 `TxO`·`Continue`, [MS-ODRAW]의 OfficeArt 클라이언트 앵커를 기준으로 구현했다. 메모형 `ot=0x0019`는 기존 셀 주석 경로에만 남겼다. 다른 개체형은 `TxO` 글자가 비어 있지 않을 때 XLSX 도형 글자와 같은 시트 `Paragraph`로 낸다. `OfficeArtClientData`와 `Obj`의 개수가 맞으면 같은 문서 순서로 연결해 앵커 행·열로 정렬하고, 대응을 확인할 수 없으면 시트 끝에 문서 순서로 둔다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLS 텍스트박스/도형 텍스트 | POI `ConditionalFormattingSamples.xls`와 같은 이름의 `.xlsx` | XLSX 리더의 drawing 문단 출력과 XLS 원시 `Obj`·`TxO`·`Continue`를 대조했다. | 두 형식에 공통으로 있는 16개 시트의 도형 문구 47개가 내용과 순서까지 같아야 한다. | 16개 시트에서 47/47개가 같은 순서로 일치했다. XLSX에만 있는 시트 2개와 XLS 머리글·바닥글은 비교에서 제외했다. | 통과했다. |
| XLS 텍스트박스/도형 텍스트 | 아래 목록의 POI 나머지 27파일 | 원시 BIFF8의 `ftCmo` 종류와 `TxO.cchText` 및 `Continue`의 압축·UTF-16 글자 바이트를 제품 판독 함수와 별도로 해독해 SHA-256으로 대조했다. | 차트 하위 스트림과 메모를 제외한 시트 개체 문구 601개가 문단에 남아야 한다. | 27파일의 601/601개가 문단 글자 해시와 개수까지 일치했다. | 통과했다. |
| XLS 텍스트박스/도형 텍스트 | 아래 목록의 LibreOffice 10파일 | 위와 같은 독립 원시 바이트 관찰을 사용했다. 이 10파일에는 같은 이름의 XLSX 짝이 없다. | 시트 개체 문구 22개가 문단에 남아야 한다. | 10파일의 22/22개가 문단 글자 해시와 개수까지 일치했다. | 통과했다. |

POI spreadsheet의 XLS 417개와 LibreOffice 코퍼스의 XLS 303개, 합계 720개의 Markdown을 변경 전 커밋과 변경 후 코드로 각각 만들어 UTF-8 SHA-256·문자 수·오류 목록만 보관했다. 출력 전문은 저장하지 않았다. 변경된 파일은 아래 38개뿐이며, 이 38개는 독립 원시 바이트 검사에서 시트의 비메모 문구가 확인된 파일과 정확히 같다. 나머지 682개의 Markdown 해시는 같고, 720개의 오류 목록도 모두 같다. 원시 CFB를 열 수 없어 바이트 검사를 완료하지 못한 파일은 39개(POI 6개, LibreOffice 33개)이며, 이 파일들의 Markdown 해시도 바뀌지 않았다. 실물에서 확인한 문구 670개는 32개의 서로 다른 문구 배열을 이룬다. 일부 공개 퍼징 표본의 중복을 독립 표본 수로 과장하지 않았다.

`python -m scripts.compare_office_pairs`로 POI spreadsheet의 이름이 같은 XLS/XLSX 36쌍을 전후 비교했다. 파싱 실패는 전후 모두 0개이고 평균 토큰 유사도는 0.9266에서 0.9273으로 변했다. 대상 `ConditionalFormattingSamples.xls` 짝은 0.9387에서 0.9626으로 변했다. 이 값은 도형 글자 외에 두 형식의 시트 수와 표 차이도 포함하므로 글자 정확도의 정답 지표로 쓰지 않았다. LibreOffice의 해당 XLS에는 같은 이름의 XLSX 짝이 없어서 별도 짝 점수는 만들지 않았다.

## 출력이 바뀐 공개 파일 전체

표의 개수는 차트 하위 스트림과 메모를 제외하고 `Obj`·`TxO`에서 읽은 시트 도형 문구 수다. 아래 POI 파일은 `corpus/poi-src/test-data/spreadsheet/`, LibreOffice 파일은 `corpus/lo-src/`에 있다.

| 코퍼스 | 파일 | 문구 수 |
| --- | --- | ---: |
| POI | `31749.xls` | 2 |
| POI | `37684-2.xls` | 170 |
| POI | `39512.xls` | 61 |
| POI | `39634.xls` | 1 |
| POI | `44010-SingleChart.xls` | 6 |
| POI | `44010-TwoCharts.xls` | 6 |
| POI | `45129.xls` | 30 |
| POI | `45538_form_Footer.xls` | 4 |
| POI | `45538_form_Header.xls` | 4 |
| POI | `45565.xls` | 2 |
| POI | `46137.xls` | 5 |
| POI | `50939.xls` | 1 |
| POI | `ConditionalFormattingSamples.xls` | 47 |
| POI | `LIBRE_OFFICE-94379-0.zip-57.xls` | 3 |
| POI | `StringContinueRecords.xls` | 6 |
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
| POI | `external_name.xls` | 1 |
| POI | `text.xls` | 1 |
| LibreOffice | `sc/qa/unit/data/xls/forum-mso-de-48440.xls` | 2 |
| LibreOffice | `sc/qa/unit/data/xls/forum-mso-en4-102737.xls` | 2 |
| LibreOffice | `sc/qa/unit/data/xls/forum-mso-en4-109082.xls` | 1 |
| LibreOffice | `sc/qa/unit/data/xls/forum-mso-en4-368528.xls` | 1 |
| LibreOffice | `sc/qa/unit/data/xls/opencl/logical/xor.xls` | 1 |
| LibreOffice | `sc/qa/unit/data/xls/opencl/math/sumproductTest.xls` | 1 |
| LibreOffice | `sc/qa/unit/data/xls/pictureOrder.xls` | 9 |
| LibreOffice | `sc/qa/unit/data/xls/pivottable_dates_grouping.xls` | 2 |
| LibreOffice | `sc/qa/unit/data/xls/tdf120177.xls` | 2 |
| LibreOffice | `sc/qa/unit/data/xls/tdf170285_controlsInGroupShape.xls` | 1 |

`12843-1.xls`의 비메모 `TxO` 네 개와 `forum-mso-de-48440.xls`의 19개는 워크시트 도형이 아니라 차트 `BOF(0x0020)` 하위 스트림에 있다. 이를 시트 텍스트박스 집계에 넣지 않았다. 스캔의 차트 경계는 BIFF `BOF`·`EOF` 중첩으로 판정했고, 구현도 기존 차트 하위 스트림 구분을 유지한다. 공개 XLSX 짝이 없는 37파일의 원본 화면 배치·서식까지 같다고 주장하지 않는다. 이번 칸은 단위 테스트와 실물 글자 보존 검증을 모두 통과했으므로 README의 XLS `—`를 `✅`로 바꾸자고 제안한다.
