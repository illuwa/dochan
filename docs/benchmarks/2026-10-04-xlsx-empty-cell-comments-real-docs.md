# XLSX 빈 셀 메모 실물 검증 (2026-10-04)

시트 XML에 `<c>`가 없는 좌표의 메모를 표에 실체화하여 누락을 해결했다. 메모만 있는 행도 같은 경로로 만든다. 표 범위는 dimension의 선언값 대신 실제 셀 내용과 메모 좌표로 정하며, 기존 값·수식·서식·링크·출처는 그대로 유지한다. README는 수정하지 않았으며 주석/코멘트 · XLSX의 기존 ✅ 유지를 제안한다.

## 검증 범위와 독립 정답

네트워크를 사용하지 않고 `corpus/poi-src/`와 `corpus/lo-src/`에 존재하는 `.xlsx`·`.xlsm`을 전수 열거했다. POI에는 XLSX 352개와 XLSM 14개가 있었고, 이 LibreOffice 체크아웃에는 해당 확장자가 0개였다. 따라서 결과는 현재 로컬에 있는 366개에 대한 전수 검증이며 LibreOffice XLSX·XLSM 실물 검증은 미검증이다. POI에 포함된 `LIBRE_OFFICE-128382-0.xlsx`는 별도로 검증했다.

`scripts/probe_xlsx_empty_comments.py`는 기존 `scripts/comment_probe_common.py`의 독립 Expat 정답지를 재사용한다. workbook의 시트 목록과 시트별 관계를 따라 연결된 일반 comments 파트만 읽고, 작성자 배열과 authorId, ref와 text의 일반·리치 텍스트를 직접 대조한다. 제품 코드 import는 정답을 읽은 뒤 출력 대조 단계에만 있다. 시트 관계에 연결되지 않은 comments 파일은 세지 않는다. ZIP 역슬래시 이름을 정규화하고, 중복 정규화 이름은 모호한 입력으로 거부한다. DTD·ENTITY를 파싱 전에 거부하고 XML 크기 16MiB·깊이 128·요소 20만 개, ZIP 항목 10만 개·확장 크기 128MiB 상한을 둔다. 검증 과정에서 다른 프로젝트의 구현 코드는 읽지 않았다.

독립 정답은 347문서에서 확정했다. 이 중 27문서에 메모 204개가 있고, 나머지 320문서에는 연결된 메모가 없다. 값이 없는 셀의 메모는 17개이며 그중 `<c>` 자체가 없는 것은 16개이다. 19문서는 암호화·손상·중복 파트 때문에 독립 정답 미검증으로 구분했다. 미검증 문서를 메모 0개로 세지 않았다.

## 전후 결과

| 항목 | 수정 전 | 수정 후 | 판정 |
|---|---:|---:|---|
| 독립 XML의 일반 메모 총수 | 204개 | 204개 | 원본은 바꾸지 않았다. |
| 값 없는 셀의 메모 총수 | 17개 | 17개 | 빈 셀 판정은 원시 시트 XML에 근거했다. |
| 출력에 나온 일반 메모 | 188개 | 204개 | 작성자·본문·시트·셀 위치 204/204개가 일치했다. |
| 출력에 나온 값 없는 셀 메모 | 1개 | 17개 | 17/17개가 일치했다. |
| `<c>` 없는 셀의 메모 출력 | 0개 | 16개 | 16/16개가 복원됐다. |
| 누락 | 16개 | 0개 | 독립 정답이 있는 표본에서 누락이 없다. |
| 잘못된 위치·본문 또는 추가 메모 | 0개 | 0개 | 수정 후 메모 양성 27/27문서가 완전히 일치했다. |
| XLS↔XLSX 두 짝의 원시 공통 메모 | 6/6개 | 6/6개 | 원시 정답의 내용은 같다. |
| XLS↔XLSX 두 짝의 제품 공통 메모 | 4/4개 | 6/6개 | `comments.xlsx`의 A1·A4가 추가됐다. |

## 칸별 실물 검증 표

아래 파일은 모두 POI 공개 `test-data/spreadsheet/`의 표본이다. XLSM은 XLSX와 같은 리더를 쓰므로 함께 확인했다. 정답 근거의 관계·원시 XML은 제품 코드와 독립적으로 읽었다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 주석/코멘트 · XLSX | `45544.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 3개가 원래 셀에 있어야 한다. | 3/3개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `48539.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `48923.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `50795.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `51850.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `52425.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 1개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `55745.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `55814.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `56017.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. POI `TestXSSFSheetShiftRows.java:165-175`의 A1·작성자·본문 기대값도 확인했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 1개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `56644.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 11개가 원래 셀에 있어야 한다. | 11/11개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `57181.xlsm` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 139개가 원래 셀에 있어야 한다. | 139/139개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `57828.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 2개가 원래 셀에 있어야 한다. | 2/2개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `57838.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 2개가 원래 셀에 있어야 한다. | 2/2개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `59388.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 2개가 원래 셀에 있어야 한다. | 2/2개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `59687.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `64759.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 2개가 원래 셀에 있어야 한다. | 2/2개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `DataValidationEvaluations.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 1개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `ExcelWithAttachments.xlsm` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 3개가 원래 셀에 있어야 한다. | 3/3개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `FormulaEvalTestData_Copy.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `LIBRE_OFFICE-128382-0.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `SimpleWithComments.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 3개가 원래 셀에 있어야 한다. | 3/3개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `WithMoreVariousData.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 3개가 원래 셀에 있어야 한다. | 3/3개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `WithVariousData.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 2개가 원래 셀에 있어야 한다. | 2/2개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `bug66827.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 1개가 원래 셀에 있어야 한다. | 1/1개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `commentTest.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 14개가 원래 셀에 있어야 한다. | 14/14개가 일치했고 빈 셀 메모 12개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `comments.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. POI `TestXSSFReader.java:175-196`의 3개 기대값도 확인했다. | 3개가 원래 셀에 있어야 한다. | 3/3개가 일치했고 빈 셀 메모 2개를 포함했다. | 통과했다. |
| 주석/코멘트 · XLSX | `right-to-left.xlsx` | 시트 관계로 연결된 comments XML의 ref·authorId·text를 독립 해독했다. | 2개가 원래 셀에 있어야 한다. | 2/2개가 일치했고 빈 셀 메모 0개를 포함했다. | 통과했다. |

`comments.xlsx`는 A1·A3·A4의 작성자 Sven Nissel과 본문을 모두 같은 셀에 낸다. A1·A4에는 시트 XML의 `<c>`가 없고 기존 출력에서는 A3만 있었다. `commentTest.xlsx`는 메모 14개 중 `<c>` 없는 12개가 누락되던 것이 14개 모두 출력된다. `52425.xlsx`와 `56017.xlsx`는 메모만 있는 시트에도 표가 생겼다. 본문은 기존 계약대로 양끝 공백을 제거하고 줄바꿈을 모델·JSON에 보존하며 Markdown에서 공백으로 접는다.

## 출력 회귀와 기존 내용 보존

366개 전체의 Markdown·JSON SHA-256과 오류 목록을 수정 전후 수집했다. 바뀐 파일은 다음 4개뿐이며 모두 `<c>` 없는 메모가 있는 문서다. 나머지 362개는 두 출력 해시가 동일하다. 오류 목록은 366/366개가 동일하다. XLSM 14개는 모두 출력 해시가 같다.

| 공개 파일 | 메모 출력 전 → 후 | 추가 좌표 | Markdown 문자 수 전 → 후 | JSON 문자 수 전 → 후 |
|---|---|---|---:|---:|
| `52425.xlsx` | 0 → 1개 | A4이다. | 0 → 53 | 441 → 2,991 |
| `56017.xlsx` | 0 → 1개 | A1이다. | 14 → 59 | 1,534 → 3,544 |
| `commentTest.xlsx` | 2 → 14개 | A1·B1·B2·A3·B3·A4·A5·B5·A7·B7·A8·B8이다. | 173 → 793 | 6,123 → 28,471 |
| `comments.xlsx` | 1 → 3개 | A1·A4이다. | 111 → 209 | 8,968 → 12,460 |

기존 내용 검사는 새로 실체화한 메모 좌표만 제외하고, 기존 비어 있지 않은 셀의 좌표·본문·런·서식·병합 정보·출처와 표 밖 요소 전체의 정규화 JSON 해시를 비교했다. 메모 양성 27/27문서가 동일하다. 정규화 검사가 기존 셀 값 변경을 탐지한다는 합성 테스트도 통과했다.

또한 기준 커밋 `a30fdbde8a1b1d89d9ad72312fbb932111feb095`의 XLSX 리더 소스 한 사본으로 바뀐 네 문서를 다시 읽었다. 새 메모 16개의 본문을 원시 정답과 비교하고, 나머지 모든 기존 셀의 전체 JSON이 동일한지 검사했다. 새 표·추가 격자·메모 셀을 수정 전 상태로 되돌린 JSON은 네 문서 모두 수정 전 전체 JSON과 완전히 동일했다. 메모 추가 외의 본문·서식·출처·다른 요소 변경은 없다.

기존 `scripts/probe_xls_comment_cells.py`로 POI XLS 417개를 전후 다시 읽었으며 Markdown·JSON 해시와 오류 목록은 417/417개가 같다. `SimpleWithComments.xls`↔`.xlsx`는 계속 3/3개가 같고, `comments.xls`↔`.xlsx`의 제품 공통 메모는 1/1개에서 3/3개로 늘었다. XLS 파서는 수정하지 않았다.

## 합성 테스트와 출력 계약

제품 수정 전에 `tests/test_xlsx_empty_comments.py`를 실행하여 17개 실패·3개 통과를 확인했다. 시트에 셀이 없는 경우, row가 없는 경우, dimension과 마지막 값 셀 밖의 메모, 메모만 있는 시트, 병합 영역의 앵커와 가려진 셀, 숨김·veryHidden, 대형 시트 미리보기, 격자 상한 초과·정확한 경계, 잘못된 참조와 스레드 메모 공존을 검사한다. JSON은 셀·문단·런에 같은 출처를 보존한다. 새 테스트의 초기 JSON 문자열 개수 단언은 JSON이 같은 본문을 셀·문단·런에 반복 저장하므로 부정확했다. 이를 실제 셀 JSON의 본문·위치 검사로 고쳤으며 기존 테스트 단언은 변경하지 않았다.

병합 영역의 앵커는 기존 row_span·col_span을 유지한다. 가려진 셀은 메모와 출처를 JSON에 보존하면서 span 0을 유지하며, 기존 Markdown 렌더러처럼 해당 셀 내용을 표시하지 않는다. 이 제한을 해소하려고 메모를 병합 앵커로 옮기거나 공유 출력 코드를 변경하지 않았다. 대형 시트 미리보기는 기존 메모 생략 경고를 유지한다. 메모를 포함한 격자가 20만 셀을 넘으면 새 셀·격자를 할당하기 전에 기존 `ERR: XLSX dense cell limit exceeded`를 남기고 해당 표를 생략한다. 다른 시트의 처리는 계속한다. 스레드 메모는 기존처럼 읽지 않으며, 같은 셀의 일반 메모를 대체하거나 중복하지 않는다.

`tests/test_xlsx_empty_comment_probe.py`는 제품 import 금지, 관계 없는 파트 무시, 역슬래시 ZIP 이름, 위치·본문 불일치 탐지, 기존 내용 해시와 메모만 있는 새 표의 정규화를 검사한다. 독립 XML 정답지의 DTD·ENTITY·깊이 상한은 기존 `tests/test_comment_cell_probes.py`도 검증한다. 제품·프로브 새 합성 사례는 총 26개가 통과했다.

최종 전체 테스트는 5,549개 통과·36개 건너뛰기·14개 예상 실패였고 61.79초가 걸렸다. `ruff check dochan scripts tests`와 로컬 경로 금지 검사도 통과했다.

## 독립 정답 미검증 19문서

| 표본 | 관찰 | 판정 |
|---|---|---|
| `58616.xlsx`, `protected_passtika.xlsx` | OLE의 EncryptionInfo·EncryptedPackage가 있어 원시 ZIP comments XML을 직접 읽을 수 없다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx` | 손상 OLE 암호 패키지이며 제품도 패키지 길이·섹터 경고를 남긴다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `duplicate-filename.xlsx`, `duplicate-filename-case-insensitive.xlsx` | 동일하거나 대소문자 정규화 후 같은 ZIP 파트가 있다. | 독립 정답지는 모호한 입력을 거부한다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIFuzzer-5040805309710336.xlsx` | ZIP 안에는 word 파트가 있으며 xl/workbook.xml이 없다. 일부 ZIP 헤더도 손상됐다. | XLSX 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIXSSFFuzzer-4828727001088000.xlsx` | ZIP 중앙 디렉터리의 서명이 손상됐다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIXSSFFuzzer-5089447305609216.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIXSSFFuzzer-5185049589579776.xlsx` | ZIP 중앙 디렉터리의 서명이 손상됐다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIXSSFFuzzer-6123461607817216.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIXSSFFuzzer-6419366255919104.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-POIXSSFFuzzer-6448258963341312.xlsx` | ZIP 중앙 디렉터리의 서명이 손상됐다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5025401116950528.xlsx` | ZIP 중앙 디렉터리의 서명이 손상됐다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5542865479270400.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5636439151607808.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6504225896792064.xlsx` | ZIP 중앙 디렉터리의 서명이 손상됐다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6594557414080512.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `crash-274d6342e4842d61be0fb48eaadad6208ae767ae.xlsx` | ZIP 중앙 디렉터리의 서명이 손상됐다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |
| `deep-data.xlsx` | 정상 ZIP 컨테이너로 열리지 않는다. | 원시 메모 정답은 미검증이다. 출력 회귀 해시는 같다. |

제품 처리 예외·시간 초과는 366개에서 0건이었다. 독립 정답 미검증을 제외한 메모 양성 문서에는 남은 누락·본문·위치 불일치가 없다. 실제 `<row>` 전체가 없는 메모, 병합에 가려진 셀, 대형 미리보기 경로, 스레드 메모는 이 공개 메모 표본에서 별도 양성 검증을 확보하지 못했으므로 해당 경계는 합성 테스트로만 확인했다.

## 재현 명령과 산출물

동일한 프로브를 수정 전 코드와 수정 후 코드에서 각각 실행했다. roots의 순서는 고정하며 모든 코퍼스 경로는 명령 인자로 전달한다.

```sh
/usr/bin/python3 -m scripts.probe_xlsx_empty_comments corpus/poi-src corpus/lo-src --output .codex-work/xlsx-before.json
/usr/bin/python3 -m scripts.probe_xlsx_empty_comments corpus/poi-src corpus/lo-src --output .codex-work/xlsx-after.json
/usr/bin/python3 -m scripts.probe_xls_comment_cells corpus/poi-src/test-data/spreadsheet --output .codex-work/xls-pairs-before.json
/usr/bin/python3 -m scripts.probe_xls_comment_cells corpus/poi-src/test-data/spreadsheet --output .codex-work/xls-pairs-after.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

프로브는 원본 출력을 전수 저장하지 않고 SHA-256·문자 수·오류·메모 요약만 저장한다. 네 문서의 차이 출력만 `.codex-work/differences/`에 남겼다. 전후 JSON 요약·소스 기준 사본·추가만 있었는지 확인한 검사와 `.codex-work/summary.json`은 워크트리의 제외 경로에 남겼다. pytest 임시 파일은 검증 후 삭제한다. 실물 파일을 저장소에 복사하지 않았다. 새 런타임 의존성과 공유 모델·출력·패키지 파일 변경은 없다.
