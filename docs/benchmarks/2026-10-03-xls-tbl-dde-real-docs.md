# XLS 데이터 표와 DDE 이름 수식 실물 검증

2026년 10월 3일 공개 XLS 721파일의 FORMULA 95,932셀을 조사했다. 작업 전 기록의 수식 표시 94,433셀에서 1,489셀이 추가되어 95,922셀을 표시한다. 추가분은 TABLE 90셀과 DDE 1,399셀이다. 남은 10셀은 TABLE 레코드가 손상된 1셀, 해석하지 못한 PtgElf 1셀, 기존 출력 격자 상한에 걸린 8셀이다. 공개 문서를 저장소로 복사하지 않았고, 비교 중 Markdown·JSON 본문은 디스크에 쓰지 않았다.

## 표본과 판정

POI 표본은 `corpus/poi-src/test-data/spreadsheet/`, LibreOffice 표본은 `corpus/lo-src/sc/qa/unit/data/xls/` 아래에 있다. 아래 네 TABLE XLS 파일 모두 동명 XLSX 짝이 없다. 그러므로 TABLE 수식의 독립 OOXML 정답 일치율은 제시할 수 없다. 표의 기대는 공개 테스트의 레코드 수·좌표 단언과 원시 BIFF 바이트, 입력 셀 및 캐시 값의 관계를 구분해서 적었다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| XLS PtgTbl 행 입력 | `testArraysAndTables.xls` C27:E28 | POI `poi/src/test/java/org/apache/poi/hssf/record/aggregates/TestRowRecordsAggregate.java:69-78`은 TABLE 레코드 3개를 단언한다. 첫 TABLE은 `1a001b000204040019000100ffff0000`이고 B26을 입력으로 가리킨다. C26:E26에 3, 4, 50이 있으며 C27:E27의 캐시는 103a, 104a, 150a이다. | 두 행의 6셀에 `TABLE($B$26,)`를 표시하고 캐시를 보존한다. | 6셀 모두 수식을 표시했고 캐시가 유지됐다. | 원시 배치·셀 의미와 6/6셀 일치했다. 동명 XLSX 정답은 없다. |
| XLS PtgTbl 열 입력·두 입력 | `testArraysAndTables.xls` C33:E35 및 C41:F46 | 두 TABLE은 각각 B32, B38·B39를 입력으로 가리킨다. B33:B35는 3, 4, 50이며 C33:C35 캐시는 97, 96, 50이다. 두 입력 표에서는 행 머리값과 열 머리값을 함께 바꾼 캐시가 이어진다. | 9셀에 `TABLE(,$B$32)`, 24셀에 `TABLE($B$38,$B$39)`를 표시한다. | 33/33셀에 해당 식을 표시했다. | 원시 배치·셀 의미와 33/33셀 일치했다. 동명 XLSX 정답은 없다. |
| XLS PtgTbl 열 입력·두 입력 | `44958.xls` 두 완성 표 | POI `poi/src/test/java/org/apache/poi/hssf/usermodel/TestBugs.java:887-921`은 E4 수식 셀과 두 표 영역을 확인한다. 첫 TABLE의 원시 플래그는 `0x0000`이고 입력은 B5이다. 둘째는 `0x0008`이고 입력은 B7·B5이다. 둘째 표 E3:H3은 기간, D4:D9는 이율이며 E4:H9의 캐시가 이에 따라 바뀐다. | 첫 표 18셀에 `TABLE(,$B$5)`, 둘째 표 24셀에 `TABLE($B$7,$B$5)`를 표시한다. | 42/42셀에 해당 식을 표시했다. | 원시 배치·셀 의미와 42/42셀 일치했다. 동명 XLSX 정답은 없다. |
| XLS PtgTbl 열 입력·두 입력 | `data-table/mortgage.xls` | 원시 TABLE 두 개는 `02000400030300000200010084400000`, `08000a0003040c000900010008000100`이다. 각각 B3, B10·B9를 입력으로 가리킨다. | 9셀에 해당 `TABLE` 수식을 표시한다. | 9/9셀에 수식을 표시하고 캐시를 보존했다. | 원시 배치와 9/9셀 일치했다. 동명 XLSX 정답은 없다. |
| XLS PtgTbl 손상 표본 | `44958_1.xls` E4 | PtgTbl은 E4를 가리키지만 TABLE 레코드는 18바이트다. 위 정상 표본의 16바이트 배치와 다르고 입력 주소도 화면의 입력값과 맞지 않는다. | 잘못된 입력 주소를 수식으로 만들지 않고 캐시를 유지한다. | 기존 `$356.11 ` 캐시와 WARN을 유지했다. | 1셀은 복원하지 않았다. |
| XLS DDE NameX | `49219.xls` | 원시 SupBook은 `MTX\x03DATA`, `IDT\x03IMKB`이고 ExternName의 DDE 플래그는 `0x7FE2`이다. POI `poi/src/test/java/org/apache/poi/hssf/record/TestExternalNameRecord.java:104-126,159-172`는 DDE 이름 문자열과 값 본문이 없는 이름을 시험한다. | 사용된 NameX의 서비스·토픽·항목을 `서비스|토픽!항목`으로 내고 캐시를 유지한다. | 1,399/1,399셀에 수식이 추가됐다. 고유 표기는 602개이고 `MTX|DATA` 476개, `IDT|IMKB` 126개다. | 원시 문자열·인덱스·표기 조합과 1,399/1,399셀 일치했다. 독립 XLSX 짝은 없다. |
| XLS DDE `StdDocumentName` 및 OLE | `49219.xls` | ExternName의 `0x7FEA` 이름 2개는 `fOle` 비트가 켜진 DDE `StdDocumentName` 항목이며, 수식의 NameX가 가리키지 않는다. `fOleLink`가 실제 OLE 링크를 뜻한다는 근거는 리뷰어가 확인한 [MS-XLS] 2.4.105 요약이다. | DDE 항목과 OLE 링크를 구분한다. 실제 OLE 수식의 표기는 별도 표본이 필요하다. | `fOle` 항목은 DDE로 분류했으며 이 두 이름을 참조하는 수식은 0셀이다. | OLE 수식 표기는 미검증이다. |
| XLS PtgElf `18 0a` | `forum-mso-de-49320.xls` A3 | FORMULA 토큰 접두사는 `18 0a 02 00 01 80`이다. 현재 확인한 PtgElfLel `18 01`과 다른 하위 토큰이다. | 피연산자 배치와 표시 의미가 확인되기 전에는 캐시를 유지한다. | 1셀은 캐시를 유지하고 PtgElf WARN을 남겼다. | 미지원이며 미검증이다. |
| XLSX `dataTable` | 공개 POI XLSX 352파일 | ZIP으로 열 수 있는 335파일의 워크시트 XML에서 `f t="dataTable"`을 찾지 못했다. 나머지 17파일은 ZIP으로 열리지 않았다. | XLS와 같은 `TABLE(행입력,열입력)` 표시가 필요하다. | 합성 OOXML의 행·열·두 입력 테스트가 통과한다. | 공개 실물은 미검증이다. |

서비스·토픽·항목을 결합한 602개 표기의 전체 정렬 목록은 프로브의 `dde_unique_formulas` 배열에 있다. `scripts/probe_xls_tbl_dde.py`는 코퍼스 경로를 인자로 받아 같은 목록을 다시 만든다. 목록에는 DDE 항목 안에 들어 있는 쉼표도 원문 그대로 남겨 두었다. OLE 플래그가 있는 `StdDocumentName` 두 개는 실제 수식에서 참조되지 않으므로 DDE 검증 수에 넣지 않았다.

## 구현 판단과 제한

PtgTbl은 FORMULA의 5바이트 앵커를 해당 시트의 TABLE 범위 시작 좌표와 연결한다. TABLE 레코드가 첫 FORMULA 뒤에 나타나므로 캐시를 먼저 보관하고, TABLE을 읽은 뒤 범위 안의 이미 읽은 셀과 후속 셀에 같은 식을 붙인다. 레코드 길이·범위·앵커가 맞지 않으면 WARN과 캐시를 유지한다. 같은 앵커의 중복 TABLE은 경고 후 무시한다. 인접 셀을 새로 만들지 않고 실제 FORMULA 셀만 갱신한다. 보관하는 TABLE 셀은 시트당 200,000개로 제한한다.

TABLE 단일 입력 방향은 `fRw`(0x0004)로 결정하고, 예약 비트 0x0002는 무시한다. 이는 리뷰어가 원문을 확인해 전달한 [MS-XLS] 2.4.319 조항의 요약에 근거한다. 이번 작업에서 원문을 독립적으로 다시 확인하지 못했으므로 명세 근거는 2차 전달로 구분한다. 원시 바이트로 직접 확인한 공개 TABLE 8개의 플래그는 `44958.xls` 0x0000·0x0008, `testArraysAndTables.xls` 0x0004·0x0000·0x000c, `data-table/mortgage.xls` 0x0000·0x000c, 손상된 `44958_1.xls` 0x0003이다. 마지막 레코드는 18바이트여서 수식 대신 캐시를 유지한다. 네 파일 모두 동명 XLSX 짝이 없으며, XLSX `dataTable`의 실물 검증도 아직 없다.

DDE는 SupBook의 서비스·토픽과 ExternName의 항목을 XTI·NameX 인덱스로 결합한다. 토픽·항목에 쉼표나 공백 등 수식 구분자가 있으면 작은따옴표로 묶고 내부 따옴표를 중복한다. 이 표기는 Excel 화면에 대한 2차 자료에 근거하며, 독립 XLSX 짝은 없다. DDE 이름 뒤에 선택적 값 본문이 있어도 이름의 길이만 읽고 나머지 유한한 BIFF 레코드 안에 둔다. `fOle` DDE 항목은 표시하되 `fOleLink` OLE 링크와 그림 플래그는 캐시를 유지한다. 실제 OLE 링크 표본과 `18 0a`의 확인 가능한 토큰 구조가 없어 둘은 임의 표기를 만들지 않았다.

## 회귀와 재현

공개 POI 동명 XLS/XLSX 36쌍 중 수식이 있는 20쌍의 1,070셀을 다시 비교했다. 정확 일치 986셀, 공백 차이만 있는 73셀로 총 1,059셀이 기존과 동일하게 일치했고, 불일치 11셀도 그대로다. 이 36개 XLSX의 Markdown·JSON SHA-256은 작업 시작 HEAD와 각각 36/36파일에서 동일했다. POI XLSX 352개 중 읽을 수 있는 335개에는 `dataTable` 수식이 없으므로 XLSX 신규 분기의 실물 회귀는 확인하지 못했다.

공개 XLS 전수 프로브의 예외는 0개였다. 작업 전 기록의 미표시 1,499셀과 비교해 현재 미표시 10셀이다. HEAD와 현재 소스로 721파일의 Markdown·JSON SHA-256을 다시 계산했다. 716파일은 두 형식의 해시와 오류 개수가 모두 같았다. 차이가 난 5파일은 위 TABLE 4파일과 DDE 1파일뿐이다. 그중 손상된 `44958_1.xls`의 Markdown은 같고 JSON만 TABLE 경고 1개가 추가되어 바뀌었다. 전체 테스트는 4,542개 통과, 30개 건너뜀, 16개 예상 실패였으며 `ruff check dochan scripts tests`와 `git diff --check`도 통과했다.

```bash
/usr/bin/python3 -m scripts.probe_xls_tbl_dde corpus --output .codex-work/xls-tbl-dde-summary.json
/usr/bin/python3 -m scripts.probe_xls_formula_pairs corpus/poi-src/test-data/spreadsheet --output .codex-work/xls-pairs.json
/usr/bin/python3 -m scripts.probe_spreadsheet_hashes corpus --extension xls --output .codex-work/xls-current-hashes.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
git diff --check
```


## 정정(2026-10-03, 감수 반영 후)

위 표와 본문의 DDE 표기 서술 중 "`서비스|토픽!항목`으로 낸다", "쉼표도 원문 그대로", "OLE 플래그가 있는 `StdDocumentName`" 은 감수 반영 전 상태다.
지금은 `[A-Za-z0-9_.]` 밖의 글자가 있는 토픽·항목을 `'…'` 로 감싸고(안의 `'` 는 두 번), `fOle`(0x7FEA) 이름은 [MS-XLS] 2.4.105 대로 DDE
`StdDocumentName` 항목으로 본다(실물 수식 0셀이라 미검증). 데이터 표 방향은 TABLE(2.4.319)의 fRw·fTbl2 비트로만 정한다. 세부는
[수정 기록](2026-10-03-xls-tbl-dde-fix-real-docs.md).
