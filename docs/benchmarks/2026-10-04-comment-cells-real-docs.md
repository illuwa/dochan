# PPT·XLS·PPTX 주석/코멘트 실물 검증

2026-10-04에 공개 POI·LibreOffice 코퍼스만 읽어 검증했다. 코퍼스를 저장소에 복사하지 않았고 내부 문서는 사용하지 않았다. 세 형식은 이미 메모를 읽고 있었으며 독립 대조에서 제품 결함이 발견되지 않아 런타임 코드를 바꾸지 않았다. README의 `—`는 구조 부재를 뜻하므로 세 칸을 지원 범위 각주 9가 있는 ✅로 고쳤다.

## 판정과 분모

| 칸 | 조사 문서 수 | 실물 정답과 결과 | 판정 |
| --- | --- | --- | --- |
| PPT 주석/코멘트 | POI 145개·LO 75개로 총 220개이다. | 완결된 Comment10 후보가 있는 3문서의 최신 메모 8/8개가 작성자·본문·슬라이드·순서까지 일치했다. | Comment10 범위에서 ✅로 판정했다. |
| PPTX 주석/코멘트 | POI 95개·LO 449개로 총 544개이다. | 메모 XML이 있는 5문서 중 4문서에 원시 메모 10개가 있고, 그중 비어 있지 않은 본문 8/8개가 일치했다. 남은 1문서는 빈 목록이며 출력도 0개이다. | 구형 `p:cmLst` 범위에서 ✅로 판정했다. |
| XLS 주석/코멘트 | POI 417개·LO 303개로 총 720개이다. | NOTE가 있는 34문서에 원시 헤더 511개가 있다. 정상 32문서의 509/509개는 독립 원시 정답과 일치했고, 암호화 1문서의 1개는 POI 기대값과 별도로 일치했다. 손상 1개는 제외했다. | BIFF8 범위에서 ✅로 판정했다. |

이 비율은 공개 코퍼스의 확인된 메모에 대한 값이며 모든 Office 버전·암호·손상 형태의 완전 지원을 뜻하지 않는다. PPT 양성 3문서는 작성자 3명, 여러 슬라이드, 같은 슬라이드의 여러 메모, 여러 줄 본문, 최신 저장 이력 선택을 포함한다. PPTX 양성 4문서는 작성자 id 대응, 여러 슬라이드, 같은 슬라이드의 여러 메모와 빈 본문을 포함한다. 표본이 없는 최신 스레드 메모와 BIFF5 이하 메모는 ✅의 범위에 넣지 않았다.

## 정답을 만드는 방법과 출력 계약

`scripts/probe_presentation_comments.py`와 `scripts/probe_xls_comment_cells.py`의 정답 함수는 제품 코드를 불러 쓰지 않는다. 검증용 `olefile`은 OLE 운반층의 스트림만 꺼낸다. 그 뒤의 PPT·BIFF 레코드 해독은 명세와 바이트 관찰을 근거로 직접 작성했다. XML은 DTD·엔티티를 파싱 전에 거부하는 독립 Expat 정답지로 읽는다. 다른 프로젝트의 구현 코드는 읽지 않았으며 POI 테스트의 기대 문자열·개수·셀 좌표만 사용했다. 제품 import는 정답 해독이 끝난 뒤 출력 대조 함수에서만 한다. `olefile`을 런타임 의존성에 추가하지 않았다.

PPT는 [MS-PPT] CurrentUserAtom의 최신 편집 위치에서 UserEditAtom·PersistDirectoryAtom을 따라 최신 객체를 고르고, SlideListWithText 순서로 슬라이드 위치를 정했다. `___PPT10` ProgBinaryTag의 BinaryTagData에서 Comment10(12000)을 찾아 CString instance 0/1/2의 작성자·본문·이니셜과 Comment10Atom(12001)의 번호·SYSTEMTIME·x/y를 독립 해독했다. 별도로 스트림 전체의 완결된 Comment10 후보도 조사했다. `hang-22.ppt`의 물리 기록 7개 중 과거 저장의 2개를 제외한 최신 5개만 제품에 있어야 한다. RoundTripCustomTableStyles12(1064)는 recVer가 0xF이지만 ZIP payload이므로 내부 PPT 레코드로 오해하지 않는다.

PPTX는 `presentation.xml`의 슬라이드 목록과 관계를 따라 메모 파트를 읽고, `commentAuthors.xml`의 id를 작성자 이름에 대응했다. 메모의 XML 나열 순서를 유지하며 idx 값이나 ZIP 파일명순으로 재정렬하지 않는다. 공개 메모 파트 5문서는 모두 구형 `p:cmLst`이다. `modernComment_*.xml` 또는 `p188:cmLst`의 공개 표본은 0개이고 제품에도 이를 읽는 코드가 없으므로 새 구현을 추가하지 않았다. `tdf91060.pptx`의 빈 본문 2개와 `tdf173266.pptx`의 빈 목록은 기존 계약대로 생략된다.

XLS는 [MS-XLS] BoundSheet8의 시트 순서와 NOTE의 행·열·작성자·객체 id를 읽고, Obj.ftCmo의 메모 객체 id를 TxO.cchText·Continue에 대응했다. 문자열이 Continue 경계에서 압축 문자와 UTF-16 사이를 바꾸거나 서로게이트 쌍이 갈라져도 최종 UTF-16 코드 단위열로 해독했다. NOTE 저장 순서와 셀 출력 순서는 다를 수 있으므로 표 출력 계약에 따라 시트 안에서 행·열순으로 대조했다. 셀 안 본문에 작성자 이름이 이미 있으면 중복을 제거하지 않는다.

출력은 기존 `[comment: 작성자: 본문]` 계약이며 작성자나 본문이 없으면 기존 형식의 나머지 문구만 쓴다. PPT·PPTX는 본문이 없는 메모를 생략한다. PPT·PPTX의 슬라이드 provenance와 XLS의 시트·셀 provenance를 대조했다. PPT·PPTX의 화면 x/y·시각·이니셜은 원시 정답에 기록하지만 제품 모델의 출력 필드가 아니므로 출력 일치율에는 포함하지 않는다. PPT·XLS의 CR·CRLF는 LF로 정규화하며, 표 안의 LF는 모델·JSON에서 보존하고 Markdown 렌더러가 공백으로 접는다.

정답지에는 파일·OLE 스트림 128 MiB, XML 파트 16 MiB, ZIP 항목 100,000개·총 해제 크기 128 MiB, 레코드 1,000,000개, PPT 중첩 깊이 64, XML 깊이 128·요소 200,000개 상한이 있다. 파일별 제품 대조는 격리 프로세스와 60초 제한을 쓴다. 손상된 정답지는 오류로 기록하며 일치 판정으로 바꾸지 않는다.

## 표본별 검증

표본 파일은 `corpus/poi-src` 또는 `corpus/lo-src`의 공개 자료이다. POI 테스트 근거는 해당 코퍼스의 `poi-scratchpad/src/test/java/org/apache/poi/hslf/extractor/`, `poi-ooxml/src/test/java/org/apache/poi/xslf/usermodel/`, `poi/src/test/java/org/apache/poi/hssf/usermodel/` 아래에 있다. LO의 `pass/` 표본도 독립 원시 레코드로 판단했으며 이름만으로 정상 또는 손상을 결정하지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PPT 주석/코멘트 | `45543.ppt` | Comment10 CString(instance 0/1/2)·Comment10Atom과 최신 persist/SlideListWithText 순서이다. POI `TestExtractor.java:267-277`의 `testdoc` 및 `45545_Comment.pptx`와도 일치했다. | 2개 메모가 원시 순서의 슬라이드에 연결되어야 한다. | 작성자·본문·슬라이드·출력 순서 2/2개가 일치했다. | 통과했다. |
| PPTX 주석/코멘트 | `45545_Comment.pptx` | `presentation.xml`·슬라이드 관계와 `p:cmLst`·작성자 id 대응의 독립 XML 해독이다. POI `TestXMLSlideShow.java:156-179`의 두 슬라이드·작성자·본문 기대값과도 같다. | 2개 원시 메모 중 비어 있지 않은 본문 2개를 순서대로 내야 한다. | 작성자·본문·슬라이드·출력 순서 2/2개가 일치했다. | 통과했다. |
| PPT 주석/코멘트 | `WithComments.ppt` | Comment10 CString(instance 0/1/2)·Comment10Atom과 최신 persist/SlideListWithText 순서이다. POI `TestExtractor.java:254-262`의 본문 단언과도 일치했다. | 1개 메모가 원시 순서의 슬라이드에 연결되어야 한다. | 작성자·본문·슬라이드·출력 순서 1/1개가 일치했다. | 통과했다. |
| PPT 주석/코멘트 | `hang-22.ppt` | Comment10 CString(instance 0/1/2)·Comment10Atom과 최신 persist/SlideListWithText 순서이다. | 5개 메모가 원시 순서의 슬라이드에 연결되어야 한다. 물리 기록 7개 중 과거 저장의 2개는 제외되어야 한다. | 작성자·본문·슬라이드·출력 순서 5/5개가 일치했다. | 통과했다. |
| PPTX 주석/코멘트 | `tdf173266.pptx` | `presentation.xml`·슬라이드 관계와 `p:cmLst`·작성자 id 대응의 독립 XML 해독이다. | 0개 원시 메모 중 비어 있지 않은 본문 0개를 순서대로 내야 한다. | 원시 목록과 제품 출력 모두 메모가 0개였다. | 통과했다. |
| PPTX 주석/코멘트 | `pres-with-notes.pptx` | `presentation.xml`·슬라이드 관계와 `p:cmLst`·작성자 id 대응의 독립 XML 해독이다. | 2개 원시 메모 중 비어 있지 않은 본문 2개를 순서대로 내야 한다. | 작성자·본문·슬라이드·출력 순서 2/2개가 일치했다. | 통과했다. |
| PPTX 주석/코멘트 | `tdf89064.pptx` | `presentation.xml`·슬라이드 관계와 `p:cmLst`·작성자 id 대응의 독립 XML 해독이다. | 1개 원시 메모 중 비어 있지 않은 본문 1개를 순서대로 내야 한다. | 작성자·본문·슬라이드·출력 순서 1/1개가 일치했다. | 통과했다. |
| PPTX 주석/코멘트 | `tdf91060.pptx` | `presentation.xml`·슬라이드 관계와 `p:cmLst`·작성자 id 대응의 독립 XML 해독이다. | 5개 원시 메모 중 비어 있지 않은 본문 3개를 순서대로 내야 한다. | 작성자·본문·슬라이드·출력 순서 3/3개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `15228.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 29개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 29/29개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `29982.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 2개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 2/2개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `33082.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 24개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 24/24개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `34775.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 10개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 10/10개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `36947.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 129개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 129/129개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `37684-1.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 61개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 61/61개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `37684.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 61개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 61/61개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `41139.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `44200.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `44201.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `46250.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `47251_1.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `47847.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 10개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 10/10개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `47924.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. POI `TestHSSFComment.java:71-99`의 A1·A2·A3·C3·B5·C6 본문 6개도 같다. | 메모 6개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 6/6개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `48026.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 2개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 2/2개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `50833.xls` | POI `TestBugs.java:1701-1725`의 A1·작성자 `Robert Lawrence`·본문 기대값이다. | `[comment: Robert Lawrence: Robert Lawrence:\ntest comment]`가 A1에 있어야 한다. | 시트·셀·작성자·본문 1/1개가 기대값과 같았다. | POI 기대값 대조는 통과했다. FILEPASS 암호화 원시 본문은 미검증이다. |
| XLS 주석/코멘트 | `51461.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `53446.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 42개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 42/42개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `53972.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `59858.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `Basic_Expense_Template_2011.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 5개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 5/5개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `DrawingAndComments.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 3개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 3/3개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `FormulaEvalTestData.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `SimpleWithComments.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. 동명 XLSX 원시 XML 3/3개, 제품 출력 공통 메모 3/3개도 일치했다. | 메모 3개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 3/3개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `StringContinueRecords.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls` | 완결된 NOTE 헤더 1개 이후의 BIFF 레코드가 잘린 원시 바이트이다. | 손상 메모의 작성자·본문·셀은 완전 판정할 수 없다. | 제품 메모는 0개이며 문서 경고가 남았다. | 미검증이다. 지원 비율에서 제외했다. |
| XLS 주석/코멘트 | `comments.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. 동명 XLSX 원시 XML 3/3개, 제품 출력 공통 메모 1/1개도 일치했다. | 메모 3개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 3/3개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `drawings.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. POI `TestHSSFComment.java:364-374`의 comments 시트 B3·작성자·본문도 같다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `external_image.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `florida_data.ashx.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 41개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 41/41개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `forum-en-29552.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `forum-mso-en4-368528.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `pictureOrder.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 63개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 63/63개가 일치했다. | 통과했다. |
| XLS 주석/코멘트 | `universal-content.xls` | NOTE 작성자·셀 좌표와 Obj.id·TxO.cchText·Continue 원시 바이트의 독립 해독이다. | 메모 1개가 원래 셀에 있어야 한다. | 작성자·본문·셀 위치·행열 출력 순서 1/1개가 일치했다. | 통과했다. |

## 제외 표본과 정답의 한계

PPT 220개 중 150개는 구조를 끝까지 독립 해독했다. 70개는 잘린 PPT 레코드 51개, PowerPoint 스트림 부재 8개, 비-OLE 파일 8개, 스트림 대신 저장소인 항목 2개, 잘못된 DIFAT 1개로 독립 구조 정답을 만들지 못했다. 접근 가능한 PowerPoint 스트림에는 별도의 완결된 Comment10 후보 스캔도 적용했고 양성은 위 3문서뿐이었다. 독립 구조 해독이 안 된 문서의 제품 메모 출력은 모두 0개이지만 이를 정상 메모의 통과 증거로 세지 않았다. 암호화 문서의 숨은 메모 유무도 이 스캔으로 증명하지 않는다.

PPTX 544개 중 ZIP을 열 수 없는 11개는 독립 XML 정답을 만들지 못했다. 메모 XML이 있는 공개 5문서는 모두 해독했다. XLS 720개 중 49개는 OLE 또는 BIFF 손상·BIFF5 문자열 차이 등으로 전체 독립 정답을 만들지 못했다. 그중 NOTE가 관찰된 손상 퍼저 표본 1개와 별도의 FILEPASS 암호화 표본 1개만 원시 양성 대조에서 제외했다. `50833.xls`의 NOTE 헤더 1개와 제품 출력은 보지만 암호화 본문을 제품 복호화기로 독립 정답처럼 읽지 않았다. 대신 POI `TestBugs.java:1701-1725`의 A1·작성자·본문 기대값으로 1개를 별도로 확인했다. `56450.xls`는 POI `TestBugs.java:2044-2059`의 메모 0개 기대값과 일치한다.

POI XLS↔XLSX 두 짝의 원시 XML 공통 메모는 6/6개, 양쪽 제품 출력의 공통 메모는 4/4개가 일치했다. `SimpleWithComments`는 둘 다 3개를 낸다. `comments.xlsx` 원본 XML에는 A1·A3·A4의 3개가 있지만 제품은 A3의 1개만 낸다. 따라서 이전 `2026-10-04-xls-cell-notes-real-docs.md`에서 A1·A4를 XLS에만 있는 원본 차이로 판정한 부분은 이번 독립 XML 증거로 철회한다. XLS는 원시 세 메모를 모두 원래 셀에 내므로 XLS 검증은 통과한다. XLSX의 두 빈 셀 메모 누락은 이번 배정 칸 밖의 남은 결함이며 제품 코드나 기존 단언을 바꾸지 않았다.

## 단위 테스트와 변이 검사

기존 PPT `test_review_latest_slide_comments_match_pptx_contract`·`test_review_multiline_comment_is_one_pptx_compatible_paragraph`, PPTX `test_reads_pptx_slide_comments_from_relationship`, XLS `test_xls_notes_join_obj_txo_and_note_by_id_with_mixed_continue_encodings` 등의 합성 테스트가 이미 있었다. 기존 단언은 수정하지 않았다. 새 `tests/test_comment_cell_probes.py`의 10개 실행 사례는 최신 저장 선택·슬라이드 및 메모 나열 순서·작성자 id·셀 id 대응·서로게이트 경계·독립 해독의 제품 import 금지·RoundTrip ZIP payload·DTD/엔티티 및 깊이 거부·잘못된 위치/본문의 불일치 탐지를 확인한다.

PPT 메모 목록을 빈 목록으로 만드는 변이, PPTX 작성자 사전을 빈 사전으로 만드는 변이, XLS TxO 본문을 빈 문자열로 만드는 변이를 각각 별도 pytest 프로세스의 플러그인으로 주입했다. 세 기존 테스트는 모두 실제 단언 실패로 종료했다(각 1 failed, 종료 코드 1). 런타임 파일은 변이하지 않았다. 변이를 제거한 관련 테스트는 97개가 통과했다. 전체 테스트는 5,513 passed, 36 skipped, 14 xfailed였고 `ruff check dochan scripts tests`도 통과했다.

## 변경 전후 출력과 재현

| 형식 | 전체 문서 수 | Markdown SHA-256 변경 | JSON SHA-256 변경 | 오류·경고 변경 | 문서 처리 예외·시간 초과 |
| --- | --- | --- | --- | --- | --- |
| PPT | 220개이다. | 0개이다. | 0개이다. | 0개이다. | 전후 모두 0개이다. |
| PPTX | 544개이다. | 0개이다. | 0개이다. | 0개이다. | 전후 모두 0개이다. |
| XLS | 720개이다. | 0개이다. | 0개이다. | 0개이다. | 전후 모두 0개이다. |

변경된 문서는 0개이므로 별도의 전체 출력 파일을 남기지 않았다. `.codex-work/full-before.jsonl`·`full-after.jsonl`에는 Markdown 해시·문자 수·진단만, `presentation-before.json`·`presentation-after.json`·`xls-before.json`·`xls-after.json`에는 JSON 해시·문자 수·진단과 메모 정답 요약만 저장했다. `hash-comparison.json`에는 위 변경 수를 남겼다. 문서 전체 Markdown이나 JSON은 디스크에 저장하지 않았다. 임시 pytest 파일과 변이 입력은 검증이 끝나면 삭제했다.

다음 명령의 코퍼스 인자는 공개 자료가 있는 경로로 지정한다. OLE 실물 프로브에는 검증 환경의 `olefile`이 필요하지만 합성 CI 테스트와 제품에는 필요하지 않다.

```bash
/usr/bin/python3 -m scripts.probe_presentation_comments corpus/poi-src corpus/lo-src --output .codex-work/presentation-after.json
/usr/bin/python3 -m scripts.probe_xls_comment_cells corpus/poi-src corpus/lo-src --output .codex-work/xls-after.json
/usr/bin/python3 -m scripts.probe_error_sweep corpus/poi-src corpus/lo-src --format ppt --format pptx --format xls --hash-output --output .codex-work/full-after.jsonl
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```
