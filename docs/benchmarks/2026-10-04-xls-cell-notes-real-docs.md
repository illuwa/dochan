# XLS 셀 메모 본문 실물 검증

XLS의 `NOTE.idObj`를 같은 시트의 `Obj.ftCmo.id`에 연결하고, 그 객체의 `TxO.cchText`와 뒤따르는 `Continue` 문자열을 읽었다. 본문은 작성자 뒤에 붙여 XLSX와 같은 `[comment: 작성자: 본문]` 표기로 낸다. 본문에 작성자가 이미 적혀 있으면 중복을 제거하지 않는다. `SimpleWithComments.xls`의 본문 `Yegor Kozlov:\nfirst cell`은 Markdown 표에서 줄바꿈을 공백으로 표시하므로 동명 XLSX의 표기와 일치한다.

| 칸 | 표본 파일(POI 공개 파일명) | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLS 주석/코멘트 | `SimpleWithComments.xls` | 동명 `SimpleWithComments.xlsx`의 셀 주석 3개와 POI `TestExcelExtractor.java:176-195`의 본문 단언이다. | `Yegor Kozlov: Yegor Kozlov: first/second/third cell` 3개이다. | 셀 3개의 작성자와 본문이 XLSX 출력과 3/3 일치했고 오류는 없었다. | 통과했다. |
| XLS 주석/코멘트 | `comments.xls` | 동명 `comments.xlsx`의 row3 주석 1개와 XLS의 NOTE 3개·Obj 3개·TxO 3개의 원시 바이트이다. | XLSX와 공통인 row3 본문은 `Sven Nissel: comment top row3 (index2)`이며, XLS에만 있는 row1·row4 메모도 보존한다. | 공통 본문 1/1이 일치했다. XLS의 세 메모 모두 본문을 냈고 오류는 없었다. | 통과했다. XLS와 XLSX의 메모 수 차이는 원본 차이이다. |
| XLS 주석/코멘트 | `StringContinueRecords.xls` | 원시 NOTE·Obj·TxO·Continue 레코드와 셀 출력이다. | 작성자와 본문을 이어서 낸다. | `Bruno Lefebvre` 작성자의 본문을 복원했다. | 통과했다. |
| XLS 주석/코멘트 | POI XLS 417개 전체 | 각 파일의 수정 전후 Markdown SHA-256·문자 수·오류 목록과 원시 NOTE 레코드 수이다. | 메모가 없는 문서는 Markdown이 그대로여야 한다. | 29개 파일의 Markdown만 바뀌었고 모두 메모가 있는 파일이었다. 새 오류·경고는 0건이었다. 원시 NOTE가 있는 30개 중 손상된 퍼저 표본 1개는 기존과 같이 출력을 생략했으며, 나머지 29개에서 주석 444개를 냈다. | 정상 표본에서 통과했고 손상 표본은 안전하게 생략했다. |

LibreOffice 공개 XLS 303개에도 같은 해시 검사를 적용했다. `forum-en-29552.xls`, `forum-mso-en4-368528.xls`, `pictureOrder.xls`, `universal-content.xls`의 네 파일만 바뀌었으며 모두 원시 NOTE가 있다. 나머지 299개는 Markdown 해시가 같았다. 네 파일의 메모 66개를 출력했고 새 오류·경고는 없었다.

`scripts.compare_office_pairs`를 POI document·slideshow·spreadsheet 경로에 실행한 결과 주석 지표는 수정 전 0/4에서 수정 후 4/4로 올랐다. `SimpleWithComments.xls`는 3/3, `comments.xls`는 동명 XLSX에 존재하는 1/1이 일치했다. 후자의 XLS 전용 메모 2개는 비교기의 정답 수에 포함되지 않지만, 원시 NOTE의 셀 위치와 Obj·TxO 본문으로 확인했다.

합성 BIFF8 단위 테스트는 압축 문자열과 UTF-16 문자열이 서로 다른 Continue에 이어지는 경우, 숨김 메모, ID 불일치, 빈 본문, 작성자 없는 본문, 손상·과대 길이의 경고와 안전한 생략을 확인한다. 전체 테스트는 5208개 통과, 36개 건너뜀, 14개 예상 실패였고 `lxml` import 차단 시도는 0건이었다. `ruff check dochan scripts tests`도 통과했다.

README의 XLS `주석/코멘트` 칸은 이미 ✅이다. 본문 누락을 수정하고 단위 테스트와 공개 실물 검증을 통과했으므로 ✅ 유지를 제안한다. 손상된 퍼저 표본의 NOTE 1개는 출력되지 않으므로 정상 메모의 완전 복원 수치에 포함하지 않았다.
